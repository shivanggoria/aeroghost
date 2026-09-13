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
    return parser.parse_args()


def _launch_dual_local_instances(room_name: str, password: str):
    """Launches Host and Client instances side-by-side on this machine for instant verification."""
    python_exe = sys.executable
    port = 19840
    cwd = os.path.dirname(os.path.abspath(__file__))

    # 1. Launch Host instance
    host_cmd = [
        python_exe, "main.py",
        "--room", room_name,
        "--password", password,
        "--nick", "Alice (Host)",
        "--role", "host",
        "--mode", "test",
        "--port", str(port)
    ]
    subprocess.Popen(host_cmd, cwd=cwd)

    # Allow 0.8s for host listener socket to initialize
    time.sleep(0.8)

    # 2. Launch Client instance
    client_cmd = [
        python_exe, "main.py",
        "--room", room_name,
        "--password", password,
        "--nick", "Bob (Client)",
        "--role", "client",
        "--mode", "test",
        "--target", "127.0.0.1",
        "--port", str(port)
    ]
    subprocess.Popen(client_cmd, cwd=cwd)


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
            _launch_dual_local_instances(setup_dlg.room_name, setup_dlg.password)
            sys.exit(0)

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
