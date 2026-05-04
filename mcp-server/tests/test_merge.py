"""Tests for mem_merge."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.vault import frontmatter


async def test_merge_moves_archives_and_deletes_source(
    client: Client, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_merge", {"source_slug": "beta", "target_slug": "alpha"}
    )
    d = res.data
    assert d.success is True
    # Source folder deleted
    assert not (vault_tmp / "10-episodes" / "projects" / "beta").exists()
    # Beta's archive moved into alpha/archives/ with retagged frontmatter
    moved = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives" / "2026-04-29-10h00-beta-only.md"
    assert moved.exists()
    fm, _ = frontmatter.read(moved)
    assert fm["project"] == "alpha"
    assert fm["slug"] == "alpha"
    assert "project/alpha" in fm["tags"]
    assert "project/beta" not in fm["tags"]


async def test_merge_same_slug_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_merge", {"source_slug": "alpha", "target_slug": "alpha"}
        )


async def test_merge_kind_mismatch_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_merge", {"source_slug": "alpha", "target_slug": "shared-infra"}
        )


async def test_merge_unknown_source_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_merge", {"source_slug": "nope", "target_slug": "alpha"}
        )


async def test_merge_unknown_target_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_merge", {"source_slug": "alpha", "target_slug": "nope"}
        )
