"""mem_note — Quick ingestion of a knowledge note into 20-knowledge/.

Spec: core/procedures/mem-note.md
"""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._ingestion import slugify_title, standard_frontmatter, write_atom
from memory_kit_mcp.tools._models import IngestionResult


def register(mcp: FastMCP) -> None:
    """Register mem_note with the FastMCP instance."""

    @mcp.tool()
    def mem_note(
        title: str = Field(..., description="Title of the note (used as the slug)."),
        content: str = Field(..., description="Markdown body of the note."),
        scope: str = Field("work", pattern="^(work|personal|all)$"),
        project: str | None = Field(None, description="Optional project tag."),
    ) -> IngestionResult:
        """Ingest a knowledge note into 20-knowledge/.

        Creates a single .md file with universal frontmatter (slug, zone,
        kind=knowledge, scope, tags, display). Filename collisions are
        disambiguated with -2, -3, ... suffixes.
        """
        config = get_config()
        slug = slugify_title(title)
        fm = standard_frontmatter(
            slug=slug,
            zone_short="knowledge",
            kind="knowledge",
            scope=scope,
            project=project,
            extra={"title": title, "display": title},
        )
        body = f"# {title}\n\n{content.strip()}\n"
        target = config.vault / "20-knowledge" / f"{slug}.md"
        actual = write_atom(target, fm, body)
        return IngestionResult(
            skill="mem_note",
            success=True,
            atoms_created=1,
            files_created=[str(actual)],
            target_zone="20-knowledge",
            summary_md=f"**mem_note** — `{slug}` written to `20-knowledge/{actual.name}`.\n",
        )
