"""DOCX reader — extract structured Markdown via python-docx.

Mirrors ``scripts/doc-readers/read_docx.py``: heading levels (Title=H1,
Heading N), list markers detected by both style name and the underlying
numPr XML element, tables rendered as Markdown tables.
"""

from __future__ import annotations

from pathlib import Path

from . import DocReaderDependencyError

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _heading_level(style_name: str) -> int | None:
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


def _list_marker(paragraph) -> str | None:
    style_name = (paragraph.style.name or "").lower()
    if "list number" in style_name:
        return "1."
    if "list bullet" in style_name:
        return "-"
    pPr = paragraph._p.find(f"{_W_NS}pPr")
    if pPr is None:
        return None
    numPr = pPr.find(f"{_W_NS}numPr")
    if numPr is None:
        return None
    if "number" in style_name:
        return "1."
    return "-"


def _render_paragraph(paragraph) -> str:
    text = paragraph.text.strip()
    if not text:
        return ""
    level = _heading_level(paragraph.style.name)
    if level is not None:
        return f"{'#' * level} {text}"
    marker = _list_marker(paragraph)
    if marker is not None:
        return f"{marker} {text}"
    return text


def _render_table(table) -> str:
    rows = []
    for row in table.rows:
        cells = [cell.text.replace("\n", " ").replace("|", "\\|").strip() for cell in row.cells]
        rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * width) + "|"]
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def _iter_block_items(parent, Paragraph, Table):
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == f"{_W_NS}p":
            yield Paragraph(child, parent)
        elif child.tag == f"{_W_NS}tbl":
            yield Table(child, parent)


def _kind_of(rendered: str) -> str:
    if rendered.startswith("#"):
        return "heading"
    if rendered.startswith(("- ", "1. ")):
        return "list"
    if rendered.startswith("|"):
        return "table"
    return "para"


def extract(path: Path) -> tuple[str, list[str]]:
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise DocReaderDependencyError(
            "python-docx is required to read .docx files. "
            "Install via: pip install memory-kit-mcp[doc-readers]"
        ) from exc

    warnings: list[str] = []
    doc = Document(str(path))
    blocks: list[str] = []
    prev_kind: str | None = None
    for item in _iter_block_items(doc, Paragraph, Table):
        if isinstance(item, Paragraph):
            rendered = _render_paragraph(item)
            if not rendered:
                continue
            kind = _kind_of(rendered)
        elif isinstance(item, Table):
            rendered = _render_table(item)
            if not rendered:
                continue
            kind = "table"
        else:
            continue
        if prev_kind is not None and not (kind == "list" and prev_kind == "list"):
            blocks.append("")
        blocks.append(rendered)
        prev_kind = kind
    content = "\n".join(blocks).strip()
    if not content:
        warnings.append("no textual content extracted")
    return content, warnings
