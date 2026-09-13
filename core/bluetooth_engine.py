"""
Bluetooth RFCOMM & Transport Engine for AeroGhost
Native Windows Winsock RFCOMM socket support with dual-mode hardware Bluetooth and local test mesh.
"""

import socket
import threading
import subprocess
import re
import time
from typing import Dict, List, Optional, Callable, Tuple, Any
from core.protocol import Protocol

# Windows Winsock Bluetooth Constants
AF_BTH = 32
BTPROTO_RFCOMM = 3


class PeerConnection:
    """Represents an active point-to-point stream connection with a peer."""

    def __init__(self, sock: socket.socket, addr: Any, on_frame: Callable[['PeerConnection', bytes], None], on_close: Callable[['PeerConnection'], None]):
        self.sock = sock
        self.addr = addr
        self.on_frame = on_frame
        self.on_close = on_close
        self.peer_id: Optional[str] = None
        self.nickname: str = "Unknown Peer"
        self.is_authenticated: bool = False
        self.is_alive = True
        self._buffer = bytearray()
        self._lock = threading.Lock()

        # Start receiving thread
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def send_frame(self, encrypted_bytes: bytes) -> bool:
        """Prefaces frame with 4-byte header and sends over the socket."""
        if not self.is_alive:
            return False
        try:
            framed = Protocol.frame_packet(encrypted_bytes)
            with self._lock:
                self.sock.sendall(framed)
            return True
        except Exception:
            self.close()
            return False

    def _read_loop(self):
        """Continuously reads incoming bytes, extracts framed packets, and invokes callback."""
        try:
            self.sock.settimeout(0.5)
        except Exception:
            pass

        while self.is_alive:
            try:
                data = self.sock.recv(65536)
                if not data:
                    break
                self._buffer.extend(data)
                frames, self._buffer = Protocol.extract_frames(self._buffer)
                for frame in frames:
                    self.on_frame(self, frame)
            except socket.timeout:
                continue
            except Exception:
                break
        self.close()

    def close(self):
        """Closes the socket and notifies manager."""
        if self.is_alive:
            self.is_alive = False
            try:
                self.sock.close()
            except Exception:
                pass
            self.on_close(self)


class BluetoothEngine:
    """
    Manages Bluetooth RFCOMM listener and outgoing connections.
    Supports native Windows AF_BTH and isolated loopback test mode.
    """

    DEFAULT_RFCOMM_PORT = 4
    DEFAULT_TEST_PORT = 19840

    def __init__(self, is_bluetooth_mode: bool = True):
        self.is_bluetooth_mode = is_bluetooth_mode
        self.local_mac: str = "00:00:00:00:00:00"
        self.listener_port: int = self.DEFAULT_RFCOMM_PORT if is_bluetooth_mode else self.DEFAULT_TEST_PORT
        self.server_sock: Optional[socket.socket] = None
        self.is_listening = False
        self.peers: Dict[str, PeerConnection] = {}  # peer_id -> PeerConnection
        self._lock = threading.RLock()

        # Callbacks
        self.on_peer_authenticated: Optional[Callable[[PeerConnection], None]] = None
        self.on_peer_disconnected: Optional[Callable[[PeerConnection], None]] = None
        self.on_frame_received: Optional[Callable[[PeerConnection, bytes], None]] = None

        if self.is_bluetooth_mode:
            self.local_mac = self._detect_local_bluetooth_mac()

    def _detect_local_bluetooth_mac(self) -> str:
        """Detects machine's native Bluetooth radio MAC address."""
        try:
            s = socket.socket(AF_BTH, socket.SOCK_STREAM, BTPROTO_RFCOMM)
            s.bind(("00:00:00:00:00:00", 0))
            mac, _ = s.getsockname()
            s.close()
            return mac
        except Exception:
            return "00:00:00:00:00:00"

    @staticmethod
    def scan_windows_bluetooth_devices() -> List[Dict[str, str]]:
        """
        Scans for paired and nearby Bluetooth devices using Windows PnP inventory.
        Zero internet or remote call—reads directly from Windows hardware subsystem.
        """
        devices = []
        seen_macs = set()
        try:
            cmd = 'powershell -NoProfile -Command "Get-PnpDevice -Class Bluetooth | Select-Object FriendlyName, InstanceId | ConvertTo-Json"'
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            if proc.returncode == 0 and proc.stdout.strip():
                import json
                data = json.loads(proc.stdout)
                if isinstance(data, dict):
                    data = [data]
                NON_PEER_KEYWORDS = [
                    "airpod", "headphone", "headset", "earbud", "earphone", 
                    "speaker", "keyboard", "mouse", "controller", "watch", 
                    "avrcp", "audio", "stone 350", "h.ear"
                ]
                for item in data:
                    name = item.get("FriendlyName", "").strip()
                    instance = item.get("InstanceId", "")
                    # Extract MAC if present in instance ID (BTHENUM\{...}_LOCALMFG&... or DEV_...)
                    mac_match = re.search(r"DEV_([0-9A-Fa-f]{12})", instance)
                    if mac_match:
                        raw = mac_match.group(1)
                        mac = ":".join(raw[i:i+2] for i in range(0, 12, 2)).upper()
                        name_lower = name.lower()
                        is_peripheral = any(k in name_lower for k in NON_PEER_KEYWORDS)
                        if mac not in seen_macs and name and "Bluetooth" not in name and "Adapter" not in name and not is_peripheral:
                            seen_macs.add(mac)
                            devices.append({"name": name, "mac": mac, "instance_id": instance})
        except Exception:
            pass
        return devices

    def start_listener(self, port: Optional[int] = None) -> bool:
        """Starts listening for incoming peer connections."""
        if port is not None:
            self.listener_port = port

        try:
            if self.is_bluetooth_mode:
                self.server_sock = socket.socket(AF_BTH, socket.SOCK_STREAM, BTPROTO_RFCOMM)
                self.server_sock.bind(("00:00:00:00:00:00", self.listener_port))
            else:
                self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.server_sock.bind(("127.0.0.1", self.listener_port))

            self.server_sock.listen(10)
            try:
                self.server_sock.settimeout(0.5)
            except Exception:
                pass
            self.is_listening = True

            accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
            accept_thread.start()
            return True
        except Exception as e:
            self.is_listening = False
            return False

    def _accept_loop(self):
        """Accepts incoming socket connections and wraps them into PeerConnection."""
        while self.is_listening and self.server_sock:
            try:
                client_sock, client_addr = self.server_sock.accept()
                peer_conn = PeerConnection(
                    sock=client_sock,
                    addr=client_addr,
                    on_frame=self._handle_frame,
                    on_close=self._handle_peer_close
                )
            except socket.timeout:
                continue
            except Exception:
                break

    def connect_to_peer(self, target_address: str, port: Optional[int] = None) -> Optional[PeerConnection]:
        """Initiates an outgoing connection to a peer address."""
        conn_port = port if port is not None else self.listener_port
        try:
            if self.is_bluetooth_mode:
                client_sock = socket.socket(AF_BTH, socket.SOCK_STREAM, BTPROTO_RFCOMM)
                client_sock.settimeout(5.0)
                client_sock.connect((target_address, conn_port))
            else:
                client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_sock.settimeout(3.0)
                client_sock.connect((target_address or "127.0.0.1", conn_port))

            # Reset timeout for the reader loop
            client_sock.settimeout(None)

            peer_conn = PeerConnection(
                sock=client_sock,
                addr=(target_address, conn_port),
                on_frame=self._handle_frame,
                on_close=self._handle_peer_close
            )
            return peer_conn
        except Exception:
            return None

    def _handle_frame(self, peer_conn: PeerConnection, encrypted_frame: bytes):
        if self.on_frame_received:
            self.on_frame_received(peer_conn, encrypted_frame)

    def _handle_peer_close(self, peer_conn: PeerConnection):
        with self._lock:
            if peer_conn.peer_id and peer_conn.peer_id in self.peers:
                del self.peers[peer_conn.peer_id]
        if self.on_peer_disconnected:
            self.on_peer_disconnected(peer_conn)

    def register_authenticated_peer(self, peer_conn: PeerConnection):
        """Registers peer in active peer dictionary after authentication succeeds."""
        with self._lock:
            self.peers[peer_conn.peer_id] = peer_conn
        if self.on_peer_authenticated:
            self.on_peer_authenticated(peer_conn)

    def broadcast_frame(self, encrypted_frame: bytes, exclude_peer_id: Optional[str] = None):
        """Broadcasts an encrypted frame to all authenticated peers."""
        with self._lock:
            target_peers = list(self.peers.values())
        for peer in target_peers:
            if exclude_peer_id and peer.peer_id == exclude_peer_id:
                continue
            peer.send_frame(encrypted_frame)

    def stop(self):
        """Stops listener and terminates all peer connections."""
        self.is_listening = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None

        with self._lock:
            active_peers = list(self.peers.values())
            self.peers.clear()

        for peer in active_peers:
            peer.close()
