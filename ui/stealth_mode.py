"""
Stealth Mode ("Ghost Mode") Manager for AeroGhost
Transforms the chat application into a discreet, compact, document-styled floating window.
"""

from typing import Optional
from PySide6.QtCore import Qt, QRect
from PySide6.QtWidgets import QMainWindow, QApplication
from ui.styles import NORMAL_STYLE, STEALTH_STYLE


class StealthManager:
    """Controls the window transformation and styling for Stealth Mode."""

    STEALTH_WIDTH = 340
    STEALTH_HEIGHT = 440
    _WIDGET_SIZE_MAX = 16777215  # Qt's QWIDGETSIZE_MAX, used to release a fixed-size lock

    def __init__(self, main_window: QMainWindow):
        self.win = main_window
        self.is_stealth = False
        self.saved_geometry: Optional[QRect] = None
        self.saved_opacity = 1.0

    def toggle(self):
        """Toggles between Normal Mode and Stealth Mode."""
        if self.is_stealth:
            self.exit_stealth()
        else:
            self.enter_stealth()

    def enter_stealth(self):
        """Snaps window to screen edge, applies document-white styling, and compacts UI."""
        if self.is_stealth:
            return

        self.saved_geometry = self.win.geometry()
        self.is_stealth = True

        # Let the window shrink below its normal minimum before compacting it.
        self.win.setMinimumSize(0, 0)

        # Apply flags for floating on top
        self.win.setWindowFlags(self.win.windowFlags() | Qt.WindowStaysOnTopHint)
        self.win.setStyleSheet(STEALTH_STYLE)

        # Disguise window title
        self.win.setWindowTitle("Notes - Scratchpad")

        # Hide full sidebar, switch to stealth layout
        self.win.sidebar.setVisible(False)
        self.win.stealth_bar.setVisible(True)
        self.win.btn_stealth_toggle.setText("Exit Ghost")

        # Lock to the compact size so contents (incl. the exit control) can't
        # push the window past the screen edge, then snap fully on-screen.
        self.win.setFixedSize(self.STEALTH_WIDTH, self.STEALTH_HEIGHT)
        screen = QApplication.primaryScreen().availableGeometry()
        x = max(screen.left(), screen.right() - self.STEALTH_WIDTH - 20)
        y = screen.top() + 40
        self.win.move(x, y)

        # Render messages in plain text document style
        self.win.refresh_chat_display()
        self.win.show()

    def exit_stealth(self):
        """Restores full minimalist dark window and normal chat layout."""
        if not self.is_stealth:
            return

        self.is_stealth = False
        self.win.setWindowFlags(self.win.windowFlags() & ~Qt.WindowContextHelpButtonHint & ~Qt.WindowStaysOnTopHint)
        self.win.setStyleSheet(NORMAL_STYLE)

        # Release the compact fixed-size lock applied in enter_stealth.
        self.win.setMinimumSize(0, 0)
        self.win.setMaximumSize(self._WIDGET_SIZE_MAX, self._WIDGET_SIZE_MAX)

        # Restore window geometry
        if self.saved_geometry:
            self.win.setGeometry(self.saved_geometry)
        else:
            self.win.resize(840, 580)

        self.win.setWindowTitle("AeroGhost - Bluetooth P2P Secure Chat")
        self.win.sidebar.setVisible(True)
        self.win.stealth_bar.setVisible(False)
        self.win.btn_stealth_toggle.setText("Ghost Mode (Ctrl+Shift+S)")

        self.win.setWindowOpacity(1.0)
        self.win.refresh_chat_display()
        self.win.show()

    def set_opacity(self, opacity_value: float):
        """Adjusts window opacity (0.2 to 1.0)."""
        clamped = max(0.2, min(1.0, opacity_value))
        self.win.setWindowOpacity(clamped)
