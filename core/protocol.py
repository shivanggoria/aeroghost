"""
Protocol and Framing Engine for AeroGhost
Framed binary transport over stream sockets with JSON packet headers and binary payloads.
"""

import json
import struct
import base64
from typing import Dict, Any, Optional, Tuple

class PacketType:
    AUTH_HELLO = "AUTH_HELLO"
    AUTH_CHALLENGE = "AUTH_CHALLENGE"
    AUTH_VERIFIED = "AUTH_VERIFIED"
    AUTH_REJECT = "AUTH_REJECT"
    
    CHAT_MESSAGE = "CHAT_MESSAGE"
    PEER_LIST = "PEER_LIST"
    PEER_JOIN = "PEER_JOIN"
    PEER_LEAVE = "PEER_LEAVE"
    
    FILE_OFFER = "FILE_OFFER"
    FILE_ACCEPT = "FILE_ACCEPT"
    FILE_REJECT = "FILE_REJECT"
    FILE_CHUNK = "FILE_CHUNK"
    FILE_ACK = "FILE_ACK"
    FILE_COMPLETE = "FILE_COMPLETE"
    
    HEARTBEAT = "HEARTBEAT"


class Protocol:
    """Encodes and decodes framed packets."""
    
    HEADER_FORMAT = "!I"  # 4-byte big-endian unsigned integer length
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    MAX_PACKET_SIZE = 16 * 1024 * 1024  # 16 MB max frame size safety limit

    @classmethod
    def frame_packet(cls, encrypted_bytes: bytes) -> bytes:
        """Prefaces an encrypted frame with its 4-byte length."""
        length = len(encrypted_bytes)
        if length > cls.MAX_PACKET_SIZE:
            raise ValueError(f"Packet size {length} exceeds maximum allowed {cls.MAX_PACKET_SIZE}")
        return struct.pack(cls.HEADER_FORMAT, length) + encrypted_bytes

    @classmethod
    def extract_frames(cls, buffer: bytearray) -> Tuple[list[bytes], bytearray]:
        """
        Extracts all complete frames from the incoming buffer.
        Returns a tuple of (extracted_frames, remaining_buffer).
        """
        frames = []
        while len(buffer) >= cls.HEADER_SIZE:
            (payload_length,) = struct.unpack_from(cls.HEADER_FORMAT, buffer, 0)
            if payload_length > cls.MAX_PACKET_SIZE:
                # Buffer corruption or overflow attack; reset buffer
                buffer.clear()
                raise ValueError(f"Encountered oversized packet frame ({payload_length} bytes). Dropping buffer.")

            total_frame_len = cls.HEADER_SIZE + payload_length
            if len(buffer) < total_frame_len:
                # Incomplete frame, wait for more data
                break

            payload = bytes(buffer[cls.HEADER_SIZE:total_frame_len])
            frames.append(payload)
            del buffer[:total_frame_len]

        return frames, buffer

    @staticmethod
    def serialize(packet_dict: Dict[str, Any]) -> bytes:
        """Serializes a packet dict to JSON UTF-8 bytes."""
        return json.dumps(packet_dict, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def deserialize(data: bytes) -> Dict[str, Any]:
        """Deserializes JSON UTF-8 bytes to a packet dict."""
        return json.loads(data.decode("utf-8"))

    @staticmethod
    def encode_bytes(data: bytes) -> str:
        """Encodes binary data to standard Base64 string for embedding in JSON."""
        return base64.b64encode(data).decode("ascii")

    @staticmethod
    def decode_bytes(data_str: str) -> bytes:
        """Decodes standard Base64 string back to binary data."""
        return base64.b64decode(data_str.encode("ascii"))
