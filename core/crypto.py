"""
Cryptographic Engine for AeroGhost Bluetooth P2P
Zero-telemetry, end-to-end encrypted protocol using AES-256-GCM and PBKDF2.
"""

import os
import hmac
import hashlib
import uuid
from typing import Tuple, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey


class CryptoEngine:
    """Handles key derivation, mutual challenge-response authentication, and AEAD encryption/decryption."""

    # OWASP (2023) guidance for PBKDF2-HMAC-SHA256 is >= 600,000 iterations.
    PBKDF2_ITERATIONS = 600_000

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

        Design note: peers derive the shared room key offline from (room_name,
        password) with no round-trip, so the salt cannot be random per-device --
        both sides must reach the same salt from public information alone.
        The salt therefore only provides domain separation between rooms, not the
        per-secret randomness a stored-password salt would. Brute-force resistance
        comes from the PBKDF2 iteration count above and from a strong passphrase.
        """
        return hashlib.sha256(f"aeroghost_salt:v1:{room_name.lower()}".encode("utf-8")).digest()[:16]

    @classmethod
    def _derive_key(cls, password: str, salt: bytes) -> bytes:
        """Derive a 256-bit AES key using PBKDF2-HMAC-SHA256."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=cls.PBKDF2_ITERATIONS,
        )
        return kdf.derive(password.encode("utf-8"))

    @classmethod
    def _derive_room_uuid(cls, room_name: str, room_key: bytes) -> str:
        """
        Derive a deterministic 128-bit service UUID for Bluetooth RFCOMM / SDP.

        Derived from the PBKDF2 room key via HMAC (not the raw password), so even
        if the UUID is published over SDP it cannot be used as a cheap offline
        oracle to guess the passphrase -- recovering the key still costs a full
        PBKDF2 evaluation per guess.
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
    # Ephemeral Diffie-Hellman (X25519) for per-session forward secrecy
    # ------------------------------------------------------------------
    @staticmethod
    def generate_ephemeral_keypair() -> Tuple[X25519PrivateKey, bytes]:
        """
        Generate a one-shot X25519 keypair for a single handshake.
        Returns (private_key_object, raw_32-byte_public_key). The private key is
        never sent and is discarded once the session key is derived, which is what
        gives forward secrecy: a later passphrase compromise cannot recompute it.
        """
        private_key = X25519PrivateKey.generate()
        public_bytes = private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return private_key, public_bytes

    @staticmethod
    def derive_session_key(private_key: X25519PrivateKey, peer_public_bytes: bytes, salt: bytes) -> bytes:
        """
        Derive the shared 256-bit session key from our ephemeral private key and the
        peer's ephemeral public key via X25519 + HKDF-SHA256. Both peers compute the
        identical key from the same (salt, info) and the mutual DH shared secret.
        """
        peer_public = X25519PublicKey.from_public_bytes(peer_public_bytes)
        shared_secret = private_key.exchange(peer_public)
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"aeroghost-session-v1",
        ).derive(shared_secret)

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
