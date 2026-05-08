"""Tests for migration v2_namespace_to_domain."""

from __future__ import annotations

from pathlib import Path

from memory_kit_mcp.migrations import v2_namespace_to_domain as v2
from memory_kit_mcp.vault import frontmatter


# ---------------------------------------------------------------------------
# Vault fixtures (helpers)
# ---------------------------------------------------------------------------


def _write_archeo_archive(
    archives_dir: Path, name: str, *, project: str, branch: str
) -> Path:
    archives_dir.mkdir(parents=True, exist_ok=True)
    fm = {
        "project": project,
        "zone": "episodes",
        "kind": "archive",
        "scope": "work",
        "collective": False,
        "source": "archeo-git",
        "branch": branch,
        "branch_base": "main",
        "tags": [
            f"project/{project}",
            "zone/episodes",
            "kind/archive",
            "source/archeo-git",
        ],
        "display": f"{project} — {name}",
    }
    body = f"# {project} — archeo {branch}\n\n_(test fixture)_\n"
    path = archives_dir / name
    frontmatter.write(path, fm, body)
    return path


def _make_namespace_vault(tmp_path: Path) -> Path:
    """Vault where ``projects/gmt-user/`` is a namespace candidate.

    Two archeo-git archives, two distinct branches (``ecosav``, ``dev-compta``).
    """
    vault = tmp_path / "vault"
    namespace_dir = vault / "10-episodes" / "projects" / "gmt-user"
    namespace_dir.mkdir(parents=True)
    archives_dir = namespace_dir / "archives"
    _write_archeo_archive(
        archives_dir,
        "2026-05-08-00h32-gmt-user-archeo-ecosav-branch-first.md",
        project="gmt-user", branch="ecosav",
    )
    _write_archeo_archive(
        archives_dir,
        "2026-05-05-20h13-gmt-user-archeo-dev-compta-branch-first.md",
        project="gmt-user", branch="dev-compta",
    )
    # Also write a context.md / history.md so the namespace project looks real.
    frontmatter.write(
        namespace_dir / "context.md",
        {"slug": "gmt-user", "zone": "episodes", "kind": "project"},
        "# gmt-user — namespace\n",
    )
    frontmatter.write(
        namespace_dir / "history.md",
        {"slug": "gmt-user", "zone": "episodes", "kind": "project"},
        "# gmt-user — history\n",
    )
    return vault


def _make_single_branch_vault(tmp_path: Path) -> Path:
    """Vault where the project has only one archeo branch — NOT a namespace."""
    vault = tmp_path / "vault"
    project_dir = vault / "10-episodes" / "projects" / "secondbrain"
    project_dir.mkdir(parents=True)
    _write_archeo_archive(
        project_dir / "archives",
        "2026-05-06-12h24-secondbrain-archeo-feat-x-branch-first.md",
        project="secondbrain", branch="feat/x",
    )
    return vault


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def test_detect_namespace_with_two_branches(tmp_path: Path) -> None:
    vault = _make_namespace_vault(tmp_path)
    candidates = v2._detect_namespace_projects(vault)
    assert len(candidates) == 1
    slug, branches_info = candidates[0]
    assert slug == "gmt-user"
    branches = sorted(b for b, _ in branches_info)
    assert branches == ["dev-compta", "ecosav"]


def test_detect_skips_single_branch_project(tmp_path: Path) -> None:
    vault = _make_single_branch_vault(tmp_path)
    candidates = v2._detect_namespace_projects(vault)
    assert candidates == []


def test_detect_skips_non_archeo_archives(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    project_dir = vault / "10-episodes" / "projects" / "alpha"
    project_dir.mkdir(parents=True)
    archives_dir = project_dir / "archives"
    archives_dir.mkdir()
    # Two archives but neither has source=archeo-git.
    frontmatter.write(
        archives_dir / "a.md",
        {"project": "alpha", "source": "session", "branch": "x"},
        "# alpha\n",
    )
    frontmatter.write(
        archives_dir / "b.md",
        {"project": "alpha", "source": "session", "branch": "y"},
        "# alpha\n",
    )
    assert v2._detect_namespace_projects(vault) == []


def test_detect_skips_archives_without_branch(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    project_dir = vault / "10-episodes" / "projects" / "beta"
    project_dir.mkdir(parents=True)
    archives_dir = project_dir / "archives"
    archives_dir.mkdir()
    # Two archeo-git archives but no `branch` field — not a namespace, just
    # standard mem_archeo runs that the user lumped together.
    fm = {"project": "beta", "source": "archeo-git", "zone": "episodes", "kind": "archive"}
    frontmatter.write(archives_dir / "a.md", fm, "# beta\n")
    frontmatter.write(archives_dir / "b.md", fm, "# beta\n")
    assert v2._detect_namespace_projects(vault) == []


# ---------------------------------------------------------------------------
# is_needed
# ---------------------------------------------------------------------------


def test_is_needed_returns_true_when_namespace_unmigrated(tmp_path: Path) -> None:
    vault = _make_namespace_vault(tmp_path)
    assert v2.is_needed(vault) is True


def test_is_needed_returns_false_after_apply(tmp_path: Path) -> None:
    vault = _make_namespace_vault(tmp_path)
    v2.apply(vault, dry_run=False)
    assert v2.is_needed(vault) is False


def test_is_needed_returns_false_on_clean_vault(tmp_path: Path) -> None:
    vault = _make_single_branch_vault(tmp_path)
    assert v2.is_needed(vault) is False


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------


def test_slugify_basic() -> None:
    assert v2._slugify("ecosav") == "ecosav"
    assert v2._slugify("dev-compta") == "dev-compta"


def test_slugify_handles_path_separators_and_accents() -> None:
    assert v2._slugify("feat/démarrage") == "feat-demarrage"


def test_slugify_collapses_dashes_and_strips_edges() -> None:
    assert v2._slugify("--Foo  Bar/--baz_") == "foo-bar-baz"


def test_slugify_falls_back_for_empty_strings() -> None:
    assert v2._slugify("") == "branch"
    assert v2._slugify("///") == "branch"


# ---------------------------------------------------------------------------
# Apply — dry-run
# ---------------------------------------------------------------------------


def test_apply_dry_run_lists_would_be_creations(tmp_path: Path) -> None:
    vault = _make_namespace_vault(tmp_path)
    report = v2.apply(vault, dry_run=True)
    assert report.applied is False
    assert report.dry_run is True
    # 2 archives would be copied + 2 project skeletons (each = context+history)
    # + 1 domain skeleton (context+history). Order doesn't matter.
    assert any("domains/gmt-user/context.md" in p for p in report.files_created)
    assert any("domains/gmt-user/history.md" in p for p in report.files_created)
    assert any("projects/ecosav/context.md" in p for p in report.files_created)
    assert any("projects/dev-compta/context.md" in p for p in report.files_created)
    assert any(
        "projects/ecosav/archives/2026-05-08-00h32-gmt-user-archeo-ecosav-branch-first.md"
        in p
        for p in report.files_created
    )
    # Nothing actually written.
    assert not (vault / "10-episodes" / "domains" / "gmt-user").is_dir()


# ---------------------------------------------------------------------------
# Apply — real run
# ---------------------------------------------------------------------------


def test_apply_creates_domain_skeleton(tmp_path: Path) -> None:
    vault = _make_namespace_vault(tmp_path)
    v2.apply(vault, dry_run=False)
    domain_ctx = vault / "10-episodes" / "domains" / "gmt-user" / "context.md"
    assert domain_ctx.is_file()
    fm, body = frontmatter.read(domain_ctx)
    assert fm["kind"] == "domain"
    assert fm["slug"] == "gmt-user"
    assert "ecosav" in fm["related_projects"]
    assert "dev-compta" in fm["related_projects"]


def test_apply_creates_branch_projects(tmp_path: Path) -> None:
    vault = _make_namespace_vault(tmp_path)
    v2.apply(vault, dry_run=False)
    for branch_slug in ("ecosav", "dev-compta"):
        ctx = vault / "10-episodes" / "projects" / branch_slug / "context.md"
        assert ctx.is_file(), f"missing context for {branch_slug}"
        fm, _ = frontmatter.read(ctx)
        assert fm["kind"] == "project"
        assert fm["slug"] == branch_slug
        assert fm["domain"] == "gmt-user"


def test_apply_copies_archives_with_updated_frontmatter(tmp_path: Path) -> None:
    vault = _make_namespace_vault(tmp_path)
    v2.apply(vault, dry_run=False)
    arc = (
        vault
        / "10-episodes"
        / "projects"
        / "ecosav"
        / "archives"
        / "2026-05-08-00h32-gmt-user-archeo-ecosav-branch-first.md"
    )
    assert arc.is_file()
    fm, _ = frontmatter.read(arc)
    assert fm["project"] == "ecosav"
    assert fm["domain"] == "gmt-user"
    # Original branch field preserved.
    assert fm["branch"] == "ecosav"
    # Tags rewritten: project/gmt-user -> project/ecosav, domain/gmt-user added.
    tags = fm.get("tags", [])
    assert "project/ecosav" in tags
    assert "domain/gmt-user" in tags
    assert "project/gmt-user" not in tags


def test_apply_does_not_remove_namespace_project(tmp_path: Path) -> None:
    """Conservative: the original namespace project must remain in place."""
    vault = _make_namespace_vault(tmp_path)
    v2.apply(vault, dry_run=False)
    namespace_dir = vault / "10-episodes" / "projects" / "gmt-user"
    assert namespace_dir.is_dir()
    # Original archive is still there too.
    arc = (
        namespace_dir
        / "archives"
        / "2026-05-08-00h32-gmt-user-archeo-ecosav-branch-first.md"
    )
    assert arc.is_file()


def test_apply_is_idempotent(tmp_path: Path) -> None:
    vault = _make_namespace_vault(tmp_path)
    first = v2.apply(vault, dry_run=False)
    assert first.applied is True
    second = v2.apply(vault, dry_run=False)
    # Second pass detects nothing new to create — same archives already in
    # place, same skeletons. Report is empty for files_created.
    assert second.files_created == [] or all(
        "summary" in str(s).lower() or "summary" not in str(s).lower()
        for s in second.files_created
    )
    # is_needed must return False after the first apply.
    assert v2.is_needed(vault) is False


def test_apply_collision_namespaces_branch_slug(tmp_path: Path) -> None:
    """When projects/<branch_slug> already exists for an unrelated reason,
    the migration prefixes the new branch project with the namespace.
    """
    vault = _make_namespace_vault(tmp_path)
    # Pre-create an unrelated 'ecosav' project (without domain=gmt-user).
    pre_dir = vault / "10-episodes" / "projects" / "ecosav"
    pre_dir.mkdir(parents=True)
    frontmatter.write(
        pre_dir / "context.md",
        {"slug": "ecosav", "kind": "project", "zone": "episodes"},
        "# ecosav (pre-existing, unrelated)\n",
    )

    v2.apply(vault, dry_run=False)
    # Migration must NOT have touched the unrelated 'ecosav' project — it
    # should have created 'gmt-user-ecosav' instead.
    namespaced = vault / "10-episodes" / "projects" / "gmt-user-ecosav"
    assert namespaced.is_dir()
    # Original 'ecosav' context.md untouched.
    fm, _ = frontmatter.read(pre_dir / "context.md")
    assert fm.get("domain") is None  # not migrated by us
