"""Autostart integration — per-user, cross-platform.

The OS owns the actual "start at login" state; our ``AppSettings.autostart``
flag is just a desktop-side preference. To keep them aligned we read and
write the OS-level entry whenever the user opens / saves Settings.

Per platform:

* **Windows** — ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``
  with value name ``SecondBrainDesktop`` pointing at the installed
  ``SecondBrainTray.exe``. Same key Inno's [Registry] autostart task
  writes, so an in-app save and an installer-driven tick stay
  consistent.
* **macOS** — ``~/Library/LaunchAgents/com.si-gmt.secondbrain.plist``
  (KeepAlive=false, RunAtLoad=true) loaded via ``launchctl load``.
* **Linux** — ``~/.config/autostart/secondbrain-desktop.desktop``
  following the XDG Autostart spec.

Each backend exposes the same triplet:

* :func:`is_autostart_enabled` — best-effort read; returns False on
  unsupported platforms or if the OS hook errored out.
* :func:`enable_autostart` — write the entry. Returns True on success.
* :func:`disable_autostart` — remove the entry. Returns True on success.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_VALUE_NAME = "SecondBrainDesktop"
MACOS_PLIST_LABEL = "com.si-gmt.secondbrain"
LINUX_AUTOSTART_FILENAME = "secondbrain-desktop.desktop"


def _tray_executable() -> Path:
    """Best-effort path to the launcher we want OS-autostart to invoke."""
    return Path(sys.executable).resolve()


def is_autostart_enabled() -> bool:
    if sys.platform == "win32":
        return _windows_read()
    if sys.platform == "darwin":
        return _macos_read()
    return _linux_read()


def enable_autostart() -> bool:
    if sys.platform == "win32":
        return _windows_write(_tray_executable())
    if sys.platform == "darwin":
        return _macos_write(_tray_executable())
    return _linux_write(_tray_executable())


def disable_autostart() -> bool:
    if sys.platform == "win32":
        return _windows_remove()
    if sys.platform == "darwin":
        return _macos_remove()
    return _linux_remove()


# ---------------------------------------------------------------------------
# Windows backend
# ---------------------------------------------------------------------------


def _windows_read() -> bool:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ
        ) as key:
            value, _ = winreg.QueryValueEx(key, WINDOWS_VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError as exc:
        log.warning("could not read HKCU\\Run\\%s: %s", WINDOWS_VALUE_NAME, exc)
        return False


def _windows_write(exe_path: Path) -> bool:
    import winreg

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
            quoted = f'"{exe_path}"'
            winreg.SetValueEx(key, WINDOWS_VALUE_NAME, 0, winreg.REG_SZ, quoted)
        return True
    except OSError as exc:
        log.warning("autostart write failed: %s", exc)
        return False


def _windows_remove() -> bool:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            try:
                winreg.DeleteValue(key, WINDOWS_VALUE_NAME)
            except FileNotFoundError:
                return True
        return True
    except OSError as exc:
        log.warning("autostart remove failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# macOS backend
# ---------------------------------------------------------------------------


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MACOS_PLIST_LABEL}.plist"


def _macos_read() -> bool:
    return _macos_plist_path().is_file()


def _macos_write(exe_path: Path) -> bool:
    plist = _macos_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{MACOS_PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""
    try:
        plist.write_text(payload, encoding="utf-8")
        if shutil.which("launchctl"):
            subprocess.run(
                ["launchctl", "load", "-w", str(plist)],
                check=False,
                capture_output=True,
            )
        return True
    except OSError as exc:
        log.warning("autostart write failed: %s", exc)
        return False


def _macos_remove() -> bool:
    plist = _macos_plist_path()
    if not plist.is_file():
        return True
    try:
        if shutil.which("launchctl"):
            subprocess.run(
                ["launchctl", "unload", "-w", str(plist)],
                check=False,
                capture_output=True,
            )
        plist.unlink()
        return True
    except OSError as exc:
        log.warning("autostart remove failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Linux backend (XDG Autostart)
# ---------------------------------------------------------------------------


def _linux_autostart_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "autostart" / LINUX_AUTOSTART_FILENAME


def _linux_read() -> bool:
    return _linux_autostart_path().is_file()


def _linux_write(exe_path: Path) -> bool:
    target = _linux_autostart_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=SecondBrain Desktop\n"
        "Comment=Persistent memory companion for your LLM agents\n"
        f"Exec={exe_path}\n"
        "Terminal=false\n"
        "Icon=secondbrain-desktop\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-MATE-Autostart-enabled=true\n"
    )
    try:
        target.write_text(content, encoding="utf-8")
        return True
    except OSError as exc:
        log.warning("autostart write failed: %s", exc)
        return False


def _linux_remove() -> bool:
    target = _linux_autostart_path()
    if not target.is_file():
        return True
    try:
        target.unlink()
        return True
    except OSError as exc:
        log.warning("autostart remove failed: %s", exc)
        return False
