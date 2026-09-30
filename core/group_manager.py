"""
Group Manager and Message Routing Engine for AeroGhost
Coordinates peer discovery, challenge-response mutual authentication,
message deduplication, and star-relay broadcasting.
"""

import time
import uuid
from collections import deque
from typing import Dict, List, Any, Optional, Callable
from core.crypto import CryptoEngine
from core.protocol import Protocol, PacketType
from core.storage import SecureStorage
from core.file_transfer import OutgoingFileTransfer, IncomingFileTransfer, FileTransferState
from core.bluetooth_engine import BluetoothEngine, PeerConnection


class GroupManager:
    """Orchestrates room topology, mutual authentication, messaging, and file transfers."""

    # Upper bound on the message-id dedup cache so long sessions do not leak memory.
    SEEN_MESSAGE_LIMIT = 8192

    def __init__(self, nickname: str, is_bluetooth_mode: bool = True, db_path: str = "aeroghost_history.vault"):
        self.nickname = nickname.strip()
        self.peer_id = str(uuid.uuid4())[:8]  # Short 8-char local peer ID
        self.is_bluetooth_mode = is_bluetooth_mode
        self.storage = SecureStorage(db_path=db_path)
        self.engine = BluetoothEngine(is_bluetooth_mode=is_bluetooth_mode)
        
        self.crypto: Optional[CryptoEngine] = None
        self.room_name: Optional[str] = None
        self.is_host: bool = False
        
        # Peer handshake states: peer_conn -> {"nonce_sent": bytes, "peer_nonce": bytes, "pending": bool}
        self._pending_handshakes: Dict[PeerConnection, Dict[str, Any]] = {}
        # Bounded message-id dedup cache (set for O(1) lookup, deque for FIFO eviction).
        self._seen_msg_ids = set()
        self._seen_order: deque = deque()

        # File transfers
        self.outgoing_transfers: Dict[str, OutgoingFileTransfer] = {}  # transfer_id -> Outgoing
        self.incoming_transfers: Dict[str, IncomingFileTransfer] = {}  # transfer_id -> Incoming
        self._transfer_sources: Dict[str, PeerConnection] = {}  # transfer_id -> offering peer
        
        # UI Event Callbacks
        self.on_message_received: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_peer_joined: Optional[Callable[[str, str], None]] = None  # (peer_id, nickname)
        self.on_peer_left: Optional[Callable[[str, str], None]] = None    # (peer_id, nickname)
        self.on_peers_updated: Optional[Callable[[List[Dict[str, str]]], None]] = None
        self.on_file_offered: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_file_progress: Optional[Callable[[str, float, str], None]] = None # (id, pct, filename)
        self.on_file_completed: Optional[Callable[[str, str, bool], None]] = None # (id, filename, success)

        # Wire transport callbacks
        self.engine.on_frame_received = self._handle_raw_frame
        self.engine.on_peer_disconnected = self._handle_peer_disconnected

    def setup_room(self, room_name: str, password: str, is_host: bool = True, port: Optional[int] = None) -> bool:
        """Sets up cryptographic room context and begins listening if host."""
        self.room_name = room_name.strip()
        self.is_host = is_host
        self.crypto = CryptoEngine(self.room_name, password)
        self.storage.register_room(self.room_name, self.crypto.room_salt)

        if is_host:
            return self.engine.start_listener(port=port)
        return True

    def join_host(self, host_address: str, port: Optional[int] = None) -> bool:
        """Connects to a host/coordinator peer and initiates challenge-response handshake."""
        if not self.crypto:
            return False

        peer_conn = self.engine.connect_to_peer(host_address, port=port)
        if not peer_conn:
            return False

        # Initiate handshake: send AUTH_HELLO with our ephemeral DH public key.
        nonce_a = self.crypto.generate_challenge()
        eph_priv, eph_pub = self.crypto.generate_ephemeral_keypair()
        self._pending_handshakes[peer_conn] = {
            "nonce_a": nonce_a,
            "eph_priv": eph_priv,
            "role": "INITIATOR",
        }

        hello_packet = {
            "type": PacketType.AUTH_HELLO,
            "nonce": nonce_a.hex(),
            "eph_pub": eph_pub.hex(),
            "peer_id": self.peer_id,
            "nickname": self.nickname,
            "room_name": self.room_name,
        }
        self._send_packet(peer_conn, hello_packet)
        return True

    def _send_packet(self, peer_conn: PeerConnection, packet_dict: Dict[str, Any]) -> bool:
        """
        Encrypts and transmits a packet to a specific peer connection.

        Uses that peer's forward-secret session key once the handshake has
        established one; before that (the AUTH_* handshake itself) it uses the
        room key, since no session key exists yet.
        """
        if not self.crypto:
            return False
        try:
            raw_bytes = Protocol.serialize(packet_dict)
            key = peer_conn.session_key or self.crypto.room_key
            encrypted = CryptoEngine.encrypt_with_key(key, raw_bytes, associated_data=self.room_name.encode("utf-8"))
            return peer_conn.send_frame(encrypted)
        except Exception:
            return False

    def _broadcast_packet(self, packet_dict: Dict[str, Any], exclude_peer_id: Optional[str] = None):
        """
        Encrypts a packet separately under each authenticated peer's session key
        and sends it. With forward secrecy every link has its own key, so a single
        shared ciphertext can no longer be broadcast to everyone.
        """
        if not self.crypto:
            return
        raw_bytes = Protocol.serialize(packet_dict)
        ad = self.room_name.encode("utf-8")
        for peer in list(self.engine.peers.values()):
            if exclude_peer_id and peer.peer_id == exclude_peer_id:
                continue
            if not peer.session_key:
                continue
            try:
                enc = CryptoEngine.encrypt_with_key(peer.session_key, raw_bytes, associated_data=ad)
                peer.send_frame(enc)
            except Exception:
                continue

    def _handle_raw_frame(self, peer_conn: PeerConnection, encrypted_frame: bytes):
        """Decrypts frame and routes to appropriate protocol handler."""
        if not self.crypto:
            peer_conn.close()
            return

        # Once the session key is set, all traffic uses it; the handshake packets
        # that precede it are encrypted under the room key.
        key = peer_conn.session_key or self.crypto.room_key
        try:
            decrypted = CryptoEngine.decrypt_with_key(key, encrypted_frame, associated_data=self.room_name.encode("utf-8"))
            packet = Protocol.deserialize(decrypted)
        except Exception:
            # Tampered or invalid key: drop peer immediately
            peer_conn.close()
            return

        pkt_type = packet.get("type")
        
        # Handshake handling
        if pkt_type == PacketType.AUTH_HELLO:
            self._on_auth_hello(peer_conn, packet)
        elif pkt_type == PacketType.AUTH_CHALLENGE:
            self._on_auth_challenge(peer_conn, packet)
        elif pkt_type == PacketType.AUTH_VERIFIED:
            self._on_auth_verified(peer_conn, packet)
        
        # Only process regular packets if peer is authenticated
        elif peer_conn.is_authenticated:
            if pkt_type == PacketType.CHAT_MESSAGE:
                self._on_chat_message(peer_conn, packet)
            elif pkt_type == PacketType.PEER_LIST:
                self._on_peer_list(peer_conn, packet)
            elif pkt_type == PacketType.PEER_JOIN:
                self._on_peer_join(peer_conn, packet)
            elif pkt_type == PacketType.FILE_OFFER:
                self._on_file_offer(peer_conn, packet)
            elif pkt_type == PacketType.FILE_ACCEPT:
                self._on_file_accept(peer_conn, packet)
            elif pkt_type == PacketType.FILE_CHUNK:
                self._on_file_chunk(peer_conn, packet)
            elif pkt_type == PacketType.FILE_COMPLETE:
                self._on_file_complete(peer_conn, packet)

    def _on_auth_hello(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        """Receiver receives AUTH_HELLO."""
        try:
            nonce_a = bytes.fromhex(packet["nonce"])
            peer_eph_pub = bytes.fromhex(packet["eph_pub"])
            peer_conn.peer_id = packet.get("peer_id", str(uuid.uuid4())[:8])
            peer_conn.nickname = packet.get("nickname", "Peer")

            # Compute response for Alice, generate Bob's challenge
            resp_a = self.crypto.compute_response(nonce_a, role_tag="PEER_B_AUTH")
            nonce_b = self.crypto.generate_challenge()

            # Ephemeral DH: derive the forward-secret session key now that we have
            # the peer's ephemeral public key. Salt binds it to both handshake nonces.
            eph_priv, eph_pub = self.crypto.generate_ephemeral_keypair()
            session_key = self.crypto.derive_session_key(eph_priv, peer_eph_pub, salt=nonce_a + nonce_b)

            self._pending_handshakes[peer_conn] = {
                "nonce_a": nonce_a,
                "nonce_b": nonce_b,
                "session_key": session_key,
                "role": "RESPONDER"
            }

            challenge_packet = {
                "type": PacketType.AUTH_CHALLENGE,
                "response_to_hello": resp_a.hex(),
                "nonce_b": nonce_b.hex(),
                "eph_pub": eph_pub.hex(),
                "peer_id": self.peer_id,
                "nickname": self.nickname,
            }
            self._send_packet(peer_conn, challenge_packet)
        except Exception:
            peer_conn.close()

    def _on_auth_challenge(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        """Initiator receives AUTH_CHALLENGE."""
        handshake = self._pending_handshakes.get(peer_conn)
        if not handshake:
            peer_conn.close()
            return
        
        try:
            resp_a = bytes.fromhex(packet["response_to_hello"])
            nonce_b = bytes.fromhex(packet["nonce_b"])
            peer_eph_pub = bytes.fromhex(packet["eph_pub"])

            # Verify Bob's response to Alice's challenge
            if not self.crypto.verify_response(handshake["nonce_a"], resp_a, role_tag="PEER_B_AUTH"):
                peer_conn.close()
                return

            # Set peer details
            peer_conn.peer_id = packet.get("peer_id", str(uuid.uuid4())[:8])
            peer_conn.nickname = packet.get("nickname", "Peer")
            peer_conn.is_authenticated = True

            # Ephemeral DH: derive the same forward-secret session key as the peer.
            session_key = self.crypto.derive_session_key(
                handshake["eph_priv"], peer_eph_pub, salt=handshake["nonce_a"] + nonce_b
            )

            # Compute Alice's response to Bob's challenge
            resp_b = self.crypto.compute_response(nonce_b, role_tag="PEER_A_AUTH")

            verified_packet = {
                "type": PacketType.AUTH_VERIFIED,
                "response_to_challenge": resp_b.hex(),
            }
            # Send VERIFIED under the room key (session_key not yet active), then
            # switch this connection over to the session key for all later traffic.
            self._send_packet(peer_conn, verified_packet)
            peer_conn.session_key = session_key

            # Register authenticated peer
            self.engine.register_authenticated_peer(peer_conn)
            self.storage.update_trusted_peer(peer_conn.peer_id, peer_conn.nickname, self.room_name)
            del self._pending_handshakes[peer_conn]
            
            if self.on_peer_joined:
                self.on_peer_joined(peer_conn.peer_id, peer_conn.nickname)
            self._notify_peer_list()
        except Exception:
            peer_conn.close()

    def _on_auth_verified(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        """Responder receives AUTH_VERIFIED."""
        handshake = self._pending_handshakes.get(peer_conn)
        if not handshake:
            peer_conn.close()
            return
            
        try:
            resp_b = bytes.fromhex(packet["response_to_challenge"])
            if not self.crypto.verify_response(handshake["nonce_b"], resp_b, role_tag="PEER_A_AUTH"):
                peer_conn.close()
                return

            peer_conn.is_authenticated = True
            # Activate the forward-secret session key derived in _on_auth_hello,
            # before any broadcast so this peer's first packets use it.
            peer_conn.session_key = handshake["session_key"]
            self.engine.register_authenticated_peer(peer_conn)
            self.storage.update_trusted_peer(peer_conn.peer_id, peer_conn.nickname, self.room_name)
            del self._pending_handshakes[peer_conn]
            
            # If coordinator, send current peer list to new member & announce to others
            if self.is_host:
                self._broadcast_peer_list()
                
            if self.on_peer_joined:
                self.on_peer_joined(peer_conn.peer_id, peer_conn.nickname)
            self._notify_peer_list()
        except Exception:
            peer_conn.close()

    def _broadcast_peer_list(self):
        """Host sends updated member roster to all connected peers."""
        self._broadcast_packet({"type": PacketType.PEER_LIST, "peers": self.get_roster()})

    def _on_peer_list(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        peers = packet.get("peers", [])
        if self.on_peers_updated:
            self.on_peers_updated(peers)

    def _on_peer_join(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        pid = packet.get("peer_id", "")
        nick = packet.get("nickname", "Peer")
        if self.on_peer_joined:
            self.on_peer_joined(pid, nick)
        self._notify_peer_list()

    def _handle_peer_disconnected(self, peer_conn: PeerConnection):
        if peer_conn in self._pending_handshakes:
            del self._pending_handshakes[peer_conn]
        if self.on_peer_left:
            self.on_peer_left(peer_conn.peer_id or "unknown", peer_conn.nickname)
        self._notify_peer_list()

    def get_roster(self) -> List[Dict[str, str]]:
        """Returns the current room roster (this node first, then authenticated peers)."""
        roster = [{"id": self.peer_id, "nickname": self.nickname}]
        for p in self.engine.peers.values():
            roster.append({"id": p.peer_id, "nickname": p.nickname})
        return roster

    def _mark_seen(self, msg_id: str):
        """Record a message id in the bounded dedup cache, evicting the oldest when full."""
        if msg_id in self._seen_msg_ids:
            return
        self._seen_msg_ids.add(msg_id)
        self._seen_order.append(msg_id)
        while len(self._seen_order) > self.SEEN_MESSAGE_LIMIT:
            self._seen_msg_ids.discard(self._seen_order.popleft())

    def _notify_peer_list(self):
        if self.on_peers_updated:
            self.on_peers_updated(self.get_roster())

    def send_chat_message(self, text: str) -> Dict[str, Any]:
        """Encrypts and broadcasts chat message to the room."""
        msg_id = str(uuid.uuid4())
        timestamp = time.time()
        msg_packet = {
            "type": PacketType.CHAT_MESSAGE,
            "id": msg_id,
            "sender": self.nickname,
            "sender_id": self.peer_id,
            "content": text,
            "timestamp": timestamp,
        }
        
        self._mark_seen(msg_id)
        # Encrypt per-peer under each session key and send
        self._broadcast_packet(msg_packet)

        # Save to local encrypted history
        self.storage.save_message(self.crypto, msg_id, msg_packet)
        return msg_packet

    def _on_chat_message(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        msg_id = packet.get("id")
        if not msg_id or msg_id in self._seen_msg_ids:
            return

        self._mark_seen(msg_id)

        # Save to local encrypted history
        self.storage.save_message(self.crypto, msg_id, packet)
        
        # If host coordinator, relay to other peers (Star-Relay topology)
        if self.is_host:
            self._broadcast_packet(packet, exclude_peer_id=peer_conn.peer_id)

        if self.on_message_received:
            self.on_message_received(packet)

    def send_file(self, file_path: str) -> Optional[OutgoingFileTransfer]:
        """Creates an outgoing file transfer and broadcasts FILE_OFFER to room."""
        transfer = OutgoingFileTransfer(file_path, self.nickname)
        self.outgoing_transfers[transfer.transfer_id] = transfer
        
        offer = transfer.create_offer_packet()
        self._broadcast_packet(offer)
        return transfer

    def _on_file_offer(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        """Peer is offering a file."""
        tid = packet["transfer_id"]
        incoming = IncomingFileTransfer(packet)
        self.incoming_transfers[tid] = incoming
        self._transfer_sources[tid] = peer_conn  # remember who offered, for a targeted accept

        if self.on_file_offered:
            self.on_file_offered(packet)

    def accept_file(self, transfer_id: str):
        """Accepts a file transfer and asks the offering peer to start streaming."""
        incoming = self.incoming_transfers.get(transfer_id)
        if not incoming:
            return

        accept_pkt = {
            "type": PacketType.FILE_ACCEPT,
            "transfer_id": transfer_id,
            "receiver_id": self.peer_id,
        }
        source = self._transfer_sources.get(transfer_id)
        if source is not None:
            # Reply only to the peer that offered the file, so a group room does
            # not make every member start streaming the same transfer.
            self._send_packet(source, accept_pkt)
        else:
            self._broadcast_packet(accept_pkt)

    def _on_file_accept(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        """Peer accepted our file; stream chunks."""
        tid = packet.get("transfer_id")
        transfer = self.outgoing_transfers.get(tid)
        if not transfer:
            return
        
        # Stream chunks in background thread
        import threading
        def _stream():
            for i, chunk_bytes in transfer.iter_chunks():
                chunk_pkt = {
                    "type": PacketType.FILE_CHUNK,
                    "transfer_id": tid,
                    "chunk_index": i,
                    "data_b64": Protocol.encode_bytes(chunk_bytes),
                }
                self._send_packet(peer_conn, chunk_pkt)
                time.sleep(0.005)  # Yield CPU slightly for Bluetooth MTU

                pct = ((i + 1) / transfer.total_chunks) * 100.0
                if self.on_file_progress:
                    self.on_file_progress(tid, pct, transfer.filename)
            
            # Send completion
            comp_pkt = {"type": PacketType.FILE_COMPLETE, "transfer_id": tid}
            self._send_packet(peer_conn, comp_pkt)
            if self.on_file_completed:
                self.on_file_completed(tid, transfer.filename, True)
                
        t = threading.Thread(target=_stream, daemon=True)
        t.start()

    def _on_file_chunk(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        tid = packet.get("transfer_id")
        incoming = self.incoming_transfers.get(tid)
        if not incoming:
            return
        
        idx = int(packet["chunk_index"])
        chunk_bytes = Protocol.decode_bytes(packet["data_b64"])
        incoming.write_chunk(idx, chunk_bytes)
        
        if self.on_file_progress:
            self.on_file_progress(tid, incoming.progress_percent, incoming.filename)

    def _on_file_complete(self, peer_conn: PeerConnection, packet: Dict[str, Any]):
        tid = packet.get("transfer_id")
        incoming = self.incoming_transfers.get(tid)
        if not incoming:
            return
        
        verified = incoming.finalize()
        self._transfer_sources.pop(tid, None)
        if self.on_file_completed:
            self.on_file_completed(tid, incoming.filename, verified)

    def shutdown(self):
        """Clean shutdown of transport engine and all connections."""
        self.engine.stop()
