"""Cross-platform user data / cache / log / install directories.

V0.7 multi-user architecture: SecondBrain Desktop can be installed in
two modes, and the path resolution differs slightly between them.

* **System-wide install** (recommended for RDP / shared machines) —
  the engine + binaries land under ``%ProgramFiles%\\SecondBrain\\``
  and are read-only for non-admin users. Every user on the host
  shares the same binary. The per-user mutable state still lives in
  the user's roaming / local profile so each session stays isolated.
* **Per-user install** (single-user laptops) — engine + binaries land
  under ``%LOCALAPPDATA%\\SecondBrain\\``. Only that user sees the
  install.

Per-user state, in BOTH modes:

* **Settings** (autostart, language override, notification level,
  MCP target selection) → ``%APPDATA%\\SecondBrain\\settings.json``.
  Roaming on managed setups so the user's tray preferences follow
  them across RDP sessions / machines.
* **Cache** (update-check, last engine probe) →
  ``%LOCALAPPDATA%\\SecondBrain\\cache\\``. Non-roaming — purely
  local optimization.
* **Logs** → ``%LOCALAPPDATA%\\SecondBrain\\logs\\sb-desktop.log``.
  Non-roaming. One file per user; users on the same machine never
  fight for the log handle.
* **Kit config** (vault path, language, kit_repo) →
  ``~\\.memory-kit\\config.json``. Read by the engine. Each user
  has their own — engine processes spawned by different users
  consume different configs without any coordination.
* **Vault** → user-pickable, defaults to ``~\\Documents\\SecondBrain``.
  Always per-user (even on RDP).

Resolution rules per platform mirror the OS convention:

* Windows: ``%LOCALAPPDATA%`` for non-roaming, ``%APPDATA%`` for
  roaming, ``%ProgramFiles%`` for system installs.
* macOS: ``~/Library/Application Support`` (roaming-equivalent),
  ``~/Library/Caches`` (non-roaming), ``/Applications`` for system
  installs.
* Linux: XDG-compliant.

The Memory Kit config lives at ``~/.memory-kit/config.json``
regardless of platform — that path is owned by the kit.
"""

from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path

APP_NAME = "SecondBrain"


class InstallMode(str, Enum):
    """Where the SecondBrain Desktop binaries actually live."""

    SYSTEM = "system"   # installed under Program Files (admin)
    USER = "user"       # installed under LOCALAPPDATA (current user)
    DEV = "dev"         # running from a source checkout (no install)


# ---------------------------------------------------------------------------
# Per-user roots (settings / cache / logs)
# ---------------------------------------------------------------------------


def _windows_local_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / "AppData" / "Local" / APP_NAME


def _windows_roaming_root() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / "AppData" / "Roaming" / APP_NAME


def _macos_support_root() -> Path:
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
    """Roaming-eligible per-user settings dir.

    Windows: ``%APPDATA%\\SecondBrain`` — roams with the user profile
    on managed setups, which is what we want for tray preferences.
    """
    if sys.platform == "win32":
        return _windows_roaming_root()
    if sys.platform == "darwin":
        return _macos_support_root()
    return _linux_data_root()


def app_cache_dir() -> Path:
    """Non-roaming throw-away cache (icon glyphs, update-check, last probe)."""
    if sys.platform == "win32":
        return _windows_local_root() / "cache"
    if sys.platform == "darwin":
        return _macos_cache_root()
    return _linux_cache_root()


def app_log_dir() -> Path:
    """Non-roaming rotating logs — one file per user."""
    if sys.platform == "win32":
        return _windows_local_root() / "logs"
    if sys.platform == "darwin":
        return _macos_log_root()
    return _linux_state_root() / "logs"


def settings_file_path() -> Path:
    return app_data_dir() / "settings.json"


def log_file_path() -> Path:
    return app_log_dir() / "sb-desktop.log"


# ---------------------------------------------------------------------------
# Install location detection (system / user / dev)
# ---------------------------------------------------------------------------


def _system_install_root_windows() -> Path:
    return Path(
        os.environ.get("ProgramFiles") or r"C:\Program Files"
    ) / APP_NAME


def _user_install_root_windows() -> Path:
    return _windows_local_root()


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def detect_install_mode(executable: Path | None = None) -> InstallMode:
    """Determine where the current Tray executable lives.

    ``sys.executable`` for a PyInstaller bundle points at
    ``{install_root}/app/SecondBrainTray.exe``. We compare it against
    the known system / user install roots; anything else is dev.
    """
    exe = (executable or Path(sys.executable)).resolve()
    parent_app = exe.parent
    install_root_dir = parent_app.parent if parent_app.name.lower() == "app" else parent_app

    if sys.platform == "win32":
        sys_root = _system_install_root_windows().resolve()
        user_root = _user_install_root_windows().resolve()
        if _is_under(install_root_dir, sys_root):
            return InstallMode.SYSTEM
        if _is_under(install_root_dir, user_root):
            return InstallMode.USER
        return InstallMode.DEV

    if sys.platform == "darwin":
        if str(install_root_dir).startswith("/Applications"):
            return InstallMode.SYSTEM
        if str(install_root_dir).startswith(str(Path.home())):
            return InstallMode.USER
        return InstallMode.DEV

    install_str = str(install_root_dir)
    if install_str.startswith(("/opt", "/usr")):
        return InstallMode.SYSTEM
    if install_str.startswith(str(Path.home())):
        return InstallMode.USER
    return InstallMode.DEV


def install_root() -> Path:
    """Return the on-disk install root of the running Tray executable."""
    exe = Path(sys.executable).resolve()
    if exe.parent.name.lower() == "app":
        return exe.parent.parent
    return exe.parent


# ---------------------------------------------------------------------------
# Engine probes — used by status + kit_installer for binary discovery.
# ---------------------------------------------------------------------------


def system_engine_scripts_dir() -> Path:
    """The engine Scripts dir for a system install — read-only for users."""
    if sys.platform == "win32":
        return _system_install_root_windows() / "engine" / "Scripts"
    if sys.platform == "darwin":
        return Path("/Applications") / APP_NAME / "engine" / "Scripts"
    return Path("/opt") / APP_NAME.lower() / "engine" / "bin"


def user_engine_scripts_dir() -> Path:
    """The engine Scripts dir for a per-user install."""
    if sys.platform == "win32":
        return _user_install_root_windows() / "engine" / "Scripts"
    if sys.platform == "darwin":
        return _macos_support_root() / "engine" / "Scripts"
    return _linux_data_root() / "engine" / "bin"


def memory_kit_config_path() -> Path:
    """Canonical Memory Kit config — owned by the kit, per-user, read-only for us."""
    return Path.home() / ".memory-kit" / "config.json"
