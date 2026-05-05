"""mem_read_archive — Read a specific archive file by its filename.

Spec: ``core/procedures/mem-read-archive.md``.

Bridges the gap for MCP-only CLI clients (Codex, Vibe, Gemini in pure MCP
mode) which don't have direct filesystem access. Lets the LLM fetch the full
content of a single archive — typical workflow: ``mem_recall`` returns a
list of recent archives, the user asks for the details of a specific one,
the LLM calls this tool with the archive filename.

Read-only — no writes.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import VaultReadResult
from memory_kit_mcp.vault import frontmatter, paths


def execute_read_archive(vault: Path, slug: str, filename: str) -> VaultReadResult:
    """Module-level entry. Resolves the archive under the project's archives/
    folder and returns its frontmatter + body."""
    if not slug or not filename:
        raise ValueError("slug and filename are both required")

    resolved = paths.resolve_slug(vault, slug)
    if resolved is None:
        raise FileNotFoundError(
            f"No project or domain {slug!r} in vault {vault}. "
            f"Available: {paths.list_projects(vault) + paths.list_domains(vault)}"
        )
    folder, kind, _archived = resolved

    # Defensive: filename must not contain path separators (no traversal).
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError(f"filename {filename!r} contains path separators or traversal")
    # Add .md if missing — accept both forms.
    if not filename.endswith(".md"):
        filename = filename + ".md"

    archive_path = folder / "archives" / filename
    if not archive_path.is_file():
        # Surface nearby names to help the LLM correct the call.
        archives_dir = folder / "archives"
        suggestions: list[str] = []
        if archives_dir.is_dir():
            suggestions = sorted(p.name for p in archives_dir.iterdir() if p.is_file() and p.suffix == ".md")[:10]
        raise FileNotFoundError(
            f"Archive {filename!r} not found in {slug!r}. "
            f"First {len(suggestions)} archives available: {suggestions}"
        )

    fm, body = frontmatter.read(archive_path)
    rel = archive_path.relative_to(vault).as_posix()

    return VaultReadResult(
        path=rel,
        slug=slug,
        kind="archive",
        frontmatter=fm,
        body=body,
        summary_md=(
            f"**mem_read_archive** — `{slug}` / `{filename}`\n\n"
            f"- Path: `{rel}`\n"
            f"- Frontmatter keys: {sorted(fm.keys())}\n"
            f"- Body length: {len(body)} chars\n"
        ),
    )


def register(mcp: FastMCP) -> None:
    """Register mem_read_archive with the FastMCP instance."""

    @mcp.tool()
    def mem_read_archive(
        slug: str = Field(..., description="Project or domain slug owning the archive."),
        filename: str = Field(
            ...,
            description=(
                "Archive filename (e.g. '2026-04-22-15h21-secondbrain-v0-3-mistral-vibe-reconstruct.md'). "
                "The .md suffix is optional."
            ),
        ),
    ) -> VaultReadResult:
        """Read a specific archive file's frontmatter + body.

        Use after ``mem_recall`` returns a list of archives to fetch the full
        content of one of them. Read-only — no writes. Refuses path traversal
        attempts in the filename.
        """
        config = get_config()
        return execute_read_archive(vault=config.vault, slug=slug, filename=filename)
