"""Vault health audit & repair — in-process call into the bundled engine.

Direct function calls into ``memory_kit_mcp`` (no MCP stdio, no
subprocess). Latency is ~10-50 ms for a typical vault scan instead of
the 1-2 s cold-start handshake the V1 stdio bridge used to pay.

We deliberately depend on internal kit symbols
(``memory_kit_mcp.health.scan.scan_vault`` and the private
``_fix_missing_display`` from the repair tool) because the kit version
is **bundled** with the desktop app — we ship both together, so there
is no API stability boundary to respect between them. When the kit
later promotes a public ``memory_kit_mcp.health.repair.repair_vault``
function, switch to that without changing this module's external shape.

Failure modes are surfaced as Pydantic models, not exceptions: the UI
expects every call to return a structured report it can render
verbatim.
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
    fixed_count: int = 0
    skipped_count: int = 0
    remaining_count: int = 0
    files_modified: list[str] = Field(default_factory=list)
    summary: str = ""
    error: str | None = None

    def render_text(self) -> str:
        if not self.ok:
            return f"Repair failed: {self.error or 'unknown error'}"
        mode = "applied" if self.applied else "dry-run"
        return (
            f"Repair {mode}: {self.fixed_count} fixed, "
            f"{self.skipped_count} skipped, {self.remaining_count} remaining."
        )


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


def scan_vault(vault_override: Path | None = None) -> HealthReport:
    """Run the full vault audit. Direct call into the bundled engine."""
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

    findings: list[HealthFinding] = []
    for f in engine_findings:
        finding_dict = {
            "category": getattr(f, "category", "unknown"),
            "severity": getattr(f, "severity", "info"),
            "path": getattr(f, "path", None),
            "message": getattr(f, "message", ""),
            "auto_fixable": bool(getattr(f, "auto_fixable", False)),
        }
        findings.append(HealthFinding(**finding_dict))

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


def repair_vault(*, apply: bool = False, vault_override: Path | None = None) -> HealthRepairReport:
    """Apply auto-fixes to the findings. Default is dry-run.

    Currently auto-fixes only ``missing-display`` and
    ``missing-zone-index-entry`` — matches the engine's policy. Other
    categories require manual review.
    """
    vault, err = _resolve_vault(vault_override)
    if vault is None:
        return HealthRepairReport(ok=False, applied=False, error=err)

    try:
        from memory_kit_mcp.health.scan import scan_vault as engine_scan
        from memory_kit_mcp.tools.health_repair import (  # type: ignore[attr-defined]
            _AUTO_FIXABLE_CATEGORIES,
            _fix_missing_display,
        )
    except ImportError as exc:
        return HealthRepairReport(
            ok=False, applied=False, error=f"bundled engine missing: {exc}"
        )

    try:
        all_findings, _errors, _files_scanned = engine_scan(vault)
    except Exception as exc:
        log.exception("engine scan_vault during repair raised: %s", exc)
        return HealthRepairReport(
            ok=False, applied=apply, error=f"scan raised: {exc}"
        )

    fixable = [f for f in all_findings if f.category in _AUTO_FIXABLE_CATEGORIES]
    applied_count = 0
    skipped_count = 0
    modified: list[str] = []

    if apply:
        # missing-display — one fix per finding
        for f in fixable:
            if f.category != "missing-display":
                continue
            try:
                ok, path = _fix_missing_display(vault, f.path)
            except Exception as exc:
                log.warning("missing-display fix raised for %s: %s", f.path, exc)
                skipped_count += 1
                continue
            if ok:
                applied_count += 1
                modified.append(str(vault / path))
            else:
                skipped_count += 1

        # missing-zone-index-entry — regenerate per affected zone, once
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
                f for f in fixable if f.category == "missing-zone-index-entry"
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
                applied_count += sum(
                    1 for f in zone_findings if (f.path or "").startswith(f"{zone}/")
                )

    remaining = (
        len([f for f in all_findings if f.category not in _AUTO_FIXABLE_CATEGORIES])
        + (len(fixable) - applied_count if apply else len(fixable))
    )

    if apply:
        summary = f"Applied {applied_count} fix(es); {remaining} remaining (manual review)."
    elif fixable:
        summary = (
            f"Dry-run: {len(fixable)} fix(es) ready. "
            "Re-invoke with apply=True to write."
        )
    else:
        summary = "No auto-fixable findings."

    return HealthRepairReport(
        ok=True,
        applied=apply,
        fixed_count=applied_count if apply else len(fixable),
        skipped_count=skipped_count,
        remaining_count=remaining,
        files_modified=modified,
        summary=summary,
    )
