"""mem_archeo_context — Phase 1 of the triphasic archeo (skill fallback).

Spec: core/procedures/mem-archeo-context.md

DESIGN DECISION (v0.8.x): kept as a stub. The Phase 1 procedure pivots on
**semantic extraction** — for each document of the repo, identify spans that
fit one of seven categories (workflow / sync / multi-tenant / security / adr /
goal / other), then forge a coherent subject (≤60 chars) and body for each
detected span. This is LLM-side classification, not Python heuristic territory:
a rules-based detector would only catch ~10% of real cases.

The mechanical parts of the procedure (slug resolution, idempotence checks,
atomic writes, topology persistence) are useful primitives but they're not the
substance of Phase 1 — the substance is the categorization itself. Porting only
the mechanical parts would deliver an empty shell.

The skills fallback in core/procedures/mem-archeo-context.md remains the
canonical executor for Phase 1. The orchestrator (mem_archeo) skips Phase 1
when it runs in MCP mode and falls back to the skills procedure.

Phase 0 (topology scan) IS ported — it's deterministic — see
memory_kit_mcp.vault.topology_scanner. Phases 2 (stack) and 3 (git) are also
ported, see archeo_stack.py and archeo_git.py.
"""

from __future__ import annotations

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register mem_archeo_context as an explicit skill-fallback stub."""

    @mcp.tool()
    def mem_archeo_context(repo_path: str | None = None) -> str:
        """Phase 1 of the triphasic archeo: organizational/decisional/functional context extraction.

        SKILLS-ONLY (by design — semantic categorization is LLM territory).
        Falls back to core/procedures/mem-archeo-context.md.
        """
        raise NotImplementedError(
            "mem_archeo_context is intentionally kept as a skills-only tool. "
            "Phase 1 requires semantic classification of document spans into "
            "seven categories — that's LLM-side work, not Python heuristics. "
            "Fall back to the skills procedure: see core/procedures/mem-archeo-context.md."
        )
