"""Tests for mem_init_project — bootstrap empty project / domain."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client

from memory_kit_mcp.vault import frontmatter


async def test_creates_project_skeleton(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem_init_project",
        {"slug": "neoproject", "kind": "project", "scope": "work"},
    )
    d = res.data
    assert d.success is True
    assert d.skill == "mem_init_project"
    assert any("neoproject/context.md" in f for f in d.files_created)
    assert any("neoproject/history.md" in f for f in d.files_created)
    assert any("neoproject/archives/.gitkeep" in f for f in d.files_created)

    folder = vault_tmp / "10-episodes" / "projects" / "neoproject"
    assert folder.is_dir()
    assert (folder / "archives").is_dir()
    assert (folder / "archives" / ".gitkeep").is_file()

    fm, body = frontmatter.read(folder / "context.md")
    assert fm["slug"] == "neoproject"
    assert fm["scope"] == "work"
    assert fm["zone"] == "episodes"
    assert fm["kind"] == "project"
    assert fm["phase"] == "initial"
    assert "Active context" in body


async def test_creates_domain_skeleton(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem_init_project",
        {"slug": "transverse-tech", "kind": "domain", "display": "Transverse Tech"},
    )
    assert res.data.success is True
    folder = vault_tmp / "10-episodes" / "domains" / "transverse-tech"
    assert folder.is_dir()
    fm, _ = frontmatter.read(folder / "context.md")
    assert fm["kind"] == "domain"
    assert fm["display"] == "Transverse Tech — context"


async def test_refuses_existing_project(client: Client, vault_tmp: Path) -> None:
    """Active project 'alpha' is already in the vault fixture."""
    with pytest.raises(Exception) as ei:
        await client.call_tool("mem_init_project", {"slug": "alpha"})
    assert "already exists" in str(ei.value)


async def test_refuses_path_traversal_in_slug(client: Client, vault_tmp: Path) -> None:
    with pytest.raises(Exception):
        await client.call_tool("mem_init_project", {"slug": "../escape"})


async def test_carries_repo_path_when_provided(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem_init_project",
        {"slug": "withrepo", "repo_path": "/path/to/withrepo"},
    )
    assert res.data.success is True
    fm, _ = frontmatter.read(
        vault_tmp / "10-episodes" / "projects" / "withrepo" / "context.md"
    )
    assert fm["repo_path"] == "/path/to/withrepo"
    assert fm["workspace_member"] == ""


async def test_history_skeleton_is_well_formed(client: Client, vault_tmp: Path) -> None:
    await client.call_tool("mem_init_project", {"slug": "fresh"})
    fm, body = frontmatter.read(
        vault_tmp / "10-episodes" / "projects" / "fresh" / "history.md"
    )
    assert fm["slug"] == "fresh"
    assert "Historique des sessions" in body
    assert "no sessions yet" in body
