#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "beautifulsoup4>=4.12",
#   "lxml>=5.0",
# ]
# ///
"""
read_html.py — extract content from a .html / .htm file as Markdown.

Strips script/style/nav/header/footer noise, preserves headings (h1..h6),
paragraphs, lists (ul/ol/li), and tables.

Stdout: Markdown.
Stderr: errors.
Exit codes:
  0  success
  1  invocation error
  2  empty extraction

Convention: invoked by core/procedures/mem-doc.md via `uv run`.
    uv run scripts/doc-readers/read_html.py {path}
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:
    print("Error: beautifulsoup4 not available. Run via `uv run`.", file=sys.stderr)
    sys.exit(1)


NOISE_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form"}


def render_table(table: Tag) -> str:
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


def render_list(ul: Tag, ordered: bool, depth: int = 0) -> list[str]:
    out: list[str] = []
    indent = "  " * depth
    marker = "1." if ordered else "-"
    for li in ul.find_all("li", recursive=False):
        nested_lists = li.find_all(["ul", "ol"], recursive=False)
        for nl in nested_lists:
            nl.extract()
        text = li.get_text(" ", strip=True)
        if text:
            out.append(f"{indent}{marker} {text}")
        for nl in nested_lists:
            out.extend(render_list(nl, ordered=(nl.name == "ol"), depth=depth + 1))
    return out


def render(soup: BeautifulSoup) -> str:
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
        name = node.name.lower() if node.name else ""
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
            blocks.extend(render_list(node, ordered=(name == "ol")))
            return
        if name == "table":
            rendered = render_table(node)
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
    soup = BeautifulSoup(text, "lxml")
    return render(soup)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract .html as Markdown")
    parser.add_argument("path", help="Path to .html/.htm file")
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
        print(f"Error parsing html: {exc}", file=sys.stderr)
        return 1

    if not content:
        print("Warning: no textual content extracted", file=sys.stderr)
        return 2

    print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
