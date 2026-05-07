"""Integration tests for the mem_archeo_index_files MCP tool."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo_with_files(tmp_path: Path) -> Path:
    repo = tmp_path / "preview_repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "alpha.py").write_text("a=1\n", encoding="utf-8")
    (repo / "src" / "beta.py").write_text("b=2\n", encoding="utf-8")
    (repo / "README.md").write_text("# r\n", encoding="utf-8")
    return repo


@pytest.fixture
def git_repo_with_branch(tmp_path: Path) -> Path:
    repo = tmp_path / "preview_git"
    repo.mkdir()
    _git(["init", "--initial-branch=main"], repo)
    _git(["config", "user.email", "t@e.com"], repo)
    _git(["config", "user.name", "t"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)
    (repo / "core.py").write_text("c=1\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-m", "init"], repo)
    _git(["checkout", "-b", "feat"], repo)
    (repo / "feat.py").write_text("f=1\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-m", "feat"], repo)
    return repo


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


async def test_mem_archeo_index_files_appears_in_inventory(
    client: Client,
) -> None:
    tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "mem_archeo_index_files" in names


# ---------------------------------------------------------------------------
# Raw mode
# ---------------------------------------------------------------------------


async def test_returns_files_count_and_hash_raw(
    client: Client, repo_with_files: Path
) -> None:
    result = await client.call_tool(
        "mem_archeo_index_files",
        {"project": "alpha", "repo_path": str(repo_with_files), "mode": "raw"},
    )
    payload = result.structured_content or {}
    assert payload["project"] == "alpha"
    assert payload["source_mode"] == "raw"
    assert payload["files_count"] >= 3
    assert isinstance(payload["files_hash"], str)
    assert len(payload["files_hash"]) == 64  # sha256 hex


async def test_returns_batches_uniform_contract(
    client: Client, repo_with_files: Path
) -> None:
    result = await client.call_tool(
        "mem_archeo_index_files",
        {
            "project": "alpha",
            "repo_path": str(repo_with_files),
            "mode": "raw",
            "batch_size": 2,
        },
    )
    payload = result.structured_content or {}
    assert isinstance(payload["batches"], list)
    assert len(payload["batches"]) >= 1
    flat = [f for batch in payload["batches"] for f in batch]
    assert sorted(flat) == sorted(payload["files"])


async def test_scope_glob_forwarded(
    client: Client, repo_with_files: Path
) -> None:
    result = await client.call_tool(
        "mem_archeo_index_files",
        {
            "project": "alpha",
            "repo_path": str(repo_with_files),
            "mode": "raw",
            "scope_glob": "src/*.py",
        },
    )
    payload = result.structured_content or {}
    assert payload["scope_glob"] == "src/*.py"
    assert payload["files_count"] == 2
    assert all(f.startswith("src/") for f in payload["files"])


# ---------------------------------------------------------------------------
# Soft caps + warnings
# ---------------------------------------------------------------------------


async def test_overflow_warning_surfaced(
    client: Client, repo_with_files: Path
) -> None:
    result = await client.call_tool(
        "mem_archeo_index_files",
        {
            "project": "alpha",
            "repo_path": str(repo_with_files),
            "mode": "raw",
            "max_files": 1,
        },
    )
    payload = result.structured_content or {}
    assert any("ScopeOverflowWarning" in w for w in payload["warnings"])
    # File list NOT truncated.
    assert payload["files_count"] >= 2


async def test_hard_abort_raises(
    client: Client, repo_with_files: Path
) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_archeo_index_files",
            {
                "project": "alpha",
                "repo_path": str(repo_with_files),
                "mode": "raw",
                "max_files": 1,
                "hard_abort": True,
            },
        )


# ---------------------------------------------------------------------------
# Git mode + branch
# ---------------------------------------------------------------------------


async def test_git_branch_first_via_mcp(
    client: Client, git_repo_with_branch: Path
) -> None:
    result = await client.call_tool(
        "mem_archeo_index_files",
        {
            "project": "alpha",
            "repo_path": str(git_repo_with_branch),
            "mode": "git",
            "branch": "feat",
        },
    )
    payload = result.structured_content or {}
    assert payload["source_mode"] == "git"
    assert payload["branch"] == "feat"
    assert payload["base_ref"] is not None
    assert payload["merge_base_strategy"] == "merge-base"
    assert "feat.py" in payload["files"]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


async def test_summary_md_contains_key_facts(
    client: Client, repo_with_files: Path
) -> None:
    result = await client.call_tool(
        "mem_archeo_index_files",
        {"project": "alpha", "repo_path": str(repo_with_files), "mode": "raw"},
    )
    payload = result.structured_content or {}
    md = payload["summary_md"]
    assert "alpha" in md
    assert "**raw**" in md
    assert "Files:" in md


# ---------------------------------------------------------------------------
# Trace surface
# ---------------------------------------------------------------------------


async def test_trace_propagated_in_structured_payload(
    client: Client, repo_with_files: Path
) -> None:
    result = await client.call_tool(
        "mem_archeo_index_files",
        {"project": "alpha", "repo_path": str(repo_with_files), "mode": "raw"},
    )
    payload = result.structured_content or {}
    trace = payload["trace"]
    assert isinstance(trace, list)
    assert any("[start]" in t for t in trace)
    assert any("[mode]" in t for t in trace)
    assert any("[done]" in t for t in trace)


async def test_trace_appears_in_summary_md(
    client: Client, repo_with_files: Path
) -> None:
    result = await client.call_tool(
        "mem_archeo_index_files",
        {"project": "alpha", "repo_path": str(repo_with_files), "mode": "raw"},
    )
    payload = result.structured_content or {}
    md = payload["summary_md"]
    assert "### Trace" in md
    assert "[start]" in md
