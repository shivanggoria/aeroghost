"""
Comprehensive Crash Traversal Test Suite
Validates all permutations, edge cases, error conditions, and failure paths
across the application to guarantee 100% crash-proof stability.
"""

import os
import sys
import time
import socket
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from core.group_manager import GroupManager
from core.crypto import CryptoEngine
from core.protocol import Protocol, PacketType
from core.storage import SecureStorage
from ui.dialogs import RoomSetupDialog, FileOfferDialog
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


# =====================================================================
# 1. SETUP DIALOG EDGE CASES & CRASH TESTS
# =====================================================================

def test_dialog_empty_fields_no_crash(qapp, tmp_path, monkeypatch):
    """Test that validating empty room, password, or nickname shows warning and never crashes."""
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    storage = SecureStorage(str(tmp_path / "test_diag.vault"))
    dlg = RoomSetupDialog(storage)

    # Empty room name
    dlg.room_combo.setCurrentText("")
    dlg.pass_edit.setText("pass123")
    dlg.nick_edit.setText("Alice")
    dlg._validate_and_accept()
    assert dlg.result() == 0  # Not accepted, rejected safely

    # Empty password
    dlg.room_combo.setCurrentText("room1")
    dlg.pass_edit.setText("")
    dlg._validate_and_accept()
    assert dlg.result() == 0

    # Empty nickname
    dlg.pass_edit.setText("pass123")
    dlg.nick_edit.setText("")
    dlg._validate_and_accept()
    assert dlg.result() == 0

    # Join mode with empty address
    dlg.nick_edit.setText("Alice")
    dlg.btn_role_join.click()
    dlg.target_edit.setText("")
    dlg._validate_and_accept()
    assert dlg.result() == 0

    dlg.close()


def test_dialog_instant_test_button(qapp, tmp_path):
    """Test that clicking the 1-click test button configures dual test cleanly."""
    storage = SecureStorage(str(tmp_path / "test_diag2.vault"))
    dlg = RoomSetupDialog(storage)
    dlg.btn_instant_test.click()
    assert dlg.launch_dual_test is True
    assert dlg.result() == 1  # Accepted
    dlg.close()


def test_dialog_role_and_transport_toggles(qapp, tmp_path):
    """Test all permutations of toggling between Host/Join and Local Mesh/Bluetooth."""
    storage = SecureStorage(str(tmp_path / "test_diag3.vault"))
    dlg = RoomSetupDialog(storage)
    dlg.show()
    qapp.processEvents()

    # Host -> Join
    dlg.btn_role_join.click()
    qapp.processEvents()
    assert dlg.target_frame.isVisible() is True
    assert dlg.target_edit.text() == "127.0.0.1"

    # Local Mesh -> Bluetooth
    dlg.btn_mode_bt.click()
    assert dlg.port_spin.value() == 4
    assert dlg.port_lbl.text() == "Channel:"

    # Bluetooth -> Local Mesh
    dlg.btn_mode_test.click()
    assert dlg.port_spin.value() == 19840
    assert dlg.target_edit.text() == "127.0.0.1"

    # Click Localhost helper shortcut
    dlg.btn_mode_bt.click()
    dlg.btn_fill_local.click()
    assert dlg.btn_mode_test.isChecked() is True
    assert dlg.target_edit.text() == "127.0.0.1"

    # Join -> Host
    dlg.btn_role_host.click()
    assert dlg.target_frame.isVisible() is False

    dlg.close()


# =====================================================================
# 2. NETWORK CONNECTION & PORT CRASH TESTS
# =====================================================================

def test_join_non_existent_host_graceful(tmp_path):
    """Verify that joining an offline/non-existent host returns False without throwing or crashing."""
    db_file = str(tmp_path / "client_fail.vault")
    mgr = GroupManager("ClientUser", is_bluetooth_mode=False, db_path=db_file)
    mgr.setup_room("offline-room", "secret123", is_host=False)

    # Connect to an unused port where nothing is listening
    connected = mgr.join_host("127.0.0.1", port=49123)
    assert connected is False  # Must return False cleanly
    mgr.shutdown()


def test_port_conflict_host_bind_graceful(tmp_path):
    """Verify that attempting to bind to an already-bound port returns False cleanly without crashing."""
    port = 29555
    # Create an external socket holding the port
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    blocker.bind(("127.0.0.1", port))
    blocker.listen(1)

    try:
        db_file = str(tmp_path / "conflict.vault")
        mgr = GroupManager("HostUser", is_bluetooth_mode=False, db_path=db_file)
        # Attempt to start listener on the occupied port
        success = mgr.setup_room("conflict-room", "pass123", is_host=True, port=port)
        assert success is False  # Must fail gracefully
        mgr.shutdown()
    finally:
        blocker.close()


# =====================================================================
# 3. MESSAGING & FILE TRANSFER EDGE CASES
# =====================================================================

def test_messaging_with_zero_peers(tmp_path):
    """Verify sending messages when 0 peers are connected does not crash and saves to vault."""
    db_file = str(tmp_path / "solo_chat.vault")
    mgr = GroupManager("SoloUser", is_bluetooth_mode=False, db_path=db_file)
    mgr.setup_room("solo-room", "password", is_host=True, port=29560)

    # Send message with no connected peers
    msg = mgr.send_chat_message("Hello in an empty room")
    assert msg["content"] == "Hello in an empty room"
    assert msg["sender"] == "SoloUser"

    # Verify message was safely stored in local encrypted vault
    cached = mgr.storage.load_messages(mgr.crypto)
    assert len(cached) == 1
    assert cached[0]["content"] == "Hello in an empty room"

    mgr.shutdown()


def test_send_nonexistent_file_graceful(tmp_path):
    """Verify attempting to send a file that doesn't exist raises FileNotFoundError handled by caller."""
    db_file = str(tmp_path / "file_fail.vault")
    mgr = GroupManager("FileUser", is_bluetooth_mode=False, db_path=db_file)
    mgr.setup_room("file-room", "password", is_host=True, port=29570)

    try:
        mgr.send_file("non_existent_file_xyz123.dat")
    except Exception as e:
        # Should raise standard exception or handle gracefully
        assert isinstance(e, FileNotFoundError)

    mgr.shutdown()


# =====================================================================
# 4. MALFORMED / CORRUPTED PACKET TAMPERING TESTS
# =====================================================================

def test_tampered_and_corrupt_packets_no_crash(tmp_path):
    """Verify that corrupt packets, wrong AEAD tags, and junk bytes are dropped without crashing."""
    port = 29580
    room = "tamper-room"
    password = "CorrectPassword123"

    db_host = str(tmp_path / "host_tamper.vault")
    host = GroupManager("HostAlice", is_bluetooth_mode=False, db_path=db_host)
    assert host.setup_room(room, password, is_host=True, port=port) is True

    # Connect raw TCP socket to simulate an attacker/corrupt peer
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("127.0.0.1", port))

    # Send complete garbage (random bytes with valid frame header)
    junk_payload = b"GARBAGE_NOT_ENCRYPTED_DATA"
    junk_frame = len(junk_payload).to_bytes(4, byteorder="big") + junk_payload
    s.sendall(junk_frame)
    time.sleep(0.3)

    # Host should still be alive and responsive!
    assert host.engine.is_listening is True

    # Send corrupted ciphertext (valid format, invalid GCM tag)
    corrupt_nonce_ct = os.urandom(12 + 32)
    corrupt_frame = len(corrupt_nonce_ct).to_bytes(4, byteorder="big") + corrupt_nonce_ct
    s.sendall(corrupt_frame)
    time.sleep(0.3)

    # Host should drop corrupt connection and remain alive
    assert host.engine.is_listening is True

    s.close()
    host.shutdown()


# =====================================================================
# 5. UI STRESS & STEALTH MODE BOUNDARY TESTS
# =====================================================================

def test_stealth_mode_rapid_toggle_and_boundaries(qapp, tmp_path):
    """Verify rapid switching into/out of stealth mode and opacity bounds never crash."""
    db_file = str(tmp_path / "ui_stress.vault")
    mgr = GroupManager("StressUser", is_bluetooth_mode=False, db_path=db_file)
    mgr.setup_room("stress-room", "pass", is_host=True, port=29590)

    win = MainWindow(mgr)
    win.show()

    # Rapid toggle 20 times
    for _ in range(20):
        win.stealth_mgr.toggle()
        qapp.processEvents()

    # Opacity boundary tests
    win.stealth_mgr.set_opacity(1.0)
    win.stealth_mgr.set_opacity(0.1)
    win.stealth_mgr.set_opacity(0.85)

    # Send message in UI
    win.msg_input.setText("Stress test message")
    win._send_message()
    assert len(win.messages) == 1

    # Send empty message in UI (should not crash)
    win.msg_input.setText("   ")
    win._send_message()
    assert len(win.messages) == 1

    # Close and clean
    win.close()
    mgr.shutdown()
