"""mem_archive — Archive the current work session into the vault.

Spec: core/procedures/mem-archive.md
Two modes:
- "incremental" (mid-session): rewrite context.md only, no new archive file.
- "full" (end-of-session): create a new dated archive + update history.md +
  rewrite context.md.

Per _archived.md doctrine: refuses to write to a project under
10-episodes/archived/. The user must /mem-historize --revive first.

Per _linking.md (v0.7.4) wikilink resolution invariant: every ``[[X]]`` in a
persisted body must resolve to an existing vault file at write time. Violation
raises ``DanglingWikilinkError`` (a ``ValueError`` subclass) listing the
offending targets and pointing to the doctrinal bypass: demote ``[[X]]`` to
inline backticks ``` `[[X]]` ``` for legitimate non-resolving citations.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter, paths
from memory_kit_mcp.vault.wikilinks import find_dangling

_SLUG_RE = re.compile(r"[^a-z0-9-]+")

# Required frontmatter keys when source_hint == "archeo-git" — mirrors the
# "source: archeo-git (archive)" column of _frontmatter-archeo.md MUST table.
# Empty string `""` and empty list `[]` are accepted; a missing key is not.
_ARCHEO_GIT_ARCHIVE_REQUIRED_KEYS: tuple[str, ...] = (
    "source",
    "scope",
    "collective",
    "modality",
    "branch",
    "branch_base",
    "branch_base_sha",
    "milestone_kind",
    "source_milestone",
    "commit_sha",
    "granularity",
    "friction_detected",
    "derived_atoms",
    "content_hash",
    "previous_atom",
    "topology_snapshot_hash",
    "repo_path",
)


class DanglingWikilinkError(ValueError):
    """Raised when a body about to be persisted contains unresolved wikilinks.

    The error message lists every offending target so the LLM client can
    correct the body in one pass — either by creating the targets first or
    by demoting them to inline backticks per the _linking.md convention.
    """


class ArcheoFrontmatterIncompleteError(ValueError):
    """Raised when ``source_hint="archeo-git"`` is set but ``archive_extra_fm``
    does not provide every MUST key required by ``_frontmatter-archeo.md``.

    The error message lists every missing key so the LLM client can correct
    the call in one pass. No partial write happens — the archive file is not
    created if validation fails.
    """


def _enforce_wikilinks(field_name: str, body: str, vault: Path) -> None:
    """Raise ``DanglingWikilinkError`` if ``body`` contains any dangling wikilinks.

    No-op when no wikilinks are present or all resolve. The vault is scanned
    fresh on each call — this is acceptable because the call paths
    (mem_archive incremental + full) are user-initiated, not high-frequency.
    """
    dangling = find_dangling(body, vault)
    if not dangling:
        return
    listed = ", ".join(f"`[[{t}]]`" for t in dangling)
    raise DanglingWikilinkError(
        f"{field_name} contains {len(dangling)} unresolved wikilink(s): {listed}. "
        "Per the _linking.md doctrine, every wikilink must resolve to an existing "
        "vault file at write time. Resolution: either create the target(s) first "
        "(preferred when the target would naturally exist) OR demote the link(s) "
        "to inline backticks (e.g. `[[X]]` instead of [[X]]) for legitimate "
        "non-resolving citations."
    )


def _slugify_subject(subject: str) -> str:
    """Normalize a subject string to a filesystem-safe slug."""
    s = subject.lower().strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = _SLUG_RE.sub("", s)
    return s.strip("-") or "session"


def _resolve_active(vault: Path, slug: str) -> tuple[Path, str]:
    """Resolve a slug to an *active* project or domain folder.

    Refuses archived projects per the _archived.md doctrine — for those, the
    LLM must call mem_historize with --revive first.
    """
    resolved = paths.resolve_slug(vault, slug)
    if resolved is None:
        raise FileNotFoundError(
            f"No project or domain '{slug}' in vault {vault}. "
            f"Available: {paths.list_projects(vault) + paths.list_domains(vault)}"
        )
    folder, kind, archived = resolved
    if archived:
        raise PermissionError(
            f"Project '{slug}' is archived. To resume active writes, run "
            f"mem_historize with revive=True first (see _archived.md doctrine)."
        )
    return folder, kind


def _do_incremental(
    vault: Path,
    slug: str,
    context_md: str,
    phase: str | None,
) -> ChangeReport:
    """Mid-session update — rewrite context.md only."""
    folder, kind = _resolve_active(vault, slug)
    _enforce_wikilinks("context_md", context_md, vault)
    ctx = folder / "context.md"

    fm: dict[str, Any] = {}
    if ctx.exists():
        fm, _ = frontmatter.read(ctx)
    if not fm:
        # Bootstrap minimal frontmatter for new contexts
        fm = {
            "project" if kind == "project" else "domain": slug,
            "tags": [f"{kind}/{slug}", "zone/episodes", f"kind/{kind}"],
            "zone": "episodes",
            "kind": kind,
            "slug": slug,
            "display": f"{slug} — context",
        }

    fm["last-session"] = datetime.now().date().isoformat()
    if phase is not None:
        fm["phase"] = phase

    frontmatter.write(ctx, fm, context_md)
    return ChangeReport(
        skill="mem_archive",
        success=True,
        files_modified=[str(ctx)],
        summary_md=(
            f"**mem_archive (incremental)** — `{slug}` ({kind})\n\n"
            f"- Updated `context.md` (last-session = {fm['last-session']}"
            f"{f', phase = {phase}' if phase is not None else ''})\n"
        ),
    )


def _merge_archive_fm(
    base_fm: dict[str, Any], extra_fm: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge ``extra_fm`` into ``base_fm``. Tags lists are concatenated
    (deduplicated, order-preserving); every other key is overridden by extra.

    Returns a new dict — does not mutate either input.
    """
    merged = dict(base_fm)
    if not extra_fm:
        return merged
    for key, value in extra_fm.items():
        if key == "tags" and isinstance(value, list):
            existing = list(merged.get("tags", []))
            for tag in value:
                if tag not in existing:
                    existing.append(tag)
            merged["tags"] = existing
        else:
            merged[key] = value
    return merged


def _validate_archeo_git_archive_fm(fm: dict[str, Any]) -> None:
    """Validate that ``fm`` carries every MUST key for an archeo-git archive.

    Raises ``ArcheoFrontmatterIncompleteError`` listing every missing key. A
    key whose value is `""` / `[]` / `False` is considered present (the
    doctrine accepts empty defaults). A key absent from the dict is missing.

    Also enforces ``source == "archeo-git"`` — a different source value is
    treated as a hint mismatch, not as a missing key (the message is
    explicit).
    """
    missing = [k for k in _ARCHEO_GIT_ARCHIVE_REQUIRED_KEYS if k not in fm]
    if missing:
        raise ArcheoFrontmatterIncompleteError(
            f"source_hint='archeo-git' requires every key from "
            f"_frontmatter-archeo.md, but {len(missing)} are missing from "
            f"archive_extra_fm: {', '.join(missing)}. "
            "See core/procedures/mem-archive.md §'Manual fallback after "
            "mem_archeo_git failure' for the canonical contract."
        )
    if fm.get("source") != "archeo-git":
        raise ArcheoFrontmatterIncompleteError(
            f"source_hint='archeo-git' requires archive_extra_fm['source'] "
            f"== 'archeo-git', got {fm.get('source')!r}."
        )


def _do_full(
    vault: Path,
    slug: str,
    archive_subject: str,
    archive_body_md: str,
    new_context_md: str,
    phase: str | None,
    archive_extra_fm: dict[str, Any] | None = None,
    source_hint: str | None = None,
) -> ChangeReport:
    """End-of-session — create a new archive + update history.md + reset context.md."""
    folder, kind = _resolve_active(vault, slug)
    _enforce_wikilinks("archive_body_md", archive_body_md, vault)
    _enforce_wikilinks("context_md", new_context_md, vault)

    # Phase E doctrine: emit <repo>/... sigils, not absolute paths. Resolve
    # repo_path from the CURRENT context.md before it gets reset below; no-op
    # for legacy projects without a repo_path.
    from memory_kit_mcp.vault.sigil import project_repo_path
    from memory_kit_mcp.vault.repo_paths import rewrite_abs_paths_to_sigil

    _repo_path = project_repo_path(folder)
    if _repo_path:
        archive_body_md, _ = rewrite_abs_paths_to_sigil(archive_body_md, _repo_path)
        new_context_md, _ = rewrite_abs_paths_to_sigil(new_context_md, _repo_path)

    now = datetime.now()
    date_iso = now.date().isoformat()
    timestamp = now.strftime("%Y-%m-%d-%Hh%M")
    subject_slug = _slugify_subject(archive_subject)
    archive_filename = f"{timestamp}-{slug}-{subject_slug}.md"

    archives_dir = folder / "archives"
    archives_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archives_dir / archive_filename

    base_fm: dict[str, Any] = {
        "project" if kind == "project" else "domain": slug,
        "tags": [f"{kind}/{slug}", "zone/episodes", "kind/archive"],
        "zone": "episodes",
        "kind": "archive",
        "slug": slug,
        "date": date_iso,
        "display": f"{slug} — {timestamp.replace('-', ' ', 1)} {archive_subject}",
    }
    archive_fm = _merge_archive_fm(base_fm, archive_extra_fm)

    if source_hint == "archeo-git":
        _validate_archeo_git_archive_fm(archive_fm)
    elif source_hint is not None:
        raise ValueError(
            f"Unknown source_hint {source_hint!r}. Supported: 'archeo-git'."
        )

    frontmatter.write(archive_path, archive_fm, archive_body_md)

    # Update history.md — prepend the new archive line
    history_path = folder / "history.md"
    if history_path.exists():
        h_fm, h_body = frontmatter.read(history_path)
    else:
        h_fm = {
            "project" if kind == "project" else "domain": slug,
            "tags": [f"{kind}/{slug}", "zone/episodes", f"kind/{kind}"],
            "zone": "episodes",
            "kind": kind,
            "slug": slug,
            "display": f"{slug} — history",
        }
        h_body = (
            f"> Fil chronologique des sessions du projet. "
            f"Voir aussi : [contexte](context.md)\n\n# {slug} — Historique\n"
        )

    new_line = (
        f"- [{date_iso} {now.strftime('%Hh%M')} — {archive_subject}]"
        f"(archives/{archive_filename})"
    )
    # Insert after the "# {slug} — Historique" header if present, else at the end
    if "# " in h_body:
        # Insert after the first H1 line + blank line
        lines = h_body.splitlines()
        out: list[str] = []
        inserted = False
        for line in lines:
            out.append(line)
            if not inserted and line.startswith("# "):
                # peek ahead: if next non-blank line is a list item, prepend; else add a blank
                out.append("")
                out.append(new_line)
                inserted = True
        h_body = "\n".join(out) + "\n" if out else new_line + "\n"
    else:
        h_body = h_body.rstrip() + "\n\n" + new_line + "\n"

    frontmatter.write(history_path, h_fm, h_body)

    # Reset context.md
    ctx_path = folder / "context.md"
    if ctx_path.exists():
        ctx_fm, _ = frontmatter.read(ctx_path)
    else:
        ctx_fm = {
            "project" if kind == "project" else "domain": slug,
            "tags": [f"{kind}/{slug}", "zone/episodes", f"kind/{kind}", "scope/work"],
            "zone": "episodes",
            "kind": kind,
            "slug": slug,
            "scope": "work",
            "display": f"{slug} — context",
        }
    ctx_fm["last-session"] = date_iso
    if phase is not None:
        ctx_fm["phase"] = phase
    frontmatter.write(ctx_path, ctx_fm, new_context_md)

    return ChangeReport(
        skill="mem_archive",
        success=True,
        files_created=[str(archive_path)],
        files_modified=[str(history_path), str(ctx_path)],
        summary_md=(
            f"**mem_archive (full)** — `{slug}` ({kind})\n\n"
            f"- Created `{archive_path.relative_to(vault)}`\n"
            f"- Updated `{history_path.relative_to(vault)}` (prepended new entry)\n"
            f"- Reset `{ctx_path.relative_to(vault)}` (last-session = {date_iso}"
            f"{f', phase = {phase}' if phase is not None else ''})\n"
        ),
    )


def register(mcp: FastMCP) -> None:
    """Register mem_archive with the FastMCP instance."""

    @mcp.tool()
    def mem_archive(
        slug: str = Field(..., description="Project or domain slug."),
        mode: Literal["incremental", "full"] = Field(
            "incremental",
            description=(
                "incremental = rewrite context.md only (mid-session). "
                "full = create a new archive + update history.md + reset context.md "
                "(end-of-session)."
            ),
        ),
        context_md: str = Field(
            "",
            description=(
                "New body for context.md. Required in both modes (in full mode, "
                "this becomes the post-session reset state)."
            ),
        ),
        archive_subject: str | None = Field(
            None,
            description="full mode only: short subject for the archive filename and entry.",
        ),
        archive_body_md: str | None = Field(
            None,
            description="full mode only: body of the new archive file.",
        ),
        phase: str | None = Field(
            None, description="Optional new phase string to set in context.md frontmatter."
        ),
        archive_extra_fm: dict[str, Any] | None = Field(
            None,
            description=(
                "full mode only: extra frontmatter fields merged into the "
                "archive's frontmatter. Tags lists are concatenated "
                "(deduplicated); other keys override the universal defaults. "
                "Required when source_hint is set, see _frontmatter-archeo.md."
            ),
        ),
        source_hint: Literal["archeo-git"] | None = Field(
            None,
            description=(
                "full mode only. When 'archeo-git', enforces the "
                "_frontmatter-archeo.md MUST table on the merged frontmatter "
                "(branch, branch_base, milestone_kind, source_milestone, "
                "commit_sha, granularity, derived_atoms, friction_detected, "
                "content_hash, etc.). Use this as the manual fallback after "
                "mem_archeo_git fails. Raises ArcheoFrontmatterIncompleteError "
                "if any MUST key is missing — no partial write."
            ),
        ),
    ) -> ChangeReport:
        """Archive the current session into the vault.

        Two modes per the spec:

        - "incremental" (default, mid-session): rewrites context.md with the new
          body, updates last-session and (optionally) phase in the frontmatter.
          No new archive file.

        - "full" (end-of-session, requires archive_subject + archive_body_md):
          creates a new dated archive file under archives/, prepends an entry
          to history.md, and resets context.md to new_context_md.

        Refuses archived projects (per _archived.md). Use mem_historize with
        revive=True first.

        Manual archeo-git fallback (v0.10.x): pass source_hint='archeo-git'
        with archive_extra_fm populated per _frontmatter-archeo.md. Use only
        when mem_archeo_git fails (timeout, refusal, etc.) — the regular
        mem_archeo_git path remains the primary writer.
        """
        config = get_config()
        vault = config.vault

        if mode == "incremental":
            return _do_incremental(vault, slug, context_md, phase)

        # full mode — validate required fields
        if not archive_subject or not archive_body_md:
            raise ValueError(
                "full mode requires both archive_subject and archive_body_md"
            )
        return _do_full(
            vault,
            slug,
            archive_subject,
            archive_body_md,
            context_md,
            phase,
            archive_extra_fm=archive_extra_fm,
            source_hint=source_hint,
        )
