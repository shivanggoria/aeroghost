"""
Dialog Windows for AeroGhost
Room setup, connection configuration, and incoming file transfer prompts.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QRadioButton, QButtonGroup, QComboBox, 
    QMessageBox, QFrame, QSpinBox, QCheckBox, QScrollArea, QWidget
)
from PySide6.QtCore import Qt
from core.bluetooth_engine import BluetoothEngine
from core.storage import SecureStorage
from ui.styles import NORMAL_STYLE


class RoomSetupDialog(QDialog):
    """Modal dialog for creating or joining an encrypted room."""

    def __init__(self, storage: SecureStorage, default_nick: str = "User", parent=None):
        super().__init__(parent)
        self.storage = storage
        self.setWindowTitle("AeroGhost - Room Setup")
        self.setMinimumWidth(520)
        self.setMinimumHeight(640)
        self.resize(540, 700)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(NORMAL_STYLE)

        # Output fields
        self.room_name = ""
        self.password = ""
        self.nickname = ""
        self.is_host = True
        self.is_bluetooth_mode = False  # Default to Local Test Mesh for instant local reliability!
        self.target_address = "127.0.0.1"
        self.target_port = 19840
        self.launch_dual_test = False

        self._build_ui(default_nick)

    def _build_ui(self, default_nick: str):
        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(12)
        root_layout.setContentsMargins(20, 18, 20, 18)

        # Header Title (Fixed at top)
        title_lbl = QLabel("Secure Bluetooth P2P Setup")
        title_lbl.setStyleSheet("font-size: 17px; font-weight: bold; color: #38BDF8;")
        desc_lbl = QLabel("100% Offline • Zero Telemetry • AES-256-GCM Encrypted")
        desc_lbl.setStyleSheet("font-size: 11px; color: #94A3B8; margin-bottom: 2px;")
        root_layout.addWidget(title_lbl)
        root_layout.addWidget(desc_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #334155; margin-bottom: 4px;")
        root_layout.addWidget(sep)

        # Scrollable form container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        form_layout = QVBoxLayout(scroll_widget)
        form_layout.setSpacing(12)
        form_layout.setContentsMargins(0, 2, 4, 2)

        # Quick Instant 2-Window Local Test Button
        self.btn_instant_test = QPushButton("🚀  Launch Instant 2-Window Test (Side-by-Side)")
        self.btn_instant_test.setObjectName("InstantTestBtn")
        self.btn_instant_test.setMinimumHeight(36)
        self.btn_instant_test.setToolTip("Automatically opens Host and Client side-by-side on this PC")
        self.btn_instant_test.clicked.connect(self._on_instant_test_clicked)
        form_layout.addWidget(self.btn_instant_test)

        # Role Selector (Modern Segmented Button Tabs)
        role_label = QLabel("SELECT YOUR ROLE:")
        role_label.setStyleSheet("font-size: 10px; font-weight: bold; color: #64748B; letter-spacing: 0.5px;")
        form_layout.addWidget(role_label)

        role_container = QHBoxLayout()
        role_container.setSpacing(8)
        self.btn_role_host = QPushButton("👑  Create Room (Host)")
        self.btn_role_host.setProperty("role", "segment")
        self.btn_role_host.setCheckable(True)
        self.btn_role_host.setChecked(True)
        self.btn_role_host.setMinimumHeight(40)

        self.btn_role_join = QPushButton("🔗  Join Room (Connect)")
        self.btn_role_join.setProperty("role", "segment")
        self.btn_role_join.setCheckable(True)
        self.btn_role_join.setMinimumHeight(40)

        self.role_group = QButtonGroup(self)
        self.role_group.setExclusive(True)
        self.role_group.addButton(self.btn_role_host)
        self.role_group.addButton(self.btn_role_join)
        self.btn_role_host.clicked.connect(self._toggle_role_ui)
        self.btn_role_join.clicked.connect(self._toggle_role_ui)
        role_container.addWidget(self.btn_role_host)
        role_container.addWidget(self.btn_role_join)
        form_layout.addLayout(role_container)

        # Transport Mode (Modern Segmented Button Tabs)
        mode_label = QLabel("SELECT NETWORK MODE:")
        mode_label.setStyleSheet("font-size: 10px; font-weight: bold; color: #64748B; letter-spacing: 0.5px;")
        form_layout.addWidget(mode_label)

        transport_container = QHBoxLayout()
        transport_container.setSpacing(8)
        self.btn_mode_test = QPushButton("💻  Local Test Mesh (1 PC)")
        self.btn_mode_test.setProperty("role", "segment")
        self.btn_mode_test.setCheckable(True)
        self.btn_mode_test.setChecked(True)  # Default to Local Test Mesh for 1-click test reliability
        self.btn_mode_test.setMinimumHeight(40)

        self.btn_mode_bt = QPushButton("📡  Bluetooth RFCOMM (2 PCs)")
        self.btn_mode_bt.setProperty("role", "segment")
        self.btn_mode_bt.setCheckable(True)
        self.btn_mode_bt.setMinimumHeight(40)

        self.transport_group = QButtonGroup(self)
        self.transport_group.setExclusive(True)
        self.transport_group.addButton(self.btn_mode_test)
        self.transport_group.addButton(self.btn_mode_bt)
        self.btn_mode_test.clicked.connect(self._toggle_transport_ui)
        self.btn_mode_bt.clicked.connect(self._toggle_transport_ui)
        transport_container.addWidget(self.btn_mode_test)
        transport_container.addWidget(self.btn_mode_bt)
        form_layout.addLayout(transport_container)

        # Two-column row: Nickname (left) and Room Name (right)
        row_nick_room = QHBoxLayout()
        row_nick_room.setSpacing(12)

        col_nick = QVBoxLayout()
        col_nick.setSpacing(4)
        nick_lbl = QLabel("Your Nickname:")
        nick_lbl.setStyleSheet("font-weight: 500; color: #E2E8F0;")
        self.nick_edit = QLineEdit(default_nick)
        self.nick_edit.setMinimumHeight(36)
        col_nick.addWidget(nick_lbl)
        col_nick.addWidget(self.nick_edit)
        row_nick_room.addLayout(col_nick)

        col_room = QVBoxLayout()
        col_room.setSpacing(4)
        room_lbl = QLabel("Room Name:")
        room_lbl.setStyleSheet("font-weight: 500; color: #E2E8F0;")
        self.room_combo = QComboBox()
        self.room_combo.setEditable(True)
        self.room_combo.setMinimumHeight(36)
        recent_rooms = self.storage.get_recent_rooms()
        if recent_rooms:
            self.room_combo.addItems(recent_rooms)
        else:
            self.room_combo.addItem("general-room")
        col_room.addWidget(room_lbl)
        col_room.addWidget(self.room_combo)
        row_nick_room.addLayout(col_room)

        form_layout.addLayout(row_nick_room)

        # Room Password
        pass_vbox = QVBoxLayout()
        pass_vbox.setSpacing(4)
        pass_lbl = QLabel("Room Password (for E2EE encryption):")
        pass_lbl.setStyleSheet("font-weight: 500; color: #E2E8F0;")
        self.pass_edit = QLineEdit()
        self.pass_edit.setMinimumHeight(36)
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass_edit.setPlaceholderText("Enter shared room passphrase...")
        pass_vbox.addWidget(pass_lbl)
        pass_vbox.addWidget(self.pass_edit)
        form_layout.addLayout(pass_vbox)

        # Target address section (only visible when Joining)
        self.target_frame = QFrame()
        self.target_frame.setStyleSheet(
            "QFrame#TargetFrame { background-color: #161820; border: 1px solid #2B2F3D; border-radius: 8px; padding: 8px; }"
        )
        self.target_frame.setObjectName("TargetFrame")
        target_vbox = QVBoxLayout(self.target_frame)
        target_vbox.setContentsMargins(10, 10, 10, 10)
        target_vbox.setSpacing(8)

        self.target_lbl = QLabel("Peer Bluetooth MAC or Loopback Address:")
        self.target_lbl.setStyleSheet("font-weight: 600; color: #38BDF8;")
        target_vbox.addWidget(self.target_lbl)

        # Address input with quick Localhost shortcut button
        row_addr = QHBoxLayout()
        row_addr.setSpacing(8)
        self.target_edit = QLineEdit()
        self.target_edit.setMinimumHeight(36)
        self.target_edit.setPlaceholderText("e.g. 58:CD:C9:F6:F2:5A or 127.0.0.1")
        row_addr.addWidget(self.target_edit, 3)

        self.btn_fill_local = QPushButton("⚡ Localhost")
        self.btn_fill_local.setMinimumHeight(36)
        self.btn_fill_local.setToolTip("Click to switch to Local Test Mesh and pre-fill 127.0.0.1")
        self.btn_fill_local.clicked.connect(self._fill_localhost)
        row_addr.addWidget(self.btn_fill_local, 1)
        target_vbox.addLayout(row_addr)

        # Sub-row for Scan button and Port
        row_scan_port = QHBoxLayout()
        row_scan_port.setSpacing(10)

        self.scan_btn = QPushButton("Scan Nearby Devices")
        self.scan_btn.setMinimumHeight(36)
        self.scan_btn.clicked.connect(lambda: self._scan_devices(silent=False))
        row_scan_port.addWidget(self.scan_btn, 2)

        col_port = QHBoxLayout()
        col_port.setSpacing(6)
        self.port_lbl = QLabel("Port:")
        self.port_lbl.setStyleSheet("font-weight: 500; color: #E2E8F0;")
        self.port_spin = QSpinBox()
        self.port_spin.setMinimumHeight(36)
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(4)
        col_port.addWidget(self.port_lbl)
        col_port.addWidget(self.port_spin)
        row_scan_port.addLayout(col_port, 1)

        target_vbox.addLayout(row_scan_port)

        self.device_combo = QComboBox()
        self.device_combo.setMinimumHeight(36)
        self.device_combo.currentIndexChanged.connect(self._on_device_selected)
        self.device_combo.setVisible(False)
        target_vbox.addWidget(self.device_combo)

        form_layout.addWidget(self.target_frame)
        self.target_frame.setVisible(False)

        # Backward-compatibility aliases so old tests or references never fail
        self.radio_host = self.btn_role_host
        self.radio_join = self.btn_role_join
        self.radio_test = self.btn_mode_test
        self.radio_bt = self.btn_mode_bt

        scroll.setWidget(scroll_widget)
        root_layout.addWidget(scroll, 1)

        # Buttons pinned to bottom
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(38)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.start_btn = QPushButton("Launch Room")
        self.start_btn.setMinimumHeight(38)
        self.start_btn.setObjectName("PrimaryBtn")
        self.start_btn.clicked.connect(self._validate_and_accept)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.start_btn)
        root_layout.addLayout(btn_layout)

    def _on_instant_test_clicked(self):
        """Prepares configuration for launching two connected instances on this PC."""
        self.launch_dual_test = True
        self.room_name = self.room_combo.currentText().strip() or "test-room"
        self.password = self.pass_edit.text().strip() or "pass123"
        self.nickname = self.nick_edit.text().strip() or "Alice"
        self.is_host = True
        self.is_bluetooth_mode = False
        self.target_address = "127.0.0.1"
        self.target_port = 19840
        self.accept()

    def _fill_localhost(self):
        """Switches to Local Test Mesh and pre-fills 127.0.0.1."""
        self.btn_mode_test.setChecked(True)
        self._toggle_transport_ui()
        self.target_edit.setText("127.0.0.1")
        self.port_spin.setValue(19840)

    def _toggle_role_ui(self):
        is_join = self.btn_role_join.isChecked()
        self.target_frame.setVisible(is_join)
        self.start_btn.setText("Connect to Room" if is_join else "Launch Room")
        if is_join:
            self.resize(540, 700)
            # Automatic smart pre-fill
            if self.btn_mode_test.isChecked():
                if not self.target_edit.text() or ":" in self.target_edit.text():
                    self.target_edit.setText("127.0.0.1")
            elif self.btn_mode_bt.isChecked():
                if not self.target_edit.text():
                    self._scan_devices(silent=True)
        else:
            self.resize(540, 560)

    def _toggle_transport_ui(self):
        is_bt = self.btn_mode_bt.isChecked()
        if is_bt:
            self.target_lbl.setText("Peer Bluetooth MAC Address:")
            self.target_edit.setPlaceholderText("e.g. 58:CD:C9:F6:F2:5A or select scanned device")
            if self.target_edit.text() == "127.0.0.1":
                self.target_edit.clear()
            self.port_lbl.setText("Channel:")
            self.port_spin.setRange(1, 30)
            self.port_spin.setValue(4)
            self.scan_btn.setVisible(True)
            if not self.target_edit.text():
                self._scan_devices(silent=True)
        else:
            self.target_lbl.setText("Target Loopback Address:")
            self.target_edit.setText("127.0.0.1")
            self.target_edit.setPlaceholderText("127.0.0.1")
            self.port_lbl.setText("Port:")
            self.port_spin.setRange(1024, 65535)
            self.port_spin.setValue(19840)
            self.scan_btn.setVisible(False)
            self.device_combo.setVisible(False)

    def _scan_devices(self, silent: bool = False):
        self.scan_btn.setText("Scanning Bluetooth devices...")
        self.scan_btn.setEnabled(False)
        devices = BluetoothEngine.scan_windows_bluetooth_devices()
        self.scan_btn.setText("Scan Nearby Devices")
        self.scan_btn.setEnabled(True)

        if devices:
            self.device_combo.clear()
            self.device_combo.addItem("-- Select Discovered Bluetooth Device --", "")
            for dev in devices:
                label = f"{dev['name']} ({dev['mac']})" if dev['mac'] else dev['name']
                self.device_combo.addItem(label, dev['mac'])
            self.device_combo.setVisible(True)

            # If address is still blank, auto-populate with first scanned device
            if not self.target_edit.text() and len(devices) > 0 and devices[0].get("mac"):
                self.device_combo.setCurrentIndex(1)
                self.target_edit.setText(devices[0]["mac"])
        else:
            if not silent:
                QMessageBox.information(
                    self, "Bluetooth Scan", 
                    "No active Bluetooth devices returned from scan. You can enter the peer's MAC manually, or click '⚡ Localhost' to test on this PC."
                )

    def _on_device_selected(self, index: int):
        mac = self.device_combo.currentData()
        if mac:
            self.target_edit.setText(mac)

    def _validate_and_accept(self):
        room = self.room_combo.currentText().strip()
        pwd = self.pass_edit.text().strip()
        nick = self.nick_edit.text().strip()

        if not room:
            QMessageBox.warning(self, "Missing Field", "Please specify a room name.")
            return
        if not pwd:
            QMessageBox.warning(self, "Missing Field", "Please specify a room password.")
            return
        if not nick:
            QMessageBox.warning(self, "Missing Field", "Please enter a nickname.")
            return

        self.room_name = room
        self.password = pwd
        self.nickname = nick
        self.is_host = self.btn_role_host.isChecked()
        self.is_bluetooth_mode = self.btn_mode_bt.isChecked()
        self.target_address = self.target_edit.text().strip()
        self.target_port = self.port_spin.value()

        if not self.is_host and not self.target_address:
            QMessageBox.warning(
                self, "Missing Target Address",
                "Please enter the target address to connect:\n\n"
                "• Testing on THIS computer? Select 'Local Test Mesh' above (connects to 127.0.0.1).\n\n"
                "• Connecting to a FRIEND over Bluetooth? Enter their Bluetooth MAC address (visible in their AeroGhost sidebar)."
            )
            return

        self.accept()


class FileOfferDialog(QDialog):
    """Prompt for incoming file transfer."""

    def __init__(self, sender: str, filename: str, filesize: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Incoming File Transfer")
        self.setFixedSize(360, 160)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("Peer Wants to Send a File")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #38BDF8;")
        layout.addWidget(title)

        size_kb = filesize / 1024.0
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024.0:.2f} MB"
        
        info = QLabel(f"<b>{sender}</b> is offering to send:<br><b>{filename}</b> ({size_str})")
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_layout = QHBoxLayout()
        self.decline_btn = QPushButton("Decline")
        self.decline_btn.clicked.connect(self.reject)
        self.accept_btn = QPushButton("Accept File")
        self.accept_btn.setObjectName("PrimaryBtn")
        self.accept_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.decline_btn)
        btn_layout.addWidget(self.accept_btn)
        layout.addLayout(btn_layout)
