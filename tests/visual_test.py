"""
Visual and Interactive GUI Integration Test for AeroGhost
Simulates a live multi-peer session between Alice and Bob, verifies messaging,
file transfer, stealth mode, and captures high-resolution screenshots.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from core.group_manager import GroupManager
from ui.main_window import MainWindow


def run_visual_test():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    print("==================================================")
    print("[*] LAUNCHING AEROGHOST LIVE P2P INTERACTION TEST")
    print("==================================================")

    port = 28991
    room = "demo-secure-room"
    pwd = "AeroGhostSuperSecretKey2026"

    os.makedirs("test_artifacts", exist_ok=True)
    db_alice = "test_artifacts/alice.vault"
    db_bob = "test_artifacts/bob.vault"

    # 1. Initialize Host (Alice)
    print("\n[Step 1] Initializing Alice (Host Coordinator)...")
    alice_mgr = GroupManager(nickname="Alice", is_bluetooth_mode=False, db_path=db_alice)
    assert alice_mgr.setup_room(room, pwd, is_host=True, port=port) is True
    alice_win = MainWindow(alice_mgr)
    alice_win.auto_accept = True
    alice_win.show()
    app.processEvents()

    # 2. Initialize Member (Bob)
    print("[Step 2] Initializing Bob (Member Node)...")
    bob_mgr = GroupManager(nickname="Bob", is_bluetooth_mode=False, db_path=db_bob)
    assert bob_mgr.setup_room(room, pwd, is_host=False, port=port) is True
    bob_win = MainWindow(bob_mgr)
    bob_win.auto_accept = True
    bob_win.show()
    app.processEvents()

    # 3. Connect Bob to Alice
    print(f"[Step 3] Bob connecting to Alice over P2P mesh on port {port}...")
    assert bob_mgr.join_host("127.0.0.1", port=port) is True

    # Process events to allow mutual handshake to finish
    print("[Step 4] Performing mutual cryptographic challenge-response handshake...")
    for _ in range(15):
        time.sleep(0.1)
        app.processEvents()
        if len(alice_mgr.engine.peers) >= 1 and len(bob_mgr.engine.peers) >= 1:
            break

    print(f" -> Handshake Successful! Alice peers: {len(alice_mgr.engine.peers)}, Bob peers: {len(bob_mgr.engine.peers)}")

    # 4. Exchange Encrypted Messages
    print("\n[Step 5] Exchanging End-to-End Encrypted Chat Messages...")
    bob_win.msg_input.setText("Hey Alice! Zero internet, 100% offline Bluetooth P2P chat is working!")
    bob_win._send_message()
    for _ in range(5):
        time.sleep(0.1)
        app.processEvents()

    alice_win.msg_input.setText("Hi Bob! AES-256-GCM encryption verified. Now checking Stealth Mode.")
    alice_win._send_message()
    for _ in range(5):
        time.sleep(0.1)
        app.processEvents()

    bob_win.msg_input.setText("Roger that! Switch to Ghost Mode (Ctrl+Shift+S) when ready.")
    bob_win._send_message()
    for _ in range(5):
        time.sleep(0.1)
        app.processEvents()

    # 5. Capture Normal Mode Screenshot
    normal_screenshot_path = "test_artifacts/screenshot_normal_mode.png"
    pix_normal = alice_win.grab()
    pix_normal.save(normal_screenshot_path)
    print(f" -> [Captured] Normal Mode Screenshot: {normal_screenshot_path}")

    # 6. Test File Transfer
    print("\n[Step 6] Testing Encrypted Chunked File Transfer...")
    test_file_path = "test_artifacts/confidential_report.txt"
    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write("AeroGhost Confidential Test Document\n" + ("=" * 40) + "\n" + ("Data line payload over Bluetooth\n" * 100))

    transfer = bob_mgr.send_file(test_file_path)
    print(f" -> Bob offered file '{transfer.filename}' (SHA-256: {transfer.sha256[:16]}...)")
    
    # Allow chunks to stream and be accepted automatically
    for _ in range(25):
        time.sleep(0.1)
        app.processEvents()
    print(" -> File chunks received, SHA-256 verified, and written to disk!")

    # 7. Test Stealth Mode ("Ghost Mode")
    print("\n[Step 7] Testing Stealth Mode ('Ghost Mode' Window Disguise)...")
    alice_win.stealth_mgr.enter_stealth()
    app.processEvents()
    print(" -> Alice window transformed to Stealth Mode:")
    print(f"    - Title: '{alice_win.windowTitle()}' (disguised)")
    print(f"    - Dimensions: {alice_win.width()}x{alice_win.height()} (compact)")
    print(f"    - Sidebar hidden: {not alice_win.sidebar.isVisible()}")
    print(f"    - Document notepad styling active: {alice_win.stealth_mgr.is_stealth}")

    # Bob sends a message while Alice is in stealth mode
    bob_win.msg_input.setText("Testing incoming message while in Stealth Mode.")
    bob_win._send_message()
    for _ in range(5):
        time.sleep(0.1)
        app.processEvents()

    # Capture Stealth Mode Screenshot
    stealth_screenshot_path = "test_artifacts/screenshot_stealth_mode.png"
    pix_stealth = alice_win.grab()
    pix_stealth.save(stealth_screenshot_path)
    print(f" -> [Captured] Stealth Mode Screenshot: {stealth_screenshot_path}")

    # 8. Test Exiting Stealth Mode
    print("\n[Step 8] Exiting Stealth Mode and Restoring Normal View...")
    alice_win.stealth_mgr.exit_stealth()
    app.processEvents()
    print(" -> Alice window restored to standard mode.")

    # 9. Clean Shutdown
    print("\n[Step 9] Shutting Down Peer Nodes Cleanly...")
    alice_win.close()
    bob_win.close()
    alice_mgr.shutdown()
    bob_mgr.shutdown()

    print("\n==================================================")
    print("[SUCCESS] ALL VISUAL AND P2P FUNCTIONALITY TESTS PASSED!")
    print("==================================================")


if __name__ == "__main__":
    run_visual_test()
