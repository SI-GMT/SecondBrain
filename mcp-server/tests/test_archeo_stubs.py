"""Tests for the archeo stubs — verify they're registered and surface a clear fallback message."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

ARCHEO_TOOLS = [
    "mem_archeo",
    "mem_archeo_context",
    "mem_archeo_stack",
    "mem_archeo_git",
    "mem_archeo_atlassian",
]

# Tools still in stub mode (raise NotImplementedError). Updated as ports land.
STILL_STUB_TOOLS = [
    "mem_archeo_context",
    "mem_archeo_atlassian",
]


@pytest.mark.parametrize("tool_name", STILL_STUB_TOOLS)
async def test_archeo_stub_raises_with_fallback_message(
    client: Client, tool_name: str
) -> None:
    with pytest.raises(ToolError) as exc_info:
        await client.call_tool(tool_name, {})
    msg = str(exc_info.value).lower()
    assert "skills" in msg or "fallback" in msg or "core/procedures" in msg


async def test_all_archeo_tools_appear_in_inventory(client: Client) -> None:
    tools = await client.list_tools()
    tool_names = {t.name for t in tools}
    for name in ARCHEO_TOOLS:
        assert name in tool_names, f"{name} missing from MCP inventory"


async def test_total_tool_count_is_24(client: Client) -> None:
    """Sanity check: the v0.8.0 milestone is 24 mem_* tools registered."""
    tools = await client.list_tools()
    mem_tools = [t for t in tools if t.name == "mem" or t.name.startswith("mem_")]
    assert len(mem_tools) == 24, f"expected 24 mem_* tools, got {len(mem_tools)}: {[t.name for t in mem_tools]}"
