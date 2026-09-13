"""
Integration tests for End-to-End P2P Group Chat & Cryptographic Handshake
"""

import time
import pytest
from core.group_manager import GroupManager


def test_e2e_p2p_chat_and_handshake(tmp_path):
    port = 21980
    room = "test-group"
    password = "SuperSecretPassword123"

    db_alice = str(tmp_path / "alice.vault")
    db_bob = str(tmp_path / "bob.vault")

    alice = GroupManager(nickname="Alice", is_bluetooth_mode=False, db_path=db_alice)
    bob = GroupManager(nickname="Bob", is_bluetooth_mode=False, db_path=db_bob)

    alice_received_msgs = []
    bob_received_msgs = []

    alice.on_message_received = lambda msg: alice_received_msgs.append(msg)
    bob.on_message_received = lambda msg: bob_received_msgs.append(msg)

    # 1. Alice starts room as Host
    assert alice.setup_room(room_name=room, password=password, is_host=True, port=port) is True

    # 2. Bob joins Alice's room
    assert bob.setup_room(room_name=room, password=password, is_host=False, port=port) is True
    assert bob.join_host(host_address="127.0.0.1", port=port) is True

    # Allow handshake to complete
    time.sleep(0.5)

    # Verify both peers are authenticated
    assert len(alice.engine.peers) == 1
    assert len(bob.engine.peers) == 1

    # 3. Bob sends message to room
    bob.send_chat_message("Hello Alice from Bob!")
    time.sleep(0.3)

    assert len(alice_received_msgs) == 1
    assert alice_received_msgs[0]["content"] == "Hello Alice from Bob!"
    assert alice_received_msgs[0]["sender"] == "Bob"

    # 4. Alice replies
    alice.send_chat_message("Hi Bob, encryption is solid!")
    time.sleep(0.3)

    assert len(bob_received_msgs) == 1
    assert bob_received_msgs[0]["content"] == "Hi Bob, encryption is solid!"
    assert bob_received_msgs[0]["sender"] == "Alice"

    # Cleanup
    alice.shutdown()
    bob.shutdown()


def test_rogue_peer_rejected(tmp_path):
    port = 21985
    room = "secure-vault"

    db_host = str(tmp_path / "host.vault")
    db_rogue = str(tmp_path / "rogue.vault")

    host = GroupManager(nickname="Host", is_bluetooth_mode=False, db_path=db_host)
    rogue = GroupManager(nickname="Eve", is_bluetooth_mode=False, db_path=db_rogue)

    # Host starts with correct password
    assert host.setup_room(room_name=room, password="CorrectPassword123", is_host=True, port=port) is True

    # Rogue connects with wrong password
    assert rogue.setup_room(room_name=room, password="WrongPassword!!!", is_host=False, port=port) is True
    rogue.join_host(host_address="127.0.0.1", port=port)

    # Allow handshake attempt
    time.sleep(0.5)

    # Rogue should NOT be authenticated and connection should be dropped
    assert len(host.engine.peers) == 0

    host.shutdown()
    rogue.shutdown()
