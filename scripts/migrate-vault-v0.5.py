#!/usr/bin/env python3
"""
migrate-vault-v0.5.py — migration d'un vault SecondBrain v0.4 vers la structure brain-centric v0.5.

Transforme :
  archives/                       → 10-episodes/projects/{slug}/archives/  (par projet)
  projets/{slug}/context.md     → 10-episodes/projects/{slug}/context.md
  projets/{slug}/history.md   → 10-episodes/projects/{slug}/history.md
  _index.md                       → index.md  (renommé + reste à la racine)

Crée les 9 zones racines vides si absentes.
Enrichit les frontmatters avec : zone, kind, scope, collectif, modality, type, tags v0.5.

Usage :
    python scripts/migrate-vault-v0.5.py --vault /path/to/vault [--apply] [--default-scope pro]

Sans --apply, mode dry-run par défaut : affiche le plan, n'écrit rien.
Avec --apply, exécute la migration. Backup automatique du vault avant.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ============================================================
# Constantes — structure v0.5
# ============================================================

ZONES_V05 = [
    '00-inbox',
    '10-episodes',
    '20-knowledge',
    '30-procedures',
    '40-principles',
    '50-goals',
    '60-people',
    '70-cognition',
    '99-meta',
]

ZONES_SUBDIRS = {
    '10-episodes': ['projects', 'domains'],
    '20-knowledge': ['business', 'tech', 'life', 'methods'],
    '30-procedures': ['work', 'personal'],
    '40-principles': ['work', 'personal'],
    '50-goals': [
        'personal/life', 'personal/health', 'personal/family', 'personal/finance',
        'work/career', 'work/projects'
    ],
    '60-people': [
        'work/colleagues', 'work/clients', 'work/partners',
        'personal/family', 'personal/friends', 'personal/acquaintances'
    ],
    '70-cognition': ['schemas', 'metaphors', 'moodboards', 'sketches'],
}

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

def log(msg, color=Color.INFO):
    print(f"{color}{msg}{Color.RESET}")

def ok(msg):    log(f"  [OK] {msg}", Color.OK)
def warn(msg):  log(f"  [!]  {msg}", Color.WARN)
def err(msg):   log(f"  [X]  {msg}", Color.ERR)
def step(msg):  log(msg, Color.INFO)
def skip(msg):  log(f"  [--] {msg}", Color.GRAY)

def parse_frontmatter(content):
    """Extrait le frontmatter YAML (entre --- ... ---) en dict simple. Retourne (frontmatter_dict, body_str)."""
    # Retirer le BOM UTF-8 si présent (legacy v0.4 avant durcissement encodage v0.3.1)
    if content.startswith('﻿'):
        content = content.lstrip('﻿')
    if not content.startswith('---'):
        return {}, content
    end = content.find('\n---', 4)
    if end == -1:
        return {}, content
    fm_block = content[4:end].strip()
    body = content[end + 4:].lstrip('\n')
    fm = {}
    for line in fm_block.split('\n'):
        if ':' in line:
            key, _, val = line.partition(':')
            key, val = key.strip(), val.strip()
            # Liste basique : [a, b, c]
            if val.startswith('[') and val.endswith(']'):
                val = [v.strip() for v in val[1:-1].split(',') if v.strip()]
            elif val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            fm[key] = val
    return fm, body

def render_frontmatter(fm):
    """Reconstruit un bloc frontmatter YAML. Listes en format inline [a, b, c]."""
    lines = ['---']
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        else:
            # Quote si contient des caractères spéciaux
            sval = str(v)
            if any(c in sval for c in [':', '#']) and not (sval.startswith('"') and sval.endswith('"')):
                sval = f'"{sval}"'
            lines.append(f"{k}: {sval}")
    lines.append('---')
    return '\n'.join(lines) + '\n'

def write_utf8_lf(path, content):
    """Écrit un fichier en UTF-8 sans BOM, fins de ligne LF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Forcer LF même si on est sur Windows
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    path.write_text(content, encoding='utf-8', newline='\n')

# ============================================================
# Étapes de migration
# ============================================================

def create_v05_structure(vault, dry_run):
    """Crée les 9 zones racines + sous-dossiers de base."""
    step("> Création de la structure v0.5")
    for zone in ZONES_V05:
        zpath = vault / zone
        if zpath.exists():
            skip(f"Zone {zone} existe deja")
        else:
            if not dry_run:
                zpath.mkdir(parents=True, exist_ok=True)
            ok(f"Zone {zone} {'creee' if not dry_run else '(dry-run, sera creee)'}")
        for sub in ZONES_SUBDIRS.get(zone, []):
            spath = zpath / sub
            if not spath.exists():
                if not dry_run:
                    spath.mkdir(parents=True, exist_ok=True)
                ok(f"  Sous-dossier {zone}/{sub} {'cree' if not dry_run else '(sera cree)'}")

def migrate_projects(vault, default_scope, dry_run):
    """Déplace projets/{slug}/ -> 10-episodes/projects/{slug}/ avec enrichissement frontmatter."""
    step("\n> Migration des projets")
    src_dir = vault / 'projets'
    if not src_dir.exists():
        skip("Aucun dossier projets/ a migrer")
        return []

    migrated_slugs = []
    for proj_dir in sorted(src_dir.iterdir()):
        if not proj_dir.is_dir():
            continue
        slug = proj_dir.name
        dst = vault / '10-episodes' / 'projects' / slug
        ok(f"Projet {slug} -> 10-episodes/projects/{slug}/")
        migrated_slugs.append(slug)

        if dry_run:
            continue

        dst.mkdir(parents=True, exist_ok=True)
        (dst / 'archives').mkdir(exist_ok=True)

        # Migrer context.md
        ctx_src = proj_dir / 'context.md'
        if ctx_src.exists():
            content = ctx_src.read_text(encoding='utf-8')
            fm, body = parse_frontmatter(content)
            fm.setdefault('zone', 'episodes')
            fm.setdefault('kind', 'project')
            fm.setdefault('slug', slug)
            fm.setdefault('scope', default_scope)
            fm.setdefault('collective', False)
            tags = fm.get('tags', [])
            if isinstance(tags, str):
                tags = [tags]
            for t in [f'zone/episodes', f'kind/project', f'project/{slug}', f'scope/{default_scope}']:
                if t not in tags:
                    tags.append(t)
            fm['tags'] = tags
            write_utf8_lf(dst / 'context.md', render_frontmatter(fm) + '\n' + body)

        # Migrer history.md (réécrire les liens relatifs vers archives/ qui ont changé)
        hist_src = proj_dir / 'history.md'
        if hist_src.exists():
            content = hist_src.read_text(encoding='utf-8')
            fm, body = parse_frontmatter(content)
            fm.setdefault('zone', 'episodes')
            fm.setdefault('kind', 'project')
            fm.setdefault('slug', slug)
            tags = fm.get('tags', [])
            if isinstance(tags, str):
                tags = [tags]
            for t in [f'zone/episodes', f'kind/project', f'project/{slug}']:
                if t not in tags:
                    tags.append(t)
            fm['tags'] = tags
            # Réécrire les liens : ../../archives/... -> archives/... (les archives sont maintenant dans le dossier projet)
            body = re.sub(r'\.\./\.\./archives/', 'archives/', body)
            write_utf8_lf(dst / 'history.md', render_frontmatter(fm) + '\n' + body)

        # features/ : migrer aussi si présent
        features_src = proj_dir / 'features'
        if features_src.exists():
            features_dst = dst / 'features'
            shutil.copytree(features_src, features_dst, dirs_exist_ok=True)
            ok(f"  features/ migre vers {dst}/features/")

    return migrated_slugs

def migrate_archives(vault, migrated_slugs, default_scope, dry_run):
    """Déplace archives/*.md -> 10-episodes/projects/{slug}/archives/ ou 00-inbox/ selon detection."""
    step("\n> Migration des archives")
    src_dir = vault / 'archives'
    if not src_dir.exists():
        skip("Aucun dossier archives/ a migrer")
        return 0, 0

    moved, inboxed = 0, 0
    for arch in sorted(src_dir.glob('*.md')):
        # Extraction du slug depuis le frontmatter ou le nom de fichier
        content = arch.read_text(encoding='utf-8')
        fm, body = parse_frontmatter(content)
        # Casse-insensible : `projet: SecondBrain` doit matcher slug `secondbrain`
        raw_projet = fm.get('projet', '')
        slug = None
        if raw_projet:
            for s in migrated_slugs:
                if s.lower() == str(raw_projet).lower():
                    slug = s
                    break
        if not slug:
            slug = extract_slug_from_filename(arch.name, migrated_slugs)

        if slug and slug in migrated_slugs:
            dst = vault / '10-episodes' / 'projects' / slug / 'archives' / arch.name
            kind = 'project'
        else:
            dst = vault / '00-inbox' / arch.name
            slug = None
            kind = None
            inboxed += 1

        # Enrichir le frontmatter
        fm.setdefault('zone', 'episodes' if slug else 'inbox')
        if slug:
            fm.setdefault('kind', kind)
            fm.setdefault('project', slug)
            fm.setdefault('scope', default_scope)
        fm.setdefault('collective', False)
        fm.setdefault('modality', 'left')
        fm.setdefault('source', fm.get('source', 'lived'))
        fm.setdefault('type', 'archive')
        tags = fm.get('tags', [])
        if isinstance(tags, str):
            tags = [tags]
        if slug:
            for t in [f'zone/episodes', f'kind/{kind}', f'project/{slug}', f'scope/{default_scope}',
                      f'modality/left', f'source/{fm["source"]}', 'type/archive']:
                if t not in tags:
                    tags.append(t)
        else:
            tags = ['zone/inbox', 'migration-v0.5-ambiguous']
        fm['tags'] = tags

        ok(f"{arch.name} -> {dst.relative_to(vault)}")
        if not dry_run:
            write_utf8_lf(dst, render_frontmatter(fm) + '\n' + body)
        moved += 1

    return moved, inboxed

def extract_slug_from_filename(filename, migrated_slugs):
    """Tente d'extraire un slug depuis un nom comme '2026-04-22-15h30-{slug}-...md'.
    Supporte les slugs multi-tirets (ex: mcp-iris-connector) en cherchant le préfixe le plus long.
    """
    # Capturer tout après l'horodatage (formats supportés : YYYY-MM-DD-HHhMM- ou YYYY-MM-DD-)
    m = re.match(r'^\d{4}-\d{2}-\d{2}(?:-\d{2}h\d{2})?-(.+?)\.md$', filename)
    if not m:
        return None
    after_date = m.group(1)
    # Chercher le slug le plus long qui matche le préfixe (case-insensible)
    best = None
    for slug in migrated_slugs:
        if after_date.lower() == slug.lower() or after_date.lower().startswith(slug.lower() + '-'):
            if best is None or len(slug) > len(best):
                best = slug
    return best

def migrate_index(vault, migrated_slugs, dry_run):
    """Régénère l'index à la racine du vault (v0.5 : index.md à la racine, plus dans 99-meta/)."""
    step("\n> Migration de l'index")
    src_legacy = vault / '_index.md'  # ancien nom v0.4
    dst = vault / 'index.md'

    if not src_legacy.exists() and not dst.exists():
        warn("Aucun _index.md a migrer — generation d'un index v0.5 vide")
        if not dry_run:
            generate_empty_index(vault, migrated_slugs)
        return

    ok(f"index a la racine (regeneration complete)")
    if dry_run:
        return

    # Régénération complète : on s'appuie sur les migrated_slugs et on scanne les nouveaux dossiers
    generate_empty_index(vault, migrated_slugs)

def generate_empty_index(vault, migrated_slugs):
    """Génère un index.md v0.5 propre."""
    today = datetime.now().strftime('%Y-%m-%d')
    archives_root = vault / '10-episodes' / 'projects'
    all_archives = []
    for proj in sorted(archives_root.iterdir()) if archives_root.exists() else []:
        if not proj.is_dir():
            continue
        for a in sorted((proj / 'archives').glob('*.md')) if (proj / 'archives').exists() else []:
            all_archives.append((proj.name, a))

    lines = [
        '---',
        f'date: {today}',
        'zone: meta',
        'type: index',
        'tags: [zone/meta, type/index]',
        '---',
        '',
        '# Vault SecondBrain v0.5 — Index',
        '',
        'Point d\'entree du second cerveau. Mis a jour automatiquement par les skills mem-* lors des operations d\'ecriture.',
        '',
        '## Zones',
        '',
    ]
    for z in ZONES_V05:
        lines.append(f'- [{z}]({z}/)')
    lines.append('')
    lines.append('## Projects')
    lines.append('')
    if migrated_slugs:
        for slug in sorted(migrated_slugs):
            lines.append(f'- [{slug}](10-episodes/projects/{slug}/history.md)')
    else:
        lines.append('(none yet)')
    lines.append('')
    lines.append('## Domains')
    lines.append('')
    lines.append('(none yet — use /mem-promote-domain to create one)')
    lines.append('')
    lines.append('## Archives')
    lines.append('')
    for slug, a in all_archives:
        rel = a.relative_to(vault)
        lines.append(f'- [{a.stem}]({rel.as_posix()})')
    lines.append('')

    write_utf8_lf(vault / 'index.md', '\n'.join(lines))

def cleanup_old_dirs(vault, dry_run):
    """Supprime les artefacts v0.4 après migration : archives/, projets/, _index.md (legacy).
    Le backup garantit qu'on peut récupérer en cas de pépin.
    """
    step("\n> Nettoyage des dossiers v0.4 (backup garanti)")
    for old in ['archives', 'projets']:
        path = vault / old
        if path.exists():
            ok(f"Suppression de {old}/ ({len(list(path.rglob('*.md')))} fichiers)")
            if not dry_run:
                shutil.rmtree(path)
    legacy_index = vault / '_index.md'
    if legacy_index.exists():
        ok(f"Suppression de _index.md legacy (régénéré en index.md à la racine)")
        if not dry_run:
            legacy_index.unlink()

def copy_doctrine(vault, doctrine_src, dry_run):
    """Copie le doc de cadrage v0.5 dans 99-meta/doctrine.md."""
    if not doctrine_src or not Path(doctrine_src).exists():
        skip("Doctrine source introuvable, skip copie")
        return
    dst = vault / '99-meta' / 'doctrine.md'
    ok(f"Doctrine -> 99-meta/doctrine.md")
    if not dry_run:
        content = Path(doctrine_src).read_text(encoding='utf-8')
        write_utf8_lf(dst, content)

def backup_vault(vault):
    """Crée un backup complet du vault avant migration. Retourne le chemin du backup."""
    timestamp = datetime.now().strftime('%Y-%m-%d-%Hh%M')
    backup = vault.parent / f"{vault.name}.backup-{timestamp}"
    if backup.exists():
        err(f"Backup existe deja : {backup}. Renomme-le ou supprime-le avant de relancer.")
        sys.exit(1)
    log(f"Backup vault: {vault} -> {backup}", Color.INFO)
    shutil.copytree(vault, backup)
    ok(f"Backup cree : {backup}")
    return backup

# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Migration vault SecondBrain v0.4 -> v0.5')
    parser.add_argument('--vault', required=True, help='Chemin absolu du vault à migrer')
    parser.add_argument('--apply', action='store_true', help='Applique la migration (sinon dry-run)')
    parser.add_argument('--default-scope', default='work', choices=['personal', 'work'],
                        help='Scope par défaut pour les contenus migrés (défaut: pro)')
    parser.add_argument('--doctrine', default=None,
                        help='Chemin vers brain-architecture-v0.5.md à copier dans 99-meta/doctrine.md')
    parser.add_argument('--no-backup', action='store_true', help='Skip le backup (déconseillé)')
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.exists():
        err(f"Vault introuvable : {vault}")
        sys.exit(1)
    if not vault.is_dir():
        err(f"Le vault doit être un dossier : {vault}")
        sys.exit(1)

    log(f"\n=== Migration vault SecondBrain v0.4 -> v0.5 ===\n", Color.INFO)
    log(f"Vault         : {vault}", Color.INFO)
    log(f"Default scope : {args.default_scope}", Color.INFO)
    log(f"Mode          : {'APPLY' if args.apply else 'DRY-RUN (no write)'}", Color.OK if args.apply else Color.WARN)

    if args.apply and not args.no_backup:
        log("\n> Backup obligatoire avant --apply", Color.INFO)
        backup_vault(vault)

    log("", Color.INFO)
    create_v05_structure(vault, dry_run=not args.apply)
    migrated_slugs = migrate_projects(vault, args.default_scope, dry_run=not args.apply)
    moved, inboxed = migrate_archives(vault, migrated_slugs, args.default_scope, dry_run=not args.apply)
    migrate_index(vault, migrated_slugs, dry_run=not args.apply)
    copy_doctrine(vault, args.doctrine, dry_run=not args.apply)
    if args.apply:
        cleanup_old_dirs(vault, dry_run=False)

    log(f"\n=== Migration {'effectuee' if args.apply else '(dry-run termine)'} ===", Color.OK)
    log(f"Projets migres   : {len(migrated_slugs)}", Color.INFO)
    log(f"Archives migrees : {moved} (dont {inboxed} en inbox)", Color.INFO)
    if not args.apply:
        log("\nPour appliquer reellement : ajoute --apply", Color.WARN)
    else:
        log("\nProchaines etapes :", Color.INFO)
        log("  1. Verifier index.md", Color.INFO)
        log("  2. Verifier au moins une archive dans 10-episodes/projects/{slug}/archives/", Color.INFO)
        log("  3. Tester : /mem-recall {slug} dans une nouvelle session", Color.INFO)

if __name__ == '__main__':
    main()
