"""
Modern Aesthetic Stylesheets for AeroGhost
Contains Normal Mode (sleek dark aesthetic) and Stealth Mode (plain white document disguise).
"""

NORMAL_STYLE = """
QMainWindow, QDialog, QWidget#CentralWidget {
    background-color: #121316;
    color: #E2E8F0;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
}

/* Left Sidebar */
QFrame#Sidebar {
    background-color: #18191E;
    border-right: 1px solid #23252B;
}

QLabel#AppTitle {
    font-size: 16px;
    font-weight: bold;
    color: #F8FAFC;
    letter-spacing: 0.5px;
}

QLabel#SectionHeader {
    font-size: 11px;
    font-weight: 600;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* Peer List */
QListWidget#PeerList {
    background-color: transparent;
    border: none;
    color: #CBD5E1;
}

QListWidget#PeerList::item {
    padding: 8px 12px;
    border-radius: 6px;
    margin-bottom: 2px;
}

QListWidget#PeerList::item:hover {
    background-color: #23252E;
}

QListWidget#PeerList::item:selected {
    background-color: #2D313E;
    color: #38BDF8;
}

/* Chat View */
QTextBrowser#ChatArea {
    background-color: #121316;
    border: none;
    color: #E2E8F0;
    selection-background-color: #38BDF8;
    selection-color: #0F172A;
    padding: 10px;
}

/* Input Area */
QFrame#InputContainer {
    background-color: #18191E;
    border-top: 1px solid #23252B;
    padding: 8px;
}

/* Input Fields */
QLineEdit, QComboBox, QSpinBox {
    background-color: #1E2028;
    border: 1px solid #2E323D;
    border-radius: 6px;
    padding: 8px 12px;
    color: #F8FAFC;
    font-size: 13px;
    min-height: 20px;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #38BDF8;
    background-color: #242733;
}

QComboBox::drop-down {
    border: none;
    width: 26px;
    subcontrol-position: right center;
}

QComboBox QAbstractItemView {
    background-color: #1E2028;
    border: 1px solid #333644;
    selection-background-color: #0284C7;
    color: #F8FAFC;
    padding: 4px;
}

QRadioButton {
    color: #E2E8F0;
    font-size: 13px;
    spacing: 8px;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 2px solid #64748B;
    background-color: #18191E;
}

QRadioButton::indicator:checked {
    border-color: #38BDF8;
    background-color: #0284C7;
}

QLineEdit#MessageInput {
    background-color: #22242B;
    border: 1px solid #2E323B;
    border-radius: 8px;
    padding: 10px 14px;
    color: #F8FAFC;
    font-size: 13px;
}

QLineEdit#MessageInput:focus {
    border: 1px solid #38BDF8;
    background-color: #262933;
}

/* Buttons */
QPushButton {
    background-color: #262832;
    border: 1px solid #333642;
    border-radius: 6px;
    padding: 8px 14px;
    color: #F1F5F9;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #323542;
    border-color: #474B5C;
}

QPushButton:pressed {
    background-color: #1D1E26;
}

QPushButton#PrimaryBtn {
    background-color: #0284C7;
    border: 1px solid #0369A1;
    color: #FFFFFF;
    font-weight: 600;
}

QPushButton#PrimaryBtn:hover {
    background-color: #0369A1;
}

/* Segmented Toggle Buttons for Dialog */
QPushButton[role="segment"] {
    background-color: #1A1C24;
    border: 1px solid #2B2F3D;
    border-radius: 8px;
    padding: 9px 14px;
    color: #94A3B8;
    font-size: 13px;
    font-weight: 600;
    min-height: 20px;
}

QPushButton[role="segment"]:hover {
    background-color: #222530;
    color: #F1F5F9;
    border-color: #38BDF8;
}

QPushButton[role="segment"]:checked {
    background-color: #0284C7;
    border: 1px solid #38BDF8;
    color: #FFFFFF;
    font-weight: bold;
}

QPushButton#InstantTestBtn {
    background-color: #1E293B;
    border: 1px dashed #38BDF8;
    color: #38BDF8;
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 12px;
}

QPushButton#InstantTestBtn:hover {
    background-color: #0F172A;
    border-color: #7DD3FC;
    color: #BAE6FD;
}

QPushButton#StealthBtn {
    background-color: #1E293B;
    border: 1px solid #334155;
    color: #94A3B8;
}

QPushButton#StealthBtn:hover {
    background-color: #334155;
    color: #F8FAFC;
}

/* Progress bar */
QProgressBar {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 4px;
    text-align: center;
    color: #E2E8F0;
    font-size: 11px;
    height: 16px;
}

QProgressBar::chunk {
    background-color: #38BDF8;
    border-radius: 3px;
}
"""

STEALTH_STYLE = """
QMainWindow, QDialog, QWidget#CentralWidget {
    background-color: #FFFFFF;
    color: #2D3748;
    font-family: 'Consolas', 'Courier New', 'Segoe UI', monospace;
    font-size: 11px;
}

/* Disguised Sidebar / Header */
QFrame#Sidebar {
    background-color: #F7FAFC;
    border-right: 1px solid #E2E8F0;
}

QLabel#AppTitle {
    font-size: 11px;
    font-weight: normal;
    color: #718096;
    letter-spacing: normal;
}

QLabel#SectionHeader {
    font-size: 10px;
    font-weight: normal;
    color: #A0AEC0;
}

/* Disguised Peer List */
QListWidget#PeerList {
    background-color: transparent;
    border: none;
    color: #4A5568;
    font-size: 11px;
}

QListWidget#PeerList::item {
    padding: 3px 6px;
}

QListWidget#PeerList::item:hover {
    background-color: #EDF2F7;
}

QListWidget#PeerList::item:selected {
    background-color: #E2E8F0;
    color: #2D3748;
}

/* Document / Scratchpad Style Chat Area */
QTextBrowser#ChatArea {
    background-color: #FFFFFF;
    border: none;
    color: #2D3748;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
    padding: 6px;
}

/* Minimalist Input */
QFrame#InputContainer {
    background-color: #F7FAFC;
    border-top: 1px solid #E2E8F0;
    padding: 4px;
}

QLineEdit#MessageInput {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E0;
    border-radius: 2px;
    padding: 4px 8px;
    color: #2D3748;
    font-family: 'Consolas', monospace;
    font-size: 11px;
}

QLineEdit#MessageInput:focus {
    border: 1px solid #A0AEC0;
    background-color: #FFFFFF;
}

/* Inconspicuous Plain Buttons */
QPushButton {
    background-color: #EDF2F7;
    border: 1px solid #CBD5E0;
    border-radius: 2px;
    padding: 4px 8px;
    color: #4A5568;
    font-size: 10px;
    font-weight: normal;
}

QPushButton:hover {
    background-color: #E2E8F0;
}

QPushButton#PrimaryBtn {
    background-color: #E2E8F0;
    border: 1px solid #CBD5E0;
    color: #2D3748;
}

QPushButton#StealthBtn {
    background-color: #F7FAFC;
    border: 1px solid #E2E8F0;
    color: #718096;
}

QProgressBar {
    background-color: #EDF2F7;
    border: 1px solid #CBD5E0;
    border-radius: 2px;
    text-align: center;
    color: #4A5568;
    font-size: 9px;
    height: 10px;
}

QProgressBar::chunk {
    background-color: #A0AEC0;
}
"""
