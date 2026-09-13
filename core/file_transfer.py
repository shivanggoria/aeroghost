"""
Chunked P2P File Transfer Manager for AeroGhost
Direct chunked file streaming with SHA-256 verification and sandbox isolation.
"""

import os
import uuid
import math
from typing import Dict, Any, Optional, Callable
from core.crypto import CryptoEngine
from core.protocol import Protocol, PacketType


class FileTransferState:
    PENDING = "PENDING"
    TRANSFERRING = "TRANSFERRING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class OutgoingFileTransfer:
    """Manages an outgoing file send."""

    CHUNK_SIZE = 32 * 1024  # 32 KB chunks optimized for Bluetooth RFCOMM

    def __init__(self, file_path: str, sender_nickname: str):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.filesize = os.path.getsize(file_path)
        self.sender_nickname = sender_nickname
        self.transfer_id = str(uuid.uuid4())
        self.sha256 = CryptoEngine.sha256_checksum(file_path)
        self.total_chunks = max(1, math.ceil(self.filesize / self.CHUNK_SIZE))
        self.state = FileTransferState.PENDING
        self.chunks_sent = 0

    def create_offer_packet(self) -> Dict[str, Any]:
        """Creates the FILE_OFFER packet to announce the file to peers."""
        return {
            "type": PacketType.FILE_OFFER,
            "transfer_id": self.transfer_id,
            "sender": self.sender_nickname,
            "filename": self.filename,
            "filesize": self.filesize,
            "sha256": self.sha256,
            "chunk_size": self.CHUNK_SIZE,
            "total_chunks": self.total_chunks,
        }

    def read_chunk(self, chunk_index: int) -> Optional[bytes]:
        """Reads a specific chunk from the file."""
        if chunk_index < 0 or chunk_index >= self.total_chunks:
            return None
        with open(self.file_path, "rb") as f:
            f.seek(chunk_index * self.CHUNK_SIZE)
            return f.read(self.CHUNK_SIZE)


class IncomingFileTransfer:
    """Manages an incoming file receive, assembly, and SHA-256 verification."""

    def __init__(self, offer_packet: Dict[str, Any], download_dir: str = "Received_Files"):
        self.transfer_id = offer_packet["transfer_id"]
        self.sender = offer_packet["sender"]
        self.filename = os.path.basename(offer_packet["filename"])  # Prevent path traversal
        self.filesize = int(offer_packet["filesize"])
        self.expected_sha256 = offer_packet["sha256"]
        self.chunk_size = int(offer_packet.get("chunk_size", 32 * 1024))
        self.total_chunks = int(offer_packet["total_chunks"])
        self.download_dir = download_dir
        self.state = FileTransferState.PENDING

        os.makedirs(self.download_dir, exist_ok=True)
        self.part_path = os.path.join(self.download_dir, f"{self.transfer_id}.part")
        self.final_path = self._get_unique_filepath(os.path.join(self.download_dir, self.filename))
        self.received_chunks = set()

    @staticmethod
    def _get_unique_filepath(target_path: str) -> str:
        """Avoids overwriting existing files by appending (1), (2), etc."""
        base, ext = os.path.splitext(target_path)
        counter = 1
        candidate = target_path
        while os.path.exists(candidate):
            candidate = f"{base} ({counter}){ext}"
            counter += 1
        return candidate

    def write_chunk(self, chunk_index: int, chunk_bytes: bytes) -> bool:
        """Writes received chunk data to the temporary part file."""
        if chunk_index in self.received_chunks:
            return True  # Already written

        mode = "r+b" if os.path.exists(self.part_path) else "wb"
        with open(self.part_path, mode) as f:
            f.seek(chunk_index * self.chunk_size)
            f.write(chunk_bytes)

        self.received_chunks.add(chunk_index)
        self.state = FileTransferState.TRANSFERRING
        return True

    @property
    def progress_percent(self) -> float:
        if self.total_chunks == 0:
            return 100.0
        return (len(self.received_chunks) / self.total_chunks) * 100.0

    def is_complete(self) -> bool:
        return len(self.received_chunks) == self.total_chunks

    def finalize(self) -> bool:
        """
        Validates SHA-256 hash of assembled file and moves to final destination.
        Returns True if hash verified, False otherwise.
        """
        if not os.path.exists(self.part_path):
            self.state = FileTransferState.FAILED
            return False

        # Verify file size matches
        actual_size = os.path.getsize(self.part_path)
        if actual_size != self.filesize:
            self.state = FileTransferState.FAILED
            return False

        # Verify SHA-256 checksum
        actual_sha256 = CryptoEngine.sha256_checksum(self.part_path)
        if actual_sha256.lower() != self.expected_sha256.lower():
            self.state = FileTransferState.FAILED
            if os.path.exists(self.part_path):
                os.remove(self.part_path)
            return False

        # Atomic rename to final path
        os.replace(self.part_path, self.final_path)
        self.state = FileTransferState.COMPLETED
        return True
