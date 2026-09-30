"""
Cryptographic Engine for AeroGhost Bluetooth P2P
Zero-telemetry, end-to-end encrypted protocol.

v2 cryptography:
  - Argon2id                    memory-hard passphrase stretch (at-rest vault key)
  - SPAKE2                      password-authenticated key exchange (no offline dictionary attack)
  - X25519 + ML-KEM-768         hybrid classical/post-quantum key agreement
  - HKDF-SHA256                 key derivation
  - AES-256-GCM                 authenticated encryption
The per-message Double Ratchet lives in core/ratchet.py and sender-key group
encryption in core/sender_key.py; this module provides the primitives they use.
"""

import os
import hmac
import hashlib
import uuid
from typing import Tuple, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.asymmetric.mlkem import MLKEM768PrivateKey, MLKEM768PublicKey
from argon2.low_level import hash_secret_raw, Type as _Argon2Type
from spake2 import SPAKE2_A, SPAKE2_B


def hkdf_sha256(key_material: bytes, length: int = 32, salt: bytes = b"", info: bytes = b"") -> bytes:
    """One-shot HKDF-SHA256."""
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(key_material)


class CryptoEngine:
    """Derives the at-rest vault key (Argon2id) and provides AEAD helpers.

    Transport authentication no longer relies on a password-derived key: the live
    handshake uses SPAKE2 (a PAKE), so capturing it grants no offline dictionary
    attack. Argon2id here protects the locally stored message history.
    """

    # Argon2id parameters (OWASP: >= 19 MiB; we use 64 MiB, memory-hard vs GPU/ASIC).
    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_KIB = 64 * 1024  # 64 MiB
    ARGON2_PARALLELISM = 4

    def __init__(self, room_name: str, password: str):
        self.room_name = room_name.strip()
        self.password = password.strip()
        self.room_salt = self._generate_salt(self.room_name)
        self.room_key = self._derive_key(self.password, self.room_salt)
        self.room_uuid = self._derive_room_uuid(self.room_name, self.room_key)

    @classmethod
    def _generate_salt(cls, room_name: str) -> bytes:
        """
        Derive a deterministic room salt from the room name.

        The vault salt is deterministic from the room name so the same room +
        password always reproduces the at-rest key on the same device. Brute-force
        resistance against a stolen vault comes from Argon2id's memory-hardness
        plus a strong passphrase; live traffic is protected by the PAKE instead.
        """
        return hashlib.sha256(f"aeroghost_salt:v2:{room_name.lower()}".encode("utf-8")).digest()[:16]

    @classmethod
    def _derive_key(cls, password: str, salt: bytes) -> bytes:
        """Derive a 256-bit vault key using Argon2id (memory-hard)."""
        return hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt,
            time_cost=cls.ARGON2_TIME_COST,
            memory_cost=cls.ARGON2_MEMORY_KIB,
            parallelism=cls.ARGON2_PARALLELISM,
            hash_len=32,
            type=_Argon2Type.ID,
        )

    @classmethod
    def _derive_room_uuid(cls, room_name: str, room_key: bytes) -> str:
        """
        Derive a deterministic 128-bit service UUID for Bluetooth RFCOMM / SDP.

        Derived from the Argon2id vault key via HMAC (not the raw password), so even
        if the UUID is published over SDP it cannot be used as a cheap offline
        oracle to guess the passphrase.
        """
        h = hmac.new(room_key, f"aeroghost-sdp-uuid:{room_name.lower()}".encode("utf-8"), hashlib.sha256).digest()
        # Convert first 16 bytes into standard UUID format
        return str(uuid.UUID(bytes=h[:16]))

    @staticmethod
    def encrypt_with_key(key: bytes, plaintext: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """
        Encrypts with an arbitrary 256-bit AES-GCM key (room key or session key).
        Returns: 12-byte Nonce + Ciphertext (includes 16-byte GCM tag).
        """
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, associated_data)
        return nonce + ciphertext

    @staticmethod
    def decrypt_with_key(key: bytes, encrypted_data: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """
        Decrypts an AES-256-GCM payload (12-byte nonce + ciphertext + tag) with the
        given key. Raises ValueError/InvalidTag if tampered or the wrong key is used.
        """
        if len(encrypted_data) < 28:  # 12-byte nonce + 16-byte tag
            raise ValueError("Encrypted data is too short to be valid AES-GCM payload.")
        nonce = encrypted_data[:12]
        ciphertext_and_tag = encrypted_data[12:]
        return AESGCM(key).decrypt(nonce, ciphertext_and_tag, associated_data)

    def encrypt_payload(self, plaintext: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """Encrypts with the long-lived room key (used for at-rest storage)."""
        return self.encrypt_with_key(self.room_key, plaintext, associated_data)

    def decrypt_payload(self, encrypted_data: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """Decrypts with the long-lived room key (used for at-rest storage)."""
        return self.decrypt_with_key(self.room_key, encrypted_data, associated_data)

    # ------------------------------------------------------------------
    # X25519 ephemeral keys (reused by the hybrid handshake and the ratchet)
    # ------------------------------------------------------------------
    @staticmethod
    def generate_ephemeral_keypair() -> Tuple[X25519PrivateKey, bytes]:
        """Generate a one-shot X25519 keypair; returns (private_key, raw 32-byte public)."""
        private_key = X25519PrivateKey.generate()
        public_bytes = private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return private_key, public_bytes

    @staticmethod
    def x25519_shared(private_key: X25519PrivateKey, peer_public_bytes: bytes) -> bytes:
        """Raw X25519 Diffie-Hellman shared secret (32 bytes)."""
        return private_key.exchange(X25519PublicKey.from_public_bytes(peer_public_bytes))

    def generate_challenge(self) -> bytes:
        """Generate a cryptographically secure 16-byte random challenge nonce."""
        return os.urandom(16)

    def compute_response(self, challenge: bytes, role_tag: str = "PEER") -> bytes:
        """Compute HMAC-SHA256 challenge response using the derived room key."""
        h = hmac.new(self.room_key, challenge + role_tag.encode("utf-8"), hashlib.sha256)
        return h.digest()

    def verify_response(self, challenge: bytes, response: bytes, role_tag: str = "PEER") -> bool:
        """Verify HMAC-SHA256 challenge response with constant-time comparison."""
        expected = self.compute_response(challenge, role_tag)
        return hmac.compare_digest(expected, response)

    @staticmethod
    def sha256_checksum(data_or_file_path) -> str:
        """Compute hex SHA-256 checksum for bytes or a file on disk."""
        h = hashlib.sha256()
        if isinstance(data_or_file_path, (bytes, bytearray)):
            h.update(data_or_file_path)
            return h.hexdigest()

        # It's a file path
        with open(data_or_file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()


# ======================================================================
# v2 handshake primitives: SPAKE2 PAKE + hybrid X25519/ML-KEM-768 KEM
# ======================================================================

def x25519_public_from_private(private_key: X25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def mlkem_keygen() -> Tuple[MLKEM768PrivateKey, bytes]:
    """Generate an ML-KEM-768 keypair; returns (private_key, raw public-key bytes)."""
    private_key = MLKEM768PrivateKey.generate()
    return private_key, private_key.public_key().public_bytes_raw()


def mlkem_encapsulate(peer_public_bytes: bytes) -> Tuple[bytes, bytes]:
    """
    Encapsulate to an ML-KEM-768 public key.
    Returns (shared_secret_32B, ciphertext_1088B). The responder runs this.
    """
    public_key = MLKEM768PublicKey.from_public_bytes(peer_public_bytes)
    shared_secret, ciphertext = public_key.encapsulate()
    return shared_secret, ciphertext


def mlkem_decapsulate(private_key: MLKEM768PrivateKey, ciphertext: bytes) -> bytes:
    """Decapsulate an ML-KEM-768 ciphertext back to the shared secret. The initiator runs this."""
    return private_key.decapsulate(ciphertext)


def pake_new(password: str, is_initiator: bool):
    """
    Create a SPAKE2 state for one handshake. Returns (state, outbound_message).
    The two roles (A=initiator, B=responder) must differ so the exchange completes.
    """
    pw = password.encode("utf-8")
    state = SPAKE2_A(pw) if is_initiator else SPAKE2_B(pw)
    return state, state.start()


def pake_finish(state, peer_message: bytes) -> bytes:
    """Finish SPAKE2 with the peer's message, returning the 32-byte PAKE key.

    If the two sides used different passwords, the keys will simply differ; the
    handshake then fails at the key-confirmation step below.
    """
    return state.finish(peer_message)


def derive_root_key(pake_key: bytes, x25519_shared: bytes, mlkem_shared: bytes, salt: bytes) -> bytes:
    """
    Combine the PAKE key with the classical (X25519) and post-quantum (ML-KEM)
    shared secrets into one 256-bit root key via HKDF. An attacker must break the
    password (PAKE) AND X25519 AND ML-KEM to recover it.
    """
    ikm = pake_key + x25519_shared + mlkem_shared
    return hkdf_sha256(ikm, length=32, salt=salt, info=b"aeroghost-v2-root")


def confirm_tag(root_key: bytes, label: bytes, transcript: bytes) -> bytes:
    """Key-confirmation MAC over the handshake transcript, keyed by the root key."""
    return hmac.new(root_key, label + transcript, hashlib.sha256).digest()


def verify_confirm_tag(root_key: bytes, label: bytes, transcript: bytes, tag: bytes) -> bool:
    return hmac.compare_digest(confirm_tag(root_key, label, transcript), tag)
