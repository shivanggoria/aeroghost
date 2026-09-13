# GEMINI.md - Bluetooth P2P Secure Chat & File Transfer (Windows)

## 1. Project Overview & Mission
**Bluetooth P2P Secure Chat** (working codename: **AeroGhost** / **BlueP2P**) is a fully offline, zero-telemetry, peer-to-peer Windows desktop application designed for secure group messaging and direct file transfers over local Bluetooth (RFCOMM/WinRT).

The application operates with **absolute internet isolation**—no network sockets connecting to WAN/LAN, no external telemetry, no remote servers, and zero cloud dependencies. It is purpose-built to be hosted as an open-source project on GitHub with portable, single-click executable releases that any friend or colleague can download and use instantly without complex setup.

---

## 2. Core Security & Privacy Principles
1. **Zero Internet Footprint:**
   - The application does not bind to any TCP/UDP IP sockets or make any HTTP/HTTPS web requests.
   - Works in Air-Gapped and offline environments.
2. **Untrusted Air-Interface (End-to-End Encryption - E2EE):**
   - Bluetooth RFCOMM channels are considered public and sniffable.
   - All communications (chat messages, group management packets, file blocks, metadata) are encrypted end-to-end using **AES-256-GCM** or **XChaCha20-Poly1305**.
   - Keys are derived via **Argon2id** or **PBKDF2-HMAC-SHA256** from the shared room passphrase + room salt.
3. **Cryptographic Room Isolation:**
   - Unauthenticated eavesdroppers or nearby Bluetooth devices cannot read messages, decrypt file transfers, or inspect chat members.
   - Room Service UUID / Handshake Beacon is cryptographically hashed from the room key so outsiders cannot identify chat activity.
4. **Trust-on-First-Use (TOFU) & Reconnection Memory:**
   - Once a room and its participants are established, peer public keys/device fingerprints are saved locally in an encrypted store.
   - When devices come back in Bluetooth range, they automatically authenticate each other and reconnect seamlessly.
5. **Encrypted Local Storage:**
   - Chat history and pending transfer metadata are stored locally in an encrypted database/file protected by the room key or a master user PIN.

---

## 3. Feature Breakdown

### 3.1 P2P Bluetooth Connectivity
- Uses Windows Native WinRT Bluetooth RFCOMM Sockets (`Windows.Devices.Bluetooth.Rfcomm` and `Windows.Networking.Sockets.StreamSocket`).
- Custom RFCOMM Service definition with dynamic SDP (Service Discovery Protocol) records.
- Peer discovery: Background scanning for nearby active peers advertising the matching room signature.
- Fast auto-pairing / auto-connecting without requiring manual Windows Settings Bluetooth pairing for standard RFCOMM sockets where supported.

### 3.2 Multi-User Group Chat Topology
- **Multi-Peer Topology:**
  - Hybrid Mesh / Star-Relay: One peer acts as the room coordinator/initiator, while all peers establish direct or relayed RFCOMM channels.
  - Broadcast routing: A message sent by one user is encrypted with the group key and relayed across connected peers with message IDs to avoid loops.
  - Member status presence: Real-time discovery of who is within Bluetooth signal range (online/offline indicator, signal strength indicator).

### 3.3 Password Protection & Group Persistence
- **One-Time Room Setup:**
  - Create Room: Enter Room Name + Strong Password.
  - Join Room: Enter Room Name + Password.
- **Mutual Authentication:**
  - Zero-Knowledge or Challenge-Response handshake upon connection using the password-derived key.
  - Unauthorized devices attempting to connect to the Bluetooth RFCOMM port are dropped immediately if the cryptographic handshake fails.
- **Chat History & Reconnection:**
  - Chat history saved locally (tamper-proof, encrypted).
  - Automatically recognizes returning devices when in physical proximity without re-prompting for password on every reconnect.

### 3.4 P2P File Transfer
- Direct chunked file streaming over dedicated or multiplexed RFCOMM sockets.
- File integrity verification via **SHA-256** checksum.
- Chunk size optimization (16 KB - 64 KB chunks) tailored for Bluetooth throughput.
- In-chat progress bar, estimated time, pause/resume, and safe drag-and-drop.
- Secure destination folder isolation (no auto-executing scripts; safe download sandbox).

### 3.5 Minimalist UI & "Stealth Mode" (Boss Key)
- **Normal View:**
  - Clean, minimalist aesthetic (modern dark or sleek neutral theme, crisp typography).
  - Sidebar with active Bluetooth peers & signal quality.
  - Simple chat stream with timestamp, peer nickname, message status (sent/delivered), and inline file preview/download buttons.
- **Stealth Mode (Ghost / Document Mode):**
  - **Quick Trigger:** Keyboard shortcut (e.g., `Ctrl + Shift + S` or double-tap `Esc`) or a subtle toggle button.
  - **Window Transformation:**
    - Snaps into an ultra-compact, borderless or minimal floating window positioned at the screen edge/corner.
    - Neutral plain white background (looks like a minimalist Notepad, sticky note, or blank document from afar).
    - Tiny muted typography without message bubbles or avatar icons.
    - Bystanders from 2-3 feet away cannot recognize it as a messaging app.
  - **Opacity Slider:** Optional transparency adjustment (making the window semi-transparent against background apps).
  - **Panic/Boss Key:** Instant minimize to Windows System Tray (`Ctrl + Shift + H`).

---

## 4. Architectural Stack Options

### Option A: Native C# .NET 8 / 9 (WPF or WinUI 3) [Recommended]
- **Why:** First-class native integration with Windows 10/11 `Windows.Devices.Bluetooth.Rfcomm` and `StreamSocket` without buggy 3rd party wrappers.
- **Delivery:** Compiles to a **single self-contained portable `.exe`** (~25-35MB trimmed) with zero prerequisites. Friends can simply double-click and run directly from a USB or GitHub release download.
- **Performance:** Instant startup, minimal RAM footprint (<40MB), hardware-accelerated rendering, flawless window manipulation for Stealth Mode and system tray docking.

### Option B: Tauri v2 (Rust Backend + Lightweight Web Frontend)
- **Why:** Beautiful HTML/CSS frontend flexibility for custom stealth styling with high-performance Rust backend.
- **Considerations:** Windows Bluetooth RFCOMM bindings in Rust require interfacing with the Windows WinRT C++ crate (`windows-rs`). Slightly more complex to maintain than native C#.

### Option C: Python (PyQt6 / PySide6)
- **Why:** Fast prototyping.
- **Considerations:** Severe limitations with Windows Bluetooth RFCOMM libraries in modern Python (PyBluez is unmaintained and broken on Windows 11; bleak only supports BLE GATT which has low bandwidth unsuitable for files). Standalone packaging via PyInstaller produces bulky executables frequently hit by false-positive antivirus flags.

---

## 5. Repository & GitHub Distribution Plan
- **Pre-configured `.gitignore`:** Excludes all build artifacts, local databases, peer caches, test keys, and logs.
- **Automated GitHub Actions CI:** Builds a standalone release `.exe` upon git tagging, attaching the ready-to-run binary to GitHub Releases.
- **README & Security Audit Guide:** Step-by-step instructions verifying zero telemetry and instructions for offline air-gapped deployment.

---

## 6. Implementation Stages
1. **Bluetooth RFCOMM Core:** WinRT service advertiser, scanner, listener, and peer connection manager.
2. **Cryptographic Engine:** Key derivation, handshake protocol, packet encryption/decryption, and local database encryption.
3. **P2P Messaging & File Transfer Protocol:** Frame encoding/decoding, packet multiplexing, chunked file transfer, and SHA-256 verification.
4. **UI Design & Stealth Mode:** Clean minimal interface, theme engine, stealth mode hotkeys, floating widget, and system tray integration.
5. **Testing & Hardening:** Multi-device verification, reconnection stress tests, file transfer integrity tests, and GitHub release packaging.
