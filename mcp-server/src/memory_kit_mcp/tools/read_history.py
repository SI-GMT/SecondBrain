"""mem_read_history — Read a project or domain's ``history.md`` directly.

Spec: ``core/procedures/mem-read-history.md``.

Surface the chronological session log without going through ``mem_recall``
or ``mem_digest``. Useful when the LLM wants to scan the raw session list
(file links + one-line summaries) rather than a synthesised digest.

Read-only.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import VaultReadResult
from memory_kit_mcp.vault import frontmatter, paths


def execute_read_history(vault: Path, slug: str) -> VaultReadResult:
    if not slug:
        raise ValueError("slug is required")
    resolved = paths.resolve_slug(vault, slug)
    if resolved is None:
        raise FileNotFoundError(
            f"No project or domain {slug!r} in vault {vault}. "
            f"Available: {paths.list_projects(vault) + paths.list_domains(vault)}"
        )
    folder, kind, _archived = resolved
    hist_path = folder / "history.md"
    if not hist_path.is_file():
        raise FileNotFoundError(
            f"history.md missing for {slug!r}. "
            "Run mem_init_project to bootstrap, or mem_archive to populate."
        )
    fm, body = frontmatter.read(hist_path)
    rel = hist_path.relative_to(vault).as_posix()
    # Count session entries (rough — lines starting with `- [`)
    entries = sum(1 for line in body.splitlines() if line.lstrip().startswith("- ["))
    return VaultReadResult(
        path=rel,
        slug=slug,
        kind="history",
        frontmatter=fm,
        body=body,
        summary_md=(
            f"**mem_read_history** — `{slug}` ({kind})\n\n"
            f"- Path: `{rel}`\n"
            f"- Session entries detected: {entries}\n"
            f"- Body length: {len(body)} chars\n"
        ),
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def mem_read_history(
        slug: str = Field(..., description="Project or domain slug."),
    ) -> VaultReadResult:
        """Read the ``history.md`` of a project or domain (frontmatter + body).

        Returns the chronological session log as-is — no synthesis. Use
        ``mem_digest`` for an aggregated narrative. Read-only.
        """
        config = get_config()
        return execute_read_history(vault=config.vault, slug=slug)
