"""Tests for mem_archeo_plan — Phase 0 interactive cadrage.

Spec: core/procedures/mem-archeo-git.md Phase 0.

Each test crafts a tiny synthetic git repo + vault skeleton and asserts on
the structured ArcheoPlan: identity capture, branch resolution, slug
proposal, project init flag, scope mode, granularity proposal, filters,
warnings.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastmcp import Client


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )


def _git_init_with_user(path: Path, email: str = "user@example.com",
                         name: str = "User Self") -> None:
    # -b main forces the initial branch name regardless of the user's global
    # init.defaultBranch (older git defaults to master).
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    _git(path, "config", "user.email", email)
    _git(path, "config", "user.name", name)
    _git(path, "config", "commit.gpgsign", "false")


def _commit_file(
    repo: Path, fname: str, content: str, message: str,
    author_email: str | None = None, author_name: str | None = None,
) -> str:
    (repo / fname).parent.mkdir(parents=True, exist_ok=True)
    (repo / fname).write_text(content, encoding="utf-8")
    _git(repo, "add", fname)
    env_args = []
    if author_email or author_name:
        env_args = [
            "-c", f"user.email={author_email or 'user@example.com'}",
            "-c", f"user.name={author_name or 'User Self'}",
        ]
    subprocess.run(
        ["git", "-C", str(repo), *env_args, "commit", "-q", "-m", message],
        check=True, capture_output=True, text=True,
    )
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _checkout_branch(repo: Path, name: str, *, create: bool = True) -> None:
    if create:
        _git(repo, "checkout", "-q", "-b", name)
    else:
        _git(repo, "checkout", "-q", name)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_solo_human_branch(tmp_path: Path) -> Path:
    """Solo branch 'ecosav' with 3 commits, alive (not merged), human-readable name."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_user(repo)
    # default branch = main
    _commit_file(repo, "README.md", "# init", "initial commit on main")
    _checkout_branch(repo, "ecosav")
    _commit_file(repo, "src/EcoSAV/Detail.cls", "Class A {}", "feat: detail")
    _commit_file(repo, "src/EcoSAV/Devis.cls", "Class B {}", "feat: devis")
    _commit_file(repo, "src/EcoSAV/Materiel.cls", "Class C {}", "feat: materiel")
    return repo


@pytest.fixture
def repo_multi_author_branch(tmp_path: Path) -> Path:
    """Branch 'feature-foo' with 3 authors, several commits."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_user(repo)
    _commit_file(repo, "README.md", "# init", "initial")
    _checkout_branch(repo, "feature-foo")
    _commit_file(repo, "a.txt", "1", "a", author_email="user@example.com",
                 author_name="User Self")
    _commit_file(repo, "b.txt", "2", "b", author_email="bob@example.com",
                 author_name="Bob")
    _commit_file(repo, "c.txt", "3", "c", author_email="alice@example.com",
                 author_name="Alice")
    return repo


@pytest.fixture
def repo_cryptic_branch(tmp_path: Path) -> Path:
    """Branch 'JIRA-1234' (cryptic ticket-style name)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_user(repo)
    _commit_file(repo, "README.md", "# init", "initial")
    _checkout_branch(repo, "JIRA-1234")
    _commit_file(repo, "fix.txt", "x", "fix")
    return repo


@pytest.fixture
def repo_fully_merged_branch(tmp_path: Path) -> Path:
    """Branch 'ecosav' fully merged into main (merge-base == HEAD).

    No real merge commit on main first-parent — the branch ref simply
    points at a base-side commit (squash-merge / rebase-and-ff scenario).
    Used to exercise the auto-scope-by-name fallback path.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_user(repo)
    _commit_file(repo, "README.md", "# init", "initial")
    _commit_file(repo, "src/EcoSAV/x.cls", "x", "feat: ecosav x")
    _checkout_branch(repo, "ecosav")
    # branch points at the same HEAD as main → fully merged
    return repo


@pytest.fixture
def repo_merged_via_merge_commit(tmp_path: Path) -> Path:
    """Branch 'ecosav' merged into main via a true merge commit (--no-ff).

    main:  c0 ── M (merge ecosav)
                /
    ecosav: c1 ── c2

    HEAD(main) = M, HEAD(ecosav) = c2 (preserved as branch tip).
    M.parent1 = c0 (merge_base at merge time), M.parent2 = c2.
    Walking ``git log main --merges --first-parent`` finds M with
    parent2 == HEAD(ecosav) → mode='merged-via-merge-commit'.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_user(repo)
    _commit_file(repo, "README.md", "# init", "c0 on main")
    _checkout_branch(repo, "ecosav")
    _commit_file(repo, "src/EcoSAV/Detail.cls", "A", "feat: detail")
    _commit_file(repo, "src/EcoSAV/Devis.cls", "B", "feat: devis")
    _checkout_branch(repo, "main", create=False)
    # --no-ff forces a real merge commit even when ff would be possible.
    subprocess.run(
        ["git", "-C", str(repo), "merge", "--no-ff", "-q",
         "-m", "Merge ecosav into main", "ecosav"],
        check=True, capture_output=True, text=True,
    )
    return repo


# ---------------------------------------------------------------------------
# user_self capture
# ---------------------------------------------------------------------------


async def test_captures_user_identity_from_git_config(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    plan = res.data
    assert plan.user_self.email == "user@example.com"
    assert plan.user_self.name == "User Self"


# ---------------------------------------------------------------------------
# Branch resolution
# ---------------------------------------------------------------------------


async def test_resolves_current_branch_from_head_when_unspecified(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    assert res.data.branch.name == "ecosav"
    assert res.data.branch.base == "main"
    assert res.data.branch.fully_merged is False
    assert res.data.branch.commits_count == 3


async def test_explicit_branch_arg_overrides_head(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch), "branch": "main"},
    )
    assert res.data.branch.name == "main"


async def test_detects_fully_merged_branch(
    client: Client, repo_fully_merged_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {
            "repo_path": str(repo_fully_merged_branch),
            "branch": "ecosav",
            "branch_base": "main",
        },
    )
    assert res.data.branch.fully_merged is True
    # commits_count is repopulated from the auto-scope-by-name lineage when
    # the merge-base range is empty: the EcoSAV/ dir was touched by 1 commit.
    assert res.data.branch.commits_count == 1


# ---------------------------------------------------------------------------
# Slug proposal
# ---------------------------------------------------------------------------


async def test_human_readable_branch_yields_trusted_slug(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    assert res.data.slug.candidate == "ecosav"
    assert res.data.slug.source == "branch-name"
    assert res.data.slug.needs_confirmation is False


async def test_cryptic_branch_yields_needs_prompt(
    client: Client, repo_cryptic_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_cryptic_branch)},
    )
    assert res.data.slug.needs_confirmation is True
    assert res.data.slug.source == "needs-prompt"


async def test_explicit_project_arg_overrides_heuristic(
    client: Client, repo_cryptic_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_cryptic_branch), "project": "my-project"},
    )
    assert res.data.slug.candidate == "my-project"
    assert res.data.slug.source == "project-arg"
    assert res.data.slug.needs_confirmation is False


# ---------------------------------------------------------------------------
# Project existence + init flag
# ---------------------------------------------------------------------------


async def test_project_will_init_when_missing(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    """Vault has no 'ecosav' project → will_init=True."""
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    assert res.data.project.exists is False
    assert res.data.project.will_init is True
    assert "10-episodes/projects/ecosav" in res.data.project.path


async def test_project_exists_when_present_in_vault(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    # Pre-create the project
    proj_dir = vault_tmp / "10-episodes" / "projects" / "ecosav"
    proj_dir.mkdir(parents=True)
    (proj_dir / "context.md").write_text("---\nproject: ecosav\n---\n", encoding="utf-8")
    (proj_dir / "history.md").write_text("---\nproject: ecosav\n---\n", encoding="utf-8")
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    assert res.data.project.exists is True
    assert res.data.project.will_init is False


# ---------------------------------------------------------------------------
# Scope proposal
# ---------------------------------------------------------------------------


async def test_live_scope_for_alive_branch(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    assert res.data.scope.mode == "live"
    assert res.data.scope.files_count_estimate >= 3  # 3 EcoSAV files


async def test_auto_scope_by_name_when_fully_merged_with_dir_match(
    client: Client, repo_fully_merged_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {
            "repo_path": str(repo_fully_merged_branch),
            "branch": "ecosav",
            "branch_base": "main",
        },
    )
    # branch 'ecosav' + repo has src/EcoSAV/ → auto-scope-by-name kicks in
    assert res.data.scope.mode == "auto-scope-by-name"
    assert res.data.scope.scope_glob is not None
    assert "EcoSAV" in res.data.scope.scope_glob or "ecosav" in res.data.scope.scope_glob.lower()


async def test_merged_via_perimeter_when_real_merge_exists(
    client: Client, repo_merged_via_merge_commit: Path, vault_tmp: Path
) -> None:
    """A --no-ff merge of ecosav into main → perimeter walker captures
    that single cycle → mode='merged-via-perimeter'.

    Scope is the union of files touched by every captured merge cycle.
    """
    res = await client.call_tool(
        "mem_archeo_plan",
        {
            "repo_path": str(repo_merged_via_merge_commit),
            "branch": "ecosav",
            "branch_base": "main",
        },
    )
    assert res.data.branch.fully_merged is True
    assert res.data.scope.mode == "merged-via-perimeter"
    # 2 EcoSAV files introduced on the branch — both captured.
    assert res.data.scope.files_count_estimate >= 2
    # Repop: 1 cycle, range M^1..M = 2 branch commits + the merge commit M.
    assert res.data.branch.commits_count == 3
    # Warning surface mentions perimeter resolution.
    assert any(
        "perimeter" in w.lower() or "multi-signal" in w.lower()
        for w in res.data.warnings
    )


async def test_perimeter_walker_takes_priority_over_name_heuristic(
    client: Client, repo_merged_via_merge_commit: Path, vault_tmp: Path
) -> None:
    """Even when src/EcoSAV/ exists (name heuristic would match), the
    perimeter walker wins because it is multi-signal deterministic."""
    res = await client.call_tool(
        "mem_archeo_plan",
        {
            "repo_path": str(repo_merged_via_merge_commit),
            "branch": "ecosav",
            "branch_base": "main",
        },
    )
    assert res.data.scope.mode == "merged-via-perimeter"
    assert res.data.scope.scope_glob is None  # no glob — uses captured merges


async def test_refusal_when_fully_merged_no_match(
    client: Client, tmp_path: Path, vault_tmp: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_with_user(repo)
    _commit_file(repo, "README.md", "# init", "init")
    _checkout_branch(repo, "totally-unrelated-name-xyz")
    # branch fully merged into main, no matching dir
    res = await client.call_tool(
        "mem_archeo_plan",
        {
            "repo_path": str(repo),
            "branch": "totally-unrelated-name-xyz",
            "branch_base": "main",
        },
    )
    assert res.data.scope.mode == "refusal"


# ---------------------------------------------------------------------------
# Authors + filters
# ---------------------------------------------------------------------------


async def test_solo_branch_proposes_author_self_only(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    assert res.data.is_solo_branch is True
    assert res.data.filters.author_self_only is True
    assert res.data.filters.include_team is False


async def test_multi_author_branch_proposes_team_inclusion(
    client: Client, repo_multi_author_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_multi_author_branch)},
    )
    emails = {a.email for a in res.data.branch_authors}
    assert {"user@example.com", "bob@example.com", "alice@example.com"} <= emails
    assert res.data.is_solo_branch is False
    assert res.data.filters.author_self_only is False
    assert res.data.filters.include_team is True


# ---------------------------------------------------------------------------
# Granularity proposal
# ---------------------------------------------------------------------------


async def test_solo_branch_with_few_commits_uses_window_month_or_week(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    # 3 commits, no merges, solo → by-window-month
    assert res.data.granularity.proposed in ("by-window-month", "by-window-week")
    assert "by-author" not in res.data.granularity.proposed


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


async def test_warns_when_project_will_init(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    assert any("does not exist" in w for w in res.data.warnings)


async def test_warns_when_slug_cryptic(
    client: Client, repo_cryptic_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_cryptic_branch)},
    )
    assert any("cryptic" in w.lower() for w in res.data.warnings)


async def test_warns_when_branch_fully_merged_with_match(
    client: Client, repo_fully_merged_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {
            "repo_path": str(repo_fully_merged_branch),
            "branch": "ecosav",
            "branch_base": "main",
        },
    )
    assert any("fully merged" in w.lower() for w in res.data.warnings)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


async def test_raises_on_non_directory_path(
    client: Client, tmp_path: Path, vault_tmp: Path
) -> None:
    with pytest.raises(Exception) as exc_info:
        await client.call_tool(
            "mem_archeo_plan",
            {"repo_path": str(tmp_path / "nonexistent")},
        )
    assert "not a directory" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Summary md
# ---------------------------------------------------------------------------


async def test_next_call_carries_branch_first_for_perimeter_mode(
    client: Client, repo_merged_via_merge_commit: Path, vault_tmp: Path
) -> None:
    """next_call MUST include branch_first when scope.mode triggers it.
    Without this, free-form translation drops branch_first and standard
    discovery fires (case study 2026-05-09 IRIS USER → 2 archives instead
    of 30+ across 30 ecosav cycles)."""
    res = await client.call_tool(
        "mem_archeo_plan",
        {
            "repo_path": str(repo_merged_via_merge_commit),
            "branch": "ecosav",
            "branch_base": "main",
        },
    )
    nc = res.data.next_call
    assert nc, "next_call must be populated for non-refusal modes"
    assert nc["branch_first"] == "ecosav"
    assert nc["branch_base"] == "main"
    assert nc["project"] == "ecosav"
    assert nc["repo_path"]


async def test_next_call_carries_branch_first_for_live_mode(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    nc = res.data.next_call
    assert nc["branch_first"] == "ecosav"
    assert nc["branch_base"] == "main"


async def test_next_call_empty_on_refusal(
    client: Client, tmp_path, vault_tmp: Path
) -> None:
    """When scope.mode == 'refusal', next_call is empty — caller MUST
    re-invoke with explicit anchor."""
    repo = tmp_path / "refusal_repo"
    repo.mkdir()
    _git_init_with_user(repo)
    _commit_file(repo, "README.md", "init", "init")
    _checkout_branch(repo, "totally-unrelated-name-xyz")
    res = await client.call_tool(
        "mem_archeo_plan",
        {
            "repo_path": str(repo),
            "branch": "totally-unrelated-name-xyz",
            "branch_base": "main",
        },
    )
    assert res.data.scope.mode == "refusal"
    assert res.data.next_call == {}


async def test_summary_md_includes_next_call_block(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    md = res.data.summary_md
    assert "Next call (LITERAL — do not translate)" in md
    # Targets the orchestrator now (post-2026-05-09), not mem_archeo_git
    # directly — chains Phase 0/2/3 + Phase 1 brief auto-prepared.
    assert "mem_archeo(" in md
    assert "branch_first=" in md
    assert "acknowledged_via_plan=True" in md


async def test_summary_md_contains_key_sections(
    client: Client, repo_solo_human_branch: Path, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_archeo_plan",
        {"repo_path": str(repo_solo_human_branch)},
    )
    md = res.data.summary_md
    assert "## mem_archeo_plan" in md
    assert "Branch:" in md
    assert "Slug proposal" in md
    assert "Project" in md
    assert "Scope" in md
    assert "Granularity" in md
    assert "Filters" in md
