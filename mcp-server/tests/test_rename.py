"""Tests for mem_rename."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.vault import frontmatter


async def test_rename_project_moves_folder_and_patches_frontmatter(
    client: Client, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_rename", {"old_slug": "alpha", "new_slug": "alpha-renamed"}
    )
    d = res.data
    assert d.success is True
    new_folder = vault_tmp / "10-episodes" / "projects" / "alpha-renamed"
    assert new_folder.exists()
    assert not (vault_tmp / "10-episodes" / "projects" / "alpha").exists()

    fm, _ = frontmatter.read(new_folder / "context.md")
    assert fm["slug"] == "alpha-renamed"
    assert fm["project"] == "alpha-renamed"
    assert "project/alpha-renamed" in fm["tags"]
    assert "project/alpha" not in fm["tags"]


async def test_rename_domain(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem_rename", {"old_slug": "shared-infra", "new_slug": "infra-shared"}
    )
    assert res.data.success is True
    assert (vault_tmp / "10-episodes" / "domains" / "infra-shared").exists()
    fm, _ = frontmatter.read(
        vault_tmp / "10-episodes" / "domains" / "infra-shared" / "context.md"
    )
    assert fm["slug"] == "infra-shared"
    assert fm["domain"] == "infra-shared"


async def test_rename_identical_slugs_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_rename", {"old_slug": "alpha", "new_slug": "alpha"}
        )


async def test_rename_collision_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_rename", {"old_slug": "alpha", "new_slug": "beta"}
        )


async def test_rename_unknown_slug_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_rename", {"old_slug": "does-not-exist", "new_slug": "anything"}
        )


async def test_rename_emits_wikilink_warning(client: Client) -> None:
    res = await client.call_tool(
        "mem_rename", {"old_slug": "alpha", "new_slug": "alpha-v2"}
    )
    assert any("Wikilinks" in w for w in res.data.warnings)
