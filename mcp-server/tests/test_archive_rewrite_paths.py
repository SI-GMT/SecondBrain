"""Tests for mem_archive_rewrite_paths."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.vault import frontmatter


def _seed_archive_with_abs_paths(vault: Path, slug: str, old_root: str) -> Path:
    """Write a fixture archive containing absolute path references."""
    archive = (
        vault / "10-episodes" / "projects" / slug / "archives"
        / "2026-05-01-12h00-alpha-paths-fixture.md"
    )
    archive.write_text(
        "---\n"
        f"project: {slug}\n"
        "zone: episodes\n"
        "kind: archive\n"
        "---\n\n"
        f"Edited `{old_root}/src/foo.py` and `{old_root}/tests/test_foo.py` today.\n"
        f"Saw the same issue in `{old_root}/docs/notes.md`.\n",
        encoding="utf-8",
        newline="\n",
    )
    return archive


def _set_repo_path(vault: Path, slug: str, repo_path: str) -> None:
    ctx = vault / "10-episodes" / "projects" / slug / "context.md"
    fm, body = frontmatter.read(ctx)
    fm["repo_path"] = repo_path
    frontmatter.write(ctx, fm, body)


async def test_dry_run_lists_files_without_changing(
    client: Client, vault_tmp: Path
) -> None:
    old_root = "C:/_PROJETS/X/alpha"
    archive = _seed_archive_with_abs_paths(vault_tmp, "alpha", old_root)
    _set_repo_path(vault_tmp, "alpha", old_root)

    res = await client.call_tool("mem_archive_rewrite_paths", {"slug": "alpha"})
    d = res.data
    assert d.success is True
    assert "Dry-run only" in " ".join(d.warnings)
    # Archive body untouched.
    assert old_root in archive.read_text(encoding="utf-8")
    assert "<repo>" not in archive.read_text(encoding="utf-8")


async def test_confirm_rewrites_archive_bodies(
    client: Client, vault_tmp: Path
) -> None:
    old_root = "C:/_PROJETS/X/alpha"
    archive = _seed_archive_with_abs_paths(vault_tmp, "alpha", old_root)
    _set_repo_path(vault_tmp, "alpha", old_root)

    res = await client.call_tool(
        "mem_archive_rewrite_paths", {"slug": "alpha", "confirm": True}
    )
    assert res.data.success is True
    text = archive.read_text(encoding="utf-8")
    assert old_root not in text
    assert "<repo>/src/foo.py" in text
    assert "<repo>/tests/test_foo.py" in text
    assert "<repo>/docs/notes.md" in text

    # Audit log written.
    log = vault_tmp / "99-meta" / "migrations" / "relocations.md"
    assert log.exists()
    assert "mem_archive_rewrite_paths" in log.read_text(encoding="utf-8")


async def test_idempotent_second_run_finds_nothing(
    client: Client, vault_tmp: Path
) -> None:
    old_root = "C:/_PROJETS/X/alpha"
    _seed_archive_with_abs_paths(vault_tmp, "alpha", old_root)
    _set_repo_path(vault_tmp, "alpha", old_root)

    await client.call_tool(
        "mem_archive_rewrite_paths", {"slug": "alpha", "confirm": True}
    )
    res = await client.call_tool(
        "mem_archive_rewrite_paths", {"slug": "alpha", "confirm": True}
    )
    assert res.data.success is True
    assert "Nothing to rewrite" in res.data.summary_md


async def test_explicit_old_root_overrides_context(
    client: Client, vault_tmp: Path
) -> None:
    # context.md repo_path points to the NEW root; archive still has OLD paths.
    old_root = "C:/legacy/alpha"
    new_root = "D:/projets/alpha"
    archive = _seed_archive_with_abs_paths(vault_tmp, "alpha", old_root)
    _set_repo_path(vault_tmp, "alpha", new_root)

    res = await client.call_tool(
        "mem_archive_rewrite_paths",
        {"slug": "alpha", "old_root": old_root, "confirm": True},
    )
    assert res.data.success is True
    text = archive.read_text(encoding="utf-8")
    assert old_root not in text
    assert "<repo>/src/foo.py" in text


async def test_missing_repo_path_without_old_root_raises(
    client: Client, vault_tmp: Path
) -> None:
    # alpha has no repo_path set, no --old-root given.
    with pytest.raises(ToolError, match="(repo_path|old_root)"):
        await client.call_tool(
            "mem_archive_rewrite_paths", {"slug": "alpha", "confirm": True}
        )


async def test_unknown_slug_raises(client: Client, vault_tmp: Path) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_archive_rewrite_paths",
            {"slug": "no-such-project", "old_root": "C:/x", "confirm": True},
        )


async def test_no_include_context_history_skips_context(
    client: Client, vault_tmp: Path
) -> None:
    old_root = "C:/_PROJETS/X/alpha"
    archive = _seed_archive_with_abs_paths(vault_tmp, "alpha", old_root)

    # Seed context.md with an absolute path too.
    ctx = vault_tmp / "10-episodes" / "projects" / "alpha" / "context.md"
    fm, body = frontmatter.read(ctx)
    fm["repo_path"] = old_root
    frontmatter.write(ctx, fm, body + f"\n\nReference: `{old_root}/README.md`\n")

    res = await client.call_tool(
        "mem_archive_rewrite_paths",
        {"slug": "alpha", "confirm": True, "include_context_history": False},
    )
    assert res.data.success is True
    # Archive rewritten, context.md untouched.
    assert "<repo>" in archive.read_text(encoding="utf-8")
    assert old_root in ctx.read_text(encoding="utf-8")
