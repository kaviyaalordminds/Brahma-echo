import json, os, platform
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "api_keys.json"

def get_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _detected_os() -> str:
    """The OS Brahma Echo is actually running on right now."""
    system = platform.system().lower()
    if system == "darwin":
        return "mac"
    if system == "windows":
        return "windows"
    return "linux"

def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'

    Defaults to the real, detected OS (via `platform.system()`), not a value
    read from disk. A stored 'os_system' in config/api_keys.json is honored
    only when it names one of the three supported values explicitly - so a
    config file that's missing the field, stale, or copied from another
    machine can never silently force Windows-only behavior on a real Mac or
    Linux install.
    """
    try:
        stored = str(get_config().get("os_system", "")).strip().lower()
    except Exception:
        stored = ""
    if stored in ("windows", "mac", "linux"):
        return stored
    return _detected_os()

def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"