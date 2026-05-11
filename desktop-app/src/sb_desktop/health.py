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

# Categories the desktop auto-fixes. The first three mirror the kit's
# ``auto_fixable=True`` annotations. The next two are kit-conservative
# (``auto_fixable=False`` upstream) but deterministic enough that we
# wire them here — see the per-category helper docstrings below.
SAFE_CATEGORIES = frozenset({
    "missing-display",
    "missing-zone-index-entry",
    "missing-zone-index",
    "missing-universal-frontmatter",
    "topology-archives-out-of-sync",
})

DESTRUCTIVE_CATEGORIES = frozenset({
    "stray-zone-md",
    "empty-md-at-root",
})

ALL_AUTO_FIXABLE = SAFE_CATEGORIES | DESTRUCTIVE_CATEGORIES

# ``archeo-archive-incomplete-frontmatter`` requires re-running
# ``mem-archeo-git`` to repopulate the MUST keys from git history, so
# we surface it as manual-review with a recommended workflow rather
# than attempting a half-correct in-place rewrite.
WORKFLOW_HINTS: dict[str, str] = {
    "archeo-archive-incomplete-frontmatter": (
        "Re-run `mem-archeo-git` against the source project to repopulate the "
        "archeo MUST keys (branch / branch_base / commit_sha / milestone_kind / …). "
        "Editing the frontmatter by hand is error-prone and the archeo planner "
        "is the authoritative source of those values."
    ),
}


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
    workflow_hints: dict[str, str] = Field(default_factory=dict)
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


# ---------------------------------------------------------------------------
# missing-universal-frontmatter helpers
# ---------------------------------------------------------------------------
#
# The kit's scanner flags any atom outside ``00-inbox`` / ``99-meta`` that
# lacks one of the three universal MUST fields: ``scope``, ``collective``,
# ``modality``. Upstream the category is ``auto_fixable=False`` because the
# semantic fields are nominally editorial.
#
# In practice, two of the three are mechanically derivable from the file
# path and the kit's ``default_scope`` setting, and the third has a safe
# default. The heuristics below fill *only* the missing keys (never
# overwrite a value the user already chose).

_MODALITY_BY_PATH_SEGMENT: dict[str, str] = {
    "20-knowledge": "knowledge",
    "40-principles": "principle",
    "50-goals": "goal",
    "60-people": "person",
    "70-resources": "resource",
    "99-meta": "meta",
}


def _modality_from_path(rel: str) -> str | None:
    """Best-effort modality inference from the vault-relative POSIX path."""
    parts = rel.split("/")
    if not parts:
        return None
    first = parts[0]
    if first in _MODALITY_BY_PATH_SEGMENT:
        return _MODALITY_BY_PATH_SEGMENT[first]
    if first == "10-episodes":
        # 10-episodes/projects/{slug}/{archives|context.md|history.md|topology.md}
        # 10-episodes/domains/{slug}/{archives|context.md|history.md}
        if len(parts) >= 4 and parts[3] == "archives":
            return "archive"
        if len(parts) >= 4 and parts[3].startswith("context"):
            return "context"
        if len(parts) >= 4 and parts[3].startswith("history"):
            return "history"
        if len(parts) >= 4 and parts[3].startswith("topology"):
            return "topology"
        return "episode"
    return None


def _scope_from_path(rel: str, default_scope: str) -> str:
    """Detect ``/work/`` / ``/perso/`` markers, fall back to default_scope."""
    segments = set(rel.split("/"))
    if "work" in segments:
        return "work"
    if "perso" in segments:
        return "perso"
    if default_scope in {"work", "perso", "mixed"}:
        return default_scope
    return "work"  # the kit's own default


def _kit_default_scope() -> str:
    """Read ``default_scope`` from the kit config; safe fallback."""
    kit = load_kit_config()
    if kit is None:
        return "work"
    return str(kit.extras.get("default_scope", "work"))


def _fix_universal_frontmatter(
    vault: Path, rel: str, default_scope: str
) -> tuple[bool, str | None]:
    """Fill the missing universal MUST fields in place.

    Returns ``(ok, path_str)``. ``ok=False`` means the file disappeared,
    was unreadable, or already had all three fields (shouldn't happen
    given the scanner reports it, but defensive).
    """
    try:
        from memory_kit_mcp.vault import frontmatter
    except ImportError:
        return False, None

    target = vault / rel
    if not target.is_file():
        return False, None
    try:
        fm, body = frontmatter.read(target)
    except Exception as exc:
        log.warning("universal-frontmatter read failed for %s: %s", rel, exc)
        return False, None

    changed = False
    if "modality" not in fm:
        modality = _modality_from_path(rel)
        if modality:
            fm["modality"] = modality
            changed = True
    if "scope" not in fm:
        fm["scope"] = _scope_from_path(rel, default_scope)
        changed = True
    if "collective" not in fm:
        # Safe default: personal until promoted. Promoting later is a
        # cheap manual flip (or a future bulk action in this UI).
        fm["collective"] = False
        changed = True

    if not changed:
        return False, None

    try:
        frontmatter.write(target, fm, body)
    except Exception as exc:
        log.warning("universal-frontmatter write failed for %s: %s", rel, exc)
        return False, None
    return True, rel


# ---------------------------------------------------------------------------
# topology-archives-out-of-sync helper
# ---------------------------------------------------------------------------
#
# The scanner flags ``99-meta/repo-topology/{slug}.md`` topology atoms that
# don't reference every archive in ``10-episodes/projects/{slug}/archives/``
# via wikilink. The fix is deterministic: list the archives, append the
# missing wikilinks to the body's "Atomes dérivés des phases archeo"
# section (creating it if absent).

_ARCHEO_SECTION_TITLES = (
    "## Atomes dérivés des phases archeo",
    "## Atomes dérivés",
    "## Archives",
)


def _fix_topology_archives(vault: Path, rel: str) -> tuple[bool, str | None]:
    """Append the missing archive wikilinks to the topology body."""
    try:
        from memory_kit_mcp.vault import frontmatter
        from memory_kit_mcp.vault.wikilinks import WIKILINK_RE, strip_code
    except ImportError:
        return False, None

    target = vault / rel
    if not target.is_file():
        return False, None
    try:
        fm, body = frontmatter.read(target)
    except Exception as exc:
        log.warning("topology read failed for %s: %s", rel, exc)
        return False, None
    if fm.get("type") != "repo-topology":
        return False, None
    slug = fm.get("project")
    if not slug:
        return False, None

    arch_dir = vault / "10-episodes" / "projects" / slug / "archives"
    if not arch_dir.is_dir():
        return False, None

    archives = sorted(p.stem for p in arch_dir.glob("*.md") if p.is_file())
    if not archives:
        return False, None

    existing_targets: set[str] = set()
    for m in WIKILINK_RE.finditer(strip_code(body)):
        existing_targets.add(m.group(1).strip().split("/")[-1])

    missing = [a for a in archives if a not in existing_targets]
    if not missing:
        return False, None

    # Insert at the existing "Atomes dérivés…" section if present;
    # otherwise append a fresh section at the end.
    section_index = -1
    for title in _ARCHEO_SECTION_TITLES:
        idx = body.find(title)
        if idx >= 0:
            section_index = idx
            break

    addition = "\n".join(f"- [[{a}]]" for a in missing)

    if section_index >= 0:
        # Insert after the section header line.
        line_end = body.find("\n", section_index)
        if line_end < 0:
            new_body = body + "\n" + addition + "\n"
        else:
            new_body = (
                body[: line_end + 1]
                + addition
                + "\n"
                + body[line_end + 1 :]
            )
    else:
        new_body = (
            body.rstrip("\n")
            + "\n\n## Atomes dérivés des phases archeo\n\n"
            + addition
            + "\n"
        )

    try:
        frontmatter.write(target, fm, new_body)
    except Exception as exc:
        log.warning("topology write failed for %s: %s", rel, exc)
        return False, None
    return True, rel


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

        # 4. missing-universal-frontmatter — fill scope/collective/modality.
        default_scope = _kit_default_scope()
        for f in safe_fixable:
            if f.category != "missing-universal-frontmatter" or not f.path:
                continue
            try:
                ok, rel = _fix_universal_frontmatter(vault, f.path, default_scope)
            except Exception as exc:
                log.warning("universal-frontmatter fix raised for %s: %s", f.path, exc)
                skipped += 1
                continue
            if ok and rel:
                fixed_by_cat["missing-universal-frontmatter"] += 1
                modified.append(str(vault / rel))
            else:
                skipped += 1

        # 5. topology-archives-out-of-sync — append missing wikilinks.
        for f in safe_fixable:
            if f.category != "topology-archives-out-of-sync" or not f.path:
                continue
            try:
                ok, rel = _fix_topology_archives(vault, f.path)
            except Exception as exc:
                log.warning("topology fix raised for %s: %s", f.path, exc)
                skipped += 1
                continue
            if ok and rel:
                fixed_by_cat["topology-archives-out-of-sync"] += 1
                modified.append(str(vault / rel))
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

    # Attach workflow hints for any manual-review category we know about.
    manual_categories = {f.category for f in manual_review}
    hints = {
        cat: WORKFLOW_HINTS[cat]
        for cat in manual_categories
        if cat in WORKFLOW_HINTS
    }

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
        workflow_hints=hints,
        summary="\n".join(summary_lines),
    )
