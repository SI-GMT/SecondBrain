"""First-run wizard — guides a fresh user through the kit install.

Six-page Tkinter assistant invoked the first time ``SecondBrainTray``
launches (or any time the kit config is absent / explicitly
re-requested):

1. **Welcome** — what SecondBrain is, what the next pages will do.
2. **Vault** — pick the folder where the Markdown vault lives.
3. **Language** — conversational language.
4. **LLM CLIs** — detected installs + tick which to wire.
5. **Install** — runs the kit install **in pure Python** (V0.6+),
   one step at a time, progress shown live.
6. **Done** — success or failure summary + Close button.

State is held in a small dataclass passed between pages; pages call
``go_next`` / ``go_back`` to drive the controller. The controller is
the single ``tk.Tk`` root and swaps the page Frame in place — no
multi-window flicker.

Returns ``True`` when the user successfully reaches the Done page
after a clean install, ``False`` if they cancelled or the install
failed.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable

from .. import __version__
from ..config import save_settings
from ..kit_installer import (
    InstallLayout,
    InstallPlan,
    InstallReport,
    LlmCliInfo,
    default_vault_path,
    detect_llm_clis,
    ensure_vault_exists,
    find_install_layout,
    run_install,
)
from ._base import dialog_lifecycle, make_root

log = logging.getLogger(__name__)


@dataclass
class WizardState:
    """Choices the wizard collects before invoking the kit installer."""

    vault: Path = field(default_factory=default_vault_path)
    language: str = "en"
    detected_clis: list[LlmCliInfo] = field(default_factory=list)
    selected_cli_ids: set[str] = field(default_factory=set)
    install_layout: InstallLayout | None = None
    install_report: InstallReport | None = None


_LANGUAGES = [
    ("English", "en"),
    ("Français", "fr"),
    ("Español", "es"),
    ("Deutsch", "de"),
    ("Русский", "ru"),
]


class _PageBase(ttk.Frame):
    title: str = ""
    next_label: str = "Next"

    def __init__(self, parent: tk.Misc, controller: "_Controller", state: WizardState):
        super().__init__(parent, padding=16)
        self.controller = controller
        self.state = state
        title = ttk.Label(self, text=self.title, font=("", 14, "bold"))
        title.pack(anchor="w", pady=(0, 12))
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.build_body(body)

    def build_body(self, parent: ttk.Frame) -> None:
        raise NotImplementedError

    def on_show(self) -> None:
        pass

    def on_next(self) -> bool:
        return True


class _WelcomePage(_PageBase):
    title = "Welcome to SecondBrain"

    def build_body(self, parent: ttk.Frame) -> None:
        layout = find_install_layout()
        system_install = (
            layout is not None
            and layout.is_system_install
            and layout.engine_already_bootstrapped
        )

        if system_install:
            engine_line = (
                "  • use the shared Memory Kit engine already installed on this "
                "machine (no admin rights needed for this user setup),\n"
            )
        else:
            engine_line = (
                "  • install the Memory Kit engine (bundled in this installer "
                "— no Python required on your machine),\n"
            )

        intro = (
            "SecondBrain gives your AI assistants a persistent memory: a "
            "Markdown vault that survives across sessions, viewable in "
            "Obsidian.\n\n"
            "This short setup will:\n"
            "  • pick a folder for the vault,\n"
            "  • choose a conversational language,\n"
            f"{engine_line}"
            "  • wire it up to every LLM CLI we find on this machine.\n\n"
            "Everything that's specific to you (vault, settings, MCP wiring) "
            "lives in your user profile — on a shared / RDP machine each user "
            "gets their own setup without touching the shared engine."
        )
        ttk.Label(parent, text=intro, justify="left", wraplength=560).pack(
            anchor="w", fill="x", expand=True
        )

        version_row = ttk.Frame(parent)
        version_row.pack(fill="x", pady=(16, 0))
        ttk.Label(
            version_row,
            text=f"SecondBrain Desktop v{__version__}",
            foreground="#666666",
        ).pack(side="left")
        ttk.Button(
            version_row,
            text="Open documentation",
            command=lambda: webbrowser.open("https://github.com/SI-GMT/SecondBrain"),
        ).pack(side="right")


class _VaultPage(_PageBase):
    title = "Where should your vault live?"

    def build_body(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text=(
                "The vault is a regular folder full of Markdown files. We'll "
                "create it now if it doesn't exist."
            ),
            wraplength=560,
            justify="left",
        ).pack(anchor="w")

        self.path_var = tk.StringVar(value=str(self.state.vault))
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(16, 8))
        ttk.Entry(row, textvariable=self.path_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(row, text="Browse…", command=self._browse).pack(
            side="left", padx=(8, 0)
        )

        self.note = ttk.Label(parent, text="", foreground="#666666", wraplength=560)
        self.note.pack(anchor="w", pady=(4, 0))
        self._refresh_note()

        ttk.Button(
            parent, text="Use default location", command=self._use_default
        ).pack(anchor="w", pady=(12, 0))

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(
            title="Pick a folder for your vault",
            initialdir=str(Path(self.path_var.get()).expanduser()),
        )
        if chosen:
            self.path_var.set(chosen)
            self._refresh_note()

    def _use_default(self) -> None:
        self.path_var.set(str(default_vault_path()))
        self._refresh_note()

    def _refresh_note(self) -> None:
        path = Path(self.path_var.get()).expanduser()
        if path.is_dir():
            self.note.configure(text=f"Existing folder: {path}", foreground="#2d8a4f")
        elif path.parent.is_dir():
            self.note.configure(
                text=f"Will be created: {path}", foreground="#666666"
            )
        else:
            self.note.configure(
                text=f"Parent folder does not exist: {path.parent}",
                foreground="#aa3333",
            )

    def on_next(self) -> bool:
        raw = self.path_var.get().strip()
        if not raw:
            self.note.configure(text="Please enter a vault path.", foreground="#aa3333")
            return False
        path = Path(raw).expanduser().resolve()
        if not path.parent.is_dir():
            self.note.configure(
                text=f"Parent folder must exist: {path.parent}",
                foreground="#aa3333",
            )
            return False
        try:
            ensure_vault_exists(path)
        except OSError as exc:
            self.note.configure(text=f"Cannot create folder: {exc}", foreground="#aa3333")
            return False
        self.state.vault = path
        return True


class _LanguagePage(_PageBase):
    title = "Conversational language"

    def build_body(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text=(
                "Your LLM will reply to you in this language. The vault file "
                "structure stays English regardless — only the conversation "
                "surface adapts."
            ),
            wraplength=560,
            justify="left",
        ).pack(anchor="w")

        self.lang_var = tk.StringVar(value=self.state.language)
        frame = ttk.Frame(parent)
        frame.pack(anchor="w", pady=(16, 0))
        for label, code in _LANGUAGES:
            ttk.Radiobutton(
                frame, text=label, value=code, variable=self.lang_var
            ).pack(anchor="w")

    def on_next(self) -> bool:
        self.state.language = self.lang_var.get() or "en"
        return True


class _LlmClisPage(_PageBase):
    title = "LLM clients to wire"

    def build_body(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text=(
                "The installer will configure MCP for the LLM clients you "
                "tick below. We pre-tick the ones we detected locally; "
                "untick any you don't want touched."
            ),
            wraplength=560,
            justify="left",
        ).pack(anchor="w")

        self.checks: dict[str, tk.BooleanVar] = {}
        self.detect_frame = ttk.Frame(parent)
        self.detect_frame.pack(fill="x", pady=(16, 0))

    def on_show(self) -> None:
        for widget in self.detect_frame.winfo_children():
            widget.destroy()
        if not self.state.detected_clis:
            self.state.detected_clis = detect_llm_clis()
        any_installed = False
        for cli in self.state.detected_clis:
            installed = cli.installed
            any_installed = any_installed or installed
            default_value = installed or (cli.identifier in self.state.selected_cli_ids)
            var = tk.BooleanVar(value=default_value)
            self.checks[cli.identifier] = var
            row = ttk.Frame(self.detect_frame)
            row.pack(fill="x", pady=2)
            ttk.Checkbutton(row, text=cli.label, variable=var).pack(side="left")
            status = "detected" if installed else "not detected"
            colour = "#2d8a4f" if installed else "#999999"
            ttk.Label(row, text=f"({status})", foreground=colour).pack(
                side="left", padx=(8, 0)
            )
            if cli.description:
                ttk.Label(row, text=cli.description, foreground="#666666").pack(
                    side="left", padx=(8, 0)
                )

        if not any_installed:
            ttk.Label(
                self.detect_frame,
                text=(
                    "\nNo LLM clients were detected. The engine will still be "
                    "installed so you can wire one up later from the tray."
                ),
                foreground="#aa6633",
            ).pack(anchor="w")

    def on_next(self) -> bool:
        self.state.selected_cli_ids = {
            ident for ident, var in self.checks.items() if var.get()
        }
        return True


class _InstallPage(_PageBase):
    title = "Installing"
    next_label = "Finish"

    def build_body(self, parent: ttk.Frame) -> None:
        self.status_var = tk.StringVar(value="Preparing…")
        ttk.Label(parent, textvariable=self.status_var, font=("", 11, "bold")).pack(
            anchor="w"
        )

        self.progress = ttk.Progressbar(parent, mode="indeterminate", length=560)
        self.progress.pack(fill="x", pady=(8, 8))

        ttk.Label(parent, text="Steps:").pack(anchor="w")
        self.log_text = tk.Text(
            parent, height=14, wrap="word", state="disabled", font=("Consolas", 9)
        )
        yscroll = ttk.Scrollbar(parent, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=yscroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

    def on_show(self) -> None:
        self.controller.set_buttons(back=False, next_enabled=False, cancel_label="Cancel")
        self.progress.start(80)
        layout = find_install_layout()
        if layout is not None and layout.is_system_install and layout.engine_already_bootstrapped:
            self.status_var.set(
                "System engine already installed — running per-user setup only…"
            )
        else:
            self.status_var.set("Running the install in the background…")
        threading.Thread(target=self._do_install, daemon=True, name="kit-install").start()

    def _append(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _do_install(self) -> None:
        layout = find_install_layout()
        if layout is None or not layout.python_exe.is_file():
            self.controller.after(
                0,
                lambda: self._finish(
                    InstallReport(
                        ok=False,
                        error=(
                            "Could not locate the bundled Python runtime. "
                            "This wizard expects to run from an installed "
                            "SecondBrain Desktop — make sure you launched "
                            "via the installer's shortcut, not from a "
                            "source checkout."
                        ),
                    )
                ),
            )
            return
        self.state.install_layout = layout

        selected = [
            cli
            for cli in self.state.detected_clis
            if cli.identifier in self.state.selected_cli_ids
        ]
        plan = InstallPlan(
            vault=self.state.vault,
            language=self.state.language,
            install_dir=layout.install_dir,
            selected_clis=selected,
        )

        def on_progress(message: str) -> None:
            self.controller.after(0, lambda: self._append(message))

        report = run_install(plan, on_progress=on_progress)
        self.controller.after(0, lambda: self._finish(report))

    def _finish(self, report: InstallReport) -> None:
        self.progress.stop()
        self.state.install_report = report
        if report.ok:
            self.status_var.set("Install complete.")
            self._append("")
            self._append(f"Steps OK: {len(report.steps)}")
            self._append(f"CLI wirings: {len(report.wiring)}")
            for w in report.wiring:
                self._append(f"  {w.label}: {w.status} ({w.config_path})")
        else:
            first_fail = report.first_failure()
            label = first_fail.label if first_fail else "install"
            self.status_var.set(f"Install failed at: {label}")
            self._append("")
            self._append(report.error or "Unknown error.")
            if first_fail:
                self._append(first_fail.detail)
        self.controller.set_buttons(back=False, next_enabled=True, cancel_label=None)


class _DonePage(_PageBase):
    title = "All set"
    next_label = "Close"

    def build_body(self, parent: ttk.Frame) -> None:
        self.summary_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.summary_var, font=("", 11)).pack(
            anchor="w", pady=(0, 8)
        )

        self.list_box = tk.Text(
            parent, height=10, wrap="word", state="disabled", font=("Consolas", 9)
        )
        self.list_box.pack(fill="both", expand=True)

        self.hint = ttk.Label(parent, text="", wraplength=560, foreground="#666666")
        self.hint.pack(anchor="w", pady=(12, 0))

    def on_show(self) -> None:
        report = self.state.install_report
        layout = self.state.install_layout
        self.list_box.configure(state="normal")
        self.list_box.delete("1.0", "end")
        if report is None or not report.ok:
            self.summary_var.set("Install did not complete.")
            self.hint.configure(
                text=(
                    "You can retry the wizard from the tray menu (Re-run "
                    "setup wizard). Logs are available via Open logs."
                ),
                foreground="#aa3333",
            )
            if report:
                for step in report.steps:
                    self.list_box.insert(
                        "end", f"{'OK ' if step.ok else 'FAIL'}  {step.label}\n"
                    )
                if report.error:
                    self.list_box.insert("end", "\n" + report.error + "\n")
        else:
            wired_lines = [
                f"  {w.label} → {w.status}" for w in report.wiring if w.ok
            ]
            self.summary_var.set(
                f"Vault: {self.state.vault}\n"
                f"Language: {self.state.language}\n"
                f"Install: {layout.install_dir if layout else '?'}"
            )
            self.list_box.insert("end", "Wired clients:\n")
            if wired_lines:
                self.list_box.insert("end", "\n".join(wired_lines) + "\n")
            else:
                self.list_box.insert("end", "  (none — wire one later from the tray)\n")
            self.hint.configure(
                text=(
                    "The tray icon stays open in your system tray — click it "
                    "to scan, repair, or check for updates anytime."
                ),
                foreground="#666666",
            )
        self.list_box.configure(state="disabled")
        self.controller.set_buttons(back=False, next_enabled=True, cancel_label=None)


class _Controller:
    PAGES: list[type[_PageBase]] = [
        _WelcomePage,
        _VaultPage,
        _LanguagePage,
        _LlmClisPage,
        _InstallPage,
        _DonePage,
    ]

    def __init__(self) -> None:
        self.state = WizardState()
        self.root = make_root(title="SecondBrain — Setup", size=(700, 560))
        self.root.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.container = ttk.Frame(self.root)
        self.container.pack(fill="both", expand=True)

        footer = ttk.Frame(self.root, padding=(16, 8, 16, 16))
        footer.pack(fill="x")
        self.cancel_btn = ttk.Button(footer, text="Cancel", command=self._on_cancel)
        self.cancel_btn.pack(side="right", padx=(8, 0))
        self.next_btn = ttk.Button(footer, text="Next", command=self._on_next)
        self.next_btn.pack(side="right")
        self.back_btn = ttk.Button(footer, text="Back", command=self._on_back)
        self.back_btn.pack(side="right", padx=(0, 8))

        self.current_index = 0
        self.completed = False
        self._build_current()

    def after(self, ms: int, fn: Callable[[], None]) -> None:
        self.root.after(ms, fn)

    def set_buttons(
        self,
        *,
        back: bool = True,
        next_enabled: bool = True,
        cancel_label: str | None = "Cancel",
    ) -> None:
        self.back_btn.configure(state="normal" if back else "disabled")
        self.next_btn.configure(state="normal" if next_enabled else "disabled")
        if cancel_label is None:
            self.cancel_btn.pack_forget()
        else:
            self.cancel_btn.configure(text=cancel_label)
            self.cancel_btn.pack(side="right", padx=(8, 0))

    def _build_current(self) -> None:
        for widget in self.container.winfo_children():
            widget.destroy()
        page_cls = self.PAGES[self.current_index]
        page = page_cls(self.container, self, self.state)
        page.pack(fill="both", expand=True)
        self.current_page = page
        self.next_btn.configure(text=page.next_label)
        self.set_buttons(
            back=(self.current_index > 0 and self.current_index < len(self.PAGES) - 2),
            next_enabled=True,
            cancel_label="Cancel" if self.current_index < len(self.PAGES) - 1 else None,
        )
        page.on_show()

    def _on_next(self) -> None:
        page = self.current_page
        if not page.on_next():
            return
        if self.current_index >= len(self.PAGES) - 1:
            self.completed = (
                self.state.install_report is not None
                and self.state.install_report.ok
            )
            self.root.quit()
            return
        self.current_index += 1
        self._build_current()

    def _on_back(self) -> None:
        if self.current_index == 0:
            return
        self.current_index -= 1
        self._build_current()

    def _on_cancel(self) -> None:
        self.completed = False
        self.root.quit()

    def run(self) -> bool:
        with dialog_lifecycle(self.root):
            pass
        try:
            from ..config import load_settings

            current = load_settings()
            save_settings(current)
        except Exception as exc:
            log.warning("could not persist post-wizard settings: %s", exc)
        return self.completed


def run_first_run_wizard() -> bool:
    """Public entry point — returns True if install completed cleanly."""
    controller = _Controller()
    return controller.run()
