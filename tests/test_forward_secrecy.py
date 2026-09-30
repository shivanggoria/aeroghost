"""
Forward-secrecy tests.

Verify the ephemeral X25519 + HKDF handshake: both peers agree on a per-session
key, it is distinct from the long-lived room key, it changes on every connection,
and traffic encrypted under it cannot be recovered with the room key (which is
what a passphrase-cracker would obtain).
"""

import time
import pytest

from core.crypto import CryptoEngine
from core.group_manager import GroupManager


# --------------------------------------------------------------------------
# Unit level: the key-agreement primitive
# --------------------------------------------------------------------------
def test_derive_session_key_agrees():
    """Both parties derive the identical session key from mutual ephemeral pubkeys."""
    priv_a, pub_a = CryptoEngine.generate_ephemeral_keypair()
    priv_b, pub_b = CryptoEngine.generate_ephemeral_keypair()
    salt = b"nonce-a" + b"nonce-b"
    ka = CryptoEngine.derive_session_key(priv_a, pub_b, salt)
    kb = CryptoEngine.derive_session_key(priv_b, pub_a, salt)
    assert ka == kb
    assert len(ka) == 32


def test_session_keys_are_ephemeral():
    """Fresh keypairs each time => a different session key every handshake."""
    pa1, ua1 = CryptoEngine.generate_ephemeral_keypair()
    pb1, ub1 = CryptoEngine.generate_ephemeral_keypair()
    k1 = CryptoEngine.derive_session_key(pa1, ub1, b"salt")

    pa2, ua2 = CryptoEngine.generate_ephemeral_keypair()
    pb2, ub2 = CryptoEngine.generate_ephemeral_keypair()
    k2 = CryptoEngine.derive_session_key(pa2, ub2, b"salt")

    assert k1 != k2


# --------------------------------------------------------------------------
# Integration level: the live handshake over loopback
# --------------------------------------------------------------------------
def _connect(tmp_path, port, name_suffix=""):
    alice = GroupManager("Alice", is_bluetooth_mode=False, db_path=str(tmp_path / f"a{name_suffix}.vault"))
    bob = GroupManager("Bob", is_bluetooth_mode=False, db_path=str(tmp_path / f"b{name_suffix}.vault"))
    assert alice.setup_room("fs-room", "password-1234", is_host=True, port=port) is True
    assert bob.setup_room("fs-room", "password-1234", is_host=False, port=port) is True
    assert bob.join_host("127.0.0.1", port=port) is True
    for _ in range(30):
        time.sleep(0.1)
        if alice.engine.peers and bob.engine.peers:
            break
    return alice, bob


def _peer(mgr):
    return next(iter(mgr.engine.peers.values()))


def test_handshake_establishes_matching_session_key(tmp_path):
    alice, bob = _connect(tmp_path, 29650)
    try:
        assert len(alice.engine.peers) == 1
        assert len(bob.engine.peers) == 1

        a_key = _peer(alice).session_key
        b_key = _peer(bob).session_key
        assert a_key is not None and b_key is not None
        # Both ends of the link derived the same session key...
        assert a_key == b_key
        # ...and it is NOT the passphrase-derived room key.
        assert a_key != alice.crypto.room_key
    finally:
        alice.shutdown()
        bob.shutdown()


def test_room_key_cannot_decrypt_session_traffic(tmp_path):
    """A recovered room key (e.g. cracked passphrase) cannot read session traffic."""
    alice, bob = _connect(tmp_path, 29651)
    try:
        session_key = _peer(alice).session_key
        room_key = alice.crypto.room_key
        ad = b"fs-room"

        ciphertext = CryptoEngine.encrypt_with_key(session_key, b"top secret", ad)
        # Correct session key recovers the plaintext...
        assert CryptoEngine.decrypt_with_key(session_key, ciphertext, ad) == b"top secret"
        # ...but the long-lived room key does not.
        with pytest.raises(Exception):
            CryptoEngine.decrypt_with_key(room_key, ciphertext, ad)
    finally:
        alice.shutdown()
        bob.shutdown()


def test_reconnect_yields_new_session_key(tmp_path):
    """Same room + password, new connection => brand-new key (the essence of FS)."""
    a1, b1 = _connect(tmp_path, 29652, name_suffix="1")
    k1 = _peer(a1).session_key
    a1.shutdown()
    b1.shutdown()
    time.sleep(0.3)

    a2, b2 = _connect(tmp_path, 29653, name_suffix="2")
    k2 = _peer(a2).session_key
    a2.shutdown()
    b2.shutdown()

    assert k1 is not None and k2 is not None
    assert k1 != k2  # a session captured earlier cannot be replayed/decrypted later


def test_e2e_chat_over_forward_secret_channel(tmp_path):
    alice, bob = _connect(tmp_path, 29654)
    try:
        received = []
        alice.on_message_received = lambda m: received.append(m)
        bob.send_chat_message("hello over the forward-secret channel")
        for _ in range(15):
            time.sleep(0.1)
            if received:
                break
        assert received and received[0]["content"] == "hello over the forward-secret channel"
    finally:
        alice.shutdown()
        bob.shutdown()
