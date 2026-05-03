"""mem_doc — Ingest a local document into the vault as a single-shot archive.

Spec: core/procedures/mem-doc.md (full multi-format support)

POC implementation: native text formats (.md, .txt) only. For PDF/DOCX/PPTX/
XLSX/CSV/HTML, the spec delegates to scripts/doc-readers/*.py via uv run —
that integration is deferred to v0.8.x. This POC raises a clear error for
unsupported formats so the LLM can fall back to the skills mode.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._ingestion import slugify_title, standard_frontmatter, write_atom
from memory_kit_mcp.tools._models import IngestionResult

_NATIVE_TEXT_EXTS = {".md", ".markdown", ".txt", ".text"}


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

        POC supports native text (.md, .markdown, .txt, .text) only. PDF, DOCX,
        PPTX, XLSX, CSV, HTML require the doc-readers from scripts/doc-readers/
        which will be integrated in v0.8.x.
        """
        src = Path(path).expanduser()
        if not src.exists():
            raise FileNotFoundError(f"Document not found: {src}")
        if not src.is_file():
            raise IsADirectoryError(f"Not a file: {src}")

        suffix = src.suffix.lower()
        if suffix not in _NATIVE_TEXT_EXTS:
            raise NotImplementedError(
                f"Unsupported format {suffix!r}. POC v0.8.0 supports "
                f"{sorted(_NATIVE_TEXT_EXTS)} natively. For PDF/DOCX/PPTX/XLSX/CSV/HTML, "
                "fall back to the skills procedure (uses scripts/doc-readers/ via uv run)."
            )

        try:
            content = src.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(f"Cannot read {src} as UTF-8: {e}") from e

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
        return IngestionResult(
            skill="mem_doc",
            success=True,
            atoms_created=1,
            files_created=[str(actual)],
            target_zone="00-inbox",
            summary_md=(
                f"**mem_doc** — ingested `{src.name}` to `00-inbox/{actual.name}` "
                f"({len(content)} chars).\n"
            ),
        )
