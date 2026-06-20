"""Tests for mem_relocate_project."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.vault import frontmatter


def _make_git_repo(path: Path, origin: str = "git@github.com:test/proj.git") -> None:
    """Initialize a bare-enough git repo with an origin remote for tests."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--initial-branch=main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", origin], cwd=path, check=True, capture_output=True)


async def test_dry_run_returns_plan_without_writing(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    new_root = tmp_path / "moved-alpha"
    _make_git_repo(new_root)
    res = await client.call_tool(
        "mem_relocate_project",
        {"slug": "alpha", "new_root": str(new_root), "force": True},
    )
    d = res.data
    assert d.success is True
    assert "dry-run" in d.summary_md.lower()
    # context.md untouched.
    fm, _ = frontmatter.read(vault_tmp / "10-episodes" / "projects" / "alpha" / "context.md")
    assert fm.get("repo_path") in (None, "")


async def test_confirm_updates_repo_path(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    new_root = tmp_path / "moved-alpha"
    _make_git_repo(new_root)
    res = await client.call_tool(
        "mem_relocate_project",
        {
            "slug": "alpha",
            "new_root": str(new_root),
            "confirm": True,
            "force": True,
            "reason": "moved to D: after disk swap",
        },
    )
    assert res.data.success is True
    ctx = vault_tmp / "10-episodes" / "projects" / "alpha" / "context.md"
    fm, _ = frontmatter.read(ctx)
    assert Path(fm["repo_path"]) == new_root

    log = vault_tmp / "99-meta" / "migrations" / "relocations.md"
    assert log.exists()
    log_text = log.read_text(encoding="utf-8")
    assert "alpha" in log_text
    assert "moved to D:" in log_text


async def test_no_op_when_already_at_new_root(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    new_root = tmp_path / "moved-alpha"
    _make_git_repo(new_root)
    # First call: actually relocate.
    await client.call_tool(
        "mem_relocate_project",
        {"slug": "alpha", "new_root": str(new_root), "confirm": True, "force": True},
    )
    # Second call to the same target: should be a no-op success.
    res = await client.call_tool(
        "mem_relocate_project",
        {"slug": "alpha", "new_root": str(new_root), "confirm": True, "force": True},
    )
    assert res.data.success is True
    assert "no-op" in res.data.summary_md.lower()


async def test_unknown_slug_raises(client: Client, tmp_path: Path) -> None:
    target = tmp_path / "x"
    _make_git_repo(target)
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_relocate_project",
            {"slug": "no-such-project", "new_root": str(target), "force": True},
        )


async def test_missing_new_root_raises(client: Client, vault_tmp: Path, tmp_path: Path) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_relocate_project",
            {"slug": "alpha", "new_root": str(tmp_path / "does-not-exist"), "force": True},
        )


async def test_missing_git_without_force_raises(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    new_root = tmp_path / "no-git"
    new_root.mkdir()
    with pytest.raises(ToolError, match="\\.git"):
        await client.call_tool(
            "mem_relocate_project",
            {"slug": "alpha", "new_root": str(new_root), "confirm": True},
        )


async def test_force_bypasses_git_check(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    new_root = tmp_path / "no-git"
    new_root.mkdir()
    res = await client.call_tool(
        "mem_relocate_project",
        {"slug": "alpha", "new_root": str(new_root), "confirm": True, "force": True},
    )
    assert res.data.success is True
    fm, _ = frontmatter.read(vault_tmp / "10-episodes" / "projects" / "alpha" / "context.md")
    assert Path(fm["repo_path"]) == new_root
