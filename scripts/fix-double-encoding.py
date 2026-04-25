#!/usr/bin/env python3
"""Fix double-encoded UTF-8->CP1252->UTF-8 corruptions dans un vault v0.5.

Symptome typique : `Ã©` au lieu de `é`, `â€™` au lieu de `'`.

Cause historique : ingestion via PowerShell `Set-Content` sans `-Encoding utf8NoBOM`
avant le durcissement v0.3.1.

Usage :
    python scripts/fix-double-encoding.py --vault /chemin/vault [--apply]

Sans --apply : dry-run, affiche uniquement les fichiers detectes.
Avec --apply : applique les corrections (atomic write via .tmp).

Refactor 2026-04-25 (v0.5.0.1) : scan recursif sur l'arbo brain-centric v0.5
au lieu de la liste TARGETS hardcodee de la v0.4.
"""
import argparse
import sys
from pathlib import Path

# Ordre important : sequences plus longues d'abord pour eviter les matches partiels.
FIXES = [
    ("â€™", "’"),  # right single quote
    ("â€˜", "‘"),  # left single quote
    ("â€œ", "“"),  # left double quote
    ("â€\x9d", "”"),  # right double quote (souvent encode avec un \x9d)
    ("â€¢", "•"),  # bullet
    ("â€¦", "…"),  # ellipsis
    ("â€“", "–"),  # en dash
    ("â€”", "—"),  # em dash
    ("Ã©", "é"),
    ("Ã¨", "è"),
    ("Ãª", "ê"),
    ("Ã«", "ë"),
    ("Ã ", "à"),
    ("Ã¢", "â"),
    ("Ã®", "î"),
    ("Ã¯", "ï"),
    ("Ã´", "ô"),
    ("Ã¶", "ö"),
    ("Ã»", "û"),
    ("Ã¼", "ü"),
    ("Ã§", "ç"),
    ("Ã‰", "É"),
    ("Ãˆ", "È"),
    ("Ã€", "À"),
    ("ÃŠ", "Ê"),
    ("ÃŽ", "Î"),
    ("Ã”", "Ô"),
    ("Ã›", "Û"),
    ("Ã‡", "Ç"),
    ("Â ", " "),  # nbsp
    ("Â°", "°"),
    ("Â«", "«"),
    ("Â»", "»"),
]


def strip_code_spans(text: str) -> str:
    """Retire les contenus dans backticks inline et blocks ``` ``` pour eviter les faux positifs.
    Les exemples de corruption cites dans la documentation (ex: `Ã©` -> `é`) ne doivent pas
    etre comptes comme corruptions reelles a corriger.
    """
    import re
    # Blocs ``` ``` (multi-lignes)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Backticks inline (single-line)
    text = re.sub(r"`[^`\n]*`", "", text)
    return text


def count_suspects(text: str) -> int:
    """Compte les sequences suspectes restantes (heuristique de detection).
    Ignore le contenu dans les backticks (code inline et blocs) pour eviter les faux positifs.
    """
    cleaned = strip_code_spans(text)
    return cleaned.count("Ã") + cleaned.count("â€") + cleaned.count("Â ")


def fix_text(text: str) -> str:
    fixed = text
    for bad, good in FIXES:
        fixed = fixed.replace(bad, good)
    return fixed


def scan_vault(vault: Path, apply: bool):
    if not vault.exists():
        print(f"ERROR Vault introuvable : {vault}", file=sys.stderr)
        sys.exit(1)

    # Exclure les dossiers Obsidian + binaires (sources copiees, archives binaires)
    EXCLUDE = {".obsidian", ".trash", "sources", "_sources"}

    candidates = []
    for md in vault.rglob("*.md"):
        if any(part in EXCLUDE for part in md.parts):
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"SKIP  {md.relative_to(vault)} (decode UTF-8 echoue)")
            continue
        n = count_suspects(text)
        if n > 0:
            candidates.append((md, text, n))

    print(f"\n=== Scan double-encoding sur {vault} ===")
    print(f"Mode : {'APPLY' if apply else 'DRY-RUN (no write)'}")
    print(f"Candidats detectes : {len(candidates)}\n")

    if not candidates:
        print("Vault propre. Rien a corriger.")
        return 0

    fixed_count = 0
    for md, original, before in candidates:
        fixed = fix_text(original)
        after = count_suspects(fixed)

        if after >= before:
            print(f"  [SKIP]  {md.relative_to(vault)} : {before} suspects (pas d'amelioration apres fix)")
            continue

        print(f"  [{'FIX' if apply else 'DRY'}]  {md.relative_to(vault)} : {before} -> {after} suspects")

        if apply:
            tmp = md.with_suffix(md.suffix + ".tmp")
            tmp.write_text(fixed, encoding="utf-8", newline="")
            tmp.replace(md)
            fixed_count += 1

    print(f"\n=== {'Termine' if apply else 'Dry-run termine'} ===")
    if apply:
        print(f"Fichiers corriges : {fixed_count}")
    else:
        actionnables = sum(1 for _, txt, before in candidates if count_suspects(fix_text(txt)) < before)
        print(f"Fichiers actionnables : {actionnables} / {len(candidates)} candidats")
        print("Pour appliquer reellement : ajoute --apply")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Fix double-encoded UTF-8 sur vault SecondBrain v0.5")
    parser.add_argument("--vault", required=True, help="Chemin absolu du vault")
    parser.add_argument("--apply", action="store_true", help="Applique les corrections (sinon dry-run)")
    args = parser.parse_args()

    sys.exit(scan_vault(Path(args.vault).resolve(), args.apply))


if __name__ == "__main__":
    main()
