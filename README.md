# AeroGhost (BlueP2P)

[![Zero Telemetry](https://img.shields.io/badge/Telemetry-ZERO%20%28Air--Gapped%29-brightgreen.svg)](README.md)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg)](README.md)
[![Encryption](https://img.shields.io/badge/Encryption-AES--256--GCM-blueviolet.svg)](README.md)
[![Key Derivation](https://img.shields.io/badge/KDF-PBKDF2--HMAC--SHA256-orange.svg)](README.md)
[![Forward Secrecy](https://img.shields.io/badge/Forward%20Secrecy-X25519%20%2B%20HKDF-9cf.svg)](README.md)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/CI-GitHub%20Actions-success.svg)](.github/workflows/build-release.yml)

**AeroGhost** is a 100% offline, zero-telemetry, peer-to-peer (P2P) secure group chat and chunked file transfer application for Windows over local **Bluetooth (RFCOMM/WinRT)** and isolated loopback mesh.

Built with absolute internet isolation: **no WAN sockets, no remote servers, no telemetry, no tracking, and zero cloud dependencies**.

---

## Key Highlights

- **Untrusted Air-Interface (End-to-End Encrypted):** All messages, file chunks, and peer metadata are encrypted on-the-fly using **AES-256-GCM** with unique 96-bit initialization vectors per packet.
- **Cryptographic Room Isolation:** Keys are derived from your room passphrase using **PBKDF2-HMAC-SHA256** (600,000 rounds, per OWASP guidance). Even if nearby Bluetooth sniffers intercept the raw radio packets, they cannot decrypt messages, view files, or know what room is being used.
- **Mutual Challenge-Response Authentication:** Unauthorized devices or rogue sniffers attempting to connect to your Bluetooth port are rejected and dropped immediately during the cryptographic handshake.
- **Per-Session Forward Secrecy:** Every connection performs an **ephemeral X25519 Diffie-Hellman** exchange (authenticated inside the room-key-encrypted handshake) and derives a one-time session key via **HKDF-SHA256**. All chat and file traffic is then encrypted under that session key — never the long-lived passphrase key. If the passphrase is ever compromised, previously recorded sessions still cannot be decrypted, because the ephemeral private keys were discarded.
- **Star-Relay Group Rooms:** Form encrypted group rooms (one host plus connected clients) where the host relays each message to the other members, with automatic deduplication.
- **P2P Chunked File Transfers:** Send documents, images, and files over Bluetooth in 32 KB chunks with **SHA-256 integrity verification** and real-time progress bars.
- **Crash-Proof Fault Tolerant Architecture:** Resilient reconnection loops with friendly in-app guidance—no crashes if peers are temporarily out of range or host has not started yet.
- **Modern Segmented Button UI:** High-contrast, tactile segmented button controls for role and transport selection.
- **Session Memory (Trust-on-First-Use):** Automatically remembers returning peers and decrypts stored message history locally when you enter the room password.
- **Stealth Mode ("Ghost / Document Mode"):**
  - Toggle with **`Ctrl + Shift + S`**; exit with **`Esc`**.
  - Snaps into an ultra-compact floating widget positioned at the screen edge.
  - Transforms into an inconspicuous plain white document/scratchpad disguise without speech bubbles or avatars.
  - Transparent opacity slider so it blends seamlessly into background documents.
  - **Boss Key:** **`Ctrl + Shift + H`** instantly minimizes to the Windows System Tray.

---

## Zero Telemetry & Air-Gap Verification

You can verify AeroGhost's complete offline isolation:
1. Open **Windows Defender Firewall** / **Resource Monitor** -> **Network** tab.
2. Note that AeroGhost never binds to any WAN/LAN IP sockets or resolves external DNS domains.
3. Air-gap certified: operates flawlessly on laptops with Wi-Fi and Ethernet completely disconnected.

---

## Download (No Installation Required)

For friends and colleagues who do not have Python installed:

1. Go to the [Releases](https://github.com/shivanggoria/aeroghost/releases) tab on GitHub.
2. Download **`AeroGhost.exe`** (single portable executable, ~49 MB).
3. Double-click to run directly from your desktop or a USB drive—no setup, installer, or Python needed!

> **Note:** the executable is **not code-signed**, so Windows SmartScreen/Defender may show a "Windows protected your PC" warning on first run. Choose **More info → Run anyway** if you trust the source, or run from source (below) instead.

---

## Getting Started from Source

### Prerequisites
- Windows 10 or 11 with Bluetooth enabled
- Python 3.10+ (if running from source)

### Installation
```bash
git clone https://github.com/shivanggoria/aeroghost.git
cd aeroghost
pip install -r requirements.txt
```

### Running the App
```bash
python main.py
```

### 1-Click Instant Test on a Single PC
Want to test immediately without a second PC?
1. Run `python main.py`.
2. Click the top button:
   > **`Launch Instant 2-Window Test (Side-by-Side)`**
3. AeroGhost will automatically launch both **Host** and **Client** windows side-by-side, pre-connected and encrypted!

### Testing over Real Bluetooth Between 2 PCs
1. Turn Bluetooth **ON** on both PCs.
2. **PC 1 (Host):** Select `Create Room (Host)` and `Bluetooth RFCOMM (2 PCs)`. Click `Launch Room`. Note your Bluetooth MAC in the sidebar.
3. **PC 2 (Client):** Select `Join Room (Connect)` and `Bluetooth RFCOMM (2 PCs)`. Click `Scan Nearby Devices` (or paste PC 1's MAC address). Click `Connect to Room`.

---

## Packaging Your Own Portable `.exe`

To compile a standalone `.exe` using PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name AeroGhost --clean main.py
```
The resulting `dist/AeroGhost.exe` is completely self-contained.

An automated GitHub Actions workflow (`.github/workflows/build-release.yml`) also compiles and publishes ready-to-run releases automatically whenever you push a version tag (e.g. `git tag v1.0.0 && git push origin v1.0.0`).

---

## Hotkeys & Shortcuts

| Shortcut | Function |
| :--- | :--- |
| **`Ctrl + Shift + S`** | Toggle Stealth Mode (Snap to side & document scratchpad disguise) |
| **`Ctrl + Shift + H`** | Boss Key / Panic (Instantly minimize to System Tray) |
| **`Esc`** | Exit Stealth Mode |
| **`Enter`** | Send chat message |

---

## Running the Test Suite

```bash
python -m pytest tests/ -v
```
Includes 30+ automated unit, integration, protocol, crash-traversal, and security-regression tests. On a headless machine (or CI) run with the offscreen Qt backend:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v
```

---

## Security Model & Limitations

AeroGhost aims to keep casual, offline conversations private from nearby radio sniffers. It is **not** a substitute for a professionally audited secure-messaging protocol. Be aware of the following:

- **Room entry rests on the passphrase.** The room key (derived offline from room name + passphrase) gates who can join and authenticates the session handshake. Its per-room salt is deterministic (it only separates rooms; it is not the random per-secret salt a stored-password database would use), so brute-force resistance comes from the 600,000-round PBKDF2 stretch **and** from choosing a strong passphrase. Rooms created in the app now require at least 8 characters.
- **Forward secrecy against outsiders.** Traffic is encrypted under per-session keys from an ephemeral X25519 exchange (see Highlights), so cracking the passphrase *after* recording a session does not decrypt it. Caveat: the ephemeral keys are authenticated with the shared room key, so a malicious *room member* who already holds the passphrase could in principle MITM a fresh handshake — forward secrecy holds fully only against parties who never learn the passphrase.
- **Group topology is host-relay.** Rooms are one host plus connected clients, with the host relaying chat between peers; it is not a full peer-to-peer mesh.
- **The released binary is unsigned** (see the Download note above).

## License
Open source and privacy-preserving. Distributed under the MIT License.
