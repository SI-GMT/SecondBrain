"""mem_archeo_git — Phase 3 of the triphasic archeo: Git history reconstruction.

Spec: core/procedures/mem-archeo-git.md

Reconstructs the temporal history of a Git repo as N dated archives. Four
granularity levels supported (v0.9.1):

- ``tags`` (default) — 1 archive per semver tag ``v*.*.*``.
- ``releases`` — 1 archive per GitHub Release (via ``gh release list``).
  Tag-backed releases include the release notes body in the archive.
- ``merges`` — 1 archive per merged GitHub PR (via ``gh pr list --merged``).
  Each archive embeds the merge commit metadata + PR body.
- ``commits`` — 1 archive per time window (day / week / month). Optional
  ``by_author=True`` further splits each window per primary author. Co-authors
  recorded as metadata.

Branch-first mode (``branch_first={branch}``) restricts the scan to the
commits unique to ``{branch}`` since its divergence from ``branch_base``
(default ``main``). Each archive's frontmatter carries the branch / base /
base_sha so ``mem-archeo`` orchestration can wire branch topology files
under ``99-meta/repo-topology/{slug}-branches/``.

Each archive embeds the AI files context (CLAUDE.md / AGENTS.md / GEMINI.md
/ MISTRAL.md / README.md) at the time of the representative commit, read via
``git show {sha}:{file}``.

GitHub-backed levels (``releases``, ``merges``) require the ``gh`` CLI on
PATH and an authenticated session (``gh auth status`` ready). When ``gh`` is
absent or unauthenticated, the level emits a warning and returns no
milestones — the LLM client can fall back to the skills procedure.

Idempotence: (project, source_milestone) — looks for any existing archive
under ``projects/{slug}/archives/`` whose frontmatter ``source_milestone``
matches. Format per level:

- tags     → ``v0.8.0``
- releases → ``release-v0.8.0``
- merges   → ``pr-#42``
- commits  → ``window-2026-W18`` (or ``window-2026-W18-author@example.com``
             when ``by_author=True``)

Friction detection (heuristic ≥3 successive commits same theme) remains
deferred — section emitted with the explicit fallback line per spec
invariant.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.archeo.file_summary import (
    render_technical_section,
    summarize_files,
)
from memory_kit_mcp.archeo.topology import (
    BranchMerge,
    find_branch_merges_via_perimeter,
    find_merge_commit_for_branch,
)
from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ArcheoGitResult, MilestoneInfo
from memory_kit_mcp.vault import frontmatter, paths
from memory_kit_mcp.vault.atomic_io import hash_content
from memory_kit_mcp.vault.topology_scanner import NotAGitRepoError, scan


# ----------------------------------------------------------------------
# Public tool
# ----------------------------------------------------------------------


_VALID_LEVELS = ("tags", "releases", "merges", "commits")
_VALID_WINDOWS = ("day", "week", "month")


def execute_git(
    vault: Path,
    repo: Path,
    project: str | None,
    level: str = "tags",
    since: str | None = None,
    until: str | None = None,
    window: str = "week",
    by_author: bool = False,
    branch_first: str | None = None,
    branch_base: str = "main",
    since_sha: str | None = None,
    since_date: str | None = None,
    by_files: bool = False,
    skip_repo_validation: bool = False,
) -> ArcheoGitResult:
    """Run the Phase 3 git history reconstruction. Module-level so the
    orchestrator can call it without going through the MCP layer.

    `skip_repo_validation=True` is set by the orchestrator which has already
    validated the repo via Phase 0 — avoids redundant subprocess calls.
    """
    if level not in _VALID_LEVELS:
        raise ValueError(
            f"Unknown level {level!r}. Expected one of: {list(_VALID_LEVELS)}."
        )
    if window not in _VALID_WINDOWS:
        raise ValueError(
            f"Unknown window {window!r}. Expected one of: {list(_VALID_WINDOWS)}."
        )

    if not skip_repo_validation:
        try:
            scan(repo, depth=1, vault=vault)
        except NotAGitRepoError as e:
            raise NotAGitRepoError(str(e)) from e

    slug = _resolve_project_slug(vault, repo, project)
    warnings: list[str] = []

    # Branch-first mode resolves the divergence point upfront and overrides
    # the per-level milestone discovery to scope on commits unique to the branch.
    branch_ctx: _BranchContext | None = None
    if branch_first:
        try:
            branch_ctx = _resolve_branch_context(
                repo, branch_first, branch_base,
                since_sha=since_sha, since_date=since_date, by_files=by_files,
            )
        except BranchScopeUnresolvedError as exc:
            # Fully merged + no anchor + no name match. Surface the actionable
            # message as a warning rather than crashing the whole tool — the
            # LLM (or user) can re-invoke with scope_glob / since_sha. The
            # tool then proceeds with standard milestone discovery, which
            # may still yield useful repo-wide results (typically 0 in this
            # case, but the explicit warning is the value).
            warnings.append(f"Branch-first resolution failed: {exc}")
            branch_ctx = None
        if branch_ctx is None and not warnings:
            warnings.append(
                f"Branch-first mode requested for {branch_first!r} but no "
                f"merge-base, by-files set, name-based scope, or explicit "
                f"since_sha could resolve a starting point relative to "
                f"{branch_base!r}. Falling back to standard mode."
            )

    if branch_ctx is not None:
        milestones = _discover_branch_first(
            repo, branch_ctx, level=level, window=window, by_author=by_author,
            since=since, until=until, warnings=warnings,
        )
    else:
        milestones = _discover_milestones(
            repo, level=level, since=since, until=until,
            window=window, by_author=by_author, warnings=warnings,
        )

    if not milestones:
        warnings.append(
            f"No milestones found for level={level!r}"
            + (f" on branch {branch_first!r}" if branch_first else "")
            + " in the requested range."
        )

    existing_milestones = _scan_existing_milestones(vault, slug)

    # Phase 3 perf: pre-fetch all AI files referenced by the milestones in
    # one ``git cat-file --batch`` invocation instead of N×8 ``git show``
    # subprocess calls inside the body-build loop. Drops the per-milestone
    # cost from ~280ms to ~1ms on Windows where CreateProcess overhead
    # dominates. Critical to keep mem_archeo_git under the 30s MCP timeout
    # on repos with many tags / commits.
    ai_cache = _prefetch_ai_files_at_commits(
        repo, [info.commit_sha for info in milestones if info.commit_sha]
    )

    files_created: list[str] = []
    files_modified: list[str] = []
    created = revised = skipped = 0

    archives_created_paths: list[str] = []
    archives_revised_paths: list[str] = []

    for info in milestones:
        outcome, archive_path = _write_archive(
            vault, slug, repo, info, existing_milestones,
            branch_ctx=branch_ctx,
            ai_cache=ai_cache,
        )
        info.outcome = outcome
        info.archive_path = archive_path
        if outcome == "created":
            created += 1
            files_created.append(archive_path)
            archives_created_paths.append(archive_path)
        elif outcome == "revised":
            revised += 1
            files_modified.append(archive_path)
            archives_revised_paths.append(archive_path)
        else:
            skipped += 1

    # Phase 5 enforcement (v0.10.x post-Gemini-drift case study) : auto-init
    # the project skeleton if missing, prepend new archives to history.md,
    # update context.md phase + last-session, register in root index.md.
    # Doctrine: every archeo write lands inside a project that carries
    # context.md + history.md.
    if archives_created_paths or archives_revised_paths:
        try:
            extra_created, extra_modified = _enforce_phase5(
                vault=vault,
                slug=slug,
                repo=repo,
                archives_created=archives_created_paths,
                archives_revised=archives_revised_paths,
                branch_ctx=branch_ctx,
            )
            files_created.extend(extra_created)
            files_modified.extend(extra_modified)
        except (OSError, RuntimeError, ValueError) as exc:
            # Surface as warning rather than crash — the archives have already
            # been written successfully. The user can re-run mem_health_repair
            # to recover the skeleton.
            warnings.append(
                f"Phase 5 enforcement failed: {type(exc).__name__}: {exc}. "
                "Archives were written but context.md / history.md / index.md "
                "may be out of sync. Run mem_health_repair to reconcile."
            )

    return ArcheoGitResult(
        project=slug,
        repo_path=str(repo),
        level=level,
        milestones_processed=len(milestones),
        archives_created=created,
        archives_revised=revised,
        archives_skipped=skipped,
        milestones=milestones,
        files_created=files_created,
        files_modified=files_modified,
        warnings=warnings,
        summary_md=_summary_md(slug, level, milestones, created, revised, skipped),
    )


def _discover_milestones(
    repo: Path,
    *,
    level: str,
    since: str | None,
    until: str | None,
    window: str,
    by_author: bool,
    warnings: list[str],
) -> list[MilestoneInfo]:
    """Standard-mode milestone discovery — dispatches to per-level helpers."""
    if level == "tags":
        tags = _list_semver_tags(repo, since=since, until=until)
        # Batch-fetch metadata for every tag's commit in one git log call;
        # _build_tag_milestone will pull from the cache instead of issuing
        # 2 forks per tag.
        meta_cache = _commit_metadata_batch(repo, [tag.sha for tag in tags])
        return [_build_tag_milestone(repo, tag, meta_cache=meta_cache) for tag in tags]
    if level == "releases":
        return _list_github_releases(repo, since=since, until=until, warnings=warnings)
    if level == "merges":
        return _list_github_merges(repo, since=since, until=until, warnings=warnings)
    if level == "commits":
        return _list_commit_windows(
            repo, since=since, until=until, window=window, by_author=by_author,
            warnings=warnings,
        )
    raise AssertionError(f"unreachable: level={level!r}")


def register(mcp: FastMCP) -> None:
    """Register mem_archeo_git with the FastMCP instance."""

    @mcp.tool()
    def mem_archeo_git(
        repo_path: str = Field(..., description="Absolute path to the local Git repository to walk."),
        project: str | None = Field(
            None,
            description="Target project slug. Defaults to basename(repo_path) if it matches an existing project.",
        ),
        level: str = Field(
            "tags",
            description=(
                "Granularity: 'tags' (semver v*.*.*), 'releases' (GitHub Releases via gh CLI), "
                "'merges' (merged PRs via gh CLI), or 'commits' (time-windowed)."
            ),
        ),
        since: str | None = Field(
            None,
            description="Lower bound (inclusive) on milestone date, format YYYY-MM-DD.",
        ),
        until: str | None = Field(
            None,
            description="Upper bound (inclusive) on milestone date, format YYYY-MM-DD.",
        ),
        window: str = Field(
            "week",
            description="For level='commits': grouping window — one of day, week, month.",
        ),
        by_author: bool = Field(
            False,
            description=(
                "For level='commits' or branch-first: split each window per primary author. "
                "Co-authors recorded as metadata."
            ),
        ),
        branch_first: str | None = Field(
            None,
            description=(
                "If set, scope the scan to commits relevant to this branch. "
                "Resolution order: explicit since_sha > since_date > merge-base; "
                "if the branch is fully merged into branch_base, falls back "
                "automatically to the first-parent divergence point. Activates "
                "branch-first mode."
            ),
        ),
        branch_base: str = Field(
            "main",
            description="Branch-first mode: base branch for divergence detection. Default 'main'.",
        ),
        since_sha: str | None = Field(
            None,
            description=(
                "Branch-first escape hatch (C): explicit start SHA. Bypasses "
                "merge-base detection. Useful when the branch was rebased / squashed "
                "and the historical divergence point is known."
            ),
        ),
        since_date: str | None = Field(
            None,
            description=(
                "Branch-first escape hatch (C, alt): YYYY-MM-DD floor. The walk "
                "starts at this date on the branch tip. Use when the branch has "
                "no clean divergence point but a date-based scope is acceptable."
            ),
        ),
        by_files: bool = Field(
            False,
            description=(
                "Branch-first strategy (B): query commits TOUCHING the files "
                "introduced by the branch (detected via --diff-filter=A on the "
                "first-parent lineage), repo-wide rather than constrained to "
                "the branch range. Captures creation, evolution and post-merge "
                "fixes on the same files. Recommended for archeology of long-lived "
                "feature branches."
            ),
        ),
    ) -> ArcheoGitResult:
        """Phase 3 of the triphasic archeo: reconstruct Git history as dated archives.

        Standard mode walks the repo at the chosen ``level`` (tags / releases /
        merges / commits) and writes one archive per milestone in
        ``10-episodes/projects/{slug}/archives/``.

        **Branch-first mode** (set ``branch_first``) supports three resolution
        strategies, mix-and-matchable:

        - **A. Auto first-parent fallback** — when the branch has been merged
          into ``branch_base``, ``merge-base`` would yield no commits. The
          tool detects this and uses the first-parent divergence point
          instead. No flag needed; happens transparently.
        - **B. By-files** — set ``by_files=True`` to query commits touching
          the files introduced by the branch (repo-wide), capturing the full
          lineage including post-merge fixes.
        - **C. Explicit since** — pass ``since_sha`` or ``since_date`` to
          override merge-base detection with an arbitrary anchor.

        Each archive embeds AI files context at the time of the representative
        commit. Idempotent on (project, source_milestone). Refuses non-Git
        directories. GitHub-backed levels require the ``gh`` CLI on PATH.
        """
        config = get_config()
        return execute_git(
            vault=config.vault,
            repo=Path(repo_path).expanduser().resolve(),
            project=project,
            level=level,
            since=since,
            until=until,
            window=window,
            by_author=by_author,
            branch_first=branch_first,
            branch_base=branch_base,
            since_sha=since_sha,
            since_date=since_date,
            by_files=by_files,
        )


# ----------------------------------------------------------------------
# Tag discovery
# ----------------------------------------------------------------------


@dataclass
class _Tag:
    name: str
    sha: str
    date_iso: str  # full ISO including time, e.g. 2026-04-21T21:03:14+00:00


_SEMVER_TAG_RE = re.compile(r"^v\d+(\.\d+){1,3}([-+].+)?$")


def _list_semver_tags(repo: Path, since: str | None, until: str | None) -> list[_Tag]:
    """Return semver tags v*.*.* sorted by commit date ascending.

    Uses ``git for-each-ref`` with a format that resolves the **commit** SHA
    in a single subprocess — no per-tag ``git rev-parse`` follow-up call
    (each ``rev-parse`` adds ~30ms of CreateProcess overhead on Windows
    and the cost is linear in tag count, dominating Phase 3 on large repos).

    Format fields (6):

    - ``%(refname:short)`` — the tag name.
    - ``%(objectname)`` — the SHA of the ref target. For lightweight tags
      this is the commit; for annotated tags this is the *tag object*.
    - ``%(*objectname)`` — the dereferenced SHA. For annotated tags this
      is the commit SHA; empty for lightweight tags.
    - ``%(creatordate:iso-strict)`` — the tag's creator date (informational
      only, kept for forward compatibility).
    - ``%(*committerdate:iso-strict)`` — the *commit*'s committer date for
      annotated tags. Empty for lightweight tags.
    - ``%(committerdate:iso-strict)`` — the tagger date for annotated, or
      the commit date for lightweight. Used as a fallback for the date
      column when the dereferenced one is empty.

    The commit SHA we keep is ``*objectname or objectname`` — covers both
    tag flavours without a follow-up ``rev-parse``.
    """
    cmd = [
        "git", "-C", str(repo), "for-each-ref",
        "--format=%(refname:short)|%(objectname)|%(*objectname)|%(creatordate:iso-strict)|%(*committerdate:iso-strict)|%(committerdate:iso-strict)",
        "refs/tags",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    out: list[_Tag] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 5)
        if len(parts) != 6:
            continue
        name, ref_sha, deref_sha, _creatordate, deref_committerdate, committerdate = parts
        if not _SEMVER_TAG_RE.match(name):
            continue
        # Annotated tag: deref_sha = commit. Lightweight tag: ref_sha already
        # points at the commit and deref_sha is empty.
        commit_sha = deref_sha or ref_sha
        commit_date_iso = deref_committerdate or committerdate
        date_part = commit_date_iso[:10] if len(commit_date_iso) >= 10 else ""
        if since and date_part and date_part < since:
            continue
        if until and date_part and date_part > until:
            continue
        out.append(_Tag(name=name, sha=commit_sha, date_iso=commit_date_iso))

    out.sort(key=lambda t: t.date_iso)
    return out


def _rev_parse_commit(repo: Path, ref: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", f"{ref}^{{commit}}"],
            capture_output=True, text=True, check=True,
        stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


# ----------------------------------------------------------------------
# Milestone info extraction
# ----------------------------------------------------------------------


def _build_tag_milestone(
    repo: Path,
    tag: _Tag,
    *,
    meta_cache: dict[str, MilestoneInfo] | None = None,
) -> MilestoneInfo:
    """Extract the metadata for a tag's commit and wrap it as a MilestoneInfo.

    When ``meta_cache`` (built by :func:`_commit_metadata_batch`) is provided
    and contains the tag's commit SHA, we copy from it rather than issuing
    fresh ``git show`` subprocess calls. The fallback ISO date is still
    applied when the cache lookup yielded an empty author date.
    """
    cached = meta_cache.get(tag.sha) if meta_cache else None
    if cached is not None:
        info = MilestoneInfo(
            commit_sha=cached.commit_sha,
            date=cached.date or (tag.date_iso[:10] if len(tag.date_iso) >= 10 else ""),
            time=cached.time or _extract_hhmm(tag.date_iso),
            author_name=cached.author_name,
            author_email=cached.author_email,
            subject=cached.subject,
            files_changed=cached.files_changed,
            insertions=cached.insertions,
            deletions=cached.deletions,
        )
    else:
        info = _commit_metadata(repo, tag.sha, fallback_iso=tag.date_iso)
    info.milestone_kind = "tag"
    info.tag = tag.name
    return info


_METADATA_BATCH_DELIM = "__ARCHEO_GIT_META__"


def _commit_metadata_batch(
    repo: Path, shas: list[str]
) -> dict[str, MilestoneInfo]:
    """Batch-read author / subject / diff-stats for many SHAs in one ``git log``.

    Replaces ``2 × N`` per-commit ``git show`` calls (one for header, one
    for ``--shortstat``) with a single ``git log --no-walk --shortstat``
    that emits all requested commits at once. On Windows where each fork
    costs ~15ms, this drops the per-tag metadata cost from ~80ms to a few
    ms and keeps Phase 3 well under the MCP timeout regardless of milestone
    count.

    The output uses a custom delimiter prefix ``__ARCHEO_GIT_META__`` so
    we can split commits unambiguously even when subjects contain pipes or
    newlines. Returns a mapping ``sha -> MilestoneInfo`` (no ``milestone_kind``
    set — the caller fills it according to the level).
    """
    out: dict[str, MilestoneInfo] = {}
    if not shas:
        return out

    # Deduplicate while preserving the order, so the parsing order is stable
    # and predictable for testing.
    unique: list[str] = []
    seen: set[str] = set()
    for sha in shas:
        if sha and sha not in seen:
            seen.add(sha)
            unique.append(sha)
    if not unique:
        return out

    cmd = [
        "git", "-C", str(repo), "log", "--no-walk",
        f"--pretty=format:{_METADATA_BATCH_DELIM}|%H|%an|%ae|%aI|%s",
        "--shortstat",
        *unique,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True,
            encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return out

    chunks = result.stdout.split(_METADATA_BATCH_DELIM)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.splitlines()
        header = lines[0].lstrip("|")
        parts = header.split("|", 4)
        if len(parts) < 5:
            continue
        sha, author_name, author_email, author_iso, subject = parts
        files_changed = insertions = deletions = 0
        for line in lines[1:]:
            line = line.strip()
            if "changed" in line and (
                "insertion" in line or "deletion" in line or "file" in line
            ):
                files_changed, insertions, deletions = _parse_shortstat(line)
        out[sha] = MilestoneInfo(
            commit_sha=sha,
            date=author_iso[:10] if len(author_iso) >= 10 else "",
            time=_extract_hhmm(author_iso),
            author_name=author_name,
            author_email=author_email,
            subject=subject,
            files_changed=files_changed,
            insertions=insertions,
            deletions=deletions,
        )
    return out


def _commit_metadata(
    repo: Path,
    sha: str,
    fallback_iso: str = "",
    *,
    cache: dict[str, MilestoneInfo] | None = None,
) -> MilestoneInfo:
    """Build a MilestoneInfo populated with author/subject/diff-stats for ``sha``.

    Used by every level: tags, releases (via the tag's commit), merges (via the
    merge commit), commits (via the representative commit of a window).

    When ``cache`` (built by :func:`_commit_metadata_batch`) is provided and
    contains ``sha``, returns a copy from it instead of issuing fresh
    ``git show`` subprocess calls. Critical for repos with many milestones
    where the per-commit fork overhead would push the run past the MCP
    timeout. Falls back to per-commit ``git show`` when the cache is None
    or the SHA is missing — preserves backward compatibility.
    """
    if cache is not None and sha in cache:
        cached = cache[sha]
        return MilestoneInfo(
            commit_sha=cached.commit_sha,
            date=cached.date or (fallback_iso[:10] if len(fallback_iso) >= 10 else ""),
            time=cached.time or _extract_hhmm(fallback_iso),
            author_name=cached.author_name,
            author_email=cached.author_email,
            subject=cached.subject,
            files_changed=cached.files_changed,
            insertions=cached.insertions,
            deletions=cached.deletions,
        )
    cmd = [
        "git", "-C", str(repo), "show", "-s",
        "--format=%an|%ae|%aI|%s",
        sha,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
        parts = result.stdout.strip().split("|", 3)
    except (FileNotFoundError, subprocess.CalledProcessError):
        parts = ["", "", fallback_iso, ""]
    if len(parts) < 4:
        parts = parts + [""] * (4 - len(parts))
    author_name, author_email, author_iso, subject = parts

    files_changed = insertions = deletions = 0
    try:
        stat = subprocess.run(
            ["git", "-C", str(repo), "show", "--shortstat", "--format=", sha],
            capture_output=True, text=True, check=True,
        stdin=subprocess.DEVNULL,
        )
        last_line = ""
        for line in stat.stdout.splitlines():
            line = line.strip()
            if "changed" in line and ("insertion" in line or "deletion" in line or "file" in line):
                last_line = line
        if last_line:
            files_changed, insertions, deletions = _parse_shortstat(last_line)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    iso = author_iso or fallback_iso
    return MilestoneInfo(
        commit_sha=sha,
        date=iso[:10] if len(iso) >= 10 else "",
        time=_extract_hhmm(iso),
        author_name=author_name,
        author_email=author_email,
        subject=subject,
        files_changed=files_changed,
        insertions=insertions,
        deletions=deletions,
    )


_SHORTSTAT_RE = re.compile(
    r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?",
)


def _parse_shortstat(line: str) -> tuple[int, int, int]:
    m = _SHORTSTAT_RE.search(line)
    if not m:
        return 0, 0, 0
    files = int(m.group(1) or 0)
    ins = int(m.group(2) or 0)
    dels = int(m.group(3) or 0)
    return files, ins, dels


def _extract_hhmm(iso: str) -> str:
    """Extract HH:MM from an ISO 8601 datetime string. Returns '' on failure."""
    if "T" in iso:
        time_part = iso.split("T", 1)[1]
        if len(time_part) >= 5:
            return time_part[:5]
    return ""


# ----------------------------------------------------------------------
# AI files extraction (MUST per spec invariant)
# ----------------------------------------------------------------------


_AI_FILES_TO_READ = (
    "CLAUDE.md", "AGENTS.md", "GEMINI.md", "MISTRAL.md",
    ".cursorrules", ".windsurfrules", ".aider.conf.yml",
    "README.md",
)


def _read_at_commit(repo: Path, sha: str, file: str) -> str | None:
    """Read a file's content at a given commit. Returns None if absent at that commit.

    Single-file read — useful as a fallback when no batch cache was pre-built.
    Heavier callers (the milestone loop) pre-fetch via
    :func:`_prefetch_ai_files_at_commits` instead, which reduces ``N`` forks
    to one ``git cat-file --batch`` invocation.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", f"{sha}:{file}"],
            capture_output=True, text=True, check=True,
        stdin=subprocess.DEVNULL,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _prefetch_ai_files_at_commits(
    repo: Path, shas: list[str]
) -> dict[str, dict[str, str | None]]:
    """Batch-fetch AI files for multiple commits via a single ``git cat-file --batch``.

    Replaces ``N × M`` individual ``git show`` subprocess calls with one
    long-lived process that streams all requested objects. Critical for
    ``mem_archeo_git`` performance on repos with many milestones — the
    Windows ``CreateProcess`` overhead alone (~15ms per fork) can push the
    runtime past the 30s MCP timeout once a project crosses ~100 tags or
    commits.

    Returns a mapping ``sha -> {filename: content | None}``. SHAs absent from
    the input return ``{}``; files not present at a given commit return
    ``None``. Decode failures (binary blobs, non-UTF-8 content) also surface
    as ``None`` — the caller's regex extractor only consumes text.

    Falls through to ``{sha: {}}`` on any subprocess error so the per-file
    fallback ``_read_at_commit`` can still service the request — never
    bubbles the error up to the milestone loop.
    """
    if not shas:
        return {}

    # Deduplicate SHAs while preserving order so the parsing pass stays
    # aligned with the input request stream.
    unique_shas: list[str] = []
    seen: set[str] = set()
    for sha in shas:
        if sha and sha not in seen:
            seen.add(sha)
            unique_shas.append(sha)

    requests: list[tuple[str, str]] = [
        (sha, fname) for sha in unique_shas for fname in _AI_FILES_TO_READ
    ]
    out: dict[str, dict[str, str | None]] = {sha: {} for sha in unique_shas}
    if not requests:
        return out

    # cat-file --batch reads ``<ref>\n`` per line, outputs per object:
    #   "<sha> <type> <size>\n<content>\n"   if found
    #   "<input> missing\n"                  if not found
    input_bytes = (
        "\n".join(f"{sha}:{fname}" for sha, fname in requests) + "\n"
    ).encode("utf-8")

    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "--batch"],
            input=input_bytes,
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return out

    if proc.returncode != 0:
        return out

    stdout = proc.stdout
    pos = 0

    for sha, fname in requests:
        nl = stdout.find(b"\n", pos)
        if nl == -1:
            out[sha][fname] = None
            break
        header = stdout[pos:nl].decode("utf-8", errors="replace")
        pos = nl + 1
        parts = header.split()
        if len(parts) >= 2 and parts[1] == "missing":
            out[sha][fname] = None
            continue
        if len(parts) != 3:
            out[sha][fname] = None
            continue
        try:
            size = int(parts[2])
        except ValueError:
            out[sha][fname] = None
            continue
        if pos + size > len(stdout):
            out[sha][fname] = None
            break
        content_bytes = stdout[pos:pos + size]
        pos += size
        # cat-file --batch appends one trailing newline after each object body.
        if pos < len(stdout) and stdout[pos:pos + 1] == b"\n":
            pos += 1
        try:
            out[sha][fname] = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            out[sha][fname] = None

    return out


# Heuristic keyword patterns to surface the five categories the spec calls for.
# Best-effort: matches headings (markdown # / ##) whose text contains the keyword.
_AI_CATEGORY_PATTERNS: dict[str, re.Pattern[str]] = {
    "Workflow / methodology": re.compile(
        r"(?im)^\s{0,3}#{1,4}\s+.*\b(workflow|methodology|process|adr|branch|review|speckit|conventional commits)\b.*$",
    ),
    "Sync / offline-first": re.compile(
        r"(?im)^\s{0,3}#{1,4}\s+.*\b(sync|offline|replication|crdt|merge resolution)\b.*$",
    ),
    "Multi-tenant / role scopes": re.compile(
        r"(?im)^\s{0,3}#{1,4}\s+.*\b(multi[- ]?tenant|tenant|rbac|role|scope)\b.*$",
    ),
    "Security / non-negotiable": re.compile(
        r"(?im)^\s{0,3}#{1,4}\s+.*\b(security|rls|gdpr|ccpa|pii|secret|red[- ]line)\b.*$",
    ),
    "Architecture decisions": re.compile(
        r"(?im)^\s{0,3}#{1,4}\s+.*\b(architecture|decision|pattern|invariant|constraint)\b.*$",
    ),
}


def _extract_ai_categories(content: str) -> dict[str, list[str]]:
    """Return matched headings per category. Empty list if no signal."""
    out: dict[str, list[str]] = {}
    for cat, pat in _AI_CATEGORY_PATTERNS.items():
        matches = [m.group(0).strip() for m in pat.finditer(content)]
        # De-duplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for h in matches:
            if h not in seen:
                seen.add(h)
                deduped.append(h)
        if deduped:
            out[cat] = deduped
    return out


def _build_ai_context_section(
    repo: Path,
    sha: str,
    *,
    ai_cache: dict[str, dict[str, str | None]] | None = None,
) -> str:
    """Build the ``## AI files context`` section content.

    If ``ai_cache`` is provided (mapping ``sha -> {filename: content}``),
    reads from it instead of issuing per-file ``git show`` subprocess calls.
    The cache is built upfront via :func:`_prefetch_ai_files_at_commits` to
    amortise subprocess overhead across all milestones in a single pass.

    Falls back to per-file ``git show`` if the cache is ``None`` or doesn't
    contain the requested SHA — preserves backward compatibility for
    callers that don't pre-fetch.

    Always returns content matching the spec invariant (explicit fallback
    line if nothing extractable).
    """
    sha_cache = ai_cache.get(sha) if ai_cache else None
    excerpts: list[str] = []
    for fname in _AI_FILES_TO_READ:
        if sha_cache is not None and fname in sha_cache:
            content = sha_cache[fname]
        else:
            content = _read_at_commit(repo, sha, fname)
        if not content:
            continue
        cats = _extract_ai_categories(content)
        if not cats:
            continue
        excerpts.append(f"### From `{fname}`")
        for cat, headings in cats.items():
            excerpts.append(f"- **{cat}** : {len(headings)} signal(s)")
            for h in headings[:5]:  # cap to 5 per category for brevity
                excerpts.append(f"  - `{h}`")

    if not excerpts:
        return "No AI-files context extracted for this milestone.\n"
    return "\n".join(excerpts) + "\n"


# ----------------------------------------------------------------------
# GitHub releases discovery (level=releases)
# ----------------------------------------------------------------------


def _gh_available() -> bool:
    """Return True if the gh CLI is on PATH and reports an authenticated session."""
    try:
        subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, check=True,
        stdin=subprocess.DEVNULL,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _list_github_releases(
    repo: Path,
    *,
    since: str | None,
    until: str | None,
    warnings: list[str],
) -> list[MilestoneInfo]:
    """Return one MilestoneInfo per GitHub Release in date range."""
    if not _gh_available():
        warnings.append(
            "level='releases' needs the gh CLI on PATH and an authenticated "
            "session (`gh auth status`). Skipping — fall back to skill if needed."
        )
        return []
    try:
        result = subprocess.run(
            [
                "gh", "release", "list",
                "--repo", str(repo),
                "--limit", "200",
                "--json", "tagName,name,publishedAt,url,isPrerelease,isDraft,body",
            ],
            capture_output=True, text=True, check=True, cwd=str(repo),
        stdin=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        warnings.append(f"gh release list failed: {exc.stderr.strip() or exc}")
        return []

    import json
    try:
        raw = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        warnings.append(f"gh release list returned invalid JSON: {exc}")
        return []

    # First pass: filter by date and resolve every release tag's commit SHA in
    # one batch. We can't avoid the per-tag _rev_parse_commit (each tag is its
    # own ref), but we can collect the resulting SHAs and batch-fetch their
    # metadata in one git log call afterwards.
    filtered: list[tuple[dict, str, str]] = []  # (raw_release, tag_name, commit_sha)
    for r in raw:
        tag_name = r.get("tagName") or ""
        published = r.get("publishedAt") or ""
        date_part = published[:10]
        if since and date_part and date_part < since:
            continue
        if until and date_part and date_part > until:
            continue
        sha = _rev_parse_commit(repo, tag_name) if tag_name else ""
        filtered.append((r, tag_name, sha))

    meta_cache = _commit_metadata_batch(
        repo, [sha for _, _, sha in filtered if sha]
    )

    out: list[MilestoneInfo] = []
    for r, tag_name, sha in filtered:
        published = r.get("publishedAt") or ""
        date_part = published[:10]
        if sha:
            base = _commit_metadata(
                repo, sha, fallback_iso=published, cache=meta_cache
            )
        else:
            # Tag missing locally (release pointing at a deleted tag, or fetched
            # only from remote). Build a minimal info from the GH metadata.
            base = MilestoneInfo(
                date=date_part,
                time=_extract_hhmm(published),
                subject=r.get("name") or tag_name,
            )
        base.milestone_kind = "release"
        base.release_tag = tag_name
        base.release_url = r.get("url") or ""
        base.release_is_prerelease = bool(r.get("isPrerelease"))
        base.release_is_draft = bool(r.get("isDraft"))
        # Use release name as the headline subject if non-empty, else the tag.
        base.subject = (r.get("name") or tag_name or base.subject).strip()
        # Stash the body excerpt into the subject_long via a custom attr — we
        # render it in the body builder.
        base.tag = tag_name  # convenience: archives carry the tag in `tag` too
        out.append(base)
    out.sort(key=lambda m: m.date)
    return out


# ----------------------------------------------------------------------
# GitHub merges discovery (level=merges)
# ----------------------------------------------------------------------


def _list_github_merges(
    repo: Path,
    *,
    since: str | None,
    until: str | None,
    warnings: list[str],
) -> list[MilestoneInfo]:
    """Return one MilestoneInfo per merged GitHub PR in date range."""
    if not _gh_available():
        warnings.append(
            "level='merges' needs the gh CLI on PATH and an authenticated "
            "session (`gh auth status`). Skipping — fall back to skill if needed."
        )
        return []
    try:
        result = subprocess.run(
            [
                "gh", "pr", "list",
                "--repo", str(repo),
                "--state", "merged",
                "--limit", "200",
                "--json", "number,title,mergeCommit,mergedAt,baseRefName,headRefName,url,author",
            ],
            capture_output=True, text=True, check=True, cwd=str(repo),
        stdin=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        warnings.append(f"gh pr list failed: {exc.stderr.strip() or exc}")
        return []

    import json
    try:
        raw = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        warnings.append(f"gh pr list returned invalid JSON: {exc}")
        return []

    # First pass: filter by date and collect merge commit SHAs for batch
    # metadata fetch. PRs with squash/rebase merges have no merge commit
    # and stay on the empty-metadata fallback path.
    filtered: list[tuple[dict, str, str]] = []  # (pr, merged_at, merge_commit)
    for pr in raw:
        merged_at = pr.get("mergedAt") or ""
        date_part = merged_at[:10]
        if since and date_part and date_part < since:
            continue
        if until and date_part and date_part > until:
            continue
        merge_commit = (pr.get("mergeCommit") or {}).get("oid") or ""
        filtered.append((pr, merged_at, merge_commit))

    meta_cache = _commit_metadata_batch(
        repo, [sha for _, _, sha in filtered if sha]
    )

    out: list[MilestoneInfo] = []
    for pr, merged_at, merge_commit in filtered:
        date_part = merged_at[:10]
        if merge_commit:
            base = _commit_metadata(
                repo, merge_commit, fallback_iso=merged_at, cache=meta_cache
            )
        else:
            # Squash/rebase merges have no merge commit; use empty metadata.
            base = MilestoneInfo(
                date=date_part,
                time=_extract_hhmm(merged_at),
                subject=pr.get("title") or "",
            )
        base.milestone_kind = "merge"
        base.pr_number = int(pr.get("number") or 0)
        base.pr_url = pr.get("url") or ""
        base.pr_base = pr.get("baseRefName") or ""
        base.pr_head = pr.get("headRefName") or ""
        base.pr_merged_at = merged_at
        base.subject = (pr.get("title") or base.subject).strip()
        # Author from PR if commit author missing
        if not base.author_name and pr.get("author"):
            base.author_name = pr["author"].get("login") or ""
        out.append(base)
    out.sort(key=lambda m: m.date)
    return out


# ----------------------------------------------------------------------
# Commit window discovery (level=commits)
# ----------------------------------------------------------------------

import datetime as _dt  # noqa: E402 — local import keeps top tidy


def _window_label(date_iso: str, window: str) -> tuple[str, str, str]:
    """Return (label, window_start, window_end) for ``date_iso`` (YYYY-MM-DD).

    - day:   label="2026-05-04", start=end=date
    - week:  label="2026-W18",   start=Mon, end=Sun (ISO week)
    - month: label="2026-05",    start=01, end=last-day
    """
    if not date_iso:
        return ("", "", "")
    d = _dt.date.fromisoformat(date_iso)
    if window == "day":
        return (date_iso, date_iso, date_iso)
    if window == "week":
        iso_year, iso_week, iso_dow = d.isocalendar()
        monday = d - _dt.timedelta(days=iso_dow - 1)
        sunday = monday + _dt.timedelta(days=6)
        return (f"{iso_year}-W{iso_week:02d}", monday.isoformat(), sunday.isoformat())
    if window == "month":
        first = d.replace(day=1)
        if d.month == 12:
            next_month = d.replace(year=d.year + 1, month=1, day=1)
        else:
            next_month = d.replace(month=d.month + 1, day=1)
        last = next_month - _dt.timedelta(days=1)
        return (f"{d.year:04d}-{d.month:02d}", first.isoformat(), last.isoformat())
    raise ValueError(f"unknown window {window!r}")


def _list_commit_windows(
    repo: Path,
    *,
    since: str | None,
    until: str | None,
    window: str,
    by_author: bool,
    warnings: list[str],
    rev_range: str | None = None,
) -> list[MilestoneInfo]:
    """Return one MilestoneInfo per (window) — or per (window, author) when
    ``by_author=True``. Uses ``git log --no-merges`` over the requested range.

    When neither ``since`` nor ``rev_range`` is provided, defaults to the last
    30 days to bound the scan.
    """
    cmd = [
        "git", "-C", str(repo), "log", "--no-merges",
        "--format=%H|%an|%ae|%aI|%s",
    ]
    if rev_range:
        cmd.append(rev_range)
    else:
        if not since:
            since = (_dt.date.today() - _dt.timedelta(days=30)).isoformat()
            warnings.append(
                f"level='commits' without --since defaults to last 30 days "
                f"(since={since}). Pass since=YYYY-MM-DD to override."
            )
        cmd.extend([f"--since={since}", "--no-merges"])
        if until:
            cmd.append(f"--until={until} 23:59:59")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        warnings.append(f"git log failed for commits level: {exc}")
        return []

    @dataclass
    class _Commit:
        sha: str
        author_name: str
        author_email: str
        date_iso: str
        subject: str

    commits: list[_Commit] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 4)
        if len(parts) != 5:
            continue
        commits.append(_Commit(*parts))
    if not commits:
        return []

    # Apply rev_range-mode date filtering (since/until still apply when given
    # alongside an explicit branch_first base).
    if rev_range and (since or until):
        commits = [
            c for c in commits
            if (not since or c.date_iso[:10] >= since)
            and (not until or c.date_iso[:10] <= until)
        ]

    # Collect Co-Authored-By trailers per commit (best-effort, single git call).
    co_by_sha = _co_authors_for_commits(repo, [c.sha for c in commits])

    # Group by (window_label, author_email) when by_author, else by window only.
    groups: dict[tuple[str, str], list[_Commit]] = {}
    group_meta: dict[tuple[str, str], tuple[str, str]] = {}  # window_start, window_end
    for c in commits:
        date_part = c.date_iso[:10]
        label, w_start, w_end = _window_label(date_part, window)
        key = (label, c.author_email if by_author else "")
        groups.setdefault(key, []).append(c)
        group_meta[key] = (w_start, w_end)

    # Pre-compute representatives so we can batch-fetch their metadata in
    # a single git log call instead of N forks.
    reps: dict[tuple[str, str], _Commit] = {
        key: max(members, key=lambda c: c.date_iso)
        for key, members in groups.items()
    }
    meta_cache = _commit_metadata_batch(repo, [r.sha for r in reps.values()])

    out: list[MilestoneInfo] = []
    for (label, author_key), members in groups.items():
        rep = reps[(label, author_key)]
        w_start, w_end = group_meta[(label, author_key)]
        # Aggregate co-authors across the group.
        co_authors: list[str] = []
        seen: set[str] = set()
        for c in members:
            for ca in co_by_sha.get(c.sha, []):
                if ca and ca not in seen and ca != rep.author_email:
                    seen.add(ca)
                    co_authors.append(ca)
        info = _commit_metadata(
            repo, rep.sha, fallback_iso=rep.date_iso, cache=meta_cache
        )
        info.milestone_kind = "window"
        info.window_label = label
        info.window_start = w_start
        info.window_end = w_end
        info.commit_count = len(members)
        info.co_authors = co_authors
        if not info.subject:
            info.subject = rep.subject
        # When by_author, append the author email to the label for uniqueness.
        if by_author and author_key:
            info.window_label = f"{label}-{author_key}"
        out.append(info)
    out.sort(key=lambda m: (m.window_start, m.window_label))
    return out


def _co_authors_for_commits(repo: Path, shas: list[str]) -> dict[str, list[str]]:
    """Return {sha: [co-author emails]} extracted from ``Co-Authored-By:`` trailers."""
    if not shas:
        return {}
    out: dict[str, list[str]] = {sha: [] for sha in shas}
    cmd = [
        "git", "-C", str(repo), "log",
        "--format=%H%x00%(trailers:key=Co-authored-by,valueonly,unfold,separator=%x1f)",
        "--no-walk",
    ] + shas
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return out
    email_re = re.compile(r"<([^>]+)>")
    for line in result.stdout.splitlines():
        if "\x00" not in line:
            continue
        sha, trailer_blob = line.split("\x00", 1)
        if sha not in out:
            continue
        for trailer in trailer_blob.split("\x1f"):
            m = email_re.search(trailer)
            if m:
                out[sha].append(m.group(1))
    return out


# ----------------------------------------------------------------------
# Branch-first mode
# ----------------------------------------------------------------------


@dataclass
class _BranchContext:
    branch: str
    base: str
    base_sha: str  # divergence point — semantics depend on `mode` below
    # Mode values:
    #   'live'                    — branch not fully merged; merge_base..branch is the range
    #   'merged-via-merge-commit' — branch fully merged AND the absorbing merge commit M
    #                               is detectable on base first-parent. base_sha = M^1
    #                               (merge_base at merge time), head_ref = M^2 (= branch tip).
    #                               Range = base_sha..head_ref = commits unique to the absorbed
    #                               branch. Deterministic; replaces by-name as primary
    #                               strategy whenever possible.
    #   'since-sha'               — explicit anchor via since_sha
    #   'since-date'              — explicit anchor via since_date
    #   'by-files'                — scope = files introduced by the branch (--diff-filter=A)
    #   'auto-scope-by-name'      — fallback when the merge commit was lost to squash/rebase;
    #                               scope derived from branch name heuristic matching repo dirs
    mode: str = "live"
    files: list[str] = field(default_factory=list)  # populated when mode='by-files' or 'auto-scope-by-name'
    scope_glob: str | None = None  # populated when mode='auto-scope-by-name'
    # When mode='merged-via-merge-commit', head_ref = M (the merge commit
    # itself). Range = base_sha..head_ref. Other modes use branch as the
    # range tip and leave this empty.
    head_ref: str = ""
    # When mode='merged-via-perimeter', the multi-signal walker captured
    # ≥1 merge cycles (handles dev-reset workflows). Phase 3 emits one
    # archive per captured merge instead of treating the branch as a
    # contiguous range.
    captured_merges: list[BranchMerge] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # human-readable explanation


def _first_parent_ancestors(repo: Path, ref: str) -> list[str]:
    """Return the first-parent ancestor chain of ``ref`` (most recent first).

    Used to find the historical divergence point between two branches even
    when they have been fully merged (``git merge-base`` reports the merge
    point in that case, which is HEAD of the branch and useless for
    archeology).
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-list", "--first-parent", ref],
            capture_output=True, text=True, check=True,
        stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _first_parent_divergence_point(
    repo: Path, branch: str, base: str,
) -> str | None:
    """Return the most recent first-parent ancestor common to ``branch`` and ``base``.

    Unlike ``git merge-base``, this gives a stable historical anchor even when
    the branch has been fully merged into the base — the merge-back commit is
    skipped because it appears as a non-first-parent on the base lineage.

    None if no common first-parent ancestor (disjoint histories).
    """
    branch_chain = _first_parent_ancestors(repo, branch)
    if not branch_chain:
        return None
    base_set = set(_first_parent_ancestors(repo, base))
    if not base_set:
        return None
    for sha in branch_chain:
        if sha in base_set:
            return sha
    return None


def _branch_specific_files(repo: Path, branch: str, base_sha: str) -> list[str]:
    """Return the files INTRODUCED by the branch's first-parent lineage since
    ``base_sha`` — i.e. files that did not exist before the branch and were
    added on it. Used by the by-files strategy to derive a stable "scope of
    files this branch is about", which then drives a wider commit query.

    Heuristic: ``git log --first-parent --diff-filter=A --name-only`` over
    ``base_sha..branch``. Captures ``A`` (added) entries; ``M`` (modified)
    is intentionally excluded — modifications on the branch don't make a
    file "branch-specific".
    """
    if not base_sha:
        return []
    try:
        result = subprocess.run(
            [
                "git", "-C", str(repo), "log", "--first-parent",
                "--diff-filter=A", "--name-only", "--format=",
                f"{base_sha}..{branch}",
            ],
            capture_output=True, text=True, check=True,
        stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    files = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return sorted(files)


class BranchScopeUnresolvedError(RuntimeError):
    """Raised when a branch-first archeo run cannot resolve a meaningful scope.

    Triggered when the branch is fully merged into its base AND no anchor
    (``since_sha`` / ``since_date`` / ``scope_glob``) was provided AND the
    name-based heuristic returned no candidate directory in the repo.

    The previous v0.10.0 strategy A "first-parent fallback" used to dive
    into the base branch's history at this point, producing a sloppy
    1000+-commit scope that the user almost never wanted (case study:
    ``ecosav`` on the IRIS USER repo). That fallback was retired in
    v0.10.x post-Codex case study (see ``_archeo-architecture-v2.md``
    Principe 2 amendment).
    """


_BRANCH_PREFIX_RE = re.compile(
    r"^(feat|feature|fix|chore|hotfix|release|bugfix|task|story|epic)[-/]",
    re.IGNORECASE,
)


def _generate_name_variants(name: str) -> list[str]:
    """Generate plausible directory-name variants for a branch name.

    Used by :func:`_suggest_scope_from_branch_name` to match branch names
    like ``ecosav`` against directories like ``EcoSAV``, ``eco-sav``,
    ``ECOSAV``, etc. Strips common git-flow prefixes (``feat/``, ``fix/``)
    before generating variants.

    Order of returned variants is informational only — the caller filters
    against actual repo directories and ranks by depth.
    """
    bare = _BRANCH_PREFIX_RE.sub("", name).strip("-/_ ")
    if not bare:
        return []

    seeds: set[str] = {bare}

    # Split on common separators to get tokens.
    tokens = re.split(r"[-_/ ]+", bare)
    tokens = [t for t in tokens if t]
    if not tokens:
        return []

    # Variants: kebab, snake, camelCase, PascalCase, UPPER, lower, concatenated.
    seeds.add("-".join(tokens))
    seeds.add("_".join(tokens))
    seeds.add("".join(t.lower() for t in tokens))
    seeds.add("".join(t.capitalize() for t in tokens))
    seeds.add(tokens[0].lower() + "".join(t.capitalize() for t in tokens[1:]))
    seeds.add("-".join(t.lower() for t in tokens))
    seeds.add("-".join(t.capitalize() for t in tokens))
    seeds.add("".join(tokens).upper())
    seeds.add("".join(tokens).lower())

    # Drop duplicates, drop too-short tokens (1-2 chars match too liberally).
    out = sorted({s for s in seeds if len(s) >= 3})
    return out


def _suggest_scope_from_branch_name(
    repo: Path, branch: str
) -> list[str]:
    """Find repo directories whose name matches a variant of the branch name.

    Returns POSIX-relative directory paths sorted by depth (deepest first =
    most specific). Best-effort: no match guarantees a single ``/``-rooted
    fold-case match — falls through silently if nothing is found, leaving
    the caller free to raise :class:`BranchScopeUnresolvedError`.

    Implementation: ``git ls-tree -r -d --name-only HEAD`` lists every
    directory tracked at HEAD; we filter to those whose **last** path
    component matches one of the variants (case-insensitive).
    """
    variants = _generate_name_variants(branch)
    if not variants:
        return []
    variants_lower = {v.lower() for v in variants}

    try:
        result = subprocess.run(
            [
                "git", "-C", str(repo), "ls-tree", "-r", "-d", "--name-only", "HEAD",
            ],
            capture_output=True, text=True, check=True,
        stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    matches: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        last = line.rsplit("/", 1)[-1]
        if last.lower() in variants_lower:
            matches.append(line)

    # Sort by depth descending (more `/` = deeper = more specific), then alphabetically.
    matches.sort(key=lambda p: (-p.count("/"), p))
    return matches


def _resolve_branch_context(
    repo: Path,
    branch: str,
    base: str,
    *,
    since_sha: str | None = None,
    since_date: str | None = None,
    by_files: bool = False,
) -> _BranchContext | None:
    """Resolve the working scope of a branch-first archeo run.

    Resolution priority (post-v0.10.x amendment, see
    ``core/procedures/_archeo-architecture-v2.md`` Principe 2):

    1. ``since_sha`` provided → mode ``'since-sha'``. Bypass merge-base.
    2. ``since_date`` provided → mode ``'since-date'``. Bypass merge-base.
    3. ``git merge-base <base> <branch>`` distinct from ``HEAD(branch)`` →
       mode ``'live'``. Standard range-strict path.
    4. Branch fully merged (merge-base == HEAD(branch)) →
       a. ``by_files=True``: derive branch-specific files via
          ``--first-parent --diff-filter=A`` over ``merge_base..branch``.
          If non-empty, mode = ``'by-files'``. If empty, fall through to (b).
       b. Try :func:`_suggest_scope_from_branch_name`. If at least one
          directory matches → mode = ``'auto-scope-by-name'``.
       c. Otherwise raise :class:`BranchScopeUnresolvedError`. **No
          first-parent fallback.** The caller (or the LLM) must provide an
          explicit anchor (``since_sha`` / ``since_date`` / ``scope_glob``)
          or accept that the branch has no archivable scope.

    The first-parent-fallback strategy from v0.10.0 was retired here — it
    silently scoped to base-branch history (often 1000+ commits) and
    produced sloppy archives. The Codex case study on ``ecosav`` made the
    pattern obvious.

    Returns ``None`` only when refs (``branch``, ``base``, ``since_sha``)
    can't be resolved — that's a hard usage error, distinct from the
    "fully merged branch" case which raises.
    """
    if not _rev_parse_commit(repo, branch):
        return None

    # Escape hatch (C): explicit since_sha bypasses base resolution.
    if since_sha:
        if not _rev_parse_commit(repo, since_sha):
            return None
        ctx = _BranchContext(
            branch=branch, base=base, base_sha=since_sha,
            mode="since-sha",
            notes=[f"explicit since_sha={since_sha[:12]} bypasses merge-base"],
        )
        if by_files:
            ctx.files = _branch_specific_files(repo, branch, since_sha)
            ctx.mode = "by-files"
            ctx.notes.append(
                f"by_files mode: {len(ctx.files)} branch-specific file(s) detected"
            )
        return ctx

    # Escape hatch (C, alt): explicit since_date.
    if since_date:
        ctx = _BranchContext(
            branch=branch, base=base, base_sha="",
            mode="since-date",
            notes=[f"explicit since_date={since_date} drives the floor"],
        )
        if by_files:
            mb = subprocess.run(
                ["git", "-C", str(repo), "merge-base", base, branch],
                capture_output=True, text=True,
            stdin=subprocess.DEVNULL,
            )
            if mb.returncode == 0:
                fallback_base = mb.stdout.strip()
                ctx.files = _branch_specific_files(repo, branch, fallback_base)
                ctx.mode = "by-files"
                ctx.notes.append(
                    f"by_files mode (since_date set): {len(ctx.files)} file(s) "
                    f"derived via merge-base for the file detection step"
                )
        return ctx

    # Standard path: need base ref to exist for merge-base.
    if not _rev_parse_commit(repo, base):
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "merge-base", base, branch],
            capture_output=True, text=True, check=True,
        stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    merge_base = result.stdout.strip()
    if not merge_base:
        return None

    branch_head = _rev_parse_commit(repo, branch)

    # Live branch (not fully merged): standard path.
    if merge_base != branch_head:
        ctx = _BranchContext(
            branch=branch, base=base, base_sha=merge_base, mode="live",
        )
        if by_files:
            ctx.files = _branch_specific_files(repo, branch, merge_base)
            ctx.mode = "by-files"
            ctx.notes.append(
                f"by_files mode: {len(ctx.files)} branch-specific file(s) detected"
            )
        return ctx

    # Fully merged branch: try perimeter walker FIRST (handles dev-reset
    # cycles via multi-signal scoring), then single-tip merge-commit,
    # then by-files (if requested), then auto-scope-by-name, else raise.
    captured = find_branch_merges_via_perimeter(repo, branch, base)
    if captured:
        notes = [
            f"branch fully merged into {base}; perimeter walker captured "
            f"{len(captured)} merge cycle(s) (multi-signal scoring: file "
            "overlap with reciprocity + author match + subject match). "
            "Handles dev-reset workflows (branch reset to origin/base "
            "between cycles). Per-merge audit:",
        ]
        for bm in captured:
            notes.append(
                f"  - M={bm.sha[:12]} score={bm.score:.2f} "
                f"file={bm.breakdown['file_score']:.2f} "
                f"author={bm.breakdown['author_score']:.2f} "
                f"subject={bm.breakdown['subject_score']:.2f} "
                f"({len(bm.files)} file(s)) — {bm.subject[:80]}"
            )
        return _BranchContext(
            branch=branch, base=base,
            base_sha=captured[0].parent1,  # first cycle anchor
            mode="merged-via-perimeter",
            captured_merges=captured,
            notes=notes,
        )

    merge_info = find_merge_commit_for_branch(repo, branch, base)
    if merge_info is not None:
        m_sha, parent1, parent2 = merge_info
        return _BranchContext(
            branch=branch, base=base, base_sha=parent1,
            mode="merged-via-merge-commit",
            head_ref=m_sha,
            notes=[
                f"branch fully merged into {base}; absorbing merge commit "
                f"detected on base first-parent: M={m_sha[:12]}, "
                f"M^1={parent1[:12]} (merge_base at merge time), "
                f"M^2={parent2[:12]} (= branch tip). Range = "
                f"{parent1[:12]}..{m_sha[:12]} = commits unique to the "
                "absorbed branch (deterministic, no name heuristic).",
            ],
        )

    if by_files:
        ctx_files = _branch_specific_files(repo, branch, merge_base)
        if ctx_files:
            return _BranchContext(
                branch=branch, base=base, base_sha=merge_base,
                mode="by-files",
                files=ctx_files,
                notes=[
                    f"branch fully merged into {base}; by_files mode "
                    f"detected {len(ctx_files)} file(s) introduced by the branch",
                ],
            )

    suggested_dirs = _suggest_scope_from_branch_name(repo, branch)
    if suggested_dirs:
        # Keep the deepest match as the primary scope; surface the rest as
        # alternates the caller can override via scope_glob if needed.
        primary = suggested_dirs[0]
        glob = f"{primary}/**"
        notes = [
            f"branch fully merged into {base}; auto-scope-by-name matched "
            f"directory '{primary}' (variants tried: {_generate_name_variants(branch)})",
        ]
        if len(suggested_dirs) > 1:
            notes.append(
                f"alternate matches available: {suggested_dirs[1:]}; pass "
                f"scope_glob explicitly to override"
            )
        return _BranchContext(
            branch=branch, base=base, base_sha=merge_base,
            mode="auto-scope-by-name",
            scope_glob=glob,
            files=[primary],  # surface as the primary scoped path
            notes=notes,
        )

    raise BranchScopeUnresolvedError(
        f"branch '{branch}' is fully merged into '{base}' AND no absorbing "
        f"merge commit was found on '{base}' first-parent (squash or rebase + "
        f"ff erased the merge) AND the name does not match any directory in "
        f"the repo. Provide one of:\n"
        f"  - scope_glob='<glob>'                 (e.g. 'src/Module/**')\n"
        f"  - since_sha=<sha>                     (commit before the "
        f"branch's specialisation)\n"
        f"  - since_date=YYYY-MM-DD               (date floor)\n"
        f"Auto-scope by name tried variants: {_generate_name_variants(branch)}.\n"
        f"No first-parent fallback is attempted (retired v0.10.x — produced "
        f"sloppy scopes diving into the base branch history)."
    )


def _discover_branch_first(
    repo: Path,
    branch_ctx: _BranchContext,
    *,
    level: str,
    window: str,
    by_author: bool,
    since: str | None,
    until: str | None,
    warnings: list[str],
) -> list[MilestoneInfo]:
    """Branch-first discovery — covers five modes:

    - ``'live'``: branch not fully merged; enumerate commits in
      ``merge_base..branch`` rev-range, group per window + by_author.
    - ``'since-sha'`` / ``'since-date'``: explicit anchors, same enumeration
      as ``'live'`` but with a user-supplied floor.
    - ``'by-files'``: derive the branch-specific files (set on the context)
      and query commits TOUCHING those files repo-wide — captures the full
      lineage (creation, evolution, post-merge fixes on the same files).
    - ``'auto-scope-by-name'``: branch fully merged AND name-based heuristic
      matched a repo directory; treated like ``'by-files'`` but the scope is
      a single directory rather than a list of files. Replaces the retired
      ``'merged-fallback'`` mode (v0.10.x post-Codex case study).
    - **merges**: enumerate merge commits in the rev-range.
    - **tags / releases**: meaningless on a branch scope; warn and fall back
      to commits-by-author.
    """
    # Surface context notes to the caller so they understand the resolution.
    for note in branch_ctx.notes:
        warnings.append(f"branch-first: {note}")

    # Perimeter-walker mode: emit one milestone per captured merge cycle
    # directly. Bypasses the rev_range path because the captured merges
    # are NOT contiguous in master history (they're separated by reset
    # cycles). Each archive corresponds to one merge cycle of the branch.
    if branch_ctx.mode == "merged-via-perimeter":
        if not branch_ctx.captured_merges:
            warnings.append(
                "merged-via-perimeter mode: captured_merges empty (should "
                "not happen; mode requires ≥1 captured merge). Falling back."
            )
            return []
        return _list_perimeter_merge_milestones(
            repo, branch_ctx, warnings=warnings,
        )

    # By-files / auto-scope-by-name: query commits that TOUCHED any of the
    # branch-specific paths (files for by-files, a directory for
    # auto-scope-by-name), repo-wide — not constrained to a rev-range.
    # Captures creation, evolution on/off the branch, and post-merge fixes.
    # Honours since/until date filters.
    if branch_ctx.mode in ("by-files", "auto-scope-by-name"):
        if not branch_ctx.files:
            warnings.append(
                "by_files mode: no branch-specific files detected. "
                "Branch may be empty, or all changes were modifications of "
                "pre-existing files (heuristic uses --diff-filter=A only)."
            )
            return []
        return _list_commits_for_files(
            repo, branch_ctx.files, since=since, until=until,
            window=window, by_author=by_author or True, warnings=warnings,
        )

    # Resolve the rev-range used by the standard branch-first paths.
    if branch_ctx.mode == "since-date":
        # No base_sha — use git log directly with --since on the branch tip.
        rev_range = branch_ctx.branch
    elif branch_ctx.mode == "merged-via-merge-commit":
        # head_ref = M (the absorbing merge commit), base_sha = M^1.
        # Range = M^1..M = commits unique to the absorbed branch + M itself.
        rev_range = f"{branch_ctx.base_sha}..{branch_ctx.head_ref}"
    else:
        rev_range = f"{branch_ctx.base_sha}..{branch_ctx.branch}"

    if level == "commits":
        # Default --by-author when branch-first per spec v0.7.1.
        return _list_commit_windows(
            repo, since=since, until=until, window=window,
            by_author=by_author or True,
            warnings=warnings, rev_range=rev_range,
        )
    if level == "merges":
        return _list_branch_merges(
            repo, branch_ctx, since=since, until=until, warnings=warnings,
        )
    if level == "tags":
        warnings.append(
            "Branch-first mode with level='tags' is meaningless (tags are "
            "repo-wide). Defaulting to commits-by-author on the branch range."
        )
        return _list_commit_windows(
            repo, since=since, until=until, window=window, by_author=True,
            warnings=warnings, rev_range=rev_range,
        )
    if level == "releases":
        warnings.append(
            "Branch-first mode with level='releases' is meaningless (releases "
            "are repo-wide). Defaulting to commits-by-author on the branch range."
        )
        return _list_commit_windows(
            repo, since=since, until=until, window=window, by_author=True,
            warnings=warnings, rev_range=rev_range,
        )
    raise AssertionError(f"unreachable: level={level!r}")


def _list_commits_for_files(
    repo: Path,
    files: list[str],
    *,
    since: str | None,
    until: str | None,
    window: str,
    by_author: bool,
    warnings: list[str],
) -> list[MilestoneInfo]:
    """Enumerate every commit (repo-wide) that touched any of the given files,
    then group them per window/by-author the same way ``_list_commit_windows``
    does. Used by branch-first mode ``by-files``.

    Caveat: ``--follow`` only works on a single path in git. We use a plain
    pathspec query instead — meaning renames before the rev-range are not
    tracked. Acceptable trade-off for a v0.9.x port; real ``--follow``
    multi-file would need per-file iteration.
    """
    if not files:
        return []
    cmd = [
        "git", "-C", str(repo), "log", "--no-merges",
        "--format=%H|%an|%ae|%aI|%s",
    ]
    if since:
        cmd.append(f"--since={since}")
    if until:
        cmd.append(f"--until={until} 23:59:59")
    cmd.append("--")
    cmd.extend(files)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        warnings.append(f"git log on branch-specific files failed: {exc}")
        return []

    @dataclass
    class _Commit:
        sha: str
        author_name: str
        author_email: str
        date_iso: str
        subject: str

    commits: list[_Commit] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 4)
        if len(parts) != 5:
            continue
        commits.append(_Commit(*parts))
    if not commits:
        return []

    co_by_sha = _co_authors_for_commits(repo, [c.sha for c in commits])

    groups: dict[tuple[str, str], list[_Commit]] = {}
    group_meta: dict[tuple[str, str], tuple[str, str]] = {}
    for c in commits:
        date_part = c.date_iso[:10]
        label, w_start, w_end = _window_label(date_part, window)
        key = (label, c.author_email if by_author else "")
        groups.setdefault(key, []).append(c)
        group_meta[key] = (w_start, w_end)

    reps: dict[tuple[str, str], _Commit] = {
        key: max(members, key=lambda c: c.date_iso)
        for key, members in groups.items()
    }
    meta_cache = _commit_metadata_batch(repo, [r.sha for r in reps.values()])

    out: list[MilestoneInfo] = []
    for (label, author_key), members in groups.items():
        rep = reps[(label, author_key)]
        w_start, w_end = group_meta[(label, author_key)]
        co_authors: list[str] = []
        seen: set[str] = set()
        for c in members:
            for ca in co_by_sha.get(c.sha, []):
                if ca and ca not in seen and ca != rep.author_email:
                    seen.add(ca)
                    co_authors.append(ca)
        info = _commit_metadata(
            repo, rep.sha, fallback_iso=rep.date_iso, cache=meta_cache
        )
        info.milestone_kind = "window"
        info.window_label = label
        info.window_start = w_start
        info.window_end = w_end
        info.commit_count = len(members)
        info.co_authors = co_authors
        if not info.subject:
            info.subject = rep.subject
        if by_author and author_key:
            info.window_label = f"{label}-{author_key}"
        out.append(info)
    out.sort(key=lambda m: (m.window_start, m.window_label))
    return out


def _list_perimeter_merge_milestones(
    repo: Path,
    branch_ctx: _BranchContext,
    *,
    warnings: list[str],
) -> list[MilestoneInfo]:
    """Emit one MilestoneInfo per captured BranchMerge.

    Used when ``branch_ctx.mode == 'merged-via-perimeter'``. Each milestone
    represents one full merge cycle of the branch (handles dev-reset
    workflows where the branch was reset to ``origin/base`` between cycles).
    """
    out: list[MilestoneInfo] = []
    shas = [bm.sha for bm in branch_ctx.captured_merges]
    meta_cache = _commit_metadata_batch(repo, shas)
    for bm in branch_ctx.captured_merges:
        info = _commit_metadata(repo, bm.sha, fallback_iso="", cache=meta_cache)
        info.milestone_kind = "merge"
        info.pr_base = branch_ctx.base
        info.pr_head = branch_ctx.branch
        info.subject = info.subject or bm.subject or f"merge into {branch_ctx.base}"
        # Perimeter audit fields — surfaced in body + frontmatter so the
        # user can audit the walker's decision per cycle.
        info.perimeter_score = bm.score
        info.perimeter_breakdown = dict(bm.breakdown)
        info.perimeter_files = sorted(bm.files)
        info.perimeter_range = bm.range
        out.append(info)
    out.sort(key=lambda m: m.date)
    return out


def _list_branch_merges(
    repo: Path,
    branch_ctx: _BranchContext,
    *,
    since: str | None,
    until: str | None,
    warnings: list[str],
) -> list[MilestoneInfo]:
    """Enumerate merge commits unique to the branch since divergence."""
    if branch_ctx.mode == "merged-via-merge-commit" and branch_ctx.head_ref:
        rev_range = f"{branch_ctx.base_sha}..{branch_ctx.head_ref}"
    else:
        rev_range = f"{branch_ctx.base_sha}..{branch_ctx.branch}"
    cmd = [
        "git", "-C", str(repo), "log", "--merges", rev_range,
        "--format=%H|%aI",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        warnings.append(f"git log --merges failed: {exc}")
        return []
    # Collect all merge commit SHAs first so we can batch-fetch their metadata
    # in a single git log call instead of one fork per merge.
    candidates: list[tuple[str, str]] = []  # (sha, iso)
    for line in result.stdout.splitlines():
        if "|" not in line:
            continue
        sha, iso = line.split("|", 1)
        date_part = iso[:10]
        if since and date_part and date_part < since:
            continue
        if until and date_part and date_part > until:
            continue
        candidates.append((sha, iso))

    meta_cache = _commit_metadata_batch(repo, [sha for sha, _ in candidates])

    out: list[MilestoneInfo] = []
    for sha, iso in candidates:
        info = _commit_metadata(repo, sha, fallback_iso=iso, cache=meta_cache)
        info.milestone_kind = "merge"
        info.pr_base = branch_ctx.base
        info.pr_head = branch_ctx.branch
        info.subject = info.subject or f"merge into {branch_ctx.branch}"
        out.append(info)
    out.sort(key=lambda m: m.date)
    return out


# ----------------------------------------------------------------------
# Archive write + idempotence
# ----------------------------------------------------------------------


def _resolve_project_slug(vault: Path, repo: Path, explicit: str | None) -> str:
    """Resolve the target project slug.

    With an explicit slug, trust the caller — Phase 5 will auto-init the
    project skeleton if it doesn't exist yet. Without an explicit slug,
    refuse to guess past basename(repo) (still requires the project to
    exist already in the vault — auto-init for an inferred slug would risk
    creating typo'd / mis-classified projects without user oversight,
    exactly the 2026-05-08 Gemini drift).
    """
    if explicit:
        return explicit
    candidate = repo.name
    if (vault / "10-episodes" / "projects" / candidate).is_dir():
        return candidate
    raise ValueError(
        f"Cannot auto-resolve target project slug for repo {repo.name!r}. "
        f"No project named {candidate!r} exists in {paths.ZONE_EPISODES}/projects/. "
        "Pass `project=<slug>` explicitly (Phase 5 will auto-init the skeleton), "
        "or create the project via mem_init_project first."
    )


def _scan_existing_milestones(vault: Path, slug: str) -> dict[str, dict[str, Any]]:
    """Index existing archives by source_milestone.

    Returns {milestone_value: {'path': Path, 'fm': dict, 'body': str}}.
    """
    archives_dir = vault / "10-episodes" / "projects" / slug / "archives"
    out: dict[str, dict[str, Any]] = {}
    if not archives_dir.is_dir():
        return out
    for f in archives_dir.iterdir():
        if not f.is_file() or f.suffix != ".md":
            continue
        try:
            fm, body = frontmatter.read(f)
        except (ValueError, OSError):
            continue
        if fm.get("source") != "archeo-git":
            continue
        ms = fm.get("source_milestone")
        if isinstance(ms, str) and ms:
            out[ms] = {"path": f, "fm": fm, "body": body}
    return out


_FILENAME_SAN_RE = re.compile(r"[^a-z0-9-]+")


def _sanitize_for_filename(text: str) -> str:
    """Lowercase + dot-to-dash + collapse non-alphanum runs. v0.8.0 -> v0-8-0."""
    s = text.lower().replace(".", "-").replace("@", "-at-")
    s = _FILENAME_SAN_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _milestone_id(info: MilestoneInfo) -> str:
    """Idempotence key written to ``source_milestone`` and re-checked on next run."""
    if info.milestone_kind == "tag":
        return info.tag
    if info.milestone_kind == "release":
        return f"release-{info.release_tag or info.tag}"
    if info.milestone_kind == "merge":
        return f"pr-#{info.pr_number}" if info.pr_number else f"merge-{info.commit_sha[:12]}"
    if info.milestone_kind == "window":
        return f"window-{info.window_label}"
    return info.commit_sha[:12] or "unknown"


def _archive_filename(slug: str, info: MilestoneInfo) -> str:
    time_part = info.time.replace(":", "h") if info.time else "00h00"
    if info.milestone_kind == "tag":
        suffix = _sanitize_for_filename(info.tag) or "tag"
    elif info.milestone_kind == "release":
        suffix = "release-" + (_sanitize_for_filename(info.release_tag or info.tag) or "release")
    elif info.milestone_kind == "merge":
        if info.pr_number:
            suffix = f"merge-pr-{info.pr_number}"
        else:
            suffix = f"merge-{info.commit_sha[:12]}" if info.commit_sha else "merge"
    elif info.milestone_kind == "window":
        suffix = "window-" + (_sanitize_for_filename(info.window_label) or "window")
    else:
        suffix = "unknown"
    return f"{info.date}-{time_part}-{slug}-archeo-git-{suffix}.md"


def _build_body(
    repo: Path,
    slug: str,
    info: MilestoneInfo,
    *,
    ai_cache: dict[str, dict[str, str | None]] | None = None,
) -> str:
    """Build the archive body. Five mandatory sections, always present per the
    v0.10.x doctrine (extends the v0.7.0 invariant):

    1. Headline metadata (date, author, commit SHA, diff stats — kind-specific).
    2. **Analyse fonctionnelle** — what changed for the user/business. Empty
       skeleton with explicit fallback ; the LLM is doctrinally expected to
       enrich this section post-write when material warrants narrative.
    3. **Analyse technique** — how the change is implemented (layer touched,
       pattern, side-effects, risks). Same skeleton+fallback contract.
    4. **AI files context** — verbatim contents of the project's AI files
       (CLAUDE.md / AGENTS.md / GEMINI.md / MISTRAL.md / README.md) at the
       time of the representative commit. Pre-computed by the AI cache.
    5. **Friction & Resolution** — surfaced when ≥3 successive commits target
       the same theme (heuristic deferred ; explicit fallback line in body).

    The 2026-05-08 Gemini case study showed mechanical archives ("subject Git
    + diff stats" only) lose all narrative value. The 2 new sections force
    the LLM to either fill them with judgment OR explicitly mark them empty
    via the fallback marker — no silent omission possible.
    """
    ai_section = (
        _build_ai_context_section(repo, info.commit_sha, ai_cache=ai_cache)
        if info.commit_sha
        else "No commit SHA resolved for this milestone — AI files context unavailable.\n"
    )
    head = _milestone_headline(info)

    # Perimeter-mode milestones carry a list of files touched in the cycle
    # range. Pre-fill Analyse technique with mechanical extraction (class
    # names, method signatures, top docstrings, schema lines) so the
    # archive carries actual file content, not placeholder markers. The
    # 2026-05-09 IRIS USER case study showed that "subject + diff stats"
    # alone strips all narrative value from the archive.
    perimeter_audit = ""
    if info.perimeter_files and info.commit_sha:
        summaries, truncated = summarize_files(
            repo, info.commit_sha, info.perimeter_files
        )
        technical_block = render_technical_section(summaries, truncated)
        if info.perimeter_score:
            bd = info.perimeter_breakdown or {}
            perimeter_audit = (
                f"\n\n## Perimeter walker audit\n\n"
                f"- **Score** : `{info.perimeter_score:.2f}` "
                f"(threshold 0.4)\n"
                f"- **Breakdown** : "
                f"file=`{bd.get('file_score', 0):.2f}` · "
                f"author=`{bd.get('author_score', 0):.2f}` · "
                f"subject=`{bd.get('subject_score', 0):.2f}`\n"
                f"- **Range** : `{info.perimeter_range}`\n"
                f"- **Files in cycle** : {len(info.perimeter_files)}"
            )
        functional_block = (
            f"_Cycle covers {len(info.perimeter_files)} file(s) "
            f"({info.commit_count or 'n'} commit(s) in range "
            f"`{info.perimeter_range or info.pr_head + '→' + info.pr_base}`)._\n\n"
            f"_(LLM verifier — synthesize the user-facing / business intent "
            f"of this cycle from the file list below + commit subjects. "
            f"What feature was delivered? What bug was fixed? Replace this "
            f"paragraph with a one-line narrative.)_"
        )
    else:
        technical_block = (
            "_(LLM TODO — describe how the change is implemented : layer touched, "
            "pattern introduced, dependencies added/removed, side-effects, risks, "
            "perf implications. Surface anything an experienced engineer reading "
            "the diff would want to know in 30 seconds. If the diff is trivial "
            "(typo, format), replace with a one-liner saying so.)_"
        )
        functional_block = (
            "_(LLM TODO — surface the user-facing / business intent of this milestone : "
            "what changed for the user, what feature was delivered, what bug was fixed, "
            "what behaviour was altered. Strip technical detail — that lives in the "
            "next section. If genuinely no functional impact (refactor, tooling, doc), "
            "replace this paragraph with a one-liner saying so.)_"
        )

    return (
        f"{head}{perimeter_audit}\n\n"
        f"## Analyse fonctionnelle\n\n"
        f"{functional_block}\n\n"
        f"## Analyse technique\n\n"
        f"{technical_block}\n\n"
        f"## AI files context\n\n"
        f"{ai_section}\n"
        f"## Friction & Resolution\n\n"
        f"No friction detected for this milestone.\n\n"
        f"_(Friction detection deferred — fall back to skill for ≥3 commits same theme heuristic.)_\n"
    )


def _milestone_headline(info: MilestoneInfo) -> str:
    """Render the Main section that opens the archive — kind-specific."""
    common = (
        f"**Date** : {info.date} {info.time}\n"
        f"**Author** : {info.author_name} <{info.author_email}>\n"
        f"**Commit SHA** : `{info.commit_sha}`\n"
        f"**Subject** : {info.subject}\n"
        f"**Diff stats** : {info.files_changed} files changed, "
        f"+{info.insertions} / -{info.deletions}"
    )
    if info.milestone_kind == "tag":
        return f"# Milestone archive — {info.tag}\n\n{common}"
    if info.milestone_kind == "release":
        flags = []
        if info.release_is_prerelease:
            flags.append("prerelease")
        if info.release_is_draft:
            flags.append("draft")
        flags_str = f" _({', '.join(flags)})_" if flags else ""
        url_line = f"\n**Release URL** : <{info.release_url}>" if info.release_url else ""
        return (
            f"# Release archive — {info.release_tag or info.tag}{flags_str}\n\n"
            f"{common}{url_line}"
        )
    if info.milestone_kind == "merge":
        url_line = f"\n**PR URL** : <{info.pr_url}>" if info.pr_url else ""
        branches_line = (
            f"\n**Branches** : `{info.pr_head}` → `{info.pr_base}`"
            if (info.pr_head or info.pr_base) else ""
        )
        merged_line = f"\n**Merged at** : {info.pr_merged_at}" if info.pr_merged_at else ""
        return (
            f"# Merge archive — PR #{info.pr_number or '?'}: {info.subject}\n\n"
            f"{common}{url_line}{branches_line}{merged_line}"
        )
    if info.milestone_kind == "window":
        co_line = ""
        if info.co_authors:
            co_line = "\n**Co-authors** : " + ", ".join(f"`{c}`" for c in info.co_authors)
        return (
            f"# Commit window archive — {info.window_label}\n\n"
            f"**Range** : {info.window_start} → {info.window_end}\n"
            f"**Commits** : {info.commit_count}\n"
            f"{common}{co_line}"
        )
    return f"# Archive — {info.subject}\n\n{common}"


def _write_archive(
    vault: Path,
    slug: str,
    repo: Path,
    info: MilestoneInfo,
    existing: dict[str, dict[str, Any]],
    branch_ctx: _BranchContext | None = None,
    *,
    ai_cache: dict[str, dict[str, str | None]] | None = None,
) -> tuple[str, str]:
    """Write or skip the archive for a milestone. Returns (outcome, archive_path).

    ``ai_cache`` (optional) is the pre-fetched AI files cache from
    :func:`_prefetch_ai_files_at_commits`. When provided, the body builder
    reads from it instead of issuing per-file ``git show`` calls — the
    main perf win on repos with many milestones.
    """
    body = _build_body(repo, slug, info, ai_cache=ai_cache)
    new_hash = hash_content(body)

    archives_dir = vault / "10-episodes" / "projects" / slug / "archives"
    archives_dir.mkdir(parents=True, exist_ok=True)
    target = archives_dir / _archive_filename(slug, info)
    archive_rel = f"10-episodes/projects/{slug}/archives/{target.name}"

    milestone_id = _milestone_id(info)
    granularity = ""
    if info.milestone_kind == "window":
        granularity = "by-author" if info.window_label.count("-") > 1 and "@" in info.window_label else "window"

    fm: dict[str, Any] = {
        "date": info.date,
        "time": info.time,
        "zone": "episodes",
        "kind": "project",
        "scope": "work",
        "collective": False,
        "modality": "left",
        "type": "archive",
        "project": slug,
        "source": "archeo-git",
        "milestone_kind": info.milestone_kind,
        "source_milestone": milestone_id,
        "commit_sha": info.commit_sha,
        "friction_detected": False,
        "content_hash": new_hash,
        "previous_atom": "",
        "topology_snapshot_hash": "",
        "previous_topology_hash": "",
        # Branch-first fields populated when branch_ctx is set, empty otherwise.
        "branch": branch_ctx.branch if branch_ctx else "",
        "branch_base": branch_ctx.base if branch_ctx else "",
        "branch_base_sha": branch_ctx.base_sha if branch_ctx else "",
        "author_email": info.author_email,
        "author_name": info.author_name,
        "co_authors": list(info.co_authors),
        "granularity": granularity,
        "tags": [
            f"project/{slug}",
            "zone/episodes",
            "kind/archive",
            "scope/work",
            "source/archeo-git",
        ],
        "display": f"{slug} — {info.date} {info.time} {milestone_id}",
        "derived_atoms": [],
    }
    # Kind-specific extras only when meaningful — keeps tag archives flat.
    if info.milestone_kind == "release":
        fm["release_tag"] = info.release_tag
        fm["release_url"] = info.release_url
        fm["release_is_prerelease"] = info.release_is_prerelease
        fm["release_is_draft"] = info.release_is_draft
    elif info.milestone_kind == "merge":
        fm["pr_number"] = info.pr_number
        fm["pr_url"] = info.pr_url
        fm["pr_base"] = info.pr_base
        fm["pr_head"] = info.pr_head
        fm["pr_merged_at"] = info.pr_merged_at
    elif info.milestone_kind == "window":
        fm["window_label"] = info.window_label
        fm["window_start"] = info.window_start
        fm["window_end"] = info.window_end
        fm["commit_count"] = info.commit_count

    if milestone_id in existing:
        existing_entry = existing[milestone_id]
        existing_hash = existing_entry["fm"].get("content_hash")
        if existing_hash == new_hash:
            return "skipped", str(existing_entry["path"])
        previous_path: Path = existing_entry["path"]
        fm["previous_atom"] = f"[[{previous_path.stem}]]"
        revised = archives_dir / f"{target.stem}-revision{target.suffix}"
        i = 2
        while revised.exists():
            revised = archives_dir / f"{target.stem}-revision-{i}{target.suffix}"
            i += 1
        frontmatter.write(revised, fm, body)
        return "revised", f"10-episodes/projects/{slug}/archives/{revised.name}"

    frontmatter.write(target, fm, body)
    return "created", archive_rel


# ----------------------------------------------------------------------
# Phase 5 enforcement — context / history / index updates (v0.10.x)
# ----------------------------------------------------------------------
#
# Doctrine: every archeo write must land inside a project that carries a
# context.md + history.md + archives/ skeleton. The 2026-05-08 Gemini case
# study showed what happens when this is left to LLM judgement: 73 archives
# under user-prod-iris/, no context.md, no history.md, broken doctrine. The
# functions below are called from execute_git AFTER the per-milestone write
# loop to guarantee the project skeleton exists, history is kept current,
# and the root index references the new archives.


def _ensure_project_skeleton(
    vault: Path, slug: str, repo_path: Path | None = None
) -> list[str]:
    """If the project's context.md / history.md is missing, initialise the skeleton.

    Returns the list of files created (vault-relative POSIX paths). Empty list
    when nothing was needed (project already initialised). Re-uses
    ``execute_init_project`` for the skeleton — same content as a manual
    ``mem_init_project`` call.

    Refuses to overwrite existing files. Idempotent — calling twice is a
    no-op the second time.
    """
    project_dir = vault / "10-episodes" / "projects" / slug
    ctx_path = project_dir / "context.md"
    hist_path = project_dir / "history.md"
    if ctx_path.is_file() and hist_path.is_file():
        return []
    # Lazy import to avoid a circular dependency at module load.
    from memory_kit_mcp.tools.init_project import execute_init_project

    # When the skeleton is partial (one file present, one missing), back the
    # existing file out of the way so init_project can write its skeleton
    # without raising. In practice this branch is rare; real-world drift
    # produces fully-missing skeletons (the Gemini case study).
    if ctx_path.is_file() or hist_path.is_file():
        for stale in (ctx_path, hist_path):
            if stale.is_file():
                stale.rename(stale.with_suffix(".md.partial"))
    # Move the archives/ folder out of the way temporarily so init_project
    # (which refuses to overwrite an existing project) can run; then merge
    # the existing archives back in afterwards.
    archives_existing = project_dir / "archives"
    archives_backup = project_dir.with_name(project_dir.name + ".__archeo_archives_backup")
    has_backup = False
    if project_dir.is_dir():
        if archives_existing.is_dir():
            archives_existing.rename(archives_backup)
            has_backup = True
        # Remove the now-empty project_dir so init_project starts clean.
        try:
            project_dir.rmdir()
        except OSError:
            pass

    report = execute_init_project(vault=vault, slug=slug, kind="project")

    if has_backup:
        # Restore the user's archives, dropping the freshly-created (empty)
        # archives/ folder + .gitkeep that init_project just produced.
        new_archives = project_dir / "archives"
        if new_archives.is_dir():
            for child in new_archives.iterdir():
                try:
                    child.unlink()
                except OSError:
                    pass
            try:
                new_archives.rmdir()
            except OSError:
                pass
        archives_backup.rename(new_archives)

    return list(report.files_created)


def _patch_history_with_archives(
    vault: Path, slug: str, archive_rels: list[str], display: str | None = None
) -> bool:
    """Prepend an entry per new archive to ``{project}/history.md``.

    Idempotent — skips entries whose archive filename is already present in
    the body. Returns True when at least one entry was inserted.
    """
    if not archive_rels:
        return False
    hist_path = vault / "10-episodes" / "projects" / slug / "history.md"
    if not hist_path.is_file():
        return False
    fm, body = frontmatter.read(hist_path)
    inserted = 0
    new_lines: list[str] = []
    for rel in archive_rels:
        archive_name = Path(rel).name
        if archive_name in body or rel in body:
            continue
        # Surface a minimal entry (archeo-git archives are mechanical;
        # the heavy narrative lives in the archive itself).
        stem = Path(archive_name).stem
        line = f"- [{stem}](archives/{archive_name})"
        new_lines.append(line)
        inserted += 1
    if not new_lines:
        return False
    # Insert after the first H1 header line ("# {Slug} — Historique des sessions").
    lines = body.splitlines()
    out: list[str] = []
    inserted_flag = False
    for line in lines:
        out.append(line)
        if not inserted_flag and line.startswith("# "):
            out.append("")
            out.extend(new_lines)
            inserted_flag = True
    if not inserted_flag:
        out.extend([""] + new_lines)
    new_body = "\n".join(out) + ("\n" if not body.endswith("\n") else "")
    frontmatter.write(hist_path, fm, new_body)
    return inserted > 0


def _patch_context_phase(
    vault: Path,
    slug: str,
    archives_count: int,
    branch_ctx: _BranchContext | None,
) -> bool:
    """Update ``{project}/context.md`` ``phase`` + ``last-session`` after an archeo run.

    The phase is rewritten to summarise what was archived (count + branch +
    base), not to replace any narrative the user already wrote. Idempotent:
    if ``last-session`` already equals today and the phase already mentions
    the same archives_count, the file is left untouched.
    """
    if archives_count <= 0:
        return False
    ctx_path = vault / "10-episodes" / "projects" / slug / "context.md"
    if not ctx_path.is_file():
        return False
    fm, body = frontmatter.read(ctx_path)
    today = _today_iso()
    branch_part = ""
    if branch_ctx:
        branch_part = f" branch {branch_ctx.branch} ← {branch_ctx.base} (sha {branch_ctx.base_sha[:12]})"
    phase = (
        f"archeo-git run on {today} — {archives_count} archive(s) created" + branch_part
    )
    if fm.get("last-session") == today and fm.get("phase") == phase:
        return False
    fm["last-session"] = today
    fm["phase"] = phase
    frontmatter.write(ctx_path, fm, body)
    return True


def _patch_root_index(vault: Path, archive_rels: list[str]) -> bool:
    """Insert each new archive at the top of the ## Archives section of index.md.

    Idempotent — skips entries already referenced. Best-effort: if the
    Archives section is not found (older vault layout), append a one-line
    fallback at the end of the file.
    """
    if not archive_rels:
        return False
    index_path = vault / "index.md"
    if not index_path.is_file():
        return False
    fm, body = frontmatter.read(index_path)
    lines = body.splitlines()
    new_entries: list[str] = []
    for rel in archive_rels:
        archive_name = Path(rel).name
        if archive_name in body:
            continue
        stem = Path(archive_name).stem
        new_entries.append(f"- [{stem}]({rel})")
    if not new_entries:
        return False
    out: list[str] = []
    inserted_flag = False
    for i, line in enumerate(lines):
        out.append(line)
        if (
            not inserted_flag
            and line.strip() == "## Archives"
        ):
            # Look ahead for the next non-empty non-list line to preserve
            # blank-line separator. Insert right after the "## Archives"
            # header.
            out.append("")
            out.extend(new_entries)
            inserted_flag = True
    if not inserted_flag:
        out.extend(["", "## Archives", ""] + new_entries)
    new_body = "\n".join(out) + ("\n" if not body.endswith("\n") else "")
    frontmatter.write(index_path, fm, new_body)
    return True


def _patch_root_index_projects(vault: Path, slug: str) -> bool:
    """Add the project to the ## Projets section of root index.md if absent.

    The Phase 5 skeleton initialiser ensures ``10-episodes/projects/{slug}/
    history.md`` exists; this patch ensures the root index lists it as a
    first-class project (not just via its archives). Idempotent.
    """
    index_path = vault / "index.md"
    if not index_path.is_file():
        return False
    fm, body = frontmatter.read(index_path)
    target_link = f"10-episodes/projects/{slug}/history.md"
    if target_link in body:
        return False
    lines = body.splitlines()
    out: list[str] = []
    inserted = False
    in_projects = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Projets" or stripped == "## Projects":
            in_projects = True
            out.append(line)
            continue
        if in_projects and stripped.startswith("## "):
            # End of projects section : insert before next H2.
            out.append(f"- [{slug}]({target_link})")
            inserted = True
            in_projects = False
        out.append(line)
    if in_projects and not inserted:
        out.append(f"- [{slug}]({target_link})")
        inserted = True
    if not inserted:
        return False
    new_body = "\n".join(out) + ("\n" if not body.endswith("\n") else "")
    frontmatter.write(index_path, fm, new_body)
    return True


def _today_iso() -> str:
    from datetime import datetime

    return datetime.now().date().isoformat()


def _enforce_phase5(
    vault: Path,
    slug: str,
    repo: Path,
    archives_created: list[str],
    archives_revised: list[str],
    branch_ctx: _BranchContext | None,
) -> tuple[list[str], list[str]]:
    """Run all Phase 5 enforcement steps after the per-milestone write loop.

    Returns ``(extra_files_created, extra_files_modified)`` — paths to add to
    the parent ``execute_git`` report so the user sees the full surface of
    side-effects (skeleton init, history.md / context.md / index.md updates).

    Order is important: the skeleton MUST be initialised before history /
    context can be patched, since those targets only exist post-init.
    """
    extra_created: list[str] = list(_ensure_project_skeleton(vault, slug, repo))
    extra_modified: list[str] = []

    # All archives that just landed (created OR revised) get listed in
    # history.md / index.md.
    all_archives = archives_created + archives_revised
    if all_archives:
        if _patch_history_with_archives(vault, slug, all_archives):
            extra_modified.append(
                f"10-episodes/projects/{slug}/history.md"
            )
        if _patch_root_index(vault, all_archives):
            extra_modified.append("index.md")

    # Always ensure the project is listed in root index Projets section,
    # even when the run produced 0 new archives (re-run on existing project).
    if _patch_root_index_projects(vault, slug):
        if "index.md" not in extra_modified:
            extra_modified.append("index.md")

    if _patch_context_phase(
        vault, slug, len(archives_created), branch_ctx
    ):
        extra_modified.append(
            f"10-episodes/projects/{slug}/context.md"
        )

    return extra_created, extra_modified


# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------


def _summary_md(
    slug: str,
    level: str,
    milestones: list[MilestoneInfo],
    created: int,
    revised: int,
    skipped: int,
) -> str:
    lines = [
        f"**mem_archeo_git** — {slug} (level={level})",
        "",
        f"Milestones processed : {len(milestones)}",
        f"Archives created     : {created}",
        f"Archives revised     : {revised}",
        f"Archives skipped     : {skipped} (idempotent)",
    ]
    if milestones:
        lines.extend(["", "## By milestone"])
        for m in milestones:
            marker = {"created": "+", "revised": "~", "skipped": "·"}.get(m.outcome, "?")
            lines.append(
                f"- {marker} **{_milestone_id(m)}** ({m.date}) — {m.outcome} — {m.subject[:60]}"
            )
    lines.append("")
    return "\n".join(lines)
