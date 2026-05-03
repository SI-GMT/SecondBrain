"""mem_archeo_git — Phase 3 of the triphasic archeo: Git history reconstruction.

Spec: core/procedures/mem-archeo-git.md

STUB (v0.8.x port in progress). Will replace this stub with a subprocess-based
git history walker that produces dated archive atoms per tag/release/merge/commit
window, with idempotence via commit SHA.
"""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register mem_archeo_git stub."""

    @mcp.tool()
    def mem_archeo_git(repo_path: str | None = None) -> str:
        """Phase 3 of the triphasic archeo: Git history reconstruction.

        STUB v0.8.x — fall back to core/procedures/mem-archeo-git.md.
        """
        raise NotImplementedError(
            "mem_archeo_git is not yet ported to the MCP server (v0.8.x port in progress). "
            "Fall back to the skills procedure: see core/procedures/mem-archeo-git.md."
        )
