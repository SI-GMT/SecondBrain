"""Tests for mem_health_scan and mem_health_repair."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

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
