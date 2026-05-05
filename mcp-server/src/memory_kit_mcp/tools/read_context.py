"""mem_read_context — Read a project or domain's ``context.md`` directly.

Spec: ``core/procedures/mem-read-context.md``.

Lighter-weight alternative to ``mem_recall`` when the LLM only needs the
current snapshot (phase, decisions, next steps) without the full briefing
synthesis (active principles, open goals, key people, topology, etc.).

Read-only.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import VaultReadResult
from memory_kit_mcp.vault import frontmatter, paths


def execute_read_context(vault: Path, slug: str) -> VaultReadResult:
    if not slug:
        raise ValueError("slug is required")
    resolved = paths.resolve_slug(vault, slug)
    if resolved is None:
        raise FileNotFoundError(
            f"No project or domain {slug!r} in vault {vault}. "
            f"Available: {paths.list_projects(vault) + paths.list_domains(vault)}"
        )
    folder, kind, _archived = resolved
    ctx_path = folder / "context.md"
    if not ctx_path.is_file():
        raise FileNotFoundError(
            f"context.md missing for {slug!r} (folder exists but no context.md). "
            "Run mem_init_project to bootstrap, or mem_archive to populate."
        )
    fm, body = frontmatter.read(ctx_path)
    rel = ctx_path.relative_to(vault).as_posix()
    return VaultReadResult(
        path=rel,
        slug=slug,
        kind="context",
        frontmatter=fm,
        body=body,
        summary_md=(
            f"**mem_read_context** — `{slug}` ({kind})\n\n"
            f"- Path: `{rel}`\n"
            f"- Phase: {fm.get('phase') or '(unset)'}\n"
            f"- Last session: {fm.get('last-session') or '(unset)'}\n"
            f"- Body length: {len(body)} chars\n"
        ),
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def mem_read_context(
        slug: str = Field(..., description="Project or domain slug."),
    ) -> VaultReadResult:
        """Read the ``context.md`` of a project or domain (frontmatter + body).

        Lighter than ``mem_recall`` — surface only the current snapshot
        without the full briefing synthesis. Read-only.
        """
        config = get_config()
        return execute_read_context(vault=config.vault, slug=slug)
