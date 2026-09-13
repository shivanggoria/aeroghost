"""
Unit tests for AeroGhost Protocol Framing and Serialization
"""

import pytest
from core.protocol import Protocol, PacketType


def test_packet_framing_and_extraction():
    p1 = b"Frame number one payload"
    p2 = b"Frame number two payload with extra bytes"

    f1 = Protocol.frame_packet(p1)
    f2 = Protocol.frame_packet(p2)

    # Combine into incoming stream buffer
    stream_buffer = bytearray(f1 + f2)

    extracted, remaining = Protocol.extract_frames(stream_buffer)
    assert len(extracted) == 2
    assert extracted[0] == p1
    assert extracted[1] == p2
    assert len(remaining) == 0


def test_partial_frame_buffering():
    payload = b"Full packet data here"
    framed = Protocol.frame_packet(payload)

    # Feed half of the frame
    half1 = bytearray(framed[: len(framed) // 2])
    extracted1, rem1 = Protocol.extract_frames(half1)
    assert len(extracted1) == 0
    assert len(rem1) == len(framed) // 2

    # Feed the second half
    rem1.extend(framed[len(framed) // 2 :])
    extracted2, rem2 = Protocol.extract_frames(rem1)
    assert len(extracted2) == 1
    assert extracted2[0] == payload
    assert len(rem2) == 0


def test_packet_serialization():
    data = {
        "type": PacketType.CHAT_MESSAGE,
        "sender": "Alice",
        "content": "Hello Bluetooth World!",
        "timestamp": 1700000000.0,
    }
    serialized = Protocol.serialize(data)
    assert isinstance(serialized, bytes)

    deserialized = Protocol.deserialize(serialized)
    assert deserialized == data


def test_base64_byte_encoding():
    raw = bytes([0, 1, 2, 255, 254, 128, 64])
    encoded = Protocol.encode_bytes(raw)
    assert isinstance(encoded, str)
    decoded = Protocol.decode_bytes(encoded)
    assert decoded == raw
