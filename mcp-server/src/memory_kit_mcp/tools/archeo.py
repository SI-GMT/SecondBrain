"""mem_archeo — Triphasic archeo orchestrator.

Spec: core/procedures/mem-archeo.md

STUB (v0.8.x port in progress). Once Phases 2 and 3 are ported (archeo_stack,
archeo_git), this orchestrator will share a single Phase 0 topology scan
(via memory_kit_mcp.vault.topology_scanner) across both ported phases and
delegate Phase 1 (context) to the skill fallback.
"""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register mem_archeo orchestrator stub."""

    @mcp.tool()
    def mem_archeo(
        repo_path: str | None = None,
        branch_first: str | None = None,
    ) -> str:
        """Triphasic archeo orchestrator (Phase 1 context + Phase 2 stack + Phase 3 git).

        STUB v0.8.x — fall back to core/procedures/mem-archeo.md.
        """
        raise NotImplementedError(
            "mem_archeo orchestrator is not yet ported to the MCP server (v0.8.x port in progress). "
            "Fall back to the skills procedure: see core/procedures/mem-archeo.md."
        )
