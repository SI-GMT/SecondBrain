"""Tests for mem_reclass."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.vault import frontmatter


async def test_reclass_scope_only_patches_frontmatter(
    client: Client, vault_tmp: Path
) -> None:
    # Create a fresh atom under 40-principles/work/
    target = vault_tmp / "40-principles" / "work" / "demo-rule.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {"slug": "demo-rule", "scope": "work", "zone": "principles"},
        "# demo-rule\n",
    )

    res = await client.call_tool(
        "mem_reclass",
        {"path": "40-principles/work/demo-rule.md", "scope": "personal"},
    )
    d = res.data
    assert d.success is True
    # File moved because scope segment is rewritten
    new_path = vault_tmp / "40-principles" / "personal" / "demo-rule.md"
    assert new_path.exists()
    fm, _ = frontmatter.read(new_path)
    assert fm["scope"] == "personal"


async def test_reclass_zone_moves_file(client: Client, vault_tmp: Path) -> None:
    src = vault_tmp / "20-knowledge" / "concept.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(src, {"slug": "concept", "zone": "knowledge"}, "# Concept\n")

    res = await client.call_tool(
        "mem_reclass",
        {"path": "20-knowledge/concept.md", "zone": "30-procedures"},
    )
    assert res.data.success is True
    assert (vault_tmp / "30-procedures" / "concept.md").exists()
    assert not src.exists()


async def test_reclass_requires_scope_or_zone(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_reclass", {"path": "10-episodes/projects/alpha/context.md"}
        )


async def test_reclass_invalid_scope_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_reclass",
            {"path": "10-episodes/projects/alpha/context.md", "scope": "bogus"},
        )


async def test_reclass_unknown_path_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_reclass", {"path": "does/not/exist.md", "scope": "work"}
        )
