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
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import NoReturn

from . import __version__
from .logging_setup import configure_logging

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
    return parser


def _run_headless_action(action: str) -> int:
    """Dispatch a single headless action to its module. Returns exit code."""
    if action == "status":
        from .status import probe_status

        snapshot = probe_status()
        print(snapshot.render_text())
        return 0 if snapshot.is_ok() else 1
    if action == "scan":
        from .health import scan_vault

        report = scan_vault()
        print(report.render_text())
        return 0 if not report.has_findings() else 2
    if action == "check-update":
        from .update import check_update

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
        from .status import probe_status

        snapshot = probe_status()
        return 0 if snapshot.is_ok() else 1

    if args.action:
        return _run_headless_action(args.action)

    if args.no_tray:
        log.warning("--no-tray without --action is a no-op; exiting.")
        return 0

    from .tray import run_tray

    return run_tray()


def _entry() -> NoReturn:
    sys.exit(main())


if __name__ == "__main__":
    _entry()
