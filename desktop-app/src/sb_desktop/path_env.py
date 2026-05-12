"""PATH management — per-user (HKCU) or system-wide (HKLM).

V0.7 multi-user: the engine binary location depends on the install
mode. A system-wide install (``%ProgramFiles%\\SecondBrain``) means
the engine's ``Scripts`` directory should be on the **system** PATH
(``HKLM\\System\\CurrentControlSet\\Control\\Session Manager\\
Environment\\Path``) so every user on the machine sees it. A
per-user install (``%LOCALAPPDATA%\\SecondBrain``) means the user's
PATH (``HKCU\\Environment\\PATH``).

The system path edit requires admin privileges — without them, the
function returns False and the caller (kit_installer) falls back to
the per-user PATH for this user only. On RDP the admin runs the
installer once for everyone; per-user invocations of the wizard
never need to touch HKLM.

After any registry edit we broadcast ``WM_SETTINGCHANGE`` so new
processes (and the Explorer shell) pick up the new value without
logout.

POSIX side: same managed block as v0.6 in ``~/.bashrc`` /
``~/.zshrc``. For system installs there is no good cross-distro
equivalent of HKLM PATH; we still write the per-user rc file but
note the system path in ``/etc/profile.d`` is a separate concern.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

POSIX_MARKER_START = "# >>> SecondBrain Desktop PATH >>>"
POSIX_MARKER_END = "# <<< SecondBrain Desktop PATH <<<"


def _normalize(path: str) -> str:
    """Case-insensitive normaliser for membership checks on Windows."""
    if sys.platform == "win32":
        return os.path.normpath(path).lower().rstrip("\\")
    return os.path.normpath(path).rstrip("/")


_SYSTEM_ENV_SUBKEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def _read_user_path_windows() -> tuple[str, int]:
    """Return (current_value, value_type). Type is winreg.REG_EXPAND_SZ
    or REG_SZ — we preserve whichever the user already had."""
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ
    ) as key:
        try:
            value, value_type = winreg.QueryValueEx(key, "PATH")
        except FileNotFoundError:
            return "", winreg.REG_EXPAND_SZ
    return value or "", value_type


def _write_user_path_windows(new_value: str, value_type: int) -> None:
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, "PATH", 0, value_type, new_value)


def _read_system_path_windows() -> tuple[str, int]:
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE, _SYSTEM_ENV_SUBKEY, 0, winreg.KEY_READ
    ) as key:
        try:
            value, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return "", winreg.REG_EXPAND_SZ
    return value or "", value_type


def _write_system_path_windows(new_value: str, value_type: int) -> None:
    import winreg

    # KEY_WOW64_64KEY ensures we read the same 64-bit hive an installer
    # would write. Without admin this open raises PermissionError.
    flags = winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE, _SYSTEM_ENV_SUBKEY, 0, flags
    ) as key:
        winreg.SetValueEx(key, "Path", 0, value_type, new_value)


def is_admin_windows() -> bool:
    """Return True if the current process has admin privileges."""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _broadcast_environment_change() -> None:
    """Tell other processes (Explorer, new shells) to re-read env vars."""
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    result = ctypes.c_long()
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST,
        WM_SETTINGCHANGE,
        0,
        "Environment",
        SMTO_ABORTIFHUNG,
        5000,
        ctypes.byref(result),
    )


def add_to_user_path_windows(directory: Path) -> bool:
    """Append ``directory`` to HKCU\\Environment\\PATH if not already there.

    Returns True if the value was changed, False if it was already
    present.
    """
    directory = directory.resolve()
    target = _normalize(str(directory))
    current, value_type = _read_user_path_windows()
    parts = [p for p in current.split(";") if p]
    if any(_normalize(p) == target for p in parts):
        return False
    new_value = (current.rstrip(";") + ";" + str(directory)) if current else str(directory)
    _write_user_path_windows(new_value, value_type)
    _broadcast_environment_change()
    return True


def remove_from_user_path_windows(directory: Path) -> bool:
    directory = directory.resolve()
    target = _normalize(str(directory))
    current, value_type = _read_user_path_windows()
    parts = [p for p in current.split(";") if p]
    filtered = [p for p in parts if _normalize(p) != target]
    if len(filtered) == len(parts):
        return False
    new_value = ";".join(filtered)
    _write_user_path_windows(new_value, value_type)
    _broadcast_environment_change()
    return True


def add_to_system_path_windows(directory: Path) -> bool:
    """Append ``directory`` to the HKLM system PATH. Requires admin.

    Returns True if the value was changed, False if it was already
    present. Raises ``PermissionError`` if the current process does
    not have admin privileges — let the caller fall back to the
    per-user path.
    """
    directory = directory.resolve()
    target = _normalize(str(directory))
    current, value_type = _read_system_path_windows()
    parts = [p for p in current.split(";") if p]
    if any(_normalize(p) == target for p in parts):
        return False
    new_value = (current.rstrip(";") + ";" + str(directory)) if current else str(directory)
    _write_system_path_windows(new_value, value_type)
    _broadcast_environment_change()
    return True


def remove_from_system_path_windows(directory: Path) -> bool:
    directory = directory.resolve()
    target = _normalize(str(directory))
    current, value_type = _read_system_path_windows()
    parts = [p for p in current.split(";") if p]
    filtered = [p for p in parts if _normalize(p) != target]
    if len(filtered) == len(parts):
        return False
    new_value = ";".join(filtered)
    _write_system_path_windows(new_value, value_type)
    _broadcast_environment_change()
    return True


def _posix_rc_files() -> list[Path]:
    home = Path.home()
    return [home / ".bashrc", home / ".zshrc"]


def add_to_user_path_posix(directory: Path) -> bool:
    """Append a managed block to each present rc file."""
    directory = directory.resolve()
    block = (
        f"\n{POSIX_MARKER_START}\n"
        f'export PATH="{directory}:$PATH"\n'
        f"{POSIX_MARKER_END}\n"
    )
    changed = False
    for rc in _posix_rc_files():
        if not rc.is_file():
            continue
        try:
            current = rc.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("could not read %s: %s", rc, exc)
            continue
        if POSIX_MARKER_START in current and str(directory) in current:
            continue
        if POSIX_MARKER_START in current:
            # Update the existing block in place.
            import re

            pattern = re.compile(
                re.escape(POSIX_MARKER_START)
                + r"[\s\S]*?"
                + re.escape(POSIX_MARKER_END)
                + r"\n?",
                re.MULTILINE,
            )
            updated = pattern.sub(block.lstrip("\n"), current)
            if updated != current:
                rc.write_text(updated, encoding="utf-8")
                changed = True
            continue
        rc.write_text(current.rstrip("\n") + "\n" + block, encoding="utf-8")
        changed = True
    return changed


def remove_from_user_path_posix(directory: Path) -> bool:  # noqa: ARG001 — kept for symmetry
    import re

    changed = False
    pattern = re.compile(
        re.escape(POSIX_MARKER_START)
        + r"[\s\S]*?"
        + re.escape(POSIX_MARKER_END)
        + r"\n?",
        re.MULTILINE,
    )
    for rc in _posix_rc_files():
        if not rc.is_file():
            continue
        try:
            current = rc.read_text(encoding="utf-8")
        except OSError:
            continue
        if POSIX_MARKER_START not in current:
            continue
        updated = pattern.sub("", current)
        if updated != current:
            rc.write_text(updated, encoding="utf-8")
            changed = True
    return changed


def add_to_user_path(directory: Path) -> bool:
    """Cross-platform shim — dispatches to the OS-specific implementation."""
    if sys.platform == "win32":
        return add_to_user_path_windows(directory)
    return add_to_user_path_posix(directory)


def remove_from_user_path(directory: Path) -> bool:
    if sys.platform == "win32":
        return remove_from_user_path_windows(directory)
    return remove_from_user_path_posix(directory)


def add_to_system_path(directory: Path) -> bool:
    """Cross-platform shim for system-wide PATH (admin only on Windows).

    On POSIX falls back to ``add_to_user_path`` — distros vary on how
    to inject a system-wide PATH entry safely (``/etc/profile.d`` vs
    ``/etc/environment`` vs systemd), so we leave that to the
    distribution package and only manage per-user rc files here.
    """
    if sys.platform == "win32":
        return add_to_system_path_windows(directory)
    return add_to_user_path_posix(directory)


def remove_from_system_path(directory: Path) -> bool:
    if sys.platform == "win32":
        return remove_from_system_path_windows(directory)
    return remove_from_user_path_posix(directory)
