"""
Group Manager and Message Routing Engine for AeroGhost (v2).

Security architecture:
  - Handshake: SPAKE2 PAKE (no offline dictionary attack) combined with a hybrid
    X25519 + ML-KEM-768 key agreement, mutually confirmed. Handshake packets are
    sent in clear -- SPAKE2 messages and public keys are safe to expose.
  - Transport: a per-peer Double Ratchet (core/ratchet.py) protects every 1:1 link
    (host<->client), giving per-message keys and post-compromise security.
  - Group content: sender keys (core/sender_key.py). Each member signs+encrypts
    once with their own sender key; the relay host forwards opaque ciphertext and
    cannot forge it. Sender keys are re-issued on every membership change.
"""

import time
import uuid
from collections import deque
from typing import Dict, List, Any, Optional, Callable

from core import crypto as C
from core.crypto import CryptoEngine
from core.protocol import Protocol, PacketType
from core.storage import SecureStorage
from core.file_transfer import OutgoingFileTransfer, IncomingFileTransfer, FileTransferState
from core.bluetooth_engine import BluetoothEngine, PeerConnection
from core.ratchet import DoubleRatchet
from core.sender_key import SenderKeyPair, SenderKeyPublic


class GroupManager:
    """Orchestrates room topology, authentication, messaging, and file transfers."""

    SEEN_MESSAGE_LIMIT = 8192
    # Group-content packet types the host relays (as opaque ciphertext) to other members.
    BROADCAST_RELAY_TYPES = {PacketType.GROUP_MSG, PacketType.SENDER_KEY_DIST, PacketType.FILE_OFFER}

    def __init__(self, nickname: str, is_bluetooth_mode: bool = True, db_path: str = "aeroghost_history.vault"):
        self.nickname = nickname.strip()
        self.peer_id = str(uuid.uuid4())[:8]
        self.is_bluetooth_mode = is_bluetooth_mode
        self.storage = SecureStorage(db_path=db_path)
        self.engine = BluetoothEngine(is_bluetooth_mode=is_bluetooth_mode)

        self.crypto: Optional[CryptoEngine] = None
        self.password: str = ""
        self.room_name: Optional[str] = None
        self.is_host: bool = False

        self._pending_handshakes: Dict[PeerConnection, Dict[str, Any]] = {}
        self._seen_msg_ids = set()
        self._seen_order: deque = deque()
        # Peers we have received a ratchet message from (host can only send to a
        # peer after its first message, since the ratchet responder cannot send first).
        self._ratchet_ready: set = set()

        # Group encryption state
        self.my_sender_key: Optional[SenderKeyPair] = None
        self.peer_sender_keys: Dict[str, SenderKeyPublic] = {}  # sender_id -> their sender key

        # File transfers
        self.outgoing_transfers: Dict[str, OutgoingFileTransfer] = {}
        self.incoming_transfers: Dict[str, IncomingFileTransfer] = {}
        self._offer_from: Dict[str, str] = {}  # transfer_id -> offerer peer_id

        # UI callbacks
        self.on_message_received: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_peer_joined: Optional[Callable[[str, str], None]] = None
        self.on_peer_left: Optional[Callable[[str, str], None]] = None
        self.on_peers_updated: Optional[Callable[[List[Dict[str, str]]], None]] = None
        self.on_file_offered: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_file_progress: Optional[Callable[[str, float, str], None]] = None
        self.on_file_completed: Optional[Callable[[str, str, bool], None]] = None

        self.engine.on_frame_received = self._handle_raw_frame
        self.engine.on_peer_disconnected = self._handle_peer_disconnected

    # ==================================================================
    # Setup / connect
    # ==================================================================
    def setup_room(self, room_name: str, password: str, is_host: bool = True, port: Optional[int] = None) -> bool:
        self.room_name = room_name.strip()
        self.password = password
        self.is_host = is_host
        self.crypto = CryptoEngine(self.room_name, password)
        self.my_sender_key = SenderKeyPair.new()
        self.storage.register_room(self.room_name, self.crypto.room_salt)
        if is_host:
            return self.engine.start_listener(port=port)
        return True

    def join_host(self, host_address: str, port: Optional[int] = None) -> bool:
        if not self.crypto:
            return False
        peer_conn = self.engine.connect_to_peer(host_address, port=port)
        if not peer_conn:
            return False

        # Initiator: SPAKE2 msg + ephemeral X25519 + ML-KEM public key, all in clear.
        pake, pake_msg = C.pake_new(self.password, is_initiator=True)
        xa_priv, xa_pub = self.crypto.generate_ephemeral_keypair()
        ka_priv, ka_pub = C.mlkem_keygen()
        nonce_a = self.crypto.generate_challenge()
        self._pending_handshakes[peer_conn] = {
            "role": "INITIATOR", "pake": pake, "pake_msg": pake_msg,
            "xa_priv": xa_priv, "xa_pub": xa_pub, "ka_priv": ka_priv, "ka_pub": ka_pub,
            "nonce_a": nonce_a,
        }
        self._send_plain(peer_conn, {
            "type": PacketType.PAKE_HELLO,
            "pake": Protocol.encode_bytes(pake_msg),
            "xpub": Protocol.encode_bytes(xa_pub),
            "kpub": Protocol.encode_bytes(ka_pub),
            "nonce": Protocol.encode_bytes(nonce_a),
            "peer_id": self.peer_id, "nickname": self.nickname, "room_name": self.room_name,
        })
        return True

    # ==================================================================
    # Transport (plain handshake frames, then Double Ratchet)
    # ==================================================================
    def _send_plain(self, peer_conn: PeerConnection, packet: Dict[str, Any]) -> bool:
        """Send a cleartext handshake frame (used only before the ratchet exists)."""
        try:
            return peer_conn.send_frame(Protocol.serialize(packet))
        except Exception:
            return False

    def _send_packet(self, peer_conn: PeerConnection, packet: Dict[str, Any]) -> bool:
        """Send a ratchet-encrypted frame to a fully-authenticated peer."""
        if peer_conn.ratchet is None:
            return False
        try:
            wire = peer_conn.ratchet.encrypt(Protocol.serialize(packet), self.room_name.encode("utf-8"))
            return peer_conn.send_frame(wire)
        except Exception:
            return False

    def _broadcast_packet(self, packet: Dict[str, Any], exclude_peer_id: Optional[str] = None):
        """Send to every connected peer over its own ratchet (a client's only peer is the host)."""
        for peer in list(self.engine.peers.values()):
            if exclude_peer_id and peer.peer_id == exclude_peer_id:
                continue
            self._send_packet(peer, packet)

    def _route_out(self, packet: Dict[str, Any], to_peer_id: str) -> bool:
        """Send a unicast packet toward to_peer_id, directly if connected else via the host."""
        packet = dict(packet, to=to_peer_id)
        dest = self.engine.peers.get(to_peer_id)
        if dest is not None and dest.ratchet is not None:
            return self._send_packet(dest, packet)
        for peer in self.engine.peers.values():  # not directly connected -> hand to host
            if peer.ratchet is not None:
                return self._send_packet(peer, packet)
        return False

    def _handle_raw_frame(self, peer_conn: PeerConnection, frame: bytes):
        if not self.crypto:
            peer_conn.close()
            return
        try:
            if peer_conn.ratchet is None:
                packet = Protocol.deserialize(frame)  # cleartext handshake
            else:
                plaintext = peer_conn.ratchet.decrypt(frame, self.room_name.encode("utf-8"))
                packet = Protocol.deserialize(plaintext)
        except Exception:
            peer_conn.close()
            return

        ptype = packet.get("type")
        if peer_conn.ratchet is None:
            if ptype == PacketType.PAKE_HELLO:
                self._on_pake_hello(peer_conn, packet)
            elif ptype == PacketType.PAKE_REPLY:
                self._on_pake_reply(peer_conn, packet)
            elif ptype == PacketType.PAKE_CONFIRM:
                self._on_pake_confirm(peer_conn, packet)
            else:
                peer_conn.close()
            return
        self._route_authenticated(peer_conn, packet)

    # ==================================================================
    # PAKE + hybrid handshake
    # ==================================================================
    def _transcript(self, hs: Dict[str, Any]) -> bytes:
        return (hs["pake_msg_a"] + hs["pake_msg_b"] + hs["xa_pub"] + hs["xb_pub"]
                + hs["ka_pub"] + hs["mlkem_ct"] + hs["nonce_a"] + hs["nonce_b"])

    def _on_pake_hello(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        """Responder (host) handles the initiator's PAKE_HELLO."""
        try:
            pake_msg_a = Protocol.decode_bytes(packet["pake"])
            xa_pub = Protocol.decode_bytes(packet["xpub"])
            ka_pub = Protocol.decode_bytes(packet["kpub"])
            nonce_a = Protocol.decode_bytes(packet["nonce"])
            peer_conn.peer_id = packet.get("peer_id", str(uuid.uuid4())[:8])
            peer_conn.nickname = packet.get("nickname", "Peer")

            pake, pake_msg_b = C.pake_new(self.password, is_initiator=False)
            pake_key = C.pake_finish(pake, pake_msg_a)
            xb_priv, xb_pub = self.crypto.generate_ephemeral_keypair()
            x_shared = self.crypto.x25519_shared(xb_priv, xa_pub)
            mlkem_ss, mlkem_ct = C.mlkem_encapsulate(ka_pub)
            nonce_b = self.crypto.generate_challenge()
            root_key = C.derive_root_key(pake_key, x_shared, mlkem_ss, salt=nonce_a + nonce_b)

            # Responder's initial ratchet keypair (seeds the Double Ratchet).
            rb_priv, rb_pub = self.crypto.generate_ephemeral_keypair()

            hs = {
                "role": "RESPONDER", "root_key": root_key,
                "pake_msg_a": pake_msg_a, "pake_msg_b": pake_msg_b,
                "xa_pub": xa_pub, "xb_pub": xb_pub, "ka_pub": ka_pub, "mlkem_ct": mlkem_ct,
                "nonce_a": nonce_a, "nonce_b": nonce_b, "rb_priv": rb_priv, "rb_pub": rb_pub,
            }
            self._pending_handshakes[peer_conn] = hs
            conf_b = C.confirm_tag(root_key, b"B->A", self._transcript(hs))

            self._send_plain(peer_conn, {
                "type": PacketType.PAKE_REPLY,
                "pake": Protocol.encode_bytes(pake_msg_b),
                "xpub": Protocol.encode_bytes(xb_pub),
                "mlkem_ct": Protocol.encode_bytes(mlkem_ct),
                "nonce": Protocol.encode_bytes(nonce_b),
                "confirm": Protocol.encode_bytes(conf_b),
                "ratchet_pub": Protocol.encode_bytes(rb_pub),
                "peer_id": self.peer_id, "nickname": self.nickname,
            })
        except Exception:
            peer_conn.close()

    def _on_pake_reply(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        """Initiator handles PAKE_REPLY: verify, establish ratchet, send confirm."""
        hs = self._pending_handshakes.get(peer_conn)
        if not hs:
            peer_conn.close()
            return
        try:
            pake_msg_b = Protocol.decode_bytes(packet["pake"])
            xb_pub = Protocol.decode_bytes(packet["xpub"])
            mlkem_ct = Protocol.decode_bytes(packet["mlkem_ct"])
            nonce_b = Protocol.decode_bytes(packet["nonce"])
            conf_b = Protocol.decode_bytes(packet["confirm"])
            rb_pub = Protocol.decode_bytes(packet["ratchet_pub"])

            pake_key = C.pake_finish(hs["pake"], pake_msg_b)
            x_shared = self.crypto.x25519_shared(hs["xa_priv"], xb_pub)
            mlkem_ss = C.mlkem_decapsulate(hs["ka_priv"], mlkem_ct)
            root_key = C.derive_root_key(pake_key, x_shared, mlkem_ss, salt=hs["nonce_a"] + nonce_b)

            full = {
                "pake_msg_a": hs["pake_msg"], "pake_msg_b": pake_msg_b,
                "xa_pub": hs["xa_pub"], "xb_pub": xb_pub, "ka_pub": hs["ka_pub"],
                "mlkem_ct": mlkem_ct, "nonce_a": hs["nonce_a"], "nonce_b": nonce_b,
            }
            transcript = self._transcript(full)
            if not C.verify_confirm_tag(root_key, b"B->A", transcript, conf_b):
                peer_conn.close()  # wrong password (or tampering)
                return
            conf_a = C.confirm_tag(root_key, b"A->B", transcript)

            peer_conn.peer_id = packet.get("peer_id", peer_conn.peer_id or str(uuid.uuid4())[:8])
            peer_conn.nickname = packet.get("nickname", "Peer")
            peer_conn.ratchet = DoubleRatchet.init_initiator(root_key, rb_pub)
            peer_conn.is_authenticated = True

            self._send_plain(peer_conn, {
                "type": PacketType.PAKE_CONFIRM, "confirm": Protocol.encode_bytes(conf_a),
            })
            del self._pending_handshakes[peer_conn]
            self._on_peer_established(peer_conn)
        except Exception:
            peer_conn.close()

    def _on_pake_confirm(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        """Responder handles PAKE_CONFIRM: verify and establish the ratchet."""
        hs = self._pending_handshakes.get(peer_conn)
        if not hs:
            peer_conn.close()
            return
        try:
            conf_a = Protocol.decode_bytes(packet["confirm"])
            if not C.verify_confirm_tag(hs["root_key"], b"A->B", self._transcript(hs), conf_a):
                peer_conn.close()
                return
            peer_conn.ratchet = DoubleRatchet.init_responder(hs["root_key"], hs["rb_priv"], hs["rb_pub"])
            peer_conn.is_authenticated = True
            del self._pending_handshakes[peer_conn]
            self._on_peer_established(peer_conn)
        except Exception:
            peer_conn.close()

    def _on_peer_established(self, peer_conn: PeerConnection):
        """Common post-handshake: register, announce, and seed the group state.

        The client is the ratchet initiator, so it can (and does) send first -- it
        distributes its sender key immediately, which also primes the host's ratchet.
        The host is the ratchet responder and must wait for that first message before
        it can send; it performs the roster/rekey step on first contact (see routing).
        """
        self.engine.register_authenticated_peer(peer_conn)
        try:
            self.storage.update_trusted_peer(peer_conn.peer_id, peer_conn.nickname, self.room_name)
        except Exception:
            pass
        if self.on_peer_joined:
            self.on_peer_joined(peer_conn.peer_id, peer_conn.nickname)
        if not self.is_host:
            self._distribute_sender_key()  # client sends first (primes the host ratchet)
        self._notify_peer_list()

    # ==================================================================
    # Authenticated routing
    # ==================================================================
    def _route_authenticated(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        to = packet.get("to")
        if to is not None and to != self.peer_id:
            dest = self.engine.peers.get(to)   # unicast for someone else -> relay (host)
            if dest is not None and dest.ratchet is not None:
                self._send_packet(dest, packet)
            return

        # First ratchet message from this peer: the host can now send to it, so
        # treat it as a membership change (roster + group rekey).
        host_first_contact = self.is_host and peer_conn.peer_id not in self._ratchet_ready
        if peer_conn.peer_id:
            self._ratchet_ready.add(peer_conn.peer_id)

        ptype = packet.get("type")
        if ptype == PacketType.GROUP_MSG:
            self._on_group_msg(peer_conn, packet)
        elif ptype == PacketType.SENDER_KEY_DIST:
            self._on_sender_key_dist(peer_conn, packet)
        elif ptype == PacketType.GROUP_REKEY:
            self._on_group_rekey(peer_conn, packet)
        elif ptype == PacketType.PEER_LIST:
            self._on_peer_list(peer_conn, packet)
        elif ptype == PacketType.FILE_OFFER:
            self._on_file_offer(peer_conn, packet)
        elif ptype == PacketType.FILE_ACCEPT:
            self._on_file_accept(peer_conn, packet)
        elif ptype == PacketType.FILE_CHUNK:
            self._on_file_chunk(peer_conn, packet)
        elif ptype == PacketType.FILE_COMPLETE:
            self._on_file_complete(peer_conn, packet)

        # Host relays group-content packets (as opaque ciphertext) to the other members.
        if self.is_host and ptype in self.BROADCAST_RELAY_TYPES:
            self._broadcast_packet(packet, exclude_peer_id=peer_conn.peer_id)

        # On a peer's first ratchet message, the host announces the roster and
        # rotates sender keys so everyone (including the newcomer) is in sync.
        if host_first_contact:
            self._broadcast_peer_list()
            self._rekey_group()

    # ==================================================================
    # Roster / dedup
    # ==================================================================
    def get_roster(self) -> List[Dict[str, str]]:
        roster = [{"id": self.peer_id, "nickname": self.nickname}]
        for p in self.engine.peers.values():
            roster.append({"id": p.peer_id, "nickname": p.nickname})
        return roster

    def _mark_seen(self, msg_id: str):
        if msg_id in self._seen_msg_ids:
            return
        self._seen_msg_ids.add(msg_id)
        self._seen_order.append(msg_id)
        while len(self._seen_order) > self.SEEN_MESSAGE_LIMIT:
            self._seen_msg_ids.discard(self._seen_order.popleft())

    def _notify_peer_list(self):
        if self.on_peers_updated:
            self.on_peers_updated(self.get_roster())

    def _broadcast_peer_list(self):
        self._broadcast_packet({"type": PacketType.PEER_LIST, "peers": self.get_roster()})

    def _on_peer_list(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        if self.on_peers_updated:
            self.on_peers_updated(packet.get("peers", []))

    def _handle_peer_disconnected(self, peer_conn: PeerConnection):
        self._pending_handshakes.pop(peer_conn, None)
        if peer_conn.peer_id:
            self.peer_sender_keys.pop(peer_conn.peer_id, None)
            self._ratchet_ready.discard(peer_conn.peer_id)
        if self.on_peer_left:
            self.on_peer_left(peer_conn.peer_id or "unknown", peer_conn.nickname)
        if self.is_host and self.engine.peers:
            self._rekey_group()  # membership changed -> cut off the departed member
        self._notify_peer_list()

    # ==================================================================
    # Sender-key group encryption
    # ==================================================================
    def _distribute_sender_key(self):
        if not self.my_sender_key:
            return
        self._broadcast_packet({
            "type": PacketType.SENDER_KEY_DIST,
            "sender_id": self.peer_id,
            "blob": Protocol.encode_bytes(self.my_sender_key.distribution_blob()),
        })

    def _on_sender_key_dist(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        sender_id = packet.get("sender_id")
        if not sender_id or sender_id == self.peer_id:
            return
        try:
            self.peer_sender_keys[sender_id] = SenderKeyPublic(Protocol.decode_bytes(packet["blob"]))
        except Exception:
            pass

    def _rekey_group(self):
        """Host: rotate to a fresh sender key and prompt every member to do the same."""
        self.my_sender_key = SenderKeyPair.new()
        self.peer_sender_keys.clear()
        self._broadcast_packet({"type": PacketType.GROUP_REKEY})
        self._distribute_sender_key()

    def _on_group_rekey(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        """Client: on the host's signal, rotate our sender key and redistribute it."""
        self.my_sender_key = SenderKeyPair.new()
        self.peer_sender_keys.clear()
        self._distribute_sender_key()

    def send_chat_message(self, text: str) -> Dict[str, Any]:
        msg_id = str(uuid.uuid4())
        msg_packet = {
            "type": PacketType.CHAT_MESSAGE, "id": msg_id,
            "sender": self.nickname, "sender_id": self.peer_id,
            "content": text, "timestamp": time.time(),
        }
        self._mark_seen(msg_id)
        if self.my_sender_key:
            ad = self.room_name.encode("utf-8") + self.peer_id.encode("utf-8")
            content = self.my_sender_key.encrypt(Protocol.serialize(msg_packet), ad)
            self._broadcast_packet({
                "type": PacketType.GROUP_MSG, "sender_id": self.peer_id,
                "content": Protocol.encode_bytes(content),
            })
        self.storage.save_message(self.crypto, msg_id, msg_packet)
        return msg_packet

    def _on_group_msg(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        sender_id = packet.get("sender_id")
        if not sender_id or sender_id == self.peer_id:
            return
        sender_key = self.peer_sender_keys.get(sender_id)
        if sender_key is None:
            return  # sender key not distributed yet (e.g. mid-rekey); drop gracefully
        try:
            ad = self.room_name.encode("utf-8") + sender_id.encode("utf-8")
            inner = Protocol.deserialize(sender_key.decrypt(Protocol.decode_bytes(packet["content"]), ad))
        except Exception:
            return
        msg_id = inner.get("id")
        if not msg_id or msg_id in self._seen_msg_ids:
            return
        self._mark_seen(msg_id)
        self.storage.save_message(self.crypto, msg_id, inner)
        if self.on_message_received:
            self.on_message_received(inner)

    # ==================================================================
    # File transfer (point-to-point over the ratchet; unicast-routed via the host)
    # ==================================================================
    def send_file(self, file_path: str) -> Optional[OutgoingFileTransfer]:
        transfer = OutgoingFileTransfer(file_path, self.nickname)
        self.outgoing_transfers[transfer.transfer_id] = transfer
        offer = transfer.create_offer_packet()
        offer["offerer_id"] = self.peer_id
        self._broadcast_packet(offer)
        return transfer

    def _on_file_offer(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        tid = packet["transfer_id"]
        if packet.get("offerer_id") == self.peer_id:
            return
        self.incoming_transfers[tid] = IncomingFileTransfer(packet)
        self._offer_from[tid] = packet.get("offerer_id") or peer_conn.peer_id
        if self.on_file_offered:
            self.on_file_offered(packet)

    def accept_file(self, transfer_id: str):
        incoming = self.incoming_transfers.get(transfer_id)
        if not incoming:
            return
        offerer = self._offer_from.get(transfer_id)
        accept_pkt = {"type": PacketType.FILE_ACCEPT, "transfer_id": transfer_id, "receiver_id": self.peer_id}
        if offerer:
            self._route_out(accept_pkt, offerer)

    def _on_file_accept(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        tid = packet.get("transfer_id")
        transfer = self.outgoing_transfers.get(tid)
        if not transfer:
            return
        receiver_id = packet.get("receiver_id") or peer_conn.peer_id

        import threading
        def _stream():
            for i, chunk_bytes in transfer.iter_chunks():
                self._route_out({
                    "type": PacketType.FILE_CHUNK, "transfer_id": tid,
                    "chunk_index": i, "data_b64": Protocol.encode_bytes(chunk_bytes),
                }, receiver_id)
                time.sleep(0.005)
                pct = ((i + 1) / transfer.total_chunks) * 100.0
                if self.on_file_progress:
                    self.on_file_progress(tid, pct, transfer.filename)
            self._route_out({"type": PacketType.FILE_COMPLETE, "transfer_id": tid}, receiver_id)
            if self.on_file_completed:
                self.on_file_completed(tid, transfer.filename, True)

        threading.Thread(target=_stream, daemon=True).start()

    def _on_file_chunk(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        incoming = self.incoming_transfers.get(packet.get("transfer_id"))
        if not incoming:
            return
        incoming.write_chunk(int(packet["chunk_index"]), Protocol.decode_bytes(packet["data_b64"]))
        if self.on_file_progress:
            self.on_file_progress(packet.get("transfer_id"), incoming.progress_percent, incoming.filename)

    def _on_file_complete(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        tid = packet.get("transfer_id")
        incoming = self.incoming_transfers.get(tid)
        if not incoming:
            return
        verified = incoming.finalize()
        self._offer_from.pop(tid, None)
        if self.on_file_completed:
            self.on_file_completed(tid, incoming.filename, verified)

    def shutdown(self):
        self.engine.stop()
