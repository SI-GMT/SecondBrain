"""Tests for vault.topology_scanner — Phase 0 shared primitive.

Spec: core/procedures/_repo-topology.md (T1-T8).

Each test builds a tiny disposable git repo on disk and asserts on the
classification, stack hints, or workspace detection. No network, no vault
required.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from memory_kit_mcp.vault import topology_scanner as ts


def _git_init(path: Path) -> None:
    """Init a minimal git repo with one commit so rev-list succeeds."""
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        check=True,
    )
    # at least one file so the commit is non-empty
    (path / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"],
        check=True,
        capture_output=True,
    )


# ---------- T7: not a git repo ----------


def test_scan_raises_on_non_git_dir(tmp_path: Path) -> None:
    with pytest.raises(ts.NotAGitRepoError):
        ts.scan(tmp_path)


# ---------- T2: categories ----------


def test_scan_classifies_root_files(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("# foo", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("ai", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# log", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("node_modules", encoding="utf-8")
    (tmp_path / ".editorconfig").write_text("", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM scratch", encoding="utf-8")

    topo = ts.scan(tmp_path)

    assert "README.md" in topo.categories["readme"]
    assert "CLAUDE.md" in topo.categories["ai_files"]
    assert "CHANGELOG.md" in topo.categories["changelog"]
    assert any(name.startswith("LICENSE") for name in topo.categories["license"])
    assert "package.json" in topo.categories["manifests"]
    assert "uv.lock" in topo.categories["lockfiles"]
    assert ".gitignore" in topo.categories["git_meta"]
    assert ".editorconfig" in topo.categories["editor"]
    assert "Dockerfile" in topo.categories["infra"]


def test_scan_classifies_directories(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "config").mkdir()

    topo = ts.scan(tmp_path)

    assert "src/" in topo.categories["sources"]
    assert "docs/" in topo.categories["docs"]
    assert "tests/" in topo.categories["tests"]
    assert ".github/workflows/" in topo.categories["ci"]
    assert "config/" in topo.categories["config"]


def test_scan_excludes_standard_dirs(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "node_modules" / "foo").mkdir(parents=True)
    (tmp_path / ".venv").mkdir()
    (tmp_path / "dist").mkdir()

    topo = ts.scan(tmp_path)

    assert all("node_modules" not in v for cat in topo.categories.values() for v in cat)
    assert all(".venv" not in v for cat in topo.categories.values() for v in cat)
    assert all("dist" not in v for cat in topo.categories.values() for v in cat)


# ---------- T4: stack hints ----------


def test_stack_hints_detect_nextjs_typescript(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "package.json").write_text(
        json.dumps({
            "dependencies": {"next": "14", "react": "18"},
            "devDependencies": {"typescript": "5"},
        }),
        encoding="utf-8",
    )

    topo = ts.scan(tmp_path)

    assert "Next.js" in topo.stack_hints["frontend"]
    assert "React" in topo.stack_hints["frontend"]
    assert "typescript" in topo.stack_hints["lang"]


def test_stack_hints_detect_python_fastapi(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "app"\nversion = "0.1"\n'
        'dependencies = ["fastapi>=0.100", "psycopg2-binary"]\n',
        encoding="utf-8",
    )

    topo = ts.scan(tmp_path)

    assert "FastAPI" in topo.stack_hints["backend"]
    assert "PostgreSQL" in topo.stack_hints["db"]
    assert "python" in topo.stack_hints["lang"]


def test_stack_hints_detect_rust_axum(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "app"\nversion = "0.1.0"\n\n'
        '[dependencies]\naxum = "0.7"\n',
        encoding="utf-8",
    )

    topo = ts.scan(tmp_path)

    assert "rust" in topo.stack_hints["lang"]
    assert "Axum" in topo.stack_hints["backend"]


def test_stack_hints_detect_go(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n", encoding="utf-8")

    topo = ts.scan(tmp_path)

    assert "go" in topo.stack_hints["lang"]


# ---------- T3.1: workspaces ----------


def test_workspaces_npm_array(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": ["packages/*"]}),
        encoding="utf-8",
    )
    (tmp_path / "packages" / "web").mkdir(parents=True)
    (tmp_path / "packages" / "web" / "package.json").write_text(
        json.dumps({"name": "@acme/web"}),
        encoding="utf-8",
    )
    (tmp_path / "packages" / "api").mkdir(parents=True)
    (tmp_path / "packages" / "api" / "package.json").write_text(
        json.dumps({"name": "@acme/api"}),
        encoding="utf-8",
    )

    topo = ts.scan(tmp_path)

    names = {w.name for w in topo.workspaces}
    assert names == {"@acme/web", "@acme/api"}
    paths_set = {w.path for w in topo.workspaces}
    assert paths_set == {"packages/web", "packages/api"}


def test_workspaces_cargo(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["crates/*"]\n',
        encoding="utf-8",
    )
    (tmp_path / "crates" / "core").mkdir(parents=True)
    (tmp_path / "crates" / "core" / "Cargo.toml").write_text(
        '[package]\nname = "core"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    topo = ts.scan(tmp_path)

    assert any(w.name == "core" for w in topo.workspaces)


def test_workspaces_implicit_fallback(tmp_path: Path) -> None:
    _git_init(tmp_path)
    # Pas de root manifest avec workspaces — fallback implicite
    (tmp_path / "apps" / "frontend").mkdir(parents=True)
    (tmp_path / "apps" / "frontend" / "package.json").write_text(
        json.dumps({"name": "frontend"}), encoding="utf-8",
    )
    (tmp_path / "packages" / "ui").mkdir(parents=True)
    (tmp_path / "packages" / "ui" / "package.json").write_text(
        json.dumps({"name": "@org/ui"}), encoding="utf-8",
    )

    topo = ts.scan(tmp_path)

    names = {w.name for w in topo.workspaces}
    assert names == {"frontend", "@org/ui"}
    assert all(w.workspace_implicit for w in topo.workspaces)


def test_workspaces_resolve_vault_project(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / "package.json").write_text(
        json.dumps({"workspaces": ["packages/*"]}),
        encoding="utf-8",
    )
    (repo / "packages" / "web").mkdir(parents=True)
    (repo / "packages" / "web" / "package.json").write_text(
        json.dumps({"name": "@acme/web"}),
        encoding="utf-8",
    )

    vault = tmp_path / "vault"
    (vault / "10-episodes" / "projects" / "acme-web").mkdir(parents=True)

    topo = ts.scan(repo, vault=vault)

    web = next(w for w in topo.workspaces if w.name == "@acme/web")
    assert web.vault_project == "acme-web"


# ---------- T3: metadata ----------


def test_topology_carries_metadata(tmp_path: Path) -> None:
    _git_init(tmp_path)

    topo = ts.scan(tmp_path, depth=3)

    assert topo.repo_path == str(tmp_path.resolve())
    assert topo.depth_limit == 3
    assert topo.scanned_at  # ISO string non-empty
    # No remote configured
    assert topo.repo_remote == ""
