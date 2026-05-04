"""mem_doc — Ingest a local document into the vault as a single-shot archive.

Spec: ``core/procedures/mem-doc.md``.

Native fast-path for plain-text formats (``.md``, ``.markdown``, ``.txt``,
``.text``). All other formats (``.pdf``, ``.docx``, ``.pptx``, ``.xlsx``,
``.csv``, ``.html`` / ``.htm``) are dispatched to ``memory_kit_mcp.readers``
which extracts Markdown via the optional ``[doc-readers]`` extra.

Failure modes intentionally distinguished:

- ``UnsupportedFormatError`` — suffix has no registered reader; the caller
  (LLM) should fall back to native reading or refuse the file.
- ``DocReaderDependencyError`` — the optional extra is missing; install via
  ``pip install memory-kit-mcp[doc-readers]``.
- ``ValueError`` with a ``fall back to native LLM reading`` hint — file was
  parsed but yielded no usable text (e.g. scanned PDF without OCR). The
  LLM client should reattempt via its own vision/document-reading capability.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.readers import read_document
from memory_kit_mcp.tools._ingestion import slugify_title, standard_frontmatter, write_atom
from memory_kit_mcp.tools._models import IngestionResult

_NATIVE_TEXT_EXTS = {".md", ".markdown", ".txt", ".text"}


def _read_native_text(src: Path) -> str:
    try:
        return src.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"Cannot read {src} as UTF-8: {e}") from e


def _read_via_dispatcher(src: Path) -> tuple[str, list[str]]:
    content, warnings = read_document(src)
    if not content:
        warning_tail = f" Warnings: {'; '.join(warnings)}" if warnings else ""
        raise ValueError(
            f"Reader for {src.suffix!r} parsed {src} but yielded no usable text. "
            f"Fall back to native LLM reading.{warning_tail}"
        )
    return content, warnings


def register(mcp: FastMCP) -> None:
    """Register mem_doc with the FastMCP instance."""

    @mcp.tool()
    def mem_doc(
        path: str = Field(..., description="Absolute path to the local document to ingest."),
        title: str | None = Field(
            None,
            description="Optional title (defaults to filename stem).",
        ),
        project: str | None = Field(None, description="Optional project tag."),
        scope: str = Field("work", pattern="^(work|personal|all)$"),
    ) -> IngestionResult:
        """Ingest a local document as a single-shot vault archive.

        Native text (.md, .markdown, .txt, .text) is read directly. Other
        supported formats (.pdf, .docx, .pptx, .xlsx, .csv, .html, .htm) go
        through the readers package (requires the ``[doc-readers]`` extra).
        """
        src = Path(path).expanduser()
        if not src.exists():
            raise FileNotFoundError(f"Document not found: {src}")
        if not src.is_file():
            raise IsADirectoryError(f"Not a file: {src}")

        suffix = src.suffix.lower()
        warnings: list[str] = []
        if suffix in _NATIVE_TEXT_EXTS:
            content = _read_native_text(src)
        else:
            content, warnings = _read_via_dispatcher(src)

        config = get_config()
        timestamp = datetime.now().strftime("%Y-%m-%d-%Hh%M")
        title_resolved = title or src.stem
        slug_seed = slugify_title(title_resolved)
        slug = f"{timestamp}-doc-{slug_seed}"
        fm = standard_frontmatter(
            slug=slug,
            zone_short="inbox",
            kind="doc-ingest",
            scope=scope,
            project=project,
            extra={
                "display": title_resolved,
                "title": title_resolved,
                "source_path": str(src),
                "source_format": suffix.lstrip("."),
                "ingested_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        body = f"# {title_resolved}\n\n_(ingested from `{src}`)_\n\n{content}\n"
        target = config.vault / "00-inbox" / f"{slug}.md"
        actual = write_atom(target, fm, body)
        warnings_md = ""
        if warnings:
            warnings_md = "\n\nWarnings:\n" + "\n".join(f"- {w}" for w in warnings)
        return IngestionResult(
            skill="mem_doc",
            success=True,
            atoms_created=1,
            files_created=[str(actual)],
            target_zone="00-inbox",
            summary_md=(
                f"**mem_doc** — ingested `{src.name}` to `00-inbox/{actual.name}` "
                f"({len(content)} chars).{warnings_md}\n"
            ),
        )
