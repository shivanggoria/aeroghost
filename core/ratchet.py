"""
Double Ratchet (Signal-style) for AeroGhost 1:1 channels.

Provides per-message keys with a Diffie-Hellman ratchet, giving:
  - forward secrecy: an old message key cannot be recovered from later state
  - post-compromise security ("self-healing"): after a state leak, the next DH
    ratchet step re-randomises the chain so future messages become private again

Built from vetted primitives in the `cryptography` package (X25519, HKDF-SHA256,
HMAC-SHA256, AES-256-GCM). The ratchet is the protocol composition, not new crypto.

Wire format of one ratchet message:
    dh_pub (32 bytes) || PN (4 bytes BE) || N (4 bytes BE) || AEAD(nonce||ct||tag)
The 40-byte header is bound into the AEAD associated data so it cannot be altered.
"""

import hmac
import hashlib
import struct
from typing import Dict, Tuple, Optional
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from core.crypto import CryptoEngine

_HEADER_LEN = 40  # 32-byte pubkey + 4-byte PN + 4-byte N
_MAX_SKIP = 1000  # cap on message keys skipped within a single chain (anti-DoS)
_MAX_STORED_SKIPPED = 2000  # cap on retained skipped-message keys


def _kdf_rk(root_key: bytes, dh_out: bytes) -> Tuple[bytes, bytes]:
    """Root-key KDF: returns (new_root_key, chain_key) from HKDF over the DH output."""
    out = HKDF(algorithm=hashes.SHA256(), length=64, salt=root_key,
               info=b"aeroghost-ratchet-rk").derive(dh_out)
    return out[:32], out[32:]


def _kdf_ck(chain_key: bytes) -> Tuple[bytes, bytes]:
    """Chain-key KDF: returns (next_chain_key, message_key) via HMAC with distinct constants."""
    message_key = hmac.new(chain_key, b"\x01", hashlib.sha256).digest()
    next_chain_key = hmac.new(chain_key, b"\x02", hashlib.sha256).digest()
    return next_chain_key, message_key


def _pack_header(dh_pub: bytes, pn: int, n: int) -> bytes:
    return dh_pub + struct.pack("!II", pn, n)


def _unpack_header(blob: bytes) -> Tuple[bytes, int, int]:
    dh_pub = blob[:32]
    pn, n = struct.unpack("!II", blob[32:_HEADER_LEN])
    return dh_pub, pn, n


class DoubleRatchet:
    """One Double Ratchet session with a single peer."""

    def __init__(self):
        self.DHs = None            # our current ratchet X25519 private key
        self.DHs_pub = b""         # our current ratchet public key (raw bytes)
        self.DHr: Optional[bytes] = None   # peer's current ratchet public key
        self.RK = b""              # root key
        self.CKs: Optional[bytes] = None   # sending chain key
        self.CKr: Optional[bytes] = None   # receiving chain key
        self.Ns = 0                # sending message number
        self.Nr = 0                # receiving message number
        self.PN = 0                # previous sending chain length
        self.MKSKIPPED: Dict[Tuple[bytes, int], bytes] = {}

    # ---- initialisation ---------------------------------------------------
    @classmethod
    def init_initiator(cls, root_key: bytes, peer_ratchet_pub: bytes) -> "DoubleRatchet":
        """Initiator (knows the peer's initial ratchet public key)."""
        r = cls()
        r.DHs, r.DHs_pub = CryptoEngine.generate_ephemeral_keypair()
        r.DHr = peer_ratchet_pub
        r.RK, r.CKs = _kdf_rk(root_key, CryptoEngine.x25519_shared(r.DHs, r.DHr))
        return r

    @classmethod
    def init_responder(cls, root_key: bytes, ratchet_private, ratchet_public: bytes) -> "DoubleRatchet":
        """Responder (its published ratchet keypair seeds the first DH step)."""
        r = cls()
        r.DHs = ratchet_private
        r.DHs_pub = ratchet_public
        r.DHr = None
        r.RK = root_key
        r.CKs = None
        return r

    # ---- ratchet steps ----------------------------------------------------
    def _dh_ratchet(self, header_dh_pub: bytes):
        self.PN = self.Ns
        self.Ns = 0
        self.Nr = 0
        self.DHr = header_dh_pub
        self.RK, self.CKr = _kdf_rk(self.RK, CryptoEngine.x25519_shared(self.DHs, self.DHr))
        self.DHs, self.DHs_pub = CryptoEngine.generate_ephemeral_keypair()
        self.RK, self.CKs = _kdf_rk(self.RK, CryptoEngine.x25519_shared(self.DHs, self.DHr))

    def _skip_message_keys(self, until: int):
        if self.CKr is None:
            return
        if until - self.Nr > _MAX_SKIP:
            raise ValueError("Too many skipped messages")
        while self.Nr < until:
            self.CKr, mk = _kdf_ck(self.CKr)
            self.MKSKIPPED[(self.DHr, self.Nr)] = mk
            self.Nr += 1
        # Bound the skipped-key store.
        while len(self.MKSKIPPED) > _MAX_STORED_SKIPPED:
            self.MKSKIPPED.pop(next(iter(self.MKSKIPPED)))

    # ---- public API -------------------------------------------------------
    def encrypt(self, plaintext: bytes, associated_data: bytes = b"") -> bytes:
        self.CKs, mk = _kdf_ck(self.CKs)
        header = _pack_header(self.DHs_pub, self.PN, self.Ns)
        self.Ns += 1
        blob = CryptoEngine.encrypt_with_key(mk, plaintext, associated_data + header)
        return header + blob

    def decrypt(self, wire: bytes, associated_data: bytes = b"") -> bytes:
        header_bytes = wire[:_HEADER_LEN]
        blob = wire[_HEADER_LEN:]
        dh_pub, pn, n = _unpack_header(header_bytes)
        ad = associated_data + header_bytes

        # 1. Was this a previously skipped message?
        skipped = self.MKSKIPPED.pop((dh_pub, n), None)
        if skipped is not None:
            return CryptoEngine.decrypt_with_key(skipped, blob, ad)

        # 2. New ratchet public key => DH ratchet step (skipping the tail of the old chain).
        if self.DHr != dh_pub:
            self._skip_message_keys(pn)
            self._dh_ratchet(dh_pub)

        # 3. Skip within the current receiving chain, then derive this message key.
        self._skip_message_keys(n)
        self.CKr, mk = _kdf_ck(self.CKr)
        self.Nr += 1
        return CryptoEngine.decrypt_with_key(mk, blob, ad)
