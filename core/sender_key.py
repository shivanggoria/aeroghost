"""
Sender-key group encryption for AeroGhost (Signal-style group messaging).

Each member owns a sender key = a symmetric hash-ratchet chain (for one-time
message keys) PLUS an Ed25519 signing keypair. To post to the group a member
derives a message key from their own chain, encrypts once, and signs the result.
Every other member holds a copy of that sender's chain key and signing PUBLIC key
(distributed once), so they can decrypt and verify, but cannot forge messages as
that sender (they never get the signing private key).

Properties:
  - one encryption per message, broadcast to the whole group
  - sender authentication: only the true sender can produce valid messages
  - relay is zero-knowledge of the *relay function*: the host forwards opaque
    ciphertext and cannot forge it
  - on a membership change the app issues fresh sender keys (see GroupManager), so
    a departed member's old key can no longer read or write future traffic

Wire format of one group-content message:
    generation (4 bytes BE) || signature (64 bytes) || AEAD(message_key, plaintext, ad||gen)
The signature covers generation || AEAD-blob || ad.
"""

import os
import hmac
import hashlib
import struct
from typing import Dict, Tuple
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from core.crypto import CryptoEngine

_MAX_SKIP = 2000
_SIG_LEN = 64


def _chain_step(chain_key: bytes) -> Tuple[bytes, bytes]:
    message_key = hmac.new(chain_key, b"\x01", hashlib.sha256).digest()
    next_chain_key = hmac.new(chain_key, b"\x02", hashlib.sha256).digest()
    return next_chain_key, message_key


class _Chain:
    """Internal symmetric hash ratchet (shared logic for send + receive)."""

    def __init__(self, chain_key: bytes, generation: int = 0):
        self.chain_key = chain_key
        self.generation = generation
        self._skipped: Dict[int, bytes] = {}

    def next_key(self) -> Tuple[int, bytes]:
        gen = self.generation
        self.chain_key, mk = _chain_step(self.chain_key)
        self.generation += 1
        return gen, mk

    def key_for(self, target_gen: int) -> bytes:
        if target_gen in self._skipped:
            return self._skipped.pop(target_gen)
        if target_gen < self.generation:
            raise ValueError("Sender-key generation already consumed")
        if target_gen - self.generation > _MAX_SKIP:
            raise ValueError("Too many skipped sender-key generations")
        mk = None
        while self.generation <= target_gen:
            self.chain_key, mk = _chain_step(self.chain_key)
            if self.generation < target_gen:
                self._skipped[self.generation] = mk
            self.generation += 1
        while len(self._skipped) > _MAX_SKIP:
            self._skipped.pop(next(iter(self._skipped)))
        return mk


class SenderKeyPair:
    """A member's own sender key (chain + Ed25519 signing key). Used to send."""

    def __init__(self, chain_key: bytes = None, sign_private: Ed25519PrivateKey = None):
        self._chain = _Chain(chain_key if chain_key is not None else os.urandom(32), 0)
        self._sign = sign_private if sign_private is not None else Ed25519PrivateKey.generate()

    @classmethod
    def new(cls) -> "SenderKeyPair":
        return cls()

    def distribution_blob(self) -> bytes:
        """Chain key + generation + Ed25519 public key, handed to each member once."""
        pub = self._sign.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return self._chain.chain_key + struct.pack("!I", self._chain.generation) + pub

    def encrypt(self, plaintext: bytes, associated_data: bytes = b"") -> bytes:
        gen, mk = self._chain.next_key()
        gen_bytes = struct.pack("!I", gen)
        blob = CryptoEngine.encrypt_with_key(mk, plaintext, associated_data + gen_bytes)
        signature = self._sign.sign(gen_bytes + blob + associated_data)
        return gen_bytes + signature + blob


class SenderKeyPublic:
    """A peer's sender key as held by a recipient (receiving chain + verify key)."""

    def __init__(self, blob: bytes):
        self._chain = _Chain(blob[:32], struct.unpack("!I", blob[32:36])[0])
        self._verify = Ed25519PublicKey.from_public_bytes(blob[36:68])

    def decrypt(self, wire: bytes, associated_data: bytes = b"") -> bytes:
        gen_bytes = wire[:4]
        signature = wire[4:4 + _SIG_LEN]
        blob = wire[4 + _SIG_LEN:]
        # Verify the sender's signature BEFORE deriving/using any key material.
        try:
            self._verify.verify(signature, gen_bytes + blob + associated_data)
        except InvalidSignature:
            raise ValueError("Sender-key signature verification failed")
        gen = struct.unpack("!I", gen_bytes)[0]
        mk = self._chain.key_for(gen)
        return CryptoEngine.decrypt_with_key(mk, blob, associated_data + gen_bytes)
