"""mem_update_phase — Targeted update of a project's ``phase`` frontmatter field.

Spec: ``core/procedures/mem-update-phase.md``.

Lightweight alternative to ``mem_archive(mode='incremental')`` when the LLM
only needs to bump the phase string without rewriting the entire context
body. Preserves the body verbatim, updates ``phase`` and ``last-session``
in the frontmatter, writes atomically.

Refuses archived projects per the ``_archived.md`` doctrine — for those,
the user must ``mem_historize`` with revive first.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter, paths


def execute_update_phase(vault: Path, slug: str, phase: str) -> ChangeReport:
    if not slug:
        raise ValueError("slug is required")
    if phase is None:  # explicit empty string is allowed (clears the phase)
        raise ValueError("phase must be a string (use '' to clear)")

    resolved = paths.resolve_slug(vault, slug)
    if resolved is None:
        raise FileNotFoundError(
            f"No project or domain {slug!r} in vault {vault}. "
            f"Available: {paths.list_projects(vault) + paths.list_domains(vault)}"
        )
    folder, kind, archived = resolved
    if archived:
        raise PermissionError(
            f"Project {slug!r} is archived. Run mem_historize with revive=True first."
        )

    ctx_path = folder / "context.md"
    if not ctx_path.is_file():
        raise FileNotFoundError(
            f"context.md missing for {slug!r}. Run mem_init_project to bootstrap first."
        )

    fm, body = frontmatter.read(ctx_path)
    old_phase = str(fm.get("phase") or "")
    fm["phase"] = phase
    fm["last-session"] = datetime.now().date().isoformat()
    frontmatter.write(ctx_path, fm, body)

    rel = ctx_path.relative_to(vault).as_posix()
    return ChangeReport(
        skill="mem_update_phase",
        success=True,
        files_modified=[rel],
        summary_md=(
            f"**mem_update_phase** — `{slug}` ({kind})\n\n"
            f"- `phase`: {old_phase!r} → {phase!r}\n"
            f"- `last-session` bumped to {fm['last-session']}\n"
            f"- Body preserved verbatim ({len(body)} chars).\n"
        ),
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def mem_update_phase(
        slug: str = Field(..., description="Project or domain slug."),
        phase: str = Field(
            ...,
            description=(
                "New phase string (e.g. 'v0.9.3 in progress', 'cap-cadrage', 'archived'). "
                "Pass empty string to clear the phase."
            ),
        ),
    ) -> ChangeReport:
        """Update the ``phase`` field of a project's ``context.md`` frontmatter.

        Lightweight alternative to ``mem_archive(mode='incremental')`` — only
        rewrites the frontmatter, preserves the body verbatim. Bumps
        ``last-session`` to today. Refuses archived projects (use
        ``mem_historize`` with revive=True first).
        """
        config = get_config()
        return execute_update_phase(vault=config.vault, slug=slug, phase=phase)
