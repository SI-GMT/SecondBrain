"""Tests for mem_historize — archive and revive flows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.vault import frontmatter


async def test_historize_archives_active_project(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool("mem_historize", {"slug": "alpha"})
    d = res.data
    assert d.success is True
    assert (vault_tmp / "10-episodes" / "archived" / "alpha" / "context.md").exists()
    assert not (vault_tmp / "10-episodes" / "projects" / "alpha").exists()
    fm, _ = frontmatter.read(
        vault_tmp / "10-episodes" / "archived" / "alpha" / "context.md"
    )
    assert fm["phase"] == "archived"
    assert fm["archived_at"] == datetime.now().date().isoformat()
    assert fm["display"].endswith("[archived]")


async def test_historize_idempotent_when_already_archived(client: Client) -> None:
    res = await client.call_tool("mem_historize", {"slug": "legacy-app"})
    d = res.data
    assert d.success is True
    assert any("already archived" in w for w in d.warnings)


async def test_historize_revive(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem_historize", {"slug": "legacy-app", "revive": True}
    )
    d = res.data
    assert d.success is True
    assert (vault_tmp / "10-episodes" / "projects" / "legacy-app").exists()
    assert not (vault_tmp / "10-episodes" / "archived" / "legacy-app").exists()
    fm, _ = frontmatter.read(
        vault_tmp / "10-episodes" / "projects" / "legacy-app" / "context.md"
    )
    assert "archived_at" not in fm
    assert fm.get("phase") != "archived"
    assert "[archived]" not in fm["display"]


async def test_historize_revive_idempotent_when_active(client: Client) -> None:
    res = await client.call_tool("mem_historize", {"slug": "alpha", "revive": True})
    assert res.data.success is True
    assert any("already active" in w for w in res.data.warnings)


async def test_historize_refuses_project_without_context(
    client: Client, vault_tmp: Path
) -> None:
    # beta has history.md + archives but no context.md
    with pytest.raises(ToolError):
        await client.call_tool("mem_historize", {"slug": "beta"})


async def test_historize_unknown_slug_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool("mem_historize", {"slug": "does-not-exist"})
