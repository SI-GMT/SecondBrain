"""Tests for memory_kit_mcp.archeo.topology.enumerate_files."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from memory_kit_mcp.archeo import (
    BATCH_SIZE_DEFAULT,
    DEFAULT_IGNORE_DIRS,
    EnumerateResult,
    ScopeOverflowError,
    detect_mode,
    enumerate_files,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def raw_repo(tmp_path: Path) -> Path:
    """Plain directory tree (no .git/) with a mix of code, ignored dirs, junk."""
    repo = tmp_path / "raw_repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "alpha.py").write_text("print('alpha')\n", encoding="utf-8")
    (repo / "src" / "beta.py").write_text("print('beta')\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_alpha.py").write_text("# test\n", encoding="utf-8")
    (repo / "README.md").write_text("# raw\n", encoding="utf-8")
    # Decoys — must be ignored.
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "junk.js").write_text("//\n", encoding="utf-8")
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "alpha.cpython-312.pyc").write_text("", encoding="utf-8")
    (repo / "src" / "compiled.pyc").write_text("", encoding="utf-8")
    (repo / "build").mkdir()
    (repo / "build" / "out.txt").write_text("artifact\n", encoding="utf-8")
    return repo


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Git repo with a main branch and a feature branch carrying 2 distinct files."""
    repo = tmp_path / "git_repo"
    repo.mkdir()
    _git(["init", "--initial-branch=main"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)

    # Initial commit on main
    (repo / "README.md").write_text("# main\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "core.py").write_text("CORE = 1\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-m", "initial"], repo)

    # Feature branch — adds 2 files, modifies one
    _git(["checkout", "-b", "feature/x"], repo)
    (repo / "src" / "feature.py").write_text("FEATURE = 1\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "feature.md").write_text("# feature docs\n", encoding="utf-8")
    (repo / "src" / "core.py").write_text("CORE = 2\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-m", "feat: add feature.py + feature.md"], repo)

    return repo


# ---------------------------------------------------------------------------
# detect_mode
# ---------------------------------------------------------------------------


def test_detect_mode_git(git_repo: Path) -> None:
    assert detect_mode(git_repo) == "git"


def test_detect_mode_raw(raw_repo: Path) -> None:
    assert detect_mode(raw_repo) == "raw"


# ---------------------------------------------------------------------------
# Raw mode
# ---------------------------------------------------------------------------


def test_raw_mode_lists_files(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw")
    files_str = [str(f) for f in result.files]
    assert "src/alpha.py" in files_str
    assert "src/beta.py" in files_str
    assert "README.md" in files_str
    assert "tests/test_alpha.py" in files_str


def test_raw_mode_skips_ignored_dirs(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw")
    files_str = [str(f) for f in result.files]
    assert not any("node_modules" in f for f in files_str)
    assert not any("__pycache__" in f for f in files_str)
    assert not any("build/" in f for f in files_str)


def test_raw_mode_skips_pyc_suffix(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw")
    files_str = [str(f) for f in result.files]
    assert not any(f.endswith(".pyc") for f in files_str)


def test_raw_mode_branch_param_ignored(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw", branch="feature/x")
    assert any("ignored in raw mode" in w for w in result.warnings)
    assert result.branch is None


def test_raw_mode_source_mode(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="auto")
    assert result.source_mode == "raw"


# ---------------------------------------------------------------------------
# Scope glob
# ---------------------------------------------------------------------------


def test_scope_glob_filters(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw", scope_glob="src/*.py")
    files_str = [str(f) for f in result.files]
    assert files_str == ["src/alpha.py", "src/beta.py"]
    assert result.scope_glob == "src/*.py"


def test_scope_glob_no_match(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw", scope_glob="nope/**")
    assert result.files == []
    assert result.files_count == 0
    assert result.files_bytes == 0
    assert result.batches == [[]]


# ---------------------------------------------------------------------------
# Git mode — full inventory
# ---------------------------------------------------------------------------


def test_git_mode_full_inventory(git_repo: Path) -> None:
    result = enumerate_files(git_repo, mode="git")
    files_str = [str(f) for f in result.files]
    # On main (default checkout is feature/x after fixture)
    assert "README.md" in files_str
    assert "src/core.py" in files_str


def test_git_mode_source_mode(git_repo: Path) -> None:
    result = enumerate_files(git_repo, mode="auto")
    assert result.source_mode == "git"


# ---------------------------------------------------------------------------
# Git mode — branch-first Pass A
# ---------------------------------------------------------------------------


def test_git_branch_first_pass_a(git_repo: Path) -> None:
    """Pass A on feature/x captures the 2 created files + the modified one."""
    result = enumerate_files(git_repo, mode="git", branch="feature/x")
    files_str = sorted(str(f) for f in result.files)
    assert files_str == [
        "docs/feature.md",
        "src/core.py",
        "src/feature.py",
    ]
    assert result.branch == "feature/x"
    assert result.base_ref is not None
    assert result.merge_base_strategy == "merge-base"


def test_git_branch_first_with_explicit_base_ref(git_repo: Path) -> None:
    base_sha = subprocess.run(
        ["git", "rev-parse", "main"],
        cwd=str(git_repo),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    result = enumerate_files(
        git_repo, mode="git", branch="feature/x", base_ref=base_sha
    )
    assert result.base_ref == base_sha
    assert result.merge_base_strategy == "manual"


def test_git_branch_first_fully_merged_raises_without_anchor(
    git_repo: Path,
) -> None:
    """When the branch is fully merged into main and no base_ref is given,
    the lib refuses to invent a fallback (v0.10.x post-Codex amendment —
    first-parent-fallback retired).
    """
    from memory_kit_mcp.archeo.topology import BranchScopeUnresolvedError

    _git(["checkout", "main"], git_repo)
    _git(["merge", "--no-ff", "-m", "merge feature/x", "feature/x"], git_repo)
    _git(["checkout", "feature/x"], git_repo)

    with pytest.raises(BranchScopeUnresolvedError) as exc_info:
        enumerate_files(git_repo, mode="git", branch="feature/x")
    msg = str(exc_info.value)
    assert "fully merged" in msg
    assert "base_ref" in msg


def test_git_branch_first_fully_merged_works_with_explicit_base_ref(
    git_repo: Path,
) -> None:
    """The escape hatch: pass an explicit ``base_ref`` to anchor the scope on
    a fully-merged branch. No fallback dérive, fully under user control.
    """
    _git(["checkout", "main"], git_repo)
    _git(["merge", "--no-ff", "-m", "merge feature/x", "feature/x"], git_repo)
    _git(["checkout", "feature/x"], git_repo)

    initial_sha = subprocess.run(
        ["git", "rev-list", "--max-parents=0", "main"],
        cwd=str(git_repo),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    result = enumerate_files(
        git_repo, mode="git", branch="feature/x", base_ref=initial_sha
    )
    assert result.merge_base_strategy == "manual"
    assert result.files_count > 0


# ---------------------------------------------------------------------------
# Soft caps + warnings
# ---------------------------------------------------------------------------


def test_soft_cap_files_emits_warning(raw_repo: Path) -> None:
    # Only 4 real files; cap at 1 to force overflow.
    result = enumerate_files(raw_repo, mode="raw", max_files=1)
    assert result.files_count >= 2  # full list intact
    assert any("ScopeOverflowWarning" in w for w in result.warnings)


def test_soft_cap_zero_disables(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw", max_files=0, max_bytes=0)
    assert result.warnings == []  # no overflow possible


def test_hard_abort_raises(raw_repo: Path) -> None:
    with pytest.raises(ScopeOverflowError):
        enumerate_files(raw_repo, mode="raw", max_files=1, hard_abort=True)


def test_warning_contains_batch_suggestion(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw", max_files=1, batch_size=2)
    assert any("batch_size=2" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Batches
# ---------------------------------------------------------------------------


def test_batches_default_size(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw")
    # All under 200 → single batch.
    assert len(result.batches) == 1
    assert result.batches[0] == result.files


def test_batches_custom_size(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw", batch_size=2)
    expected_batch_count = (result.files_count + 1) // 2
    assert len(result.batches) == max(1, expected_batch_count)
    for batch in result.batches[:-1]:
        assert len(batch) == 2


def test_batches_empty_files_yields_one_empty_batch(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = enumerate_files(empty, mode="raw")
    assert result.batches == [[]]


# ---------------------------------------------------------------------------
# files_hash determinism
# ---------------------------------------------------------------------------


def test_files_hash_stable_across_runs(raw_repo: Path) -> None:
    a = enumerate_files(raw_repo, mode="raw")
    b = enumerate_files(raw_repo, mode="raw")
    assert a.files_hash == b.files_hash


def test_files_hash_changes_on_added_file(raw_repo: Path) -> None:
    a = enumerate_files(raw_repo, mode="raw")
    (raw_repo / "src" / "gamma.py").write_text("# new\n", encoding="utf-8")
    b = enumerate_files(raw_repo, mode="raw")
    assert a.files_hash != b.files_hash


# ---------------------------------------------------------------------------
# Pass B — Python imports
# ---------------------------------------------------------------------------


def test_pass_b_resolves_python_repo_local_import(tmp_path: Path) -> None:
    repo = tmp_path / "pyrepo"
    repo.mkdir()
    (repo / "main.py").write_text(
        "from helpers import util\nimport core\n", encoding="utf-8"
    )
    (repo / "helpers").mkdir()
    (repo / "helpers" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "helpers" / "util.py").write_text("def f(): pass\n", encoding="utf-8")
    (repo / "core.py").write_text("X = 1\n", encoding="utf-8")

    # Pass A forced via scope_glob to just main.py
    result = enumerate_files(repo, mode="raw", scope_glob="main.py", pass_b=True)
    pass_b_str = sorted(str(f) for f in result.pass_b_files)
    # 'helpers' resolves to helpers/__init__.py; 'core' to core.py.
    assert "core.py" in pass_b_str
    assert "helpers/__init__.py" in pass_b_str


def test_pass_b_drops_external_imports(tmp_path: Path) -> None:
    repo = tmp_path / "extrepo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "import requests\nimport os\nfrom typing import Any\n", encoding="utf-8"
    )
    result = enumerate_files(repo, mode="raw", scope_glob="app.py", pass_b=True)
    assert result.pass_b_files == []  # nothing resolves to a repo file


# ---------------------------------------------------------------------------
# Pass B — JS/TS imports
# ---------------------------------------------------------------------------


def test_pass_b_resolves_js_relative_import(tmp_path: Path) -> None:
    repo = tmp_path / "jsrepo"
    repo.mkdir()
    (repo / "app.js").write_text(
        "import x from './util';\nconst y = require('./other');\n",
        encoding="utf-8",
    )
    (repo / "util.js").write_text("export default 1;\n", encoding="utf-8")
    (repo / "other.js").write_text("module.exports = 2;\n", encoding="utf-8")

    result = enumerate_files(repo, mode="raw", scope_glob="app.js", pass_b=True)
    pass_b_str = sorted(str(f) for f in result.pass_b_files)
    assert "util.js" in pass_b_str
    assert "other.js" in pass_b_str


def test_pass_b_drops_bare_js_specifier(tmp_path: Path) -> None:
    repo = tmp_path / "barejs"
    repo.mkdir()
    (repo / "app.ts").write_text(
        "import _ from 'lodash';\n", encoding="utf-8"
    )
    result = enumerate_files(repo, mode="raw", scope_glob="app.ts", pass_b=True)
    assert result.pass_b_files == []


def test_pass_b_off_by_default(tmp_path: Path) -> None:
    repo = tmp_path / "off"
    repo.mkdir()
    (repo / "main.py").write_text("from helper import x\n", encoding="utf-8")
    (repo / "helper.py").write_text("x = 1\n", encoding="utf-8")
    result = enumerate_files(repo, mode="raw", scope_glob="main.py")
    assert result.pass_b_files == []


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def test_invalid_mode_raises(raw_repo: Path) -> None:
    with pytest.raises(ValueError):
        enumerate_files(raw_repo, mode="weird")  # type: ignore[arg-type]


def test_missing_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        enumerate_files(tmp_path / "does-not-exist")


def test_default_ignore_dirs_constant_exposed() -> None:
    assert ".git" in DEFAULT_IGNORE_DIRS
    assert "node_modules" in DEFAULT_IGNORE_DIRS


def test_batch_size_default_constant() -> None:
    assert BATCH_SIZE_DEFAULT == 200


def test_returns_dataclass_instance(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw")
    assert isinstance(result, EnumerateResult)


# ---------------------------------------------------------------------------
# Pass B regression — performance contract
# ---------------------------------------------------------------------------


def test_pass_b_skips_unscanned_languages_without_io(tmp_path: Path) -> None:
    """Files with non-Pass-B suffixes must not be opened, even if they exist.

    Regression for the IRIS USER timeout: reading 1226 .cls / .mac files
    just to discover none of them yield imports was the dominant cost.
    """
    repo = tmp_path / "iris_like"
    repo.mkdir()
    # Create 50 files of an unscanned language. The test is fast because we
    # stay under any cap; the assertion is that pass_b returns empty without
    # raising, and most importantly, the runtime does not balloon (we don't
    # measure it here, but skipping I/O is what makes it possible).
    for i in range(50):
        (repo / f"class_{i}.cls").write_text(
            "Class Foo Extends Bar { Property X; }\n", encoding="utf-8"
        )
    result = enumerate_files(repo, mode="raw", pass_b=True)
    assert result.pass_b_files == []
    # No Pass-B truncation warning either (no candidates to truncate).
    assert not any("Pass B truncated" in w for w in result.warnings)


def test_pass_b_truncates_above_cap(tmp_path: Path) -> None:
    """When more Pass B candidates exist than max_pass_b_files, warn + truncate."""
    repo = tmp_path / "many_py"
    repo.mkdir()
    for i in range(20):
        (repo / f"mod_{i}.py").write_text("import os\n", encoding="utf-8")
    result = enumerate_files(
        repo, mode="raw", pass_b=True, max_pass_b_files=5
    )
    assert any("Pass B truncated" in w for w in result.warnings)


def test_pass_b_max_files_zero_disables_cap(tmp_path: Path) -> None:
    repo = tmp_path / "uncapped"
    repo.mkdir()
    for i in range(10):
        (repo / f"x_{i}.py").write_text("import os\n", encoding="utf-8")
    result = enumerate_files(
        repo, mode="raw", pass_b=True, max_pass_b_files=0
    )
    assert not any("Pass B truncated" in w for w in result.warnings)


def test_pass_b_only_reads_head_of_files(tmp_path: Path) -> None:
    """Imports below the read-bytes cap must NOT be discovered.

    Use a payload of ``# pad\n`` * N to push the import past 16 KiB, then
    check it's invisible to Pass B.
    """
    repo = tmp_path / "deep"
    repo.mkdir()
    pad = ("# pad\n" * 4000)  # ~24 KiB of comments
    (repo / "main.py").write_text(
        pad + "from helpers import util\n", encoding="utf-8"
    )
    (repo / "helpers").mkdir()
    (repo / "helpers" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "helpers" / "util.py").write_text("x=1\n", encoding="utf-8")

    # Default 16 KiB head — import is past that, so resolved set is empty.
    result = enumerate_files(repo, mode="raw", scope_glob="main.py", pass_b=True)
    assert result.pass_b_files == []

    # With unlimited reads, the import is discovered.
    result_full = enumerate_files(
        repo, mode="raw", scope_glob="main.py", pass_b=True, pass_b_read_bytes=0
    )
    assert any("helpers" in str(f) for f in result_full.pass_b_files)


# ---------------------------------------------------------------------------
# Misnamed default branch — actionable error
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Trace — visible step-by-step rationale
# ---------------------------------------------------------------------------


def test_trace_populated_in_raw_mode(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw")
    trace_text = "\n".join(result.trace)
    assert "[start]" in trace_text
    assert "[mode] forced: raw" in trace_text
    assert "[raw] os.walk" in trace_text
    assert "[stats]" in trace_text
    assert "[caps]" in trace_text
    assert "[hash]" in trace_text
    assert "[batches]" in trace_text
    assert "[done]" in trace_text


def test_trace_records_pass_a_in_git_mode(git_repo: Path) -> None:
    result = enumerate_files(git_repo, mode="git", branch="feature/x")
    trace_text = "\n".join(result.trace)
    assert "[git] resolving base_ref" in trace_text
    assert "[git] merge-base" in trace_text or "first-parent" in trace_text
    assert "[git] Pass A" in trace_text
    # Pass A line must show diff/log/union counts.
    assert "diff=" in trace_text
    assert "log=" in trace_text
    assert "union=" in trace_text


def test_trace_records_overflow_state(raw_repo: Path) -> None:
    result = enumerate_files(raw_repo, mode="raw", max_files=1)
    trace_text = "\n".join(result.trace)
    assert "[caps] OVER soft cap" in trace_text


def test_trace_records_pass_b_skip_unscanned(tmp_path: Path) -> None:
    repo = tmp_path / "iris_like"
    repo.mkdir()
    for i in range(5):
        (repo / f"class_{i}.cls").write_text("Class X\n", encoding="utf-8")
    result = enumerate_files(repo, mode="raw", pass_b=True)
    trace_text = "\n".join(result.trace)
    assert "[pass-b]" in trace_text
    assert "skipped without I/O" in trace_text


def test_trace_constant_size(tmp_path: Path) -> None:
    """Trace size must not scale linearly with file count."""
    repo = tmp_path / "many_files"
    repo.mkdir()
    for i in range(300):
        (repo / f"f_{i:03d}.txt").write_text("x", encoding="utf-8")
    result = enumerate_files(repo, mode="raw")
    # Even with 300 files, trace stays well under 30 lines.
    assert len(result.trace) < 30


def test_merge_base_failure_lists_local_branches(git_repo: Path) -> None:
    """Mistyping ``fallback_base`` should yield an error that hints at the fix."""
    with pytest.raises(RuntimeError) as exc_info:
        enumerate_files(
            git_repo, mode="git", branch="feature/x", fallback_base="totally-not-a-branch"
        )
    msg = str(exc_info.value)
    assert "totally-not-a-branch" in msg
    # Either lists local branches or suggests master — both are improvements
    # over the bare git stderr the v1 path returned.
    assert "Hint" in msg or "main" in msg.lower()
