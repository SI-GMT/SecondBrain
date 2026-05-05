"""Standalone CLI for vault migrations: ``python -m memory_kit_mcp.migrate``.

Useful for the deploy hook, headless CI, and users who don't want to spin
up the MCP server just to migrate. Same engine as the ``mem_migrate`` MCP
tool — just a different surface.

Usage:
    python -m memory_kit_mcp.migrate                  # dry-run
    python -m memory_kit_mcp.migrate --apply          # apply with auto-backup
    python -m memory_kit_mcp.migrate --apply --skip-backup
    python -m memory_kit_mcp.migrate --vault PATH     # override vault path
    python -m memory_kit_mcp.migrate --config PATH    # override config path
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from memory_kit_mcp.config import _resolve_config_path, get_config
from memory_kit_mcp.migrations import CURRENT_SCHEMA_VERSION, run_pending


def _force_utf8_console() -> None:
    """Reconfigure stdout/stderr to UTF-8 with replacement on Windows.

    Default Python on Windows uses cp1252 for stdout, which crashes on any
    character outside that codepage (e.g. ``→`` in summaries, accented
    French in messages). We reconfigure on entry — supported since Python
    3.7 — with ``errors='replace'`` so even unexpected characters degrade
    to ``?`` rather than raise. No-op on systems already running UTF-8.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                # Best-effort; if reconfigure isn't supported (e.g. piped
                # through a wrapper), fall through silently.
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_console()
    parser = argparse.ArgumentParser(
        prog="python -m memory_kit_mcp.migrate",
        description="Run pending vault schema migrations.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually run the migrations (default is dry-run).",
    )
    parser.add_argument(
        "--skip-backup", action="store_true",
        help="Skip the automatic backup before applying. Use only when you've "
             "manually backed up, or for vaults > 500 MiB.",
    )
    parser.add_argument("--vault", help="Override vault path.")
    parser.add_argument("--config", help="Override config file path.")
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Less verbose output.",
    )
    args = parser.parse_args(argv)

    if args.vault:
        vault = Path(args.vault).expanduser().resolve()
    else:
        try:
            vault = get_config().vault
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR] Cannot resolve vault path: {exc}", file=sys.stderr)
            return 2

    if args.config:
        config_path = Path(args.config).expanduser().resolve()
    else:
        config_path = _resolve_config_path()

    if not vault.is_dir():
        print(f"[ERR] Vault directory not found: {vault}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"[i] Vault          : {vault}")
        print(f"[i] Config         : {config_path}")
        print(f"[i] Target version : {CURRENT_SCHEMA_VERSION}")
        print(f"[i] Mode           : {'apply' if args.apply else 'dry-run'}")
        print()

    report = run_pending(
        vault=vault,
        config_path=config_path,
        dry_run=not args.apply,
        skip_backup=args.skip_backup,
    )

    print(f"From version: {report.from_version}")
    print(f"To version  : {report.to_version}")
    if report.backup_path:
        print(f"Backup       : {report.backup_path}")
    print()
    if not report.steps:
        print("No pending migrations.")
    for step in report.steps:
        marker = "[OK]" if step.applied else ("[--]" if step.needed else "[..]")
        print(f"{marker} v{step.target_version} ({step.module}) — needed={step.needed} applied={step.applied}")
        if step.files_modified:
            print(f"     {len(step.files_modified)} file(s) modified")
        if step.files_created:
            print(f"     {len(step.files_created)} file(s) created")
        if step.error:
            print(f"     ERROR: {step.error}")
    print()
    print(report.summary)
    if not args.apply and any(s.needed for s in report.steps):
        print()
        print("Re-invoke with --apply to write changes (auto-backup will be taken).")
    return 0 if all(not s.error for s in report.steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
