"""Tests for the manual archeo-git fallback path of mem_archive.

Covers:
- archive_extra_fm merges into archive frontmatter (tags concatenated, others overridden).
- source_hint='archeo-git' enforces _frontmatter-archeo.md MUST keys.
- Validation error lists every missing key + does not write a partial archive.
- Unknown source_hint values rejected.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.vault import frontmatter


def _full_archeo_meta() -> dict[str, object]:
    """Return a complete archeo-git archive frontmatter dict (all MUST keys present)."""
    return {
        "source": "archeo-git",
        "scope": "work",
        "collective": False,
        "modality": "left",
        "branch": "dev-compta",
        "branch_base": "master",
        "branch_base_sha": "95dd7423b58dee8dcbeaa205589ea9af4195b6da",
        "milestone_kind": "merge",
        "source_milestone": "branch-first-dev-compta",
        "commit_sha": "ebc2cff27970d194b111653f42fe782464260f8b",
        "granularity": "by-merge",
        "friction_detected": False,
        "derived_atoms": [],
        "content_hash": "0" * 64,
        "previous_atom": "",
        "topology_snapshot_hash": "",
        "repo_path": "C:/_PROJETS/IRIS/PROD/USER",
        "tags": ["source/archeo-git", "branch/dev-compta"],
    }


async def test_archive_extra_fm_merges_into_archive_fm(
    client: Client, vault_tmp: Path
) -> None:
    """Extra fields land in the persisted frontmatter; tags get concatenated."""
    res = await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "full",
            "context_md": "Reset.",
            "archive_subject": "test merge fm",
            "archive_body_md": "# Body\n\nNothing fancy.\n",
            "archive_extra_fm": {
                "source": "archeo-git",
                "branch": "ecosav",
                "tags": ["source/archeo-git", "branch/ecosav"],
            },
        },
    )
    assert res.data.success is True
    archives = list(
        (vault_tmp / "10-episodes" / "projects" / "alpha" / "archives").glob(
            "*-test-merge-fm.md"
        )
    )
    assert len(archives) == 1
    fm, _ = frontmatter.read(archives[0])
    assert fm["source"] == "archeo-git"
    assert fm["branch"] == "ecosav"
    # Tags concatenated, not overwritten — universal kind/archive must persist.
    assert "kind/archive" in fm["tags"]
    assert "source/archeo-git" in fm["tags"]
    assert "branch/ecosav" in fm["tags"]


async def test_archive_extra_fm_does_not_duplicate_tags(
    client: Client, vault_tmp: Path
) -> None:
    """Tags concatenation is dedup'd — no duplicates if extra repeats a base tag."""
    await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "full",
            "context_md": "Reset.",
            "archive_subject": "dup tags",
            "archive_body_md": "Body.",
            "archive_extra_fm": {
                "tags": ["kind/archive", "extra-tag"],
            },
        },
    )
    archives = list(
        (vault_tmp / "10-episodes" / "projects" / "alpha" / "archives").glob(
            "*-dup-tags.md"
        )
    )
    fm, _ = frontmatter.read(archives[0])
    # kind/archive appears exactly once.
    assert fm["tags"].count("kind/archive") == 1
    assert "extra-tag" in fm["tags"]


async def test_source_hint_archeo_git_with_full_meta_succeeds(
    client: Client, vault_tmp: Path
) -> None:
    """Complete archeo-git frontmatter passes validation."""
    res = await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "full",
            "context_md": "Reset.",
            "archive_subject": "archeo dev compta branch first",
            "archive_body_md": "# Body\n\nFull archeo archive.\n",
            "archive_extra_fm": _full_archeo_meta(),
            "source_hint": "archeo-git",
        },
    )
    assert res.data.success is True
    archives = list(
        (vault_tmp / "10-episodes" / "projects" / "alpha" / "archives").glob(
            "*-archeo-dev-compta-branch-first.md"
        )
    )
    assert len(archives) == 1
    fm, _ = frontmatter.read(archives[0])
    assert fm["source"] == "archeo-git"
    assert fm["branch"] == "dev-compta"
    assert fm["branch_base_sha"] == "95dd7423b58dee8dcbeaa205589ea9af4195b6da"
    assert fm["granularity"] == "by-merge"
    assert fm["derived_atoms"] == []


async def test_source_hint_archeo_git_missing_keys_raises(
    client: Client, vault_tmp: Path
) -> None:
    """Source hint set without complete extra_fm aborts. Lists missing keys."""
    incomplete = _full_archeo_meta()
    del incomplete["branch"]
    del incomplete["branch_base_sha"]
    del incomplete["milestone_kind"]
    with pytest.raises(ToolError) as ei:
        await client.call_tool(
            "mem_archive",
            {
                "slug": "alpha",
                "mode": "full",
                "context_md": "Reset.",
                "archive_subject": "incomplete archeo",
                "archive_body_md": "Body.",
                "archive_extra_fm": incomplete,
                "source_hint": "archeo-git",
            },
        )
    msg = str(ei.value)
    assert "branch" in msg
    assert "branch_base_sha" in msg
    assert "milestone_kind" in msg


async def test_source_hint_archeo_git_no_extra_fm_raises(
    client: Client, vault_tmp: Path
) -> None:
    """source_hint without archive_extra_fm at all is a hard error (every key missing)."""
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_archive",
            {
                "slug": "alpha",
                "mode": "full",
                "context_md": "Reset.",
                "archive_subject": "no extra",
                "archive_body_md": "Body.",
                "source_hint": "archeo-git",
            },
        )


async def test_source_hint_archeo_git_failure_writes_nothing(
    client: Client, vault_tmp: Path
) -> None:
    """A validation failure must not leave a half-written archive on disk."""
    archives_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    before = sorted(archives_dir.glob("*.md"))
    incomplete = _full_archeo_meta()
    del incomplete["commit_sha"]
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_archive",
            {
                "slug": "alpha",
                "mode": "full",
                "context_md": "Reset.",
                "archive_subject": "should not persist",
                "archive_body_md": "Body.",
                "archive_extra_fm": incomplete,
                "source_hint": "archeo-git",
            },
        )
    after = sorted(archives_dir.glob("*.md"))
    assert before == after


async def test_source_hint_archeo_git_wrong_source_value_raises(
    client: Client, vault_tmp: Path
) -> None:
    """source_hint='archeo-git' but extra_fm['source']='archeo-context' is a hint mismatch."""
    meta = _full_archeo_meta()
    meta["source"] = "archeo-context"
    with pytest.raises(ToolError) as ei:
        await client.call_tool(
            "mem_archive",
            {
                "slug": "alpha",
                "mode": "full",
                "context_md": "Reset.",
                "archive_subject": "wrong source",
                "archive_body_md": "Body.",
                "archive_extra_fm": meta,
                "source_hint": "archeo-git",
            },
        )
    assert "archeo-context" in str(ei.value) or "source" in str(ei.value)


async def test_source_hint_unknown_value_rejected(
    client: Client, vault_tmp: Path
) -> None:
    """Pydantic Literal validation rejects an unknown source_hint."""
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_archive",
            {
                "slug": "alpha",
                "mode": "full",
                "context_md": "Reset.",
                "archive_subject": "bogus hint",
                "archive_body_md": "Body.",
                "source_hint": "archeo-cosmic-rays",
            },
        )


async def test_no_source_hint_skips_validation(
    client: Client, vault_tmp: Path
) -> None:
    """Without source_hint, archive_extra_fm is just merged — no doctrine check."""
    res = await client.call_tool(
        "mem_archive",
        {
            "slug": "alpha",
            "mode": "full",
            "context_md": "Reset.",
            "archive_subject": "no hint",
            "archive_body_md": "Body.",
            "archive_extra_fm": {"custom_field": 42},
        },
    )
    assert res.data.success is True
    archives = list(
        (vault_tmp / "10-episodes" / "projects" / "alpha" / "archives").glob(
            "*-no-hint.md"
        )
    )
    fm, _ = frontmatter.read(archives[0])
    assert fm["custom_field"] == 42
