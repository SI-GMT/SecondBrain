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
            from sb_desktop.ui import run_first_run_wizard

            log.info("launching first-run wizard")
            ok = run_first_run_wizard()
            if not ok:
                log.warning("first-run wizard cancelled or install failed")
                # We still drop into the tray so the user can retry from the
                # menu, see logs, or use the desktop without the engine.

    from sb_desktop.tray import run_tray

    return run_tray()


def _entry() -> NoReturn:
    sys.exit(main())


if __name__ == "__main__":
    _entry()
