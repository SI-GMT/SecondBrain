#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pypdf>=4.0",
# ]
# ///
"""
read_pdf.py — extract textual content from a .pdf file as Markdown.

Strategy: pypdf text extraction. PDFs scanned without OCR yield empty/near-empty
output; in that case we exit with code 2 so that mem-doc.md falls back to the
LLM's native PDF reading capability (vision-based).

Stdout: Markdown (each page prefixed by `## Page N`).
Stderr: warnings (pages with low signal) and errors.
Exit codes:
  0  success — meaningful textual content extracted
  1  invocation error (missing arg, file not found, unreadable, parse error)
  2  scanned PDF or empty extraction (< 100 chars total) — caller should fall
     back to native LLM reading

Convention: invoked by core/procedures/mem-doc.md via `uv run`.
    uv run scripts/doc-readers/read_pdf.py {path}
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from pypdf import PdfReader
except ImportError:
    print("Error: pypdf not available. Run via `uv run`.", file=sys.stderr)
    sys.exit(1)


SCAN_THRESHOLD_CHARS = 100


def extract(path: Path) -> str:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            print(
                "Error: PDF is password-protected, cannot decrypt with empty password",
                file=sys.stderr,
            )
            raise SystemExit(1)
    pages_out: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            print(f"Warning: page {idx} failed extraction: {exc}", file=sys.stderr)
            text = ""
        text = text.strip()
        if not text:
            continue
        pages_out.append(f"## Page {idx}\n\n{text}")
    return "\n\n".join(pages_out).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract .pdf as Markdown")
    parser.add_argument("path", help="Path to .pdf file")
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
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1
    except Exception as exc:
        print(f"Error parsing pdf: {exc}", file=sys.stderr)
        return 1

    if len(content) < SCAN_THRESHOLD_CHARS:
        print(
            f"Warning: extraction yielded {len(content)} chars (< {SCAN_THRESHOLD_CHARS}); "
            "PDF likely scanned without OCR. Caller should use native LLM reading.",
            file=sys.stderr,
        )
        return 2

    print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
