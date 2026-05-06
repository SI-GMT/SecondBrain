"""Tests for mem_health_scan and mem_health_repair."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.health.scan import scan_vault
from memory_kit_mcp.sync import ManifestEntry, compute_procedure_hash, save_manifest
from memory_kit_mcp.vault import frontmatter


# ---------- mem_health_scan ----------


async def test_health_scan_clean_fixture_baseline(client: Client, vault_tmp: Path) -> None:
    """Baseline: the fixture vault is well-formed, expect mostly missing-display findings."""
    res = await client.call_tool("mem_health_scan", {})
    d = res.data
    assert d.files_scanned > 0
    # The fixture has display set on most files but not the index.md
    # We don't assert == 0 because the seeded fixture isn't perfect — just that scan runs.
    assert d.findings_total >= 0


async def test_health_scan_detects_malformed_frontmatter(
    client: Client, vault_tmp: Path
) -> None:
    bad = vault_tmp / "00-inbox" / "bad.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text(
        "---\n: invalid: yaml:\n  - bad\n :\n---\n# body\n",
        encoding="utf-8",
    )
    res = await client.call_tool("mem_health_scan", {})
    d = res.data
    assert any(
        f.category == "malformed-frontmatter" and "bad.md" in f.path for f in d.findings
    )


async def test_health_scan_detects_missing_display(
    client: Client, vault_tmp: Path
) -> None:
    target = vault_tmp / "20-knowledge" / "no-display.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(target, {"slug": "no-display", "zone": "knowledge"}, "# body\n")
    res = await client.call_tool("mem_health_scan", {})
    d = res.data
    matching = [
        f for f in d.findings if f.category == "missing-display" and "no-display.md" in f.path
    ]
    assert matching, "expected a missing-display finding"
    assert matching[0].auto_fixable is True


async def test_health_scan_detects_orphan_atom(
    client: Client, vault_tmp: Path
) -> None:
    target = vault_tmp / "40-principles" / "work" / "orphan.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    # No project/* tag, no project/domain frontmatter — orphan
    frontmatter.write(
        target,
        {"slug": "orphan", "zone": "principles", "display": "orphan"},
        "# orphan\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    d = res.data
    assert any(
        f.category == "orphan-atoms" and "orphan.md" in f.path for f in d.findings
    )


async def test_health_scan_category_filter(client: Client, vault_tmp: Path) -> None:
    target = vault_tmp / "20-knowledge" / "no-display.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(target, {"slug": "no-display", "zone": "knowledge"}, "# body\n")
    res = await client.call_tool(
        "mem_health_scan", {"category": "missing-display"}
    )
    d = res.data
    assert all(f.category == "missing-display" for f in d.findings)


# ---------- New categories ported from scripts/mem-health-scan.py ----------


async def test_health_scan_detects_stray_zone_md(
    client: Client, vault_tmp: Path
) -> None:
    """Empty MD at root named after a zone (e.g. 20-knowledge.md) — created
    by Obsidian when clicking a dangling wikilink."""
    stray = vault_tmp / "20-knowledge.md"
    stray.write_text("", encoding="utf-8")
    res = await client.call_tool("mem_health_scan", {})
    d = res.data
    matches = [f for f in d.findings if f.category == "stray-zone-md"]
    assert any("20-knowledge.md" in f.path for f in matches)


async def test_health_scan_detects_empty_md_at_root(
    client: Client, vault_tmp: Path
) -> None:
    """Empty MD at root NOT named after a zone."""
    empty = vault_tmp / "scratchpad.md"
    empty.write_text("", encoding="utf-8")
    res = await client.call_tool("mem_health_scan", {})
    d = res.data
    matches = [f for f in d.findings if f.category == "empty-md-at-root"]
    assert any("scratchpad.md" in f.path for f in matches)


async def test_health_scan_detects_missing_zone_index(
    client: Client, vault_tmp: Path
) -> None:
    """A zone folder exists but has no index.md hub."""
    # Create a zone without its index.md
    zone = vault_tmp / "70-cognition"
    zone.mkdir(parents=True, exist_ok=True)
    # Make sure no index.md exists
    idx = zone / "index.md"
    if idx.exists():
        idx.unlink()
    res = await client.call_tool("mem_health_scan", {})
    d = res.data
    matches = [f for f in d.findings if f.category == "missing-zone-index"]
    assert any("70-cognition" in f.path for f in matches)


async def test_health_scan_detects_dangling_wikilinks(
    client: Client, vault_tmp: Path
) -> None:
    """A wikilink [[X]] whose target does not exist anywhere in the vault."""
    target = vault_tmp / "20-knowledge" / "with-dangling.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {"slug": "with-dangling", "zone": "knowledge", "display": "with-dangling"},
        "See also [[totally-fictional-target]] for context.\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    d = res.data
    matches = [f for f in d.findings if f.category == "dangling-wikilinks"]
    assert any("totally-fictional-target" in f.message for f in matches)


async def test_health_scan_dangling_wikilink_ignores_code(
    client: Client, vault_tmp: Path
) -> None:
    """Wikilinks inside fenced code blocks must not trigger dangling findings."""
    target = vault_tmp / "20-knowledge" / "with-codeblock.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {"slug": "with-codeblock", "zone": "knowledge", "display": "with-codeblock"},
        "Example:\n```\n[[example-fictional-link]]\n```\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    d = res.data
    # The fictional link inside the code block must NOT trigger a finding.
    assert not any(
        "example-fictional-link" in f.message
        for f in d.findings if f.category == "dangling-wikilinks"
    )


async def test_health_scan_detects_missing_archeo_hashes(
    client: Client, vault_tmp: Path
) -> None:
    """An atom with `source: archeo-*` and no `content_hash` is flagged."""
    target = vault_tmp / "20-knowledge" / "alpha-stack-frontend.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {
            "slug": "alpha-stack-frontend",
            "zone": "knowledge",
            "display": "alpha-stack-frontend",
            "source": "archeo-stack",
            # content_hash deliberately missing
            "project": "alpha",
        },
        "# Stack — frontend\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    d = res.data
    matches = [f for f in d.findings if f.category == "missing-archeo-hashes"]
    assert any("alpha-stack-frontend" in f.path for f in matches)


async def test_health_scan_detects_missing_previous_topology_hash(
    client: Client, vault_tmp: Path
) -> None:
    """A repo-topology atom missing previous_topology_hash is flagged."""
    target = vault_tmp / "99-meta" / "repo-topology" / "beta.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {
            "slug": "beta",
            "zone": "meta",
            "display": "beta — topology",
            "type": "repo-topology",
            "source": "archeo-orchestrator",
            "content_hash": "abc123",
            "project": "beta",
            # previous_topology_hash deliberately missing
        },
        "# Topology — beta\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    d = res.data
    matches = [
        f for f in d.findings
        if f.category == "missing-archeo-hashes" and "previous_topology_hash" in f.message
    ]
    assert matches, "expected a missing previous_topology_hash finding"


# ---------- mcp-tool-spec-drift (9th category) ----------


def _seed_kit_with_procedure(root: Path, name: str, body: str) -> Path:
    proc_dir = root / "core" / "procedures"
    proc_dir.mkdir(parents=True, exist_ok=True)
    (proc_dir / name).write_text(body, encoding="utf-8")
    return proc_dir / name


def test_drift_detected_when_procedure_changed_after_sync(
    tmp_path: Path, vault_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A procedure body that no longer matches the recorded hash → finding."""
    kit = tmp_path / "kit"
    proc_path = _seed_kit_with_procedure(kit, "mem-recall.md", "# baseline\n")
    baseline_hash = compute_procedure_hash(proc_path)

    manifest_path = tmp_path / "sync.json"
    save_manifest(
        {"mem_recall": ManifestEntry("mem-recall.md", baseline_hash)},
        manifest_path,
    )
    monkeypatch.setattr("memory_kit_mcp.sync.MANIFEST_PATH", manifest_path)

    # Simulate the developer editing the procedure WITHOUT re-syncing.
    proc_path.write_text("# modified body — drift!\n", encoding="utf-8")

    findings, _errors, _scanned = scan_vault(vault_tmp, kit_repo=kit)
    drift = [f for f in findings if f.category == "mcp-tool-spec-drift"]
    assert len(drift) == 1
    assert "mem_recall" in drift[0].message
    assert drift[0].severity == "info"


def test_no_drift_when_procedure_matches_manifest(
    tmp_path: Path, vault_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = tmp_path / "kit"
    proc_path = _seed_kit_with_procedure(kit, "mem-recall.md", "# stable body\n")
    manifest_path = tmp_path / "sync.json"
    save_manifest(
        {"mem_recall": ManifestEntry("mem-recall.md", compute_procedure_hash(proc_path))},
        manifest_path,
    )
    monkeypatch.setattr("memory_kit_mcp.sync.MANIFEST_PATH", manifest_path)

    findings, _errors, _scanned = scan_vault(vault_tmp, kit_repo=kit)
    assert not [f for f in findings if f.category == "mcp-tool-spec-drift"]


def test_drift_silently_skipped_when_kit_repo_absent(
    vault_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No kit_repo argument → category silently does nothing (no errors)."""
    findings, _errors, _scanned = scan_vault(vault_tmp, kit_repo=None)
    assert not [f for f in findings if f.category == "mcp-tool-spec-drift"]


def test_drift_silently_skipped_when_manifest_absent(
    tmp_path: Path, vault_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = tmp_path / "kit"
    _seed_kit_with_procedure(kit, "mem-recall.md", "# body\n")
    monkeypatch.setattr(
        "memory_kit_mcp.sync.MANIFEST_PATH", tmp_path / "absent.json"
    )
    findings, _errors, _scanned = scan_vault(vault_tmp, kit_repo=kit)
    assert not [f for f in findings if f.category == "mcp-tool-spec-drift"]


def test_drift_flags_missing_procedure_file(
    tmp_path: Path, vault_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Manifest references a procedure that no longer exists on disk → finding."""
    kit = tmp_path / "kit"
    (kit / "core" / "procedures").mkdir(parents=True)
    manifest_path = tmp_path / "sync.json"
    save_manifest(
        {"mem_recall": ManifestEntry("mem-recall.md", "any-hash")},
        manifest_path,
    )
    monkeypatch.setattr("memory_kit_mcp.sync.MANIFEST_PATH", manifest_path)

    findings, _errors, _scanned = scan_vault(vault_tmp, kit_repo=kit)
    drift = [f for f in findings if f.category == "mcp-tool-spec-drift"]
    assert len(drift) == 1
    assert "missing" in drift[0].message.lower()


# ---------- skill-description-too-long (10th category, mcp-only) ----------


def _seed_kit_with_skill(
    root: Path,
    adapter: str,
    skill_name: str,
    description: str,
    *,
    codex_style: bool = False,
) -> Path:
    """Write a minimal SKILL.md template for the given adapter.

    ``codex_style`` (also used for vibe and copilot-cli) writes the file at
    ``adapters/{adapter}/skills/{skill_name}/SKILL.md.template``. Otherwise
    (claude-code style) writes ``adapters/{adapter}/skills/{skill_name}.template.md``.
    """
    if codex_style:
        path = root / "adapters" / adapter / "skills" / skill_name / "SKILL.md.template"
    else:
        path = root / "adapters" / adapter / "skills" / f"{skill_name}.template.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {skill_name}\ndescription: \"{description}\"\n---\n\n{{{{PROCEDURE}}}}\n",
        encoding="utf-8",
    )
    return path


def test_skill_description_too_long_detected_claude_code(
    tmp_path: Path, vault_tmp: Path
) -> None:
    kit = tmp_path / "kit"
    long_desc = "x" * 1100  # > 1024
    _seed_kit_with_skill(kit, "claude-code", "mem-bad", long_desc)

    findings, _errors, _scanned = scan_vault(vault_tmp, kit_repo=kit)
    matches = [f for f in findings if f.category == "skill-description-too-long"]
    assert len(matches) == 1
    assert "mem-bad" in matches[0].path
    assert "1100" in matches[0].message
    assert matches[0].severity == "warning"


def test_skill_description_within_limit_no_finding(
    tmp_path: Path, vault_tmp: Path
) -> None:
    kit = tmp_path / "kit"
    _seed_kit_with_skill(kit, "claude-code", "mem-fine", "x" * 1024)
    findings, _errors, _scanned = scan_vault(vault_tmp, kit_repo=kit)
    assert not [f for f in findings if f.category == "skill-description-too-long"]


def test_skill_description_too_long_detected_codex_style(
    tmp_path: Path, vault_tmp: Path
) -> None:
    """Same check applies to codex / vibe / copilot SKILL.md.template layout."""
    kit = tmp_path / "kit"
    _seed_kit_with_skill(kit, "codex", "mem-bad", "y" * 1500, codex_style=True)
    findings, _errors, _scanned = scan_vault(vault_tmp, kit_repo=kit)
    matches = [f for f in findings if f.category == "skill-description-too-long"]
    assert len(matches) == 1
    assert "codex" in matches[0].path
    assert "mem-bad" in matches[0].path


def test_skill_description_skipped_when_kit_repo_absent(
    vault_tmp: Path,
) -> None:
    findings, _errors, _scanned = scan_vault(vault_tmp, kit_repo=None)
    assert not [f for f in findings if f.category == "skill-description-too-long"]


def test_skill_description_skipped_when_adapters_absent(
    tmp_path: Path, vault_tmp: Path
) -> None:
    kit = tmp_path / "kit-without-adapters"
    kit.mkdir()
    findings, _errors, _scanned = scan_vault(vault_tmp, kit_repo=kit)
    assert not [f for f in findings if f.category == "skill-description-too-long"]


def test_skill_description_gemini_not_audited(
    tmp_path: Path, vault_tmp: Path
) -> None:
    """Gemini uses TOML, not the Anthropic SKILL.md format — must not be scanned."""
    kit = tmp_path / "kit"
    gemini_dir = kit / "adapters" / "gemini-cli" / "commands"
    gemini_dir.mkdir(parents=True)
    # Even a wildly long description in a Gemini TOML must not be flagged
    (gemini_dir / "mem-x.template.toml").write_text(
        f"description = '''{'z' * 5000}'''\n",
        encoding="utf-8",
    )
    findings, _errors, _scanned = scan_vault(vault_tmp, kit_repo=kit)
    assert not [f for f in findings if f.category == "skill-description-too-long"]


# ---------- missing-zone-index-entry (11th category, v0.9.4) ----------


async def test_missing_zone_index_entry_detected(
    client: Client, vault_tmp: Path
) -> None:
    """Atom present in 40-principles/ but absent from 40-principles/index.md → finding."""
    target = vault_tmp / "40-principles" / "work" / "ghost-principle.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {"slug": "ghost-principle", "zone": "principles", "display": "ghost-principle",
         "kind": "principle", "scope": "work", "project": "alpha"},
        "# ghost\n",
    )
    # Ensure the zone index exists but does NOT mention the atom (stub form).
    idx = vault_tmp / "40-principles" / "index.md"
    idx.write_text(
        "---\nzone: meta\ntype: zone-index\ndisplay: \"40-principles — index\"\n"
        "tags: [zone/meta, type/zone-index, target-zone/40-principles]\n---\n\n"
        "# 40-principles — Index\n\n_Hub of the zone._\n",
        encoding="utf-8",
    )
    res = await client.call_tool(
        "mem_health_scan", {"category": "missing-zone-index-entry"}
    )
    matches = [f for f in res.data.findings if f.category == "missing-zone-index-entry"]
    assert any("ghost-principle" in f.path for f in matches)


async def test_missing_zone_index_entry_auto_fixable(
    client: Client, vault_tmp: Path
) -> None:
    """mem_health_repair --apply regenerates the zone index, including the atom."""
    target = vault_tmp / "40-principles" / "work" / "fix-me.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {"slug": "fix-me", "zone": "principles", "display": "fix-me",
         "kind": "principle", "scope": "work", "project": "alpha"},
        "# fix me\n",
    )
    # Stub-only zone index
    idx = vault_tmp / "40-principles" / "index.md"
    idx.write_text(
        "---\nzone: meta\ntype: zone-index\ndisplay: \"40-principles — index\"\n"
        "tags: [zone/meta, type/zone-index]\n---\n\n# 40-principles — Index\n",
        encoding="utf-8",
    )

    res = await client.call_tool("mem_health_repair", {"apply": True})
    assert res.data.dry_run is False
    assert res.data.fixes_applied >= 1

    body = (vault_tmp / "40-principles" / "index.md").read_text(encoding="utf-8")
    assert "fix-me" in body


# ---------- mem_health_repair ----------


async def test_health_repair_dry_run_does_not_write(
    client: Client, vault_tmp: Path
) -> None:
    target = vault_tmp / "20-knowledge" / "no-display.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(target, {"slug": "no-display", "zone": "knowledge"}, "# body\n")
    res = await client.call_tool("mem_health_repair", {})
    assert res.data.dry_run is True
    assert res.data.files_modified == []
    fm, _ = frontmatter.read(target)
    assert "display" not in fm  # no write happened


async def test_health_repair_apply_writes_display(
    client: Client, vault_tmp: Path
) -> None:
    target = vault_tmp / "20-knowledge" / "no-display.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(target, {"slug": "no-display", "zone": "knowledge"}, "# body\n")
    res = await client.call_tool("mem_health_repair", {"apply": True})
    assert res.data.dry_run is False
    assert res.data.fixes_applied >= 1
    fm, _ = frontmatter.read(target)
    assert "display" in fm
    assert fm["display"] == "no-display"


async def test_health_repair_idempotent(client: Client, vault_tmp: Path) -> None:
    target = vault_tmp / "20-knowledge" / "no-display.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(target, {"slug": "no-display", "zone": "knowledge"}, "# body\n")
    await client.call_tool("mem_health_repair", {"apply": True})
    res = await client.call_tool("mem_health_repair", {"apply": True})
    # Second pass: no missing-display findings remain on this file
    assert res.data.fixes_applied == 0 or all(
        "no-display.md" not in m for m in res.data.files_modified
    )


# ---------- missing-universal-frontmatter (12th category, v0.9.x) ----------


async def test_health_scan_detects_missing_universal_frontmatter(
    client: Client, vault_tmp: Path
) -> None:
    """An atom outside inbox/meta missing scope/collective/modality is flagged."""
    target = vault_tmp / "40-principles" / "work" / "methodology" / "weak.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {
            "zone": "principles",
            "type": "principle",
            "project": "alpha",
            "display": "principle: weak",
            # scope, collective, modality DELIBERATELY missing
        },
        "# Weak principle\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    matches = [
        f for f in res.data.findings
        if f.category == "missing-universal-frontmatter" and "weak" in f.path
    ]
    assert matches, "expected a missing-universal-frontmatter finding"
    assert "scope" in matches[0].message
    assert "collective" in matches[0].message
    assert "modality" in matches[0].message


async def test_health_scan_meta_zone_exempt_from_universal_check(
    client: Client, vault_tmp: Path
) -> None:
    """An atom with zone: meta is exempt regardless of where it lives."""
    target = vault_tmp / "20-knowledge" / "ghost-meta.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {"zone": "meta", "type": "doctrine", "display": "ghost"},
        "# meta-typed atom in a non-meta folder\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    matches = [
        f for f in res.data.findings
        if f.category == "missing-universal-frontmatter" and "ghost-meta" in f.path
    ]
    assert not matches, "zone: meta atoms should not trigger universal-frontmatter check"


# ---------- missing-archeo-context-origin (13th category, v0.9.x) ----------


async def test_health_scan_detects_missing_archeo_context_origin(
    client: Client, vault_tmp: Path
) -> None:
    """An archeo-context atom without context_origin is flagged."""
    target = vault_tmp / "40-principles" / "work" / "no-origin.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {
            "zone": "principles", "type": "principle", "project": "alpha",
            "scope": "work", "collective": False, "modality": "left",
            "source": "archeo-context", "source_doc": "CLAUDE.md",
            "display": "principle: no-origin",
            # context_origin DELIBERATELY missing
        },
        "# No origin\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    matches = [
        f for f in res.data.findings
        if f.category == "missing-archeo-context-origin" and "no-origin" in f.path
    ]
    assert matches


async def test_health_scan_detects_wrong_archeo_context_origin(
    client: Client, vault_tmp: Path
) -> None:
    """An archeo-stack atom with a context_origin that doesn't point to topology."""
    target = vault_tmp / "20-knowledge" / "wrong-origin.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {
            "zone": "knowledge", "type": "architecture", "project": "alpha",
            "scope": "work", "collective": False, "modality": "left",
            "source": "archeo-stack",
            "context_origin": "[[some-random-anchor]]",  # wrong target
            "display": "knowledge: wrong-origin",
        },
        "# Wrong origin\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    matches = [
        f for f in res.data.findings
        if f.category == "missing-archeo-context-origin" and "wrong-origin" in f.path
    ]
    assert matches
    assert "expected" in matches[0].message


async def test_health_scan_archeo_git_archive_exempt_from_origin_check(
    client: Client, vault_tmp: Path
) -> None:
    """archeo-git archives (in archives/) don't need context_origin."""
    arch_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    arch_dir.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        arch_dir / "2026-05-06-12h00-alpha-archeo-git-window-2026-05-06.md",
        {
            "date": "2026-05-06", "time": "12:00",
            "zone": "episodes", "kind": "project", "project": "alpha",
            "scope": "work", "collective": False, "modality": "left",
            "type": "archive", "source": "archeo-git",
            "milestone_kind": "window", "source_milestone": "window-2026-05-06",
            "commit_sha": "abc", "friction_detected": False,
            "branch": "", "branch_base": "", "branch_base_sha": "",
            "display": "alpha — 2026-05-06 archive",
            "derived_atoms": [],
            # context_origin deliberately absent — archives don't need it
        },
        "# Archive\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    matches = [
        f for f in res.data.findings
        if f.category == "missing-archeo-context-origin"
        and "alpha-archeo-git-window" in f.path
    ]
    assert not matches


# ---------- archeo-derived-orphan (14th category, v0.9.x) ----------


async def test_health_scan_detects_archeo_derived_orphan(
    client: Client, vault_tmp: Path
) -> None:
    """An archeo-git atom outside archives/ not referenced anywhere is flagged."""
    target = vault_tmp / "40-principles" / "work" / "orphan-derived.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        target,
        {
            "zone": "principles", "type": "principle", "project": "alpha",
            "scope": "work", "collective": False, "modality": "left",
            "source": "archeo-git", "source_milestone": "window-X",
            "context_origin": "[[some-archive]]",
            "display": "principle: orphan-derived",
        },
        "# Orphan derived\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    matches = [
        f for f in res.data.findings
        if f.category == "archeo-derived-orphan" and "orphan-derived" in f.path
    ]
    assert matches


async def test_health_scan_archeo_derived_linked_via_archive(
    client: Client, vault_tmp: Path
) -> None:
    """An archeo-git derived atom listed in an archive's derived_atoms is OK."""
    arch_dir = vault_tmp / "10-episodes" / "projects" / "alpha" / "archives"
    arch_dir.mkdir(parents=True, exist_ok=True)
    derived_target = vault_tmp / "40-principles" / "work" / "linked-derived.md"
    derived_target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        derived_target,
        {
            "zone": "principles", "type": "principle", "project": "alpha",
            "scope": "work", "collective": False, "modality": "left",
            "source": "archeo-git",
            "context_origin": "[[2026-05-06-12h00-alpha-archeo-git-window]]",
            "display": "principle: linked-derived",
        },
        "# Linked derived\n",
    )
    frontmatter.write(
        arch_dir / "2026-05-06-12h00-alpha-archeo-git-window.md",
        {
            "date": "2026-05-06", "time": "12:00", "zone": "episodes",
            "kind": "project", "project": "alpha", "scope": "work",
            "collective": False, "modality": "left", "type": "archive",
            "source": "archeo-git", "milestone_kind": "window",
            "source_milestone": "window", "commit_sha": "abc",
            "friction_detected": False, "branch": "",
            "branch_base": "", "branch_base_sha": "",
            "display": "alpha — archive",
            "derived_atoms": ["[[40-principles/work/linked-derived]]"],
        },
        "# Archive\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    matches = [
        f for f in res.data.findings
        if f.category == "archeo-derived-orphan" and "linked-derived" in f.path
    ]
    assert not matches


# ---------- topology-archives-out-of-sync (15th category, v0.9.x) ----------


async def test_health_scan_detects_topology_archives_out_of_sync(
    client: Client, vault_tmp: Path
) -> None:
    """A topology that doesn't reference an existing archive is flagged."""
    arch_dir = vault_tmp / "10-episodes" / "projects" / "ghost" / "archives"
    arch_dir.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        arch_dir / "2026-05-06-12h00-ghost-archive.md",
        {
            "date": "2026-05-06", "time": "12:00", "zone": "episodes",
            "kind": "project", "project": "ghost", "scope": "work",
            "collective": False, "modality": "left", "type": "archive",
            "source": "archeo-git", "milestone_kind": "window",
            "source_milestone": "w", "commit_sha": "abc",
            "friction_detected": False, "branch": "",
            "branch_base": "", "branch_base_sha": "",
            "display": "ghost — archive", "derived_atoms": [],
        },
        "# Archive\n",
    )
    topo = vault_tmp / "99-meta" / "repo-topology" / "ghost.md"
    topo.parent.mkdir(parents=True, exist_ok=True)
    frontmatter.write(
        topo,
        {
            "date": "2026-05-06", "zone": "meta", "type": "repo-topology",
            "project": "ghost", "repo_path": "/x", "repo_remote": "",
            "content_hash": "x", "previous_topology_hash": "",
            "last_archive": "", "display": "ghost — topology",
        },
        "# Topology — ghost\n\n## Atomes dérivés\n\n_(none yet)_\n",
    )
    res = await client.call_tool("mem_health_scan", {})
    matches = [
        f for f in res.data.findings
        if f.category == "topology-archives-out-of-sync" and "ghost.md" in f.path
    ]
    assert matches
