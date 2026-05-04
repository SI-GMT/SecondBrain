"""Tests for mem_list."""

from __future__ import annotations

from fastmcp import Client


async def test_list_default_excludes_archived(client: Client) -> None:
    res = await client.call_tool("mem_list", {})
    d = res.data
    assert {p.slug for p in d.projects} == {"alpha", "beta"}
    assert {x.slug for x in d.domains} == {"shared-infra"}
    assert d.archived == []  # hidden by default
    assert "Archived projects (1, hidden)" in d.summary_md


async def test_list_with_include_archived(client: Client) -> None:
    res = await client.call_tool("mem_list", {"include_archived": True})
    d = res.data
    assert {a.slug for a in d.archived} == {"legacy-app"}
    assert "Archived projects (1)" in d.summary_md
    assert "legacy-app" in d.summary_md


async def test_list_archived_only(client: Client) -> None:
    res = await client.call_tool("mem_list", {"archived_only": True})
    d = res.data
    assert d.projects == []
    assert d.domains == []
    assert {a.slug for a in d.archived} == {"legacy-app"}


async def test_list_metadata_carries_phase_and_last_session(client: Client) -> None:
    res = await client.call_tool("mem_list", {})
    by_slug = {p.slug: p for p in res.data.projects}
    assert by_slug["alpha"].phase == "in-progress (demo fixture)"
    assert by_slug["alpha"].last_session == "2026-04-30"
    assert by_slug["alpha"].scope == "work"
    assert by_slug["alpha"].archives_count == 1


async def test_list_summary_md_renders_projects_section(client: Client) -> None:
    res = await client.call_tool("mem_list", {})
    md = res.data.summary_md
    assert "## Vault inventory" in md
    assert "### Projects (2)" in md
    assert "### Domains (1)" in md
    assert "**alpha**" in md
    assert "phase=in-progress (demo fixture)" in md
