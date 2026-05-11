"""Vault health audit & repair — in-process call into the bundled engine.

Direct function calls into ``memory_kit_mcp`` (no MCP stdio, no
subprocess). Latency is ~10-50 ms for a typical vault scan instead of
the 1-2 s cold-start handshake the V1 stdio bridge used to pay.

Auto-fix coverage (desktop-side, mirrors the kit's ``auto_fixable``
flags):

* ``missing-display``         — add the ``display:`` frontmatter key.
* ``missing-zone-index-entry`` — regenerate the affected zone index.
* ``missing-zone-index``      — create the empty zone hub file.
* ``stray-zone-md``           — delete the empty zone-named file at root.
* ``empty-md-at-root``        — delete the empty root file.

The last two operations delete files and are gated behind an explicit
``apply_destructive=True`` flag so the UI can require a second
confirmation before invoking them.

Other categories the scanner reports (``missing-universal-frontmatter``,
``archeo-archive-incomplete-frontmatter``, ``topology-archives-out-of-sync``,
``orphan-atoms``, ``dangling-wikilinks``, …) require editorial judgment
or non-trivial content edits — they are reported but not auto-fixed.
The :class:`HealthRepairReport` surfaces them as
``manual_review_count`` so the user understands why ``Repair`` didn't
fix everything the ``Scan`` flagged.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .config import load_kit_config

log = logging.getLogger(__name__)

_SEVERITY_ORDER = ("error", "warn", "warning", "info")

# Categories the desktop auto-fixes. Kept aligned with the kit's
# ``auto_fixable=True`` annotations in ``memory_kit_mcp.health.scan``.
SAFE_CATEGORIES = frozenset({
    "missing-display",
    "missing-zone-index-entry",
    "missing-zone-index",
})

DESTRUCTIVE_CATEGORIES = frozenset({
    "stray-zone-md",
    "empty-md-at-root",
})

ALL_AUTO_FIXABLE = SAFE_CATEGORIES | DESTRUCTIVE_CATEGORIES


class HealthFinding(BaseModel):
    category: str
    severity: str = Field(default="info")
    path: str | None = None
    message: str = ""
    auto_fixable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class HealthReport(BaseModel):
    ok: bool
    findings: list[HealthFinding] = Field(default_factory=list)
    counts_by_category: dict[str, int] = Field(default_factory=dict)
    counts_by_severity: dict[str, int] = Field(default_factory=dict)
    files_scanned: int = 0
    scan_errors: list[tuple[str, str]] = Field(default_factory=list)
    summary: str = ""
    error: str | None = None

    def has_findings(self) -> bool:
        return bool(self.findings)

    def render_text(self) -> str:
        if not self.ok:
            return f"Scan failed: {self.error or 'unknown error'}"
        if not self.findings:
            return f"Vault is clean ({self.files_scanned} files scanned)."
        lines = [self.summary or "Findings:"]
        for category, count in sorted(self.counts_by_category.items()):
            if count:
                lines.append(f"  {category}: {count}")
        return "\n".join(lines)


class HealthRepairReport(BaseModel):
    ok: bool
    applied: bool
    destructive_applied: bool = False
    findings_before: int = 0
    findings_after: int = 0
    fixed_count: int = 0
    skipped_count: int = 0
    manual_review_count: int = 0
    fixed_by_category: dict[str, int] = Field(default_factory=dict)
    files_modified: list[str] = Field(default_factory=list)
    files_deleted: list[str] = Field(default_factory=list)
    counts_before: dict[str, int] = Field(default_factory=dict)
    counts_after: dict[str, int] = Field(default_factory=dict)
    summary: str = ""
    error: str | None = None

    def fixed_total(self) -> int:
        return self.fixed_count

    def render_text(self) -> str:
        if not self.ok:
            return f"Repair failed: {self.error or 'unknown error'}"
        mode = "applied" if self.applied else "dry-run"
        lines = [
            f"Repair {mode}: {self.fixed_count} fixed, "
            f"{self.skipped_count} skipped, "
            f"{self.manual_review_count} manual review."
        ]
        if self.applied:
            lines.append(
                f"Findings: {self.findings_before} → {self.findings_after}."
            )
        return "\n".join(lines)


def _resolve_vault(vault_override: Path | None = None) -> tuple[Path | None, str | None]:
    if vault_override is not None:
        return (vault_override, None) if vault_override.is_dir() else (
            None,
            f"vault path does not exist: {vault_override}",
        )
    kit = load_kit_config()
    if kit is None:
        return None, "memory-kit config not found at ~/.memory-kit/config.json"
    if not kit.vault_exists:
        return None, f"configured vault path does not exist: {kit.vault}"
    return kit.vault, None


def _summarise(findings: list[HealthFinding]) -> tuple[dict[str, int], dict[str, int], str]:
    by_cat = Counter(f.category for f in findings)
    by_sev = Counter(f.severity.lower() for f in findings)
    if not findings:
        return dict(by_cat), dict(by_sev), "Vault is clean."
    severity_chunks = [
        f"{by_sev.get(s, 0)} {s}" for s in _SEVERITY_ORDER if by_sev.get(s)
    ]
    summary = f"{len(findings)} finding(s) — " + ", ".join(severity_chunks)
    return dict(by_cat), dict(by_sev), summary


def _engine_findings_to_models(raw_findings) -> list[HealthFinding]:
    out: list[HealthFinding] = []
    for f in raw_findings:
        out.append(
            HealthFinding(
                category=getattr(f, "category", "unknown"),
                severity=getattr(f, "severity", "info"),
                path=getattr(f, "path", None),
                message=getattr(f, "message", ""),
                auto_fixable=bool(getattr(f, "auto_fixable", False)),
            )
        )
    return out


def scan_vault(vault_override: Path | None = None) -> HealthReport:
    vault, err = _resolve_vault(vault_override)
    if vault is None:
        return HealthReport(ok=False, error=err)

    try:
        from memory_kit_mcp.health.scan import scan_vault as engine_scan
    except ImportError as exc:
        return HealthReport(ok=False, error=f"bundled engine missing: {exc}")

    try:
        engine_findings, scan_errors, files_scanned = engine_scan(vault)
    except Exception as exc:
        log.exception("engine scan_vault raised: %s", exc)
        return HealthReport(ok=False, error=f"engine raised: {exc}")

    findings = _engine_findings_to_models(engine_findings)
    by_cat, by_sev, summary = _summarise(findings)
    return HealthReport(
        ok=True,
        findings=findings,
        counts_by_category=by_cat,
        counts_by_severity=by_sev,
        files_scanned=files_scanned,
        scan_errors=list(scan_errors),
        summary=summary,
    )


def _safe_unlink(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except OSError as exc:
        log.warning("failed to delete %s: %s", path, exc)
        return False


_EMPTY_ZONE_INDEX_TEMPLATE = """---
display: {zone} — index
kind: zone-index
zone: {zone}
---

# {zone}

(empty hub — populated on demand by atom additions)
"""


def _create_zone_hub(vault: Path, zone_dir: str) -> Path | None:
    """Create a minimal ``{zone}/index.md`` if missing."""
    zone = zone_dir.rstrip("/").split("/")[-1]
    target = vault / zone / "index.md"
    if target.exists():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        _EMPTY_ZONE_INDEX_TEMPLATE.format(zone=zone),
        encoding="utf-8",
        newline="\n",
    )
    return target


def repair_vault(
    *,
    apply: bool = False,
    apply_destructive: bool = False,
    vault_override: Path | None = None,
) -> HealthRepairReport:
    """Apply auto-fixes to the findings.

    Args:
        apply: when False (default) just enumerate what would be fixed
            without writing anything.
        apply_destructive: even with ``apply=True``, destructive
            operations (file deletion) only run if this is also True.
            Requires a second confirmation in the UI.
        vault_override: optional vault path; defaults to the configured
            one.
    """
    vault, err = _resolve_vault(vault_override)
    if vault is None:
        return HealthRepairReport(ok=False, applied=False, error=err)

    try:
        from memory_kit_mcp.health.scan import scan_vault as engine_scan
        from memory_kit_mcp.tools.health_repair import (  # type: ignore[attr-defined]
            _fix_missing_display,
        )
    except ImportError as exc:
        return HealthRepairReport(
            ok=False, applied=False, error=f"bundled engine missing: {exc}"
        )

    try:
        before_engine, _errors, _files_scanned = engine_scan(vault)
    except Exception as exc:
        log.exception("engine scan during repair raised: %s", exc)
        return HealthRepairReport(
            ok=False, applied=apply, error=f"scan raised: {exc}"
        )

    before = _engine_findings_to_models(before_engine)
    counts_before, _, _ = _summarise(before)
    findings_before = len(before)

    fixed_by_cat: Counter[str] = Counter()
    skipped = 0
    modified: list[str] = []
    deleted: list[str] = []
    destructive_applied = False

    safe_fixable = [f for f in before if f.category in SAFE_CATEGORIES]
    destructive_fixable = [f for f in before if f.category in DESTRUCTIVE_CATEGORIES]
    manual_review = [f for f in before if f.category not in ALL_AUTO_FIXABLE]

    if apply:
        # 1. missing-display — one rewrite per file.
        for f in safe_fixable:
            if f.category != "missing-display" or not f.path:
                continue
            try:
                ok, path = _fix_missing_display(vault, f.path)
            except Exception as exc:
                log.warning("missing-display fix raised for %s: %s", f.path, exc)
                skipped += 1
                continue
            if ok:
                fixed_by_cat["missing-display"] += 1
                modified.append(str(vault / path))
            else:
                skipped += 1

        # 2. missing-zone-index-entry — regen affected zones once each.
        try:
            from memory_kit_mcp.vault.zone_index import (
                ATOM_ZONES,
                regenerate_zone_index,
            )
        except ImportError:
            ATOM_ZONES = set()  # type: ignore[assignment]
            regenerate_zone_index = None  # type: ignore[assignment]

        if regenerate_zone_index is not None:
            zone_findings = [
                f for f in safe_fixable
                if f.category == "missing-zone-index-entry" and f.path
            ]
            zones_to_regen: set[str] = set()
            for f in zone_findings:
                first_segment = (f.path or "").split("/", 1)[0]
                if first_segment in ATOM_ZONES:
                    zones_to_regen.add(first_segment)
            for zone in sorted(zones_to_regen):
                try:
                    index_path = regenerate_zone_index(vault, zone)
                except Exception as exc:
                    log.warning("regen zone %s raised: %s", zone, exc)
                    continue
                modified.append(str(index_path))
                fixed_by_cat["missing-zone-index-entry"] += sum(
                    1 for f in zone_findings
                    if (f.path or "").startswith(f"{zone}/")
                )

        # 3. missing-zone-index — create empty hubs.
        for f in safe_fixable:
            if f.category != "missing-zone-index" or not f.path:
                continue
            try:
                created = _create_zone_hub(vault, f.path)
            except Exception as exc:
                log.warning("zone-hub creation raised for %s: %s", f.path, exc)
                skipped += 1
                continue
            if created is not None:
                fixed_by_cat["missing-zone-index"] += 1
                modified.append(str(created))
            else:
                skipped += 1

        # 4. Destructive: stray-zone-md + empty-md-at-root.
        if apply_destructive and destructive_fixable:
            destructive_applied = True
            for f in destructive_fixable:
                if not f.path:
                    skipped += 1
                    continue
                target = vault / f.path
                if not target.is_file():
                    skipped += 1
                    continue
                if _safe_unlink(target):
                    fixed_by_cat[f.category] += 1
                    deleted.append(str(target))
                else:
                    skipped += 1

    # Re-scan after apply (or compute the planned-fix count for dry-run).
    if apply:
        try:
            after_engine, _e2, _f2 = engine_scan(vault)
        except Exception as exc:
            log.warning("post-apply scan raised: %s", exc)
            after_engine = before_engine
        after = _engine_findings_to_models(after_engine)
    else:
        after = before  # dry-run leaves the vault as-is

    counts_after, _, _ = _summarise(after)
    fixed_count = sum(fixed_by_cat.values())
    if not apply:
        # Dry-run report: enumerate what *would* be fixed.
        fixed_count = len([f for f in safe_fixable]) + (
            len(destructive_fixable) if apply_destructive else 0
        )

    summary_lines = []
    if apply:
        delta = findings_before - len(after)
        summary_lines.append(
            f"Applied {fixed_count} fix(es). Findings went from "
            f"{findings_before} to {len(after)} (Δ {delta:+d})."
        )
    elif safe_fixable or (apply_destructive and destructive_fixable):
        summary_lines.append(
            f"Dry-run: {fixed_count} fix(es) ready. "
            "Re-invoke with apply=True to write."
        )
    else:
        summary_lines.append("No auto-fixable findings.")

    if manual_review:
        cats = ", ".join(
            f"{c}: {n}"
            for c, n in Counter(f.category for f in manual_review).most_common()
        )
        summary_lines.append(f"Manual review still required — {cats}")

    return HealthRepairReport(
        ok=True,
        applied=apply,
        destructive_applied=destructive_applied,
        findings_before=findings_before,
        findings_after=len(after),
        fixed_count=fixed_count,
        skipped_count=skipped,
        manual_review_count=len(manual_review),
        fixed_by_category=dict(fixed_by_cat),
        files_modified=modified,
        files_deleted=deleted,
        counts_before=counts_before,
        counts_after=counts_after,
        summary="\n".join(summary_lines),
    )
