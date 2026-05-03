"""Tests for mem_archeo_git — Phase 3 of the triphasic archeo.

Spec: core/procedures/mem-archeo-git.md.

Each test spins up a tiny git repo with one or more semver tags and asserts
on archive creation, AI files context extraction, idempotence, etc.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastmcp import Client

from memory_kit_mcp.vault import frontmatter


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )


def _git_init_with_user(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "commit.gpgsign", "false")


def _commit_file(repo: Path, fname: str, content: str, message: str) -> str:
    (repo / fname).write_text(content, encoding="utf-8")
    _git(repo, "add", fname)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _tag(repo: Path, name: str, message: str = "release") -> None:
    _git(repo, "tag", "-a", name, "-m", message)


@pytest.fixture
def repo_with_tags(tmp_path: Path) -> Path:
    """Repo with 3 semver tags: v0.1.0, v0.2.0, v0.3.0."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_user(repo)
    _commit_file(repo, "README.md", "# v0.1.0\nfirst", "init")
    _tag(repo, "v0.1.0")
    _commit_file(repo, "README.md", "# v0.2.0\nsecond", "second commit")
    _tag(repo, "v0.2.0")
    _commit_file(repo, "README.md", "# v0.3.0\nthird", "third commit")
    _tag(repo, "v0.3.0")
    return repo


# ---------- Validation ----------


async def test_raises_on_non_git_dir(client: Client, tmp_path: Path) -> None:
    not_a_repo = tmp_path / "noop"
    not_a_repo.mkdir()
    with pytest.raises(Exception) as exc_info:
        await client.call_tool(
            "mem_archeo_git",
            {"repo_path": str(not_a_repo), "project": "alpha"},
        )
    assert "not a Git repository" in str(exc_info.value)


async def test_rejects_unsupported_level(client: Client, repo_with_tags: Path) -> None:
    with pytest.raises(Exception) as exc_info:
        await client.call_tool(
            "mem_archeo_git",
            {"repo_path": str(repo_with_tags), "project": "alpha", "level": "merges"},
        )
    assert "level='tags'" in str(exc_info.value) or "POC" in str(exc_info.value)


async def test_warns_no_tags(client: Client, vault_tmp: Path, tmp_path: Path) -> None:
    repo = tmp_path / "no-tags"
    repo.mkdir()
    _git_init_with_user(repo)
    _commit_file(repo, "README.md", "# x", "init")
    result = await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo), "project": "alpha"},
    )
    data = result.structured_content
    assert data["milestones_processed"] == 0
    assert any("No semver tags" in w for w in data["warnings"])


# ---------- Tag enumeration + archive write ----------


async def test_creates_one_archive_per_tag(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    result = await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "alpha"},
    )
    data = result.structured_content
    assert data["milestones_processed"] == 3
    assert data["archives_created"] == 3
    assert data["archives_skipped"] == 0
    tags = {m["tag"] for m in data["milestones"]}
    assert tags == {"v0.1.0", "v0.2.0", "v0.3.0"}

    archives_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    files = sorted(p.name for p in archives_dir.iterdir() if "archeo-git" in p.name)
    assert len(files) == 3
    assert all("alpha-archeo-git-" in f for f in files)


async def test_archive_frontmatter_must_fields(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "alpha"},
    )
    archives_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    archive = next(p for p in archives_dir.iterdir() if "archeo-git-v0-1-0" in p.name)
    fm, body = frontmatter.read(archive)

    # MUST fields per spec
    assert fm["source"] == "archeo-git"
    assert fm["source_milestone"] == "v0.1.0"
    assert fm["commit_sha"]  # non-empty SHA
    assert fm["friction_detected"] is False
    assert fm["content_hash"]
    assert fm["previous_atom"] == ""
    assert fm["topology_snapshot_hash"] == ""
    assert fm["previous_topology_hash"] == ""
    # branch-first fields present even in standard mode (canonical schema)
    assert fm["branch"] == ""
    assert fm["co_authors"] == []
    assert fm["granularity"] == ""
    # base archive fields
    assert fm["zone"] == "episodes"
    assert fm["type"] == "archive"
    assert fm["project"] == "alpha"

    # Mandatory body sections always present (per invariant)
    assert "## AI files context" in body
    assert "## Friction & Resolution" in body


# ---------- AI files context ----------


async def test_ai_files_context_extracted_when_present(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_user(repo)
    (repo / "CLAUDE.md").write_text(
        "# Project guide\n\n"
        "## Workflow\n\n"
        "Speckit + ADR.\n\n"
        "## Security\n\n"
        "Never commit secrets.\n",
        encoding="utf-8",
    )
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "doctrine")
    _tag(repo, "v1.0.0")

    await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo), "project": "alpha"},
    )
    archive = next(
        p for p in (vault_tmp / "10-episodes" / "projects" / "alpha" / "archives").iterdir()
        if "archeo-git" in p.name
    )
    _, body = frontmatter.read(archive)
    assert "From `CLAUDE.md`" in body
    assert "Workflow" in body or "workflow" in body
    assert "Security" in body or "security" in body
    # Fallback line MUST NOT appear when extraction succeeded
    assert "No AI-files context extracted" not in body


async def test_ai_files_fallback_when_silent(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_user(repo)
    # Commit a README without any of the 5 category keywords
    (repo / "README.md").write_text("# Project\n\nA cool app.\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    _tag(repo, "v0.1.0")

    await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo), "project": "alpha"},
    )
    archive = next(
        p for p in (vault_tmp / "10-episodes" / "projects" / "alpha" / "archives").iterdir()
        if "archeo-git" in p.name
    )
    _, body = frontmatter.read(archive)
    # Spec invariant: fallback line MUST be present when nothing extractable
    assert "No AI-files context extracted for this milestone." in body


# ---------- Idempotence ----------


async def test_idempotent_second_call_skips(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    first = await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "alpha"},
    )
    second = await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "alpha"},
    )
    assert first.structured_content["archives_created"] == 3
    assert second.structured_content["archives_created"] == 0
    assert second.structured_content["archives_skipped"] == 3


# ---------- since/until filters ----------


async def test_since_until_bounds(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    # Tags are all on the same day (test runs fast). until in the past → 0 milestones.
    result = await client.call_tool(
        "mem_archeo_git",
        {
            "repo_path": str(repo_with_tags),
            "project": "alpha",
            "until": "2020-01-01",
        },
    )
    data = result.structured_content
    assert data["milestones_processed"] == 0


# ---------- Filename convention ----------


async def test_filename_uses_tag_sanitized(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "alpha"},
    )
    archives_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    files = sorted(p.name for p in archives_dir.iterdir() if "archeo-git" in p.name)
    assert any("archeo-git-v0-1-0" in f for f in files)
    assert any("archeo-git-v0-2-0" in f for f in files)
    assert any("archeo-git-v0-3-0" in f for f in files)
    # Date prefix YYYY-MM-DD
    assert all(f[:4].isdigit() and f[4] == "-" for f in files)
