"""CSV reader — render as a single Markdown table (stdlib only).

Mirrors ``scripts/doc-readers/read_csv.py``. Auto-detects the delimiter via
``csv.Sniffer`` (``,;\\t|``) with a comma fallback. Encoding fallback chain:
``utf-8-sig``, ``utf-8``, ``cp1252``, ``latin-1``. Same row/col clipping as
the XLSX reader.
"""

from __future__ import annotations

import csv as _csv
from pathlib import Path

MAX_ROWS = 200
MAX_COLS = 30


def _cell_to_str(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|").strip()


def _detect_dialect(sample: str) -> _csv.Dialect:
    try:
        return _csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except _csv.Error:
        class Default(_csv.excel):
            delimiter = ","

        return Default()


def extract(path: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    raw = path.read_bytes()
    text: str | None = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError("could not decode file with utf-8/cp1252/latin-1")

    sample = text[:4096]
    dialect = _detect_dialect(sample)
    reader = _csv.reader(text.splitlines(), dialect=dialect)
    rows: list[list[str]] = []
    clipped_rows = clipped_cols = False
    for idx, row in enumerate(reader, start=1):
        if idx > MAX_ROWS:
            clipped_rows = True
            break
        cells = [_cell_to_str(c) for c in row]
        if len(cells) > MAX_COLS:
            cells = cells[:MAX_COLS]
            clipped_cols = True
        rows.append(cells)
    while rows and not any(c for c in rows[-1]):
        rows.pop()
    if not rows:
        warnings.append("empty csv")
        return "", warnings
    if clipped_rows:
        warnings.append(f"clipped to {MAX_ROWS} rows")
    if clipped_cols:
        warnings.append(f"clipped to {MAX_COLS} columns")
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * width) + "|"]
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out), warnings
