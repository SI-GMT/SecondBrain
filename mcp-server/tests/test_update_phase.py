"""Tests for mem_update_phase — targeted phase frontmatter update."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastmcp import Client

from memory_kit_mcp.vault import frontmatter


async def test_updates_phase_and_bumps_last_session(
    client: Client, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_update_phase",
        {"slug": "alpha", "phase": "v0.9.3 in progress"},
    )
    d = res.data
    assert d.success is True
    assert d.skill == "mem_update_phase"
    assert any("alpha/context.md" in m for m in d.files_modified)

    fm, _ = frontmatter.read(
        vault_tmp / "10-episodes" / "projects" / "alpha" / "context.md"
    )
    assert fm["phase"] == "v0.9.3 in progress"
    assert fm["last-session"] == datetime.now().date().isoformat()


async def test_preserves_body_verbatim(client: Client, vault_tmp: Path) -> None:
    ctx_path = vault_tmp / "10-episodes" / "projects" / "alpha" / "context.md"
    _, body_before = frontmatter.read(ctx_path)
    await client.call_tool(
        "mem_update_phase",
        {"slug": "alpha", "phase": "phase-x"},
    )
    _, body_after = frontmatter.read(ctx_path)
    assert body_before == body_after, "body must not change"


async def test_empty_phase_clears_field(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem_update_phase",
        {"slug": "alpha", "phase": ""},
    )
    assert res.data.success is True
    fm, _ = frontmatter.read(
        vault_tmp / "10-episodes" / "projects" / "alpha" / "context.md"
    )
    assert fm["phase"] == ""


async def test_refuses_archived_project(client: Client, vault_tmp: Path) -> None:
    with pytest.raises(Exception) as ei:
        await client.call_tool(
            "mem_update_phase",
            {"slug": "legacy-app", "phase": "anything"},
        )
    assert "archived" in str(ei.value).lower()


async def test_unknown_slug_raises(client: Client) -> None:
    with pytest.raises(Exception):
        await client.call_tool(
            "mem_update_phase", {"slug": "nope", "phase": "x"}
        )
