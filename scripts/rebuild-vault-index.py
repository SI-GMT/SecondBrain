#!/usr/bin/env python3
"""
rebuild-vault-index.py — regenerate {vault}/index.md from filesystem scan + i18n strings.

Sections produced (in user's language, from core/i18n/strings.yaml):
  - Zones (links to each numbered zone)
  - Projects
  - Domains
  - Archives (across all projects/domains, sorted by date desc)
  - Principles (grouped by attached project; orphans under "(unattached)")
  - Knowledge   (idem)
  - Goals       (idem)
  - People      (idem)

Language resolution priority:
  1. --language argument
  2. {language} field of {vault}/.. memory-kit.json files
  3. Fallback "en"

Usage:
    python scripts/rebuild-vault-index.py --vault /path/to/vault [--language fr] [--dry-run]
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

ZONES = [
    '00-inbox', '10-episodes', '20-knowledge', '30-procedures',
    '40-principles', '50-goals', '60-people', '70-cognition', '99-meta',
]

# ============================================================
# Helpers
# ============================================================

def parse_frontmatter(text):
    """Return (dict, body) from a markdown file with YAML frontmatter."""
    if not text.startswith('---'):
        return {}, text
    end = text.find('\n---', 4)
    if end == -1:
        return {}, text
    fm_block = text[4:end]
    body = text[end + 4:].lstrip('\n')
    try:
        fm = yaml.safe_load(fm_block) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body

def detect_language(vault: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    # Try ~/.claude/memory-kit.json then siblings
    home = Path.home()
    for cli in ['.claude', '.gemini', '.codex', '.vibe']:
        cfg = home / cli / 'memory-kit.json'
        if cfg.exists():
            try:
                data = json.loads(cfg.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                continue
            if data.get('vault') and Path(data['vault']).resolve() == vault.resolve():
                lang = data.get('language')
                if lang:
                    return lang
    return 'en'

def load_strings(repo_root: Path, language: str) -> dict:
    """Load strings.yaml; return the section for `language`, falling back to 'en'."""
    yaml_path = repo_root / 'core' / 'i18n' / 'strings.yaml'
    if not yaml_path.exists():
        print(f"Warning: {yaml_path} not found, using English defaults", file=sys.stderr)
        return _builtin_en_strings()
    data = yaml.safe_load(yaml_path.read_text(encoding='utf-8'))
    en = data.get('en', {})
    lang_data = data.get(language, {})
    # Merge with EN as fallback (deep merge for index/context/etc.)
    return _deep_merge(en, lang_data)

def _builtin_en_strings():
    return {
        'index': {
            'title': 'Vault SecondBrain v0.5 — Index',
            'intro': 'Entry point of the second brain.',
            'section_zones': 'Zones',
            'section_projects': 'Projects',
            'section_domains': 'Domains',
            'section_archives': 'Archives',
            'section_principles': 'Principles',
            'section_knowledge': 'Knowledge',
            'section_goals': 'Goals',
            'section_people': 'People',
            'empty_projects': '(none yet)',
            'empty_domains': '(none yet)',
            'empty_archives': '(none yet)',
            'empty_principles': '(none yet)',
            'empty_knowledge': '(none yet)',
            'empty_goals': '(none yet)',
            'empty_people': '(none yet)',
            'unattached_label': '(unattached)',
            'zone_labels': {z: '' for z in ZONES},
        }
    }

def _deep_merge(base, override):
    """Recursive merge: override wins, falls back to base."""
    if not isinstance(override, dict):
        return override if override is not None else base
    result = dict(base) if isinstance(base, dict) else {}
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

# ============================================================
# Vault scan
# ============================================================

def list_projects_or_domains(vault: Path, kind: str) -> list[str]:
    """kind = 'projects' or 'domains'. Returns list of slugs."""
    base = vault / '10-episodes' / kind
    if not base.exists():
        return []
    return sorted([d.name for d in base.iterdir() if d.is_dir()])

def list_archives_for(vault: Path, kind: str, slug: str) -> list[Path]:
    base = vault / '10-episodes' / kind / slug / 'archives'
    if not base.exists():
        return []
    return sorted(base.glob('*.md'))

def scan_atoms(vault: Path, zone: str) -> list[tuple[Path, dict]]:
    """Scan a zone (40-principles, 20-knowledge, 50-goals, 60-people) and
    return a list of (path, frontmatter)."""
    base = vault / zone
    if not base.exists():
        return []
    out = []
    for f in sorted(base.rglob('*.md')):
        if any(p.startswith('.') for p in f.parts):
            continue
        try:
            content = f.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        fm, _ = parse_frontmatter(content)
        out.append((f, fm))
    return out

def group_atoms_by_project(atoms: list[tuple[Path, dict]]) -> dict[str | None, list[Path]]:
    """Return {project_slug -> [paths]} ; None key for unattached atoms."""
    grouped: dict[str | None, list[Path]] = {}
    for path, fm in atoms:
        project = fm.get('project') or fm.get('domain')
        grouped.setdefault(project, []).append(path)
    return grouped

# ============================================================
# Index rendering
# ============================================================

def render_index(vault: Path, lang: str, strings: dict) -> str:
    s = strings.get('index', {})
    today = _today()

    lines = [
        '---',
        f'date: {today}',
        'zone: meta',
        'type: index',
        'display: "vault index"',
        'tags: [zone/meta, type/index]',
        '---',
        '',
        f'# {s.get("title", "Vault Index")}',
        '',
        s.get('intro', ''),
        '',
    ]

    # Section: Zones
    # v0.7.3 : on linke vers {zone}/index.md (existe physiquement, voir
    # ensure_zone_indexes) au lieu de ({zone}/) qui generait des noeuds
    # fantomes dans le graph Obsidian + des MD vides crees au clic.
    lines.append(f"## {s.get('section_zones', 'Zones')}")
    lines.append('')
    zone_labels = s.get('zone_labels', {})
    for z in ZONES:
        label = zone_labels.get(z, '')
        if label:
            lines.append(f'- [{z}]({z}/index.md) — {label}')
        else:
            lines.append(f'- [{z}]({z}/index.md)')
    lines.append('')

    # Section: Projects
    projects = list_projects_or_domains(vault, 'projects')
    lines.append(f"## {s.get('section_projects', 'Projects')}")
    lines.append('')
    if projects:
        for slug in projects:
            lines.append(f'- [{slug}](10-episodes/projects/{slug}/history.md)')
    else:
        lines.append(s.get('empty_projects', '(none yet)'))
    lines.append('')

    # Section: Domains
    domains = list_projects_or_domains(vault, 'domains')
    lines.append(f"## {s.get('section_domains', 'Domains')}")
    lines.append('')
    if domains:
        for slug in domains:
            lines.append(f'- [{slug}](10-episodes/domains/{slug}/history.md)')
    else:
        lines.append(s.get('empty_domains', '(none yet)'))
    lines.append('')

    # Section: Archives (sorted by filename desc — filename starts with date)
    all_archives: list[tuple[str, str, Path]] = []  # (slug, kind, path)
    for slug in projects:
        for a in list_archives_for(vault, 'projects', slug):
            all_archives.append((slug, 'projects', a))
    for slug in domains:
        for a in list_archives_for(vault, 'domains', slug):
            all_archives.append((slug, 'domains', a))
    all_archives.sort(key=lambda t: t[2].name, reverse=True)

    lines.append(f"## {s.get('section_archives', 'Archives')}")
    lines.append('')
    if all_archives:
        for slug, kind, path in all_archives:
            rel = path.relative_to(vault).as_posix()
            lines.append(f'- [{path.stem}]({rel})')
    else:
        lines.append(s.get('empty_archives', '(none yet)'))
    lines.append('')

    # Section: Health (v0.7.3) — list of mem-health-scan/repair reports.
    # Renders only if 99-meta/health/ exists and contains at least one report.
    health_dir = vault / '99-meta' / 'health'
    if health_dir.exists():
        health_reports = sorted(
            [p for p in health_dir.glob('*.md') if p.is_file()],
            key=lambda p: p.name,
            reverse=True,
        )
        if health_reports:
            lines.append('## Health')
            lines.append('')
            for p in health_reports:
                rel = p.relative_to(vault).as_posix()
                lines.append(f'- [{p.stem}]({rel})')
            lines.append('')

    # Sections: Principles / Knowledge / Goals / People — grouped by project
    section_map = [
        ('40-principles', 'section_principles', 'empty_principles'),
        ('20-knowledge',  'section_knowledge',  'empty_knowledge'),
        ('50-goals',      'section_goals',      'empty_goals'),
        ('60-people',     'section_people',     'empty_people'),
    ]
    unattached_label = s.get('unattached_label', '(unattached)')
    for zone, section_key, empty_key in section_map:
        atoms = scan_atoms(vault, zone)
        section_title = s.get(section_key, zone)
        lines.append(f'## {section_title}')
        lines.append('')
        if not atoms:
            lines.append(s.get(empty_key, '(none yet)'))
            lines.append('')
            continue
        grouped = group_atoms_by_project(atoms)
        # Order: known project slugs first (alphabetical), then unattached
        attached = sorted(k for k in grouped.keys() if k)
        for project in attached:
            lines.append(f'### {project}')
            lines.append('')
            for p in sorted(grouped[project], key=lambda x: x.name):
                rel = p.relative_to(vault).as_posix()
                lines.append(f'- [{p.stem}]({rel})')
            lines.append('')
        if None in grouped:
            lines.append(f'### {unattached_label}')
            lines.append('')
            for p in sorted(grouped[None], key=lambda x: x.name):
                rel = p.relative_to(vault).as_posix()
                lines.append(f'- [{p.stem}]({rel})')
            lines.append('')

    return '\n'.join(lines)

def _today():
    from datetime import date
    return date.today().isoformat()

# ============================================================
# Zone indexes (v0.7.3)
# ============================================================
# Each {zone}/index.md is a zone hub: a real markdown file with frontmatter
# (zone: meta, type: zone-index, display: "{zone} — index") that the vault
# root index.md links to. Replaces the old `[{zone}]({zone}/)` that produced
# ghost graph nodes + empty MDs at the vault root when clicked in Obsidian.

def render_zone_index(zone: str, lang: str, strings: dict) -> str:
    s = strings.get('index', {})
    zone_labels = s.get('zone_labels', {})
    label = zone_labels.get(zone, '')
    today = _today()

    body_intro = (
        f'Hub of the `{zone}/` zone — {label}.' if label
        else f'Hub of the `{zone}/` zone.'
    )

    lines = [
        '---',
        f'date: {today}',
        'zone: meta',
        'type: zone-index',
        f'display: "{zone} — index"',
        f'tags: [zone/meta, type/zone-index, target-zone/{zone}]',
        '---',
        '',
        f'# {zone} — Index',
        '',
        body_intro,
        '',
        f'> Back to [[index|vault index]].',
        '',
    ]
    return '\n'.join(lines)

def ensure_zone_indexes(vault: Path, lang: str, strings: dict, dry_run: bool) -> list[str]:
    """Create {zone}/index.md for each zone if missing. Idempotent: never
    overwrites an existing file (a user may have customised the hub).
    Returns the list of zones for which an index was created."""
    created = []
    for zone in ZONES:
        zone_dir = vault / zone
        if not zone_dir.exists():
            # The zone itself does not exist yet (vault not scaffolded for
            # this zone). Skip silently — scaffold-vault.py should create it
            # before rebuild is called.
            continue
        idx_path = zone_dir / 'index.md'
        if idx_path.exists():
            continue
        content = render_zone_index(zone, lang, strings)
        if dry_run:
            print(f"[dry-run] Would create {idx_path}")
        else:
            tmp = idx_path.with_suffix('.md.tmp')
            tmp.write_text(content, encoding='utf-8', newline='\n')
            tmp.replace(idx_path)
            print(f"[OK] Created zone index {zone}/index.md")
        created.append(zone)
    return created

# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Regenerate vault index.md from filesystem scan + i18n')
    parser.add_argument('--vault', required=True, help='Absolute path of the vault')
    parser.add_argument('--language', default=None, help='Override conversational language (en/fr/es/de/ru)')
    parser.add_argument('--dry-run', action='store_true', help='Print to stdout instead of writing')
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"Vault not found: {vault}", file=sys.stderr)
        sys.exit(1)

    repo_root = Path(__file__).resolve().parent.parent

    language = detect_language(vault, args.language)
    print(f"[i] Vault    : {vault}")
    print(f"[i] Language : {language}")

    strings = load_strings(repo_root, language)

    # v0.7.3: ensure each zone has its hub index.md (created if missing).
    # Done before rendering the root index so its links never dangle.
    ensure_zone_indexes(vault, language, strings, args.dry_run)

    content = render_index(vault, language, strings)

    target = vault / 'index.md'
    if args.dry_run:
        print(content)
        print(f"\n[dry-run] Would write {target}")
    else:
        # Atomic write UTF-8 LF
        tmp = target.with_suffix('.md.tmp')
        tmp.write_text(content, encoding='utf-8', newline='\n')
        tmp.replace(target)
        print(f"[OK] Wrote {target}")


if __name__ == '__main__':
    main()
