"""mem_goal — Ingest a goal (future intention, desired state, aim) into 50-goals/.

Spec: core/procedures/mem-goal.md
"""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._ingestion import slugify_title, standard_frontmatter, write_atom
from memory_kit_mcp.tools._models import IngestionResult


def register(mcp: FastMCP) -> None:
    """Register mem_goal with the FastMCP instance."""

    @mcp.tool()
    def mem_goal(
        title: str = Field(..., description="Title of the goal (used as slug)."),
        content: str = Field("", description="Optional Markdown body (rationale, sub-goals)."),
        horizon: str = Field(
            "short",
            pattern="^(short|medium|long)$",
            description="Time horizon: short (<3 months), medium (3-12 months), long (>1 year).",
        ),
        deadline: str | None = Field(
            None, description="Optional ISO-format deadline (YYYY-MM-DD)."
        ),
        status: str = Field(
            "open", pattern="^(open|in-progress|done|abandoned)$"
        ),
        scope: str = Field("work", pattern="^(work|personal|all)$"),
        project: str | None = Field(None, description="Optional project tag."),
    ) -> IngestionResult:
        """Ingest a goal into 50-goals/{horizon}/."""
        config = get_config()
        slug = slugify_title(title)
        extra: dict = {"title": title, "display": title, "horizon": horizon, "status": status}
        if deadline:
            extra["deadline"] = deadline
        fm = standard_frontmatter(
            slug=slug,
            zone_short="goals",
            kind="goal",
            scope=scope,
            project=project,
            extra=extra,
        )
        body = f"# {title}\n\n{content.strip()}\n" if content.strip() else f"# {title}\n"
        target = config.vault / "50-goals" / horizon / f"{slug}.md"
        actual = write_atom(target, fm, body)
        return IngestionResult(
            skill="mem_goal",
            success=True,
            atoms_created=1,
            files_created=[str(actual)],
            target_zone="50-goals",
            summary_md=(
                f"**mem_goal** — `{slug}` ({horizon}, {status}) written to "
                f"`50-goals/{horizon}/{actual.name}`.\n"
            ),
        )
