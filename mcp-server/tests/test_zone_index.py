"""Tests for vault.zone_index — transverse-atom zone index generator (v0.9.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_kit_mcp.vault import frontmatter
from memory_kit_mcp.vault.zone_index import (
    ATOM_ZONES,
    ZONE_DISPLAY_NAMES,
    group_atoms_by_project,
    regenerate_all_zone_indexes,
    regenerate_zone_index,
    scan_zone_atoms,
    update_zone_index_for_atom,
)


def _seed_atom(vault: Path, zone: str, sub: str, slug: str, project: str | None) -> Path:
    p = vault / zone / sub / f"{slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "slug": slug,
        "zone": zone.split("-", 1)[1] if "-" in zone else zone,
        "kind": "principle" if "principles" in zone else "knowledge",
        "scope": "work",
        "tags": [f"zone/{zone}", f"scope/work"],
        "display": slug,
    }
    if project:
        fm["project"] = project
        fm["tags"].append(f"project/{project}")
    frontmatter.write(p, fm, f"# {slug}\n\nbody\n")
    return p


def test_scan_zone_atoms_excludes_index(vault_tmp: Path) -> None:
    _seed_atom(vault_tmp, "40-principles", "work/security", "no-force-push", "alpha")
    _seed_atom(vault_tmp, "40-principles", "work/security", "rls-policy", "alpha")
    atoms = scan_zone_atoms(vault_tmp, "40-principles")
    names = {p.stem for p, _ in atoms}
    assert "no-force-push" in names
    assert "rls-policy" in names
    assert "index" not in names


def test_group_atoms_by_project(vault_tmp: Path) -> None:
    _seed_atom(vault_tmp, "40-principles", "work", "p1", "alpha")
    _seed_atom(vault_tmp, "40-principles", "work", "p2", "alpha")
    _seed_atom(vault_tmp, "40-principles", "work", "p3", "beta")
    _seed_atom(vault_tmp, "40-principles", "work", "p4", None)
    atoms = scan_zone_atoms(vault_tmp, "40-principles")
    grouped = group_atoms_by_project(atoms)
    assert sorted(p.stem for p in grouped["alpha"]) == ["p1", "p2"]
    assert [p.stem for p in grouped["beta"]] == ["p3"]
    assert [p.stem for p in grouped[None]] == ["p4"]


def test_regenerate_zone_index_writes_file(vault_tmp: Path) -> None:
    _seed_atom(vault_tmp, "40-principles", "work/sec", "p1", "alpha")
    target = regenerate_zone_index(vault_tmp, "40-principles")
    assert target == vault_tmp / "40-principles" / "index.md"
    assert target.is_file()
    fm, body = frontmatter.read(target)
    assert fm["zone"] == "meta"
    assert fm["type"] == "zone-index"
    assert "40-principles" in body
    assert "alpha" in body
    assert "p1" in body


def test_regenerate_zone_index_idempotent(vault_tmp: Path) -> None:
    _seed_atom(vault_tmp, "40-principles", "work/sec", "p1", "alpha")
    target = regenerate_zone_index(vault_tmp, "40-principles")
    content_first = target.read_text(encoding="utf-8")
    target = regenerate_zone_index(vault_tmp, "40-principles")
    content_second = target.read_text(encoding="utf-8")
    assert content_first == content_second


def test_regenerate_zone_index_unattached_section(vault_tmp: Path) -> None:
    _seed_atom(vault_tmp, "20-knowledge", "concepts", "stray", None)
    regenerate_zone_index(vault_tmp, "20-knowledge")
    body = (vault_tmp / "20-knowledge" / "index.md").read_text(encoding="utf-8")
    assert "Unattached" in body
    assert "stray" in body


def test_regenerate_zone_index_empty(vault_tmp: Path) -> None:
    # Force a clean zone (some fixtures may have content; we use a fresh subdir)
    fresh_zone = "60-people"
    # Wipe any seed files
    base = vault_tmp / fresh_zone
    base.mkdir(parents=True, exist_ok=True)
    for f in list(base.rglob("*.md")):
        if f.name != "index.md":
            f.unlink()
    target = regenerate_zone_index(vault_tmp, fresh_zone)
    body = target.read_text(encoding="utf-8")
    assert "(none yet" in body


def test_regenerate_zone_index_rejects_non_atom_zone(vault_tmp: Path) -> None:
    with pytest.raises(ValueError):
        regenerate_zone_index(vault_tmp, "00-inbox")


def test_update_zone_index_for_atom_targets_correct_zone(vault_tmp: Path) -> None:
    p = _seed_atom(vault_tmp, "40-principles", "work", "fresh-principle", "alpha")
    target = update_zone_index_for_atom(vault_tmp, p)
    assert target == vault_tmp / "40-principles" / "index.md"
    body = target.read_text(encoding="utf-8")
    assert "fresh-principle" in body


def test_update_zone_index_for_atom_returns_none_for_non_atom_zone(
    vault_tmp: Path,
) -> None:
    p = vault_tmp / "00-inbox" / "anything.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nslug: x\n---\nbody\n", encoding="utf-8")
    assert update_zone_index_for_atom(vault_tmp, p) is None


def test_update_zone_index_for_atom_returns_none_outside_vault(
    vault_tmp: Path, tmp_path: Path,
) -> None:
    outside = tmp_path / "elsewhere.md"
    outside.write_text("body", encoding="utf-8")
    assert update_zone_index_for_atom(vault_tmp, outside) is None


def test_regenerate_all_zone_indexes(vault_tmp: Path) -> None:
    _seed_atom(vault_tmp, "40-principles", "work", "p1", "alpha")
    _seed_atom(vault_tmp, "20-knowledge", "concepts", "k1", "alpha")
    written = regenerate_all_zone_indexes(vault_tmp)
    paths = {p.name for p in written}
    assert "index.md" in paths
    # Both zones should be regenerated since they contain atoms
    written_zones = {p.parent.name for p in written}
    assert "40-principles" in written_zones
    assert "20-knowledge" in written_zones


def test_atom_zones_constant_complete() -> None:
    """Sanity: ATOM_ZONES covers exactly knowledge / principles / goals / people."""
    assert set(ATOM_ZONES) == {"20-knowledge", "40-principles", "50-goals", "60-people"}
    assert all(z in ZONE_DISPLAY_NAMES for z in ATOM_ZONES)


def test_ingestion_via_mem_principle_updates_zone_index(
    vault_tmp: Path,
) -> None:
    """Integration test — going through the public mem_principle tool path
    triggers the zone-index update via the modified write_atom."""
    from memory_kit_mcp.tools._ingestion import standard_frontmatter, write_atom

    fm = standard_frontmatter(
        slug="integration-test-principle",
        zone_short="principles",
        kind="principle",
        scope="work",
        project="alpha",
    )
    target = vault_tmp / "40-principles" / "work" / "integration-test-principle.md"
    body = "# integration test\n\nbody\n"
    written = write_atom(target, fm, body, vault=vault_tmp)
    assert written.is_file()

    index_body = (vault_tmp / "40-principles" / "index.md").read_text(encoding="utf-8")
    assert "integration-test-principle" in index_body
