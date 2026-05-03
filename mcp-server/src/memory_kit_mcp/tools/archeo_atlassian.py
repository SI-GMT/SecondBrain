"""mem_archeo_atlassian — Confluence + Jira retro-archive.

Spec: core/procedures/mem-archeo-atlassian.md

STUB (v0.8.x — port deferred). The skills procedure relies on the client-side
Atlassian MCP (Claude Code / Claude Desktop), which the Python server cannot
invoke. Two paths are open for a native port:

1. Direct REST via httpx + auth Basic (env vars ATLASSIAN_TOKEN, ATLASSIAN_EMAIL,
   ATLASSIAN_SITE) — feasible but adds a dependency and a credential burden.
2. Keep skills-only — the client-side MCP is already the right channel.

Decision pending: see the v0.8.x roadmap.
"""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register mem_archeo_atlassian stub."""

    @mcp.tool()
    def mem_archeo_atlassian(confluence_url: str | None = None) -> str:
        """Retro-archive a Confluence page tree + linked Jira tickets.

        STUB v0.8.x — fall back to core/procedures/mem-archeo-atlassian.md.
        """
        raise NotImplementedError(
            "mem_archeo_atlassian is not yet ported to the MCP server. "
            "The skills procedure delegates to the client-side Atlassian MCP. "
            "Fall back to the skills procedure: see core/procedures/mem-archeo-atlassian.md."
        )
