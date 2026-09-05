import os
import sqlite3
import threading
from gi.repository import GLib


def get_db_path():
    """Satu-satunya tempat yang tau lokasi database. Ganti di sini aja kalau perlu."""
    data_dir = os.path.join(GLib.get_user_data_dir(), "hon")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "library.db")


class Connection:
    """Singleton — cuma ada 1 instance koneksi DB, dipakai bareng di seluruh app."""

    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._setup()
        return cls._instance

    def _setup(self):
        db_path = get_db_path()

        # cek SEBELUM connect, karena sqlite3.connect() otomatis BIKIN file baru
        # kalau belum ada -- jadi ini nentuin apakah ini "first run" atau bukan
        self.is_first_run = not os.path.exists(db_path)

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.query_lock = threading.Lock()

    def get(self):
        return self.conn