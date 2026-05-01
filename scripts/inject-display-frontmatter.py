#!/usr/bin/env python3
"""
inject-display-frontmatter.py — backfill the `display` frontmatter field on
every file in the vault, following the conventions per kind documented in
core/procedures/_frontmatter-universal.md.

Used by Obsidian's Front Matter Title community plugin to disambiguate
homonymous nodes (every project has its `context.md` and `history.md`;
without `display`, the graph view collapses them into indistinguishable
nodes labelled "context" and "history").

Idempotent: a file already carrying a `display` value is left untouched
unless --force is passed. Dry-run by default.

Usage:
    python scripts/inject-display-frontmatter.py --vault /path/to/vault
    python scripts/inject-display-frontmatter.py --vault /path/to/vault --apply
    python scripts/inject-display-frontmatter.py --vault /path/to/vault --apply --force
"""

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n(.*)$", re.DOTALL)
KEY_VALUE_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*?)\s*$")
ARCHIVE_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-(\d{2}h\d{2}))?-(.+?)\.md$")
BRANCH_FOLDER_RE = re.compile(r"^(.+)-branches$")


def parse_frontmatter(text: str):
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    raw_fm = m.group(1)
    body = m.group(2)
    fields: dict[str, str] = {}
    for line in raw_fm.splitlines():
        if not line or line.startswith(" ") or line.startswith("\t") or line.startswith("-"):
            continue
        km = KEY_VALUE_RE.match(line)
        if km:
            fields[km.group(1)] = km.group(2)
    return fields, raw_fm, body


def write_atomic(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def inject_field(raw_fm: str, key: str, value: str) -> str:
    """Insert key: value at the end of the frontmatter."""
    quoted = f'"{value}"' if any(ch in value for ch in [':', '#', '"', "'"]) or value != value.strip() else value
    if quoted == value:
        line = f"{key}: {value}"
    else:
        # Escape internal quotes
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        line = f'{key}: "{escaped}"'
    return raw_fm.rstrip("\n") + "\n" + line + "\n"


def replace_field(raw_fm: str, key: str, value: str) -> str:
    """Replace an existing key: line with the new value."""
    pattern = re.compile(rf"^({re.escape(key)}\s*:).*$", re.MULTILINE)
    if any(ch in value for ch in [':', '#', '"', "'"]) or value != value.strip():
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        replacement = rf'\1 "{escaped}"'
    else:
        replacement = rf"\1 {value}"
    return pattern.sub(replacement, raw_fm, count=1)


def derive_display(path: Path, vault: Path, fields: dict[str, str]) -> str | None:
    """
    Compute the canonical display value for a vault file based on its path
    and frontmatter. Returns None if no convention applies (the file should
    keep its filename-based default label).
    """
    rel = path.relative_to(vault)
    parts = rel.parts
    name = path.name
    stem = path.stem

    if name == "index.md" and len(parts) == 1:
        return "vault index"

    # Topology files
    if len(parts) >= 3 and parts[0] == "99-meta" and parts[1] == "repo-topology":
        # Branch topology: 99-meta/repo-topology/{slug}-branches/{branch-san}.md
        if len(parts) >= 4:
            mb = BRANCH_FOLDER_RE.match(parts[2])
            if mb:
                slug = mb.group(1)
                branch_san = stem
                # Try to recover the original branch name from frontmatter
                branch = fields.get("branch", "").strip().strip('"').strip("'") or branch_san
                return f"{slug} — topology ({branch})"
        # Main topology: 99-meta/repo-topology/{slug}.md
        if len(parts) == 3:
            slug = stem
            return f"{slug} — topology"

    # Project / domain context.md, history.md, archives
    if len(parts) >= 4 and parts[0] == "10-episodes" and parts[1] in ("projects", "domains"):
        slug = parts[2]
        if name == "context.md" and len(parts) == 4:
            return f"{slug} — context"
        if name == "history.md" and len(parts) == 4:
            return f"{slug} — history"
        if len(parts) >= 5 and parts[3] == "archives":
            am = ARCHIVE_FILENAME_RE.match(name)
            if am:
                date = am.group(1)
                # Extract short subject from the rest (after slug-)
                rest = am.group(3)
                # Try to drop the leading slug part if present
                rest_clean = rest
                if rest.startswith(slug + "-"):
                    rest_clean = rest[len(slug) + 1:]
                short = rest_clean.replace("-", " ")[:50]
                return f"{slug} — {date} {short}"

    # Transverse atoms — derive from zone
    zone = fields.get("zone", "").strip().strip('"').strip("'")
    type_field = fields.get("type", "").strip().strip('"').strip("'")
    if zone == "principles":
        return f"principle: {stem}"
    if zone == "knowledge":
        suffix = type_field or "knowledge"
        return f"{suffix}: {stem}"
    if zone == "goals":
        return f"goal: {stem}"
    if zone == "people":
        return f"person: {stem}"
    if zone == "procedures":
        return f"procedure: {stem}"
    if zone == "cognition":
        return f"cognition: {stem}"
    if zone == "inbox":
        return f"inbox: {stem}"

    return None


def process_file(path: Path, vault: Path, force: bool, dry_run: bool) -> tuple[bool, str]:
    text = path.read_text(encoding="utf-8")
    parsed = parse_frontmatter(text)
    if not parsed:
        return False, "no frontmatter"
    fields, raw_fm, body = parsed
    existing = fields.get("display", "").strip().strip('"').strip("'")

    target = derive_display(path, vault, fields)
    if target is None:
        return False, "no convention applies"

    if existing == target:
        return False, "already has correct display"

    if existing and not force:
        return False, f"has custom display '{existing}' (use --force to override)"

    if "display" in fields:
        new_fm = replace_field(raw_fm, "display", target)
        action = f"updated display: '{existing}' -> '{target}'"
    else:
        new_fm = inject_field(raw_fm, "display", target)
        action = f"injected display: '{target}'"

    if not dry_run:
        write_atomic(path, f"---\n{new_fm}---\n{body}")
    return True, action


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    ap.add_argument("--force", action="store_true", help="Override existing display values that don't match the convention")
    args = ap.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.exists():
        print(f"Error: vault not found: {vault}", file=sys.stderr)
        return 1
    dry_run = not args.apply

    print(f"[i] Vault : {vault}")
    print(f"[i] Mode  : {'APPLY' if args.apply else 'DRY-RUN'}{'  --force' if args.force else ''}")
    print()

    changed = unchanged = 0
    for md in sorted(vault.rglob("*.md")):
        if ".obsidian" in md.parts or ".trash" in md.parts:
            continue
        if md.suffix in (".excalidraw.md", ".canvas", ".base"):
            continue
        modified, msg = process_file(md, vault, args.force, dry_run)
        rel = md.relative_to(vault)
        if modified:
            changed += 1
            print(f"[*] {rel} — {msg}")
        else:
            unchanged += 1

    print()
    print(f"[=] {changed} file(s) {'would be' if dry_run else ''} modified, {unchanged} unchanged.")
    if dry_run and changed > 0:
        print("    Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
