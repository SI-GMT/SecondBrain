"""PATH management — cross-OS automatic.

Windows
=======

* User install → ``HKCU\\Environment\\PATH`` (no admin).
* System install → ``HKLM\\System\\CurrentControlSet\\Control\\
  Session Manager\\Environment\\Path`` (admin only). Without admin
  we fall back to HKCU so at least the current user can reach the
  engine.

After any registry edit we broadcast ``WM_SETTINGCHANGE`` so new
processes (and the Explorer shell) pick up the new value without
logout.

POSIX (macOS / Linux)
=====================

Two layers, both applied so GUI apps **and** terminal shells see
the binary:

1. **Symlink** the engine binary into a directory that's already on
   the default PATH for every process — including GUI apps spawned
   by launchd / systemd-user that never source shell rc files:

   * System install → ``/usr/local/bin/`` (admin/sudo).
     ``path_helper`` on macOS and most Linux distros put this dir
     on PATH before login.
   * User install → ``~/.local/bin/``.
     Auto-added on most distros via ``~/.profile``; on macOS
     ``~/.zprofile`` ships with a snippet that does the same on
     fresh installs. We also write a managed rc-file block as a
     safety net.

2. **rc-file block** in ``~/.bashrc`` / ``~/.zshrc`` so shells that
   skip the login chain (``bash --norc`` etc., embedded terminals)
   still see the entry. The block is fenced by markers so we can
   update it idempotently.

The two layers cover the gap: a Claude Desktop app launched from
Spotlight reads the symlink (no shell init at all), while an open
terminal that pre-existed the install gets the rc-file update on
its next ``source ~/.zshrc``.
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


def user_local_bin() -> Path:
    """Per-user binary directory — on PATH by default on most distros."""
    return Path.home() / ".local" / "bin"


def system_local_bin() -> Path:
    """System binary directory — on PATH for every process on POSIX."""
    return Path("/usr/local/bin")


def _posix_rc_files() -> list[Path]:
    home = Path.home()
    return [home / ".bashrc", home / ".zshrc"]


def ensure_symlink(source: Path, link: Path) -> bool:
    """Idempotently point ``link`` at ``source``.

    Returns True if the symlink was created or re-pointed, False if it
    was already correct. Raises ``PermissionError`` if the parent dir
    can't be written (caller is expected to fall back).
    """
    source = source.resolve()
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        try:
            if link.resolve() == source:
                return False
        except OSError:
            pass
        link.unlink()
    elif link.exists():
        # Existing non-symlink (real file) — refuse to clobber.
        raise FileExistsError(
            f"{link} exists and is not a symlink; refusing to overwrite"
        )
    link.symlink_to(source)
    return True


def remove_symlink_if_ours(link: Path, source: Path) -> bool:
    """Remove ``link`` only if it points at ``source``."""
    if not link.is_symlink():
        return False
    try:
        resolved = link.resolve()
    except OSError:
        return False
    if resolved != source.resolve():
        return False
    link.unlink()
    return True


def _write_rc_block(directory: Path) -> bool:
    """Append/update a managed PATH block in every present rc file.

    Returns True if any rc file was modified. Missing rc files are
    skipped silently — most users only have one.
    """
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


def _strip_rc_block() -> bool:
    """Remove the managed PATH block from any present rc file."""
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


def add_to_user_path_posix(directory: Path, *, binary: Path | None = None) -> bool:
    """Make the engine reachable from PATH for the current user.

    Strategy:
    * If ``binary`` is given, symlink it into ``~/.local/bin``. This
      reaches GUI apps (launchd / systemd-user) that never source
      shell rc files.
    * Always write the rc-file block as well — covers shells that
      pre-existed the install or run with ``--norc``.
    * Missing ``~/.local/bin`` is created automatically.

    Returns True if anything actually changed on disk.
    """
    changed = False
    if binary is not None:
        link = user_local_bin() / binary.name
        try:
            if ensure_symlink(binary, link):
                changed = True
        except (OSError, FileExistsError) as exc:
            log.warning("could not symlink %s -> %s: %s", binary, link, exc)
    rc_dir = user_local_bin() if binary is not None else directory
    if _write_rc_block(rc_dir):
        changed = True
    return changed


def remove_from_user_path_posix(
    directory: Path, *, binary: Path | None = None
) -> bool:
    """Reverse of ``add_to_user_path_posix``."""
    changed = False
    if binary is not None:
        link = user_local_bin() / binary.name
        if remove_symlink_if_ours(link, binary):
            changed = True
    if _strip_rc_block():
        changed = True
    return changed


def add_to_system_path_posix(
    directory: Path, *, binary: Path | None = None
) -> bool:
    """Make the engine reachable from PATH for every user on this host.

    On POSIX the standard way is a symlink in ``/usr/local/bin/``
    (writable by root, already on the default PATH of every process,
    including GUI apps). Without a binary to symlink we fall back to
    the per-user rc file — there is no portable system-wide rc file.

    Raises ``PermissionError`` if root is required and the current
    process can't write to ``/usr/local/bin``; let the caller decide
    whether to fall back to the per-user path.
    """
    if binary is None:
        return add_to_user_path_posix(directory)
    link = system_local_bin() / binary.name
    return ensure_symlink(binary, link)


def remove_from_system_path_posix(
    directory: Path, *, binary: Path | None = None
) -> bool:
    if binary is None:
        return remove_from_user_path_posix(directory)
    link = system_local_bin() / binary.name
    return remove_symlink_if_ours(link, binary)


def add_to_user_path(directory: Path, *, binary: Path | None = None) -> bool:
    """Cross-platform: append ``directory`` to the current user's PATH.

    ``binary`` is honoured on POSIX only (drives the symlink layer).
    Windows callers can leave it None — the registry edit already
    exposes every executable in ``directory``.
    """
    if sys.platform == "win32":
        return add_to_user_path_windows(directory)
    return add_to_user_path_posix(directory, binary=binary)


def remove_from_user_path(directory: Path, *, binary: Path | None = None) -> bool:
    if sys.platform == "win32":
        return remove_from_user_path_windows(directory)
    return remove_from_user_path_posix(directory, binary=binary)


def add_to_system_path(directory: Path, *, binary: Path | None = None) -> bool:
    """Cross-platform: append ``directory`` to the machine-wide PATH.

    Windows: writes ``HKLM`` (raises ``PermissionError`` without admin).
    POSIX: symlinks ``binary`` into ``/usr/local/bin`` (raises
    ``PermissionError`` without root). If ``binary`` is None on POSIX
    we fall back to the per-user rc file.
    """
    if sys.platform == "win32":
        return add_to_system_path_windows(directory)
    return add_to_system_path_posix(directory, binary=binary)


def remove_from_system_path(
    directory: Path, *, binary: Path | None = None
) -> bool:
    if sys.platform == "win32":
        return remove_from_system_path_windows(directory)
    return remove_from_system_path_posix(directory, binary=binary)
