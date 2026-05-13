"""Tkinter-based dialogs for the SecondBrain desktop app.

Tkinter ships with the standard library, so dialogs add zero deployment
weight. Each dialog runs as a self-contained ``Tk`` instance on the
calling thread (typically the pystray worker thread): construct, mainloop,
destroy. This keeps the implementation simple at the cost of disallowing
two dialogs simultaneously — acceptable since the tray menu is the
single user-driven entry point.

Public API: re-exports the dialog runners as flat functions so callers
need only one import line.
"""

from .confirm_dialog import ask_confirm
from .first_run_wizard import run_first_run_wizard
from .logs_viewer import open_logs_viewer
from .repair_dialog import show_repair_report
from .scan_dialog import show_scan_report
from .settings_dialog import open_settings_dialog
from .update_dialog import show_combined_update_dialog, show_update_progress

__all__ = [
    "ask_confirm",
    "open_logs_viewer",
    "open_settings_dialog",
    "run_first_run_wizard",
    "show_combined_update_dialog",
    "show_repair_report",
    "show_scan_report",
    "show_update_progress",
]
