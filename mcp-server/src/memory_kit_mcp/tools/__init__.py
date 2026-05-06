"""Tool registration for the memory-kit MCP server.

Each tool lives in its own module under tools/. The register_all() function
applies all @mcp.tool() decorators to the FastMCP instance at startup. Adding
a new tool means: (1) write tools/X.py with a register(mcp) function, then (2)
import X here and call X.register(mcp).
"""

from __future__ import annotations

from fastmcp import FastMCP

from memory_kit_mcp.tools import (
    archeo,
    archeo_atlassian,
    archeo_context,
    archeo_context_finalize,
    archeo_git,
    archeo_stack,
    archive,
    digest,
    doc,
    get_topology,
    goal,
    health_repair,
    health_scan,
    historize,
    ingest,
    init_project,
    list as list_tool,
    merge,
    migrate,
    note,
    person,
    principle,
    promote_domain,
    read_archive,
    read_context,
    read_history,
    recall,
    reclass,
    rename,
    rollback_archive,
    search,
    update_phase,
)


def register_all(mcp: FastMCP) -> None:
    """Register every mem_* tool with the FastMCP instance."""
    # Cycle session
    recall.register(mcp)
    archive.register(mcp)
    # Inventory
    list_tool.register(mcp)
    search.register(mcp)
    digest.register(mcp)
    # Vault management
    init_project.register(mcp)
    rename.register(mcp)
    merge.register(mcp)
    reclass.register(mcp)
    rollback_archive.register(mcp)
    promote_domain.register(mcp)
    historize.register(mcp)
    update_phase.register(mcp)
    # Direct file readers (v0.9.3 — bridge for MCP-only CLI clients)
    read_archive.register(mcp)
    read_context.register(mcp)
    read_history.register(mcp)
    get_topology.register(mcp)
    # Hygiene
    health_scan.register(mcp)
    health_repair.register(mcp)
    # Schema migrations (v0.9.4)
    migrate.register(mcp)
    # Ingestion
    note.register(mcp)
    principle.register(mcp)
    goal.register(mcp)
    person.register(mcp)
    ingest.register(mcp)
    doc.register(mcp)
    # Archeo (one module per tool — v0.8.x progressive port).
    # mem_archeo_context stays as a skills-only stub by design (semantic LLM work).
    # The other phases are being ported one by one onto topology_scanner.
    archeo.register(mcp)
    archeo_context.register(mcp)
    archeo_context_finalize.register(mcp)
    archeo_stack.register(mcp)
    archeo_git.register(mcp)
    archeo_atlassian.register(mcp)
