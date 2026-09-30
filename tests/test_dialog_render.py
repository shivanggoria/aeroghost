"""
Renders RoomSetupDialog in Host, Join (Bluetooth), and Join (Local Mesh) modes
and saves screenshots.

Written as a real pytest test (not a module-level script) so pytest collects it
cleanly and it never executes at import time. Screenshots are written under the
test's tmp_path, so the suite does not depend on any pre-existing folder.
"""

import sys
import pytest
from PySide6.QtWidgets import QApplication
from core.storage import SecureStorage
from ui.dialogs import RoomSetupDialog
from ui.styles import NORMAL_STYLE


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setStyleSheet(NORMAL_STYLE)
    return app


def test_dialog_renders_all_modes(qapp, tmp_path):
    out_dir = tmp_path / "dialog_shots"
    out_dir.mkdir(parents=True, exist_ok=True)

    storage = SecureStorage(str(tmp_path / "dialog_test.vault"))
    dlg = RoomSetupDialog(storage)
    dlg.show()
    qapp.processEvents()

    # 1. Host mode
    assert dlg.grab().save(str(out_dir / "dialog_host_mode.png"))

    # 2. Join Room (Bluetooth)
    dlg.btn_role_join.click()
    dlg.btn_mode_bt.click()
    qapp.processEvents()
    assert dlg.grab().save(str(out_dir / "dialog_join_bt_mode.png"))

    # 3. Join Room (Local Test Mesh)
    dlg.btn_mode_test.click()
    qapp.processEvents()
    assert dlg.grab().save(str(out_dir / "dialog_join_mesh_mode.png"))

    dlg.close()
