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
    list as list_tool,
    recall,
    search,
)


def register_all(mcp: FastMCP) -> None:
    """Register every mem_* tool with the FastMCP instance."""
    recall.register(mcp)
    archive.register(mcp)
    list_tool.register(mcp)
    search.register(mcp)
    digest.register(mcp)
    # Other tools will be registered here as they are implemented (chunks 7-10).
