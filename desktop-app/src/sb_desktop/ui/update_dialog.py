"""Update dialogs.

Two flavours:

* :func:`show_combined_update_dialog` — the v0.9 dual-channel UX. Shows
  engine + desktop status side by side, lets the user download the
  available asset and trigger the install per channel. Used by the
  tray menu's "Check for updates" action.
* :func:`show_update_progress` — legacy single-channel progress
  dialog kept for the deploy.ps1 path (still used by ``run_update``
  on dev installs that don't have a system installer to upgrade).
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..update import (
    ApplyResult,
    CombinedUpdateInfo,
    DownloadResult,
    UpdateCheckResult,
    UpdateRunResult,
    download_and_install_engine,
    download_asset,
    install_engine_update,
    launch_desktop_installer,
)
from ._base import dialog_lifecycle, make_root


# ---------------------------------------------------------------------------
# Combined dialog (engine + desktop)
# ---------------------------------------------------------------------------


def show_combined_update_dialog(
    info: CombinedUpdateInfo,
    *,
    title: str = "SecondBrain — Updates",
) -> None:
    """Render both channels with per-channel download + install actions."""
    root = make_root(title=title, size=(620, 440))

    header = ttk.Frame(root, padding=(14, 14, 14, 6))
    header.pack(fill="x")
    ttk.Label(
        header,
        text="SecondBrain update status",
        font=("", 12, "bold"),
    ).pack(anchor="w")
    ttk.Label(
        header,
        text=(
            "The engine (kit on your PATH) and the desktop app update "
            "independently. Choose what to install — your vault, "
            "settings and MCP wirings stay intact."
        ),
        wraplength=580,
        foreground="#555",
    ).pack(anchor="w", pady=(2, 0))

    body = ttk.Frame(root, padding=(14, 6, 14, 6))
    body.pack(fill="both", expand=True)

    _ChannelRow(
        body,
        info.desktop,
        channel="desktop",
        on_apply=_apply_desktop,
    ).pack(fill="x", pady=(0, 10))
    _ChannelRow(
        body,
        info.engine,
        channel="engine",
        on_apply=_apply_engine,
    ).pack(fill="x", pady=(0, 10))

    footer = ttk.Frame(root, padding=(14, 0, 14, 14))
    footer.pack(fill="x")
    ttk.Button(footer, text="Close", command=root.quit).pack(side="right")

    with dialog_lifecycle(root):
        pass


class _ChannelRow(ttk.LabelFrame):
    """One row per update channel — version display + action button."""

    def __init__(
        self,
        master: tk.Widget,
        result: UpdateCheckResult,
        *,
        channel: str,
        on_apply: Callable[[UpdateCheckResult, "_ChannelRow"], None],
    ) -> None:
        super().__init__(
            master,
            text=_channel_title(channel),
            padding=10,
        )
        self.result = result
        self.channel = channel
        self.on_apply = on_apply

        # Versions line.
        line = ttk.Frame(self)
        line.pack(fill="x")
        self._current_label = ttk.Label(
            line,
            text=f"Current: v{result.current_version or '—'}",
            font=("", 10),
        )
        self._current_label.pack(side="left")
        ttk.Label(
            line,
            text=f"Latest: v{result.latest_version or '—'}",
            font=("", 10),
        ).pack(side="left", padx=(20, 0))

        # Status text.
        self.status_var = tk.StringVar(value=_initial_status(result, channel))
        ttk.Label(self, textvariable=self.status_var, wraplength=560).pack(
            anchor="w", pady=(4, 0)
        )

        # Progress + action button.
        self.progress = ttk.Progressbar(self, length=420, mode="determinate")
        self.progress.pack(fill="x", pady=(8, 0))

        button_row = ttk.Frame(self)
        button_row.pack(fill="x", pady=(6, 0))
        self.action_btn = ttk.Button(
            button_row,
            text=_action_label(result, channel),
            command=self._handle_click,
            state=("normal" if result.update_available and _has_asset(result, channel)
                   else "disabled"),
        )
        self.action_btn.pack(side="right")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def set_current_version(self, version: str) -> None:
        self._current_label.configure(text=f"Current: v{version}")

    def set_progress(self, value: float) -> None:
        self.progress.configure(value=value)

    def disable_button(self, new_text: str | None = None) -> None:
        if new_text:
            self.action_btn.configure(text=new_text)
        self.action_btn.configure(state="disabled")

    def _handle_click(self) -> None:
        self.action_btn.configure(state="disabled")
        threading.Thread(
            target=self.on_apply, args=(self.result, self), daemon=True
        ).start()


def _channel_title(channel: str) -> str:
    return "SecondBrain Desktop (installer)" if channel == "desktop" else "SecondBrain Engine"


def _initial_status(result: UpdateCheckResult, channel: str) -> str:
    if not result.ok:
        return f"Check failed: {result.error or 'unknown error'}"
    if not result.update_available:
        return "Up to date."
    if not _has_asset(result, channel):
        if channel == "engine":
            return (
                "Update is published on GitHub, but no installable wheel "
                "asset is attached to the release. To apply it now, install "
                "the next desktop release (which bundles the latest engine). "
            )
        return "Update available, but no installer asset found on the release."
    return "Update available — click to download & install."


def _action_label(result: UpdateCheckResult, channel: str) -> str:
    if not result.update_available:
        return "Up to date"
    if not _has_asset(result, channel):
        return "Open release page"
    return "Download & install"


def _has_asset(result: UpdateCheckResult, channel: str) -> bool:
    return bool(result.asset_url and result.asset_filename)


def _apply_desktop(result: UpdateCheckResult, row: _ChannelRow) -> None:
    """Download the installer and launch/open it for the current platform."""
    if not result.asset_url or not result.asset_filename:
        return _open_release_page(result, row, "sb-desktop")

    def on_progress(received: int, total: int | None) -> None:
        if total and total > 0:
            pct = (received / total) * 100
            row.master.after(0, lambda: row.set_progress(pct))
            row.master.after(
                0,
                lambda: row.set_status(
                    f"Downloading installer… {received // 1024} KB / {total // 1024} KB"
                ),
            )
        else:
            row.master.after(
                0,
                lambda: row.set_status(
                    f"Downloading installer… {received // 1024} KB"
                ),
            )

    row.set_status("Downloading installer…")
    download = download_asset(
        result.asset_url,
        result.asset_filename,
        on_progress=on_progress,
    )
    if not download.ok or download.path is None:
        row.master.after(
            0,
            lambda: row.set_status(
                f"Download failed: {download.error or 'unknown error'}"
            ),
        )
        return

    launch_text = (
        "Opening DMG — drag SecondBrain.app to Applications…"
        if sys.platform == "darwin"
        else "Launching installer (look for the UAC prompt)…"
    )
    row.master.after(0, lambda: row.set_status(launch_text))
    apply_result = launch_desktop_installer(download.path)
    if apply_result.ok:
        followup = (
            "DMG opened. Drag SecondBrain.app to Applications to complete "
            "the upgrade, then restart the app."
            if sys.platform == "darwin"
            else (
                "Installer launched. The tray will be closed automatically; "
                "follow the installer to complete the upgrade."
            )
        )
        row.master.after(
            0,
            lambda: row.set_status(followup),
        )
        final_label = "DMG opened" if sys.platform == "darwin" else "Installing…"
        row.master.after(0, lambda: row.disable_button(final_label))
    else:
        row.master.after(
            0, lambda: row.set_status(f"Launch failed: {apply_result.error}")
        )


def _apply_engine(result: UpdateCheckResult, row: _ChannelRow) -> None:
    """Engine in-place upgrade via the offline wheelhouse asset.

    Downloads the release's ``memory_kit_mcp-*-wheelhouse-*.zip``, extracts
    it, and runs :func:`install_engine_update` (pip ``--no-index
    --find-links`` against the embedded ``python.exe``). When the engine lives
    under a system install, pip re-elevates via a UAC prompt. Falls back to
    opening the release page when no wheelhouse asset is attached.
    """
    if not result.asset_url or not result.asset_filename:
        return _open_release_page(result, row, "engine")

    def on_download(received: int, total: int | None) -> None:
        if total and total > 0:
            pct = (received / total) * 100
            row.master.after(0, lambda: row.set_progress(pct))
            row.master.after(
                0,
                lambda: row.set_status(
                    f"Downloading engine wheelhouse… "
                    f"{received // 1024} KB / {total // 1024} KB"
                ),
            )
        else:
            row.master.after(
                0,
                lambda: row.set_status(
                    f"Downloading engine wheelhouse… {received // 1024} KB"
                ),
            )

    def on_status(message: str) -> None:
        row.master.after(0, lambda: row.set_status(message))

    row.set_status("Downloading engine wheelhouse…")
    apply_result = download_and_install_engine(
        result.asset_url,
        result.asset_filename,
        on_download=on_download,
        on_status=on_status,
    )
    if apply_result.ok:
        # Re-read the on-disk engine version so the row reflects the upgrade
        # without a tray restart; fall back to the target (latest) version.
        from ..update import _installed_engine_version

        new_version = _installed_engine_version() or result.latest_version or ""
        row.master.after(0, lambda: row.set_current_version(new_version))
        row.master.after(
            0,
            lambda: row.set_status(
                f"Engine updated to v{new_version}. Restart your CLI sessions "
                "to pick up the new version."
            ),
        )
        row.master.after(0, lambda: row.disable_button("Up to date"))
    else:
        row.master.after(
            0,
            lambda: row.set_status(
                f"Engine update failed: {apply_result.error}"
            ),
        )


def _open_release_page(
    result: UpdateCheckResult, row: _ChannelRow, kind: str
) -> None:
    import webbrowser

    tag = "sb-desktop-v" + (result.latest_version or "")
    if kind == "engine":
        tag = "v" + (result.latest_version or "")
    url = f"https://github.com/SI-GMT/SecondBrain/releases/tag/{tag}"
    webbrowser.open(url)
    row.master.after(0, lambda: row.set_status(f"Release page opened: {url}"))


# ---------------------------------------------------------------------------
# Legacy single-channel progress dialog (deploy.ps1 path)
# ---------------------------------------------------------------------------


def show_update_progress(
    runner: Callable[[], UpdateRunResult],
    *,
    title: str = "SecondBrain — Updating",
) -> UpdateRunResult | None:
    """Spawn a worker thread that runs ``runner`` and updates the UI.

    Kept for the deploy.ps1 path used by ``run_update`` in development
    installs. Production desktop installs go through
    :func:`show_combined_update_dialog` instead.
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
