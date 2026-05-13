"""Vault relocation + Obsidian scaffolding tests."""

from __future__ import annotations

import json
from pathlib import Path

from sb_desktop import vault_setup


def _make_obsidian_style_adapter(root: Path) -> Path:
    """Create a minimal adapter tree mirroring the real one."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "graph.json").write_text(
        json.dumps({"_secondbrain_canonical": "v0.7.3", "colorGroups": []}),
        encoding="utf-8",
    )
    plugin_dir = root / "plugins" / "obsidian-front-matter-title-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "data.json").write_text(
        json.dumps({"_secondbrain_canonical": "v0.7.3", "templates": {}}),
        encoding="utf-8",
    )
    # README should be ignored.
    (root / "README.md").write_text("docs", encoding="utf-8")
    return root


# Expected base-structure file count: vault/index.md + one index per
# canonical zone (00-inbox, 10-episodes, 20-knowledge, 30-procedures,
# 40-principles, 50-goals, 60-people, 70-cognition, 99-meta).
BASE_SCAFFOLD_FILES = 1 + 9


def test_scaffold_creates_vault_and_copies_files(tmp_path: Path):
    adapter = _make_obsidian_style_adapter(tmp_path / "adapter")
    vault = tmp_path / "vault"

    result = vault_setup.scaffold_vault(vault, obsidian_style_dir=adapter)

    assert vault.is_dir()
    assert (vault / "index.md").is_file()
    # Every canonical zone has its dir + index.md hub.
    for slug, _display, _body in vault_setup.VAULT_ZONES:
        assert (vault / slug).is_dir(), f"missing zone dir {slug}"
        assert (vault / slug / "index.md").is_file(), f"missing zone index {slug}"
    assert (vault / ".obsidian" / "graph.json").is_file()
    plugin = vault / ".obsidian" / "plugins" / "obsidian-front-matter-title-plugin" / "data.json"
    assert plugin.is_file()
    assert not (vault / ".obsidian" / "README.md").exists()  # docs filtered
    assert result.action == "scaffolded"
    # 2 Obsidian files + base structure.
    assert result.scaffold_files == 2 + BASE_SCAFFOLD_FILES


def test_scaffold_idempotent(tmp_path: Path):
    adapter = _make_obsidian_style_adapter(tmp_path / "adapter")
    vault = tmp_path / "vault"

    first = vault_setup.scaffold_vault(vault, obsidian_style_dir=adapter)
    second = vault_setup.scaffold_vault(vault, obsidian_style_dir=adapter)

    assert first.scaffold_files == 2 + BASE_SCAFFOLD_FILES
    assert second.scaffold_files == 0  # everything already in place


def test_scaffold_preserves_user_customisation(tmp_path: Path):
    adapter = _make_obsidian_style_adapter(tmp_path / "adapter")
    vault = tmp_path / "vault"
    custom_path = vault / ".obsidian" / "graph.json"
    custom_path.parent.mkdir(parents=True)
    custom_path.write_text(
        json.dumps({"colorGroups": ["user-customised"]}),  # no marker
        encoding="utf-8",
    )

    result = vault_setup.scaffold_vault(vault, obsidian_style_dir=adapter)

    # User file untouched, no backup; the other Obsidian file plus the
    # base structure are still written.
    assert json.loads(custom_path.read_text(encoding="utf-8")) == {
        "colorGroups": ["user-customised"]
    }
    assert result.skipped_files == 1
    assert result.scaffold_files == 1 + BASE_SCAFFOLD_FILES
    assert not any(custom_path.parent.glob("graph.json.bak-*"))


def test_scaffold_replaces_outdated_canonical(tmp_path: Path):
    adapter = _make_obsidian_style_adapter(tmp_path / "adapter")
    vault = tmp_path / "vault"
    target = vault / ".obsidian" / "graph.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps({"_secondbrain_canonical": "v0.6.0", "colorGroups": []}),
        encoding="utf-8",
    )

    result = vault_setup.scaffold_vault(vault, obsidian_style_dir=adapter)

    # Old canonical replaced + backed up.
    fresh = json.loads(target.read_text(encoding="utf-8"))
    assert fresh["_secondbrain_canonical"] == "v0.7.3"
    backups = list(target.parent.glob("graph.json.bak-pre-style-*"))
    assert len(backups) == 1
    assert result.backed_up_files == 1


def test_migrate_moves_content_then_scaffolds(tmp_path: Path):
    adapter = _make_obsidian_style_adapter(tmp_path / "adapter")
    old = tmp_path / "old-vault"
    new = tmp_path / "new-vault"
    (old / "10-episodes").mkdir(parents=True)
    (old / "10-episodes" / "session-1.md").write_text("hello", encoding="utf-8")
    (old / "index.md").write_text("# Index", encoding="utf-8")

    result = vault_setup.setup_vault(
        new, old_vault=old, obsidian_style_dir=adapter
    )

    assert (
        new / "10-episodes" / "session-1.md"
    ).read_text(encoding="utf-8") == "hello"
    # Migrated index.md must be preserved as-is (idempotent base scaffold
    # never overwrites an existing file).
    assert (new / "index.md").read_text(encoding="utf-8") == "# Index"
    assert (new / ".obsidian" / "graph.json").is_file()
    assert not old.exists()  # old folder cleaned up
    assert result.action == "migrated"
    assert result.moved_entries == 2
    # Migration moved index.md + 10-episodes/ over. Subsequent scaffold
    # creates 10-episodes/index.md (missing in old) + the other 8 zone
    # index files + 2 Obsidian config files. The vault root index.md is
    # preserved as-is.
    assert result.scaffold_files == 2 + 9


def test_migrate_noop_when_paths_equal(tmp_path: Path):
    adapter = _make_obsidian_style_adapter(tmp_path / "adapter")
    vault = tmp_path / "vault"
    vault.mkdir()

    result = vault_setup.setup_vault(
        vault, old_vault=vault, obsidian_style_dir=adapter
    )

    # Equal paths → scaffold only, no migration noise.
    assert result.action == "scaffolded"


def test_migrate_skips_collisions_without_overwriting(tmp_path: Path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    (old / "archives").mkdir(parents=True)
    (old / "archives" / "x.md").write_text("source", encoding="utf-8")
    (new / "archives").mkdir(parents=True)
    (new / "archives" / "x.md").write_text("target", encoding="utf-8")

    result = vault_setup.migrate_vault(old, new)

    # Target preserved, source kept in old/ for the user to inspect.
    assert (new / "archives" / "x.md").read_text(encoding="utf-8") == "target"
    assert (old / "archives" / "x.md").exists()
    assert result.skipped_files >= 1


def test_audit_reports_missing_zones(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    # Partial scaffold: vault root index.md + one zone only.
    (vault / "index.md").write_text("# x", encoding="utf-8")
    (vault / "00-inbox").mkdir()
    (vault / "00-inbox" / "index.md").write_text("# inbox", encoding="utf-8")
    # Add a non-canonical dir so the audit surfaces it.
    (vault / "old-archives").mkdir()

    audit = vault_setup.audit_vault_structure(vault)
    assert audit.needs_repair is True
    assert audit.root_index_missing is False
    assert "00-inbox" not in audit.missing_zone_dirs
    assert "10-episodes" in audit.missing_zone_dirs
    assert "old-archives" in audit.non_canonical_top_level


def test_audit_clean_vault(tmp_path: Path):
    vault = tmp_path / "vault"
    vault_setup.scaffold_vault(vault, obsidian_style_dir=None)
    audit = vault_setup.audit_vault_structure(vault)
    assert audit.needs_repair is False
    assert audit.missing_zone_dirs == []
    assert audit.missing_zone_indexes == []


def test_repair_vault_structure_idempotent(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    # One zone present + custom file under it.
    (vault / "10-episodes").mkdir()
    (vault / "10-episodes" / "user.md").write_text("hello", encoding="utf-8")

    first = vault_setup.repair_vault_structure(vault)
    assert first.scaffold_files > 0
    # User file preserved.
    assert (vault / "10-episodes" / "user.md").read_text(encoding="utf-8") == "hello"
    audit = vault_setup.audit_vault_structure(vault)
    assert audit.needs_repair is False

    second = vault_setup.repair_vault_structure(vault)
    assert second.scaffold_files == 0  # everything already present


def test_setup_vault_creates_target_without_adapter(tmp_path: Path):
    vault = tmp_path / "vault"

    result = vault_setup.setup_vault(vault, obsidian_style_dir=None)

    assert vault.is_dir()
    assert not (vault / ".obsidian").exists()  # no adapter, no scaffold
    assert result.action == "scaffolded"
