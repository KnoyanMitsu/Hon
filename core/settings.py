import json
import os
from pathlib import Path

from gi.repository import GLib


def _settings_path():
    directory = Path(GLib.get_user_config_dir()) / "hon"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "settings.json"


def load_settings():
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings):
    path = _settings_path()
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)


def get_setting(name, default=None):
    return load_settings().get(name, default)


def set_setting(name, value):
    settings = load_settings()
    settings[name] = value
    save_settings(settings)