"""Document readers — extract textual content from binary office formats as Markdown.

Public API: ``read_document(path: Path) -> tuple[str, list[str]]`` returns
``(markdown_content, warnings)``. Empty markdown means the file was parsed but
no usable text was found (e.g. scanned PDF, empty workbook); the warnings list
explains why.

Heavy dependencies (``pypdf``, ``python-docx``, ``python-pptx``, ``openpyxl``,
``beautifulsoup4``, ``lxml``) are imported lazily inside each reader so that
``memory_kit_mcp`` stays importable when the optional ``[doc-readers]`` extra
is not installed. A missing dep raises ``DocReaderDependencyError`` with the
exact pip command to fix it.

This package mirrors the standalone scripts in ``scripts/doc-readers/`` (per
the doctrine documented in ``CLAUDE.md``: standalone autonomy + library reuse).
The standalone copy is the canonical reference; both must stay in sync.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "DocReaderDependencyError",
    "UnsupportedFormatError",
    "read_document",
    "supported_suffixes",
]


class DocReaderDependencyError(RuntimeError):
    """Raised when a reader's optional dependency is not installed."""


class UnsupportedFormatError(ValueError):
    """Raised when no reader is registered for a file's extension."""


_SUFFIX_DISPATCH = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".html": "html",
    ".htm": "html",
}


def supported_suffixes() -> list[str]:
    """Return the list of file suffixes handled by this package."""
    return sorted(_SUFFIX_DISPATCH.keys())


def read_document(path: Path) -> tuple[str, list[str]]:
    """Dispatch ``path`` to the matching reader based on its suffix.

    Returns ``(markdown, warnings)``. Raises ``UnsupportedFormatError`` if the
    suffix has no registered reader, ``FileNotFoundError`` / ``IsADirectoryError``
    on path errors, ``DocReaderDependencyError`` if an optional dep is missing.
    """
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if not path.is_file():
        raise IsADirectoryError(f"not a file: {path}")
    suffix = path.suffix.lower()
    module_name = _SUFFIX_DISPATCH.get(suffix)
    if module_name is None:
        raise UnsupportedFormatError(
            f"unsupported document suffix {suffix!r}; "
            f"supported: {supported_suffixes()}"
        )
    from importlib import import_module

    module = import_module(f"memory_kit_mcp.readers.{module_name}")
    return module.extract(path)
