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

from ..config import load_kit_config
from ..health import HealthReport
from ..kit_installer import find_install_layout
from ..vault_setup import audit_vault_structure, repair_vault_structure
from ._base import dialog_lifecycle, make_root


def show_scan_report(
    report: HealthReport,
    *,
    on_repair: Callable[[bool], str] | None = None,
) -> None:
    root = make_root(title="SecondBrain — Vault scan", size=(820, 560))

    container = ttk.Frame(root, padding=12)
    container.pack(fill="both", expand=True)

    header_text = report.summary or report.render_text()
    header = ttk.Label(container, text=header_text, font=("", 11, "bold"))
    header.pack(anchor="w", pady=(0, 8))

    # Vault-structure audit banner — surfaced ABOVE the findings table
    # so the user notices the more fundamental "you have no zones at
    # all" problem before drowning in per-file findings.
    kit = load_kit_config()
    if kit is not None:
        struct_frame = ttk.Frame(container)
        struct_frame.pack(fill="x", pady=(0, 8))
        struct_status_var = tk.StringVar()
        struct_detail_var = tk.StringVar()
        ttk.Label(
            struct_frame, textvariable=struct_status_var, font=("", 10, "bold")
        ).pack(anchor="w")
        ttk.Label(
            struct_frame,
            textvariable=struct_detail_var,
            foreground="#666666",
            wraplength=780,
        ).pack(anchor="w")
        struct_btn = ttk.Button(struct_frame, text="Repair structure", state="disabled")
        struct_btn.pack(anchor="e", pady=(4, 0))

        def _refresh_struct() -> None:
            audit = audit_vault_structure(kit.vault)
            struct_status_var.set(audit.summary())
            if audit.needs_repair:
                bits: list[str] = []
                if audit.root_index_missing:
                    bits.append("missing: index.md")
                if audit.missing_zone_dirs:
                    bits.append(
                        "missing zones: " + ", ".join(audit.missing_zone_dirs)
                    )
                if audit.missing_zone_indexes:
                    bits.append(
                        "no hub in: " + ", ".join(audit.missing_zone_indexes)
                    )
                struct_detail_var.set(" | ".join(bits))
                struct_btn.configure(state="normal")
            else:
                struct_detail_var.set("")
                struct_btn.configure(state="disabled")

        def _do_struct_repair() -> None:
            from tkinter import messagebox

            layout = find_install_layout()
            obsidian_style = (
                layout.resources_dir / "adapters" / "obsidian-style"
                if layout is not None
                else None
            )
            result = repair_vault_structure(
                kit.vault,
                obsidian_style_dir=(
                    obsidian_style if obsidian_style and obsidian_style.is_dir()
                    else None
                ),
            )
            messagebox.showinfo(
                "SecondBrain — Vault scan",
                f"Vault structure repaired.\n{result.detail}",
            )
            _refresh_struct()

        struct_btn.configure(command=_do_struct_repair)
        _refresh_struct()

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
