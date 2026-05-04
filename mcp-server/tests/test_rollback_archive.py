"""Tests for mem_rollback_archive."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.vault import frontmatter


async def test_rollback_deletes_latest_archive(client: Client, vault_tmp: Path) -> None:
    archive_file = (
        vault_tmp
        / "10-episodes"
        / "projects"
        / "alpha"
        / "archives"
        / "2026-04-30-14h00-alpha-initial.md"
    )
    assert archive_file.exists()
    res = await client.call_tool("mem_rollback_archive", {"slug": "alpha"})
    assert res.data.success is True
    assert not archive_file.exists()
    assert any(
        "2026-04-30-14h00-alpha-initial.md" in p for p in res.data.files_deleted
    )


async def test_rollback_strips_history_line(client: Client, vault_tmp: Path) -> None:
    history = vault_tmp / "10-episodes" / "projects" / "alpha" / "history.md"
    _, body_before = frontmatter.read(history)
    assert "2026-04-30-14h00-alpha-initial.md" in body_before
    await client.call_tool("mem_rollback_archive", {"slug": "alpha"})
    _, body_after = frontmatter.read(history)
    assert "2026-04-30-14h00-alpha-initial.md" not in body_after


async def test_rollback_no_archives_raises(client: Client) -> None:
    # shared-infra domain has no archives
    with pytest.raises(ToolError):
        await client.call_tool("mem_rollback_archive", {"slug": "shared-infra"})


async def test_rollback_unknown_slug_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool("mem_rollback_archive", {"slug": "nope"})
