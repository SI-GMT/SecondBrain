"""Vault health audit & repair, delegated to the engine via MCP.

We model two operations:

* :func:`scan_vault` — wraps ``mem_health_scan``. Read-only; returns a
  structured report grouping findings per category with severity counts.
* :func:`repair_vault` — wraps ``mem_health_repair``. Defaults to dry-run
  (no writes) so the UI can show the user what's about to change before
  they confirm. Pass ``apply=True`` only after confirmation.

Both return Pydantic models that the UI layer can render directly without
re-parsing free text. Keeping the return shape stable here means the tray
+ Tkinter dialogs can stay dumb.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field

from .mcp_client import McpError, McpResponse, McpUnavailable, call_tool

log = logging.getLogger(__name__)

SCAN_TIMEOUT = 90
REPAIR_TIMEOUT = 120

_SEVERITY_ORDER = ("error", "warn", "warning", "info")


class HealthFinding(BaseModel):
    """One row from the engine's findings list."""

    category: str
    severity: str = Field(default="info")
    path: str | None = None
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class HealthReport(BaseModel):
    """Structured outcome of a scan invocation."""

    ok: bool
    findings: list[HealthFinding] = Field(default_factory=list)
    counts_by_category: dict[str, int] = Field(default_factory=dict)
    counts_by_severity: dict[str, int] = Field(default_factory=dict)
    summary: str = ""
    error: str | None = None
    raw_text: str = ""

    def has_findings(self) -> bool:
        return any(c > 0 for c in self.counts_by_category.values())

    def render_text(self) -> str:
        if not self.ok:
            return f"Scan failed: {self.error or 'unknown error'}"
        if not self.has_findings():
            return "Vault is clean — no findings."
        lines = [self.summary or "Findings:"]
        for category, count in sorted(self.counts_by_category.items()):
            if count:
                lines.append(f"  {category}: {count}")
        return "\n".join(lines)


class HealthRepairReport(BaseModel):
    """Structured outcome of a repair invocation."""

    ok: bool
    applied: bool
    fixed_count: int = 0
    skipped_count: int = 0
    fixed_paths: list[str] = Field(default_factory=list)
    skipped_paths: list[str] = Field(default_factory=list)
    summary: str = ""
    error: str | None = None
    raw_text: str = ""

    def render_text(self) -> str:
        if not self.ok:
            return f"Repair failed: {self.error or 'unknown error'}"
        mode = "applied" if self.applied else "dry-run"
        return (
            f"Repair {mode}: {self.fixed_count} fixed, "
            f"{self.skipped_count} skipped.\n{self.summary}"
        )


def _findings_from_payload(payload: dict[str, Any]) -> list[HealthFinding]:
    """Map the engine's findings array into HealthFinding objects.

    The engine schema groups findings under per-category keys; we flatten
    into a single list while preserving the category as a column.
    """
    findings: list[HealthFinding] = []
    raw = payload.get("findings")
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            findings.append(
                HealthFinding(
                    category=str(entry.get("category", "unknown")),
                    severity=str(entry.get("severity", "info")),
                    path=entry.get("path"),
                    message=str(entry.get("message", "")),
                    details={
                        k: v
                        for k, v in entry.items()
                        if k not in {"category", "severity", "path", "message"}
                    },
                )
            )
        return findings

    by_category = payload.get("findings_by_category")
    if isinstance(by_category, dict):
        for category, entries in by_category.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                findings.append(
                    HealthFinding(
                        category=str(category),
                        severity=str(entry.get("severity", "info")),
                        path=entry.get("path"),
                        message=str(entry.get("message", "")),
                        details={
                            k: v
                            for k, v in entry.items()
                            if k not in {"severity", "path", "message"}
                        },
                    )
                )
    return findings


def _summarise(findings: list[HealthFinding]) -> tuple[dict[str, int], dict[str, int], str]:
    by_cat = Counter(f.category for f in findings)
    by_sev = Counter(f.severity.lower() for f in findings)
    if not findings:
        return dict(by_cat), dict(by_sev), "Vault is clean."
    severities_in_order = [
        f"{by_sev.get(s, 0)} {s}" for s in _SEVERITY_ORDER if by_sev.get(s)
    ]
    summary = f"{len(findings)} finding(s) — " + ", ".join(severities_in_order)
    return dict(by_cat), dict(by_sev), summary


def _engine_unavailable(report_cls):  # noqa: ANN001 — local helper
    if report_cls is HealthReport:
        return HealthReport(
            ok=False,
            error="Memory Kit engine is not installed.",
            summary="Install the kit then retry.",
        )
    return HealthRepairReport(
        ok=False,
        applied=False,
        error="Memory Kit engine is not installed.",
    )


def scan_vault() -> HealthReport:
    response = call_tool("mem_health_scan", {}, timeout=SCAN_TIMEOUT)

    if isinstance(response, McpUnavailable):
        return _engine_unavailable(HealthReport)
    if isinstance(response, McpError):
        return HealthReport(ok=False, error=response.message, raw_text=response.detail or "")

    assert isinstance(response, McpResponse)
    payload = response.structured or {}
    findings = _findings_from_payload(payload)
    by_cat, by_sev, summary = _summarise(findings)
    return HealthReport(
        ok=True,
        findings=findings,
        counts_by_category=by_cat,
        counts_by_severity=by_sev,
        summary=summary,
        raw_text=response.text,
    )


def repair_vault(*, apply: bool = False) -> HealthRepairReport:
    response = call_tool(
        "mem_health_repair",
        {"apply": apply},
        timeout=REPAIR_TIMEOUT,
    )

    if isinstance(response, McpUnavailable):
        return _engine_unavailable(HealthRepairReport)
    if isinstance(response, McpError):
        return HealthRepairReport(
            ok=False,
            applied=apply,
            error=response.message,
            raw_text=response.detail or "",
        )

    assert isinstance(response, McpResponse)
    payload = response.structured or {}
    fixed_paths = list(payload.get("fixed_paths", []) or [])
    skipped_paths = list(payload.get("skipped_paths", []) or [])
    summary = str(payload.get("summary", ""))
    return HealthRepairReport(
        ok=True,
        applied=bool(payload.get("applied", apply)),
        fixed_count=int(payload.get("fixed_count", len(fixed_paths))),
        skipped_count=int(payload.get("skipped_count", len(skipped_paths))),
        fixed_paths=fixed_paths,
        skipped_paths=skipped_paths,
        summary=summary,
        raw_text=response.text,
    )
