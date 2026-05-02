"""mem_health_scan — Audit vault hygiene.

Spec: core/procedures/mem-health-scan.md
Scripted reference: scripts/mem-health-scan.py (canonical impl in the kit)

POC subset of the canonical 8 categories:
- malformed-frontmatter (severity error) — invalid YAML, breaks parsing.
- missing-display (warning, auto-fixable) — universal frontmatter convention.
- empty-md (warning, auto-fixable) — empty .md files (only frontmatter or 0 bytes).
- orphan-atom (info) — atoms in 20-knowledge/40-principles/etc with no project
  or domain tag.

Read-only — no writes. mem_health_repair applies fixes.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml
from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import HealthFinding, HealthScanResult
from memory_kit_mcp.vault import frontmatter, paths

_ATOM_ZONES = (
    paths.ZONE_KNOWLEDGE,
    paths.ZONE_PROCEDURES,
    paths.ZONE_PRINCIPLES,
    paths.ZONE_GOALS,
    paths.ZONE_PEOPLE,
    paths.ZONE_COGNITION,
)


def _scan_file(vault: Path, md_path: Path) -> list[HealthFinding]:
    rel = md_path.relative_to(vault)
    rel_str = str(rel).replace("\\", "/")
    raw = md_path.read_text(encoding="utf-8")

    findings: list[HealthFinding] = []

    # empty-md
    if not raw.strip() or len(raw.strip()) < 4:
        findings.append(
            HealthFinding(
                category="empty-md",
                severity="warning",
                path=rel_str,
                message="File is empty or contains nothing meaningful.",
                auto_fixable=False,
            )
        )
        return findings

    # malformed-frontmatter
    fm: dict[str, object] = {}
    body = raw
    try:
        fm, body = frontmatter.parse(raw)
    except (ValueError, yaml.YAMLError) as e:
        findings.append(
            HealthFinding(
                category="malformed-frontmatter",
                severity="error",
                path=rel_str,
                message=f"YAML parse error: {e}",
                auto_fixable=False,
            )
        )
        return findings  # cannot keep checking if frontmatter is broken

    # missing-display (only on files that have a frontmatter at all)
    if fm and "display" not in fm:
        findings.append(
            HealthFinding(
                category="missing-display",
                severity="warning",
                path=rel_str,
                message="Frontmatter has no `display` field (universal convention).",
                auto_fixable=True,
            )
        )

    # orphan-atom: atoms in atom zones with no project or domain tag
    parts = rel.parts
    if parts and parts[0] in _ATOM_ZONES:
        tags = fm.get("tags") or []
        has_link = False
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str) and (
                    tag.startswith("project/") or tag.startswith("domain/")
                ):
                    has_link = True
                    break
        if not has_link and "project" not in fm and "domain" not in fm:
            findings.append(
                HealthFinding(
                    category="orphan-atom",
                    severity="info",
                    path=rel_str,
                    message=(
                        "Atom is not attached to any project or domain "
                        "(no project/* or domain/* tag, no project/domain frontmatter)."
                    ),
                    auto_fixable=False,
                )
            )

    return findings


def _format_summary_md(
    vault: str,
    files_scanned: int,
    by_cat: dict[str, int],
    findings: list[HealthFinding],
) -> str:
    lines = [f"## Health scan — {vault}\n"]
    lines.append(f"_{files_scanned} file(s) scanned, {len(findings)} finding(s)._\n")
    if not findings:
        lines.append("✅ No findings — vault is clean.")
        return "\n".join(lines)

    lines.append("### By category\n")
    for cat, count in sorted(by_cat.items()):
        lines.append(f"- **{cat}**: {count}")
    lines.append("")

    # First 25 findings detail
    lines.append(f"### Findings (showing first {min(25, len(findings))})\n")
    for f in findings[:25]:
        sev_icon = {"error": "❌", "warning": "⚠️ ", "info": "ℹ️ "}.get(f.severity, "•")
        fix_hint = " _(auto-fixable)_" if f.auto_fixable else ""
        lines.append(f"- {sev_icon} `{f.path}` — [{f.category}] {f.message}{fix_hint}")
    if len(findings) > 25:
        lines.append(f"- … and {len(findings) - 25} more")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    """Register mem_health_scan with the FastMCP instance."""

    @mcp.tool()
    def mem_health_scan(
        category: str | None = Field(
            None,
            description=(
                "Restrict to one category: malformed-frontmatter | missing-display "
                "| empty-md | orphan-atom. None = all."
            ),
        ),
    ) -> HealthScanResult:
        """Audit vault hygiene. Read-only — no writes.

        POC implementation covers 4 of the 8 canonical categories:
        - malformed-frontmatter (error)
        - missing-display (warning, auto-fixable)
        - empty-md (warning)
        - orphan-atom (info)

        Use mem_health_repair to apply auto-fixes.
        """
        config = get_config()
        vault = config.vault

        all_findings: list[HealthFinding] = []
        files_scanned = 0
        for md in vault.rglob("*.md"):
            files_scanned += 1
            try:
                file_findings = _scan_file(vault, md)
            except (OSError, UnicodeDecodeError):
                continue
            if category is not None:
                file_findings = [f for f in file_findings if f.category == category]
            all_findings.extend(file_findings)

        by_cat = dict(Counter(f.category for f in all_findings))
        return HealthScanResult(
            vault=str(vault),
            files_scanned=files_scanned,
            findings_total=len(all_findings),
            by_category=by_cat,
            findings=all_findings,
            summary_md=_format_summary_md(str(vault), files_scanned, by_cat, all_findings),
        )
