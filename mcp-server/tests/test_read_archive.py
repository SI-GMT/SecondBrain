"""Tests for mem_read_archive — read a specific archive file."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client

from memory_kit_mcp.vault import frontmatter


async def test_reads_existing_archive(client: Client, vault_tmp: Path) -> None:
    # Use the fixture archive 'alpha-initial' shipped with the vault skeleton
    archives = list(
        (vault_tmp / "10-episodes" / "projects" / "alpha" / "archives").glob("*.md")
    )
    assert archives, "fixture should contain at least one archive on alpha"
    archive_filename = archives[0].name

    res = await client.call_tool(
        "mem_read_archive",
        {"slug": "alpha", "filename": archive_filename},
    )
    d = res.data
    assert d.kind == "archive"
    assert d.slug == "alpha"
    assert archive_filename in d.path
    assert isinstance(d.frontmatter, dict)
    assert isinstance(d.body, str)
    assert len(d.body) > 0


async def test_accepts_filename_without_md_suffix(client: Client, vault_tmp: Path) -> None:
    archives = list(
        (vault_tmp / "10-episodes" / "projects" / "alpha" / "archives").glob("*.md")
    )
    stem = archives[0].stem
    res = await client.call_tool(
        "mem_read_archive", {"slug": "alpha", "filename": stem}
    )
    assert res.data.kind == "archive"


async def test_rejects_path_traversal(client: Client, vault_tmp: Path) -> None:
    with pytest.raises(Exception):
        await client.call_tool(
            "mem_read_archive",
            {"slug": "alpha", "filename": "../../etc/passwd"},
        )


async def test_unknown_slug_raises(client: Client) -> None:
    with pytest.raises(Exception):
        await client.call_tool(
            "mem_read_archive", {"slug": "nope", "filename": "anything.md"}
        )


async def test_unknown_filename_raises_with_suggestions(
    client: Client, vault_tmp: Path
) -> None:
    with pytest.raises(Exception) as ei:
        await client.call_tool(
            "mem_read_archive",
            {"slug": "alpha", "filename": "ghost-archive.md"},
        )
    # Suggestions should surface real archive names from the fixture
    assert "ghost-archive" in str(ei.value) or "available" in str(ei.value).lower()


async def test_works_on_archived_project(client: Client, vault_tmp: Path) -> None:
    """Per _archived.md, reads are allowed on archived projects."""
    archived = vault_tmp / "10-episodes" / "archived" / "legacy-app" / "archives"
    if not archived.is_dir():
        pytest.skip("fixture has no archived project with archives")
    files = list(archived.glob("*.md"))
    if not files:
        pytest.skip("archived project has no archives")
    res = await client.call_tool(
        "mem_read_archive",
        {"slug": "legacy-app", "filename": files[0].name},
    )
    assert res.data.kind == "archive"
