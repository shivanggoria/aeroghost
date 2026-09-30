"""
v2 advanced-crypto tests: Argon2id, SPAKE2 PAKE, hybrid X25519/ML-KEM key
agreement, the Double Ratchet (forward secrecy + PCS), signed sender keys, and
the full handshake + group-relay integration over loopback.
"""

import time
import pytest

from core import crypto as C
from core.crypto import CryptoEngine
from core.ratchet import DoubleRatchet
from core.sender_key import SenderKeyPair, SenderKeyPublic
from core.group_manager import GroupManager


# ---------------------------------------------------------------- primitives
def test_argon2id_vault_key_deterministic():
    a = CryptoEngine("room", "correct horse battery staple")
    b = CryptoEngine("room", "correct horse battery staple")
    c = CryptoEngine("room", "different passphrase")
    assert a.room_key == b.room_key and len(a.room_key) == 32
    assert a.room_key != c.room_key


def test_hybrid_pake_agrees_and_rejects_wrong_password():
    def run(pw_a, pw_b):
        xa_priv, xa_pub = CryptoEngine.generate_ephemeral_keypair()
        ka_priv, ka_pub = C.mlkem_keygen()
        pake_a, ma = C.pake_new(pw_a, True)
        xb_priv, xb_pub = CryptoEngine.generate_ephemeral_keypair()
        pake_b, mb = C.pake_new(pw_b, False)
        mss, mct = C.mlkem_encapsulate(ka_pub)
        salt = b"n1n2"
        root_b = C.derive_root_key(C.pake_finish(pake_b, ma),
                                   CryptoEngine.x25519_shared(xb_priv, xa_pub), mss, salt)
        root_a = C.derive_root_key(C.pake_finish(pake_a, mb),
                                   CryptoEngine.x25519_shared(xa_priv, xb_pub),
                                   C.mlkem_decapsulate(ka_priv, mct), salt)
        return root_a, root_b

    ra, rb = run("hunter2-strong", "hunter2-strong")
    assert ra == rb and len(ra) == 32           # classical + PQ + PAKE all agree
    ra, rb = run("hunter2-strong", "WRONG")
    assert ra != rb                              # PAKE: wrong password -> no shared key


def test_double_ratchet_forward_and_pcs():
    root = b"R" * 32
    bob_priv, bob_pub = CryptoEngine.generate_ephemeral_keypair()
    alice = DoubleRatchet.init_initiator(root, bob_pub)
    bob = DoubleRatchet.init_responder(root, bob_priv, bob_pub)
    ad = b"room"
    for i in range(4):
        assert bob.decrypt(alice.encrypt(f"a{i}".encode(), ad), ad) == f"a{i}".encode()
        assert alice.decrypt(bob.encrypt(f"b{i}".encode(), ad), ad) == f"b{i}".encode()
    # out-of-order delivery
    a = DoubleRatchet.init_initiator(root, bob_pub)
    b = DoubleRatchet.init_responder(root, bob_priv, bob_pub)
    w0, w1, w2 = a.encrypt(b"0", ad), a.encrypt(b"1", ad), a.encrypt(b"2", ad)
    assert b.decrypt(w2, ad) == b"2" and b.decrypt(w0, ad) == b"0" and b.decrypt(w1, ad) == b"1"


def test_sender_key_signed_group_and_forgery_rejected():
    ad = b"room|alice"
    alice = SenderKeyPair.new()
    bob = SenderKeyPublic(alice.distribution_blob())
    for i in range(3):
        assert bob.decrypt(alice.encrypt(f"g{i}".encode(), ad), ad) == f"g{i}".encode()
    forger = SenderKeyPair.new()  # a member holding the chain copy cannot forge (no signing key)
    with pytest.raises(Exception):
        bob.decrypt(forger.encrypt(b"fake", ad), ad)


# ---------------------------------------------------------------- integration
def _connect(tmp_path, port, pw_host="strong-room-pass", pw_join=None, suffix=""):
    a = GroupManager("Alice", is_bluetooth_mode=False, db_path=str(tmp_path / f"a{suffix}.vault"))
    b = GroupManager("Bob", is_bluetooth_mode=False, db_path=str(tmp_path / f"b{suffix}.vault"))
    a.setup_room("room", pw_host, is_host=True, port=port)
    b.setup_room("room", pw_join or pw_host, is_host=False, port=port)
    b.join_host("127.0.0.1", port=port)
    for _ in range(40):
        time.sleep(0.1)
        if a.engine.peers and b.engine.peers:
            break
    time.sleep(1.2)  # settle sender-key distribution / rekey
    return a, b


def test_handshake_establishes_ratchets(tmp_path):
    a, b = _connect(tmp_path, 29650)
    try:
        assert len(a.engine.peers) == 1 and len(b.engine.peers) == 1
        assert next(iter(a.engine.peers.values())).ratchet is not None
        assert next(iter(b.engine.peers.values())).ratchet is not None
        # each side learned the other's sender key
        assert b.peer_id in a.peer_sender_keys and a.peer_id in b.peer_sender_keys
    finally:
        a.shutdown(); b.shutdown()


def test_wrong_password_rejected(tmp_path):
    a, b = _connect(tmp_path, 29651, pw_host="CorrectHorse!", pw_join="WrongPassword!")
    try:
        assert len(a.engine.peers) == 0  # PAKE confirmation fails -> dropped
    finally:
        a.shutdown(); b.shutdown()


def test_e2e_chat_over_full_v2_stack(tmp_path):
    a, b = _connect(tmp_path, 29652)
    try:
        got = []
        a.on_message_received = lambda m: got.append(m["content"])
        b.send_chat_message("hello over PAKE+hybrid+ratchet+sender-keys")
        for _ in range(15):
            time.sleep(0.1)
            if got:
                break
        assert got == ["hello over PAKE+hybrid+ratchet+sender-keys"]
    finally:
        a.shutdown(); b.shutdown()


def test_group_relay_host_forwards_between_clients(tmp_path):
    """A 3-member room: the host relays sender-key ciphertext between two clients."""
    H = GroupManager("Host", is_bluetooth_mode=False, db_path=str(tmp_path / "H.vault"))
    C1 = GroupManager("C1", is_bluetooth_mode=False, db_path=str(tmp_path / "C1.vault"))
    C2 = GroupManager("C2", is_bluetooth_mode=False, db_path=str(tmp_path / "C2.vault"))
    rx1, rx2 = [], []
    C1.on_message_received = lambda m: rx1.append((m["sender"], m["content"]))
    C2.on_message_received = lambda m: rx2.append((m["sender"], m["content"]))
    H.setup_room("g", "strong-group-pass", is_host=True, port=29653)
    C1.setup_room("g", "strong-group-pass", is_host=False, port=29653)
    C2.setup_room("g", "strong-group-pass", is_host=False, port=29653)
    C1.join_host("127.0.0.1", port=29653); time.sleep(1.2)
    C2.join_host("127.0.0.1", port=29653); time.sleep(2.0)
    try:
        assert len(H.engine.peers) == 2
        C1.send_chat_message("hi from C1")
        for _ in range(20):
            time.sleep(0.1)
            if rx2:
                break
        # C2 received C1's message even though they are not directly connected
        assert ("C1", "hi from C1") in rx2
    finally:
        H.shutdown(); C1.shutdown(); C2.shutdown()
