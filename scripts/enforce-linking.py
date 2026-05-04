#!/usr/bin/env python3
"""
enforce-linking.py — retroactively enforce the "zero orphan atom" linking
invariant on an existing vault.

For every project and domain in 10-episodes/, ensures that:
  - context.md carries the localized intro line with a link to history.md
  - history.md carries the localized intro line with a link to context.md

Idempotent: if the intro line is already present, leaves the file untouched.

Language is read from the user's memory-kit.json (matching this vault path),
falling back to English if not found. Lines are sourced from
core/i18n/strings.yaml (`{language}.context.intro_with_links` and
`{language}.history.intro_with_links`).

Usage:
    python scripts/enforce-linking.py --vault /path/to/vault [--language fr] [--dry-run]
"""

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import yaml
except ImportError:
    print("Error: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)

# ============================================================
# Helpers
# ============================================================

def detect_language(vault: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    home = Path.home()
    for cli in ['.claude', '.gemini', '.codex', '.vibe']:
        cfg = home / cli / 'memory-kit.json'
        if not cfg.exists():
            continue
        try:
            data = json.loads(cfg.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            continue
        if data.get('vault') and Path(data['vault']).resolve() == vault.resolve():
            lang = data.get('language')
            if lang:
                return lang
    return 'en'

def load_intro_lines(repo_root: Path, language: str) -> tuple[str, str]:
    yaml_path = repo_root / 'core' / 'i18n' / 'strings.yaml'
    if not yaml_path.exists():
        return _default_intros()
    data = yaml.safe_load(yaml_path.read_text(encoding='utf-8'))
    en = data.get('en', {})
    lang_data = data.get(language, {})
    ctx = (lang_data.get('context', {}).get('intro_with_links')
           or en.get('context', {}).get('intro_with_links')
           or _default_intros()[0])
    hist = (lang_data.get('history', {}).get('intro_with_links')
            or en.get('history', {}).get('intro_with_links')
            or _default_intros()[1])
    return ctx, hist

def _default_intros():
    return (
        '> Mutable snapshot of the project. See also: [history](history.md) · [archives/](archives/)',
        '> Chronological session log. See also: [context](context.md)',
    )

# Detect a pre-existing intro line (any language) so we don't duplicate.
# Heuristic: a line starting with `> ` that contains a markdown link to
# history.md, context.md, or archives/.
INTRO_PATTERN = re.compile(
    r'^>\s+.*\[(?:[^]]+)\]\((?:history\.md|context\.md|archives/)\)',
    re.MULTILINE,
)

def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_block_with_fences, body)."""
    if not text.startswith('---'):
        return '', text
    end = text.find('\n---', 4)
    if end == -1:
        return '', text
    fm = text[:end + 4]  # include trailing ---
    body = text[end + 4:].lstrip('\n')
    return fm, body

def insert_intro(text: str, intro_line: str) -> tuple[str, bool]:
    """Insert intro_line right after frontmatter if not already there.
    Returns (new_text, changed)."""
    fm, body = split_frontmatter(text)

    # If body already has an intro callout pointing to context/history/archives,
    # rewrite it to the canonical localized line. Otherwise, prepend.
    if INTRO_PATTERN.search(body):
        new_body = INTRO_PATTERN.sub(intro_line, body, count=1)
        if new_body == body:
            return text, False
        return _join(fm, new_body), True

    new_body = intro_line + '\n\n' + body if body.strip() else intro_line + '\n'
    return _join(fm, new_body), True

def _join(fm: str, body: str) -> str:
    if not fm:
        return body
    return fm + '\n\n' + body

def write_utf8_lf(path: Path, content: str):
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    path.write_text(content, encoding='utf-8', newline='\n')

# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Enforce zero-orphan-atom linking on a vault')
    parser.add_argument('--vault', required=True, help='Absolute path of the vault')
    parser.add_argument('--language', default=None, help='Override language (en/fr/es/de/ru)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without writing')
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"Vault not found: {vault}", file=sys.stderr)
        sys.exit(1)

    repo_root = Path(__file__).resolve().parent.parent
    language = detect_language(vault, args.language)
    ctx_intro, hist_intro = load_intro_lines(repo_root, language)

    print(f"[i] Vault    : {vault}")
    print(f"[i] Language : {language}")
    print(f"[i] context.md intro: {ctx_intro}")
    print(f"[i] history.md intro: {hist_intro}")
    print()

    targets: list[tuple[Path, str]] = []  # (path, intro)
    for kind in ('projects', 'domains'):
        base = vault / '10-episodes' / kind
        if not base.exists():
            continue
        for slug_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            ctx = slug_dir / 'context.md'
            hist = slug_dir / 'history.md'
            if ctx.exists():
                targets.append((ctx, ctx_intro))
            if hist.exists():
                targets.append((hist, hist_intro))

    patched = 0
    skipped = 0
    for path, intro in targets:
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            print(f"  [!]  non-UTF-8, skip: {path.relative_to(vault)}")
            continue
        new_content, changed = insert_intro(content, intro)
        rel = path.relative_to(vault).as_posix()
        if not changed:
            print(f"  [--] {rel} (already has intro)")
            skipped += 1
            continue
        if args.dry_run:
            print(f"  [OK] (dry) would patch {rel}")
        else:
            write_utf8_lf(path, new_content)
            print(f"  [OK] patched {rel}")
        patched += 1

    print()
    print(f"=== {'Would patch' if args.dry_run else 'Patched'} : {patched} ===")
    print(f"=== Skipped (already linked): {skipped} ===")
    if args.dry_run:
        print("Re-run without --dry-run to apply.")


if __name__ == '__main__':
    main()
