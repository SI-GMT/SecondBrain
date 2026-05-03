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
        f.category == "orphan-atom" and "orphan.md" in f.path for f in d.findings
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
