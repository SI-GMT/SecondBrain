"""HTML reader — extract content as Markdown via BeautifulSoup + lxml.

Mirrors ``scripts/doc-readers/read_html.py``. Strips noise tags
(script/style/nav/header/footer/aside/form), preserves headings, paragraphs,
ordered/unordered lists (with nesting), tables, and pre/code blocks.
"""

from __future__ import annotations

from pathlib import Path

from . import DocReaderDependencyError

NOISE_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form"}


def _render_table(table) -> str:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [
            (cell.get_text(" ", strip=True) or "")
            .replace("\n", " ")
            .replace("|", "\\|")
            for cell in tr.find_all(["th", "td"])
        ]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * width) + "|"]
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def _render_list(ul, ordered: bool, depth: int = 0) -> list[str]:
    out: list[str] = []
    indent = "  " * depth
    marker = "1." if ordered else "-"
    for li in ul.find_all("li", recursive=False):
        nested = li.find_all(["ul", "ol"], recursive=False)
        for nl in nested:
            nl.extract()
        text = li.get_text(" ", strip=True)
        if text:
            out.append(f"{indent}{marker} {text}")
        for nl in nested:
            out.extend(_render_list(nl, ordered=(nl.name == "ol"), depth=depth + 1))
    return out


def _render(soup, NavigableString, Tag) -> str:
    for tag_name in NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    root = soup.body or soup
    blocks: list[str] = []

    def walk(node):
        if isinstance(node, NavigableString):
            return
        if not isinstance(node, Tag):
            return
        name = (node.name or "").lower()
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            text = node.get_text(" ", strip=True)
            if text:
                blocks.append("#" * level + " " + text)
            return
        if name == "p":
            text = node.get_text(" ", strip=True)
            if text:
                blocks.append(text)
            return
        if name in {"ul", "ol"}:
            blocks.extend(_render_list(node, ordered=(name == "ol")))
            return
        if name == "table":
            rendered = _render_table(node)
            if rendered:
                blocks.append(rendered)
            return
        if name in {"pre", "code"} and node.parent and node.parent.name != "pre":
            text = node.get_text("", strip=False)
            if text.strip():
                blocks.append("```\n" + text.rstrip() + "\n```")
            return
        for child in node.children:
            walk(child)

    walk(root)
    out: list[str] = []
    prev_kind: str | None = None
    for b in blocks:
        kind = "list" if b.startswith(("- ", "1. ", "  ")) else "block"
        if prev_kind is not None and not (kind == "list" and prev_kind == "list"):
            out.append("")
        out.append(b)
        prev_kind = kind
    return "\n".join(out).strip()


def extract(path: Path) -> tuple[str, list[str]]:
    try:
        from bs4 import BeautifulSoup, NavigableString, Tag
    except ImportError as exc:
        raise DocReaderDependencyError(
            "beautifulsoup4 (and lxml) are required to read .html files. "
            "Install via: pip install memory-kit-mcp[doc-readers]"
        ) from exc

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
    try:
        soup = BeautifulSoup(text, "lxml")
    except Exception as exc:
        raise DocReaderDependencyError(
            "lxml is required as the BeautifulSoup parser. "
            "Install via: pip install memory-kit-mcp[doc-readers]"
        ) from exc
    content = _render(soup, NavigableString, Tag)
    if not content:
        warnings.append("no textual content extracted")
    return content, warnings
