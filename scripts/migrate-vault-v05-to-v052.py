#!/usr/bin/env python3
"""
migrate-vault-v05-to-v052.py — migrate a v0.5 brain-centric vault from FR to EN schema.

Source state (v0.5 FR):
  40-principes/, 50-objectifs/, 60-personnes/
  10-episodes/projets/{slug}/{contexte,historique}.md
  10-episodes/domaines/{slug}/...
  */pro/, */perso/ subdirs
  Frontmatter values FR (kind: projet, scope: pro, source: vecu, type: principe…)
  Tags FR (projet/{slug}, kind/projet, scope/pro, type/principe…)
  Field names FR (collectif, contexte_origine, derniere_interaction, source_jalon)

Target state (v0.5.2 EN):
  40-principles/, 50-goals/, 60-people/
  10-episodes/projects/{slug}/{context,history}.md
  10-episodes/domains/{slug}/...
  */work/, */personal/ subdirs (and full lexicon: business/life/methods/career/...)
  Frontmatter values EN (kind: project, scope: work, source: lived, type: principle…)
  Tags EN (project/{slug}, kind/project, scope/work, type/principle…)
  Field names EN (collective, context_origin, last_interaction, source_milestone)
  index.md at the vault root (renamed from 99-meta/_index.md)

Usage:
    python scripts/migrate-vault-v05-to-v052.py --vault /path/to/vault [--apply]
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

# Force UTF-8 on stdout/stderr (Windows console defaults to CP1252)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# Mapping tables
# ============================================================

# Folder renames — applied from deepest to shallowest to avoid path collisions.
# Order matters: more specific paths first.
FOLDER_RENAMES_DEEP_FIRST = [
    # Deep specific first (within zones)
    ('50-objectifs/perso/vie',        '50-objectifs/personal/life'),
    ('50-objectifs/perso/sante',      '50-objectifs/personal/health'),
    ('50-objectifs/perso/famille',    '50-objectifs/personal/family'),
    ('50-objectifs/perso/finances',   '50-objectifs/personal/finance'),
    ('50-objectifs/pro/carriere',     '50-objectifs/work/career'),
    ('50-objectifs/pro/projets',      '50-objectifs/work/projects'),
    ('60-personnes/pro/collegues',    '60-personnes/work/colleagues'),
    ('60-personnes/pro/clients',      '60-personnes/work/clients'),
    ('60-personnes/pro/partenaires',  '60-personnes/work/partners'),
    ('60-personnes/perso/famille',    '60-personnes/personal/family'),
    ('60-personnes/perso/amis',       '60-personnes/personal/friends'),
    ('60-personnes/perso/connaissances', '60-personnes/personal/acquaintances'),
    # Generic pro/perso (after specifics, in any zone)
    # Handled by a generic walk later
]

# Single-segment renames applied after deep renames, then walked top-down.
SEGMENT_RENAMES = {
    # Top-level zone renames
    '40-principes':  '40-principles',
    '50-objectifs':  '50-goals',
    '60-personnes':  '60-people',
    # Inside 10-episodes
    'projets':       'projects',
    'domaines':      'domains',
    # Generic scope subdirs (anywhere)
    'pro':           'work',
    'perso':         'personal',
    # Inside 20-knowledge
    'metier':        'business',
    'methodes':      'methods',
    'vie':           'life',
    # Inside 70-cognition
    'metaphores':    'metaphors',
    # Inside 50-goals (post zone rename)
    'carriere':      'career',
    'sante':         'health',
    'famille':       'family',
    'finances':      'finance',
    # Inside 60-people (post zone rename)
    'collegues':     'colleagues',
    'partenaires':   'partners',
    'connaissances': 'acquaintances',
    'amis':          'friends',
}

# File renames inside any project/domain folder
FILE_RENAMES = {
    'contexte.md':   'context.md',
    'historique.md': 'history.md',
}

# Content substitutions — applied to every .md file in the vault.
# Order: most specific first.
CONTENT_PATTERNS = [
    # Frontmatter values (line-anchored when possible)
    (r'^kind: projet$',     'kind: project'),
    (r'^kind: domaine$',    'kind: domain'),
    (r'^scope: pro$',       'scope: work'),
    (r'^scope: perso$',     'scope: personal'),
    (r'^source: vecu$',     'source: lived'),
    (r'^type: principe$',   'type: principle'),
    (r'^type: objectif$',   'type: goal'),
    (r'^type: personne$',   'type: person'),
    (r'^type: fiche$',      'type: card'),
    (r'^type: synthese$',   'type: synthesis'),
    (r'^type: glossaire$',  'type: glossary'),
    (r'^type: metaphore$',  'type: metaphor'),
    (r'^type: taxonomie$',  'type: taxonomy'),
    (r'^type: regle$',      'type: rule'),
    # Inline values (no anchor)
    (r'\bkind: projet\b',   'kind: project'),
    (r'\bkind: domaine\b',  'kind: domain'),
    (r'\bscope: pro\b',     'scope: work'),
    (r'\bscope: perso\b',   'scope: personal'),
    (r'\bsource: vecu\b',   'source: lived'),
    # Tag namespaces (assume followed by / or end of token)
    (r'\bprojet/',          'project/'),
    (r'\bdomaine/',          'domain/'),
    (r'\bkind/projet\b',    'kind/project'),
    (r'\bkind/domaine\b',   'kind/domain'),
    (r'\bscope/pro\b',      'scope/work'),
    (r'\bscope/perso\b',    'scope/personal'),
    (r'\bsource/vecu\b',    'source/lived'),
    (r'\btype/principe\b',  'type/principle'),
    (r'\btype/objectif\b',  'type/goal'),
    (r'\btype/personne\b',  'type/person'),
    (r'\btype/fiche\b',     'type/card'),
    (r'\btype/synthese\b',  'type/synthesis'),
    (r'\btype/glossaire\b', 'type/glossary'),
    (r'\btype/metaphore\b', 'type/metaphor'),
    (r'\btype/taxonomie\b', 'type/taxonomy'),
    (r'\btype/regle\b',     'type/rule'),
    # Frontmatter field name renames (line-anchored to target YAML keys, not prose)
    (r'^projet:',                'project:'),
    (r'^domaine:',               'domain:'),
    (r'^collectif:',             'collective:'),
    (r'\bcollectif:',            'collective:'),
    (r'\bcontexte_origine\b',    'context_origin'),
    (r'\bderniere_interaction\b', 'last_interaction'),
    (r'\bsource_jalon\b',        'source_milestone'),
    # Other FR frontmatter keys observed in real vaults
    (r'^auteur:',                'author:'),
    (r'^derniere-session:',      'last-session:'),
    (r'^duree_estimee:',         'estimated_duration:'),
    (r'^echeance:',              'deadline:'),
    (r'^etapes:',                'steps:'),
    (r'^etat:',                  'state:'),
    (r'^heure:',                 'time:'),
    (r'^nom:',                   'name:'),
    (r'^organisation:',          'organization:'),
    (r'^outils:',                'tools:'),
    (r'^priorite:',              'priority:'),
    (r'^statut:',                'status:'),
    (r'^titre:',                 'title:'),
    (r'^valide_le:',             'validated_on:'),
    # Path references in markdown (links, examples)
    (r'10-episodes/projets/',  '10-episodes/projects/'),
    (r'10-episodes/domaines/', '10-episodes/domains/'),
    (r'40-principes/',         '40-principles/'),
    (r'50-objectifs/',         '50-goals/'),
    (r'60-personnes/',         '60-people/'),
    (r'cognition/metaphores',  'cognition/metaphors'),
    # Filenames in markdown text (mandatory: physical files are renamed, links would break)
    (r'\bcontexte\.md\b',   'context.md'),
    (r'\bhistorique\.md\b', 'history.md'),
    # 99-meta filenames
    (r'99-meta/regles-classement', '99-meta/classification-rules'),
    (r'99-meta/taxonomie-tags',    '99-meta/tag-taxonomy'),
    # NOTE: section headers like '## Projets' / '## Domaines' and other user-visible prose
    # are NOT patched — they follow the conversational language set in memory-kit.json
    # (resolved at write time via core/i18n/strings.yaml).
]

CONTENT_REGEX = [(re.compile(p, re.MULTILINE), r) for p, r in CONTENT_PATTERNS]

# ============================================================
# Helpers
# ============================================================

class Color:
    OK = '\033[92m'
    WARN = '\033[93m'
    ERR = '\033[91m'
    INFO = '\033[96m'
    GRAY = '\033[90m'
    RESET = '\033[0m'

def log(msg, color=Color.INFO):  print(f"{color}{msg}{Color.RESET}")
def ok(msg):    log(f"  [OK] {msg}", Color.OK)
def warn(msg):  log(f"  [!]  {msg}", Color.WARN)
def err(msg):   log(f"  [X]  {msg}", Color.ERR)
def step(msg):  log(msg, Color.INFO)
def skip(msg):  log(f"  [--] {msg}", Color.GRAY)

def write_utf8_lf(path: Path, content: str):
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    path.write_text(content, encoding='utf-8', newline='\n')

# ============================================================
# Phase 1 — Folder renames (deepest first)
# ============================================================

def rename_folders(vault: Path, dry_run: bool):
    step("\n> Folder renames (deepest first)")
    # Walk all directories, deepest first, and apply SEGMENT_RENAMES on basename.
    # We collect first, then rename from deepest to shallowest to avoid
    # path-shifts during iteration.
    all_dirs = []
    for d in vault.rglob('*'):
        if d.is_dir() and '.git' not in d.parts and '.obsidian' not in d.parts and '.trash' not in d.parts:
            all_dirs.append(d)
    # Sort by depth descending (deepest first)
    all_dirs.sort(key=lambda p: len(p.parts), reverse=True)

    renamed = 0
    for d in all_dirs:
        if not d.exists():
            continue  # already moved as part of an ancestor rename (shouldn't happen with deepest-first)
        new_name = SEGMENT_RENAMES.get(d.name)
        if not new_name:
            continue
        target = d.parent / new_name
        rel_src = d.relative_to(vault).as_posix()
        rel_dst = target.relative_to(vault).as_posix()
        if target.exists():
            warn(f"target already exists, skip: {rel_src} -> {rel_dst}")
            continue
        if dry_run:
            ok(f"(dry) {rel_src} -> {rel_dst}")
        else:
            d.rename(target)
            ok(f"{rel_src} -> {rel_dst}")
        renamed += 1
    return renamed

# ============================================================
# Phase 2 — File renames (contexte->context, historique->history, _index->index)
# ============================================================

def rename_files(vault: Path, dry_run: bool):
    step("\n> File renames (contexte/historique -> context/history)")
    renamed = 0
    for f in vault.rglob('*.md'):
        if '.git' in f.parts or '.obsidian' in f.parts or '.trash' in f.parts:
            continue
        new_name = FILE_RENAMES.get(f.name)
        if not new_name:
            continue
        target = f.parent / new_name
        rel_src = f.relative_to(vault).as_posix()
        rel_dst = target.relative_to(vault).as_posix()
        if target.exists():
            warn(f"target exists, skip: {rel_src} -> {rel_dst}")
            continue
        if dry_run:
            ok(f"(dry) {rel_src} -> {rel_dst}")
        else:
            f.rename(target)
            ok(f"{rel_src} -> {rel_dst}")
        renamed += 1

    # Special case: 99-meta/_index.md -> vault/index.md (move to root)
    legacy_index = vault / '99-meta' / '_index.md'
    new_index = vault / 'index.md'
    if legacy_index.exists() and not new_index.exists():
        if dry_run:
            ok(f"(dry) 99-meta/_index.md -> index.md (root)")
        else:
            legacy_index.rename(new_index)
            ok(f"99-meta/_index.md -> index.md (root)")
        renamed += 1
    elif legacy_index.exists() and new_index.exists():
        warn("Both 99-meta/_index.md and index.md exist — manual reconciliation required, skip")

    return renamed

# ============================================================
# Phase 3 — Content substitutions (every .md file)
# ============================================================

def patch_contents(vault: Path, dry_run: bool):
    step("\n> Content substitutions (frontmatter, tags, paths, links)")
    patched = 0
    scanned = 0
    for f in vault.rglob('*.md'):
        if '.git' in f.parts or '.obsidian' in f.parts or '.trash' in f.parts:
            continue
        scanned += 1
        try:
            content = f.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            warn(f"non-UTF-8 file, skip: {f.relative_to(vault).as_posix()}")
            continue
        new_content = content
        for regex, replacement in CONTENT_REGEX:
            new_content = regex.sub(replacement, new_content)
        if new_content != content:
            patched += 1
            rel = f.relative_to(vault).as_posix()
            if dry_run:
                ok(f"(dry) patched: {rel}")
            else:
                write_utf8_lf(f, new_content)
                ok(f"patched: {rel}")
    log(f"  {scanned} files scanned, {patched} patched", Color.GRAY)
    return patched

# ============================================================
# Phase 4 — Validation
# ============================================================

def validate_post(vault: Path):
    step("\n> Post-migration validation")
    leftover_dirs = []
    leftover_content = []

    # Check no FR directory names remain
    fr_segments = set(SEGMENT_RENAMES.keys())
    for d in vault.rglob('*'):
        if not d.is_dir() or '.git' in d.parts or '.obsidian' in d.parts or '.trash' in d.parts:
            continue
        if d.name in fr_segments:
            leftover_dirs.append(d.relative_to(vault).as_posix())

    # Check no FR content patterns remain (sample of strong indicators)
    fr_indicators = re.compile(
        r'\bkind: projet\b|\bkind: domaine\b|\bscope: pro\b|\bscope: perso\b|'
        r'\bsource: vecu\b|\btype: principe\b|\bcollectif:|\bcontexte_origine\b|'
        r'\b/projets/|\b/domaines/|\b40-principes/|\b50-objectifs/|\b60-personnes/'
    )
    for f in vault.rglob('*.md'):
        if '.git' in f.parts or '.obsidian' in f.parts or '.trash' in f.parts:
            continue
        try:
            content = f.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        if fr_indicators.search(content):
            leftover_content.append(f.relative_to(vault).as_posix())

    if leftover_dirs:
        err(f"FR folder names still present ({len(leftover_dirs)}):")
        for d in leftover_dirs[:10]:
            print(f"    - {d}")
        if len(leftover_dirs) > 10:
            print(f"    ... and {len(leftover_dirs) - 10} more")
    else:
        ok("No FR folder names remain")

    if leftover_content:
        warn(f"FR content indicators still present in {len(leftover_content)} files:")
        for f in leftover_content[:10]:
            print(f"    - {f}")
        if len(leftover_content) > 10:
            print(f"    ... and {len(leftover_content) - 10} more")
    else:
        ok("No FR content indicators remain")

    return len(leftover_dirs) == 0 and len(leftover_content) == 0

# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Migrate v0.5 vault from FR to EN schema (v0.5.2)')
    parser.add_argument('--vault', required=True, help='Absolute path of the vault to migrate')
    parser.add_argument('--apply', action='store_true', help='Apply the migration (default: dry-run)')
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.exists() or not vault.is_dir():
        err(f"Vault not found or not a directory: {vault}")
        sys.exit(1)

    log(f"\n=== Vault migration v0.5(FR) -> v0.5.2(EN) ===\n", Color.INFO)
    log(f"Vault : {vault}", Color.INFO)
    log(f"Mode  : {'APPLY' if args.apply else 'DRY-RUN (no write)'}",
        Color.OK if args.apply else Color.WARN)

    # Pre-flight: detect that this is indeed a v0.5 FR vault
    indicators = [vault / '40-principes', vault / '50-objectifs',
                  vault / '60-personnes', vault / '10-episodes' / 'projets']
    found = [str(p.relative_to(vault)) for p in indicators if p.exists()]
    if not found:
        warn("No FR v0.5 indicators found — vault may already be migrated or in a different schema.")
        if args.apply:
            err("Aborting --apply; re-run without to inspect.")
            sys.exit(1)
    else:
        ok(f"Detected FR indicators: {', '.join(found)}")

    n_dirs = rename_folders(vault, dry_run=not args.apply)
    n_files = rename_files(vault, dry_run=not args.apply)
    n_patched = patch_contents(vault, dry_run=not args.apply)

    if args.apply:
        clean = validate_post(vault)
    else:
        clean = None

    log(f"\n=== Migration {'applied' if args.apply else '(dry-run finished)'} ===", Color.OK)
    log(f"  Folders renamed   : {n_dirs}", Color.INFO)
    log(f"  Files renamed     : {n_files}", Color.INFO)
    log(f"  Files patched     : {n_patched}", Color.INFO)
    if args.apply:
        if clean:
            log("  Validation        : CLEAN", Color.OK)
        else:
            log("  Validation        : RESIDUAL FR (review manually)", Color.WARN)
    if not args.apply:
        log("\nTo apply for real: re-run with --apply", Color.WARN)


if __name__ == '__main__':
    main()
