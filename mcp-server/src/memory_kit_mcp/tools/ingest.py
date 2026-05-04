"""mem — Universal ingestion router (POC).

Spec: core/procedures/mem.md (full router with semantic classification)

POC implementation: minimal router that drops the input into 00-inbox/ as a
single timestamped note. The full classification cascade (knowledge vs
principle vs goal vs person, scope detection, project resolution) is
deferred to v0.8.x — the LLM client can call the typed shortcuts
(mem_note, mem_principle, mem_goal, mem_person) directly when the type
is known.

This POC is a SAFE FALLBACK — captures everything, classifies nothing,
loses nothing. Manual triage from 00-inbox/ stays available.
"""

from __future__ import annotations

from datetime import datetime

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._ingestion import slugify_title, standard_frontmatter, write_atom
from memory_kit_mcp.tools._models import IngestionResult


def register(mcp: FastMCP) -> None:
    """Register mem with the FastMCP instance."""

    @mcp.tool()
    def mem(
        content: str = Field(..., description="Free-form text or Markdown to capture."),
        hint: str | None = Field(
            None,
            description=(
                "Optional hint about the content type "
                "('note' | 'principle' | 'goal' | 'person' | 'idea')."
            ),
        ),
    ) -> IngestionResult:
        """Universal capture into 00-inbox/.

        POC behaviour: writes the content as a timestamped note in
        `00-inbox/`. If you know the type, prefer mem_note / mem_principle /
        mem_goal / mem_person — those have richer schemas.
        """
        config = get_config()
        timestamp = datetime.now().strftime("%Y-%m-%d-%Hh%M")
        title_seed = content.strip().split("\n", 1)[0][:60] or "capture"
        slug_seed = slugify_title(title_seed) or "capture"
        slug = f"{timestamp}-{slug_seed}"
        fm = standard_frontmatter(
            slug=slug,
            zone_short="inbox",
            kind="capture",
            scope="all",
            extra={"display": slug, "hint": hint or "unclassified"},
        )
        body = f"# {title_seed}\n\n{content.strip()}\n"
        target = config.vault / "00-inbox" / f"{slug}.md"
        actual = write_atom(target, fm, body)
        return IngestionResult(
            skill="mem",
            success=True,
            atoms_created=1,
            files_created=[str(actual)],
            target_zone="00-inbox",
            summary_md=(
                f"**mem** — captured to `00-inbox/{actual.name}` "
                f"(hint={hint or 'none'}). Manual triage from inbox.\n"
            ),
        )
