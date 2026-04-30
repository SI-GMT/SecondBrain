#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
read_csv.py — extract content from a .csv file as a Markdown table.

Auto-detects the delimiter via csv.Sniffer (comma / semicolon / tab).
Clipping rules identical to read_xlsx.py.

Stdout: Markdown table.
Stderr: clipping warnings and errors.
Exit codes:
  0  success
  1  invocation error
  2  empty file

Convention: invoked by core/procedures/mem-doc.md via `uv run`.
    uv run scripts/doc-readers/read_csv.py {path}
"""

import argparse
import csv
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


MAX_ROWS = 200
MAX_COLS = 30


def cell_to_str(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|").strip()


def detect_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        class Default(csv.excel):
            delimiter = ","
        return Default()


def extract(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError("could not decode file with utf-8/cp1252/latin-1")

    sample = text[:4096]
    dialect = detect_dialect(sample)
    reader = csv.reader(text.splitlines(), dialect=dialect)
    rows: list[list[str]] = []
    clipped_rows = clipped_cols = False
    for idx, row in enumerate(reader, start=1):
        if idx > MAX_ROWS:
            clipped_rows = True
            break
        cells = [cell_to_str(c) for c in row]
        if len(cells) > MAX_COLS:
            cells = cells[:MAX_COLS]
            clipped_cols = True
        rows.append(cells)
    while rows and not any(c for c in rows[-1]):
        rows.pop()
    if not rows:
        return ""
    if clipped_rows:
        print(f"Warning: clipped to {MAX_ROWS} rows", file=sys.stderr)
    if clipped_cols:
        print(f"Warning: clipped to {MAX_COLS} columns", file=sys.stderr)
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * width) + "|"]
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract .csv as Markdown table")
    parser.add_argument("path", help="Path to .csv file")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 1
    if not path.is_file():
        print(f"Error: not a file: {path}", file=sys.stderr)
        return 1

    try:
        content = extract(path)
    except Exception as exc:
        print(f"Error parsing csv: {exc}", file=sys.stderr)
        return 1

    if not content:
        print("Warning: empty csv", file=sys.stderr)
        return 2

    print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
