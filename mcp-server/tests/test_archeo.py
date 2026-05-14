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


# ---------- Branch-first cadrage gating (v0.10.x post-Gemini-drift) ----------


def _git_init_repo_with_branch(repo: Path, branch_name: str = "ecosav") -> None:
    """Init a repo with main + a feature branch carrying 2 commits."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "user@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "User"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "commit.gpgsign", "false"], check=True)
    (repo / "README.md").write_text("# init", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", branch_name], check=True, capture_output=True)
    (repo / "src" / "EcoSAV").mkdir(parents=True)
    (repo / "src" / "EcoSAV" / "x.cls").write_text("Class A {}", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "feat: add x"], check=True, capture_output=True)


async def test_orchestrator_branch_first_without_acknowledgment_returns_plan(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    """Branch-first invocation without acknowledged_via_plan → returns plan, no writes."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_repo_with_branch(repo, "ecosav")

    result = await client.call_tool(
        "mem_archeo",
        {
            "repo_path": str(repo),
            "branch_first": "ecosav",
            "branch_base": "main",
        },
    )
    data = result.structured_content

    assert data["needs_validation"] is True
    assert data["plan"] is not None
    assert data["plan"]["branch"]["name"] == "ecosav"
    assert data["stack"] is None
    assert data["git"] is None
    assert data["topology_outcome"] == "skipped"
    # No vault writes happened.
    proj_dir = vault_tmp / "10-episodes" / "projects" / "ecosav"
    assert not proj_dir.exists()


async def test_orchestrator_branch_first_with_acknowledgment_chains_through(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    """With acknowledged_via_plan=True, the chain runs through Phase 2 + 3 + topology + Phase 5."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_repo_with_branch(repo, "ecosav")

    result = await client.call_tool(
        "mem_archeo",
        {
            "repo_path": str(repo),
            "project": "ecosav",
            "branch_first": "ecosav",
            "branch_base": "main",
            "acknowledged_via_plan": True,
            "level": "commits",
            "window": "month",
        },
    )
    data = result.structured_content

    assert data["needs_validation"] is False
    assert data["plan"] is None
    assert data["stack"] is not None
    assert data["git"] is not None
    # Phase 5 enforcement: project skeleton created
    proj_dir = vault_tmp / "10-episodes" / "projects" / "ecosav"
    assert (proj_dir / "context.md").is_file()
    assert (proj_dir / "history.md").is_file()
    # Topology persisted in branch-specific location
    topo = (
        vault_tmp
        / "99-meta"
        / "repo-topology"
        / "ecosav-branches"
        / "ecosav.md"
    )
    assert topo.is_file()
    # Branch frontmatter populated on archives
    archives = list((proj_dir / "archives").glob("*.md"))
    assert archives, "expected at least one archive"
    fm, _ = frontmatter.read(archives[0])
    assert fm["branch"] == "ecosav"
    assert fm["branch_base"] == "main"


async def test_orchestrator_standard_mode_skips_gating(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    """Standard mode (no branch_first) bypasses the cadrage gating entirely."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_repo_with_tags(repo)

    result = await client.call_tool(
        "mem_archeo",
        {"repo_path": str(repo), "project": "alpha"},
    )
    # No needs_validation surface in standard mode.
    assert result.structured_content["needs_validation"] is False
    assert result.structured_content["git"] is not None


async def test_orchestrator_creates_branch_topology_file(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    """In branch-first mode, topology is persisted under .../slug-branches/branch.md."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init_repo_with_branch(repo, "feat/new-thing")

    topology_file = (
        vault_tmp
        / "99-meta"
        / "repo-topology"
        / "ecosav-branches"
        / "feat-new-thing.md"
    )
    assert not topology_file.exists()

    result = await client.call_tool(
        "mem_archeo",
        {
            "repo_path": str(repo),
            "project": "ecosav",
            "branch_first": "feat/new-thing",
            "branch_base": "main",
            "acknowledged_via_plan": True,
        },
    )
    data = result.structured_content

    assert data["topology_outcome"] == "created"
    assert topology_file.is_file()

    fm, body = frontmatter.read(topology_file)
    assert fm["type"] == "repo-topology"
    assert fm["project"] == "ecosav"
    assert fm["branch"] == "feat/new-thing"
    assert "branch/feat/new-thing" in fm["tags"]
    assert "Topology — ecosav (branch: feat/new-thing)" in body
    assert "- **Branch** : `feat/new-thing`" in body
