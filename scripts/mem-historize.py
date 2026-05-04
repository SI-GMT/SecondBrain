#!/usr/bin/env python3
"""
mem-historize.py — move a finished project into the archived zone (or revive
a previously-archived one). Reduces token consumption of the briefing at
session start by keeping finished projects out of `mem-recall` / `mem-list`
default scope without losing them from the vault.

Doctrinal pattern (per `core/procedures/_when-to-script.md`):
versioned, idempotent, dry-run by default. The `mem-historize` skill
delegates to this script — no in-LLM re-implementation.

Behaviours:

  --slug {slug}                Archive the project at
                               10-episodes/projects/{slug}/ to
                               10-episodes/archived/{slug}/. Patch
                               context.md frontmatter: phase: archived,
                               archived_at: {YYYY-MM-DD}, display
                               appended with " [archived]".
  --slug {slug} --revive       Revive the project at
                               10-episodes/archived/{slug}/ back to
                               10-episodes/projects/{slug}/. Restore
                               frontmatter: remove archived_at, set
                               phase: revived (user can update later),
                               strip " [archived]" suffix from display.

Idempotence:
  - Archive a project that is already archived → no-op + report.
  - Revive a project that is already active    → no-op + report.
  - Both check for slug existence in BOTH locations and decide the
    appropriate action without prompting unless ambiguous.

Safety:
  - Dry-run by default. --apply opt-in.
  - Refuses to archive a project whose context.md is unreadable or
    missing — the absence of a context.md indicates a non-conforming
    project that should be triaged manually before historizing.
  - --no-confirm to skip interactive confirmation. Without it, prints
    the plan and asks before executing.

Usage:
    python scripts/mem-historize.py --vault /path/to/vault --slug codemagdns
    python scripts/mem-historize.py --vault /path/to/vault --slug codemagdns --apply
    python scripts/mem-historize.py --vault /path/to/vault --slug codemagdns --revive --apply
    python scripts/mem-historize.py --vault /path/to/vault --slug codemagdns --apply --no-confirm
    python scripts/mem-historize.py --vault /path/to/vault --slug codemagdns --json
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


PROJECTS_DIR = "10-episodes/projects"
ARCHIVED_DIR = "10-episodes/archived"
ARCHIVED_SUFFIX = " [archived]"


def find_project(vault: Path, slug: str) -> tuple[str, Path] | None:
    """Locate a project by slug across active and archived dirs.
    Returns (location, path) where location is 'active' or 'archived',
    or None if not found."""
    active = vault / PROJECTS_DIR / slug
    archived = vault / ARCHIVED_DIR / slug
    in_active = active.is_dir()
    in_archived = archived.is_dir()
    if in_active and in_archived:
        # Should not happen — both are present, ambiguous.
        return ("ambiguous", active)
    if in_active:
        return ("active", active)
    if in_archived:
        return ("archived", archived)
    return None


def patch_context_archive(context_path: Path, dry_run: bool) -> str:
    """Patch context.md to mark as archived. Returns a status string."""
    text = context_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return "no frontmatter — skipped"
    end = text.find("\n---", 4)
    if end == -1:
        return "frontmatter delimiter never closed — skipped"

    fm = text[4:end]
    rest = text[end:]
    today = datetime.now().date().isoformat()

    new_fm = fm

    # phase: → archived
    if re.search(r"^phase:", fm, re.MULTILINE):
        new_fm = re.sub(
            r"^phase:.*$",
            f"phase: archived",
            new_fm,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        new_fm = new_fm.rstrip("\n") + f"\nphase: archived\n"

    # archived_at: {today} (insert if absent, else update)
    if re.search(r"^archived_at:", new_fm, re.MULTILINE):
        new_fm = re.sub(
            r"^archived_at:.*$",
            f'archived_at: "{today}"',
            new_fm,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        new_fm = new_fm.rstrip("\n") + f'\narchived_at: "{today}"\n'

    # display: append [archived] suffix if not already present
    m = re.search(r'^display:\s*(.*)$', new_fm, re.MULTILINE)
    if m:
        current = m.group(1).strip().strip('"').strip("'")
        if ARCHIVED_SUFFIX.strip() not in current:
            new_display = current + ARCHIVED_SUFFIX
            escaped = new_display.replace("\\", "\\\\").replace('"', '\\"')
            new_fm = re.sub(
                r"^display:.*$",
                f'display: "{escaped}"',
                new_fm,
                count=1,
                flags=re.MULTILINE,
            )

    if new_fm == fm:
        return "context.md already marked archived"

    if not dry_run:
        new_text = "---" + new_fm + rest
        tmp = context_path.with_suffix(".md.tmp")
        tmp.write_text(new_text, encoding="utf-8", newline="\n")
        tmp.replace(context_path)

    return "context.md frontmatter patched (phase, archived_at, display)"


def patch_context_revive(context_path: Path, dry_run: bool) -> str:
    """Reverse the archival patch on context.md."""
    text = context_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return "no frontmatter — skipped"
    end = text.find("\n---", 4)
    if end == -1:
        return "frontmatter delimiter never closed — skipped"

    fm = text[4:end]
    rest = text[end:]
    new_fm = fm

    # phase: archived → phase: revived
    new_fm = re.sub(
        r"^phase:\s*archived.*$",
        "phase: revived (please update with current state)",
        new_fm,
        count=1,
        flags=re.MULTILINE,
    )

    # archived_at: → remove the line
    new_fm = re.sub(r"^archived_at:.*\n", "", new_fm, flags=re.MULTILINE)

    # display: strip " [archived]" suffix
    m = re.search(r'^display:\s*(.*)$', new_fm, re.MULTILINE)
    if m:
        current = m.group(1).strip().strip('"').strip("'")
        if ARCHIVED_SUFFIX.strip() in current:
            stripped = current.replace(ARCHIVED_SUFFIX, "").strip()
            escaped = stripped.replace("\\", "\\\\").replace('"', '\\"')
            new_fm = re.sub(
                r"^display:.*$",
                f'display: "{escaped}"',
                new_fm,
                count=1,
                flags=re.MULTILINE,
            )

    if new_fm == fm:
        return "context.md already in revived state"

    if not dry_run:
        new_text = "---" + new_fm + rest
        tmp = context_path.with_suffix(".md.tmp")
        tmp.write_text(new_text, encoding="utf-8", newline="\n")
        tmp.replace(context_path)

    return "context.md frontmatter restored (phase: revived, archived_at removed, display cleaned)"


def archive_project(vault: Path, slug: str, dry_run: bool) -> dict:
    """Archive an active project. Idempotent."""
    found = find_project(vault, slug)
    if found is None:
        return {
            "status": "error",
            "message": f"project '{slug}' not found in active or archived",
        }
    location, _ = found
    if location == "ambiguous":
        return {
            "status": "error",
            "message": f"project '{slug}' exists in BOTH projects/ and archived/ — manual cleanup required",
        }
    if location == "archived":
        return {
            "status": "noop",
            "message": f"project '{slug}' is already archived",
        }
    # location == "active"
    src = vault / PROJECTS_DIR / slug
    dst = vault / ARCHIVED_DIR / slug

    context_path = src / "context.md"
    if not context_path.is_file():
        return {
            "status": "error",
            "message": f"project '{slug}' has no context.md — refusing to archive a non-conforming project",
        }

    operations = []

    # 1. Patch context.md in place (before move, so the move carries the patched file)
    op_msg = patch_context_archive(context_path, dry_run)
    operations.append({"op": "patch-context", "result": op_msg})

    # 2. Ensure archived/ parent exists
    archived_parent = vault / ARCHIVED_DIR
    if not archived_parent.exists():
        if dry_run:
            operations.append({"op": "mkdir-archived-parent", "result": f"would create {archived_parent}"})
        else:
            archived_parent.mkdir(parents=True, exist_ok=True)
            operations.append({"op": "mkdir-archived-parent", "result": f"created {archived_parent}"})

    # 3. Move src → dst
    if dry_run:
        operations.append({"op": "move", "result": f"would move {src} → {dst}"})
    else:
        shutil.move(str(src), str(dst))
        operations.append({"op": "move", "result": f"moved {src.name}/ to archived/"})

    return {
        "status": "ok",
        "action": "archived",
        "slug": slug,
        "src": str(src),
        "dst": str(dst),
        "operations": operations,
    }


def revive_project(vault: Path, slug: str, dry_run: bool) -> dict:
    """Revive an archived project back to active. Idempotent."""
    found = find_project(vault, slug)
    if found is None:
        return {
            "status": "error",
            "message": f"project '{slug}' not found in active or archived",
        }
    location, _ = found
    if location == "ambiguous":
        return {
            "status": "error",
            "message": f"project '{slug}' exists in BOTH locations — manual cleanup required",
        }
    if location == "active":
        return {
            "status": "noop",
            "message": f"project '{slug}' is already active",
        }
    # location == "archived"
    src = vault / ARCHIVED_DIR / slug
    dst = vault / PROJECTS_DIR / slug

    context_path = src / "context.md"
    operations = []

    if context_path.is_file():
        op_msg = patch_context_revive(context_path, dry_run)
        operations.append({"op": "patch-context", "result": op_msg})
    else:
        operations.append({"op": "patch-context", "result": "no context.md — skipped"})

    if dry_run:
        operations.append({"op": "move", "result": f"would move {src} → {dst}"})
    else:
        shutil.move(str(src), str(dst))
        operations.append({"op": "move", "result": f"moved {src.name}/ from archived/ to projects/"})

    return {
        "status": "ok",
        "action": "revived",
        "slug": slug,
        "src": str(src),
        "dst": str(dst),
        "operations": operations,
    }


def confirm_interactive(prompt: str) -> bool:
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes", "o", "oui")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vault", required=True)
    ap.add_argument("--slug", required=True, help="Project slug to historize/revive")
    ap.add_argument("--revive", action="store_true",
                    help="Revive an archived project back to active (default: archive an active one)")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    ap.add_argument("--no-confirm", action="store_true",
                    help="Skip interactive confirmation (combine with --apply)")
    ap.add_argument("--json", action="store_true",
                    help="Print a JSON result on stdout instead of plain text")
    args = ap.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"Error: vault not found: {vault}", file=sys.stderr)
        return 2

    dry_run = not args.apply
    action_label = "REVIVE" if args.revive else "ARCHIVE"

    if not args.json:
        print(f"[i] Vault  : {vault}")
        print(f"[i] Slug   : {args.slug}")
        print(f"[i] Action : {action_label}")
        print(f"[i] Mode   : {'APPLY' if args.apply else 'DRY-RUN'}")
        print()

    # Plan phase (always — the result of dry-run path is the plan).
    if args.revive:
        plan_result = revive_project(vault, args.slug, dry_run=True)
    else:
        plan_result = archive_project(vault, args.slug, dry_run=True)

    if args.json:
        # In JSON mode, print plan + execution result if applied
        out = {"plan": plan_result}
    else:
        if plan_result["status"] == "error":
            print(f"✗ {plan_result['message']}")
            return 1
        if plan_result["status"] == "noop":
            print(f"= {plan_result['message']}")
            return 0
        # status == ok
        print(f"Plan ({action_label} {args.slug}):")
        for op in plan_result.get("operations", []):
            print(f"  - {op['op']}: {op['result']}")
        print()

    # Execute phase if --apply
    if args.apply:
        if not args.no_confirm and not args.json:
            if not confirm_interactive(f"Apply {action_label} on {args.slug}?"):
                print("Cancelled.")
                return 0
        if args.revive:
            exec_result = revive_project(vault, args.slug, dry_run=False)
        else:
            exec_result = archive_project(vault, args.slug, dry_run=False)
        if args.json:
            out["execution"] = exec_result
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            if exec_result["status"] == "ok":
                print(f"✓ {action_label} of '{args.slug}' completed.")
                for op in exec_result.get("operations", []):
                    print(f"  - {op['op']}: {op['result']}")
                print()
                print("Reminder: run rebuild-vault-index.py to refresh the index Archived projects section.")
            else:
                print(f"✗ {exec_result.get('message', 'unknown error')}")
                return 1
    else:
        if args.json:
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            print("(dry-run: re-run with --apply to write changes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
