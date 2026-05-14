"""SecondBrain Desktop entry point.

Three execution modes:

* ``sb-desktop`` (no args)   — launch the systray app (default).
* ``sb-desktop --version``   — print version and exit (useful for installer probes).
* ``sb-desktop --healthcheck`` — run a non-interactive status probe and exit
  with code 0 if the Memory Kit MCP server is reachable, 1 otherwise.
* ``sb-desktop --no-tray --action <name>`` — invoke a single action headless
  (for installer post-hooks or CI). Supported actions: ``status``, ``scan``,
  ``check-update``.

The tray loop is blocking; everything else returns synchronously so an
installer can chain calls without spawning a long-lived process.

Imports here are **absolute** (``from sb_desktop import …``) on purpose:
PyInstaller uses this file as the bundle entrypoint and runs it as a
top-level script, which strips the package context and breaks relative
imports. Absolute imports keep both ``python -m sb_desktop`` (package
mode) and the PyInstaller-built ``SecondBrainTray.exe`` working.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from typing import NoReturn

from sb_desktop import __version__
from sb_desktop.logging_setup import configure_logging

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sb-desktop",
        description="SecondBrain Desktop — systray companion for the Memory Kit MCP server.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"sb-desktop {__version__}",
    )
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Probe the MCP server and exit (0 = reachable, 1 = not).",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Skip the tray loop (use with --action for headless invocations).",
    )
    parser.add_argument(
        "--action",
        choices=["status", "scan", "check-update"],
        help="Run a single named action and exit.",
    )
    parser.add_argument(
        "--dialog",
        choices=["settings", "logs", "scan", "repair", "wizard", "update"],
        help=(
            "Open one desktop dialog and exit. Used internally by the tray "
            "on macOS so Tk windows run outside pystray's AppKit loop."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console + file log verbosity (default: INFO).",
    )
    parser.add_argument(
        "--first-run",
        action="store_true",
        help=(
            "Force the first-run wizard even if the kit config is already "
            "present (useful for re-running setup)."
        ),
    )
    parser.add_argument(
        "--skip-first-run",
        action="store_true",
        help=(
            "Skip the auto-launched first-run wizard and go straight to the "
            "tray, even if the kit is not yet installed."
        ),
    )
    return parser


def _run_dialog_action(dialog: str) -> int:
    """Open a single Tk dialog in this process and exit."""
    log.info("dialog action requested: %s", dialog)
    if dialog == "settings":
        from sb_desktop.config import load_kit_config, load_settings
        from sb_desktop.ui import open_settings_dialog

        open_settings_dialog(load_settings(), load_kit_config())
        return 0
    if dialog == "logs":
        from sb_desktop.ui import open_logs_viewer

        open_logs_viewer()
        return 0
    if dialog == "scan":
        from sb_desktop.health import repair_vault, scan_vault
        from sb_desktop.ui import show_repair_report, show_scan_report

        def _repair_from_scan(apply: bool) -> str:
            report = repair_vault(apply=apply)
            if apply:
                show_repair_report(report)
            if not report.ok:
                return f"Repair failed: {report.error or 'unknown error'}"
            mode = "applied" if report.applied else "dry-run"
            return (
                f"Repair {mode}: {report.fixed_count} fixed, "
                f"{report.skipped_count} skipped."
            )

        show_scan_report(scan_vault(), on_repair=_repair_from_scan)
        return 0
    if dialog == "repair":
        from sb_desktop.health import repair_vault
        from sb_desktop.ui import ask_confirm, show_repair_report

        proceed = ask_confirm(
            title="Repair vault",
            message="Run a repair dry-run first, then review the proposed fixes?",
            confirm_label="Review",
        )
        if not proceed:
            return 0
        dry = repair_vault(apply=False)
        if not dry.ok or dry.fixed_count == 0:
            show_repair_report(dry)
            return 0 if dry.ok else 1
        apply = ask_confirm(
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
        show_repair_report(repair_vault(apply=True) if apply else dry)
        return 0
    if dialog == "wizard":
        from sb_desktop.ui import run_first_run_wizard

        return 0 if run_first_run_wizard() else 1
    if dialog == "update":
        from sb_desktop.ui import show_combined_update_dialog
        from sb_desktop.update import check_all_updates

        show_combined_update_dialog(check_all_updates(force_refresh=True))
        return 0
    log.error("unknown dialog: %s", dialog)
    return 64


def _dialog_command(dialog: str, *, log_level: str | None = None) -> list[str]:
    """Return a command that opens one dialog in a short-lived helper process."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--dialog", dialog]
    else:
        cmd = [sys.executable, "-m", "sb_desktop", "--dialog", dialog]
    if log_level:
        cmd.extend(["--log-level", log_level])
    return cmd


def _run_dialog_helper(dialog: str, *, log_level: str | None = None) -> int:
    """Run a dialog helper without importing Tk/AppKit in the tray process."""
    cmd = _dialog_command(dialog, log_level=log_level)
    log.info("running dialog helper: %s", " ".join(cmd))
    try:
        completed = subprocess.run(cmd, check=False)
    except Exception as exc:
        log.exception("dialog helper failed to start: %s", exc)
        return 1
    return int(completed.returncode or 0)


def _run_headless_action(action: str) -> int:
    """Dispatch a single headless action to its module. Returns exit code."""
    if action == "status":
        from sb_desktop.status import probe_status

        snapshot = probe_status()
        print(snapshot.render_text())
        return 0 if snapshot.is_ok() else 1
    if action == "scan":
        from sb_desktop.health import scan_vault

        report = scan_vault()
        print(report.render_text())
        return 0 if not report.has_findings() else 2
    if action == "check-update":
        from sb_desktop.update import check_update

        result = check_update()
        print(result.render_text())
        return 0 if not result.update_available else 3
    log.error("unknown action: %s", action)
    return 64


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    configure_logging(level=args.log_level)
    log.info("sb-desktop %s starting", __version__)

    if args.healthcheck:
        from sb_desktop.status import probe_status

        snapshot = probe_status()
        return 0 if snapshot.is_ok() else 1

    if args.dialog:
        return _run_dialog_action(args.dialog)

    if args.action:
        return _run_headless_action(args.action)

    if args.no_tray:
        log.warning("--no-tray without --action is a no-op; exiting.")
        return 0

    # First-run flow: launch the wizard if the kit config is absent (i.e. a
    # brand-new machine) OR if the user explicitly re-runs it via --first-run.
    # ``--skip-first-run`` is the escape hatch for power users or scripted
    # smoke tests that want the tray directly.
    if not args.skip_first_run:
        from sb_desktop.config import load_kit_config

        kit_present = load_kit_config() is not None
        if args.first_run or not kit_present:
            log.info("launching first-run wizard")
            rc = _run_dialog_helper("wizard", log_level=args.log_level)
            if rc != 0:
                log.warning("first-run wizard cancelled or install failed")
                # We still drop into the tray so the user can retry from the
                # menu, see logs, or use the desktop without the engine.

    from sb_desktop.tray import run_tray

    return run_tray()


def _entry() -> NoReturn:
    sys.exit(main())


if __name__ == "__main__":
    _entry()
