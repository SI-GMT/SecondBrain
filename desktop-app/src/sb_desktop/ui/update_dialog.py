"""Update progress dialog.

Driven by a callback that runs the actual update synchronously while
this dialog displays a busy state. The callback is expected to return
an :class:`sb_desktop.update.UpdateRunResult` so we can render success
or the error tail without flicker.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..update import UpdateRunResult
from ._base import dialog_lifecycle, make_root


def show_update_progress(
    runner: Callable[[], UpdateRunResult],
    *,
    title: str = "SecondBrain — Updating",
) -> UpdateRunResult | None:
    """Spawn a worker thread that runs ``runner`` and updates the UI.

    Returns the result once the dialog closes; ``None`` only if the
    runner crashed before completing.
    """
    root = make_root(title=title, size=(560, 360))
    captured: dict[str, UpdateRunResult | None] = {"result": None}

    container = ttk.Frame(root, padding=14)
    container.pack(fill="both", expand=True)

    status_var = tk.StringVar(value="Running deploy script…")
    ttk.Label(container, textvariable=status_var, font=("", 11, "bold")).pack(anchor="w")

    progress = ttk.Progressbar(container, mode="indeterminate", length=400)
    progress.pack(fill="x", pady=8)
    progress.start(50)

    log_text = tk.Text(container, height=10, wrap="word", state="disabled")
    log_text.pack(fill="both", expand=True)

    button_row = ttk.Frame(root, padding=(14, 0, 14, 14))
    button_row.pack(fill="x")
    close_btn = ttk.Button(button_row, text="Close", command=root.quit, state="disabled")
    close_btn.pack(side="right")

    def _append_log(text: str) -> None:
        log_text.configure(state="normal")
        log_text.insert("end", text)
        log_text.configure(state="disabled")
        log_text.see("end")

    def _on_done(result: UpdateRunResult) -> None:
        progress.stop()
        captured["result"] = result
        status_var.set(result.render_text().splitlines()[0])
        body = "\n--- stdout ---\n" + result.stdout_tail + "\n--- stderr ---\n" + result.stderr_tail
        _append_log(body)
        close_btn.configure(state="normal")

    def _worker() -> None:
        try:
            result = runner()
        except Exception as exc:
            err = UpdateRunResult.model_construct(
                ok=False, confirmed=True, plan=None, error=str(exc)  # type: ignore[arg-type]
            )
            root.after(0, lambda: _on_done(err))
            return
        root.after(0, lambda: _on_done(result))

    threading.Thread(target=_worker, daemon=True).start()

    with dialog_lifecycle(root):
        pass

    return captured["result"]
