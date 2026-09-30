"""
Main Window for AeroGhost
Integrates GroupManager, Chat Stream, File Transfers, System Tray, and Stealth Mode.
"""

import os
import html
import time
from typing import Dict, List, Any, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextBrowser, QListWidget, QListWidgetItem,
    QFrame, QProgressBar, QFileDialog, QSlider, QSystemTrayIcon,
    QMenu, QMessageBox, QApplication, QStyle
)
from PySide6.QtCore import Qt, Signal, QObject, QEvent
from PySide6.QtGui import QIcon, QKeySequence, QShortcut, QColor, QPixmap, QPainter, QFont

from core.group_manager import GroupManager
from ui.stealth_mode import StealthManager
from ui.dialogs import FileOfferDialog
from ui.styles import NORMAL_STYLE


class UiBridge(QObject):
    """Thread-safe signal bridge between background network threads and Qt GUI thread."""
    message_received = Signal(dict)
    peers_updated = Signal(list)
    file_offered = Signal(dict)
    file_progress = Signal(str, float, str)
    file_completed = Signal(str, str, bool)


class MainWindow(QMainWindow):
    """Main application window for AeroGhost."""

    def __init__(self, group_manager: GroupManager):
        super().__init__()
        self.mgr = group_manager
        self.bridge = UiBridge()
        self.stealth_mgr = StealthManager(self)
        self.auto_accept = False

        self.messages: List[Dict[str, Any]] = []
        self.setWindowTitle("AeroGhost - Bluetooth P2P Secure Chat")
        self.setWindowIcon(self._build_app_icon())
        self.resize(860, 580)
        self.setStyleSheet(NORMAL_STYLE)

        self._init_ui()
        self._setup_shortcuts()
        self._setup_tray()
        self._connect_signals()

        # Populate the roster immediately so members already connected (e.g. the
        # instant 2-window test, where the handshake finishes before this window
        # is built) are shown without waiting for the next roster event.
        self._update_peers_ui(self.mgr.get_roster())

        # Load local encrypted chat history for this room
        if self.mgr.crypto:
            cached = self.mgr.storage.load_messages(self.mgr.crypto)
            for m in cached:
                self.messages.append(m)
            self.refresh_chat_display()

    @staticmethod
    def _build_app_icon() -> QIcon:
        """Draws a small app icon in code so the window and tray entry are identifiable."""
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#0EA5E9"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(6, 6, 52, 52, 14, 14)
        painter.setPen(QColor("#F8FAFC"))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(34)
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignCenter, "A")
        painter.end()
        return QIcon(pix)

    def _init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ----------------- SIDEBAR -----------------
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(240)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(14, 16, 14, 14)
        sidebar_layout.setSpacing(10)

        # Header info
        title_lbl = QLabel("AeroGhost")
        title_lbl.setObjectName("AppTitle")
        sidebar_layout.addWidget(title_lbl)

        mode_desc = "Bluetooth RFCOMM" if self.mgr.is_bluetooth_mode else "Local Test Mesh"
        self.status_lbl = QLabel(f"● {mode_desc}\nRoom: #{self.mgr.room_name}")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #38BDF8; line-height: 140%;")
        sidebar_layout.addWidget(self.status_lbl)

        if self.mgr.is_bluetooth_mode and self.mgr.engine.local_mac:
            mac_lbl = QLabel(f"MAC: {self.mgr.engine.local_mac}")
            mac_lbl.setStyleSheet("font-size: 10px; color: #64748B;")
            sidebar_layout.addWidget(mac_lbl)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("color: #262933;")
        sidebar_layout.addWidget(sep1)

        # Active Peers Section
        peers_lbl = QLabel("ROOM MEMBERS")
        peers_lbl.setObjectName("SectionHeader")
        sidebar_layout.addWidget(peers_lbl)

        self.peer_list = QListWidget()
        self.peer_list.setObjectName("PeerList")
        sidebar_layout.addWidget(self.peer_list)

        # Trusted peers known count
        trusted = self.mgr.storage.get_trusted_peers(self.mgr.room_name or "")
        self.trusted_lbl = QLabel(f"Trusted in room: {len(trusted)}")
        self.trusted_lbl.setStyleSheet("font-size: 10px; color: #64748B;")
        sidebar_layout.addWidget(self.trusted_lbl)

        # Sidebar Buttons
        self.btn_send_file = QPushButton("Send File...")
        self.btn_send_file.clicked.connect(self._on_choose_file)
        sidebar_layout.addWidget(self.btn_send_file)

        self.btn_stealth_toggle = QPushButton("Ghost Mode (Ctrl+Shift+S)")
        self.btn_stealth_toggle.setObjectName("StealthBtn")
        self.btn_stealth_toggle.clicked.connect(self.stealth_mgr.toggle)
        sidebar_layout.addWidget(self.btn_stealth_toggle)

        root_layout.addWidget(self.sidebar)

        # ----------------- CHAT AREA -----------------
        chat_container = QWidget()
        chat_vbox = QVBoxLayout(chat_container)
        chat_vbox.setContentsMargins(0, 0, 0, 0)
        chat_vbox.setSpacing(0)

        # Stealth Mode Top Bar (hidden by default in normal mode)
        self.stealth_bar = QFrame()
        self.stealth_bar.setObjectName("InputContainer")
        self.stealth_bar.setFixedHeight(34)
        stealth_layout = QHBoxLayout(self.stealth_bar)
        stealth_layout.setContentsMargins(8, 2, 8, 2)
        
        stealth_label = QLabel("Doc Note")
        stealth_label.setStyleSheet("color: #718096; font-size: 11px;")
        stealth_layout.addWidget(stealth_label)
        stealth_layout.addStretch(1)  # push opacity + close control to the right

        # Opacity slider
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedWidth(80)
        self.opacity_slider.valueChanged.connect(lambda val: self.stealth_mgr.set_opacity(val / 100.0))
        stealth_layout.addWidget(QLabel("Alpha:"))
        stealth_layout.addWidget(self.opacity_slider)

        self.btn_exit_stealth = QPushButton("✕")
        self.btn_exit_stealth.setFixedSize(22, 22)
        self.btn_exit_stealth.clicked.connect(self.stealth_mgr.exit_stealth)
        stealth_layout.addWidget(self.btn_exit_stealth)

        chat_vbox.addWidget(self.stealth_bar)
        self.stealth_bar.setVisible(False)

        # File Transfer Banner
        self.transfer_banner = QFrame()
        self.transfer_banner.setStyleSheet("background-color: #1E222D; padding: 6px; border-bottom: 1px solid #282C3A;")
        t_layout = QVBoxLayout(self.transfer_banner)
        t_layout.setContentsMargins(12, 4, 12, 4)
        self.transfer_lbl = QLabel("Transferring: ...")
        self.transfer_lbl.setTextFormat(Qt.PlainText)  # never interpret a peer's filename as markup
        self.transfer_lbl.setStyleSheet("font-size: 11px; color: #E2E8F0;")
        self.transfer_bar = QProgressBar()
        self.transfer_bar.setRange(0, 100)
        self.transfer_bar.setValue(0)
        t_layout.addWidget(self.transfer_lbl)
        t_layout.addWidget(self.transfer_bar)
        chat_vbox.addWidget(self.transfer_banner)
        self.transfer_banner.setVisible(False)

        # Main Chat Message View
        self.chat_area = QTextBrowser()
        self.chat_area.setObjectName("ChatArea")
        self.chat_area.setOpenExternalLinks(False)
        chat_vbox.addWidget(self.chat_area)

        # Bottom Input Area
        self.input_container = QFrame()
        self.input_container.setObjectName("InputContainer")
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(10, 8, 10, 8)
        input_layout.setSpacing(8)

        self.msg_input = QLineEdit()
        self.msg_input.setObjectName("MessageInput")
        self.msg_input.setPlaceholderText("Type a message (End-to-end encrypted)...")
        self.msg_input.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.msg_input)

        self.btn_send = QPushButton("Send")
        self.btn_send.setObjectName("PrimaryBtn")
        self.btn_send.clicked.connect(self._send_message)
        input_layout.addWidget(self.btn_send)

        chat_vbox.addWidget(self.input_container)
        root_layout.addWidget(chat_container)

    def _setup_shortcuts(self):
        # Ctrl+Shift+S: Toggle Stealth Mode
        self.shortcut_stealth = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        self.shortcut_stealth.activated.connect(self.stealth_mgr.toggle)

        # Ctrl+Shift+H: Boss Key (Hide to system tray)
        self.shortcut_boss = QShortcut(QKeySequence("Ctrl+Shift+H"), self)
        self.shortcut_boss.activated.connect(self.hide_to_tray)

        # Esc: exit stealth mode. Handled via an application-level event filter
        # rather than a QShortcut -- a per-window Escape shortcut is consumed
        # ambiguously when two windows are open, which swallows the key without
        # firing. The filter below sees the KeyPress directly and is reliable.
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        """Exit stealth on Escape no matter which child widget currently has focus.

        Scoped by is_stealth only (not isActiveWindow, which a stays-on-top stealth
        window can report False even while focused). Escape acts as a panic exit.
        """
        if (event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape
                and self.stealth_mgr.is_stealth):
            self.stealth_mgr.exit_stealth()
            return True
        return super().eventFilter(obj, event)

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("AeroGhost - click to show/hide")

        tray_menu = QMenu()
        action_show = tray_menu.addAction("Open AeroGhost")
        action_show.triggered.connect(self.restore_from_tray)
        
        action_stealth = tray_menu.addAction("Toggle Ghost Mode")
        action_stealth.triggered.connect(self.stealth_mgr.toggle)
        
        tray_menu.addSeparator()
        action_quit = tray_menu.addAction("Quit Application")
        action_quit.triggered.connect(self.close)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide_to_tray()
            else:
                self.restore_from_tray()

    def hide_to_tray(self):
        self.hide()
        self.tray_icon.showMessage("AeroGhost", "Minimized to tray. Press Ctrl+Shift+H to restore.", QSystemTrayIcon.Information, 2000)

    def restore_from_tray(self):
        self.showNormal()
        self.activateWindow()

    def _connect_signals(self):
        # Hook group manager callbacks to Qt Bridge
        self.mgr.on_message_received = self.bridge.message_received.emit
        self.mgr.on_peers_updated = self.bridge.peers_updated.emit
        self.mgr.on_file_offered = self.bridge.file_offered.emit
        self.mgr.on_file_progress = self.bridge.file_progress.emit
        self.mgr.on_file_completed = self.bridge.file_completed.emit

        # Connect signals to GUI handlers
        self.bridge.message_received.connect(self._handle_incoming_message)
        self.bridge.peers_updated.connect(self._update_peers_ui)
        self.bridge.file_offered.connect(self._prompt_incoming_file)
        self.bridge.file_progress.connect(self._update_file_progress)
        self.bridge.file_completed.connect(self._on_file_completed)

    def _send_message(self):
        text = self.msg_input.text().strip()
        if not text:
            return

        msg_packet = self.mgr.send_chat_message(text)
        self.msg_input.clear()
        self.messages.append(msg_packet)
        self._append_message_ui(msg_packet)

    def _handle_incoming_message(self, msg_packet: Dict[str, Any]):
        self.messages.append(msg_packet)
        self._append_message_ui(msg_packet)

    def _update_peers_ui(self, peers: List[Dict[str, str]]):
        self.peer_list.clear()
        for p in peers:
            nick = p.get("nickname", "Peer")
            pid = p.get("id", "")
            is_self = (pid == self.mgr.peer_id)
            display = f"● {nick} (You)" if is_self else f"● {nick}"
            item = QListWidgetItem(display)
            item.setForeground(QColor("#38BDF8" if is_self else "#4ADE80"))
            self.peer_list.addItem(item)

    def refresh_chat_display(self):
        """Re-renders chat messages according to the active mode."""
        self.chat_area.clear()
        for msg in self.messages:
            self._append_message_ui(msg)

    def _append_message_ui(self, msg: Dict[str, Any]):
        # Peer-supplied fields are escaped so a message can never inject markup or
        # a remote resource reference into the rich-text view.
        sender = html.escape(str(msg.get("sender", "Peer")))
        content = html.escape(str(msg.get("content", "")))
        ts = msg.get("timestamp", time.time())
        try:
            time_str = time.strftime("%H:%M", time.localtime(float(ts)))
        except (ValueError, TypeError, OSError):
            time_str = time.strftime("%H:%M", time.localtime())
        is_self = (msg.get("sender_id") == self.mgr.peer_id)

        if self.stealth_mgr.is_stealth:
            # Discreet plain-text document style
            markup = (
                f"<div style='margin-bottom: 4px; font-family: monospace; font-size: 11px; color: #2D3748;'>"
                f"<span style='color: #718096;'>[{time_str}]</span> "
                f"<b>{sender}:</b> {content}"
                f"</div>"
            )
        else:
            # Rendered as a single-cell table: Qt's rich-text engine ignores
            # inline-block/border-radius/max-width, but it does honour table
            # alignment, width and cell background, giving an aligned, padded bubble.
            bubble_bg = "#0369A1" if is_self else "#1E2028"
            align = "right" if is_self else "left"
            sender_color = "#BAE6FD" if is_self else "#38BDF8"
            markup = (
                f"<table width='72%' align='{align}' cellpadding='7' cellspacing='0' style='margin: 3px 0;'>"
                f"<tr><td style='background-color: {bubble_bg};'>"
                f"<span style='font-size: 11px; font-weight: 600; color: {sender_color};'>{sender}</span>"
                f" <span style='font-size: 9px; color: #94A3B8;'>{time_str}</span><br>"
                f"<span style='font-size: 13px; color: #F8FAFC;'>{content}</span>"
                f"</td></tr></table>"
            )

        self.chat_area.append(markup)
        # Scroll to bottom
        sb = self.chat_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_choose_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File to Send over Bluetooth")
        if not file_path or not os.path.exists(file_path):
            return

        transfer = self.mgr.send_file(file_path)
        if transfer:
            self.transfer_banner.setVisible(True)
            self.transfer_lbl.setText(f"Offering '{transfer.filename}' to peers...")
            self.transfer_bar.setValue(0)

    def _prompt_incoming_file(self, offer_packet: Dict[str, Any]):
        sender = offer_packet.get("sender", "Peer")
        fname = offer_packet.get("filename", "unknown")
        fsize = int(offer_packet.get("filesize", 0))
        tid = offer_packet.get("transfer_id")

        if self.auto_accept:
            self.mgr.accept_file(tid)
            self.transfer_banner.setVisible(True)
            self.transfer_lbl.setText(f"Downloading '{fname}' from {sender}...")
            self.transfer_bar.setValue(0)
            return

        dlg = FileOfferDialog(sender, fname, fsize, self)
        if dlg.exec():
            self.mgr.accept_file(tid)
            self.transfer_banner.setVisible(True)
            self.transfer_lbl.setText(f"Downloading '{fname}' from {sender}...")
            self.transfer_bar.setValue(0)

    def _update_file_progress(self, transfer_id: str, percent: float, filename: str):
        self.transfer_banner.setVisible(True)
        self.transfer_lbl.setText(f"Transferring '{filename}' ({percent:.1f}%)")
        self.transfer_bar.setValue(int(percent))

    def _on_file_completed(self, transfer_id: str, filename: str, success: bool):
        self.transfer_banner.setVisible(False)
        if not self.auto_accept:
            if success:
                QMessageBox.information(self, "File Transfer", f"File '{filename}' transferred and verified successfully via SHA-256!")
            else:
                QMessageBox.warning(self, "File Transfer", f"File transfer for '{filename}' failed or checksum mismatch.")

    def closeEvent(self, event):
        """Ensures clean shutdown of background Bluetooth listeners and sockets."""
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.mgr.shutdown()
        event.accept()
