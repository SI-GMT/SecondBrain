"""Settings editor — autostart, language, confirmations, polling cadence.

Reads the current ``AppSettings`` + ``KitConfig`` snapshots, lets the user
edit only the desktop-app-owned bits (autostart, language override, etc.),
and writes a fresh settings file via :func:`save_settings`. The kit
config is shown read-only so the user knows where the vault lives without
being tempted to mutate it from here — that's still ``deploy.ps1``'s job.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..config import AppSettings, KitConfig, save_settings
from ._base import dialog_lifecycle, make_root

_LANGUAGES = [("(use kit value)", ""), ("English", "en"), ("Français", "fr"),
              ("Español", "es"), ("Deutsch", "de"), ("Русский", "ru")]


def open_settings_dialog(settings: AppSettings, kit: KitConfig | None) -> AppSettings:
    """Run the dialog. Returns the (possibly mutated) settings instance.

    Cancel / window close returns the input settings unchanged. Save
    returns a fresh validated AppSettings and persists it to disk.
    """
    root = make_root(title="SecondBrain — Settings", size=(560, 480))

    result = {"settings": settings, "saved": False}

    container = ttk.Frame(root, padding=16)
    container.pack(fill="both", expand=True)

    ttk.Label(container, text="Kit configuration", font=("", 11, "bold")).pack(anchor="w")

    if kit is None:
        ttk.Label(
            container,
            text="Memory Kit config not found at ~/.memory-kit/config.json.",
            foreground="#aa3333",
        ).pack(anchor="w", pady=(2, 12))
    else:
        info = ttk.Frame(container)
        info.pack(fill="x", pady=(2, 12))
        for label, value in [
            ("Vault", str(kit.vault)),
            ("Kit repo", str(kit.kit_repo) if kit.kit_repo else "(not set)"),
            ("Language (kit)", kit.language),
        ]:
            row = ttk.Frame(info)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label, width=14).pack(side="left")
            ttk.Label(row, text=value, foreground="#555555").pack(side="left")

    ttk.Separator(container, orient="horizontal").pack(fill="x", pady=8)
    ttk.Label(container, text="Desktop preferences", font=("", 11, "bold")).pack(anchor="w")

    autostart_var = tk.BooleanVar(value=settings.autostart)
    confirm_repair_var = tk.BooleanVar(value=settings.confirm_repair)
    confirm_update_var = tk.BooleanVar(value=settings.confirm_update)
    notify_scan_var = tk.BooleanVar(value=settings.notify_on_scan_findings)
    notify_update_var = tk.BooleanVar(value=settings.notify_on_update_available)
    poll_var = tk.IntVar(value=settings.poll_interval_seconds)
    lang_var = tk.StringVar(value=settings.language_override or "")

    grid = ttk.Frame(container)
    grid.pack(fill="x", pady=(8, 4))

    ttk.Checkbutton(grid, text="Start at login", variable=autostart_var).grid(
        row=0, column=0, sticky="w", padx=4, pady=4
    )
    ttk.Checkbutton(grid, text="Confirm before repair", variable=confirm_repair_var).grid(
        row=0, column=1, sticky="w", padx=4, pady=4
    )
    ttk.Checkbutton(grid, text="Confirm before update", variable=confirm_update_var).grid(
        row=1, column=0, sticky="w", padx=4, pady=4
    )
    ttk.Checkbutton(grid, text="Notify on scan findings", variable=notify_scan_var).grid(
        row=1, column=1, sticky="w", padx=4, pady=4
    )
    ttk.Checkbutton(grid, text="Notify on updates", variable=notify_update_var).grid(
        row=2, column=0, sticky="w", padx=4, pady=4
    )

    ttk.Label(grid, text="Language override:").grid(
        row=3, column=0, sticky="w", padx=4, pady=(12, 4)
    )
    lang_combo = ttk.Combobox(
        grid,
        textvariable=lang_var,
        values=[code for _, code in _LANGUAGES],
        state="readonly",
        width=8,
    )
    lang_combo.grid(row=3, column=1, sticky="w", padx=4, pady=(12, 4))

    ttk.Label(grid, text="Poll interval (s):").grid(
        row=4, column=0, sticky="w", padx=4, pady=4
    )
    poll_spin = ttk.Spinbox(grid, from_=60, to=3600, increment=60, textvariable=poll_var, width=8)
    poll_spin.grid(row=4, column=1, sticky="w", padx=4, pady=4)

    button_row = ttk.Frame(root, padding=(16, 8, 16, 16))
    button_row.pack(fill="x")

    error_label = ttk.Label(button_row, text="", foreground="#aa3333")
    error_label.pack(side="left")

    def _save() -> None:
        try:
            new_settings = AppSettings(
                autostart=autostart_var.get(),
                language_override=lang_var.get() or None,
                confirm_repair=confirm_repair_var.get(),
                confirm_update=confirm_update_var.get(),
                notify_on_scan_findings=notify_scan_var.get(),
                notify_on_update_available=notify_update_var.get(),
                poll_interval_seconds=int(poll_var.get()),
            )
        except Exception as exc:
            error_label.configure(text=f"Invalid value: {exc}")
            return
        save_settings(new_settings)
        result["settings"] = new_settings
        result["saved"] = True
        root.quit()

    def _cancel() -> None:
        root.quit()

    ttk.Button(button_row, text="Cancel", command=_cancel).pack(side="right", padx=(8, 0))
    ttk.Button(button_row, text="Save", command=_save).pack(side="right")

    root.bind("<Escape>", lambda _e: _cancel())
    root.protocol("WM_DELETE_WINDOW", _cancel)

    with dialog_lifecycle(root):
        pass

    return result["settings"]  # type: ignore[return-value]
