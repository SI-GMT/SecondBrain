"""Tests for mem_archive — incremental and full modes + archived refuse."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.vault import frontmatter


async def test_archive_incremental_rewrites_context(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "incremental",
            "context_md": "# Alpha — new context\n\nFresh state here.\n",
        },
    )
    d = res.data
    assert d.success is True
    assert d.skill == "mem_archive"
    assert any("context.md" in m for m in d.files_modified)

    fm, body = frontmatter.read(vault_tmp / "10-episodes" / "projects" / "alpha" / "context.md")
    assert "Fresh state here" in body
    assert fm["last-session"] == datetime.now().date().isoformat()


async def test_archive_incremental_can_set_phase(client: Client, vault_tmp: Path) -> None:
    await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "incremental",
            "context_md": "stub",
            "phase": "v0.8.0 in progress",
        },
    )
    fm, _ = frontmatter.read(vault_tmp / "10-episodes" / "projects" / "alpha" / "context.md")
    assert fm["phase"] == "v0.8.0 in progress"


async def test_archive_incremental_does_not_create_archive(
    client: Client, vault_tmp: Path
) -> None:
    archives_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    before = sorted(archives_dir.glob("*.md"))
    await client.call_tool(
        "mem_archive",
        {"slug": "alpha", "mode": "incremental", "context_md": "stub"},
    )
    after = sorted(archives_dir.glob("*.md"))
    assert before == after, "incremental mode must NOT create a new archive"


async def test_archive_full_creates_archive_history_and_resets_context(
    client: Client, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "full",
            "context_md": "Reset context post-session.",
            "archive_subject": "POC mem_archive end-to-end",
            "archive_body_md": "# Session — mem_archive POC\n\nFull mode test.\n",
            "phase": "post-archive",
        },
    )
    d = res.data
    assert d.success is True
    assert len(d.files_created) == 1
    assert "archives/" in d.files_created[0].replace("\\", "/")

    archives_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    new_archives = list(archives_dir.glob("*-poc-mem-archive-end-to-end.md"))
    assert len(new_archives) == 1
    fm, body = frontmatter.read(new_archives[0])
    assert fm["kind"] == "archive"
    assert fm["slug"] == "alpha"
    assert "Full mode test" in body

    # history.md got the new entry prepended after the H1
    h_fm, h_body = frontmatter.read(
        vault_tmp / "10-episodes" / "projects" / "alpha" / "history.md"
    )
    assert "POC mem_archive end-to-end" in h_body
    assert "archives/" in h_body

    # context.md was reset
    ctx_fm, ctx_body = frontmatter.read(
        vault_tmp / "10-episodes" / "projects" / "alpha" / "context.md"
    )
    assert "Reset context post-session" in ctx_body
    assert ctx_fm["phase"] == "post-archive"


async def test_archive_refuses_archived_project(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_archive",
            {"slug": "legacy-app", "mode": "incremental", "context_md": "stub"},
        )


async def test_archive_unknown_slug_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_archive",
            {"slug": "nope", "mode": "incremental", "context_md": "stub"},
        )


async def test_archive_full_requires_subject_and_body(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_archive",
            {"slug": "alpha", "mode": "full", "context_md": "stub"},
        )


async def test_archive_full_on_domain(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem_archive",
        {
            "slug": "shared-infra",
            "mode": "full",
            "context_md": "Updated domain context.",
            "archive_subject": "domain session",
            "archive_body_md": "Domain archive body.",
        },
    )
    assert res.data.success is True
    archives = list(
        (vault_tmp / "10-episodes" / "domains" / "shared-infra" / "archives").glob(
            "*-domain-session.md"
        )
    )
    assert len(archives) == 1
