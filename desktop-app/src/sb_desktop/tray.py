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
* Menu callbacks return quickly. Any Tk dialog is opened in a short-lived
  helper process so Tk does not share pystray's AppKit loop on macOS.

The shared :class:`TrayState` is protected by a re-entrant lock so the
poller and the action handlers see a coherent snapshot.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

import pystray

from . import __version__
from .config import AppSettings, KitConfig, load_kit_config, load_settings
from .i18n import t
from .icons import render_icon
from .notifications import notify
from .status import StatusLevel, StatusSnapshot, probe_status
from .update import (
    CombinedUpdateInfo,
    UpdateCheckResult,
    check_all_updates,
)

log = logging.getLogger(__name__)


@dataclass
class TrayState:
    """Mutable shared state between the poller and menu callbacks."""

    settings: AppSettings = field(default_factory=AppSettings)
    kit: KitConfig | None = None
    status: StatusSnapshot | None = None
    last_update_check: UpdateCheckResult | None = None
    last_combined_update: CombinedUpdateInfo | None = None
    notified_update_for_version: str | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
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


def _dialog_command(dialog: str) -> list[str]:
    """Return a command that opens a single UI dialog in a helper process."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--dialog", dialog]
    return [sys.executable, "-m", "sb_desktop", "--dialog", dialog]


def _launch_dialog(dialog: str) -> None:
    """Spawn a dialog helper and return immediately to pystray/AppKit."""
    cmd = _dialog_command(dialog)
    log.info("launching dialog helper: %s", " ".join(cmd))
    try:
        subprocess.Popen(
            cmd,
            close_fds=True,
            start_new_session=(sys.platform != "win32"),
        )
    except Exception as exc:
        log.exception("failed to launch dialog helper %s: %s", dialog, exc)
        notify("SecondBrain", f"Impossible d'ouvrir la fenêtre: {exc}")


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

    update_info = _preferred_update_for_menu(state)
    update_label = t("menu.check_updates")
    if update_info is not None and update_info.update_available:
        update_label = t(
            "menu.update_available",
            current=update_info.current_version,
            latest=update_info.latest_version,
        )

    return pystray.Menu(
        pystray.MenuItem(status_label, _action_status(icon, state), default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("menu.scan"), _action_scan(icon, state)),
        pystray.MenuItem(t("menu.repair"), _action_repair(icon, state)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(update_label, _action_update(icon, state)),
        pystray.MenuItem(t("menu.open_vault"), _action_open_vault(state)),
        pystray.MenuItem(t("menu.open_logs"), _action_open_logs()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("menu.settings"), _action_settings(icon, state)),
        pystray.MenuItem(t("menu.rerun_wizard"), _action_rerun_wizard(icon, state)),
        pystray.MenuItem(t("menu.about"), _action_about),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("menu.quit"), _action_quit(icon, state)),
    )


def _preferred_update_for_menu(state: TrayState) -> UpdateCheckResult | None:
    """Return the update channel that should drive the tray menu label.

    Desktop updates are preferred because installing the desktop bundle also
    refreshes the bundled engine. Older state only stored the engine result,
    which made a desktop-only update visible via notification but not via the
    menu entry the user needs to click to download it.
    """
    combined = state.last_combined_update
    if combined is not None:
        if combined.desktop.update_available:
            return combined.desktop
        if combined.engine.update_available:
            return combined.engine
    return state.last_update_check


def _action_status(icon: pystray.Icon, state: TrayState):
    def handler(*_args) -> None:
        _do_status_probe(icon, state)

    return handler


def _action_scan(icon: pystray.Icon, state: TrayState):
    def handler(*_args) -> None:
        log.info("scan action requested")
        _launch_dialog("scan")

    return handler


def _action_repair(icon: pystray.Icon, state: TrayState):
    def handler(*_args) -> None:
        log.info("repair action requested")
        _launch_dialog("repair")

    return handler


def _action_update(icon: pystray.Icon, state: TrayState):
    """Open the combined update dialog (engine + desktop)."""

    def handler(*_args) -> None:
        try:
            log.info("manual update check requested")
            _launch_dialog("update")
        except Exception as exc:
            log.exception("update dialog failed: %s", exc)
            notify("SecondBrain — update", f"Impossible d'ouvrir la fenêtre: {exc}")

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


def _action_open_logs():
    def handler(*_args) -> None:
        log.info("logs viewer action requested")
        _launch_dialog("logs")

    return handler


def _action_settings(icon: pystray.Icon, state: TrayState):
    def handler(*_args) -> None:
        log.info("settings action requested")
        _launch_dialog("settings")
        _refresh_icon(icon, state)

    return handler


def _action_about(*_args) -> None:
    webbrowser.open("https://github.com/SI-GMT/SecondBrain")


def _action_quit(icon: pystray.Icon, state: TrayState):
    def handler(*_args) -> None:
        log.info("quit action requested")
        state.stop_event.set()
        try:
            icon.stop()
        except Exception as exc:
            log.exception("tray stop failed: %s", exc)

    return handler


def _action_rerun_wizard(icon: pystray.Icon, state: TrayState):
    """Re-launch the setup wizard from the tray. Useful for adding a new
    LLM CLI after the initial install, or for changing the vault path."""

    def handler(*_args) -> None:
        log.info("first-run wizard action requested")
        _launch_dialog("wizard")

    return handler


def _do_status_probe(icon: pystray.Icon, state: TrayState) -> None:
    snapshot = probe_status()
    with state.lock:
        state.status = snapshot
    log.info("status probe: %s", snapshot.level.value)
    _refresh_icon(icon, state)


def _poll_loop(icon: pystray.Icon, state: TrayState) -> None:
    while not state.stop_event.is_set():
        try:
            with state.lock:
                interval = state.settings.poll_interval_seconds
                notify_update = state.settings.notify_on_update_available
                last_notified = state.notified_update_for_version
            _do_status_probe(icon, state)

            info = check_all_updates(force_refresh=False)
            with state.lock:
                state.last_update_check = info.engine
                state.last_combined_update = info
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
        state.stop_event.wait(timeout=interval)


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

    poller = threading.Thread(
        target=_poll_loop, args=(icon, state), daemon=True, name="sb-desktop-poller"
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
        state.stop_event.set()
        if poller.is_alive():
            poller.join(timeout=2)
    return 0
