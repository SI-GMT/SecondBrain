"""Tests for mem_archeo orchestrator.

Spec: core/procedures/mem-archeo.md.

Verifies that Phase 2 (stack) and Phase 3 (git) are chained correctly
sharing a single Phase 0 topology scan, that Phase 1 is skipped with the
expected warning, and that the topology file is created when absent.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastmcp import Client

from memory_kit_mcp.vault import frontmatter


def _git_init_repo_with_tags(repo: Path) -> None:
    """Init a repo with package.json + 2 semver tags."""
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "commit.gpgsign", "false"], check=True)

    (repo / "package.json").write_text(
        json.dumps({"dependencies": {"next": "14", "react": "18"}}),
        encoding="utf-8",
    )
    (repo / "README.md").write_text("# v0.1.0\nfirst", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "init"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "tag", "-a", "v0.1.0", "-m", "release"],
        check=True, capture_output=True,
    )

    (repo / "README.md").write_text("# v0.2.0\nsecond", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "second"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "tag", "-a", "v0.2.0", "-m", "release"],
        check=True, capture_output=True,
    )


# ---------- Validation ----------


async def test_orchestrator_raises_on_non_git(client: Client, tmp_path: Path) -> None:
    not_a_repo = tmp_path / "noop"
    not_a_repo.mkdir()
    with pytest.raises(Exception) as exc_info:
        await client.call_tool(
            "mem_archeo",
            {"repo_path": str(not_a_repo), "project": "alpha"},
        )
    assert "not a Git repository" in str(exc_info.value)


# ---------- Full chain ----------


async def test_orchestrator_runs_phase_2_and_3(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_repo_with_tags(repo)

    result = await client.call_tool(
        "mem_archeo",
        {"repo_path": str(repo), "project": "alpha"},
    )
    data = result.structured_content

    # Phase 1 explicitly skipped
    assert data["phase_1_skipped"] is True
    assert "Phase 1" in data["phase_1_message"]

    # Phase 2 ran and detected frontend
    stack_layers = {layer["layer"] for layer in data["stack"]["layers"]}
    assert "frontend" in stack_layers

    # Phase 3 ran and produced 2 archives (one per tag)
    assert data["git"]["milestones_processed"] == 2
    assert data["git"]["archives_created"] == 2

    # Vault contents
    assert (vault_tmp / "20-knowledge" / "architecture" / "alpha-stack-frontend.md").is_file()
    archives = list((vault_tmp / "10-episodes" / "projects" / "alpha" / "archives").iterdir())
    archeo_git_files = [a for a in archives if "archeo-git" in a.name]
    assert len(archeo_git_files) == 2


# ---------- Topology file creation ----------


async def test_orchestrator_creates_topology_file_when_absent(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    # Use 'beta' which has no pre-existing topology in the fixture vault.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_repo_with_tags(repo)

    topology_file = vault_tmp / "99-meta" / "repo-topology" / "beta.md"
    assert not topology_file.exists()

    result = await client.call_tool(
        "mem_archeo",
        {"repo_path": str(repo), "project": "beta"},
    )
    data = result.structured_content

    assert data["topology_outcome"] == "created"
    assert topology_file.is_file()

    fm, body = frontmatter.read(topology_file)
    assert fm["zone"] == "meta"
    assert fm["type"] == "repo-topology"
    assert fm["project"] == "beta"
    assert fm["content_hash"]
    assert fm["previous_topology_hash"] == ""
    assert "## Categories" in body
    assert "## Stack hints" in body
    assert "## Phases archeo couvertes" in body
    assert "Phase 0" in body
    assert "Phase 2" in body
    assert "Phase 3" in body


async def test_orchestrator_topology_skipped_when_exists(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    # 'alpha' already has a pre-existing topology in the fixture — exactly
    # the scenario this test exercises (don't overwrite existing topology).
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_repo_with_tags(repo)

    pre_existing = vault_tmp / "99-meta" / "repo-topology" / "alpha.md"
    assert pre_existing.is_file()  # fixture invariant
    pre_content = pre_existing.read_text(encoding="utf-8")

    result = await client.call_tool(
        "mem_archeo",
        {"repo_path": str(repo), "project": "alpha"},
    )

    assert result.structured_content["topology_outcome"] == "skipped"
    # Pre-existing content preserved byte-for-byte
    assert pre_existing.read_text(encoding="utf-8") == pre_content


# ---------- Idempotence on second call ----------


async def test_orchestrator_idempotent_on_second_call(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_repo_with_tags(repo)

    first = await client.call_tool(
        "mem_archeo",
        {"repo_path": str(repo), "project": "alpha"},
    )
    second = await client.call_tool(
        "mem_archeo",
        {"repo_path": str(repo), "project": "alpha"},
    )

    # Phase 2: re-resolve same layers, all skipped
    assert first.structured_content["stack"]["atoms_created"] >= 1
    assert second.structured_content["stack"]["atoms_created"] == 0
    # Phase 3: same tags, all skipped
    assert second.structured_content["git"]["archives_created"] == 0
    assert second.structured_content["git"]["archives_skipped"] == 2
    # Topology already exists from first run
    assert second.structured_content["topology_outcome"] == "skipped"
