#!/usr/bin/env python3
"""
migrate-vault-add-archived-zone.py — bootstrap the `10-episodes/archived/`
folder in a vault that pre-dates v0.7.4 (or that simply has never had an
archived project).

The folder is created with `.gitkeep` so it's preserved in git-tracked
vaults. Idempotent: re-runs are no-ops.

This migration is rarely needed because `mem-historize.py` itself creates
the archived/ parent on first use. The script is provided for completeness
and for vault provisioning workflows that prefer to set up the structure
explicitly upfront.

Usage:
    python scripts/migrate-vault-add-archived-zone.py --vault /path/to/vault
    python scripts/migrate-vault-add-archived-zone.py --vault /path/to/vault --apply
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vault", required=True)
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = ap.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"Error: vault not found: {vault}", file=sys.stderr)
        return 2

    archived = vault / "10-episodes" / "archived"
    gitkeep = archived / ".gitkeep"

    print(f"[i] Vault : {vault}")
    print(f"[i] Mode  : {'APPLY' if args.apply else 'DRY-RUN'}")
    print()

    actions = []

    if archived.exists():
        actions.append(f"[--] {archived.relative_to(vault).as_posix()}/ already exists")
    else:
        if args.apply:
            archived.mkdir(parents=True, exist_ok=True)
            actions.append(f"[OK] created {archived.relative_to(vault).as_posix()}/")
        else:
            actions.append(f"[plan] would create {archived.relative_to(vault).as_posix()}/")

    if gitkeep.exists():
        actions.append(f"[--] {gitkeep.relative_to(vault).as_posix()} already exists")
    else:
        if args.apply:
            gitkeep.parent.mkdir(parents=True, exist_ok=True)
            gitkeep.write_text("", encoding="utf-8", newline="\n")
            actions.append(f"[OK] created {gitkeep.relative_to(vault).as_posix()}")
        else:
            actions.append(f"[plan] would create {gitkeep.relative_to(vault).as_posix()}")

    for a in actions:
        print(a)

    if not args.apply:
        print()
        print("(dry-run: re-run with --apply to write changes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
