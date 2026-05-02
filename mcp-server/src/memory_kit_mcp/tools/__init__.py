"""Tool registration for the memory-kit MCP server.

Each tool lives in its own module under tools/. The register_all() function
applies all @mcp.tool() decorators to the FastMCP instance at startup. Adding
a new tool means: (1) write tools/X.py with a register(mcp) function, then (2)
import X here and call X.register(mcp).
"""

from __future__ import annotations

from fastmcp import FastMCP

from memory_kit_mcp.tools import (
    archive,
    digest,
    historize,
    list as list_tool,
    merge,
    promote_domain,
    recall,
    reclass,
    rename,
    rollback_archive,
    search,
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
    rename.register(mcp)
    merge.register(mcp)
    reclass.register(mcp)
    rollback_archive.register(mcp)
    promote_domain.register(mcp)
    historize.register(mcp)
    # Hygiene + ingestion + archeo will be registered here in chunks 8-10.
