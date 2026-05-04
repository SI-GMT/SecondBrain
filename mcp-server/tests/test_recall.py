"""Tests for mem_recall — the first POC tool of the memory-kit MCP server.

CallToolResult.data is a Pydantic Root model: access fields via attributes
(res.data.project), not dict subscripts. structured_content is also available
as the raw dict {"result": {...}} for cases where attribute access is awkward.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client


async def test_recall_with_known_project_returns_briefing(client: Client) -> None:
    res = await client.call_tool("mem_recall", {"slug": "alpha"})
    d = res.data
    assert d.project == "alpha"
    assert d.kind == "project"
    assert d.archived is False
    assert d.phase == "in-progress (demo fixture)"
    assert d.last_session == "2026-04-30"
    assert "## Resume — alpha (project)" in d.briefing_md
    assert "Demo project for the MCP server tests" in d.briefing_md


async def test_recall_loads_topology_when_present(client: Client) -> None:
    res = await client.call_tool("mem_recall", {"slug": "alpha"})
    assert res.data.topology_present is True
    assert "Topology captured" in res.data.briefing_md


async def test_recall_falls_back_to_last_archive_when_no_context(client: Client) -> None:
    res = await client.call_tool("mem_recall", {"slug": "beta"})
    d = res.data
    assert d.project == "beta"
    assert d.phase == "paused"
    assert d.last_session == "2026-04-29"
    assert d.topology_present is False
    assert "Topology not yet captured" in d.briefing_md


async def test_recall_archived_project_requires_explicit_slug(client: Client) -> None:
    res = await client.call_tool("mem_recall", {"slug": "legacy-app"})
    d = res.data
    assert d.project == "legacy-app"
    assert d.archived is True
    assert d.archived_at == "2026-01-15"
    assert "archived" in d.briefing_md.lower()
    assert "/mem-historize legacy-app --revive" in d.briefing_md


async def test_recall_resolves_domain(client: Client) -> None:
    res = await client.call_tool("mem_recall", {"slug": "shared-infra"})
    d = res.data
    assert d.project == "shared-infra"
    assert d.kind == "domain"
    assert d.archived is False


async def test_recall_unknown_slug_raises(client: Client) -> None:
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await client.call_tool("mem_recall", {"slug": "does-not-exist"})


async def test_recall_without_slug_returns_inventory(client: Client) -> None:
    res = await client.call_tool("mem_recall", {})
    d = res.data
    assert d.needs_disambiguation is True
    slugs = {p.slug for p in d.projects}
    assert slugs == {"alpha", "beta"}
    domain_slugs = {x.slug for x in d.domains}
    assert domain_slugs == {"shared-infra"}
    assert d.archived_count == 1
    assert "Multiple candidates" in d.message


async def test_recall_empty_vault_returns_helpful_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Independent test (no vault_tmp fixture) — empty vault path."""
    from memory_kit_mcp.config import get_config
    from memory_kit_mcp.server import mcp

    empty_vault = tmp_path / "empty-vault"
    empty_vault.mkdir()
    config_dir = tmp_path / ".memory-kit"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({"vault": str(empty_vault), "language": "en"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MEMORY_KIT_HOME", str(config_dir))
    get_config.cache_clear()

    async with Client(mcp) as c:
        res = await c.call_tool("mem_recall", {})
        d = res.data
        assert d.needs_disambiguation is True
        assert d.projects == []
        assert d.domains == []
        assert d.archived_count == 0
        assert "No project/domain found" in d.message

    get_config.cache_clear()
