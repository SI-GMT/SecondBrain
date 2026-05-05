"""mem_health_repair — Apply idempotent fixes to mem_health_scan findings.

Spec: core/procedures/mem-health-repair.md

POC: only the 'missing-display' category is auto-fixed in this implementation.
Other auto-fixable categories (stray-zone-md, empty-md-at-root,
missing-zone-index) require destructive ops (delete or scaffold) and need
explicit opt-in beyond this POC. orphan-atoms / malformed-frontmatter /
dangling-wikilinks / missing-archeo-hashes need human review.

Dry-run by default. Pass apply=True to write.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.health.scan import scan_vault
from memory_kit_mcp.tools._models import HealthRepairResult
from memory_kit_mcp.vault import frontmatter

_AUTO_FIXABLE_CATEGORIES = {"missing-display", "missing-zone-index-entry"}


def _derive_display(rel: Path, fm: dict[str, Any]) -> str:
    """Conventional display value derived from kind + slug + filename."""
    slug = fm.get("slug") or rel.stem
    kind = fm.get("kind", "")
    if kind == "context":
        return f"{slug} — context"
    if kind == "history":
        return f"{slug} — history"
    if kind == "archive":
        return f"{slug} — {rel.stem}"
    if kind in ("topology", "repo-topology"):
        return f"{slug} — topology"
    return str(slug)


def _fix_missing_display(vault: Path, rel_path: str) -> tuple[bool, str]:
    """Apply the missing-display fix. Returns (success, modified_path)."""
    md = vault / rel_path
    if not md.exists():
        return False, rel_path
    fm, body = frontmatter.read(md)
    if "display" in fm:
        return False, rel_path  # already fixed
    fm["display"] = _derive_display(Path(rel_path), fm)
    frontmatter.write(md, fm, body)
    return True, rel_path


def register(mcp: FastMCP) -> None:
    """Register mem_health_repair with the FastMCP instance."""

    @mcp.tool()
    def mem_health_repair(
        apply: bool = Field(
            False,
            description=(
                "If False (default), only report what would be fixed (dry-run). "
                "If True, write the fixes."
            ),
        ),
    ) -> HealthRepairResult:
        """Apply idempotent fixes to mem_health_scan findings.

        POC: only 'missing-display' is auto-fixed (derives display from kind+slug
        per the universal frontmatter convention). Other categories require
        manual review or explicit opt-in for destructive ops.

        Dry-run by default — pass apply=True to write.
        """
        config = get_config()
        vault = config.vault

        all_findings, _errors, _files_scanned = scan_vault(vault)

        fixable = [f for f in all_findings if f.category in _AUTO_FIXABLE_CATEGORIES]
        applied = 0
        skipped = 0
        modified: list[str] = []

        if apply:
            # missing-display: iterate per finding (one frontmatter rewrite each).
            for f in fixable:
                if f.category != "missing-display":
                    continue
                ok, path = _fix_missing_display(vault, f.path)
                if ok:
                    applied += 1
                    modified.append(str(vault / path))
                else:
                    skipped += 1

            # missing-zone-index-entry: regenerate the affected zone index
            # ONCE per zone (not once per atom — single rewrite covers all
            # missing entries in that zone). Atoms that gain coverage by
            # the rewrite all count as "applied".
            from memory_kit_mcp.vault.zone_index import (
                ATOM_ZONES,
                regenerate_zone_index,
            )

            zone_findings = [
                f for f in fixable if f.category == "missing-zone-index-entry"
            ]
            zones_to_regen: set[str] = set()
            for f in zone_findings:
                # f.path is vault-relative POSIX, e.g. '40-principles/work/sec/foo.md'
                first_segment = f.path.split("/", 1)[0]
                if first_segment in ATOM_ZONES:
                    zones_to_regen.add(first_segment)
            for zone in sorted(zones_to_regen):
                index_path = regenerate_zone_index(vault, zone)
                modified.append(str(index_path))
                # Each atom that was missing from this zone is now indexed
                # → count as applied. Failure to add some atoms (very rare,
                # e.g. unreadable file) would surface in next scan.
                applied += sum(
                    1 for f in zone_findings if f.path.startswith(f"{zone}/")
                )

        # Remaining = non-fixable findings + (fixable that weren't applied)
        remaining = (
            len([f for f in all_findings if f.category not in _AUTO_FIXABLE_CATEGORIES])
            + (len(fixable) - applied if apply else len(fixable))
        )

        action = "applied" if apply else "would apply (dry-run)"
        summary_lines = [
            f"## Health repair — {vault}\n",
            f"_{action.capitalize()} {applied if apply else len(fixable)} fix(es)._\n",
        ]
        if not apply and fixable:
            summary_lines.append("Re-invoke with `apply=True` to write changes.\n")
        if not fixable:
            summary_lines.append("No auto-fixable findings.\n")
        summary_lines.append(f"_Remaining (non-auto-fixable): {remaining}_")

        return HealthRepairResult(
            vault=str(vault),
            dry_run=not apply,
            fixes_applied=applied,
            fixes_skipped=skipped,
            findings_remaining=remaining,
            files_modified=modified,
            summary_md="\n".join(summary_lines),
        )
