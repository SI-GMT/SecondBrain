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
    assert any("Falling back to standard mode" in w for w in d["warnings"])


# ---------- Branch-first A + B + C (v0.9.x) ----------


@pytest.fixture
def repo_with_merged_branch(tmp_path: Path) -> tuple[Path, str]:
    """Repo where a feature branch was merged back into main.

    Layout:
      M0 (init main)
        \\
         F1 (feat/x)
         F2 (feat/x)
        /
      M1 (merge feat/x into main)
      M2 (post-merge fix on main, touches feat file)
    """
    import os
    repo = tmp_path / "merged-branch-repo"
    repo.mkdir()
    _git_init_with_user(repo)

    env_base = {**os.environ}

    def _commit_with_date(fname: str, content: str, msg: str, iso_date: str) -> str:
        (repo / fname).write_text(content, encoding="utf-8")
        _git(repo, "add", fname)
        env = {
            **env_base,
            "GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date,
        }
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-q", "-m", msg],
            check=True, env=env,
        )
        return _git(repo, "rev-parse", "HEAD").stdout.strip()

    # M0 — initial commit on main
    _commit_with_date("README.md", "init", "init main", "2026-04-01T10:00:00+00:00")
    try:
        _git(repo, "branch", "-m", "main")
    except subprocess.CalledProcessError:
        pass

    # Branch off
    _git(repo, "checkout", "-b", "feat/x")
    f1 = _commit_with_date("feat-file.txt", "v1", "feat: introduce X", "2026-04-05T10:00:00+00:00")
    f2 = _commit_with_date("feat-file.txt", "v2", "feat: refine X", "2026-04-06T10:00:00+00:00")

    # Merge back into main
    _git(repo, "checkout", "main")
    env = {**env_base, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00+00:00",
           "GIT_COMMITTER_DATE": "2026-04-07T10:00:00+00:00"}
    subprocess.run(
        ["git", "-C", str(repo), "merge", "--no-ff", "feat/x", "-m", "merge feat/x"],
        check=True, env=env,
    )

    # Post-merge fix on main, touching feat-file.txt
    _commit_with_date("feat-file.txt", "v3 fixed", "fix: bug on X after merge",
                      "2026-04-08T10:00:00+00:00")

    return repo, "feat/x"


async def test_branch_first_fully_merged_no_anchor_falls_back_to_skill(
    client: Client, repo_with_merged_branch: tuple[Path, str], vault_tmp: Path,
) -> None:
    """v0.10.x post-Codex amendment: when the branch is fully merged AND no
    anchor is provided AND the name doesn't match any directory, the tool
    no longer invents a first-parent fallback. The branch ``feat/x`` strips
    to ``x`` (too short) so name-based auto-scope returns nothing — the
    resolution falls back to standard mode and warns the LLM to use the
    skill or supply an explicit anchor.
    """
    repo, branch = repo_with_merged_branch
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
    # Branch context resolution returned None → tool falls through to
    # standard discovery and warns the LLM. No first-parent fallback,
    # no sloppy 1000+-commit scope dive.
    assert any(
        "could not be resolved" in w.lower()
        or "fully merged" in w.lower()
        or "no commits" in w.lower()
        or "fall back" in w.lower()
        or "neither" in w.lower()
        for w in d["warnings"]
    )


@pytest.fixture
def repo_branch_merged_via_merge_commit(tmp_path: Path) -> tuple[Path, str]:
    """Repo where ``feat/x`` was merged into main via a real merge commit
    AND the branch ref was NOT advanced past the merge.

    main:   c0 ── M (merge feat/x)
                  /
    feat/x: c1 ── c2

    HEAD(feat/x) = c2 (preserved). Walking ``git log main --merges
    --first-parent`` finds M with parent2 == HEAD(feat/x) → mode
    'merged-via-merge-commit' kicks in (range = c0..M).
    """
    repo = tmp_path / "merge-commit-repo"
    repo.mkdir()
    _git_init_with_user(repo)
    _commit_file(repo, "README.md", "init", "c0")
    # Normalize default branch to 'main' across git versions.
    try:
        _git(repo, "branch", "-m", "main")
    except subprocess.CalledProcessError:
        pass
    _git(repo, "checkout", "-b", "feat/x")
    (repo / "src" / "x").mkdir(parents=True, exist_ok=True)
    _commit_file(repo, "src/x/a.py", "A", "feat: add a")
    _commit_file(repo, "src/x/b.py", "B", "feat: add b")
    _git(repo, "checkout", "main")
    subprocess.run(
        ["git", "-C", str(repo), "merge", "--no-ff", "-q",
         "-m", "merge feat/x", "feat/x"],
        check=True, capture_output=True, text=True,
    )
    return repo, "feat/x"


async def test_branch_first_merged_via_perimeter_runs_deterministically(
    client: Client,
    repo_branch_merged_via_merge_commit: tuple[Path, str],
    vault_tmp: Path,
) -> None:
    """End-to-end: archeo_git on a fully-merged branch with a real merge
    commit resolves via perimeter walker (mode 'merged-via-perimeter'),
    NOT via auto-scope-by-name. Frontmatter records branch + base.
    """
    repo, branch = repo_branch_merged_via_merge_commit
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
    # Resolution path surfaced in warnings — mentions perimeter walker.
    assert any(
        "perimeter walker" in w.lower()
        or "multi-signal" in w.lower()
        for w in d["warnings"]
    ), f"expected perimeter-walker warning, got: {d['warnings']}"
    # 1 cycle captured → 1 archive.
    assert d["milestones_processed"] >= 1
    # Frontmatter carries the branch + base.
    archives = list(
        (vault_tmp / "10-episodes" / "projects" / "alpha" / "archives").glob(
            "*archeo-git-*.md"
        )
    )
    assert archives, "expected at least one archive"
    fm, _body = frontmatter.read(archives[0])
    assert fm["branch"] == "feat/x"
    assert fm["branch_base"] == "main"
    assert fm["branch_base_sha"]


async def test_branch_first_C_since_sha_explicit_anchor(
    client: Client, repo_with_merged_branch: tuple[Path, str], vault_tmp: Path,
) -> None:
    """Strategy C — explicit since_sha bypasses merge-base entirely."""
    repo, branch = repo_with_merged_branch
    (vault_tmp / "10-episodes" / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    init_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--max-parents=0", "main"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    res = await client.call_tool(
        "mem_archeo_git",
        {
            "repo_path": str(repo),
            "project": "alpha",
            "level": "commits",
            "branch_first": branch,
            "since_sha": init_sha,
            "window": "day",
        },
    )
    d = res.structured_content
    # Same commits as the A test but anchored explicitly.
    assert d["milestones_processed"] >= 2
    assert any("since_sha" in w.lower() for w in d["warnings"])


@pytest.fixture
def repo_with_merged_branch_named_dir(tmp_path: Path) -> tuple[Path, str, str]:
    """Repo where branch ``ecosav`` is fully merged and the repo has a
    matching ``src/EcoSAV/`` directory — exercises the auto-scope-by-name
    path of branch_first resolution.
    """
    import os
    repo = tmp_path / "named-merged-repo"
    repo.mkdir()
    _git_init_with_user(repo)

    env_base = {**os.environ}

    def _commit(fname: str, content: str, msg: str, iso_date: str) -> None:
        target = repo / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        _git(repo, "add", fname)
        env = {**env_base,
               "GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date}
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-q", "-m", msg],
            check=True, env=env,
        )

    # main: initial commit + EcoSAV/ scaffolding so the directory pre-exists.
    _commit("README.md", "init", "init", "2026-04-01T10:00:00+00:00")
    try:
        _git(repo, "branch", "-m", "main")
    except subprocess.CalledProcessError:
        pass
    _commit("src/EcoSAV/Module.cls",
            "Class A",
            "scaffold EcoSAV",
            "2026-04-02T10:00:00+00:00")

    # Branch off and add a few changes inside EcoSAV/.
    _git(repo, "checkout", "-b", "ecosav")
    _commit("src/EcoSAV/Detail.cls",
            "Class B",
            "ecosav: detail",
            "2026-04-05T10:00:00+00:00")
    _commit("src/EcoSAV/Module.cls",
            "Class A v2",
            "ecosav: refine module",
            "2026-04-06T10:00:00+00:00")

    # Merge back into main, then keep ecosav HEAD pointing at the merged tip.
    _git(repo, "checkout", "main")
    env = {**env_base,
           "GIT_AUTHOR_DATE": "2026-04-07T10:00:00+00:00",
           "GIT_COMMITTER_DATE": "2026-04-07T10:00:00+00:00"}
    subprocess.run(
        ["git", "-C", str(repo), "merge", "--no-ff", "ecosav", "-m", "merge ecosav"],
        check=True, env=env,
    )
    # Fast-forward ecosav to match main so it really is fully absorbed.
    _git(repo, "checkout", "ecosav")
    _git(repo, "merge", "--ff-only", "main")
    _git(repo, "checkout", "main")
    return repo, "ecosav", "src/EcoSAV"


async def test_branch_first_perimeter_wins_over_name_heuristic_when_branch_ffd(
    client: Client,
    repo_with_merged_branch_named_dir: tuple[Path, str, str],
    vault_tmp: Path,
) -> None:
    """v0.10.x post-2026-05-09 amendment: even when the branch was ff'd onto
    base after the merge (HEAD(branch) == HEAD(base) → single-tip walker
    fails), the multi-signal perimeter walker captures the merge cycle via
    author + subject signals, winning over auto-scope-by-name (which is
    now the last-resort fallback for squash/rebase scenarios).
    """
    repo, branch, _expected_dir = repo_with_merged_branch_named_dir
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
    # Perimeter walker captured the merge cycle.
    assert any(
        "perimeter walker" in w.lower() or "multi-signal" in w.lower()
        for w in d["warnings"]
    ), f"expected perimeter-walker warning, got: {d['warnings']}"
    assert d["milestones_processed"] >= 1


def test_generate_name_variants_strips_common_prefixes() -> None:
    from memory_kit_mcp.tools.archeo_git import _generate_name_variants

    variants = _generate_name_variants("feat/dev-compta")
    # 'feat/' is a known prefix; 'dev-compta' is the bare name.
    assert any("dev-compta" in v.lower() for v in variants)
    assert any("devCompta" in v or "DevCompta" in v for v in variants)
    # The raw 'feat/dev-compta' string itself should NOT be in variants
    # (we strip the prefix before generating).
    assert all("feat/" not in v for v in variants)


def test_generate_name_variants_handles_short_names() -> None:
    """1-2 char tokens are dropped to avoid liberal directory matches."""
    from memory_kit_mcp.tools.archeo_git import _generate_name_variants

    # 'x' alone is too short — no variants should remain.
    assert _generate_name_variants("feat/x") == []
    # 'ab' is also too short, but the concatenated 'ab' as a 2-char token
    # would be filtered. Must return [] or only ≥3-char strings.
    short = _generate_name_variants("ab")
    for v in short:
        assert len(v) >= 3


def test_generate_name_variants_for_camel_case_branch() -> None:
    from memory_kit_mcp.tools.archeo_git import _generate_name_variants

    variants = _generate_name_variants("ecosav")
    variants_lower = {v.lower() for v in variants}
    assert "ecosav" in variants_lower
    # Concatenated UPPER variant must be present so directories like
    # ``ECOSAV`` would also match in the directory scan.
    assert "ECOSAV" in variants


async def test_branch_first_B_by_files_captures_post_merge_fixes(
    client: Client, repo_with_merged_branch: tuple[Path, str], vault_tmp: Path,
) -> None:
    """Strategy B — by_files queries commits TOUCHING the branch-introduced
    files repo-wide. Captures the post-merge fix that the bare range mode
    would miss.

    Post-amendment v0.10.x: the branch is fully merged AND its name is too
    short to auto-match. We provide an explicit ``since_sha`` (the initial
    commit on main) as the anchor — by_files then derives the introduced
    files from ``since_sha..branch`` and the repo-wide query catches the
    post-merge fix.
    """
    repo, branch = repo_with_merged_branch
    (vault_tmp / "10-episodes" / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    init_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--max-parents=0", "main"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    res = await client.call_tool(
        "mem_archeo_git",
        {
            "repo_path": str(repo),
            "project": "alpha",
            "level": "commits",
            "branch_first": branch,
            "branch_base": "main",
            "since_sha": init_sha,
            "by_files": True,
            "window": "day",
            "by_author": True,
        },
    )
    d = res.structured_content
    # The 2 branch commits + the 1 post-merge fix on main = 3 day-windows
    # covered by the file-driven query.
    assert d["milestones_processed"] >= 3
    assert any("by_files" in w.lower() or "branch-specific" in w.lower()
               for w in d["warnings"])


async def test_branch_first_C_since_date_floor(
    client: Client, repo_with_merged_branch: tuple[Path, str], vault_tmp: Path,
) -> None:
    """Strategy C alternative — since_date as floor."""
    repo, branch = repo_with_merged_branch
    (vault_tmp / "10-episodes" / "projects" / "alpha").mkdir(parents=True, exist_ok=True)
    res = await client.call_tool(
        "mem_archeo_git",
        {
            "repo_path": str(repo),
            "project": "alpha",
            "level": "commits",
            "branch_first": branch,
            "since_date": "2026-04-04",
            "window": "day",
        },
    )
    d = res.structured_content
    assert d["milestones_processed"] >= 1
    assert any("since_date" in w.lower() for w in d["warnings"])


# ---------------------------------------------------------------------------
# Phase 5 enforcement (v0.10.x post-Gemini-drift case study)
# ---------------------------------------------------------------------------


async def test_phase5_auto_inits_missing_project_skeleton(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    """Project doesn't exist before mem_archeo_git → auto-init context.md + history.md."""
    project_dir = vault_tmp / "10-episodes" / "projects" / "fresh-slug"
    assert not project_dir.exists()

    res = await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "fresh-slug", "level": "tags"},
    )
    d = res.data

    assert (project_dir / "context.md").is_file()
    assert (project_dir / "history.md").is_file()
    assert (project_dir / "archives").is_dir()
    # The created skeleton files appear in files_created.
    rels = [p.replace("\\", "/") for p in d.files_created]
    assert any("fresh-slug/context.md" in r for r in rels)
    assert any("fresh-slug/history.md" in r for r in rels)


async def test_phase5_history_md_lists_new_archives(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    """Each created archive is referenced in history.md (prepended)."""
    res = await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "histo-test", "level": "tags"},
    )
    assert res.data.archives_created == 3

    hist_path = vault_tmp / "10-episodes" / "projects" / "histo-test" / "history.md"
    body = hist_path.read_text(encoding="utf-8")
    # 3 archive entries prepended (one per tag v0.1.0 / v0.2.0 / v0.3.0).
    assert body.count("](archives/") >= 3


async def test_phase5_context_md_phase_updated(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    """context.md phase reflects the archeo run."""
    await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "ctx-test", "level": "tags"},
    )
    ctx_path = vault_tmp / "10-episodes" / "projects" / "ctx-test" / "context.md"
    fm, _ = frontmatter.read(ctx_path)
    assert "archeo-git run on" in str(fm.get("phase", ""))
    assert "archive(s) created" in str(fm.get("phase", ""))


async def test_phase5_root_index_lists_new_archives(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    """Each created archive is added to the root index.md ## Archives section."""
    # Ensure there's an Archives section in the index.
    index_path = vault_tmp / "index.md"
    index_path.write_text(
        "---\nzone: meta\ntype: index\n---\n\n# Vault index\n\n## Archives\n\n"
        "- (existing)\n",
        encoding="utf-8",
    )
    res = await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "idx-test", "level": "tags"},
    )
    body = index_path.read_text(encoding="utf-8")
    # 3 new archive entries inserted after ## Archives.
    for tag in ("v0-1-0", "v0-2-0", "v0-3-0"):
        assert tag in body, f"expected {tag} in index.md"


async def test_phase5_idempotent_history_no_duplicates(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    """Running archeo twice doesn't duplicate history.md entries."""
    await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "idem-test", "level": "tags"},
    )
    hist_path = (
        vault_tmp / "10-episodes" / "projects" / "idem-test" / "history.md"
    )
    body_first = hist_path.read_text(encoding="utf-8")
    count_first = body_first.count("](archives/")

    # Re-run — all archives should be skipped (idempotent), history not touched.
    await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "idem-test", "level": "tags"},
    )
    body_second = hist_path.read_text(encoding="utf-8")
    count_second = body_second.count("](archives/")
    assert count_first == count_second, (
        f"history.md entry count drifted on re-run: {count_first} -> {count_second}"
    )


async def test_phase5_preserves_existing_archives_when_initialising(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    """If the project folder already has archives but no context/history, init must NOT clobber the archives."""
    project_dir = vault_tmp / "10-episodes" / "projects" / "partial-slug"
    archives_dir = project_dir / "archives"
    archives_dir.mkdir(parents=True)
    legacy_archive = archives_dir / "2020-01-01-legacy.md"
    legacy_archive.write_text(
        "---\nproject: partial-slug\n---\n\n# Legacy\n", encoding="utf-8"
    )

    await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "partial-slug", "level": "tags"},
    )
    assert legacy_archive.is_file(), "legacy archive must survive Phase 5 init"
    assert (project_dir / "context.md").is_file()
    assert (project_dir / "history.md").is_file()


# ---------------------------------------------------------------------------
# Body skeleton enforcement (Jet 2 light, v0.10.x)
# ---------------------------------------------------------------------------


async def test_body_contains_all_five_mandatory_sections(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    """Every archeo-git archive body must carry the 5 mandatory sections, in order."""
    await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "body-test", "level": "tags"},
    )
    archives_dir = vault_tmp / "10-episodes" / "projects" / "body-test" / "archives"
    archives = sorted(archives_dir.glob("*.md"))
    assert archives, "expected at least one archive"
    for arc in archives:
        body = arc.read_text(encoding="utf-8")
        for section in (
            "## Analyse fonctionnelle",
            "## Analyse technique",
            "## AI files context",
            "## Friction & Resolution",
        ):
            assert section in body, (
                f"missing section '{section}' in archive body of {arc.name}"
            )
        # Order: fonctionnelle before technique before AI before Friction.
        idx_fn = body.index("## Analyse fonctionnelle")
        idx_tk = body.index("## Analyse technique")
        idx_ai = body.index("## AI files context")
        idx_fr = body.index("## Friction & Resolution")
        assert idx_fn < idx_tk < idx_ai < idx_fr, (
            f"section order broken in {arc.name}"
        )


async def test_body_analyse_sections_carry_explicit_fallback_marker(
    client: Client, vault_tmp: Path, repo_with_tags: Path
) -> None:
    """Empty Analyse fonctionnelle / technique sections carry the LLM TODO marker so
    drift (silent omission) is impossible to miss on review."""
    await client.call_tool(
        "mem_archeo_git",
        {"repo_path": str(repo_with_tags), "project": "fallback-test", "level": "tags"},
    )
    archives_dir = (
        vault_tmp / "10-episodes" / "projects" / "fallback-test" / "archives"
    )
    archives = sorted(archives_dir.glob("*.md"))
    for arc in archives:
        body = arc.read_text(encoding="utf-8")
        assert "_(LLM TODO" in body, (
            f"Analyse sections must carry explicit LLM TODO marker in {arc.name}"
        )
