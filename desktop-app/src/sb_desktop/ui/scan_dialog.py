"""Display a vault scan report as a sortable findings table.

Layout:

* Header: total counts by severity.
* Table: columns ``severity / category / path / message`` rendered with a
  ttk.Treeview. Sortable per column.
* Footer: Close button + optional "Run repair (dry-run)" callback hook
  for chaining straight into the repair flow.

We intentionally do not block the caller while the dialog is open — the
``on_repair`` callback fires synchronously inside the dialog so the user
can see the result without leaving the window.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..health import HealthReport
from ._base import dialog_lifecycle, make_root


def show_scan_report(
    report: HealthReport,
    *,
    on_repair: Callable[[bool], str] | None = None,
) -> None:
    root = make_root(title="SecondBrain — Vault scan", size=(820, 520))

    container = ttk.Frame(root, padding=12)
    container.pack(fill="both", expand=True)

    header_text = report.summary or report.render_text()
    header = ttk.Label(container, text=header_text, font=("", 11, "bold"))
    header.pack(anchor="w", pady=(0, 8))

    if not report.ok:
        ttk.Label(container, text=report.error or "Unknown error.").pack(
            anchor="w", pady=(0, 8)
        )
    else:
        tree = ttk.Treeview(
            container,
            columns=("severity", "category", "path", "message"),
            show="headings",
            height=14,
        )
        for col, label, width in [
            ("severity", "Severity", 90),
            ("category", "Category", 200),
            ("path", "Path", 280),
            ("message", "Message", 240),
        ]:
            tree.heading(col, text=label, command=lambda c=col: _sort_by(tree, c, False))
            tree.column(col, width=width, stretch=(col == "message"))

        for finding in report.findings:
            tree.insert(
                "",
                "end",
                values=(
                    finding.severity,
                    finding.category,
                    finding.path or "",
                    finding.message,
                ),
            )

        scroll = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    footer = ttk.Frame(root, padding=(12, 0, 12, 12))
    footer.pack(fill="x")

    repair_status = tk.StringVar(value="")

    def _do_repair(apply: bool) -> None:
        if on_repair is None:
            return
        repair_status.set("Running…")
        root.update_idletasks()
        try:
            text = on_repair(apply)
        except Exception as exc:  # defensive — repair should never crash the UI
            text = f"Repair raised: {exc}"
        repair_status.set(text)

    if on_repair is not None:
        dry_btn = ttk.Button(footer, text="Repair (dry-run)", command=lambda: _do_repair(False))
        dry_btn.pack(side="left")
        apply_btn = ttk.Button(footer, text="Repair (apply)", command=lambda: _do_repair(True))
        apply_btn.pack(side="left", padx=(8, 0))
        ttk.Label(footer, textvariable=repair_status).pack(side="left", padx=(16, 0))

    ttk.Button(footer, text="Close", command=root.quit).pack(side="right")

    with dialog_lifecycle(root):
        pass


def _sort_by(tree: ttk.Treeview, col: str, descending: bool) -> None:
    items = [(tree.set(k, col), k) for k in tree.get_children("")]
    items.sort(reverse=descending)
    for index, (_, key) in enumerate(items):
        tree.move(key, "", index)
    tree.heading(col, command=lambda: _sort_by(tree, col, not descending))
