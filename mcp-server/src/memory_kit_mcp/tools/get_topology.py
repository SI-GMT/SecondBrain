"""mem_get_topology — Read the persisted topology snapshot of a project.

Spec: ``core/procedures/mem-get-topology.md``.

Reads ``99-meta/repo-topology/{slug}.md`` if present and surfaces its
frontmatter + body. Useful for LLM-driven tasks (Phase 1 archeo semantic
analysis, contextual reasoning) that want the topology metadata without
the cost of a fresh ``vault.topology_scanner.scan()`` call.

Returns ``exists=False`` rather than raising if the topology hasn't been
persisted yet — lets the caller decide whether to scan or fall back.

Read-only.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import TopologyReadResult
from memory_kit_mcp.vault import frontmatter, paths


def execute_get_topology(
    vault: Path, project: str, branch: str | None = None
) -> TopologyReadResult:
    if not project:
        raise ValueError("project is required")

    if branch:
        target = paths.branch_topology_file(vault, project, branch)
    else:
        target = paths.topology_file(vault, project)

    rel = (
        target.relative_to(vault).as_posix()
        if target.exists()
        else (
            f"99-meta/repo-topology/{project}-branches/"
            f"{branch.replace('/', '-').replace('\\', '-')}.md"
            if branch
            else f"99-meta/repo-topology/{project}.md"
        )
    )

    if not target.is_file():
        msg = (
            f"**mem_get_topology** — `{project}`"
            + (f" (branch `{branch}`)" if branch else "")
            + f": no topology persisted (expected at `{rel}`). "
            f"Run mem_archeo or mem_archeo_stack to scan."
        )
        return TopologyReadResult(
            project=project,
            topology_path="",
            exists=False,
            summary_md=msg,
        )

    fm, body = frontmatter.read(target)
    repo_path = str(fm.get("repo_path") or "")
    repo_remote = str(fm.get("repo_remote") or "")
    content_hash = str(fm.get("content_hash") or "")
    last_archive = str(fm.get("last_archive") or "")

    return TopologyReadResult(
        project=project,
        topology_path=rel,
        exists=True,
        frontmatter=fm,
        body=body,
        repo_path=repo_path,
        repo_remote=repo_remote,
        content_hash=content_hash,
        last_archive=last_archive,
        summary_md=(
            f"**mem_get_topology** — `{project}`\n\n"
            f"- Path: `{rel}`\n"
            f"- Repo: `{repo_path or '(unset)'}`\n"
            f"- Remote: `{repo_remote or '(unset)'}`\n"
            f"- Last archive: `{last_archive or '(none)'}`\n"
            f"- content_hash: `{content_hash[:12]}{'...' if len(content_hash) > 12 else ''}`\n"
        ),
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def mem_get_topology(
        project: str = Field(..., description="Project slug whose topology to read."),
        branch: str | None = Field(
            None,
            description="Optional branch name to read a branch-specific topology.",
        ),
    ) -> TopologyReadResult:
        """Read the persisted topology snapshot of a project.

        Surfaces ``99-meta/repo-topology/{slug}.md`` with frontmatter + body.
        Returns ``exists=False`` (rather than raising) if no topology is
        persisted yet — lets the caller decide whether to trigger a fresh
        scan via ``mem_archeo`` / ``mem_archeo_stack``.

        Read-only.
        """
        config = get_config()
        return execute_get_topology(
            vault=config.vault, project=project, branch=branch
        )
