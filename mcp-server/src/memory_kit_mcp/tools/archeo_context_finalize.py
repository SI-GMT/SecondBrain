"""mem_archeo_context_finalize — Phase 1 Python writer (LLM hands off the spans).

Spec: core/procedures/mem-archeo-context.md (LLM-side classification)
      + core/procedures/_frontmatter-archeo.md (Python-side enforcement)

Why this tool exists
====================

`mem_archeo_context` is intentionally a stub: the **classification** of
spans into the seven categories (workflow / sync / multi-tenant / security /
adr / goal / other) is semantic — LLM territory. But the **frontmatter
construction** (universal MUST fields, source-specific MUST fields, hash
calculation, idempotence keys, atomic writes, zone-index update) is
deterministic — Python territory.

Empirical motivation: a less-rigorous LLM adapter run produced batches of
atoms missing universal frontmatter (`scope`, `collective`, `modality`),
`context_origin`, `branch`, `source_doc_hash` and tag mirrors — silently
broken atoms that parsed fine but would never be recognised by mem_recall,
would be flagged as orphans by mem_health_scan, and would mis-render in
Obsidian's graph.

The fix: split responsibilities. The LLM identifies spans (subject, body,
extracted_category, source_doc) and calls this tool with the structured
input. The tool **enforces** the canonical frontmatter on every atom — no
silent omissions possible.

API contract
============

INPUT: a list of `ArcheoContextSpan` items, each carrying (at least) the
fields the LLM is allowed to choose: `subject`, `body`, `extracted_category`,
`source_doc`. Optional zone-specific fields the LLM may detect:
`force` (principles), `horizon` + `status` (goals), `adr_status` (ADRs).
Plus the project metadata: `project`, `repo_path`, `scope`.

OUTPUT: an `ArcheoContextFinalizeResult` with the list of files written /
revised / skipped, plus structured warnings per span.

Idempotence: keyed on `(project, source_doc, extracted_category, slug)`.
A second invocation with the same span content is a no-op (zero writes).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.vault import frontmatter
from memory_kit_mcp.vault.atomic_io import hash_content, write_atomic
from memory_kit_mcp.vault.zone_index import update_zone_index_for_atom

# ---- Constants ----

# Mapping (extracted_category) -> (zone path template, default frontmatter overrides).
# {scope} and {project} are placeholders — substituted at write time.
# These targets mirror core/procedures/mem-archeo-context.md §5b table.
_CATEGORY_ROUTES: dict[str, dict[str, Any]] = {
    "workflow": {
        "zone_dir": "40-principles/{scope}/methodology",
        "zone": "principles",
        "type": "principle",
        "default_force": "preference",
    },
    "sync": {
        "zone_dir": "20-knowledge/architecture",
        "zone": "knowledge",
        "type": "architecture",
    },
    "multi-tenant": {
        "zone_dir": "20-knowledge/architecture",
        "zone": "knowledge",
        "type": "architecture",
    },
    "security": {
        "zone_dir": "40-principles/{scope}/security",
        "zone": "principles",
        "type": "principle",
        "default_force": "red-line",
    },
    "adr": {
        "zone_dir": "20-knowledge/architecture/decisions",
        "zone": "knowledge",
        "type": "architecture",
        "default_adr_status": "accepted",
    },
    "goal": {
        "zone_dir": "50-goals/{scope}/projects/{project}",
        "zone": "goals",
        "type": "goal",
        "default_horizon": "medium",
        "default_status": "open",
    },
    "other": {
        "zone_dir": "00-inbox",
        "zone": "inbox",
        "type": "note",
    },
}

_VALID_CATEGORIES = tuple(_CATEGORY_ROUTES.keys())
_VALID_FORCES = ("red-line", "heuristic", "preference")
_VALID_HORIZONS = ("short", "medium", "long")
_VALID_STATUSES = ("open", "in-progress", "done", "abandoned")
_VALID_SCOPES = ("personal", "work")

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


# ---- Pydantic models ----


class ArcheoContextSpan(BaseModel):
    """One atom-to-be, classified by the LLM and ready for Python finalisation."""

    subject: str = Field(
        description="Short title of the atom (≤ 60 chars). Will be slugified."
    )
    body: str = Field(
        description="Markdown body of the atom (without frontmatter)."
    )
    extracted_category: str = Field(
        description=(
            f"One of: {' | '.join(_VALID_CATEGORIES)}. "
            "See mem-archeo-context.md §5b for routing table."
        )
    )
    source_doc: str = Field(
        description=(
            "Path of the source document, relative to the repo root. "
            "Used as the idempotence key + read by Python to compute "
            "`source_doc_hash`."
        )
    )
    # Optional zone-specific fields (LLM may detect, otherwise defaults apply)
    force: str | None = Field(
        default=None,
        description=(
            f"For principles only: one of {' | '.join(_VALID_FORCES)}. "
            "Overrides the category default if given."
        ),
    )
    horizon: str | None = Field(
        default=None,
        description=(
            f"For goals only: one of {' | '.join(_VALID_HORIZONS)}. "
            "Default: medium."
        ),
    )
    status: str | None = Field(
        default=None,
        description=(
            f"For goals only: one of {' | '.join(_VALID_STATUSES)}. "
            "Default: open."
        ),
    )
    adr_status: str | None = Field(
        default=None,
        description=(
            "For ADRs only (extracted_category=adr): one of accepted | "
            "proposed | superseded | rejected. Default: accepted."
        ),
    )


class ArcheoContextSpanResult(BaseModel):
    span_subject: str
    written_path: str | None = None
    outcome: str  # "created" | "revised" | "skipped" | "rejected"
    reason: str | None = None


class ArcheoContextFinalizeResult(BaseModel):
    project: str
    repo_path: str
    scope: str
    spans_total: int
    files_created: int
    files_revised: int
    files_skipped: int
    files_rejected: int
    spans: list[ArcheoContextSpanResult]
    warnings: list[str]
    summary_md: str


# ---- Helpers ----


def _slugify(s: str) -> str:
    """Lowercase, strip accents (best-effort), collapse non [a-z0-9-] into '-'."""
    import unicodedata

    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = _SLUG_RE.sub("-", s).strip("-")
    return s or "untitled"


def _file_slug(project: str, subject: str, category: str) -> str:
    """Build the file slug — `{project}-{subject-slug}` (canonical pattern).

    For ADRs we additionally prefix with `adr-{nnn}` if the subject already
    starts with a number (e.g. "ADR 001 …").
    """
    subj = _slugify(subject)
    if category == "adr" and subj.startswith("adr-"):
        # already adr-prefixed
        return f"{project}-{subj}"
    if category == "adr":
        return f"{project}-adr-{subj}"
    return f"{project}-{subj}"


def _read_source_doc(repo_path: Path, source_doc: str) -> tuple[str, str] | tuple[None, None]:
    """Return (text, sha256-hex) of the source doc, or (None, None) if unreadable."""
    full = repo_path / source_doc
    if not full.is_file():
        return None, None
    try:
        text = full.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, None
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text, h


def _build_tags(*, fm: dict[str, Any], category: str, project: str,
                detected_force: str | None) -> list[str]:
    """Build the redundant tag mirror per _frontmatter-archeo.md."""
    tags = [
        f"zone/{fm['zone']}",
        f"scope/{fm['scope']}",
        f"type/{fm['type']}",
        f"modality/{fm['modality']}",
        f"project/{project}",
        "source/archeo-context",
        f"category/{category}",
    ]
    if detected_force:
        tags.append(f"force/{detected_force}")
    if "horizon" in fm:
        tags.append(f"horizon/{fm['horizon']}")
    if "status" in fm:
        tags.append(f"status/{fm['status']}")
    if category == "adr" and "status" in fm:
        # ADR status is in `status` field for archetype-decisions
        pass
    if category == "adr":
        adr_status = fm.get("adr_status", "accepted")
        tags.append("category/adr")
        tags.append(f"adr/{adr_status}")
        # de-dupe duplicate category/adr from above append
        seen = set()
        deduped = []
        for t in tags:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        tags = deduped
    return tags


def _build_atom_frontmatter(
    *,
    span: ArcheoContextSpan,
    project: str,
    scope: str,
    today: str,
    source_doc_hash: str,
    body_hash: str,
    previous_atom: str = "",
    branch: str = "",
) -> dict[str, Any]:
    """Construct the full frontmatter dict — every MUST field present.

    No silent omission. This is the canonical contract per
    `core/procedures/_frontmatter-archeo.md`.
    """
    route = _CATEGORY_ROUTES[span.extracted_category]
    cat = span.extracted_category
    fm: dict[str, Any] = {
        "date": today,
        "zone": route["zone"],
        "scope": scope,
        "collective": False,
        "modality": "left",
        "type": route["type"],
        "project": project,
        "source": "archeo-context",
        "source_doc": span.source_doc,
        "source_doc_hash": source_doc_hash,
        "extracted_category": cat,
        "context_origin": f"[[99-meta/repo-topology/{project}]]",
        "branch": branch,
        "previous_atom": previous_atom,
        "content_hash": body_hash,
        "display": f"{route['type']}: {_slugify(span.subject)}",
    }

    # Category-specific fields
    if cat == "workflow" or cat == "security":
        chosen_force = span.force or route.get("default_force")
        if chosen_force not in _VALID_FORCES:
            chosen_force = route.get("default_force", "preference")
        fm["force"] = chosen_force
    elif cat == "goal":
        fm["horizon"] = span.horizon if span.horizon in _VALID_HORIZONS else route["default_horizon"]
        fm["status"] = span.status if span.status in _VALID_STATUSES else route["default_status"]
    elif cat == "adr":
        adr_status = span.adr_status or route.get("default_adr_status", "accepted")
        fm["adr_status"] = adr_status

    # Tags last — built from the now-finalised fm
    detected_force = fm.get("force")
    fm["tags"] = _build_tags(
        fm=fm, category=cat, project=project, detected_force=detected_force
    )
    return fm


def _resolve_target_path(
    vault: Path, project: str, scope: str, span: ArcheoContextSpan
) -> Path:
    """Compute the absolute write path for the given span."""
    route = _CATEGORY_ROUTES[span.extracted_category]
    zone_dir = route["zone_dir"].format(scope=scope, project=project)
    file_slug = _file_slug(project, span.subject, span.extracted_category)
    return vault / zone_dir / f"{file_slug}.md"


def _find_existing_for_idempotence(
    vault: Path,
    *,
    project: str,
    source_doc: str,
    extracted_category: str,
    expected_path: Path,
) -> Path | None:
    """Locate an existing archeo-context atom for idempotence.

    Strategy: the deterministic write path (`expected_path`) is the
    primary key — if a file exists there with matching frontmatter
    fingerprint (source+project+source_doc+extracted_category), it's
    the revision target. We don't scan the whole zone for "any atom
    with same (project, source_doc, category)" because that key is
    too coarse: multiple distinct ideas can share doc+category (e.g.
    several methodology principles from the same CLAUDE.md). The slug
    derived from the subject is what disambiguates them, and it's
    already encoded in the file path.
    """
    if not expected_path.exists():
        return None
    try:
        fm, _body = frontmatter.read(expected_path)
    except Exception:
        return None
    if (fm.get("source") == "archeo-context"
            and fm.get("project") == project
            and fm.get("source_doc") == source_doc
            and fm.get("extracted_category") == extracted_category):
        return expected_path
    return None


# ---- Core executor ----


def execute_finalize(
    *,
    vault: Path,
    project: str,
    repo_path: Path,
    scope: str,
    spans: list[ArcheoContextSpan],
    today: str,
) -> ArcheoContextFinalizeResult:
    """Pure function — testable independently of the MCP layer."""
    # 1. Validate scope
    if scope not in _VALID_SCOPES:
        raise ValueError(f"scope must be one of {_VALID_SCOPES}, got {scope!r}")
    if not repo_path.is_dir():
        raise ValueError(f"repo_path is not a directory: {repo_path}")

    # 2. Pre-read source docs once (avoid re-reading per span)
    doc_cache: dict[str, tuple[str | None, str | None]] = {}

    span_results: list[ArcheoContextSpanResult] = []
    warnings: list[str] = []
    created = revised = skipped = rejected = 0

    for span in spans:
        if span.extracted_category not in _VALID_CATEGORIES:
            span_results.append(ArcheoContextSpanResult(
                span_subject=span.subject,
                outcome="rejected",
                reason=(
                    f"invalid extracted_category {span.extracted_category!r} — "
                    f"must be one of {_VALID_CATEGORIES}"
                ),
            ))
            rejected += 1
            continue

        if span.source_doc not in doc_cache:
            doc_cache[span.source_doc] = _read_source_doc(repo_path, span.source_doc)
        _doc_text, source_doc_hash = doc_cache[span.source_doc]
        if source_doc_hash is None:
            span_results.append(ArcheoContextSpanResult(
                span_subject=span.subject,
                outcome="rejected",
                reason=f"source_doc unreadable: {span.source_doc}",
            ))
            rejected += 1
            continue

        # Compute body hash before frontmatter assembly (frontmatter contains it)
        body = span.body if span.body.endswith("\n") else span.body + "\n"
        body_hash = hash_content(body)

        # Resolve target path (also serves as idempotence anchor)
        expected_target = _resolve_target_path(vault, project, scope, span)
        # Idempotence check (keyed on the deterministic write path)
        existing = _find_existing_for_idempotence(
            vault, project=project, source_doc=span.source_doc,
            extracted_category=span.extracted_category,
            expected_path=expected_target,
        )
        previous_atom_link = ""
        if existing is not None:
            try:
                ex_fm, _ex_body = frontmatter.read(existing)
            except Exception:
                ex_fm = {}
            if ex_fm.get("content_hash") == body_hash:
                span_results.append(ArcheoContextSpanResult(
                    span_subject=span.subject,
                    written_path=str(existing.relative_to(vault)),
                    outcome="skipped",
                    reason="content_hash unchanged (idempotent)",
                ))
                skipped += 1
                continue
            # Different content → revision
            previous_atom_link = f"[[{existing.stem}]]"

        # Build full frontmatter
        fm_dict = _build_atom_frontmatter(
            span=span, project=project, scope=scope, today=today,
            source_doc_hash=source_doc_hash, body_hash=body_hash,
            previous_atom=previous_atom_link,
        )

        target = expected_target
        target.parent.mkdir(parents=True, exist_ok=True)

        # Compose final file content + write atomically
        full_content = frontmatter.serialize(fm_dict, body)
        write_atomic(target, full_content)

        if existing is None:
            created += 1
            span_results.append(ArcheoContextSpanResult(
                span_subject=span.subject,
                written_path=str(target.relative_to(vault)),
                outcome="created",
            ))
        else:
            revised += 1
            span_results.append(ArcheoContextSpanResult(
                span_subject=span.subject,
                written_path=str(target.relative_to(vault)),
                outcome="revised",
                reason=f"previous atom: {previous_atom_link}",
            ))

        # Update zone index (best-effort — does not fail the write)
        try:
            update_zone_index_for_atom(vault, target)
        except Exception as e:  # pragma: no cover — index update is best-effort
            warnings.append(
                f"zone-index update failed for {target.name}: {e}"
            )

    summary = _format_summary(
        project, repo_path, scope, len(spans), created, revised, skipped, rejected
    )

    return ArcheoContextFinalizeResult(
        project=project,
        repo_path=str(repo_path),
        scope=scope,
        spans_total=len(spans),
        files_created=created,
        files_revised=revised,
        files_skipped=skipped,
        files_rejected=rejected,
        spans=span_results,
        warnings=warnings,
        summary_md=summary,
    )


def _format_summary(
    project: str, repo_path: Path, scope: str, total: int,
    created: int, revised: int, skipped: int, rejected: int,
) -> str:
    return (
        f"**mem_archeo_context_finalize** — {project}\n\n"
        f"Scope          : {scope}\n"
        f"Repo           : {repo_path}\n"
        f"Spans received : {total}\n"
        f"  Created      : {created}\n"
        f"  Revised      : {revised}\n"
        f"  Skipped      : {skipped} (idempotent)\n"
        f"  Rejected     : {rejected}\n"
    )


# ---- MCP registration ----


def register(mcp: FastMCP) -> None:
    """Register mem_archeo_context_finalize."""

    @mcp.tool()
    def mem_archeo_context_finalize(
        project: str,
        repo_path: str,
        spans: list[ArcheoContextSpan],
        scope: str = "work",
        today: str | None = None,
    ) -> ArcheoContextFinalizeResult:
        """Phase 1 finalisation — write archeo-context atoms with canonical frontmatter.

        Companion to mem_archeo_context (LLM stub). The LLM classifies
        document spans into the seven categories then calls this tool with
        the structured input. Python enforces the canonical frontmatter on
        every atom — no silent omission of universal MUST fields possible.

        See core/procedures/mem-archeo-context.md (LLM-side classification)
        and core/procedures/_frontmatter-archeo.md (Python-side enforcement).

        Idempotence: keyed on (project, source_doc, extracted_category).
        Re-running with the same content is a no-op (zero writes).
        """
        from datetime import date as _date

        if today is None:
            today = _date.today().isoformat()

        config = get_config()
        vault = config.vault
        return execute_finalize(
            vault=vault,
            project=project,
            repo_path=Path(repo_path),
            scope=scope,
            spans=spans,
            today=today,
        )
