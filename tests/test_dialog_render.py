"""
Test script to render and screenshot RoomSetupDialog in Host, Join (BT), and Join (Mesh) modes.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from PySide6.QtWidgets import QApplication
from core.storage import SecureStorage
from ui.dialogs import RoomSetupDialog
from ui.styles import NORMAL_STYLE

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

app.setStyleSheet(NORMAL_STYLE)

storage = SecureStorage("test_artifacts/dialog_test.vault")
dlg = RoomSetupDialog(storage)
dlg.show()
app.processEvents()

# 1. Capture Host mode
pix_host = dlg.grab()
os.makedirs("test_artifacts", exist_ok=True)
pix_host.save("test_artifacts/dialog_host_mode.png")
print("[Captured] dialog_host_mode.png")

# 2. Toggle to Join Room (Bluetooth)
dlg.btn_role_join.click()
dlg.btn_mode_bt.click()
app.processEvents()
pix_join_bt = dlg.grab()
pix_join_bt.save("test_artifacts/dialog_join_bt_mode.png")
print("[Captured] dialog_join_bt_mode.png")

# 3. Toggle to Join Room (Local Test Mesh)
dlg.btn_mode_test.click()
app.processEvents()
pix_join_mesh = dlg.grab()
pix_join_mesh.save("test_artifacts/dialog_join_mesh_mode.png")
print("[Captured] dialog_join_mesh_mode.png")

dlg.close()
print("All dialog screenshots captured successfully!")
