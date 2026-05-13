"""Settings editor — tabbed dialog covering all user-tunable preferences.

The dialog has four tabs:

1. **General** — autostart, language, poll cadence.
2. **Behaviour** — confirmations, notification level / categories.
3. **Vault & MCP** — vault picker (read-only kit snapshot + per-session
   override), which LLM CLIs the desktop is willing to wire when an
   update is run.
4. **About** — version info, links, log location.

The dialog reads the current snapshots, lets the user edit only the
desktop-owned bits (the kit config stays read-only — it's owned by
``deploy.ps1``), and writes a fresh validated settings file on Save.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk

from .. import __version__
from ..autostart import (
    disable_autostart,
    enable_autostart,
    is_autostart_enabled,
)
from ..config import AppSettings, KitConfig, save_settings
from ..i18n import t
from ..kit_installer import detect_llm_clis
from ..paths import log_file_path, settings_file_path
from ._base import dialog_lifecycle, make_root

_LANGUAGES = [
    ("(use kit value)", ""),
    ("English", "en"),
    ("Français", "fr"),
    ("Español", "es"),
    ("Deutsch", "de"),
    ("Русский", "ru"),
]

_NOTIFY_LEVELS = [
    ("All notifications", "all"),
    ("Errors only", "errors"),
    ("Silent", "silent"),
]

def _detect_installed_clis() -> dict[str, bool]:
    """Return {identifier: installed} via the kit installer detector."""
    return {cli.identifier: cli.installed for cli in detect_llm_clis()}


def _build_mcp_targets() -> list[tuple[str, str, str]]:
    """Source of truth for the MCP target list — pulled from
    :func:`detect_llm_clis` so labels stay aligned with the wizard."""
    return [
        (cli.identifier, cli.label, cli.description) for cli in detect_llm_clis()
    ]


def open_settings_dialog(settings: AppSettings, kit: KitConfig | None) -> AppSettings:
    """Run the dialog. Returns the (possibly mutated) settings instance."""
    root = make_root(title=t("settings.title"), size=(640, 540))
    result: dict = {"settings": settings, "saved": False}

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=12, pady=(12, 0))

    # ---------- variables shared across tabs ----------
    # Autostart UI mirrors the OS-level entry as ground truth, not the
    # cached AppSettings.autostart bit (which can drift if the user toggled
    # the registry value outside the app, or if the installer wrote the
    # entry on first install but the settings file still reads False).
    v_autostart = tk.BooleanVar(value=is_autostart_enabled())
    v_confirm_repair = tk.BooleanVar(value=settings.confirm_repair)
    v_confirm_update = tk.BooleanVar(value=settings.confirm_update)
    v_confirm_destructive = tk.BooleanVar(value=settings.confirm_destructive_repair)
    v_notify_scan = tk.BooleanVar(value=settings.notify_on_scan_findings)
    v_notify_update = tk.BooleanVar(value=settings.notify_on_update_available)
    v_notify_level = tk.StringVar(value=settings.notify_level)
    v_poll = tk.IntVar(value=settings.poll_interval_seconds)
    v_lang = tk.StringVar(value=settings.language_override or "")
    v_vault_override = tk.StringVar(value=settings.vault_override_path or "")
    mcp_targets = _build_mcp_targets()
    installed_map = _detect_installed_clis()
    # On first open (no explicit selection saved) default to detected CLIs;
    # otherwise preserve the user's saved selection AND visibly mark which
    # rows correspond to detected installs.
    has_saved_selection = bool(settings.mcp_targets)
    target_vars: dict[str, tk.BooleanVar] = {
        ident: tk.BooleanVar(
            value=(
                ident in (settings.mcp_targets or [])
                if has_saved_selection
                else installed_map.get(ident, False)
            )
        )
        for ident, _, _ in mcp_targets
    }
    target_status_vars: dict[str, tk.StringVar] = {
        ident: tk.StringVar(
            value=(
                t("settings.detected")
                if installed_map.get(ident)
                else t("settings.not_detected")
            )
        )
        for ident, _, _ in mcp_targets
    }

    # ---------- Tab 1: General ----------
    tab_general = ttk.Frame(notebook, padding=12)
    notebook.add(tab_general, text=t("settings.tab.general"))

    ttk.Checkbutton(
        tab_general, text=t("settings.autostart"), variable=v_autostart
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=4)

    ttk.Label(tab_general, text=t("settings.language")).grid(
        row=1, column=0, sticky="w", pady=4
    )
    lang_combo = ttk.Combobox(
        tab_general,
        textvariable=v_lang,
        values=[code for _, code in _LANGUAGES],
        state="readonly",
        width=10,
    )
    lang_combo.grid(row=1, column=1, sticky="w", pady=4)
    ttk.Label(
        tab_general,
        text="(blank = inherit from ~/.memory-kit/config.json)",
        foreground="#666666",
    ).grid(row=2, column=0, columnspan=2, sticky="w", padx=(0, 0))

    ttk.Label(tab_general, text=t("settings.poll_interval")).grid(
        row=3, column=0, sticky="w", pady=(12, 4)
    )
    ttk.Spinbox(
        tab_general, from_=60, to=3600, increment=60, textvariable=v_poll, width=10
    ).grid(row=3, column=1, sticky="w", pady=(12, 4))
    ttk.Label(
        tab_general,
        text="(how often to refresh status + check for updates)",
        foreground="#666666",
    ).grid(row=4, column=0, columnspan=2, sticky="w")

    # ---------- Tab 2: Behaviour ----------
    tab_behaviour = ttk.Frame(notebook, padding=12)
    notebook.add(tab_behaviour, text=t("settings.tab.behaviour"))

    section = ttk.LabelFrame(tab_behaviour, text="Confirmations", padding=8)
    section.pack(fill="x", pady=(0, 8))
    ttk.Checkbutton(
        section, text="Confirm before running a repair", variable=v_confirm_repair
    ).pack(anchor="w")
    ttk.Checkbutton(
        section,
        text="Always require a second confirmation for destructive repair (file deletion)",
        variable=v_confirm_destructive,
    ).pack(anchor="w")
    ttk.Checkbutton(
        section, text="Confirm before running an update", variable=v_confirm_update
    ).pack(anchor="w")

    notif_section = ttk.LabelFrame(tab_behaviour, text="Notifications", padding=8)
    notif_section.pack(fill="x")
    ttk.Label(notif_section, text="Notification level:").pack(anchor="w")
    for label, value in _NOTIFY_LEVELS:
        ttk.Radiobutton(
            notif_section, text=label, value=value, variable=v_notify_level
        ).pack(anchor="w", padx=(20, 0))
    ttk.Separator(notif_section, orient="horizontal").pack(fill="x", pady=8)
    ttk.Checkbutton(
        notif_section,
        text="Notify when a scan reports findings",
        variable=v_notify_scan,
    ).pack(anchor="w")
    ttk.Checkbutton(
        notif_section,
        text="Notify when an update is available",
        variable=v_notify_update,
    ).pack(anchor="w")

    # ---------- Tab 3: Vault & MCP ----------
    tab_vault = ttk.Frame(notebook, padding=12)
    notebook.add(tab_vault, text=t("settings.tab.vault"))

    kit_box = ttk.LabelFrame(tab_vault, text="Memory Kit configuration (read-only)", padding=8)
    kit_box.pack(fill="x")
    if kit is None:
        ttk.Label(
            kit_box,
            text="No ~/.memory-kit/config.json detected. Install the kit first.",
            foreground="#aa3333",
        ).pack(anchor="w")
    else:
        for label, value in (
            ("Vault:", str(kit.vault)),
            ("Engine:", str(kit.kit_repo) if kit.kit_repo else "(not set)"),
            ("Language:", kit.language),
        ):
            row = ttk.Frame(kit_box)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label, width=14).pack(side="left")
            ttk.Label(row, text=value, foreground="#555555").pack(side="left")

    vault_box = ttk.LabelFrame(tab_vault, text="Per-session vault override", padding=8)
    vault_box.pack(fill="x", pady=(8, 0))
    ttk.Label(
        vault_box,
        text=(
            "Optional. When set, scan / repair / update use this path instead of the "
            "kit-configured vault. Leave blank to use the kit value."
        ),
        foreground="#666666",
        wraplength=560,
    ).pack(anchor="w")
    vault_row = ttk.Frame(vault_box)
    vault_row.pack(fill="x", pady=(4, 0))
    ttk.Entry(vault_row, textvariable=v_vault_override).pack(
        side="left", fill="x", expand=True
    )

    def _browse_vault() -> None:
        chosen = filedialog.askdirectory(
            title="Pick a vault folder", initialdir=v_vault_override.get() or "."
        )
        if chosen:
            v_vault_override.set(chosen)

    ttk.Button(vault_row, text="Browse…", command=_browse_vault).pack(
        side="left", padx=(8, 0)
    )

    targets_box = ttk.LabelFrame(
        tab_vault,
        text="MCP wiring targets (used by Update + the installer)",
        padding=8,
    )
    targets_box.pack(fill="x", pady=(8, 0))
    ttk.Label(
        targets_box,
        text=(
            "Only detected CLIs are pre-ticked. Re-detect after you install "
            "a new client to refresh the list. Tick a row to ask the next "
            "Update / installer run to wire it; untick to leave it alone."
        ),
        foreground="#666666",
        wraplength=560,
    ).pack(anchor="w")

    target_row_widgets: dict[str, tuple[tk.Widget, tk.Widget]] = {}

    def _render_target_rows() -> None:
        for ident, label, descr in mcp_targets:
            row = ttk.Frame(targets_box)
            row.pack(anchor="w", fill="x", pady=1)
            ttk.Checkbutton(
                row, text=f"{label} — {descr}", variable=target_vars[ident]
            ).pack(side="left")
            status_lbl = ttk.Label(
                row,
                textvariable=target_status_vars[ident],
                foreground=(
                    "#2d8a3e" if installed_map.get(ident) else "#999999"
                ),
            )
            status_lbl.pack(side="right", padx=(8, 0))
            target_row_widgets[ident] = (row, status_lbl)

    _render_target_rows()

    def _redetect_clis() -> None:
        fresh = _detect_installed_clis()
        for ident, _ in installed_map.items():
            now_installed = fresh.get(ident, False)
            installed_map[ident] = now_installed
            target_status_vars[ident].set(
                t("settings.detected") if now_installed else t("settings.not_detected")
            )
            _, status_lbl = target_row_widgets[ident]
            status_lbl.configure(
                foreground="#2d8a3e" if now_installed else "#999999"
            )
            if now_installed and not target_vars[ident].get():
                target_vars[ident].set(True)

    ttk.Button(
        targets_box, text=t("settings.redetect"), command=_redetect_clis
    ).pack(anchor="e", pady=(6, 0))

    # ---------- Tab 4: About ----------
    tab_about = ttk.Frame(notebook, padding=12)
    notebook.add(tab_about, text=t("settings.tab.about"))

    ttk.Label(
        tab_about, text="SecondBrain Desktop", font=("", 14, "bold")
    ).pack(anchor="w")
    ttk.Label(tab_about, text=f"Version {__version__}").pack(anchor="w")

    try:
        from memory_kit_mcp import __version__ as kit_version
        ttk.Label(tab_about, text=f"Bundled engine: v{kit_version}").pack(anchor="w")
    except ImportError:
        ttk.Label(tab_about, text="Bundled engine: not importable.").pack(anchor="w")

    ttk.Separator(tab_about, orient="horizontal").pack(fill="x", pady=8)

    links = ttk.Frame(tab_about)
    links.pack(anchor="w")
    ttk.Button(
        links,
        text="Open repository on GitHub",
        command=lambda: webbrowser.open("https://github.com/SI-GMT/SecondBrain"),
    ).pack(anchor="w", pady=2)
    ttk.Button(
        links,
        text="Open release notes",
        command=lambda: webbrowser.open(
            "https://github.com/SI-GMT/SecondBrain/releases"
        ),
    ).pack(anchor="w", pady=2)

    ttk.Separator(tab_about, orient="horizontal").pack(fill="x", pady=8)

    paths = ttk.Frame(tab_about)
    paths.pack(anchor="w")
    for label, value in (
        ("Settings file:", str(settings_file_path())),
        ("Log file:", str(log_file_path())),
    ):
        row = ttk.Frame(paths)
        row.pack(anchor="w", pady=1)
        ttk.Label(row, text=label, width=14).pack(side="left")
        ttk.Label(row, text=value, foreground="#555555").pack(side="left")

    ttk.Label(
        tab_about,
        text=(
            "AGPL-3.0-or-later — © SI-GMT.\n"
            "Issues and feedback: github.com/SI-GMT/SecondBrain/issues"
        ),
        foreground="#666666",
    ).pack(anchor="w", pady=(8, 0))

    # ---------- Footer: Save / Cancel ----------
    button_row = ttk.Frame(root, padding=(16, 8, 16, 16))
    button_row.pack(fill="x")
    error_label = ttk.Label(button_row, text="", foreground="#aa3333")
    error_label.pack(side="left")

    def _save() -> None:
        try:
            new_settings = AppSettings(
                autostart=v_autostart.get(),
                language_override=v_lang.get() or None,
                confirm_repair=v_confirm_repair.get(),
                confirm_update=v_confirm_update.get(),
                confirm_destructive_repair=v_confirm_destructive.get(),
                notify_on_scan_findings=v_notify_scan.get(),
                notify_on_update_available=v_notify_update.get(),
                notify_level=v_notify_level.get() or "all",
                poll_interval_seconds=int(v_poll.get()),
                mcp_targets=[ident for ident, var in target_vars.items() if var.get()],
                vault_override_path=(v_vault_override.get() or None),
            )
        except Exception as exc:
            error_label.configure(text=f"Invalid value: {exc}")
            return

        # If the user typed an override path, validate it exists before saving.
        if new_settings.vault_override_path:
            override = Path(new_settings.vault_override_path).expanduser()
            if not override.is_dir():
                error_label.configure(
                    text=f"Vault override path does not exist: {override}"
                )
                return

        # Apply the OS-level autostart entry so the registry / launchd /
        # XDG state matches what the user just ticked. Failure is logged
        # but doesn't block the save — the settings file is still
        # authoritative for the in-app preference.
        if new_settings.autostart:
            if not enable_autostart():
                error_label.configure(
                    text="Saved, but the OS autostart entry could not be written."
                )
        else:
            disable_autostart()

        save_settings(new_settings)
        # Drop the i18n cache so the next dialog opens in the freshly
        # picked language without an app restart.
        try:
            from ..i18n import reset_active_language

            reset_active_language()
        except ImportError:
            pass
        result["settings"] = new_settings
        result["saved"] = True
        root.quit()

    def _cancel() -> None:
        root.quit()

    ttk.Button(button_row, text=t("settings.cancel"), command=_cancel).pack(
        side="right", padx=(8, 0)
    )
    ttk.Button(button_row, text=t("settings.save"), command=_save).pack(side="right")

    root.bind("<Escape>", lambda _e: _cancel())
    root.protocol("WM_DELETE_WINDOW", _cancel)

    with dialog_lifecycle(root):
        pass

    return result["settings"]  # type: ignore[return-value]
