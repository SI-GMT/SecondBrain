"""Tests for mem_get_topology — read persisted topology snapshots."""

from __future__ import annotations

from pathlib import Path

from fastmcp import Client

from memory_kit_mcp.vault import frontmatter


async def test_returns_exists_false_when_no_topology(
    client: Client, vault_tmp: Path
) -> None:
    # Use a slug we know has no topology snapshot in the fixture vault.
    res = await client.call_tool("mem_get_topology", {"project": "never-archeod"})
    d = res.data
    assert d.exists is False
    assert d.project == "never-archeod"
    assert "no topology persisted" in d.summary_md.lower()


async def test_reads_existing_topology(client: Client, vault_tmp: Path) -> None:
    target = vault_tmp / "99-meta" / "repo-topology" / "betaproj.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "date": "2026-05-04",
        "zone": "meta",
        "type": "repo-topology",
        "project": "betaproj",
        "repo_path": "/path/to/betaproj",
        "repo_remote": "git@github.com:org/betaproj.git",
        "content_hash": "deadbeefcafe",
        "previous_topology_hash": "",
        "last_archive": "2026-05-04-12h00-betaproj-something.md",
        "tags": ["zone/meta", "type/repo-topology", "project/betaproj"],
        "display": "betaproj — repo topology",
    }
    body = "# Topology — betaproj\n\nContent body...\n"
    frontmatter.write(target, fm, body)

    res = await client.call_tool("mem_get_topology", {"project": "betaproj"})
    d = res.data
    assert d.exists is True
    assert d.project == "betaproj"
    assert d.repo_path == "/path/to/betaproj"
    assert d.repo_remote.startswith("git@github.com")
    assert d.content_hash == "deadbeefcafe"
    assert d.last_archive.endswith(".md")
    assert "betaproj" in d.body


async def test_reads_branch_topology(client: Client, vault_tmp: Path) -> None:
    target = (
        vault_tmp
        / "99-meta"
        / "repo-topology"
        / "betaproj-branches"
        / "feat-x.md"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "date": "2026-05-04",
        "zone": "meta",
        "type": "repo-topology",
        "project": "betaproj",
        "branch": "feat/x",
        "repo_path": "/path/to/betaproj",
        "content_hash": "abc",
        "tags": ["zone/meta", "type/repo-topology", "project/betaproj", "branch/feat/x"],
        "display": "betaproj — repo topology (feat/x)",
    }
    body = "# Topology — betaproj (branch: feat/x)\n"
    frontmatter.write(target, fm, body)

    res = await client.call_tool(
        "mem_get_topology", {"project": "betaproj", "branch": "feat/x"}
    )
    d = res.data
    assert d.exists is True
    assert d.project == "betaproj"
    assert d.frontmatter["branch"] == "feat/x"
    assert "feat/x" in d.body
