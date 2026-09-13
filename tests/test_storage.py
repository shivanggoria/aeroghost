"""
Unit tests for AeroGhost Encrypted Local Storage
"""

import os
from core.storage import SecureStorage
from core.crypto import CryptoEngine


def test_storage_lifecycle(tmp_path):
    db_file = str(tmp_path / "test_history.vault")
    storage = SecureStorage(db_path=db_file)
    crypto = CryptoEngine("finance-team", "SuperSecretPass!")

    # Test room registration
    storage.register_room("finance-team", crypto.room_salt)
    recent = storage.get_recent_rooms()
    assert "finance-team" in recent

    # Test peer persistence
    storage.update_trusted_peer("peer123", "Bob-Laptop", "finance-team")
    peers = storage.get_trusted_peers("finance-team")
    assert len(peers) == 1
    assert peers[0]["nickname"] == "Bob-Laptop"
    assert peers[0]["peer_id"] == "peer123"

    # Test encrypted message saving and retrieval
    msg = {
        "id": "msg-001",
        "sender": "Bob-Laptop",
        "sender_id": "peer123",
        "content": "Meeting in Room 3 at 2 PM",
        "timestamp": 1700000001.0,
    }
    storage.save_message(crypto, "msg-001", msg)

    loaded = storage.load_messages(crypto)
    assert len(loaded) == 1
    assert loaded[0]["content"] == "Meeting in Room 3 at 2 PM"

    # Test that unauthorized crypto engine cannot decrypt messages
    wrong_crypto = CryptoEngine("finance-team", "WrongPassword!")
    unauthorized_loaded = storage.load_messages(wrong_crypto)
    assert len(unauthorized_loaded) == 0  # Cannot decrypt with wrong password
