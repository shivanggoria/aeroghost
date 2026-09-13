"""
Unit tests for AeroGhost Cryptographic Engine
"""

import pytest
from core.crypto import CryptoEngine


def test_key_derivation_consistency():
    c1 = CryptoEngine("my-room", "secret123")
    c2 = CryptoEngine("my-room", "secret123")
    assert c1.room_key == c2.room_key
    assert c1.room_uuid == c2.room_uuid
    assert c1.room_salt == c2.room_salt


def test_key_derivation_isolation():
    c1 = CryptoEngine("room-A", "secret123")
    c2 = CryptoEngine("room-B", "secret123")
    c3 = CryptoEngine("room-A", "wrongpassword")
    assert c1.room_key != c2.room_key
    assert c1.room_key != c3.room_key
    assert c1.room_uuid != c2.room_uuid


def test_aes_gcm_encryption_decryption():
    crypto = CryptoEngine("test-room", "password-abc")
    plaintext = b"Hello, this is a top-secret Bluetooth message!"
    ad = b"associated_room_data"

    ciphertext = crypto.encrypt_payload(plaintext, associated_data=ad)
    assert ciphertext != plaintext
    assert len(ciphertext) > len(plaintext) + 12  # 12-byte IV + 16-byte tag

    decrypted = crypto.decrypt_payload(ciphertext, associated_data=ad)
    assert decrypted == plaintext


def test_tamper_detection():
    crypto = CryptoEngine("test-room", "password-abc")
    plaintext = b"Sensitive financial file data"
    ciphertext = bytearray(crypto.encrypt_payload(plaintext))

    # Tamper with one byte in the ciphertext payload
    ciphertext[-1] ^= 0xFF

    with pytest.raises(Exception):
        crypto.decrypt_payload(bytes(ciphertext))


def test_challenge_response_handshake():
    alice = CryptoEngine("room-1", "shared-pass")
    bob = CryptoEngine("room-1", "shared-pass")
    eve = CryptoEngine("room-1", "wrong-pass")

    challenge = alice.generate_challenge()
    assert len(challenge) == 16

    # Valid peer Bob computes response
    bob_resp = bob.compute_response(challenge, role_tag="PEER_AUTH")
    assert alice.verify_response(challenge, bob_resp, role_tag="PEER_AUTH") is True

    # Rogue peer Eve computes response with wrong password
    eve_resp = eve.compute_response(challenge, role_tag="PEER_AUTH")
    assert alice.verify_response(challenge, eve_resp, role_tag="PEER_AUTH") is False


def test_sha256_checksum():
    data = b"Aeroghost cryptographic verification"
    expected_hex = "f9a2b6e5e8e81ce1c27ad6e021eb9436e2f1f0a174092b3a985a73e6ebc45388"
    import hashlib
    actual = hashlib.sha256(data).hexdigest()
    assert CryptoEngine.sha256_checksum(data) == actual
