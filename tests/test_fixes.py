"""
Regression tests for the QA fixes: HTML-escaping of peer text, local-time
timestamps, roster population, bounded dedup, targeted file accept, and the
hardened key-derivation parameters.
"""

import sys
import time
import pytest
from PySide6.QtWidgets import QApplication

from core.crypto import CryptoEngine
from core.group_manager import GroupManager
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_kdf_is_argon2id_memory_hard():
    # Argon2id vault key: OWASP minimum is 19 MiB; we use more.
    assert CryptoEngine.ARGON2_MEMORY_KIB >= 19 * 1024
    assert CryptoEngine.ARGON2_TIME_COST >= 2


def test_room_uuid_not_derived_from_raw_password():
    """UUID must be deterministic per (room, password) and change with the password."""
    a = CryptoEngine("room", "correct horse battery staple")
    b = CryptoEngine("room", "correct horse battery staple")
    c = CryptoEngine("room", "a different passphrase entirely")
    assert a.room_uuid == b.room_uuid
    assert a.room_uuid != c.room_uuid


def test_roster_includes_self(tmp_path):
    mgr = GroupManager("Solo", is_bluetooth_mode=False, db_path=str(tmp_path / "r.vault"))
    mgr.setup_room("roster-room", "password-1234", is_host=True, port=29610)
    roster = mgr.get_roster()
    assert any(p["nickname"] == "Solo" and p["id"] == mgr.peer_id for p in roster)
    mgr.shutdown()


def test_seen_message_cache_is_bounded(tmp_path):
    mgr = GroupManager("Cap", is_bluetooth_mode=False, db_path=str(tmp_path / "c.vault"))
    mgr.setup_room("cap-room", "password-1234", is_host=True, port=29611)
    for i in range(GroupManager.SEEN_MESSAGE_LIMIT + 500):
        mgr._mark_seen(f"id-{i}")
    assert len(mgr._seen_msg_ids) <= GroupManager.SEEN_MESSAGE_LIMIT
    assert len(mgr._seen_order) <= GroupManager.SEEN_MESSAGE_LIMIT
    mgr.shutdown()


def test_incoming_chat_html_is_escaped(qapp, tmp_path):
    """A peer message containing markup must be shown as literal text, not rendered."""
    mgr = GroupManager("Me", is_bluetooth_mode=False, db_path=str(tmp_path / "x.vault"))
    mgr.setup_room("xss-room", "password-1234", is_host=True, port=29612)
    win = MainWindow(mgr)

    hostile = {
        "sender": "<i>Eve</i>",
        "sender_id": "peer",
        "content": "<b>bold</b> <img src=x>",
        "timestamp": 0,
    }
    win._handle_incoming_message(hostile)
    shown = win.chat_area.toPlainText()
    # The literal tags appear as text (escaped), proving they were not interpreted.
    assert "<b>bold</b>" in shown
    assert "<i>Eve</i>" in shown

    win.close()
    mgr.shutdown()


def test_timestamp_is_local_time(qapp, tmp_path):
    mgr = GroupManager("Me", is_bluetooth_mode=False, db_path=str(tmp_path / "t.vault"))
    mgr.setup_room("time-room", "password-1234", is_host=True, port=29613)
    win = MainWindow(mgr)

    ts = 1_700_000_000.0
    expected = time.strftime("%H:%M", time.localtime(ts))
    win._handle_incoming_message({"sender": "A", "sender_id": "p", "content": "hi", "timestamp": ts})
    assert expected in win.chat_area.toPlainText()

    win.close()
    mgr.shutdown()


def test_escape_exits_stealth_via_event_filter(qapp, tmp_path):
    """A synthetic Escape KeyPress routed through the app event filter exits stealth."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    mgr = GroupManager("Me", is_bluetooth_mode=False, db_path=str(tmp_path / "e.vault"))
    mgr.setup_room("esc-room", "password-1234", is_host=True, port=29615)
    win = MainWindow(mgr)
    win.show()

    win.stealth_mgr.enter_stealth()
    assert win.stealth_mgr.is_stealth is True

    # Application event filters run for events delivered via QApplication.notify,
    # so sending Escape to a child widget exercises the same path a real keypress
    # takes (which the UI automation harness does not forward for Escape).
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    qapp.sendEvent(win.msg_input, event)
    assert win.stealth_mgr.is_stealth is False

    win.close()
    mgr.shutdown()


def test_accept_file_targets_offering_peer(tmp_path, monkeypatch):
    """accept_file should unicast FILE_ACCEPT to the offering peer, not broadcast."""
    mgr = GroupManager("Recv", is_bluetooth_mode=False, db_path=str(tmp_path / "f.vault"))
    mgr.setup_room("file-room", "password-1234", is_host=True, port=29614)

    sent = []

    class FakePeer:
        peer_id = "offerer"
        ratchet = object()  # non-None so _route_out sends directly to this peer

        def close(self):
            pass

    offerer = FakePeer()
    mgr.engine.peers["offerer"] = offerer
    monkeypatch.setattr(
        mgr, "_send_packet",
        lambda peer, pkt: sent.append((getattr(peer, "peer_id", None), pkt.get("type"), pkt.get("to"))),
    )

    class SrcPeer:
        peer_id = "offerer"

    offer = {
        "type": "FILE_OFFER", "transfer_id": "tid-1", "offerer_id": "offerer", "sender": "Bob",
        "filename": "a.txt", "filesize": 10, "sha256": "0" * 64,
        "chunk_size": 32768, "total_chunks": 1,
    }
    mgr._on_file_offer(SrcPeer(), offer)
    mgr.accept_file("tid-1")

    # Exactly one send, addressed (to=) the offerer.
    assert sent == [("offerer", "FILE_ACCEPT", "offerer")]
    mgr.shutdown()
