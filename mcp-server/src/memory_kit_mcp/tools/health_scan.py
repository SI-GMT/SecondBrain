"""mem_health_scan — Audit vault hygiene + kit-repo spec drift + skill descriptions.

Spec: core/procedures/mem-health-scan.md
Scripted reference: scripts/mem-health-scan.py (12 vault categories)

Thin wrapper over the shared library memory_kit_mcp.health.scan, which
implements the canonical 15-category audit:

- malformed-frontmatter         (error)
- stray-zone-md                 (warning)
- empty-md-at-root              (warning)
- missing-zone-index            (warning)
- missing-display               (info, auto-fixable)
- dangling-wikilinks            (info)
- orphan-atoms                  (warning)
- missing-archeo-hashes         (warning)
- mcp-tool-spec-drift           (info)    — mcp-only; needs kit_repo + sync.json.
- skill-description-too-long    (warning) — mcp-only; needs kit_repo + adapters/.
- missing-zone-index-entry      (warning) — mcp-only; auto-fixable.
- missing-universal-frontmatter (warning) — v0.9.x; scope/collective/modality.
- missing-archeo-context-origin (warning) — v0.9.x; archeo-* atoms.
- archeo-derived-orphan         (warning) — v0.9.x; broken bidirectional link.
- topology-archives-out-of-sync (info)    — v0.9.x; topology vs archives drift.

Read-only — no writes. mem_health_repair applies fixes.
"""

from __future__ import annotations

from collections import Counter

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import HealthFinding, HealthScanResult

# Lazy-imported inside the tool body — see the comment in health_repair.py for
# the full rationale (circular import with ``health.__init__`` when an
# external in-process consumer reaches into ``health.scan`` directly).


def _format_summary_md(
    vault: str,
    files_scanned: int,
    by_cat: dict[str, int],
    findings: list[HealthFinding],
) -> str:
    from memory_kit_mcp.health.scan import CATEGORIES  # noqa: F401 — used in caller

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
                "orphan-atoms | missing-archeo-hashes | mcp-tool-spec-drift | "
                "skill-description-too-long | missing-zone-index-entry | "
                "missing-universal-frontmatter | missing-archeo-context-origin | "
                "archeo-derived-orphan | topology-archives-out-of-sync. "
                "None = all."
            ),
        ),
    ) -> HealthScanResult:
        """Audit vault hygiene + kit-repo spec drift + adapter SKILL.md description lengths. Read-only — no writes.

        Covers the 15 canonical categories defined in core/procedures/mem-health-scan.md.
        Use mem_health_repair to apply auto-fixes (currently: missing-display +
        missing-zone-index-entry; stray-zone-md and empty-md-at-root are auto-fixable
        in principle but the repair tool requires opt-in for delete operations).
        """
        from memory_kit_mcp.health.scan import scan_vault

        config = get_config()
        vault = config.vault

        findings, _scan_errors, files_scanned = scan_vault(
            vault, only_filter=category, kit_repo=config.kit_repo
        )
        by_cat = dict(Counter(f.category for f in findings))

        return HealthScanResult(
            vault=str(vault),
            files_scanned=files_scanned,
            findings_total=len(findings),
            by_category=by_cat,
            findings=findings,
            summary_md=_format_summary_md(str(vault), files_scanned, by_cat, findings),
        )
