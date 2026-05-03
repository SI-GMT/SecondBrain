"""mem_archeo* — Stub registrations for the 5 archeo tools.

The full archeo toolchain (orchestrator + Phase 1 context + Phase 2 stack +
Phase 3 git + Atlassian) involves repo scanning, manifest parsing, git log
walking, and Confluence/Jira REST integration. That work is deferred to
v0.8.x — see core/procedures/mem-archeo*.md for the canonical specs.

For v0.8.0, these stubs:
- Are registered in the MCP server so the tool inventory shows all 24 tools.
- Raise NotImplementedError with a clear message instructing the LLM to fall
  back to the skills procedure (which delegates to the existing scripts and
  procedures in the kit).

Pattern MCP-first/skills-fallback (cf. doc d'archi v0.8.0 §9): when the MCP
tool is unavailable OR raises an explicit NotImplementedError, the LLM
re-runs the procedure body from core/procedures/.
"""

from __future__ import annotations

from fastmcp import FastMCP

_FALLBACK_MSG = (
    "{tool} is not yet ported to the MCP server (v0.8.0 POC scope). "
    "Fall back to the skills procedure: see core/procedures/{spec}.md. "
    "The skill embeds the full procedure and will execute it locally."
)


def register(mcp: FastMCP) -> None:
    """Register the 5 archeo tools as stubs that raise NotImplementedError."""

    @mcp.tool()
    def mem_archeo(repo_path: str | None = None, branch_first: str | None = None) -> str:
        """Triphasic archeo orchestrator (Phase 1 context + Phase 2 stack + Phase 3 git).

        STUB v0.8.0 — full implementation deferred to v0.8.x. The skills
        fallback in core/procedures/mem-archeo.md remains fully operational.
        """
        raise NotImplementedError(
            _FALLBACK_MSG.format(tool="mem_archeo", spec="mem-archeo")
        )

    @mcp.tool()
    def mem_archeo_context(repo_path: str | None = None) -> str:
        """Phase 1 of the triphasic archeo: organizational/decisional/functional context.

        STUB v0.8.0 — fall back to core/procedures/mem-archeo-context.md.
        """
        raise NotImplementedError(
            _FALLBACK_MSG.format(tool="mem_archeo_context", spec="mem-archeo-context")
        )

    @mcp.tool()
    def mem_archeo_stack(repo_path: str | None = None) -> str:
        """Phase 2 of the triphasic archeo: technical stack resolution.

        STUB v0.8.0 — fall back to core/procedures/mem-archeo-stack.md.
        """
        raise NotImplementedError(
            _FALLBACK_MSG.format(tool="mem_archeo_stack", spec="mem-archeo-stack")
        )

    @mcp.tool()
    def mem_archeo_git(repo_path: str | None = None) -> str:
        """Phase 3 of the triphasic archeo: Git history reconstruction.

        STUB v0.8.0 — fall back to core/procedures/mem-archeo-git.md.
        """
        raise NotImplementedError(
            _FALLBACK_MSG.format(tool="mem_archeo_git", spec="mem-archeo-git")
        )

    @mcp.tool()
    def mem_archeo_atlassian(confluence_url: str | None = None) -> str:
        """Retro-archive a Confluence page tree + linked Jira tickets.

        STUB v0.8.0 — fall back to core/procedures/mem-archeo-atlassian.md.
        """
        raise NotImplementedError(
            _FALLBACK_MSG.format(tool="mem_archeo_atlassian", spec="mem-archeo-atlassian")
        )
