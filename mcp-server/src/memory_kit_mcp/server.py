"""FastMCP server entry point for memory-kit.

Exposes the mem_* tools over stdio. Launched by client CLIs (Claude Code,
Codex, Copilot CLI, ...) via their MCP config.

All logging goes to stderr — stdout is reserved for the JSON-RPC channel.

The MCP ``initialize`` handshake sets ``serverInfo`` (name, version) and
``instructions`` — clients display the latter to the LLM as part of the
session-start system context. We use it to surface an update-available
banner so the user sees release notifications **at CLI launch**, without
having to invoke any tool. The banner is computed at module-import time
(once per server boot, which is once per CLI session for stdio).
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


def _build_instructions() -> str:
    """Compose the MCP serverInfo.instructions string.

    Returned string is sent at the MCP ``initialize`` handshake. Per MCP
    spec the field is intended as LLM-side session context — clients are
    not required to surface it to the user, and LLMs treat it as untrusted
    by default (it cannot reliably force a user-visible banner). The
    actual update notification is surfaced through tool results
    (``mem_recall`` and ``mem_help``), which IS user-visible because the
    LLM relays tool output. We still mention the available update here so
    the LLM has the context if it needs to answer a question about it.
    """
    base = (
        "Memory Kit MCP — persistent vault for SecondBrain. "
        "All `mem_*` tools operate against the local Markdown vault "
        "configured in `~/.memory-kit/config.json`."
    )
    try:
        info = check_for_update()
        if info.update_available and info.latest_version:
            note = (
                f" Note: a newer release is available "
                f"(v{info.latest_version}, installed v{info.current_version}); "
                "the user will see the banner the next time they invoke "
                "`mem_recall` or `mem_help`."
            )
            return f"{base}{note}"
    except Exception:  # noqa: BLE001 — never let the check break boot
        pass
    return base


mcp: FastMCP = FastMCP(
    "memory-kit",
    instructions=_build_instructions(),
    version=__version__,
)
register_all(mcp)


def main() -> None:
    """Console-script entry point — launches the stdio server."""
    log.info("memory-kit-mcp v%s starting on stdio", __version__)
    # Passive update check — cache makes this near-instant 99% of the time;
    # network errors are swallowed so the server always starts. The banner
    # also lands in the stderr log via emit_update_log for the dev/operator
    # who tails the MCP log file.
    try:
        emit_update_log(check_for_update(), log)
    except Exception:  # noqa: BLE001 — never let the check break startup
        pass
    mcp.run(transport="stdio")
