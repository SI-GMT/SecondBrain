"""mem_principle — Ingest a principle (heuristic, red-line, value, action rule).

Spec: core/procedures/mem-principle.md
"""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._ingestion import slugify_title, standard_frontmatter, write_atom
from memory_kit_mcp.tools._models import IngestionResult


def register(mcp: FastMCP) -> None:
    """Register mem_principle with the FastMCP instance."""

    @mcp.tool()
    def mem_principle(
        title: str = Field(..., description="Short title of the principle (used as slug)."),
        content: str = Field(..., description="Markdown body — rationale, when to apply."),
        force: str = Field(
            "heuristic",
            pattern="^(red-line|heuristic|value|action-rule)$",
            description="Strength of the principle. red-line = absolute, never break.",
        ),
        scope: str = Field("work", pattern="^(work|personal|all)$"),
        project: str | None = Field(None, description="Optional project tag."),
    ) -> IngestionResult:
        """Ingest a principle into 40-principles/{scope}/.

        Stored under 40-principles/{scope}/{category}/{slug}.md when scope is
        explicit. POC keeps the layout flat (40-principles/{scope}/{slug}.md).
        """
        config = get_config()
        slug = slugify_title(title)
        fm = standard_frontmatter(
            slug=slug,
            zone_short="principles",
            kind="principle",
            scope=scope,
            project=project,
            extra={"title": title, "display": title, "force": force},
        )
        body = f"# {title}\n\n{content.strip()}\n"
        target = config.vault / "40-principles" / scope / f"{slug}.md"
        actual = write_atom(target, fm, body)
        return IngestionResult(
            skill="mem_principle",
            success=True,
            atoms_created=1,
            files_created=[str(actual)],
            target_zone="40-principles",
            summary_md=(
                f"**mem_principle** — `{slug}` ({force}) written to "
                f"`40-principles/{scope}/{actual.name}`.\n"
            ),
        )
