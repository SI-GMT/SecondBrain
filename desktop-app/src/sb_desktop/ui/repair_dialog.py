"""Detailed repair feedback dialog.

Shows the before/after diff produced by :func:`repair_vault` so the
user can see exactly what changed. The previous footer-label feedback
made it look like "nothing happened" when the vault simply had no
auto-fixable findings — this dialog spells out the per-category
breakdown and the manual-review remainder.

Layout:

* Header — one-line summary (Applied N fixes, Δ findings).
* Two-column table: category | before | fixed | after.
* Lists of modified and deleted files (scrollable).
* Manual-review remainder explained.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..health import HealthRepairReport
from ._base import dialog_lifecycle, make_root


def show_repair_report(report: HealthRepairReport) -> None:
    root = make_root(title="SecondBrain — Repair result", size=(720, 540))

    container = ttk.Frame(root, padding=12)
    container.pack(fill="both", expand=True)

    headline = report.render_text().splitlines()[0]
    ttk.Label(container, text=headline, font=("", 11, "bold")).pack(anchor="w")

    if not report.ok:
        ttk.Label(container, text=report.error or "", foreground="#aa3333").pack(
            anchor="w", pady=(4, 0)
        )
        _close_button(root)
        with dialog_lifecycle(root):
            pass
        return

    diff_frame = ttk.LabelFrame(container, text="Findings by category", padding=8)
    diff_frame.pack(fill="x", pady=(8, 8))

    tree = ttk.Treeview(
        diff_frame,
        columns=("category", "before", "fixed", "after"),
        show="headings",
        height=8,
    )
    for col, label, width, anchor in [
        ("category", "Category", 280, "w"),
        ("before", "Before", 90, "center"),
        ("fixed", "Fixed", 90, "center"),
        ("after", "After", 90, "center"),
    ]:
        tree.heading(col, text=label)
        tree.column(col, width=width, anchor=anchor)

    categories = sorted(
        set(report.counts_before) | set(report.counts_after)
    )
    for cat in categories:
        before = report.counts_before.get(cat, 0)
        after = report.counts_after.get(cat, 0)
        fixed = report.fixed_by_category.get(cat, 0)
        tag = "drop" if after < before else ("flat" if after == before else "up")
        tree.insert(
            "", "end",
            values=(cat, before, fixed if fixed else "—", after),
            tags=(tag,),
        )
    tree.tag_configure("drop", foreground="#2d8a4f")
    tree.tag_configure("flat", foreground="#666666")
    tree.tag_configure("up", foreground="#aa6633")
    tree.pack(fill="x")

    counters = ttk.Frame(container)
    counters.pack(fill="x", pady=(0, 8))
    for label, value in (
        ("Fixed:", report.fixed_count),
        ("Skipped:", report.skipped_count),
        ("Manual review:", report.manual_review_count),
        ("Δ findings:", report.findings_before - report.findings_after),
    ):
        cell = ttk.Frame(counters)
        cell.pack(side="left", padx=(0, 16))
        ttk.Label(cell, text=label).pack(side="left")
        ttk.Label(cell, text=str(value), font=("", 10, "bold")).pack(side="left", padx=(4, 0))

    if report.files_modified or report.files_deleted:
        files_frame = ttk.LabelFrame(container, text="Affected files", padding=8)
        files_frame.pack(fill="both", expand=True, pady=(0, 8))

        text = tk.Text(files_frame, height=8, wrap="none")
        scroll = ttk.Scrollbar(files_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set, state="normal")

        for path in report.files_modified:
            text.insert("end", f"M  {path}\n")
        for path in report.files_deleted:
            text.insert("end", f"D  {path}\n")

        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    if report.manual_review_count:
        hint = ttk.Label(
            container,
            text=(
                f"{report.manual_review_count} finding(s) still require manual "
                "review — see the Scan dialog for details."
            ),
            foreground="#aa6633",
        )
        hint.pack(anchor="w", pady=(0, 8))

    if report.workflow_hints:
        hints_frame = ttk.LabelFrame(
            container, text="Recommended workflow", padding=8
        )
        hints_frame.pack(fill="x", pady=(0, 8))
        for category, hint_text in report.workflow_hints.items():
            row = ttk.Frame(hints_frame)
            row.pack(fill="x", pady=(0, 6))
            ttk.Label(row, text=f"{category}:", font=("", 9, "bold")).pack(
                anchor="w"
            )
            ttk.Label(
                row, text=hint_text, wraplength=640, foreground="#555555"
            ).pack(anchor="w", padx=(12, 0))

    _close_button(root)

    with dialog_lifecycle(root):
        pass


def _close_button(root: tk.Tk) -> None:
    footer = ttk.Frame(root, padding=(12, 0, 12, 12))
    footer.pack(fill="x")
    ttk.Button(footer, text="Close", command=root.quit).pack(side="right")
    root.bind("<Escape>", lambda _e: root.quit())
