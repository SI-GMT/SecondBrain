"""Tests for mem_archeo_stack — Phase 2 of the triphasic archeo.

Spec: core/procedures/mem-archeo-stack.md.

The vault-skeleton fixture provides projects 'alpha' and 'beta'. Each test
spins up a tiny git repo on disk under tmp_path/repo and calls mem_archeo_stack
with project='alpha' so the slug resolves cleanly.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastmcp import Client

from memory_kit_mcp.vault import frontmatter


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@e.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "T"], check=True)
    (path / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo_dir(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    return repo


# ---------- Validation ----------


async def test_raises_on_non_git_dir(client: Client, tmp_path: Path) -> None:
    not_a_repo = tmp_path / "noop"
    not_a_repo.mkdir()
    with pytest.raises(Exception) as exc_info:
        await client.call_tool(
            "mem_archeo_stack",
            {"repo_path": str(not_a_repo), "project": "alpha"},
        )
    assert "not a Git repository" in str(exc_info.value)


async def test_raises_when_no_matching_project(
    client: Client, repo_dir: Path
) -> None:
    # repo basename != alpha or beta → must raise ValueError
    with pytest.raises(Exception) as exc_info:
        await client.call_tool("mem_archeo_stack", {"repo_path": str(repo_dir)})
    assert "auto-resolve" in str(exc_info.value).lower() or "project" in str(exc_info.value).lower()


# ---------- Frontend ----------


async def test_detects_nextjs_frontend(
    client: Client, vault_tmp: Path, repo_dir: Path
) -> None:
    (repo_dir / "package.json").write_text(
        json.dumps({
            "name": "demo",
            "dependencies": {"next": "14", "react": "18", "tailwindcss": "3"},
            "devDependencies": {"vitest": "1", "typescript": "5"},
        }),
        encoding="utf-8",
    )

    result = await client.call_tool(
        "mem_archeo_stack",
        {"repo_path": str(repo_dir), "project": "alpha"},
    )
    data = result.structured_content
    assert data["project"] == "alpha"
    assert data["atoms_created"] >= 1
    layers = {layer["layer"] for layer in data["layers"]}
    assert "frontend" in layers

    # Atom file landed in the right place
    atom = vault_tmp / "20-knowledge" / "architecture" / "alpha-stack-frontend.md"
    assert atom.is_file()
    fm, body = frontmatter.read(atom)
    assert fm["source"] == "archeo-stack"
    assert fm["detected_layer"] == "frontend"
    assert "Next.js" in fm["detected_techno"]
    assert "React" in fm["detected_techno"]
    assert fm["project"] == "alpha"
    assert fm["content_hash"]  # non-empty SHA-256
    assert fm["previous_atom"] == ""
    assert fm["context_origin"] == "[[99-meta/repo-topology/alpha]]"
    assert "Frontend" in body


# ---------- Backend ----------


async def test_detects_python_fastapi_backend(
    client: Client, vault_tmp: Path, repo_dir: Path
) -> None:
    (repo_dir / "pyproject.toml").write_text(
        '[project]\nname = "api"\nversion = "0.1"\n'
        'dependencies = ["fastapi>=0.100", "sqlalchemy", "pydantic>=2"]\n',
        encoding="utf-8",
    )

    result = await client.call_tool(
        "mem_archeo_stack",
        {"repo_path": str(repo_dir), "project": "alpha"},
    )
    data = result.structured_content
    layers = {layer["layer"] for layer in data["layers"]}
    assert "backend" in layers
    assert "db" in layers  # sqlalchemy hits

    atom = vault_tmp / "20-knowledge" / "architecture" / "alpha-stack-backend.md"
    fm, _ = frontmatter.read(atom)
    assert "FastAPI" in fm["detected_techno"]
    assert fm["source_manifest"] == "pyproject.toml"


# ---------- DB via docker-compose ----------


async def test_detects_postgres_via_docker_compose(
    client: Client, vault_tmp: Path, repo_dir: Path
) -> None:
    (repo_dir / "docker-compose.yml").write_text(
        "services:\n"
        "  db:\n"
        "    image: postgres:16\n"
        "    ports:\n"
        '      - "5432:5432"\n',
        encoding="utf-8",
    )

    result = await client.call_tool(
        "mem_archeo_stack",
        {"repo_path": str(repo_dir), "project": "alpha"},
    )
    data = result.structured_content
    layers = {layer["layer"] for layer in data["layers"]}
    assert "db" in layers
    assert "infra" in layers

    db_atom = vault_tmp / "20-knowledge" / "architecture" / "alpha-stack-db.md"
    fm_db, _ = frontmatter.read(db_atom)
    assert any("Postgres" in t for t in fm_db["detected_techno"])


# ---------- Tooling ----------


async def test_detects_python_tooling_via_pyproject_tool_sections(
    client: Client, vault_tmp: Path, repo_dir: Path
) -> None:
    (repo_dir / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1"\ndependencies = []\n\n'
        '[tool.ruff]\nline-length = 100\n\n'
        '[tool.mypy]\nstrict = true\n',
        encoding="utf-8",
    )
    (repo_dir / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")

    result = await client.call_tool(
        "mem_archeo_stack",
        {"repo_path": str(repo_dir), "project": "alpha"},
    )
    layers = {layer["layer"] for layer in result.structured_content["layers"]}
    assert "tooling" in layers

    atom = vault_tmp / "20-knowledge" / "architecture" / "alpha-stack-tooling.md"
    fm, body = frontmatter.read(atom)
    assert "ruff" in fm["detected_techno"]
    assert "mypy" in fm["detected_techno"]
    assert "pre-commit" in fm["detected_techno"]


# ---------- Idempotence ----------


async def test_idempotent_second_call_skips(
    client: Client, vault_tmp: Path, repo_dir: Path
) -> None:
    (repo_dir / "package.json").write_text(
        json.dumps({"dependencies": {"next": "14", "react": "18"}}),
        encoding="utf-8",
    )
    first = await client.call_tool(
        "mem_archeo_stack",
        {"repo_path": str(repo_dir), "project": "alpha"},
    )
    second = await client.call_tool(
        "mem_archeo_stack",
        {"repo_path": str(repo_dir), "project": "alpha"},
    )
    assert first.structured_content["atoms_created"] >= 1
    assert second.structured_content["atoms_created"] == 0
    assert second.structured_content["atoms_skipped"] == first.structured_content["atoms_created"]


# ---------- Auto-resolve slug ----------


async def test_auto_resolves_slug_from_basename(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    # Repo named exactly 'alpha' so slug resolution succeeds without explicit project
    repo = tmp_path / "alpha"
    repo.mkdir()
    _git_init(repo)
    (repo / "package.json").write_text(
        json.dumps({"dependencies": {"react": "18"}}),
        encoding="utf-8",
    )

    result = await client.call_tool(
        "mem_archeo_stack",
        {"repo_path": str(repo)},
    )
    assert result.structured_content["project"] == "alpha"


# ---------- CI ----------


async def test_detects_github_actions_ci(
    client: Client, vault_tmp: Path, repo_dir: Path
) -> None:
    workflows = repo_dir / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\non: [push]\njobs: {}\n", encoding="utf-8")

    result = await client.call_tool(
        "mem_archeo_stack",
        {"repo_path": str(repo_dir), "project": "alpha"},
    )
    layers = {layer["layer"] for layer in result.structured_content["layers"]}
    assert "ci" in layers
    atom = vault_tmp / "20-knowledge" / "architecture" / "alpha-stack-ci.md"
    fm, _ = frontmatter.read(atom)
    assert "GitHub Actions" in fm["detected_techno"]


# ---------- Empty repo ----------


async def test_empty_repo_returns_zero_layers(
    client: Client, vault_tmp: Path, repo_dir: Path
) -> None:
    # repo_dir has only .gitkeep — no manifests
    result = await client.call_tool(
        "mem_archeo_stack",
        {"repo_path": str(repo_dir), "project": "alpha"},
    )
    data = result.structured_content
    assert data["layers_resolved"] == 0
    assert data["atoms_created"] == 0
