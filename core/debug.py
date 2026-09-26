import os

def is_debug_enabled() -> bool:
    """True hanya jika env DEBUG_ENABLE=1."""
    return os.environ.get("DEBUG_ENABLE") == "1"

def debug_print(*args, **kwargs):
    """Print hanya jika DEBUG_ENABLE=1. Wrapper drop-in untuk print()."""
    if is_debug_enabled():
        print(*args, **kwargs)
