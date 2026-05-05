"""Tests for mem_read_context — read a project's context.md directly."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client


async def test_reads_existing_project_context(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool("mem_read_context", {"slug": "alpha"})
    d = res.data
    assert d.kind == "context"
    assert d.slug == "alpha"
    assert "context.md" in d.path
    assert isinstance(d.frontmatter, dict)
    assert isinstance(d.body, str)


async def test_unknown_slug_raises(client: Client) -> None:
    with pytest.raises(Exception):
        await client.call_tool("mem_read_context", {"slug": "ghost-project"})


async def test_works_on_domain(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool("mem_read_context", {"slug": "shared-infra"})
    assert res.data.kind == "context"
    assert res.data.slug == "shared-infra"


async def test_summary_surfaces_phase(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool("mem_read_context", {"slug": "alpha"})
    summary = res.data.summary_md
    assert "alpha" in summary
    # Phase or last-session must be referenced
    assert "Phase:" in summary or "Last session:" in summary
