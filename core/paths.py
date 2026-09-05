# core/paths.py
import os
from gi.repository import GLib


def get_db_path():
    data_dir = os.path.join(GLib.get_user_data_dir(), "hon")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "library.db")