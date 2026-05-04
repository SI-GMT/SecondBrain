"""Tests for mem_search."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError


async def test_search_finds_text_in_active_project(client: Client) -> None:
    res = await client.call_tool("mem_search", {"query": "Demo project for the MCP"})
    d = res.data
    assert d.total_hits >= 1
    paths_hit = {h.path for h in d.hits}
    assert any("alpha" in p for p in paths_hit)


async def test_search_excludes_archived_by_default(client: Client) -> None:
    res = await client.call_tool("mem_search", {"query": "Archived demo project"})
    d = res.data
    # The string lives in 10-episodes/archived/legacy-app/context.md
    assert d.total_hits == 0
    for hit in d.hits:
        assert "archived" not in hit.path


async def test_search_with_include_archived(client: Client) -> None:
    res = await client.call_tool(
        "mem_search",
        {"query": "Archived demo project", "include_archived": True},
    )
    d = res.data
    assert d.total_hits >= 1
    assert any("archived/legacy-app" in h.path for h in d.hits)


async def test_search_zone_filter_restricts_scope(client: Client) -> None:
    res = await client.call_tool(
        "mem_search",
        {"query": "Topology", "zone": "99-meta"},
    )
    d = res.data
    assert d.total_hits >= 1
    for hit in d.hits:
        assert hit.zone == "99-meta"


async def test_search_case_insensitive_default(client: Client) -> None:
    upper = await client.call_tool("mem_search", {"query": "DEMO PROJECT"})
    lower = await client.call_tool("mem_search", {"query": "demo project"})
    assert upper.data.total_hits == lower.data.total_hits


async def test_search_case_sensitive_when_disabled(client: Client) -> None:
    res = await client.call_tool(
        "mem_search",
        {"query": "DEMO PROJECT", "case_insensitive": False},
    )
    # The fixture text is "Demo project", not "DEMO PROJECT"
    assert res.data.total_hits == 0


async def test_search_invalid_regex_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool("mem_search", {"query": "(unclosed"})


async def test_search_summary_md_groups_by_file(client: Client) -> None:
    res = await client.call_tool("mem_search", {"query": "alpha"})
    md = res.data.summary_md
    assert "## Search results for `alpha`" in md
    # Each unique file should produce a "### `path`" header
    assert md.count("### `") >= 1


async def test_search_limit_truncates_and_marks(client: Client) -> None:
    # "alpha" appears in many places; with limit=2 we should see truncated=True
    res = await client.call_tool("mem_search", {"query": "alpha", "limit": 2})
    d = res.data
    if d.total_hits > 2:
        assert d.truncated is True
        assert len(d.hits) == 2
