#!/usr/bin/env python3
"""
scaffold-vault.py — bootstrap the v0.5 brain-centric folder structure.

Idempotent. Creates the 9 root zones with their base subfolders, plus a minimal
.gitignore at the vault root. Delegates index.md generation to
rebuild-vault-index.py so the i18n strings are honored consistently.

Use cases:
  - First install: deploy.{sh,ps1} calls this when the target vault is empty.
  - Bootstrap a test vault for iterating on skills.

Does NOT migrate an existing v0.4 vault — see migrate-vault-v05-to-v052.py.

Usage:
    python scripts/scaffold-vault.py --vault /path/to/vault [--language fr] [--force]
"""

import argparse
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 9 zones racines + sous-dossiers de base (alignés sur scaffold-vault-v0.5.ps1)
ZONES = {
    '00-inbox':      [],
    '10-episodes':   ['projects', 'domains'],
    '20-knowledge':  ['business', 'tech', 'life', 'methods'],
    '30-procedures': ['work', 'personal'],
    '40-principles': ['work', 'personal'],
    '50-goals':      [
        'personal/life', 'personal/health', 'personal/family', 'personal/finance',
        'work/career', 'work/projects',
    ],
    '60-people':     [
        'work/colleagues', 'work/clients', 'work/partners',
        'personal/family', 'personal/friends', 'personal/acquaintances',
    ],
    '70-cognition':  ['schemas', 'metaphors', 'moodboards', 'sketches'],
    '99-meta':       [],
}

GITIGNORE_CONTENT = """# Vault SecondBrain — not versioned by default.
# If you want to version it, remove this file but think twice about personal data.
*
"""

# ANSI colors (skipped on non-tty)
def _c(code, msg):
    if sys.stdout.isatty():
        return f"\033[{code}m{msg}\033[0m"
    return msg

def _step(msg):  print(_c('0;36', msg))
def _ok(msg):    print(_c('0;32', f"  [OK] {msg}"))
def _skip(msg):  print(_c('0;90', f"  [--] {msg}"))
def _warn(msg):  print(_c('0;33', f"  [!]  {msg}"))


def scaffold_zones(vault: Path, force: bool) -> int:
    """Create zones + subfolders. Return number of dirs created."""
    created = 0
    for zone, subs in ZONES.items():
        zone_path = vault / zone
        if zone_path.exists():
            if force:
                import shutil
                shutil.rmtree(zone_path)
                zone_path.mkdir(parents=True)
                _ok(f"Zone {zone} reset (--force)")
                created += 1
            else:
                _skip(f"Zone {zone} already present")
        else:
            zone_path.mkdir(parents=True)
            _ok(f"Zone {zone} created")
            created += 1
        for sub in subs:
            sub_path = zone_path / sub
            if not sub_path.exists():
                sub_path.mkdir(parents=True)
                _ok(f"  Subfolder {zone}/{sub} created")
                created += 1
    return created


def write_gitignore(vault: Path) -> bool:
    gi = vault / '.gitignore'
    if gi.exists():
        _skip(".gitignore already present")
        return False
    gi.write_text(GITIGNORE_CONTENT, encoding='utf-8', newline='\n')
    _ok(".gitignore created (vault unversioned by default)")
    return True


def generate_index(vault: Path, language: str | None, repo_root: Path) -> bool:
    """Delegate to rebuild-vault-index.py to honor i18n strings."""
    rebuild = repo_root / 'scripts' / 'rebuild-vault-index.py'
    if not rebuild.exists():
        _warn(f"rebuild-vault-index.py not found at {rebuild} — skipping index.md")
        return False
    cmd = [sys.executable, str(rebuild), '--vault', str(vault)]
    if language:
        cmd += ['--language', language]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as e:
        _warn(f"index.md generation failed: {e}")
        return False
    if result.returncode != 0:
        _warn(f"rebuild-vault-index.py exit {result.returncode}: {result.stderr.strip()}")
        return False
    _ok("index.md generated (i18n via rebuild-vault-index.py)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Bootstrap v0.5 vault structure.")
    parser.add_argument('--vault', required=True, help="Absolute path to the vault directory.")
    parser.add_argument('--language', help="Language code for the seed index.md (en, fr, es, de, ru). Auto-detected from memory-kit.json if absent.")
    parser.add_argument('--force', action='store_true', help="Reset each zone if it already exists. DESTRUCTIVE.")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    repo_root = Path(__file__).resolve().parent.parent

    _step(f"Scaffold vault SecondBrain v0.5 -> {vault}")

    if not vault.exists():
        vault.mkdir(parents=True)
        _ok(f"Target directory created: {vault}")
    else:
        _skip(f"Target directory already present: {vault}")

    scaffold_zones(vault, args.force)
    write_gitignore(vault)
    generate_index(vault, args.language, repo_root)

    print()
    _step("=== Scaffold complete ===")
    print(f"Vault : {vault}")


if __name__ == '__main__':
    main()
