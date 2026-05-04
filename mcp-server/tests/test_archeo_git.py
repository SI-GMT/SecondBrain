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


async def test_rejects_invalid_level(client: Client, repo_with_tags: Path) -> None:
    """A level value outside the canonical 4 must raise ValueError."""
    with pytest.raises(Exception) as exc_info:
        await client.call_tool(
            "mem_archeo_git",
            {"repo_path": str(repo_with_tags), "project": "alpha", "level": "garbage"},
        )
    assert "Unknown level" in str(exc_info.value) or "garbage" in str(exc_info.value)


async def test_warns_no_milestones(client: Client, vault_tmp: Path, tmp_path: Path) -> None:
    """A repo with no semver tags should report 0 milestones + a 'No milestones' warning."""
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
    assert any("No milestones" in w for w in data["warnings"])


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


# ---------- Level=commits (window discovery) ----------


@pytest.fixture
def repo_with_commits_window(tmp_path: Path) -> Path:
    """Repo with 4 commits across 2 ISO weeks for window-grouping tests."""
    import os
    repo = tmp_path / "commits-repo"
    repo.mkdir()
    _git_init_with_user(repo)
    env_base = {**os.environ}

    def _commit_with_date(fname: str, content: str, msg: str, iso_date: str,
                          email: str = "alice@example.com", name: str = "Alice") -> None:
        (repo / fname).write_text(content, encoding="utf-8")
        _git(repo, "add", fname)
        env = {
            **env_base,
            "GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date,
            "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_NAME": name,
            "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_NAME": name,
        }
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-q", "-m", msg],
            check=True, env=env,
        )

    # Week 18 (Mon 2026-04-27 -> Sun 2026-05-03): 2 commits, 2 authors
    _commit_with_date("a.txt", "a1", "feat alpha 1", "2026-04-28T10:00:00+00:00",
                      "alice@example.com", "Alice")
    _commit_with_date("a.txt", "a2", "feat alpha 2", "2026-04-29T10:00:00+00:00",
                      "bob@example.com", "Bob")
    # Week 19 (Mon 2026-05-04 -> Sun 2026-05-10): 2 commits, both Alice
    _commit_with_date("a.txt", "a3", "fix beta 1", "2026-05-05T10:00:00+00:00",
                      "alice@example.com", "Alice")
    _commit_with_date("a.txt", "a4", "fix beta 2", "2026-05-06T10:00:00+00:00",
                      "alice@example.com", "Alice")
    return repo


async def test_commits_window_default_groups_by_week(
    client: Client, repo_with_commits_window: Path, vault_tmp: Path,
) -> None:
    (vault_tmp / "10-episodes" / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    res = await client.call_tool(
        "mem_archeo_git",
        {
            "repo_path": str(repo_with_commits_window),
            "project": "alpha",
            "level": "commits",
            "since": "2026-04-20",
            "until": "2026-05-15",
            "window": "week",
        },
    )
    d = res.structured_content
    assert d["milestones_processed"] == 2
    assert d["archives_created"] == 2
    archives_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    archives = [f.name for f in archives_dir.glob("*window-2026-w*.md")]
    assert len(archives) == 2


async def test_commits_window_by_author_splits_per_email(
    client: Client, repo_with_commits_window: Path, vault_tmp: Path,
) -> None:
    (vault_tmp / "10-episodes" / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    res = await client.call_tool(
        "mem_archeo_git",
        {
            "repo_path": str(repo_with_commits_window),
            "project": "alpha",
            "level": "commits",
            "since": "2026-04-20",
            "until": "2026-05-15",
            "window": "week",
            "by_author": True,
        },
    )
    d = res.structured_content
    # Week 18: 2 distinct authors -> 2 archives
    # Week 19: 1 author (alice) -> 1 archive
    assert d["milestones_processed"] == 3


async def test_commits_window_filters_since_until(
    client: Client, repo_with_commits_window: Path, vault_tmp: Path,
) -> None:
    (vault_tmp / "10-episodes" / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    res = await client.call_tool(
        "mem_archeo_git",
        {
            "repo_path": str(repo_with_commits_window),
            "project": "alpha",
            "level": "commits",
            "since": "2026-05-04",
            "until": "2026-05-15",
            "window": "week",
        },
    )
    d = res.structured_content
    # Only week 19 in range (2026-05-05 and 2026-05-06)
    assert d["milestones_processed"] == 1


# ---------- Level=releases (gh CLI mocked) ----------


def _patch_gh(monkeypatch: pytest.MonkeyPatch, payloads: dict[str, object]) -> None:
    """Make subprocess.run respond to gh subcommands; pass git through to real run.

    payloads keys: ``release_list`` (list of release dicts), ``pr_list`` (list of pr dicts).
    Missing key => empty list returned.
    """
    import json as _json
    real_run = subprocess.run

    class _R:
        def __init__(self, stdout: str = "ok", returncode: int = 0, stderr: str = "") -> None:
            self.stdout = stdout
            self.returncode = returncode
            self.stderr = stderr

    def fake_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)):
            if cmd[:2] == ["gh", "auth"]:
                return _R()
            if cmd[:3] == ["gh", "release", "list"]:
                return _R(_json.dumps(payloads.get("release_list", [])))
            if cmd[:3] == ["gh", "pr", "list"]:
                return _R(_json.dumps(payloads.get("pr_list", [])))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr("memory_kit_mcp.tools.archeo_git.subprocess.run", fake_run)


async def test_releases_creates_one_archive_per_release(
    client: Client, repo_with_tags: Path, vault_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (vault_tmp / "10-episodes" / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    _patch_gh(monkeypatch, {
        "release_list": [
            {
                "tagName": "v0.2.0",
                "name": "Release v0.2.0",
                "publishedAt": "2026-04-22T10:00:00Z",
                "url": "https://github.com/x/y/releases/tag/v0.2.0",
                "isPrerelease": False, "isDraft": False, "body": "## Changes\n- thing",
            },
            {
                "tagName": "v0.3.0",
                "name": "",
                "publishedAt": "2026-04-23T10:00:00Z",
                "url": "https://github.com/x/y/releases/tag/v0.3.0",
                "isPrerelease": True, "isDraft": False, "body": "RC notes",
            },
        ],
    })
    res = await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "alpha", "level": "releases"},
    )
    d = res.structured_content
    assert d["milestones_processed"] == 2
    assert d["archives_created"] == 2
    archives_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    rels = [f.name for f in archives_dir.glob("*archeo-git-release-*.md")]
    assert len(rels) == 2
    for f in archives_dir.glob("*archeo-git-release-v0-2-0*.md"):
        fm, body = frontmatter.read(f)
        assert fm["milestone_kind"] == "release"
        assert fm["release_tag"] == "v0.2.0"
        assert fm["source_milestone"] == "release-v0.2.0"
        assert fm["release_is_prerelease"] is False
        assert "Release archive" in body


async def test_releases_skips_when_gh_unavailable(
    client: Client, repo_with_tags: Path, vault_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and cmd[:2] == ["gh", "auth"]:
            raise FileNotFoundError("gh not on PATH")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr("memory_kit_mcp.tools.archeo_git.subprocess.run", fake_run)
    res = await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "alpha", "level": "releases"},
    )
    d = res.structured_content
    assert d["milestones_processed"] == 0
    assert any("gh CLI" in w for w in d["warnings"])


# ---------- Level=merges (gh CLI mocked) ----------


async def test_merges_creates_one_archive_per_pr(
    client: Client, repo_with_tags: Path, vault_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (vault_tmp / "10-episodes" / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    _patch_gh(monkeypatch, {
        "pr_list": [
            {
                "number": 1,
                "title": "Initial PR",
                "mergeCommit": None,  # squash merge — no merge commit
                "mergedAt": "2026-04-22T10:00:00Z",
                "baseRefName": "main",
                "headRefName": "feat/init",
                "url": "https://github.com/x/y/pull/1",
                "author": {"login": "alice"},
            },
            {
                "number": 42,
                "title": "Add feature X",
                "mergeCommit": {"oid": "deadbeef"},
                "mergedAt": "2026-04-23T15:00:00Z",
                "baseRefName": "main",
                "headRefName": "feat/x",
                "url": "https://github.com/x/y/pull/42",
                "author": {"login": "bob"},
            },
        ],
    })
    res = await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "alpha", "level": "merges"},
    )
    d = res.structured_content
    assert d["milestones_processed"] == 2
    assert d["archives_created"] == 2
    archives_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    pr1 = list(archives_dir.glob("*archeo-git-merge-pr-1.md"))
    pr42 = list(archives_dir.glob("*archeo-git-merge-pr-42.md"))
    assert pr1 and pr42
    fm, body = frontmatter.read(pr42[0])
    assert fm["pr_number"] == 42
    assert fm["pr_base"] == "main"
    assert fm["pr_head"] == "feat/x"
    assert fm["source_milestone"] == "pr-#42"
    assert "Merge archive" in body


# ---------- Branch-first mode ----------


@pytest.fixture
def repo_with_branch(tmp_path: Path) -> tuple[Path, str]:
    """Repo with main + feature branch (2 unique commits on the branch)."""
    repo = tmp_path / "branch-repo"
    repo.mkdir()
    _git_init_with_user(repo)
    _commit_file(repo, "base.txt", "base", "init main")
    try:
        _git(repo, "branch", "-m", "main")
    except subprocess.CalledProcessError:
        pass
    _commit_file(repo, "main.txt", "main2", "main work")
    _git(repo, "checkout", "-b", "feat/x")
    _commit_file(repo, "feat.txt", "feat1", "feat first")
    _commit_file(repo, "feat.txt", "feat2", "feat second")
    _git(repo, "checkout", "main")
    return repo, "feat/x"


async def test_branch_first_scopes_to_branch_commits(
    client: Client, repo_with_branch: tuple[Path, str], vault_tmp: Path,
) -> None:
    repo, branch = repo_with_branch
    (vault_tmp / "10-episodes" / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    res = await client.call_tool(
        "mem_archeo_git",
        {
            "repo_path": str(repo),
            "project": "alpha",
            "level": "commits",
            "branch_first": branch,
            "branch_base": "main",
            "window": "day",
            "by_author": True,
        },
    )
    d = res.structured_content
    # 2 unique commits on the branch, same author, same day -> 1 archive
    assert d["milestones_processed"] == 1
    archive = list(
        (vault_tmp / "10-episodes" / "projects" / "alpha" / "archives").glob(
            "*archeo-git-window-*.md"
        )
    )
    assert len(archive) == 1
    fm, _body = frontmatter.read(archive[0])
    assert fm["branch"] == "feat/x"
    assert fm["branch_base"] == "main"
    assert fm["branch_base_sha"]


async def test_branch_first_falls_back_when_branch_missing(
    client: Client, repo_with_tags: Path, vault_tmp: Path,
) -> None:
    """If the requested branch doesn't exist, warn and fall back to standard mode."""
    (vault_tmp / "10-episodes" / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    res = await client.call_tool(
        "mem_archeo_git",
        {
            "repo_path": str(repo_with_tags),
            "project": "alpha",
            "level": "tags",
            "branch_first": "nope-not-a-branch",
        },
    )
    d = res.structured_content
    # repo_with_tags has 3 semver tags -> standard mode after fallback creates 3 archives
    assert d["milestones_processed"] == 3
    assert any("could not be resolved" in w for w in d["warnings"])
