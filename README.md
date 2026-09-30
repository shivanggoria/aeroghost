# AeroGhost (BlueP2P)

[![Zero Telemetry](https://img.shields.io/badge/Telemetry-ZERO%20%28Air--Gapped%29-brightgreen.svg)](README.md)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg)](README.md)
[![Encryption](https://img.shields.io/badge/Encryption-AES--256--GCM-blueviolet.svg)](README.md)
[![KDF](https://img.shields.io/badge/KDF-Argon2id-orange.svg)](README.md)
[![PAKE](https://img.shields.io/badge/PAKE-SPAKE2-brightgreen.svg)](README.md)
[![Post-Quantum](https://img.shields.io/badge/Key%20Agreement-X25519%20%2B%20ML--KEM--768-8A2BE2.svg)](README.md)
[![Messaging](https://img.shields.io/badge/Messaging-Double%20Ratchet%20%2B%20Sender%20Keys-9cf.svg)](README.md)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/CI-GitHub%20Actions-success.svg)](.github/workflows/build-release.yml)

**AeroGhost** is a 100% offline, zero-telemetry, peer-to-peer (P2P) secure group chat and chunked file transfer application for Windows over local **Bluetooth (RFCOMM/WinRT)** and isolated loopback mesh.

Built with absolute internet isolation: **no WAN sockets, no remote servers, no telemetry, no tracking, and zero cloud dependencies**.

---

## Key Highlights

- **Authenticated Encryption:** All traffic is encrypted with **AES-256-GCM** using unique per-message keys and fresh 96-bit nonces.
- **Password-Authenticated Key Exchange (PAKE):** The handshake runs **SPAKE2**, so an attacker who records it gains **no offline dictionary attack** on the passphrase — each guess would require a fresh live interaction. This closes the classic weakness of passphrase-derived room keys.
- **Hybrid Post-Quantum Key Agreement:** Every connection combines **X25519** (classical) with **ML-KEM-768** (post-quantum, the NIST FIPS 203 standard) via HKDF. An attacker must break *both* — protecting against "harvest now, decrypt later" quantum attacks.
- **Double Ratchet (Per-Message Keys):** Each 1:1 link runs a Signal-style **Double Ratchet**, giving forward secrecy *and* post-compromise security ("self-healing"): a one-time state leak does not expose earlier or later messages.
- **End-to-End Group Encryption (Sender Keys):** Group messages use per-member **signed sender keys**. The relay host forwards opaque ciphertext it cannot forge, and sender keys are **automatically rotated on every join/leave** so a departed member is cut off from future traffic.
- **Argon2id Vault:** Locally stored message history is encrypted with a **memory-hard Argon2id** key (64 MiB), resisting GPU/ASIC cracking of a stolen vault.
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
pyinstaller --onefile --windowed --name AeroGhost --clean --collect-all argon2 --collect-all spake2 main.py
```
The resulting `dist/AeroGhost.exe` is completely self-contained. (The `--collect-all` flags bundle the Argon2 and SPAKE2 crypto libraries; ML-KEM ships inside `cryptography`.)

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
Includes 40+ automated unit, integration, protocol, crash-traversal, and cryptographic tests (PAKE, hybrid key agreement, Double Ratchet, sender keys, group relay). On a headless machine (or CI) run with the offscreen Qt backend:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v
```

---

## Cryptographic Stack

| Layer | Primitive |
| :--- | :--- |
| Passphrase authentication | **SPAKE2** (PAKE — no offline dictionary attack) |
| Key agreement | **X25519 + ML-KEM-768** hybrid, combined via HKDF-SHA256 |
| 1:1 messaging | **Double Ratchet** (per-message keys, forward secrecy + post-compromise security) |
| Group messaging | **Signed sender keys**, rotated on every membership change |
| Bulk encryption | **AES-256-GCM** |
| Message signing | **Ed25519** |
| Vault at rest | **Argon2id** (memory-hard, 64 MiB) |

## Security Model & Limitations

AeroGhost implements modern, standards-based cryptography, but it has **not** been independently audited and should not be relied on where lives depend on it. Honest caveats:

- **The host is a room participant.** In a group (3+), the coordinator is itself a member and reads group messages as a member. Sender keys ensure the *relay function* never needs plaintext and cannot forge messages, and that an outside relay could not read — but the participating host is not a blind relay.
- **Active-attacker MITM within a known password.** SPAKE2 authenticates the handshake with the passphrase, so outsiders cannot MITM. A malicious *member* who already holds the passphrase could, however, attempt to substitute keys during group key distribution. Defenses hold fully against anyone who does not know the passphrase.
- **Metadata over the radio.** Bluetooth RFCOMM still exposes device MAC addresses and traffic timing/volume to a physical sniffer, even though payloads are unreadable.
- **The released binary is unsigned** (see the Download note above), and vault history is reset when the key-derivation scheme changes between versions.

## License
Open source and privacy-preserving. Distributed under the MIT License.
