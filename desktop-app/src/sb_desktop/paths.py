"""Cross-platform user data / cache / log directories.

Resolution rules per platform (no external ``platformdirs`` dependency to
keep the PyInstaller bundle lean):

* Windows: ``%LOCALAPPDATA%/SecondBrain/{data,logs,cache}``
* macOS:   ``~/Library/Application Support/SecondBrain``,
           ``~/Library/Logs/SecondBrain``,
           ``~/Library/Caches/SecondBrain``
* Linux:   XDG-compliant — ``$XDG_DATA_HOME``, ``$XDG_STATE_HOME``,
           ``$XDG_CACHE_HOME`` with the documented fallbacks.

The Memory Kit config lives at ``~/.memory-kit/config.json`` regardless of
platform — that path is owned by the kit and intentionally not duplicated.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "SecondBrain"


def _windows_data_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / "AppData" / "Local" / APP_NAME


def _macos_data_root() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_NAME


def _macos_log_root() -> Path:
    return Path.home() / "Library" / "Logs" / APP_NAME


def _macos_cache_root() -> Path:
    return Path.home() / "Library" / "Caches" / APP_NAME


def _xdg(env: str, default: Path) -> Path:
    raw = os.environ.get(env)
    if raw:
        return Path(raw).expanduser()
    return default


def _linux_data_root() -> Path:
    return _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP_NAME


def _linux_state_root() -> Path:
    return _xdg("XDG_STATE_HOME", Path.home() / ".local" / "state") / APP_NAME


def _linux_cache_root() -> Path:
    return _xdg("XDG_CACHE_HOME", Path.home() / ".cache") / APP_NAME


def app_data_dir() -> Path:
    """Persistent settings (autostart flag, language override, last-known state)."""
    if sys.platform == "win32":
        return _windows_data_root() / "data"
    if sys.platform == "darwin":
        return _macos_data_root()
    return _linux_data_root()


def app_log_dir() -> Path:
    """Rotating log files."""
    if sys.platform == "win32":
        return _windows_data_root() / "logs"
    if sys.platform == "darwin":
        return _macos_log_root()
    return _linux_state_root() / "logs"


def app_cache_dir() -> Path:
    """Throw-away cache (icon glyphs, last MCP probe transcript, etc.)."""
    if sys.platform == "win32":
        return _windows_data_root() / "cache"
    if sys.platform == "darwin":
        return _macos_cache_root()
    return _linux_cache_root()


def memory_kit_config_path() -> Path:
    """Canonical Memory Kit config — owned by the kit, read-only for us."""
    return Path.home() / ".memory-kit" / "config.json"


def log_file_path() -> Path:
    return app_log_dir() / "sb-desktop.log"


def settings_file_path() -> Path:
    return app_data_dir() / "settings.json"
