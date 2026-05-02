"""Tests for mem_digest."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError


async def test_digest_returns_recent_archives(client: Client) -> None:
    res = await client.call_tool("mem_digest", {"slug": "alpha"})
    d = res.data
    assert d.project == "alpha"
    assert d.kind == "project"
    assert d.archives_total == 1
    assert d.archives_returned == 1
    assert d.archives[0].filename == "2026-04-30-14h00-alpha-initial.md"
    assert d.archives[0].date == "2026-04-30"
    assert "initial" in d.archives[0].subject
    assert "Initial archive" in d.archives[0].body_excerpt


async def test_digest_summary_md_renders_chronological(client: Client) -> None:
    res = await client.call_tool("mem_digest", {"slug": "alpha"})
    md = res.data.summary_md
    assert "## Digest — alpha (project)" in md
    assert "2026-04-30" in md


async def test_digest_n_caps_returned_archives(client: Client) -> None:
    # alpha has only 1 archive — n=10 should still return 1
    res = await client.call_tool("mem_digest", {"slug": "alpha", "n": 10})
    assert res.data.archives_returned == 1


async def test_digest_unknown_slug_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool("mem_digest", {"slug": "does-not-exist"})


async def test_digest_archived_refused_by_default(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool("mem_digest", {"slug": "legacy-app"})


async def test_digest_archived_with_override(client: Client) -> None:
    res = await client.call_tool(
        "mem_digest", {"slug": "legacy-app", "from_archived": True}
    )
    # legacy-app fixture has no archives/ folder
    assert res.data.archives_total == 0
    assert res.data.archives_returned == 0
    assert "(no archives yet)" in res.data.summary_md


async def test_digest_on_domain(client: Client) -> None:
    res = await client.call_tool("mem_digest", {"slug": "shared-infra"})
    d = res.data
    assert d.project == "shared-infra"
    assert d.kind == "domain"
    assert d.archives_total == 0
