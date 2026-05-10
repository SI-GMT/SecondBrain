"""Minimal one-shot JSON-RPC client for the Memory Kit MCP server.

We intentionally keep this lean instead of pulling the full ``mcp`` Python
SDK as a dependency:

* PyInstaller bundles stay small (no ``mcp`` + httpx + pydantic-settings tail).
* No persistent connection management — every desktop action is a discrete
  user-triggered request, so spawning the binary fresh and tearing it down
  is the right shape and matches the engine's stdio-per-connection design.

Protocol references:

* ``initialize`` / ``initialized`` — required handshake before any tool call.
* ``tools/call`` — invoke a tool with structured arguments, get a structured
  response. Errors come back either as JSON-RPC errors (transport failure)
  or as ``isError: true`` content blocks (tool-level failure).

If the binary cannot be located the helpers return :class:`McpUnavailable`
instead of raising — callers render that as a "kit not installed" UX state
rather than a stack trace.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from .engine import locate_binary

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60
PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "sb-desktop"


@dataclass(frozen=True, slots=True)
class McpUnavailable:
    """Returned when the engine binary can't be located."""

    reason: str = "memory-kit-mcp binary not found"


@dataclass(frozen=True, slots=True)
class McpError:
    """Transport-level or tool-level failure with a human-readable message."""

    message: str
    detail: str | None = None
    transport: bool = False


@dataclass(frozen=True, slots=True)
class McpResponse:
    """Successful tool invocation response."""

    structured: dict[str, Any] | None
    text: str
    raw: dict[str, Any]
    elapsed_ms: float


def _frame_request(method: str, params: dict[str, Any], request_id: int) -> bytes:
    msg = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }
    return (json.dumps(msg) + "\n").encode("utf-8")


def _frame_notification(method: str, params: dict[str, Any]) -> bytes:
    msg = {"jsonrpc": "2.0", "method": method, "params": params}
    return (json.dumps(msg) + "\n").encode("utf-8")


def _build_payload(tool: str, arguments: dict[str, Any]) -> bytes:
    init = _frame_request(
        "initialize",
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": CLIENT_NAME, "version": "0.1.0"},
        },
        request_id=1,
    )
    initialized = _frame_notification("notifications/initialized", {})
    call = _frame_request(
        "tools/call",
        {"name": tool, "arguments": arguments},
        request_id=2,
    )
    return init + initialized + call


def _parse_responses(raw: str) -> dict[int, dict[str, Any]]:
    """Group JSON-RPC responses by id (drop notifications and partials)."""
    responses: dict[int, dict[str, Any]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        rid = obj.get("id")
        if isinstance(rid, int):
            responses[rid] = obj
    return responses


def _extract_text(content: list[dict[str, Any]]) -> str:
    chunks = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def call_tool(
    tool: str,
    arguments: dict[str, Any] | None = None,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> McpResponse | McpError | McpUnavailable:
    """Issue a one-shot ``tools/call`` against the engine.

    ``timeout`` covers the entire spawn + handshake + call + drain cycle.
    Raise nothing; callers branch on the returned variant.
    """
    binary = locate_binary()
    if binary is None:
        return McpUnavailable()

    payload = _build_payload(tool, arguments or {})
    started = time.perf_counter()

    try:
        completed = subprocess.run(
            [str(binary)],
            input=payload,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return McpError(message=f"tool '{tool}' timed out after {timeout}s", transport=True)
    except OSError as exc:
        return McpError(message=f"failed to spawn engine: {exc}", transport=True)

    elapsed_ms = (time.perf_counter() - started) * 1000

    stdout = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
    stderr = completed.stderr.decode("utf-8", errors="replace") if completed.stderr else ""

    if completed.returncode != 0 and not stdout.strip():
        return McpError(
            message=f"engine exited with code {completed.returncode}",
            detail=stderr[:500] or None,
            transport=True,
        )

    responses = _parse_responses(stdout)
    init_response = responses.get(1)
    call_response = responses.get(2)

    if init_response is None:
        return McpError(
            message="engine never replied to initialize",
            detail=stderr[:500] or None,
            transport=True,
        )
    if "error" in init_response:
        return McpError(
            message="initialize handshake refused",
            detail=json.dumps(init_response["error"]),
            transport=True,
        )
    if call_response is None:
        return McpError(message=f"engine never replied to tools/call '{tool}'", transport=True)
    if "error" in call_response:
        err = call_response["error"]
        return McpError(
            message=err.get("message", f"tool '{tool}' transport error"),
            detail=json.dumps(err),
            transport=True,
        )

    result = call_response.get("result")
    if not isinstance(result, dict):
        return McpError(message=f"tool '{tool}' returned malformed result", transport=True)

    if result.get("isError"):
        text = _extract_text(result.get("content", []))
        return McpError(message=f"tool '{tool}' failed", detail=text or None)

    structured = result.get("structuredContent")
    text = _extract_text(result.get("content", []))

    return McpResponse(
        structured=structured if isinstance(structured, dict) else None,
        text=text,
        raw=result,
        elapsed_ms=elapsed_ms,
    )
