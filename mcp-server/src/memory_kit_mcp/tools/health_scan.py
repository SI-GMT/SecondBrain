"""mem_health_scan — Audit vault hygiene.

Spec: core/procedures/mem-health-scan.md
Scripted reference: scripts/mem-health-scan.py (versioned standalone CLI)

Thin wrapper over the shared library memory_kit_mcp.health.scan, which
implements the canonical 8-category audit:

- malformed-frontmatter  (error)
- stray-zone-md          (warning)
- empty-md-at-root       (warning)
- missing-zone-index     (warning)
- missing-display        (info, auto-fixable)
- dangling-wikilinks     (info)
- orphan-atoms           (warning)
- missing-archeo-hashes  (warning)

Read-only — no writes. mem_health_repair applies fixes.
"""

from __future__ import annotations

from collections import Counter

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.health.scan import CATEGORIES, scan_vault
from memory_kit_mcp.tools._models import HealthFinding, HealthScanResult


def _format_summary_md(
    vault: str,
    files_scanned: int,
    by_cat: dict[str, int],
    findings: list[HealthFinding],
) -> str:
    lines = [f"## Health scan — {vault}\n"]
    lines.append(f"_{files_scanned} file(s) scanned, {len(findings)} finding(s)._\n")
    if not findings:
        lines.append("No findings — vault is clean.")
        return "\n".join(lines)

    lines.append("### By category\n")
    for cat in CATEGORIES:
        count = by_cat.get(cat, 0)
        if count:
            lines.append(f"- **{cat}**: {count}")
    lines.append("")

    lines.append(f"### Findings (showing first {min(25, len(findings))})\n")
    for f in findings[:25]:
        sev_marker = {"error": "[ERROR]", "warning": "[WARN] ", "info": "[INFO] "}.get(f.severity, "•")
        fix_hint = " _(auto-fixable)_" if f.auto_fixable else ""
        lines.append(f"- {sev_marker} `{f.path}` — [{f.category}] {f.message}{fix_hint}")
    if len(findings) > 25:
        lines.append(f"- ... and {len(findings) - 25} more")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    """Register mem_health_scan with the FastMCP instance."""

    @mcp.tool()
    def mem_health_scan(
        category: str | None = Field(
            None,
            description=(
                "Restrict to one category. One of: "
                "malformed-frontmatter | stray-zone-md | empty-md-at-root | "
                "missing-zone-index | missing-display | dangling-wikilinks | "
                "orphan-atoms | missing-archeo-hashes. None = all."
            ),
        ),
    ) -> HealthScanResult:
        """Audit vault hygiene. Read-only — no writes.

        Covers the 8 canonical categories defined in core/procedures/mem-health-scan.md.
        Use mem_health_repair to apply auto-fixes (currently: missing-display only;
        stray-zone-md and empty-md-at-root are auto-fixable in principle but the
        repair tool requires opt-in for delete operations).
        """
        config = get_config()
        vault = config.vault

        findings, _scan_errors, files_scanned = scan_vault(vault, only_filter=category)
        by_cat = dict(Counter(f.category for f in findings))

        return HealthScanResult(
            vault=str(vault),
            files_scanned=files_scanned,
            findings_total=len(findings),
            by_category=by_cat,
            findings=findings,
            summary_md=_format_summary_md(str(vault), files_scanned, by_cat, findings),
        )
