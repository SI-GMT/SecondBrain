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
        branch_ctx = _resolve_branch_context(
            repo, branch_first, branch_base,
            since_sha=since_sha, since_date=since_date, by_files=by_files,
        )
        if branch_ctx is None:
            warnings.append(
                f"Branch-first mode requested for {branch_first!r} but neither "
                f"merge-base, first-parent divergence, nor explicit since_sha "
                f"could resolve a starting point relative to {branch_base!r}. "
                "Falling back to standard mode."
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
        elif outcome == "revised":
            revised += 1
            files_modified.append(archive_path)
        else:
            skipped += 1

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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
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


def _commit_metadata(repo: Path, sha: str, fallback_iso: str = "") -> MilestoneInfo:
    """Build a MilestoneInfo populated with author/subject/diff-stats for ``sha``.

    Used by every level: tags, releases (via the tag's commit), merges (via the
    merge commit), commits (via the representative commit of a window).

    Single-commit fallback path. Heavier callers (the tag/release/merge
    discovery loops) batch via :func:`_commit_metadata_batch` instead, which
    reduces ``2 × N`` forks to one ``git log --no-walk`` invocation.
    """
    cmd = [
        "git", "-C", str(repo), "show", "-s",
        "--format=%an|%ae|%aI|%s",
        sha,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
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

    out: list[MilestoneInfo] = []
    for r in raw:
        tag_name = r.get("tagName") or ""
        published = r.get("publishedAt") or ""
        date_part = published[:10]
        if since and date_part and date_part < since:
            continue
        if until and date_part and date_part > until:
            continue
        sha = _rev_parse_commit(repo, tag_name) if tag_name else ""
        if sha:
            base = _commit_metadata(repo, sha, fallback_iso=published)
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

    out: list[MilestoneInfo] = []
    for pr in raw:
        merged_at = pr.get("mergedAt") or ""
        date_part = merged_at[:10]
        if since and date_part and date_part < since:
            continue
        if until and date_part and date_part > until:
            continue
        merge_commit = (pr.get("mergeCommit") or {}).get("oid") or ""
        if merge_commit:
            base = _commit_metadata(repo, merge_commit, fallback_iso=merged_at)
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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
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

    out: list[MilestoneInfo] = []
    for (label, author_key), members in groups.items():
        # Pick the most recent commit as representative (latest date_iso wins).
        rep = max(members, key=lambda c: c.date_iso)
        w_start, w_end = group_meta[(label, author_key)]
        # Aggregate co-authors across the group.
        co_authors: list[str] = []
        seen: set[str] = set()
        for c in members:
            for ca in co_by_sha.get(c.sha, []):
                if ca and ca not in seen and ca != rep.author_email:
                    seen.add(ca)
                    co_authors.append(ca)
        info = _commit_metadata(repo, rep.sha, fallback_iso=rep.date_iso)
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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
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
    mode: str = "live"  # 'live' | 'merged-fallback' | 'since-sha' | 'since-date' | 'by-files'
    files: list[str] = field(default_factory=list)  # populated when mode='by-files'
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
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    files = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return sorted(files)


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

    Resolution priority:

    1. If ``since_sha`` is provided → escape hatch (C). Use it as the start
       point verbatim, no merge-base computation. Mode = ``'since-sha'``.

    2. Else if ``since_date`` is provided → escape hatch (C, alt). Use it as
       a date floor, base_sha is empty. Mode = ``'since-date'``.

    3. Else compute ``git merge-base {base} {branch}``. If the result equals
       the branch's HEAD (the branch has been fully merged into the base),
       fall back to the first-parent divergence point (A) — gives a stable
       historical anchor that ignores the merge-back commit. Mode =
       ``'live'`` (branch never merged) or ``'merged-fallback'`` (branch
       fully merged).

    4. If ``by_files=True`` → after resolving base_sha, derive the
       branch-specific files (B) and switch mode to ``'by-files'``. The
       caller will then query commits TOUCHING those files, repo-wide,
       instead of just commits in the branch range.

    Returns ``None`` if the refs can't be resolved.
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
            ctx.notes.append(f"by_files mode: {len(ctx.files)} branch-specific file(s) detected")
        return ctx

    # Escape hatch (C, alt): explicit since_date.
    if since_date:
        ctx = _BranchContext(
            branch=branch, base=base, base_sha="",
            mode="since-date",
            notes=[f"explicit since_date={since_date} drives the floor"],
        )
        # by_files needs a base_sha to compute "files introduced since". Without
        # since_sha we approximate by using merge-base anyway — caveat noted.
        if by_files:
            mb = subprocess.run(
                ["git", "-C", str(repo), "merge-base", base, branch],
                capture_output=True, text=True,
            )
            if mb.returncode == 0:
                fallback_base = mb.stdout.strip()
                ctx.files = _branch_specific_files(repo, branch, fallback_base)
                ctx.mode = "by-files"
                ctx.notes.append(
                    f"by_files mode (since_date set): {len(ctx.files)} file(s) "
                    f"derived via merge-base fallback for the file detection step"
                )
        return ctx

    # Standard path: need base ref to exist for merge-base.
    if not _rev_parse_commit(repo, base):
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "merge-base", base, branch],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    merge_base = result.stdout.strip()
    if not merge_base:
        return None

    branch_head = _rev_parse_commit(repo, branch)

    # Detection (A): if merge_base == branch_head, the branch is fully merged
    # into the base — `merge_base..branch` would yield no commits. Fall back
    # to first-parent divergence to get the historical anchor.
    if merge_base == branch_head:
        fp_div = _first_parent_divergence_point(repo, branch, base)
        if fp_div and fp_div != branch_head:
            ctx = _BranchContext(
                branch=branch, base=base, base_sha=fp_div,
                mode="merged-fallback",
                notes=[
                    f"branch fully merged into {base} (merge-base == HEAD); "
                    f"first-parent divergence point used instead: {fp_div[:12]}",
                ],
            )
            if by_files:
                ctx.files = _branch_specific_files(repo, branch, fp_div)
                ctx.mode = "by-files"
                ctx.notes.append(
                    f"by_files mode: {len(ctx.files)} branch-specific file(s) detected"
                )
            return ctx
        # No first-parent divergence found (very rare: branch never had its own
        # commits). Return None to signal the caller falls back to standard mode.
        return None

    # Live branch (not fully merged): standard path.
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
    """Branch-first discovery — covers four modes (live / merged-fallback /
    since-sha / since-date / by-files).

    - **commits / windowed**: enumerate commits in the resolved rev-range and
      group per window + by_author.
    - **by-files**: derive the branch-specific files (set on the context) and
      query commits TOUCHING those files repo-wide — captures the full
      lineage (creation, evolution, post-merge fixes on the same files).
    - **merges**: enumerate merge commits in the rev-range.
    - **tags / releases**: meaningless on a branch scope; warn and fall back
      to commits-by-author.
    """
    # Surface context notes to the caller so they understand the resolution.
    for note in branch_ctx.notes:
        warnings.append(f"branch-first: {note}")

    # By-files: query commits that TOUCHED any of the branch-specific files,
    # repo-wide — not constrained to the branch range. Captures pre-creation
    # commits IF the file was renamed (no), creation, evolution on/off the
    # branch, and post-merge fixes. Honours since/until date filters.
    if branch_ctx.mode == "by-files":
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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
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

    out: list[MilestoneInfo] = []
    for (label, author_key), members in groups.items():
        rep = max(members, key=lambda c: c.date_iso)
        w_start, w_end = group_meta[(label, author_key)]
        co_authors: list[str] = []
        seen: set[str] = set()
        for c in members:
            for ca in co_by_sha.get(c.sha, []):
                if ca and ca not in seen and ca != rep.author_email:
                    seen.add(ca)
                    co_authors.append(ca)
        info = _commit_metadata(repo, rep.sha, fallback_iso=rep.date_iso)
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


def _list_branch_merges(
    repo: Path,
    branch_ctx: _BranchContext,
    *,
    since: str | None,
    until: str | None,
    warnings: list[str],
) -> list[MilestoneInfo]:
    """Enumerate merge commits unique to the branch since divergence."""
    rev_range = f"{branch_ctx.base_sha}..{branch_ctx.branch}"
    cmd = [
        "git", "-C", str(repo), "log", "--merges", rev_range,
        "--format=%H|%aI",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        warnings.append(f"git log --merges failed: {exc}")
        return []
    out: list[MilestoneInfo] = []
    for line in result.stdout.splitlines():
        if "|" not in line:
            continue
        sha, iso = line.split("|", 1)
        date_part = iso[:10]
        if since and date_part and date_part < since:
            continue
        if until and date_part and date_part > until:
            continue
        info = _commit_metadata(repo, sha, fallback_iso=iso)
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
    """Same deterministic resolution as archeo_stack."""
    if explicit:
        return explicit
    candidate = repo.name
    if (vault / "10-episodes" / "projects" / candidate).is_dir():
        return candidate
    raise ValueError(
        f"Cannot auto-resolve target project slug for repo {repo.name!r}. "
        f"No project named {candidate!r} exists in {paths.ZONE_EPISODES}/projects/. "
        "Pass `project=<slug>` explicitly, or create the project via mem_archive first."
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
    """Build the archive body. The Main / AI files context / Friction sections
    are always present (per spec invariant) — only the Main section's headline
    metadata varies per milestone kind."""
    ai_section = (
        _build_ai_context_section(repo, info.commit_sha, ai_cache=ai_cache)
        if info.commit_sha
        else "No commit SHA resolved for this milestone — AI files context unavailable.\n"
    )
    head = _milestone_headline(info)
    return (
        f"{head}\n\n"
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
