"""Fixe un fichier double-encode UTF-8->CP1252->UTF-8 (symptome Ã© au lieu de e-aigu).

Table de remplacement explicite pour les sequences CP1252 courantes en francais.
Plus robuste que encode('latin-1').decode('utf-8') qui echoue sur les caracteres
> 0xFF (typique: euro sign dans l'en-dash double-encode).
"""
from pathlib import Path

# (sequence corrompue, caractere original) - escapes Unicode pour clarte.
# Ordre important : sequences plus longues d'abord.
FIXES = [
    ("â€™", "’"),  # right single quote
    ("â€˜", "‘"),  # left single quote
    ("â€œ", "“"),  # left double quote
    ("â€", "”"),  # right double quote
    ("â€¢", "•"),  # bullet
    ("â€¦", "…"),  # ellipsis
    ("â€“", "–"),  # en dash
    ("â€”", "—"),  # em dash
    ("Ã©", "é"),  # e acute
    ("Ã¨", "è"),  # e grave
    ("Ãª", "ê"),  # e circumflex
    ("Ã«", "ë"),  # e diaeresis
    ("Ã ", "à"),  # a grave
    ("Ã¢", "â"),  # a circumflex
    ("Ã®", "î"),  # i circumflex
    ("Ã¯", "ï"),  # i diaeresis
    ("Ã´", "ô"),  # o circumflex
    ("Ã¶", "ö"),  # o diaeresis
    ("Ã»", "û"),  # u circumflex
    ("Ã¼", "ü"),  # u diaeresis
    ("Ã§", "ç"),  # c cedilla
    ("Ã‰", "É"),  # E acute
    ("Ãˆ", "È"),  # E grave
    ("Ã€", "À"),  # A grave
    ("ÃŠ", "Ê"),  # E circumflex
    ("ÃŽ", "Î"),  # I circumflex
    ("Ã”", "Ô"),  # O circumflex
    ("Ã›", "Û"),  # U circumflex
    ("Ã‡", "Ç"),  # C cedilla
    ("Â ", " "),  # nbsp
    ("Â°", "°"),  # degree
    ("Â«", "«"),  # left guillemet
    ("Â»", "»"),  # right guillemet
]

TARGETS = [
    Path(r"C:\_BDC\GMT\memory") / "_index.md",
    Path(r"C:\_BDC\GMT\memory") / "projets" / "gabrielle" / "contexte.md",
    Path(r"C:\_BDC\GMT\memory") / "projets" / "gabrielle" / "historique.md",
    Path(r"C:\_BDC\GMT\memory") / "archives" / "2026-02-03-archeo-gabrielle-fondations.md",
]


def suspects(text: str) -> int:
    return text.count("Ã") + text.count("â€") + text.count("Â ")


for path in TARGETS:
    if not path.exists():
        print(f"MISS  {path}")
        continue

    original = path.read_text(encoding="utf-8")
    fixed = original
    for bad, good in FIXES:
        fixed = fixed.replace(bad, good)

    before = suspects(original)
    after = suspects(fixed)

    if before == 0:
        print(f"CLEAN {path.name} (rien a corriger)")
        continue

    if after >= before:
        print(f"SKIP  {path.name} (pas d'amelioration: {before} -> {after})")
        continue

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(fixed, encoding="utf-8", newline="")
    tmp.replace(path)
    print(f"OK    {path.name} ({before} -> {after})")
