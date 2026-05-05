"""Tests for the migration framework + mem_migrate tool (v0.9.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client

from memory_kit_mcp.migrations import (
    CURRENT_SCHEMA_VERSION,
    get_vault_schema_version,
    run_pending,
    set_vault_schema_version,
)
from memory_kit_mcp.vault import frontmatter


def test_get_vault_schema_version_defaults_to_zero(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    assert get_vault_schema_version(config) == 0  # missing file


def test_set_then_get_vault_schema_version(tmp_path: Path) -> None:
    config = tmp_path / ".memory-kit" / "config.json"
    set_vault_schema_version(config, 1)
    assert get_vault_schema_version(config) == 1
    set_vault_schema_version(config, 2)
    assert get_vault_schema_version(config) == 2


def test_set_preserves_other_fields(tmp_path: Path) -> None:
    config = tmp_path / ".memory-kit" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"vault": "/path/to/vault", "language": "fr"}),
        encoding="utf-8",
    )
    set_vault_schema_version(config, 1)
    raw = json.loads(config.read_text(encoding="utf-8"))
    assert raw["vault"] == "/path/to/vault"
    assert raw["language"] == "fr"
    assert raw["vault_schema_version"] == 1


def test_run_pending_dry_run_does_not_write(
    tmp_path: Path, vault_tmp: Path
) -> None:
    config = tmp_path / "config.json"
    # Seed an old-style atom in 40-principles
    target = vault_tmp / "40-principles" / "work" / "old-school.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {"slug": "old-school", "kind": "principle", "scope": "work", "project": "alpha"},
        "# old\n",
    )
    # Stub-only zone index
    idx = vault_tmp / "40-principles" / "index.md"
    idx.write_text(
        "---\nzone: meta\ntype: zone-index\n---\n\n# 40-principles — Index\n",
        encoding="utf-8",
    )
    before_idx = idx.read_text(encoding="utf-8")

    report = run_pending(vault_tmp, config, dry_run=True)
    assert report.dry_run is True
    assert report.from_version == 0
    assert any(s.needed for s in report.steps)
    # Dry-run: zone index unchanged on disk.
    assert idx.read_text(encoding="utf-8") == before_idx
    # Schema version unchanged.
    assert get_vault_schema_version(config) == 0


def test_run_pending_apply_migrates_and_bumps_version(
    tmp_path: Path, vault_tmp: Path
) -> None:
    config = tmp_path / ".memory-kit" / "config.json"
    target = vault_tmp / "40-principles" / "work" / "to-migrate.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {"slug": "to-migrate", "kind": "principle", "scope": "work", "project": "alpha"},
        "# atom\n",
    )
    idx = vault_tmp / "40-principles" / "index.md"
    idx.write_text(
        "---\nzone: meta\ntype: zone-index\n---\n\n# 40-principles — Index\n",
        encoding="utf-8",
    )

    report = run_pending(vault_tmp, config, dry_run=False, skip_backup=True)
    assert report.dry_run is False
    assert any(s.applied for s in report.steps)
    assert report.to_version == CURRENT_SCHEMA_VERSION
    # The atom is now indexed.
    assert "to-migrate" in idx.read_text(encoding="utf-8")
    # Version marker bumped.
    assert get_vault_schema_version(config) == CURRENT_SCHEMA_VERSION


def test_run_pending_idempotent(tmp_path: Path, vault_tmp: Path) -> None:
    config = tmp_path / ".memory-kit" / "config.json"
    target = vault_tmp / "40-principles" / "work" / "p.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {"slug": "p", "kind": "principle", "scope": "work"},
        "# p\n",
    )
    run_pending(vault_tmp, config, dry_run=False, skip_backup=True)
    # Second pass: nothing to migrate (already at current version).
    report2 = run_pending(vault_tmp, config, dry_run=False, skip_backup=True)
    assert all(not s.applied for s in report2.steps)
    assert "Nothing to migrate" in report2.summary or "no" in report2.summary.lower()


def test_run_pending_takes_backup(tmp_path: Path, vault_tmp: Path) -> None:
    config = tmp_path / ".memory-kit" / "config.json"
    backup_root = tmp_path / "backups"
    target = vault_tmp / "40-principles" / "work" / "x.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(target, {"slug": "x", "kind": "principle", "scope": "work"}, "# x\n")

    report = run_pending(
        vault_tmp, config, dry_run=False, skip_backup=False, backup_root=backup_root,
    )
    assert report.backup_path
    assert Path(report.backup_path).is_dir()
    # Backup contains the original vault layout.
    assert (Path(report.backup_path) / "40-principles" / "work" / "x.md").is_file()


# ---- Tool-level tests ----


async def test_mem_migrate_dry_run(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool("mem_migrate", {})
    d = res.data
    assert d.dry_run is True
    assert d.target_version == CURRENT_SCHEMA_VERSION


async def test_mem_migrate_apply_skip_backup(
    client: Client, vault_tmp: Path
) -> None:
    target = vault_tmp / "40-principles" / "work" / "via-tool.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {"slug": "via-tool", "kind": "principle", "scope": "work", "project": "alpha"},
        "# via tool\n",
    )
    res = await client.call_tool(
        "mem_migrate", {"apply": True, "skip_backup": True}
    )
    d = res.data
    assert d.dry_run is False
    assert d.to_version == CURRENT_SCHEMA_VERSION
    body = (vault_tmp / "40-principles" / "index.md").read_text(encoding="utf-8")
    assert "via-tool" in body
