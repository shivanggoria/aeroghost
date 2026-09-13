"""
UI and Stealth Mode test suite
"""

import sys
import pytest
from PySide6.QtWidgets import QApplication
from core.group_manager import GroupManager
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_main_window_stealth_mode_toggle(qapp, tmp_path):
    db_file = str(tmp_path / "ui_test.vault")
    mgr = GroupManager("TestUser", is_bluetooth_mode=False, db_path=db_file)
    mgr.setup_room("ui-room", "password123", is_host=True, port=29100)

    win = MainWindow(mgr)
    win.show()

    # Verify initial normal mode
    assert win.stealth_mgr.is_stealth is False
    assert win.sidebar.isVisible() is True
    assert win.stealth_bar.isVisible() is False

    # Toggle to Stealth Mode
    win.stealth_mgr.enter_stealth()
    assert win.stealth_mgr.is_stealth is True
    assert win.sidebar.isVisible() is False
    assert win.stealth_bar.isVisible() is True
    assert win.windowTitle() == "Notes - Scratchpad"

    # Test opacity slider
    win.stealth_mgr.set_opacity(0.8)
    assert abs(win.windowOpacity() - 0.8) < 0.05

    # Exit Stealth Mode
    win.stealth_mgr.exit_stealth()
    assert win.stealth_mgr.is_stealth is False
    assert win.sidebar.isVisible() is True
    assert win.stealth_bar.isVisible() is False
    assert "AeroGhost" in win.windowTitle()

    win.close()
    mgr.shutdown()
