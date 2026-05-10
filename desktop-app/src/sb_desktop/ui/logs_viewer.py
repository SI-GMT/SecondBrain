"""Tail-style log viewer.

Reads the rotating log file produced by :mod:`sb_desktop.logging_setup`
and renders it in a read-only Text widget. Includes:

* A tail-N cap (default 4 000 lines) so giant log files load fast.
* A "Refresh" button to re-read the file in place.
* A "Reveal in folder" button that opens the host file manager at the
  log directory — useful when the user wants to attach logs to a bug
  report.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ..paths import log_file_path
from ._base import dialog_lifecycle, make_root

log = logging.getLogger(__name__)

DEFAULT_TAIL_LINES = 4000


def _read_tail(path: Path, max_lines: int) -> str:
    if not path.is_file():
        return f"(no log yet — {path})"
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError as exc:
        return f"(cannot read log: {exc})"
    return "".join(lines[-max_lines:])


def _reveal_in_folder(target: Path) -> None:
    folder = target.parent
    try:
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(target)], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(target)], check=False)
        else:
            opener = "xdg-open"
            subprocess.run([opener, str(folder)], check=False)
    except Exception as exc:
        log.warning("reveal-in-folder failed: %s", exc)


def open_logs_viewer(*, max_lines: int = DEFAULT_TAIL_LINES) -> None:
    target = log_file_path()
    root = make_root(title=f"SecondBrain — Logs ({target.name})", size=(820, 520))

    container = ttk.Frame(root, padding=8)
    container.pack(fill="both", expand=True)

    text = tk.Text(container, wrap="none", font=("Consolas", 9))
    yscroll = ttk.Scrollbar(container, orient="vertical", command=text.yview)
    xscroll = ttk.Scrollbar(container, orient="horizontal", command=text.xview)
    text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

    text.grid(row=0, column=0, sticky="nsew")
    yscroll.grid(row=0, column=1, sticky="ns")
    xscroll.grid(row=1, column=0, sticky="ew")
    container.rowconfigure(0, weight=1)
    container.columnconfigure(0, weight=1)

    def _refresh() -> None:
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", _read_tail(target, max_lines))
        text.configure(state="disabled")
        text.see("end")

    _refresh()

    footer = ttk.Frame(root, padding=(8, 0, 8, 8))
    footer.pack(fill="x")

    ttk.Label(footer, text=f"Path: {target}").pack(side="left")
    ttk.Button(footer, text="Refresh", command=_refresh).pack(side="right")
    ttk.Button(
        footer,
        text="Reveal in folder",
        command=lambda: _reveal_in_folder(target),
    ).pack(side="right", padx=(0, 8))

    with dialog_lifecycle(root):
        pass
