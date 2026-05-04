"""mem_archeo_atlassian — Confluence + Jira retro-archive (skill fallback).

Spec: core/procedures/mem-archeo-atlassian.md

DESIGN DECISION (v0.8.x): kept as a skills-only stub.

The skills procedure delegates to the **client-side Atlassian MCP**
(`mcp__claude_ai_Atlassian__*` on Claude Code / Claude Desktop, equivalent
on other clients), which:
- Has authentication already configured via the user's Atlassian account.
- Exposes a richer surface (createJiraIssue, addCommentToJiraIssue,
  getConfluencePageDescendants, search across spaces, etc.) than a
  hand-rolled httpx port would replicate.
- Stays current with Atlassian's API evolution without us tracking it.

A native port would mean introducing httpx + auth Basic + env-var token
juggling (ATLASSIAN_TOKEN, ATLASSIAN_EMAIL, ATLASSIAN_SITE), wiring
mocks in tests, and duplicating an MCP that already exists — for no
appreciable user benefit. The right channel for Confluence/Jira is the
client-side MCP; the SecondBrain server's job is to receive and persist
the resulting atoms (which is what `mem_archive` and the ingestion
shortcuts already do).

The skills fallback in core/procedures/mem-archeo-atlassian.md remains
the canonical executor: it instructs the LLM client to enumerate pages
via the Atlassian MCP, build atom shells, and route them through the
vault writes which ARE ported (mem_archive, mem_doc, etc.).
"""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register mem_archeo_atlassian as an explicit skill-fallback stub."""

    @mcp.tool()
    def mem_archeo_atlassian(confluence_url: str | None = None) -> str:
        """Retro-archive a Confluence page tree + linked Jira tickets.

        SKILLS-ONLY (by design — the right channel is the client-side
        Atlassian MCP, not a duplicate REST port). Falls back to
        core/procedures/mem-archeo-atlassian.md.
        """
        raise NotImplementedError(
            "mem_archeo_atlassian is intentionally kept as a skills-only tool. "
            "The skills procedure delegates to the client-side Atlassian MCP "
            "(mcp__claude_ai_Atlassian__*), which has auth configured and a "
            "richer surface than a hand-rolled httpx port would replicate. "
            "Fall back to the skills procedure: see core/procedures/mem-archeo-atlassian.md."
        )
