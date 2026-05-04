"""mem_person — Ingest a person card (colleague, client, friend, family) into 60-people/.

Spec: core/procedures/mem-person.md
"""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._ingestion import slugify_title, standard_frontmatter, write_atom
from memory_kit_mcp.tools._models import IngestionResult


def register(mcp: FastMCP) -> None:
    """Register mem_person with the FastMCP instance."""

    @mcp.tool()
    def mem_person(
        name: str = Field(..., description="Person's full name (used as slug source)."),
        role: str | None = Field(None, description="Role / job title."),
        relation: str = Field(
            "colleague",
            pattern="^(colleague|client|friend|family|other)$",
        ),
        notes: str = Field("", description="Free-form notes about the person."),
        scope: str = Field("work", pattern="^(work|personal|all)$"),
        sensitive: bool = Field(
            True, description="Mark the card as sensitive (default True for privacy)."
        ),
        project: str | None = Field(None, description="Optional project tag."),
    ) -> IngestionResult:
        """Ingest a person card into 60-people/{relation}/."""
        config = get_config()
        slug = slugify_title(name)
        extra: dict = {
            "name": name,
            "display": name,
            "relation": relation,
            "sensitive": sensitive,
        }
        if role:
            extra["role"] = role
        fm = standard_frontmatter(
            slug=slug,
            zone_short="people",
            kind="person",
            scope=scope,
            project=project,
            extra=extra,
        )
        body = f"# {name}\n\n{notes.strip()}\n" if notes.strip() else f"# {name}\n"
        target = config.vault / "60-people" / relation / f"{slug}.md"
        actual = write_atom(target, fm, body)
        return IngestionResult(
            skill="mem_person",
            success=True,
            atoms_created=1,
            files_created=[str(actual)],
            target_zone="60-people",
            summary_md=(
                f"**mem_person** — `{slug}` ({relation}, sensitive={sensitive}) written to "
                f"`60-people/{relation}/{actual.name}`.\n"
            ),
        )
