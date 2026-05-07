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
from memory_kit_mcp._console import force_utf8_console
from memory_kit_mcp.tools import register_all
from memory_kit_mcp.update_check import check_for_update, emit_update_log

# Reconfigure stderr to UTF-8 BEFORE logging.basicConfig captures the stream.
# Otherwise the StreamHandler keeps the default cp1252 stream on Windows and
# any unicode in a log line (e.g. accented French, '->' arrows in trace
# output, project names with accents) crashes the logger mid-write.
force_utf8_console()

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
    # Passive update check — cache makes this near-instant 99% of the time;
    # network errors are swallowed so the server always starts.
    try:
        emit_update_log(check_for_update(), log)
    except Exception:  # noqa: BLE001 — never let the check break startup
        pass
    mcp.run(transport="stdio")
