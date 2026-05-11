"""Modal yes / no confirmation dialog.

Used before any action that mutates the vault or pulls upstream code.
Renders a short title + a body that can include a multi-line
description. Returns True only if the user explicitly clicks Confirm.
Closing the window or pressing Escape is treated as a cancellation.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ._base import dialog_lifecycle, make_root


def ask_confirm(
    title: str,
    message: str,
    *,
    confirm_label: str = "Confirm",
    cancel_label: str = "Cancel",
) -> bool:
    """Block until the user makes a choice. Returns ``True`` on confirm."""
    root = make_root(title=title, size=(440, 220))
    decision: dict[str, bool] = {"confirmed": False}

    container = ttk.Frame(root, padding=16)
    container.pack(fill="both", expand=True)

    title_label = ttk.Label(container, text=title, font=("", 12, "bold"))
    title_label.pack(anchor="w", pady=(0, 8))

    body = ttk.Label(container, text=message, wraplength=400, justify="left")
    body.pack(anchor="w", fill="x", expand=True)

    button_row = ttk.Frame(container)
    button_row.pack(fill="x", pady=(16, 0))

    def _confirm() -> None:
        decision["confirmed"] = True
        root.quit()

    def _cancel() -> None:
        decision["confirmed"] = False
        root.quit()

    cancel_btn = ttk.Button(button_row, text=cancel_label, command=_cancel)
    cancel_btn.pack(side="right", padx=(8, 0))
    confirm_btn = ttk.Button(button_row, text=confirm_label, command=_confirm)
    confirm_btn.pack(side="right")

    confirm_btn.focus_set()
    root.bind("<Escape>", lambda _e: _cancel())
    root.bind("<Return>", lambda _e: _confirm())
    root.protocol("WM_DELETE_WINDOW", _cancel)

    with dialog_lifecycle(root):
        pass

    return decision["confirmed"]
