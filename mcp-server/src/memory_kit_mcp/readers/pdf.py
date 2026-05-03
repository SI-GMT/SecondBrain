"""PDF reader — extract text via pypdf.

Mirrors ``scripts/doc-readers/read_pdf.py``. Scanned PDFs without OCR yield
near-empty extraction; below ``SCAN_THRESHOLD_CHARS`` we return an empty
markdown with a ``"scanned-or-low-signal"`` warning so the caller can fall
back to native LLM reading (vision).
"""

from __future__ import annotations

from pathlib import Path

from . import DocReaderDependencyError

SCAN_THRESHOLD_CHARS = 100


def extract(path: Path) -> tuple[str, list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocReaderDependencyError(
            "pypdf is required to read .pdf files. "
            "Install via: pip install memory-kit-mcp[doc-readers]"
        ) from exc

    warnings: list[str] = []
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise RuntimeError(
                f"PDF is password-protected, cannot decrypt with empty password: {exc}"
            ) from exc
    pages_out: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            warnings.append(f"page {idx} failed extraction: {exc}")
            text = ""
        text = text.strip()
        if not text:
            continue
        pages_out.append(f"## Page {idx}\n\n{text}")
    content = "\n\n".join(pages_out).strip()
    if len(content) < SCAN_THRESHOLD_CHARS:
        warnings.append(
            f"extraction yielded {len(content)} chars (< {SCAN_THRESHOLD_CHARS}); "
            "PDF likely scanned without OCR"
        )
        return "", warnings
    return content, warnings
