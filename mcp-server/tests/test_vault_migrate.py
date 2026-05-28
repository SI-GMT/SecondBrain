"""Tests for mem_vault_migrate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError


async def test_dry_run_reports_plan_without_moving(client: Client, vault_tmp: Path) -> None:
    target = vault_tmp.parent / "new-vault"
    res = await client.call_tool("mem_vault_migrate", {"target": str(target)})
    d = res.data
    assert d.success is True
    assert "dry-run" in d.summary_md.lower()
    # Source untouched, target absent.
    assert vault_tmp.exists()
    assert not target.exists()
    # Warning announces dry-run.
    assert any("dry-run" in w.lower() for w in d.warnings)


async def test_confirm_moves_vault_and_updates_config(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    target = tmp_path / "moved-vault"
    res = await client.call_tool(
        "mem_vault_migrate", {"target": str(target), "confirm": True}
    )
    d = res.data
    assert d.success is True
    # Source gone, target populated.
    assert not vault_tmp.exists()
    assert target.exists()
    assert (target / "index.md").exists()
    # ~/.memory-kit/config.json updated to new path.
    cfg_path = tmp_path / ".memory-kit" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert Path(cfg["vault"]) == target
    # Migration log written.
    log = target / "99-meta" / "migrations" / "vault-migrations.md"
    assert log.exists()
    assert "vault moved" in log.read_text(encoding="utf-8")


async def test_target_equals_source_raises(client: Client, vault_tmp: Path) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_vault_migrate", {"target": str(vault_tmp), "confirm": True}
        )


async def test_target_nonempty_raises(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    (target / "file.md").write_text("not empty", encoding="utf-8")
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_vault_migrate", {"target": str(target), "confirm": True}
        )


async def test_target_empty_dir_accepted(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    target = tmp_path / "empty-target"
    target.mkdir()
    # Dry-run only — make sure pre-flight passes.
    res = await client.call_tool("mem_vault_migrate", {"target": str(target)})
    assert res.data.success is True


async def test_idempotent_audit_log_format(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    target = tmp_path / "vault-v2"
    res = await client.call_tool(
        "mem_vault_migrate", {"target": str(target), "confirm": True}
    )
    assert res.data.success is True
    log_text = (target / "99-meta" / "migrations" / "vault-migrations.md").read_text(
        encoding="utf-8"
    )
    assert log_text.startswith("---\n")
    assert "Migration log" in log_text
    assert "vault moved" in log_text
    assert str(target) in log_text


async def test_lock_file_detection_blocks_migration(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    # Plant an Obsidian-style lock file.
    (vault_tmp / "obsidian.lock").write_text("locked", encoding="utf-8")
    target = tmp_path / "target"
    with pytest.raises(ToolError, match="locked"):
        await client.call_tool(
            "mem_vault_migrate", {"target": str(target), "confirm": True}
        )
