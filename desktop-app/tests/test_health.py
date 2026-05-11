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

    # The universal-frontmatter and topology fixers need the real
    # frontmatter / wikilinks helpers — attach them by import so the
    # tests exercise the actual write logic, not a stub.
    from memory_kit_mcp.vault import frontmatter as real_frontmatter
    from memory_kit_mcp.vault import wikilinks as real_wikilinks

    vault_pkg = types.ModuleType("memory_kit_mcp.vault")
    vault_pkg.zone_index = zone_index  # type: ignore[attr-defined]
    vault_pkg.frontmatter = real_frontmatter  # type: ignore[attr-defined]
    vault_pkg.wikilinks = real_wikilinks  # type: ignore[attr-defined]

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
    monkeypatch.setitem(sys.modules, "memory_kit_mcp.vault.frontmatter", real_frontmatter)
    monkeypatch.setitem(sys.modules, "memory_kit_mcp.vault.wikilinks", real_wikilinks)


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


def test_repair_reports_manual_review(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Categories not in ALL_AUTO_FIXABLE land in manual_review_count."""
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    findings = [
        # Auto-fixable now (v0.4) — not counted in manual review.
        FakeFinding(category="missing-display", path="a.md"),
        # Manual-only categories — should be counted.
        FakeFinding(category="orphan-atoms", path="b.md"),
        FakeFinding(category="dangling-wikilinks", path="c.md"),
    ]
    _install_fake_engine(monkeypatch, scan_result=(findings, [], 3))
    report = health.repair_vault()
    assert report.manual_review_count == 2
    assert report.findings_before == 3


def test_repair_destructive_gated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Stray-zone-md is only deleted when apply_destructive is True."""
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    vault = tmp_path / "vault"
    target = vault / "20-knowledge.md"
    target.write_text("", encoding="utf-8")
    findings = [FakeFinding(category="stray-zone-md", path="20-knowledge.md")]
    _install_fake_engine(monkeypatch, scan_result=(findings, [], 1))

    # apply without destructive: file still exists, nothing deleted.
    r1 = health.repair_vault(apply=True, apply_destructive=False)
    assert r1.applied is True
    assert r1.destructive_applied is False
    assert target.exists()
    assert "stray-zone-md" not in r1.fixed_by_category

    # apply destructive: file is deleted.
    r2 = health.repair_vault(apply=True, apply_destructive=True)
    assert r2.destructive_applied is True
    assert not target.exists()
    assert r2.fixed_by_category.get("stray-zone-md", 0) == 1


def test_repair_creates_zone_hub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """missing-zone-index should create the hub file in place."""
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    findings = [FakeFinding(category="missing-zone-index", path="20-knowledge/")]
    _install_fake_engine(monkeypatch, scan_result=(findings, [], 1))

    report = health.repair_vault(apply=True)
    assert report.applied is True
    hub = tmp_path / "vault" / "20-knowledge" / "index.md"
    assert hub.is_file()
    assert "20-knowledge" in hub.read_text(encoding="utf-8")


def test_modality_inference_from_path():
    assert health._modality_from_path("20-knowledge/foo.md") == "knowledge"
    assert health._modality_from_path("40-principles/work/x.md") == "principle"
    assert health._modality_from_path("50-goals/a.md") == "goal"
    assert health._modality_from_path("60-people/p.md") == "person"
    assert (
        health._modality_from_path("10-episodes/projects/x/archives/a.md")
        == "archive"
    )
    assert health._modality_from_path("99-meta/repo-topology/x.md") == "meta"
    assert health._modality_from_path("nonsense/x.md") is None


def test_scope_inference_from_path():
    assert health._scope_from_path("40-principles/work/sec/a.md", "perso") == "work"
    assert health._scope_from_path("40-principles/perso/a.md", "work") == "perso"
    # No /work/ or /perso/ → fall back to default_scope.
    assert health._scope_from_path("20-knowledge/architecture/a.md", "perso") == "perso"
    assert health._scope_from_path("20-knowledge/architecture/a.md", "work") == "work"


def test_repair_fills_universal_frontmatter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """missing-universal-frontmatter should add scope/collective/modality."""
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    vault = tmp_path / "vault"
    atom_rel = "40-principles/work/foo.md"
    atom = vault / atom_rel
    atom.parent.mkdir(parents=True, exist_ok=True)
    atom.write_text(
        "---\ndisplay: foo\nkind: principle\n---\n\nBody\n",
        encoding="utf-8",
    )

    findings = [FakeFinding(category="missing-universal-frontmatter", path=atom_rel)]
    _install_fake_engine(monkeypatch, scan_result=(findings, [], 1))

    report = health.repair_vault(apply=True)
    assert report.applied is True
    assert report.fixed_by_category.get("missing-universal-frontmatter", 0) == 1

    content = atom.read_text(encoding="utf-8")
    assert "scope: work" in content
    assert "collective: false" in content
    assert "modality: principle" in content


def test_repair_topology_appends_archives(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """topology-archives-out-of-sync should append missing archive wikilinks."""
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    vault = tmp_path / "vault"
    rel = "99-meta/repo-topology/myproj.md"

    topo = vault / rel
    topo.parent.mkdir(parents=True, exist_ok=True)
    topo.write_text(
        "---\ndisplay: myproj\ntype: repo-topology\nproject: myproj\n---\n\n"
        "# myproj\n\n"
        "## Atomes dérivés des phases archeo\n\n"
        "- [[existing-archive]]\n",
        encoding="utf-8",
    )

    arch_dir = vault / "10-episodes" / "projects" / "myproj" / "archives"
    arch_dir.mkdir(parents=True, exist_ok=True)
    (arch_dir / "existing-archive.md").write_text("body", encoding="utf-8")
    (arch_dir / "new-archive-1.md").write_text("body", encoding="utf-8")
    (arch_dir / "new-archive-2.md").write_text("body", encoding="utf-8")

    findings = [FakeFinding(category="topology-archives-out-of-sync", path=rel)]
    _install_fake_engine(monkeypatch, scan_result=(findings, [], 1))

    report = health.repair_vault(apply=True)
    assert report.applied is True
    assert report.fixed_by_category.get("topology-archives-out-of-sync", 0) == 1

    body = topo.read_text(encoding="utf-8")
    assert "[[new-archive-1]]" in body
    assert "[[new-archive-2]]" in body
    # Existing wikilink survives.
    assert "[[existing-archive]]" in body


def test_repair_workflow_hint_for_archeo_archives(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Manual-review categories with a known workflow surface a hint."""
    _patch_kit_config(monkeypatch, tmp_path / "vault")
    findings = [
        FakeFinding(category="archeo-archive-incomplete-frontmatter", path="x.md")
    ]
    _install_fake_engine(monkeypatch, scan_result=(findings, [], 1))

    report = health.repair_vault()
    assert "archeo-archive-incomplete-frontmatter" in report.workflow_hints
    assert "mem-archeo-git" in report.workflow_hints[
        "archeo-archive-incomplete-frontmatter"
    ]
