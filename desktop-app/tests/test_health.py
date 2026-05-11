"""Health scan + repair tests — in-process model.

The desktop reaches into ``memory_kit_mcp.health.scan`` and
``memory_kit_mcp.tools.health_repair`` at call time. We patch the
imported symbols via ``sys.modules`` so the test environment doesn't
need a real kit install.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from sb_desktop import health
from sb_desktop.config import KitConfig

from ._engine_fakes import FakeFinding


def _install_fake_engine(
    monkeypatch: pytest.MonkeyPatch,
    *,
    scan_result=None,
    scan_raises: Exception | None = None,
    fix_result: tuple[bool, str] | None = (True, "a.md"),
) -> None:
    """Stand up a fake ``memory_kit_mcp`` package in sys.modules."""

    def fake_scan(vault: Path):
        if scan_raises is not None:
            raise scan_raises
        return scan_result if scan_result is not None else ([], [], 0)

    scan_module = types.ModuleType("memory_kit_mcp.health.scan")
    scan_module.scan_vault = fake_scan  # type: ignore[attr-defined]

    health_pkg = types.ModuleType("memory_kit_mcp.health")
    health_pkg.scan = scan_module  # type: ignore[attr-defined]

    repair_module = types.ModuleType("memory_kit_mcp.tools.health_repair")
    repair_module._AUTO_FIXABLE_CATEGORIES = {"missing-display", "missing-zone-index-entry"}  # type: ignore[attr-defined]
    repair_module._fix_missing_display = lambda vault, rel: fix_result  # type: ignore[attr-defined]

    tools_pkg = types.ModuleType("memory_kit_mcp.tools")
    tools_pkg.health_repair = repair_module  # type: ignore[attr-defined]

    zone_index = types.ModuleType("memory_kit_mcp.vault.zone_index")
    zone_index.ATOM_ZONES = set()  # type: ignore[attr-defined]
    zone_index.regenerate_zone_index = lambda vault, zone: vault / "index.md"  # type: ignore[attr-defined]

    vault_pkg = types.ModuleType("memory_kit_mcp.vault")
    vault_pkg.zone_index = zone_index  # type: ignore[attr-defined]

    root = types.ModuleType("memory_kit_mcp")
    root.health = health_pkg  # type: ignore[attr-defined]
    root.tools = tools_pkg  # type: ignore[attr-defined]
    root.vault = vault_pkg  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "memory_kit_mcp", root)
    monkeypatch.setitem(sys.modules, "memory_kit_mcp.health", health_pkg)
    monkeypatch.setitem(sys.modules, "memory_kit_mcp.health.scan", scan_module)
    monkeypatch.setitem(sys.modules, "memory_kit_mcp.tools", tools_pkg)
    monkeypatch.setitem(sys.modules, "memory_kit_mcp.tools.health_repair", repair_module)
    monkeypatch.setitem(sys.modules, "memory_kit_mcp.vault", vault_pkg)
    monkeypatch.setitem(sys.modules, "memory_kit_mcp.vault.zone_index", zone_index)


def _patch_kit_config(monkeypatch: pytest.MonkeyPatch, vault: Path) -> None:
    vault.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        health,
        "load_kit_config",
        lambda: KitConfig(vault=vault, language="en", kit_repo=None),
    )


def test_scan_no_kit_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(health, "load_kit_config", lambda: None)
    report = health.scan_vault()
    assert report.ok is False
    assert "config not found" in (report.error or "")


def test_scan_clean_vault(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    _install_fake_engine(monkeypatch, scan_result=([], [], 5))
    report = health.scan_vault()
    assert report.ok is True
    assert report.files_scanned == 5
    assert not report.has_findings()


def test_scan_with_findings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    findings = [
        FakeFinding(category="missing-display", severity="info", path="a.md"),
        FakeFinding(category="orphan-atoms", severity="warning", path="b.md"),
    ]
    _install_fake_engine(monkeypatch, scan_result=(findings, [], 10))
    report = health.scan_vault()
    assert report.ok is True
    assert report.has_findings()
    assert report.counts_by_category == {"missing-display": 1, "orphan-atoms": 1}


def test_scan_engine_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    _install_fake_engine(monkeypatch, scan_raises=RuntimeError("boom"))
    report = health.scan_vault()
    assert report.ok is False
    assert "boom" in (report.error or "")


def test_repair_dry_run_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    findings = [FakeFinding(category="missing-display", path="a.md")]
    _install_fake_engine(monkeypatch, scan_result=(findings, [], 1))
    report = health.repair_vault()
    assert report.ok is True
    assert report.applied is False
    assert report.fixed_count == 1


def test_repair_apply_calls_fix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    findings = [FakeFinding(category="missing-display", path="a.md")]
    _install_fake_engine(
        monkeypatch, scan_result=(findings, [], 1), fix_result=(True, "a.md")
    )
    report = health.repair_vault(apply=True)
    assert report.applied is True
    assert report.fixed_count == 1
    assert any("a.md" in m for m in report.files_modified)


def test_repair_skip_on_fix_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    findings = [FakeFinding(category="missing-display", path="a.md")]
    _install_fake_engine(
        monkeypatch, scan_result=(findings, [], 1), fix_result=(False, "a.md")
    )
    report = health.repair_vault(apply=True)
    assert report.skipped_count == 1
    assert report.fixed_count == 0
