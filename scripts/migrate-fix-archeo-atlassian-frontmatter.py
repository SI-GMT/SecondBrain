#!/usr/bin/env python3
"""
migrate-fix-archeo-atlassian-frontmatter.py — one-shot migration that fixes
two latent issues in archeo-atlassian archives produced before v0.7.3.1:

  1. **Unquoted [TAG] values** for keys like `confluence_page_title`,
     `jira_summary`. PyYAML reads `[DUST]` as a flow sequence opener and
     chokes on the whole frontmatter; safe_load returns `{}`. Tools that
     parse the frontmatter (mem-health-scan, mem-search filters, etc.)
     then report misleading findings (e.g. "missing display" on files that
     DO carry one). Fix: double-quote the value.

  2. **Collapsed delimiter newlines** introduced by the v0.7.3 ad-hoc
     `fix_atlassian_yaml.py` repair script. That script's
     `text = '---' + new_fm + body` concatenation lost the newline between
     the opening `---` and the first frontmatter line — producing
     `---date: 2026-04-21` instead of `---\ndate: 2026-04-21`. PyYAML is
     tolerant enough to still parse this (so `mem-health-scan` does not
     flag it as `malformed-frontmatter`), but Obsidian's frontmatter view
     and stricter parsers may misbehave. Fix: insert the missing newlines
     after the opening `---` and before the closing `---`.

This migration is run-once-and-forget but idempotent: re-running on a
vault where everything is already correct is a no-op.

Idempotent. Dry-run by default. Use --apply to actually write changes.

Usage:
    python scripts/migrate-fix-archeo-atlassian-frontmatter.py --vault /path/to/vault
    python scripts/migrate-fix-archeo-atlassian-frontmatter.py --vault /path/to/vault --apply
    python scripts/migrate-fix-archeo-atlassian-frontmatter.py --vault /path/to/vault --keys confluence_page_title,jira_summary --apply
"""

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Default keys known to carry [TAG]-style values from Confluence / Atlassian
DEFAULT_KEYS = (
    "confluence_page_title",
    "jira_summary",
    "jira_title",
)


def needs_quoting(value: str) -> bool:
    """Return True if the unquoted scalar value would trip a YAML parser."""
    v = value.strip()
    if not v:
        return False
    if v[0] in ("[", "]", "{", "}", "&", "*", "!", "|", ">", "%", "@", "`"):
        return True
    if "[" in v or "]" in v or "{" in v or "}" in v:
        return True
    if ": " in v:
        return True
    if v.endswith(":"):
        return True
    return False


def quote_yaml_value(value: str) -> str:
    """Double-quote a string for YAML, escaping internal backslashes and quotes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_atomic(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def process_file(path: Path, keys: tuple, dry_run: bool) -> tuple[bool, list[str]]:
    """Returns (modified, list of fixes). Idempotent.

    Fixes applied in order:
      1. Insert missing newline after opening `---` (collapsed delimiter).
      2. Insert missing newline after closing `---` (delimiter glued to body).
      3. Quote unquoted [TAG]-style values for the configured keys.
    """
    original = path.read_text(encoding="utf-8")
    if not original.startswith("---"):
        return False, []

    fixes: list[str] = []
    text = original

    # Fix 1: collapsed opening delimiter.
    # `---<X>` where <X> is anything except `\n` becomes `---\n<X>`.
    if len(text) > 3 and text[3] != "\n":
        text = "---\n" + text[3:]
        fixes.append("opened-delimiter-newline")

    # Locate end of frontmatter.
    end = text.find("\n---", 4)
    if end == -1:
        if fixes and not dry_run:
            write_atomic(path, text)
        return bool(fixes), fixes

    # Fix 2: missing newline after the closing `---`.
    # closing block in `text` starts at `end` and is "\n---<Y>...".
    # We expect <Y> to be `\n` (or end-of-file). If not, insert one.
    after_close = end + 4  # position right after the closing "---"
    if after_close < len(text) and text[after_close] != "\n":
        text = text[:after_close] + "\n" + text[after_close:]
        fixes.append("closing-delimiter-newline")
        # `end` does not move — the closing "---" position is unchanged.

    # Fix 3: quote unquoted [TAG] values for the configured keys.
    # The `[^\s"']` first-char class excludes whitespace too — without it,
    # `\s*` backtracks to 0 and the space after `:` matches the class,
    # producing false positives on already-quoted values.
    fm_start = 4
    fm_end = end
    fm = text[fm_start:fm_end]
    new_fm = fm
    for key in keys:
        pattern = re.compile(
            rf"^({re.escape(key)}):[ \t]+([^\s\"'].*?)\s*$",
            re.MULTILINE,
        )
        for m in pattern.finditer(fm):
            value = m.group(2)
            if not needs_quoting(value):
                continue
            quoted = quote_yaml_value(value)
            old_line = m.group(0)
            new_line = f"{key}: {quoted}"
            if old_line == new_line:
                continue
            new_fm = new_fm.replace(old_line, new_line, 1)
            fixes.append(f"quoted:{key}")

    if new_fm != fm:
        text = text[:fm_start] + new_fm + text[fm_end:]

    if not fixes:
        return False, []

    if text != original and not dry_run:
        write_atomic(path, text)
    return True, fixes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vault", required=True)
    ap.add_argument("--keys", default=",".join(DEFAULT_KEYS),
                    help=f"Comma-separated list of keys to quote. Default: {','.join(DEFAULT_KEYS)}")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = ap.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"Error: vault not found: {vault}", file=sys.stderr)
        return 2

    keys = tuple(k.strip() for k in args.keys.split(",") if k.strip())
    if not keys:
        print("Error: --keys cannot be empty", file=sys.stderr)
        return 2

    print(f"[i] Vault : {vault}")
    print(f"[i] Keys  : {', '.join(keys)}")
    print(f"[i] Mode  : {'APPLY' if args.apply else 'DRY-RUN'}")
    print()

    modified = unchanged = 0
    for md in sorted(vault.rglob("*.md")):
        if ".obsidian" in md.parts or ".trash" in md.parts:
            continue
        try:
            changed, patched = process_file(md, keys, dry_run=not args.apply)
        except Exception as e:
            print(f"[!] {md.relative_to(vault).as_posix()} — error: {e}", file=sys.stderr)
            continue
        if changed:
            print(f"[*] {md.relative_to(vault).as_posix()} — fixes: {', '.join(patched)}")
            modified += 1
        else:
            unchanged += 1

    print()
    print(f"[=] {modified} file(s) modified, {unchanged} unchanged.")
    if not args.apply and modified:
        print("    (dry-run: re-run with --apply to write changes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
