#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "python-docx>=1.1",
# ]
# ///
"""
read_docx.py — extract textual content from a .docx file as structured Markdown.

Stdout: Markdown (headings, paragraphs, bullet/numbered lists, tables).
Stderr: warnings (unsupported elements) and errors.
Exit codes:
  0  success
  1  invocation error (missing arg, file not found, unreadable)
  2  empty extraction (file parsed but no textual content found)

Convention: invoked by core/procedures/mem-doc.md via `uv run`.
    uv run scripts/doc-readers/read_docx.py {path}
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except ImportError:
    print("Error: python-docx not available. Run via `uv run`.", file=sys.stderr)
    sys.exit(1)


def heading_level(style_name: str) -> int | None:
    """Return 1..6 if style is Heading N, else None."""
    if not style_name:
        return None
    name = style_name.strip().lower()
    if name == "title":
        return 1
    if name.startswith("heading "):
        try:
            n = int(name.split(" ", 1)[1])
            return max(1, min(6, n))
        except ValueError:
            return None
    return None


def list_marker(paragraph: Paragraph) -> str | None:
    """
    Detect list paragraphs. Returns '-' for bullet, '1.' for numbered, None otherwise.

    Detection combines two signals because python-docx surfaces list info in
    different places depending on how the document was produced:
      - style name ('List Bullet*', 'List Number*') — set by Word and python-docx
      - numPr XML element — present when Word actually applied a numbering
    """
    style_name = (paragraph.style.name or "").lower()
    if "list number" in style_name:
        return "1."
    if "list bullet" in style_name:
        return "-"
    pPr = paragraph._p.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr"
    )
    if pPr is None:
        return None
    numPr = pPr.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numPr"
    )
    if numPr is None:
        return None
    if "number" in style_name:
        return "1."
    return "-"


def render_paragraph(paragraph: Paragraph) -> str:
    text = paragraph.text.strip()
    if not text:
        return ""
    level = heading_level(paragraph.style.name)
    if level is not None:
        return f"{'#' * level} {text}"
    marker = list_marker(paragraph)
    if marker is not None:
        return f"{marker} {text}"
    return text


def render_table(table: Table) -> str:
    """Render a docx table as a Markdown table. First row treated as header."""
    rows = []
    for row in table.rows:
        cells = [cell.text.replace("\n", " ").replace("|", "\\|").strip() for cell in row.cells]
        rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = []
    out.append("| " + " | ".join(rows[0]) + " |")
    out.append("|" + "|".join(["---"] * width) + "|")
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def iter_block_items(parent):
    """
    Yield paragraphs and tables in document order.
    python-docx exposes them separately; we walk the underlying XML.
    """
    from docx.oxml.ns import qn
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def kind_of(rendered: str) -> str:
    if rendered.startswith("#"):
        return "heading"
    if rendered.startswith(("- ", "1. ")):
        return "list"
    if rendered.startswith("|"):
        return "table"
    return "para"


def extract(path: Path) -> str:
    doc = Document(str(path))
    blocks: list[str] = []
    prev_kind: str | None = None
    for item in iter_block_items(doc):
        if isinstance(item, Paragraph):
            rendered = render_paragraph(item)
            if not rendered:
                continue
            kind = kind_of(rendered)
        elif isinstance(item, Table):
            rendered = render_table(item)
            if not rendered:
                continue
            kind = "table"
        else:
            continue
        if prev_kind is not None:
            if kind == "list" and prev_kind == "list":
                pass
            else:
                blocks.append("")
        blocks.append(rendered)
        prev_kind = kind
    return "\n".join(blocks).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract .docx as Markdown")
    parser.add_argument("path", help="Path to .docx file")
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
        print(f"Error parsing docx: {exc}", file=sys.stderr)
        return 1

    if not content:
        print("Warning: no textual content extracted", file=sys.stderr)
        return 2

    print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
