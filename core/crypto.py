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
from cryptography.hazmat.primitives import hashes


class CryptoEngine:
    """Handles key derivation, mutual challenge-response authentication, and AEAD encryption/decryption."""

    PBKDF2_ITERATIONS = 100_000

    def __init__(self, room_name: str, password: str):
        self.room_name = room_name.strip()
        self.password = password.strip()
        self.room_salt = self._generate_salt(self.room_name)
        self.room_key = self._derive_key(self.password, self.room_salt)
        self.aesgcm = AESGCM(self.room_key)
        self.room_uuid = self._derive_room_uuid(self.room_name, self.password)

    @classmethod
    def _generate_salt(cls, room_name: str) -> bytes:
        """Derive a deterministic room salt from the room name."""
        return hashlib.sha256(f"aeroghost_salt:{room_name.lower()}".encode("utf-8")).digest()[:16]

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
    def _derive_room_uuid(cls, room_name: str, password: str) -> str:
        """
        Derive a deterministic 128-bit UUID for Bluetooth RFCOMM / SDP service discovery.
        Only nodes knowing both room_name and password can advertise or listen for this UUID.
        """
        h = hashlib.sha256(f"aeroghost_uuid:{room_name.lower()}:{password}".encode("utf-8")).digest()
        # Convert first 16 bytes into standard UUID format
        return str(uuid.UUID(bytes=h[:16]))

    def encrypt_payload(self, plaintext: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """
        Encrypts payload using AES-256-GCM.
        Returns: 12-byte Nonce + Ciphertext (includes 16-byte GCM tag).
        """
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, plaintext, associated_data)
        return nonce + ciphertext

    def decrypt_payload(self, encrypted_data: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """
        Decrypts AES-256-GCM payload.
        Expects: 12-byte Nonce + Ciphertext + Tag.
        Raises ValueError if tampered or corrupt.
        """
        if len(encrypted_data) < 28:  # 12-byte nonce + 16-byte tag
            raise ValueError("Encrypted data is too short to be valid AES-GCM payload.")

        nonce = encrypted_data[:12]
        ciphertext_and_tag = encrypted_data[12:]
        return self.aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data)

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
