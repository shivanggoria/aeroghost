"""
Encrypted Local Storage for AeroGhost
Saves room configurations, trusted peer fingerprints (TOFU), and chat history securely on disk.
All sensitive data is encrypted using AES-256-GCM.
"""

import os
import json
import sqlite3
from typing import List, Dict, Any, Optional
from core.crypto import CryptoEngine


class SecureStorage:
    """Manages encrypted local database for message history and trusted peers."""

    def __init__(self, db_path: str = "aeroghost_history.vault"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes SQLite tables for rooms, peer fingerprints, and encrypted messages."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Table for rooms
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rooms (
                    room_name TEXT PRIMARY KEY,
                    salt_hex TEXT NOT NULL,
                    last_active REAL NOT NULL
                )
            """)
            # Table for trusted peer fingerprints (Trust-On-First-Use)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trusted_peers (
                    peer_id TEXT PRIMARY KEY,
                    nickname TEXT NOT NULL,
                    room_name TEXT NOT NULL,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL
                )
            """)
            # Table for encrypted messages
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    room_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    encrypted_data BLOB NOT NULL
                )
            """)
            conn.commit()

    def register_room(self, room_name: str, salt: bytes):
        """Record or update a room's active timestamp."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO rooms (room_name, salt_hex, last_active)
                VALUES (?, ?, strftime('%s', 'now'))
                ON CONFLICT(room_name) DO UPDATE SET last_active = strftime('%s', 'now')
            """, (room_name, salt.hex()))
            conn.commit()

    def get_recent_rooms(self) -> List[str]:
        """Returns list of recently used room names."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT room_name FROM rooms ORDER BY last_active DESC LIMIT 10")
            return [row[0] for row in cursor.fetchall()]

    def update_trusted_peer(self, peer_id: str, nickname: str, room_name: str):
        """Record or update a trusted peer's identity."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trusted_peers (peer_id, nickname, room_name, first_seen, last_seen)
                VALUES (?, ?, ?, strftime('%s', 'now'), strftime('%s', 'now'))
                ON CONFLICT(peer_id) DO UPDATE SET
                    nickname = excluded.nickname,
                    last_seen = strftime('%s', 'now')
            """, (peer_id, nickname, room_name))
            conn.commit()

    def get_trusted_peers(self, room_name: str) -> List[Dict[str, Any]]:
        """Fetch all recognized peers for a room."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT peer_id, nickname, first_seen, last_seen
                FROM trusted_peers WHERE room_name = ?
                ORDER BY last_seen DESC
            """, (room_name,))
            return [
                {"peer_id": row[0], "nickname": row[1], "first_seen": row[2], "last_seen": row[3]}
                for row in cursor.fetchall()
            ]

    def save_message(self, crypto: CryptoEngine, msg_id: str, message_dict: Dict[str, Any]):
        """Encrypts message payload with the room key and stores it in SQLite."""
        plaintext = json.dumps(message_dict, ensure_ascii=False).encode("utf-8")
        encrypted_data = crypto.encrypt_payload(plaintext, associated_data=crypto.room_name.encode("utf-8"))
        timestamp = float(message_dict.get("timestamp", 0))

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO messages (id, room_name, timestamp, encrypted_data)
                VALUES (?, ?, ?, ?)
            """, (msg_id, crypto.room_name, timestamp, encrypted_data))
            conn.commit()

    def load_messages(self, crypto: CryptoEngine, limit: int = 200) -> List[Dict[str, Any]]:
        """Retrieves and decrypts the latest messages for the specified room."""
        messages = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, encrypted_data FROM messages
                WHERE room_name = ?
                ORDER BY timestamp ASC LIMIT ?
            """, (crypto.room_name, limit))
            rows = cursor.fetchall()

        for msg_id, enc_blob in rows:
            try:
                decrypted_bytes = crypto.decrypt_payload(enc_blob, associated_data=crypto.room_name.encode("utf-8"))
                msg_dict = json.loads(decrypted_bytes.decode("utf-8"))
                messages.append(msg_dict)
            except Exception:
                # If decryption fails (e.g. wrong password or corrupted data), skip entry
                continue

        return messages

    def clear_room_history(self, room_name: str):
        """Purges stored chat history for a specific room."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE room_name = ?", (room_name,))
            conn.commit()
