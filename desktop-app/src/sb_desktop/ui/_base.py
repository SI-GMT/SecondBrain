"""Shared Tkinter helpers — window setup, theming, lifecycle.

Each dialog instantiates its own ``tk.Tk`` root instead of sharing one.
That's the cheapest pattern compatible with pystray's worker-thread menu
callbacks: no cross-thread marshalling, no risk of a parent root being
destroyed mid-flow. The cost is that two dialogs cannot run at once —
but the tray menu serialises actions anyway, so it's a non-issue in
practice.
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from tkinter import ttk

from PIL import ImageTk

from ..icons import render_app_icon

log = logging.getLogger(__name__)


def _apply_theme(root: tk.Tk) -> None:
    """Pick a vaguely native ttk theme per platform."""
    style = ttk.Style(root)
    available = style.theme_names()
    preference: list[str]
    if sys.platform == "win32":
        preference = ["vista", "winnative", "clam"]
    elif sys.platform == "darwin":
        preference = ["aqua", "clam"]
    else:
        preference = ["clam", "alt", "default"]
    for theme in preference:
        if theme in available:
            style.theme_use(theme)
            return


def make_root(title: str = "SecondBrain", size: tuple[int, int] = (520, 360)) -> tk.Tk:
    root = tk.Tk()
    _activate_macos_for_dialog()
    root.title(title)
    root.geometry(f"{size[0]}x{size[1]}")
    root.minsize(380, 240)
    _apply_theme(root)
    _apply_window_icon(root)
    return root


def _activate_macos_for_dialog() -> None:
    """Make an LSUIElement menu-bar app eligible to show a foreground dialog."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import (  # type: ignore
            NSApplication,
            NSApplicationActivateIgnoringOtherApps,
            NSApplicationActivationPolicyRegular,
            NSRunningApplication,
        )

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
        NSRunningApplication.currentApplication().activateWithOptions_(
            NSApplicationActivateIgnoringOtherApps
        )
    except Exception as exc:
        log.warning("macOS dialog activation failed: %s", exc)


def _restore_macos_after_dialog() -> None:
    """Return the app to menu-bar/accessory mode after the dialog closes."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import (  # type: ignore
            NSApplication,
            NSApplicationActivationPolicyAccessory,
        )

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception as exc:
        log.debug("macOS dialog activation restore failed: %s", exc)


def _raise_dialog(root: tk.Tk) -> None:
    """Bring a freshly-created dialog to the foreground.

    macOS can create Tk windows behind the active app when they are opened
    from a tray-menu callback. A short topmost pulse makes the update dialog
    visible without leaving it permanently above every other window.
    """
    try:
        _activate_macos_for_dialog()
        root.deiconify()
        root.lift()
        root.focus_force()
        root.attributes("-topmost", True)
        root.after(100, _activate_macos_for_dialog)
        root.after(500, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass


_app_icon_cache: ImageTk.PhotoImage | None = None


def _apply_window_icon(root: tk.Tk) -> None:
    """Set the title-bar / dock icon. Errors are silent — non-critical."""
    global _app_icon_cache
    try:
        if _app_icon_cache is None:
            pil = render_app_icon(64).convert("RGBA")
            _app_icon_cache = ImageTk.PhotoImage(pil)
        root.iconphoto(True, _app_icon_cache)
    except Exception:
        pass


@contextmanager
def dialog_lifecycle(root: tk.Tk) -> Iterator[None]:
    """Centre the window then enter the mainloop, destroying on exit."""
    try:
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        root.geometry(f"+{x}+{y}")
        _raise_dialog(root)
        yield
        root.mainloop()
    finally:
        with suppress(tk.TclError):
            root.destroy()
        _restore_macos_after_dialog()
