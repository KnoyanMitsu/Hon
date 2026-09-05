import hashlib
import os
from pathlib import Path

from gi.repository import GdkPixbuf, Gtk


def thumbnail_path(path: str, width: int, height: int):
    source = Path(path).expanduser()
    stat = source.stat()
    cache_key = hashlib.sha256(
        f"{source.resolve()}:{stat.st_mtime_ns}:{stat.st_size}:{width}x{height}".encode()
    ).hexdigest()
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "hon" / "thumbnails"
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root / f"{cache_key}.png"


def load_thumbnail(path: str, width: int, height: int):
    cached_path = thumbnail_path(path, width, height)

    if not cached_path.exists():
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            path,
            width,
            height,
            True,
        )
        pixbuf.savev(str(cached_path), "png", [], [])

    return Gtk.Picture.new_for_filename(str(cached_path))