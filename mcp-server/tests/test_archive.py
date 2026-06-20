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


# ---------- Wikilink resolution enforcement (v0.9.x) ----------


async def test_archive_incremental_rejects_dangling_wikilink(
    client: Client, vault_tmp: Path
) -> None:
    """An incremental rewrite with an unresolved [[X]] must abort, not silently write."""
    with pytest.raises(ToolError) as ei:
        await client.call_tool(
            "mem_archive",
            {
                "slug": "alpha",
                "mode": "incremental",
                "context_md": "See [[totally-fictional-target]] for context.\n",
            },
        )
    assert "totally-fictional-target" in str(ei.value)


async def test_archive_incremental_accepts_resolving_wikilink(
    client: Client, vault_tmp: Path
) -> None:
    """A wikilink that resolves to an existing vault file goes through."""
    target = vault_tmp / "20-knowledge" / "real-target.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {"slug": "real-target", "zone": "knowledge", "display": "real-target"},
        "# real-target\n",
    )
    res = await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "incremental",
            "context_md": "See [[real-target]] for details.\n",
        },
    )
    assert res.data.success is True


async def test_archive_incremental_accepts_dangling_inside_backticks(
    client: Client, vault_tmp: Path
) -> None:
    """Inline-backticked wikilinks are doctrinal bypasses — must NOT be flagged."""
    res = await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "incremental",
            "context_md": "Doctrinal example: `[[hypothetical-link]]` is just a citation.\n",
        },
    )
    assert res.data.success is True


async def test_archive_full_rejects_dangling_in_archive_body(
    client: Client, vault_tmp: Path
) -> None:
    """Even at end-of-session, a dangling wikilink in the archive body aborts."""
    with pytest.raises(ToolError) as ei:
        await client.call_tool(
            "mem_archive",
            {
                "slug": "alpha",
                "mode": "full",
                "context_md": "Reset context.",
                "archive_subject": "broken session",
                "archive_body_md": "Refers to [[nonexistent-thing]].\n",
            },
        )
    assert "nonexistent-thing" in str(ei.value)


async def test_archive_full_rejects_dangling_in_new_context(
    client: Client, vault_tmp: Path
) -> None:
    """A clean archive body but dangling in the new context still aborts."""
    with pytest.raises(ToolError) as ei:
        await client.call_tool(
            "mem_archive",
            {
                "slug": "alpha",
                "mode": "full",
                "context_md": "Mention [[ghost-context-target]] in the new state.",
                "archive_subject": "another broken session",
                "archive_body_md": "Clean body, no wikilinks.\n",
            },
        )
    assert "ghost-context-target" in str(ei.value)


async def test_archive_full_writes_nothing_when_enforcement_aborts(
    client: Client, vault_tmp: Path
) -> None:
    """Failed enforcement must not leave a half-written archive on disk."""
    archives_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    before = sorted(archives_dir.glob("*.md"))
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_archive",
            {
                "slug": "alpha",
                "mode": "full",
                "context_md": "stub",
                "archive_subject": "should not persist",
                "archive_body_md": "Refers to [[ghost]].\n",
            },
        )
    after = sorted(archives_dir.glob("*.md"))
    assert before == after, "no archive must be created when enforcement aborts"


# ---------- Cumulative-decision preservation gate (brief→expand, vNEXT) ----------


async def test_archive_gate_passes_when_decisions_present(
    client: Client, vault_tmp: Path
) -> None:
    """All expected cumulative decisions present in the body → write goes through."""
    res = await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "incremental",
            "context_md": (
                "# Alpha — context\n\n## Décisions cumulées\n"
                "- Bake-at-build pour artefacts gelés\n"
                "- Absolute path dans configs MCP\n"
            ),
            "expect_decisions": [
                "Bake-at-build pour artefacts gelés",
                "Absolute path dans configs MCP",
            ],
        },
    )
    assert res.data.success is True


async def test_archive_gate_tolerates_reformatting(
    client: Client, vault_tmp: Path
) -> None:
    """The gate matches on the alphanumeric skeleton — case/punctuation/spacing
    differences between the expected identifier and the rendered body must NOT
    trip it (only a true drop should)."""
    res = await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "incremental",
            "context_md": (
                "# Alpha\n\n1. **bake at build** — pour artefacts gelés, jamais "
                "importlib.metadata dans un bundle.\n"
            ),
            "expect_decisions": ["Bake-at-build pour artefacts gelés"],
        },
    )
    assert res.data.success is True


async def test_archive_gate_rejects_dropped_decision_incremental(
    client: Client, vault_tmp: Path
) -> None:
    """A cumulative decision absent from the rewritten context aborts the write."""
    with pytest.raises(ToolError) as ei:
        await client.call_tool(
            "mem_archive",
            {
                "slug": "alpha",
                "mode": "incremental",
                "context_md": "# Alpha\n\n- Bake-at-build pour artefacts gelés\n",
                "expect_decisions": [
                    "Bake-at-build pour artefacts gelés",
                    "Update engine desktop wheelhouse offline",
                ],
            },
        )
    assert "Update engine desktop wheelhouse offline" in str(ei.value)


async def test_archive_gate_rejects_dropped_decision_full_writes_nothing(
    client: Client, vault_tmp: Path
) -> None:
    """In full mode, a dropped cumulative decision aborts before any archive
    file is created."""
    archives_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    before = sorted(archives_dir.glob("*.md"))
    with pytest.raises(ToolError) as ei:
        await client.call_tool(
            "mem_archive",
            {
                "slug": "alpha",
                "mode": "full",
                "context_md": "# Alpha\n\nNew snapshot, decisions lost.\n",
                "archive_subject": "gate drop test",
                "archive_body_md": "# Session\n\nClean body.\n",
                "expect_decisions": ["Worklog digest courriel = 4 blocs sans temporalité"],
            },
        )
    assert "Worklog digest courriel" in str(ei.value)
    after = sorted(archives_dir.glob("*.md"))
    assert before == after, "no archive must be created when the gate aborts"


async def test_archive_gate_noop_when_expect_decisions_omitted(
    client: Client, vault_tmp: Path
) -> None:
    """Classic (non-delegated) archiving passes no expect_decisions → gate is a
    no-op even if the body mentions no decision at all."""
    res = await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "incremental",
            "context_md": "# Alpha\n\nBare state, no decisions section.\n",
        },
    )
    assert res.data.success is True


def test_archive_brief_validates_contract() -> None:
    """ArchiveBrief enforces the hand-off contract used by Phase A → Phase B."""
    from pydantic import ValidationError

    from memory_kit_mcp.tools._models import ArchiveBrief

    brief = ArchiveBrief(
        slug="secondbrain",
        kind="project",
        archive_subject="vNEXT delegation",
        decisions_cumulative=["Bake-at-build pour artefacts gelés"],
        verbosity="detailed",
    )
    # decisions_cumulative is exactly what the expander forwards as expect_decisions
    assert brief.decisions_cumulative == ["Bake-at-build pour artefacts gelés"]

    with pytest.raises(ValidationError):
        ArchiveBrief(slug="x", archive_subject="y", verbosity="chatty")
    with pytest.raises(ValidationError):
        ArchiveBrief(slug="x", archive_subject="y", kind="feature")
    with pytest.raises(ValidationError):
        ArchiveBrief(
            slug="x", archive_subject="y", decisions_cumulative=["ok", "  "]
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
