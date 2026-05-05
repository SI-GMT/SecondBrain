"""Tests for mem_read_history — read a project's history.md directly."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client


async def test_reads_existing_project_history(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool("mem_read_history", {"slug": "alpha"})
    d = res.data
    assert d.kind == "history"
    assert d.slug == "alpha"
    assert "history.md" in d.path
    assert isinstance(d.frontmatter, dict)
    assert isinstance(d.body, str)


async def test_summary_counts_entries(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool("mem_read_history", {"slug": "alpha"})
    assert "entries detected" in res.data.summary_md


async def test_unknown_slug_raises(client: Client) -> None:
    with pytest.raises(Exception):
        await client.call_tool("mem_read_history", {"slug": "ghost-project"})
