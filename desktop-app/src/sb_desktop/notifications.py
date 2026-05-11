"""Cross-platform desktop notifications.

Strategy:

* Try ``plyer.notification.notify`` first (pure-Python, multi-backend).
* Fall back to platform-native primitives when plyer fails to load — the
  most common reason is missing optional deps on Windows or macOS — so the
  app keeps notifying instead of silently dropping events.

We never raise: a failed notification is annoying but never reason to
crash the tray loop. All paths log the failure and degrade gracefully.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 8


def _notify_via_plyer(title: str, message: str, app_icon: Path | None) -> bool:
    try:
        from plyer import notification  # type: ignore
    except Exception as exc:
        log.debug("plyer unavailable: %s", exc)
        return False
    try:
        notification.notify(  # type: ignore[union-attr]
            title=title,
            message=message,
            app_name="SecondBrain",
            app_icon=str(app_icon) if app_icon and app_icon.exists() else None,
            timeout=DEFAULT_TIMEOUT_SEC,
        )
        return True
    except Exception as exc:
        log.warning("plyer notify failed: %s", exc)
        return False


def _notify_via_winrt(title: str, message: str, app_icon: Path | None) -> bool:
    if sys.platform != "win32":
        return False
    try:
        from windows_toasts import Toast, WindowsToaster  # type: ignore
    except Exception:
        return False
    try:
        toaster = WindowsToaster("SecondBrain")
        toast = Toast()
        toast.text_fields = [title, message]
        if app_icon and app_icon.exists():
            try:
                toast.AddImage(str(app_icon))  # API older versions
            except Exception:
                pass
        toaster.show_toast(toast)
        return True
    except Exception as exc:
        log.warning("windows-toasts notify failed: %s", exc)
        return False


def _notify_via_osascript(title: str, message: str) -> bool:
    if sys.platform != "darwin":
        return False
    osascript = shutil.which("osascript")
    if osascript is None:
        return False
    safe_title = title.replace('"', '\\"')
    safe_message = message.replace('"', '\\"')
    script = f'display notification "{safe_message}" with title "{safe_title}"'
    try:
        subprocess.run([osascript, "-e", script], check=False, timeout=5)
        return True
    except Exception as exc:
        log.warning("osascript notify failed: %s", exc)
        return False


def _notify_via_notify_send(title: str, message: str, app_icon: Path | None) -> bool:
    if sys.platform == "win32" or sys.platform == "darwin":
        return False
    notify_send = shutil.which("notify-send")
    if notify_send is None:
        return False
    args = [notify_send, "-a", "SecondBrain"]
    if app_icon and app_icon.exists():
        args.extend(["-i", str(app_icon)])
    args.extend([title, message])
    try:
        subprocess.run(args, check=False, timeout=5)
        return True
    except Exception as exc:
        log.warning("notify-send failed: %s", exc)
        return False


def notify(title: str, message: str, app_icon: Path | None = None) -> bool:
    """Show a desktop notification. Returns True if any backend succeeded.

    Tries plyer first (cross-platform), then platform-native fallbacks.
    Returning False simply means the notification was not shown — the tray
    icon menu remains the user's authoritative status surface.
    """
    if _notify_via_plyer(title, message, app_icon):
        return True
    if sys.platform == "win32" and _notify_via_winrt(title, message, app_icon):
        return True
    if sys.platform == "darwin" and _notify_via_osascript(title, message):
        return True
    if sys.platform not in {"win32", "darwin"} and _notify_via_notify_send(
        title, message, app_icon
    ):
        return True
    log.info("no notification backend succeeded for: %s", title)
    return False
