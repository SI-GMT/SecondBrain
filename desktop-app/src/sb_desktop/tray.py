"""Tray application — pystray entrypoint + menu wiring.

The tray icon is the user's primary surface. Three responsibilities:

1. Render the current engine state as a coloured disc on the tray glyph.
2. Expose actions: Status / Scan / Repair / Update / Vault / Settings /
   Logs / Quit.
3. Refresh the icon on a configurable polling cadence so the user sees
   when something drifts (engine missing, update available) without
   having to open the menu.

Threading model:

* ``pystray.Icon.run`` blocks the calling thread (typically ``main``).
* A background ``threading.Thread`` runs the polling loop and pushes
  state onto the icon via ``icon.icon = ...`` and ``icon.menu = ...``.
* Menu callbacks run on pystray's worker thread; they may open Tk
  dialogs synchronously (each dialog spins its own ``Tk`` root).

The shared :class:`TrayState` is protected by a re-entrant lock so the
poller and the action handlers see a coherent snapshot.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

import pystray

from . import __version__
from .config import AppSettings, KitConfig, load_kit_config, load_settings
from .health import HealthRepairReport, HealthReport, repair_vault, scan_vault
from .i18n import t
from .icons import render_icon
from .notifications import notify
from .status import StatusLevel, StatusSnapshot, probe_status
from .ui import (
    ask_confirm,
    open_logs_viewer,
    open_settings_dialog,
    show_repair_report,
    show_scan_report,
    show_combined_update_dialog,
    show_update_progress,
)
from .update import (
    CombinedUpdateInfo,
    UpdateCheckResult,
    check_all_updates,
    check_desktop_update,
    check_update,
    plan_update,
    run_update,
)

log = logging.getLogger(__name__)


@dataclass
class TrayState:
    """Mutable shared state between the poller and menu callbacks."""

    settings: AppSettings = field(default_factory=AppSettings)
    kit: KitConfig | None = None
    status: StatusSnapshot | None = None
    last_update_check: UpdateCheckResult | None = None
    notified_update_for_version: str | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)


def _open_path_in_filemanager(target: Path) -> None:
    if not target.exists():
        log.warning("cannot open missing path: %s", target)
        return
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)
    except Exception as exc:
        log.error("open path failed: %s", exc)


def _refresh_icon(icon: pystray.Icon, state: TrayState) -> None:
    level = state.status.level if state.status else StatusLevel.UNKNOWN
    icon.icon = render_icon(level, size=64)
    icon.title = _tooltip(state)
    icon.menu = _build_menu(icon, state)


def _tooltip(state: TrayState) -> str:
    base = f"SecondBrain Desktop v{__version__}"
    if state.status is None:
        return base
    return f"{base}\n{state.status.summary}"


def _build_menu(icon: pystray.Icon, state: TrayState) -> pystray.Menu:
    """Re-build the menu reflecting current state.

    pystray menus are immutable once shown; we rebuild on every refresh
    so labels (status / version) stay in sync. Cheap — pystray handles
    diffing internally.
    """

    status_label = (
        state.status.summary if state.status else t("menu.status.probing")
    )

    update_label = t("menu.check_updates")
    if state.last_update_check is not None and state.last_update_check.update_available:
        update_label = t(
            "menu.update_available",
            current=state.last_update_check.current_version,
            latest=state.last_update_check.latest_version,
        )

    return pystray.Menu(
        pystray.MenuItem(status_label, _action_status(icon, state), default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("menu.scan"), _action_scan(icon, state)),
        pystray.MenuItem(t("menu.repair"), _action_repair(icon, state)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(update_label, _action_update(icon, state)),
        pystray.MenuItem(t("menu.open_vault"), _action_open_vault(state)),
        pystray.MenuItem(t("menu.open_logs"), lambda *_: open_logs_viewer()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("menu.settings"), _action_settings(icon, state)),
        pystray.MenuItem(t("menu.rerun_wizard"), _action_rerun_wizard(icon, state)),
        pystray.MenuItem(t("menu.about"), _action_about),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("menu.quit"), lambda *_: icon.stop()),
    )


def _action_status(icon: pystray.Icon, state: TrayState):
    def handler(*_args) -> None:
        _do_status_probe(icon, state)

    return handler


def _action_scan(icon: pystray.Icon, state: TrayState):
    def handler(*_args) -> None:
        report = scan_vault()
        with state.lock:
            if state.settings.notify_on_scan_findings and report.has_findings():
                notify(
                    t("notify.scan.title"),
                    t("notify.scan.body", count=len(report.findings)),
                )
        show_scan_report(
            report,
            on_repair=lambda apply: _run_repair_from_dialog(state, apply),
        )

    return handler


def _action_repair(icon: pystray.Icon, state: TrayState):
    def handler(*_args) -> None:
        with state.lock:
            confirm = state.settings.confirm_repair
        if confirm:
            ok = ask_confirm(
                title=t("confirm.repair.title"),
                message=t("confirm.repair.message"),
                confirm_label=t("confirm.repair.button"),
            )
            if not ok:
                return
        _run_repair_with_review(state)

    return handler


def _run_repair_from_dialog(state: TrayState, apply: bool) -> str:
    """Hook used by the scan dialog's inline repair buttons."""
    if apply:
        with state.lock:
            confirm = state.settings.confirm_repair
        if confirm and not ask_confirm(
            title=t("confirm.apply.title"),
            message=t("confirm.apply.message"),
            confirm_label=t("confirm.apply.button"),
        ):
            return "Cancelled."
    report = repair_vault(apply=apply)
    if apply:
        # Surface the full diff dialog so the user sees what changed.
        try:
            show_repair_report(report)
        except Exception as exc:
            log.warning("show_repair_report raised: %s", exc)
    return _format_repair(report)


def _run_repair_with_review(state: TrayState) -> None:
    dry = repair_vault(apply=False)
    if not dry.ok:
        notify("SecondBrain — repair failed", dry.error or "Unknown error")
        return
    if dry.fixed_count == 0:
        # Honest UX: distinguish "nothing to fix" from "we ignored stuff that
        # needs manual review". Surface the full report so the user sees the
        # manual-review remainder and which categories require attention.
        show_repair_report(dry)
        return
    proceed = ask_confirm(
        title="Apply repair",
        message=(
            f"Dry-run shows {dry.fixed_count} fix(es) ready to apply"
            + (
                f" plus {dry.manual_review_count} requiring manual review.\n"
                if dry.manual_review_count else ".\n"
            )
            + "Apply the auto-fixes now?"
        ),
        confirm_label="Apply",
    )
    if not proceed:
        return
    final = repair_vault(apply=True)
    show_repair_report(final)
    notify("SecondBrain — repair", _format_repair(final))


def _format_repair(report: HealthRepairReport) -> str:
    if not report.ok:
        return f"Repair failed: {report.error or 'unknown error'}"
    mode = "applied" if report.applied else "dry-run"
    return f"Repair {mode}: {report.fixed_count} fixed, {report.skipped_count} skipped."


def _action_update(icon: pystray.Icon, state: TrayState):
    """Open the combined update dialog (engine + desktop).

    Replaces the v0.8-era single-channel deploy.ps1 flow. Dialog
    drives the per-channel download + install. Old ``run_update`` /
    ``show_update_progress`` path remains available for dev installs
    via the CLI (``sb-desktop --action update``).
    """

    def handler(*_args) -> None:
        info = check_all_updates(force_refresh=True)
        with state.lock:
            state.last_update_check = info.engine
        _refresh_icon(icon, state)

        if not info.any_available:
            engine_v = info.engine.current_version or "?"
            desktop_v = info.desktop.current_version or "?"
            notify(
                t("notify.up_to_date.title"),
                t("notify.up_to_date.body", engine=engine_v, desktop=desktop_v),
            )
            return

        show_combined_update_dialog(info)
        # After the dialog closes, re-probe so the tray icon reflects
        # any in-place engine refresh.
        _do_status_probe(icon, state)

    return handler


def _action_open_vault(state: TrayState):
    def handler(*_args) -> None:
        with state.lock:
            kit = state.kit
        if kit is None or not kit.vault_exists:
            notify("SecondBrain", "Vault path not configured.")
            return
        _open_path_in_filemanager(kit.vault)

    return handler


def _action_settings(icon: pystray.Icon, state: TrayState):
    def handler(*_args) -> None:
        with state.lock:
            current_settings = state.settings
            kit_snapshot = state.kit
        new_settings = open_settings_dialog(current_settings, kit_snapshot)
        with state.lock:
            state.settings = new_settings
        _refresh_icon(icon, state)

    return handler


def _action_about(*_args) -> None:
    webbrowser.open("https://github.com/SI-GMT/SecondBrain")


def _action_rerun_wizard(icon: pystray.Icon, state: TrayState):
    """Re-launch the setup wizard from the tray. Useful for adding a new
    LLM CLI after the initial install, or for changing the vault path."""

    def handler(*_args) -> None:
        from .ui import run_first_run_wizard

        ok = run_first_run_wizard()
        if ok:
            with state.lock:
                state.kit = None  # force re-read of ~/.memory-kit/config.json
            from .config import load_kit_config

            with state.lock:
                state.kit = load_kit_config()
            _do_status_probe(icon, state)

    return handler


def _do_status_probe(icon: pystray.Icon, state: TrayState) -> None:
    snapshot = probe_status()
    with state.lock:
        state.status = snapshot
    log.info("status probe: %s", snapshot.level.value)
    _refresh_icon(icon, state)


def _poll_loop(icon: pystray.Icon, state: TrayState, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            with state.lock:
                interval = state.settings.poll_interval_seconds
                notify_update = state.settings.notify_on_update_available
                last_notified = state.notified_update_for_version
            _do_status_probe(icon, state)

            info = check_all_updates(force_refresh=False)
            with state.lock:
                state.last_update_check = info.engine
                # Notify once per (engine, desktop) version pair. Prefer
                # the desktop update line when both are available because
                # installing the desktop release implicitly refreshes the
                # bundled engine.
                key_parts: list[str] = []
                if info.desktop.update_available:
                    key_parts.append(f"desktop={info.desktop.latest_version}")
                if info.engine.update_available:
                    key_parts.append(f"engine={info.engine.latest_version}")
                key = ";".join(key_parts)
                should_notify = bool(
                    notify_update and key and key != last_notified
                )
                if should_notify:
                    state.notified_update_for_version = key

            if should_notify:
                line_parts: list[str] = []
                if info.desktop.update_available:
                    line_parts.append(
                        f"Desktop v{info.desktop.current_version} → "
                        f"v{info.desktop.latest_version}"
                    )
                if info.engine.update_available:
                    line_parts.append(
                        f"Engine v{info.engine.current_version} → "
                        f"v{info.engine.latest_version}"
                    )
                notify(
                    "SecondBrain — update available",
                    " · ".join(line_parts),
                )
            _refresh_icon(icon, state)
        except Exception as exc:
            log.exception("poll loop iteration failed: %s", exc)
        stop_event.wait(timeout=interval)


def _initial_state() -> TrayState:
    return TrayState(
        settings=load_settings(),
        kit=load_kit_config(),
    )


def run_tray() -> int:
    """Build the tray icon, start the poller, and run the event loop."""
    state = _initial_state()
    initial_icon = render_icon(StatusLevel.UNKNOWN, size=64)
    icon = pystray.Icon(
        "sb-desktop",
        icon=initial_icon,
        title=f"SecondBrain Desktop v{__version__}",
    )
    icon.menu = _build_menu(icon, state)

    stop_event = threading.Event()
    poller = threading.Thread(
        target=_poll_loop, args=(icon, state, stop_event), daemon=True, name="sb-desktop-poller"
    )

    def _on_ready(_icon: pystray.Icon) -> None:
        _icon.visible = True
        threading.Thread(
            target=lambda: _do_status_probe(icon, state),
            daemon=True,
            name="sb-desktop-init-probe",
        ).start()
        poller.start()

    try:
        icon.run(setup=_on_ready)
    finally:
        stop_event.set()
    return 0
