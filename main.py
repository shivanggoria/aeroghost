"""
AeroGhost - Offline Secure Bluetooth P2P Chat & File Transfer
Entry point for the desktop application.
"""

import sys
import os
import time
import subprocess
import argparse
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from core.group_manager import GroupManager
from core.storage import SecureStorage
from ui.dialogs import RoomSetupDialog
from ui.main_window import MainWindow
from ui.styles import NORMAL_STYLE


def parse_args():
    parser = argparse.ArgumentParser(description="AeroGhost Bluetooth P2P Secure Chat")
    parser.add_argument("--room", type=str, help="Room name")
    parser.add_argument("--password", type=str, help="Room password")
    parser.add_argument("--nick", type=str, help="User nickname")
    parser.add_argument("--role", choices=["host", "client"], help="Node role: host or client")
    parser.add_argument("--mode", choices=["bluetooth", "test"], default=None, help="Transport mode")
    parser.add_argument("--target", type=str, default=None, help="Target peer MAC or IP to join")
    parser.add_argument("--port", type=int, default=None, help="Port or RFCOMM channel number")
    
    # Strip any leading script or executable name if passed as first argument
    raw_args = sys.argv[1:]
    if raw_args and (raw_args[0].endswith(".py") or raw_args[0].endswith(".exe")):
        raw_args = raw_args[1:]
    return parser.parse_args(raw_args)


def _launch_dual_in_process_windows(app: QApplication, room_name: str, password: str) -> bool:
    """
    Launches Host and Client windows side-by-side directly within this Qt process.
    Completely immune to PyInstaller _MEIPASS deletion and Qt platform plugin initialization errors.
    """
    port = 19840
    
    # 1. Initialize Alice (Host Coordinator)
    alice_mgr = GroupManager(
        nickname="Alice (Host)",
        is_bluetooth_mode=False,
        db_path=f"aeroghost_{room_name}_Alice.vault"
    )
    alice_ok = alice_mgr.setup_room(
        room_name=room_name,
        password=password,
        is_host=True,
        port=port
    )
    if not alice_ok:
        QMessageBox.warning(
            None, "Port In Use",
            f"Port {port} is already in use by another running instance.\n"
            "Please close any existing AeroGhost windows and try again."
        )
        return False

    # 2. Initialize Bob (Client Member)
    bob_mgr = GroupManager(
        nickname="Bob (Client)",
        is_bluetooth_mode=False,
        db_path=f"aeroghost_{room_name}_Bob.vault"
    )
    bob_mgr.setup_room(
        room_name=room_name,
        password=password,
        is_host=False,
        port=port
    )
    time.sleep(0.3)
    bob_connected = bob_mgr.join_host("127.0.0.1", port=port)
    if not bob_connected:
        alice_mgr.shutdown()
        bob_mgr.shutdown()
        QMessageBox.warning(
            None, "Connection Failed",
            f"Unable to establish local loopback connection on port {port}."
        )
        return False

    # 3. Create both windows
    win_alice = MainWindow(alice_mgr)
    win_bob = MainWindow(bob_mgr)

    # Position side-by-side on screen
    primary_screen = app.primaryScreen()
    if primary_screen:
        geom = primary_screen.availableGeometry()
        w = min(680, (geom.width() // 2) - 16)
        h = min(720, geom.height() - 80)
        win_alice.setGeometry(geom.x() + 10, geom.y() + 40, w, h)
        win_bob.setGeometry(geom.x() + w + 20, geom.y() + 40, w, h)
    else:
        win_alice.resize(640, 600)
        win_bob.resize(640, 600)

    win_alice.show()
    win_bob.show()

    # Retain references on app to prevent Python GC from destroying windows
    app._dual_instances = (win_alice, win_bob, alice_mgr, bob_mgr)
    return True


def main():
    # Enable high-DPI scaling for crisp typography
    app = QApplication(sys.argv)
    app.setApplicationName("AeroGhost")
    app.setOrganizationName("AeroGhostP2P")
    app.setStyleSheet(NORMAL_STYLE)

    args = parse_args()
    storage = SecureStorage()

    # Determine configuration either from CLI or Interactive Setup Dialog
    if args.room and args.password and args.nick and args.role:
        room_name = args.room
        password = args.password
        nickname = args.nick
        is_host = (args.role == "host")
        is_bluetooth_mode = (args.mode != "test")
        target_addr = args.target or ("00:00:00:00:00:00" if is_bluetooth_mode else "127.0.0.1")
        port = args.port or (4 if is_bluetooth_mode else 19840)

        group_mgr = GroupManager(
            nickname=nickname,
            is_bluetooth_mode=is_bluetooth_mode,
            db_path=f"aeroghost_{room_name}_{nickname}.vault"
        )
        success = group_mgr.setup_room(
            room_name=room_name,
            password=password,
            is_host=is_host,
            port=port
        )
        if not success and is_host:
            QMessageBox.critical(
                None, "Connection Error",
                f"Failed to bind listener on port {port}."
            )
            sys.exit(1)

        if not is_host:
            connected = group_mgr.join_host(target_addr, port=port)
            if not connected:
                QMessageBox.critical(
                    None, "Connection Error",
                    f"Could not connect to peer at {target_addr}:{port}."
                )
                sys.exit(1)

        window = MainWindow(group_mgr)
        window.show()
        sys.exit(app.exec())

    # Interactive Loop (Never exits on connection failure)
    while True:
        setup_dlg = RoomSetupDialog(storage=storage)
        if not setup_dlg.exec():
            sys.exit(0)

        # Handle 1-click dual test launch
        if getattr(setup_dlg, "launch_dual_test", False):
            if _launch_dual_in_process_windows(app, setup_dlg.room_name, setup_dlg.password):
                sys.exit(app.exec())
            else:
                continue

        room_name = setup_dlg.room_name
        password = setup_dlg.password
        nickname = setup_dlg.nickname
        is_host = setup_dlg.is_host
        is_bluetooth_mode = setup_dlg.is_bluetooth_mode
        target_addr = setup_dlg.target_address
        port = setup_dlg.target_port

        # Initialize Group Manager with isolated database per room & nickname
        group_mgr = GroupManager(
            nickname=nickname,
            is_bluetooth_mode=is_bluetooth_mode,
            db_path=f"aeroghost_{room_name}_{nickname}.vault"
        )

        # Setup room and start listener if host
        success = group_mgr.setup_room(
            room_name=room_name,
            password=password,
            is_host=is_host,
            port=port
        )

        if not success and is_host:
            group_mgr.shutdown()
            mode_str = "Bluetooth" if is_bluetooth_mode else "Local Test Mesh"
            QMessageBox.warning(
                None, "Host Listener Failed",
                f"Failed to bind listener on port {port} ({mode_str}).\n\n"
                f"• For Bluetooth: Ensure Bluetooth is turned ON in Windows Settings.\n"
                f"• For Local Mesh: Port {port} may already be in use. Try a different port number."
            )
            continue  # Re-open setup dialog; do NOT crash!

        # If joining a host, initiate connection
        if not is_host:
            connected = group_mgr.join_host(target_addr, port=port)
            if not connected:
                group_mgr.shutdown()
                mode_str = "Bluetooth" if is_bluetooth_mode else "Localhost"
                QMessageBox.warning(
                    None, "Connection Failed",
                    f"Could not connect to {mode_str} peer at {target_addr}:{port}.\n\n"
                    f"Troubleshooting tips:\n"
                    f"1. Make sure the Host peer has clicked 'Create Room' first.\n"
                    f"2. Verify both devices have the same port/channel ({port}).\n"
                    f"3. To test with 2 windows instantly on this PC, click '🚀 Launch Instant 2-Window Test'."
                )
                continue  # Re-open setup dialog; do NOT crash!

        # Successful configuration - launch Main Window
        window = MainWindow(group_mgr)
        window.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
