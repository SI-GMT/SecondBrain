"""FastMCP server entry point for memory-kit.

Exposes the 24 mem_* tools over stdio. Launched by client CLIs (Claude Code,
Codex, Copilot CLI, ...) via their MCP config.

All logging goes to stderr — stdout is reserved for the JSON-RPC channel.
"""

from __future__ import annotations

import logging
import sys

from fastmcp import FastMCP

from memory_kit_mcp import __version__
from memory_kit_mcp.tools import register_all

# Stderr-only logging (stdout = JSON-RPC channel for MCP)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("memory_kit_mcp")

mcp: FastMCP = FastMCP("memory-kit")
register_all(mcp)


def main() -> None:
    """Console-script entry point — launches the stdio server."""
    log.info("memory-kit-mcp v%s starting on stdio", __version__)
    mcp.run(transport="stdio")
