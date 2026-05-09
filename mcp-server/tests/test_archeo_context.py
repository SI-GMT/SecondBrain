"""Tests for mem_archeo_context — Phase 1 LLM round-trip.

Spec: core/procedures/mem-archeo-context.md.

Verifies brief returns paginated files_to_read + schema, finalize without
token raises, finalize with valid synthesis writes topology atom + patches
context.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client

from memory_kit_mcp.vault import frontmatter


def _seed_archive(
    archives_dir: Path, *, name: str, sha: str, files: list[str],
) -> None:
    """Write a synthetic merge-mode archive with perimeter file bullets."""
    archives_dir.mkdir(parents=True, exist_ok=True)
    body_lines = [
        "# Merge archive",
        "",
        "**Date** : 2026-03-17 16:29",
        "",
        "## Analyse technique",
        "",
        "### cls (placeholder)",
        "",
    ]
    for f in files:
        body_lines.append(f"- **`{f}`**")
        body_lines.append("  - _classes_ : `Foo`")
    body = "\n".join(body_lines)
    fm = {
        "date": "2026-03-17",
        "time": "16:29",
        "zone": "episodes",
        "kind": "project",
        "scope": "work",
        "type": "archive",
        "project": "ecosav",
        "source": "archeo-git",
        "milestone_kind": "merge",
        "commit_sha": sha,
        "display": f"ecosav — {name}",
        "tags": ["project/ecosav", "source/archeo-git"],
    }
    frontmatter.write(archives_dir / f"{name}.md", fm, body)


def _seed_project_skeleton(vault: Path, slug: str = "ecosav") -> Path:
    proj = vault / "10-episodes" / "projects" / slug
    proj.mkdir(parents=True, exist_ok=True)
    fm = {
        "project": slug,
        "zone": "episodes",
        "kind": "project",
        "slug": slug,
        "display": f"{slug} — context",
        "tags": [f"project/{slug}", "zone/episodes"],
    }
    body = (
        "> Snapshot mutable\n\n"
        f"# {slug.capitalize()} — Active context\n\n"
        "## Current state\n- Phase : initial\n\n"
        "## Cumulative decisions\n_(none yet)_\n"
    )
    frontmatter.write(proj / "context.md", fm, body)
    return proj


# ---------------------------------------------------------------------------
# Brief phase
# ---------------------------------------------------------------------------


async def test_brief_returns_files_from_archive_perimeter(
    client: Client, vault_tmp: Path
) -> None:
    proj = _seed_project_skeleton(vault_tmp, "ecosav")
    _seed_archive(
        proj / "archives", name="cycle-1", sha="abc123",
        files=["src/EcoSAV/Statut.cls", "src/EcoSAV/Detail.cls"],
    )
    _seed_archive(
        proj / "archives", name="cycle-2", sha="def456",
        files=["src/EcoSAV/Materiel.cls"],
    )

    res = await client.call_tool(
        "mem_archeo_context",
        {"project": "ecosav"},
    )
    data = res.data
    assert data.needs_llm_read is True
    assert data.batch == 1
    assert data.total_batches == 1
    assert len(data.files_to_read) == 3
    assert "src/EcoSAV/Statut.cls" in data.files_to_read
    assert len(data.cycles) == 2
    assert "components" in data.synthesis_schema
    # Next call points at finalize tool
    assert data.next_call["tool"] == "mem_archeo_project_topology"


async def test_brief_paginates_when_files_exceed_cap(
    client: Client, vault_tmp: Path
) -> None:
    proj = _seed_project_skeleton(vault_tmp, "bigproj")
    files = [f"src/comp{i}.py" for i in range(45)]
    _seed_archive(
        proj / "archives", name="bigcycle", sha="aaa", files=files,
    )

    res1 = await client.call_tool(
        "mem_archeo_context",
        {"project": "bigproj", "batch": 1},
    )
    assert res1.data.total_batches == 2
    assert len(res1.data.files_to_read) == 30
    assert res1.data.next_call["tool"] == "mem_archeo_context"
    assert res1.data.next_call["args"]["batch"] == 2

    res2 = await client.call_tool(
        "mem_archeo_context",
        {"project": "bigproj", "batch": 2},
    )
    assert len(res2.data.files_to_read) == 15
    assert res2.data.next_call["tool"] == "mem_archeo_project_topology"


async def test_brief_empty_project_no_archives(
    client: Client, vault_tmp: Path
) -> None:
    """No archives → brief returns empty files_to_read but does not crash."""
    _seed_project_skeleton(vault_tmp, "empty")
    res = await client.call_tool(
        "mem_archeo_context",
        {"project": "empty"},
    )
    assert res.data.files_to_read == []
    assert res.data.cycles == []


# ---------------------------------------------------------------------------
# Finalize phase (mem_archeo_project_topology)
# ---------------------------------------------------------------------------


async def test_finalize_without_token_refuses(
    client: Client, vault_tmp: Path
) -> None:
    _seed_project_skeleton(vault_tmp, "ecosav")
    with pytest.raises(Exception) as exc_info:
        await client.call_tool(
            "mem_archeo_project_topology",
            {
                "project": "ecosav",
                "synthesis": {"components": {}},
            },
        )
    assert "acknowledged_via_read" in str(exc_info.value).lower()


async def test_finalize_rejects_component_without_files(
    client: Client, vault_tmp: Path
) -> None:
    """Strict schema : component with role-but-no-files is REJECTED.

    Mitigates the 2026-05-09 IRIS USER drift class where Gemini returned
    role-only top-level dirs ('### "src/Global/Components/EcoSAV"' with
    no file-level mapping). The whole point of Phase 1 is the file-level
    structure, not a directory listing the user can see with `ls`.
    """
    _seed_project_skeleton(vault_tmp, "ecosav")
    with pytest.raises(Exception) as exc_info:
        await client.call_tool(
            "mem_archeo_project_topology",
            {
                "project": "ecosav",
                "synthesis": {
                    "components": {
                        "src/EcoSAV": {
                            "role": "EcoSAV core domain",
                            # files MISSING entirely
                        }
                    },
                },
                "acknowledged_via_read": True,
            },
        )
    msg = str(exc_info.value).lower()
    assert "files" in msg and ("empty" in msg or "non-empty" in msg)


async def test_finalize_rejects_file_without_path(
    client: Client, vault_tmp: Path
) -> None:
    _seed_project_skeleton(vault_tmp, "ecosav")
    with pytest.raises(Exception) as exc_info:
        await client.call_tool(
            "mem_archeo_project_topology",
            {
                "project": "ecosav",
                "synthesis": {
                    "components": {
                        "src/EcoSAV": {
                            "role": "EcoSAV core domain",
                            "files": [
                                {"role": "missing path", "key_methods": []}
                            ],
                        }
                    },
                },
                "acknowledged_via_read": True,
            },
        )
    msg = str(exc_info.value).lower()
    assert "path" in msg and "empty" in msg


async def test_finalize_rejects_component_without_role(
    client: Client, vault_tmp: Path
) -> None:
    _seed_project_skeleton(vault_tmp, "ecosav")
    with pytest.raises(Exception) as exc_info:
        await client.call_tool(
            "mem_archeo_project_topology",
            {
                "project": "ecosav",
                "synthesis": {
                    "components": {
                        "src/EcoSAV": {
                            # role MISSING
                            "files": [
                                {"path": "x.py", "role": "x", "key_methods": []}
                            ],
                        }
                    },
                },
                "acknowledged_via_read": True,
            },
        )
    assert "role" in str(exc_info.value).lower()


async def test_finalize_strips_quoted_keys_from_components(
    client: Client, vault_tmp: Path
) -> None:
    """Component keys with parasitic quote chars are normalized."""
    proj = _seed_project_skeleton(vault_tmp, "ecosav")
    _seed_archive(
        proj / "archives", name="cycle-1", sha="abc",
        files=["src/EcoSAV/X.cls"],
    )
    res = await client.call_tool(
        "mem_archeo_project_topology",
        {
            "project": "ecosav",
            "synthesis": {
                "components": {
                    '"src/EcoSAV"': {  # extra quotes embedded in key
                        "role": "EcoSAV core",
                        "files": [
                            {
                                "path": '"src/EcoSAV/X.cls"',
                                "role": "X file",
                                "key_methods": ["Foo"],
                            }
                        ],
                    }
                },
            },
            "acknowledged_via_read": True,
        },
    )
    assert res.data.success is True
    topo = vault_tmp / "20-knowledge" / "architecture" / "ecosav-project-topology.md"
    body = topo.read_text(encoding="utf-8")
    # Clean keys rendered without parasitic quotes.
    assert '`src/EcoSAV`' in body
    assert '`src/EcoSAV/X.cls`' in body
    assert '`"src/EcoSAV"`' not in body  # parasitic quotes stripped


async def test_finalize_patches_zone_index(
    client: Client, vault_tmp: Path
) -> None:
    """Zone index 20-knowledge/index.md gets the project-topology link."""
    # Seed zone index with proper header structure
    zone = vault_tmp / "20-knowledge"
    zone.mkdir(parents=True, exist_ok=True)
    (zone / "index.md").write_text(
        "---\nzone: meta\ntype: zone-index\ndisplay: 20-knowledge — index\n---\n\n"
        "# 20-knowledge — Index\n\n"
        "## Knowledge by project\n\n"
        "### other-project\n\n- [foo](20-knowledge/architecture/foo.md)\n",
        encoding="utf-8", newline="\n",
    )
    proj = _seed_project_skeleton(vault_tmp, "ecosav")
    _seed_archive(
        proj / "archives", name="cycle-1", sha="abc",
        files=["src/EcoSAV/X.cls"],
    )
    await client.call_tool(
        "mem_archeo_project_topology",
        {
            "project": "ecosav",
            "synthesis": {
                "components": {
                    "src/EcoSAV": {
                        "role": "EcoSAV core",
                        "files": [{"path": "src/EcoSAV/X.cls", "role": "x", "key_methods": []}],
                    }
                },
            },
            "acknowledged_via_read": True,
        },
    )
    body = (zone / "index.md").read_text(encoding="utf-8")
    assert "### ecosav" in body
    assert "ecosav-project-topology" in body


async def test_finalize_with_synthesis_writes_topology_atom_and_patches_context(
    client: Client, vault_tmp: Path
) -> None:
    proj = _seed_project_skeleton(vault_tmp, "ecosav")
    _seed_archive(
        proj / "archives", name="cycle-1", sha="abc",
        files=["src/EcoSAV/Statut.cls"],
    )
    synthesis = {
        "components": {
            "src/EcoSAV": {
                "role": "EcoSAV core domain",
                "files": [
                    {
                        "path": "src/EcoSAV/Statut.cls",
                        "role": "Statut tracking for donation files",
                        "key_methods": ["ValidateDossier"],
                    }
                ],
            }
        },
        "domain_concepts": [
            "DOSSIERDON = donation file flag",
            "savRegion = SAV region reference",
        ],
        "patterns": ["3-layer split (Components/Models/Interface)"],
        "decisions": ["Default DOSSIERDON to 0 at creation"],
        "risks_or_friction": ["No validation on DOSSIERDON setter"],
    }
    res = await client.call_tool(
        "mem_archeo_project_topology",
        {
            "project": "ecosav",
            "synthesis": synthesis,
            "acknowledged_via_read": True,
        },
    )
    data = res.data
    assert data.success is True

    # Topology atom written
    topo = vault_tmp / "20-knowledge" / "architecture" / "ecosav-project-topology.md"
    assert topo.is_file()
    fm, body = frontmatter.read(topo)
    assert fm["project"] == "ecosav"
    assert fm["type"] == "project-topology"
    assert "src/EcoSAV" in body
    assert "Statut tracking" in body
    assert "DOSSIERDON" in body
    assert "3-layer split" in body

    # Context.md patched
    ctx_fm, ctx_body = frontmatter.read(proj / "context.md")
    assert "archeo-context synthesized" in ctx_fm["phase"]
    assert "DOSSIERDON" in ctx_body
    assert "3-layer split" in ctx_body
    assert "Statut" in ctx_body or "Components mapped" in ctx_body


async def test_finalize_minimal_synthesis_still_works(
    client: Client, vault_tmp: Path
) -> None:
    """Empty components accepted — topology atom still written, skeleton patched.

    Empty `components` is OK (LLM had nothing to surface). What's REJECTED
    is half-filled components (role-but-no-files).
    """
    proj = _seed_project_skeleton(vault_tmp, "ecosav")
    _seed_archive(
        proj / "archives", name="cycle-1", sha="abc",
        files=["src/EcoSAV/X.cls"],
    )
    res = await client.call_tool(
        "mem_archeo_project_topology",
        {
            "project": "ecosav",
            "synthesis": {},
            "acknowledged_via_read": True,
        },
    )
    assert res.data.success is True
    topo = vault_tmp / "20-knowledge" / "architecture" / "ecosav-project-topology.md"
    assert topo.is_file()
