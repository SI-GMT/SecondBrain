"""User PATH management — append / remove install directories.

Windows uses ``HKCU\\Environment\\PATH`` as the per-user PATH store
(no admin needed). After editing it we broadcast ``WM_SETTINGCHANGE``
so any new process (and the Explorer shell) picks up the new value
without requiring a logout.

POSIX side: append a single ``# SecondBrain managed`` block to the
user's shell rc file. We touch ``~/.bashrc`` and ``~/.zshrc`` when
present — covers macOS (zsh default) and most Linux setups. The block
is delimited with markers so a later uninstall can remove it cleanly.

All operations are idempotent: re-running them leaves the file the
same as if it had been run once.
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
