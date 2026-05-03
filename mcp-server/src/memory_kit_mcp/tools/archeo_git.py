"""mem_archeo_git — Phase 3 of the triphasic archeo: Git history reconstruction.

Spec: core/procedures/mem-archeo-git.md

Reconstructs the temporal history of a Git repo as N dated archives, one per
semver tag (v*.*.*) by default. Each archive embeds the AI files context
(CLAUDE.md / AGENTS.md / GEMINI.md / MISTRAL.md / README.md) at the time of
the tag's commit, read via `git show {sha}:{file}`.

POC scope (v0.8.x):
- level='tags' only (semver tags v*.*.*). Other granularities (releases via
  gh CLI, merges, commit windows) deferred — fall back to skills for those.
- Standard mode only (no branch-first / --by-author / --by-merge / --by-window).
- No friction detection (heuristic ≥3 successive commits same theme — fragile
  on tag-level granularity). Section emitted with the explicit fallback line
  per spec invariant.
- No router cascade. Archive written directly to the canonical path
  10-episodes/projects/{slug}/archives/. The LLM may run the skill fallback
  to extract Principle / Concept / Goal atoms from the body if needed.
- AI files context section: heuristic excerpt by keyword headings (workflow /
  sync / multi-tenant / security / decision / architecture). Best-effort.

Idempotence: (project, source_milestone=tag) — looks for any existing archive
under projects/{slug}/archives/ whose frontmatter source_milestone matches.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
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


def execute_git(
    vault: Path,
    repo: Path,
    project: str | None,
    level: str = "tags",
    since: str | None = None,
    until: str | None = None,
    skip_repo_validation: bool = False,
) -> ArcheoGitResult:
    """Run the Phase 3 git history reconstruction. Module-level so the
    orchestrator can call it without going through the MCP layer.

    `skip_repo_validation=True` is set by the orchestrator which has already
    validated the repo via Phase 0 — avoids redundant subprocess calls.
    """
    if level != "tags":
        raise NotImplementedError(
            f"mem_archeo_git POC supports level='tags' only. "
            f"Other levels (releases, merges, commit windows) deferred — "
            f"fall back to core/procedures/mem-archeo-git.md skill."
        )

    if not skip_repo_validation:
        try:
            scan(repo, depth=1, vault=vault)
        except NotAGitRepoError as e:
            raise NotAGitRepoError(str(e)) from e

    slug = _resolve_project_slug(vault, repo, project)

    warnings: list[str] = []
    tags = _list_semver_tags(repo, since=since, until=until)
    if not tags:
        warnings.append(f"No semver tags (v*.*.*) found in {repo}.")

    existing_milestones = _scan_existing_milestones(vault, slug)

    milestones: list[MilestoneInfo] = []
    files_created: list[str] = []
    files_modified: list[str] = []
    created = revised = skipped = 0

    for tag in tags:
        info = _build_milestone_info(repo, tag)
        outcome, archive_path = _write_archive(
            vault, slug, repo, tag, info, existing_milestones,
        )
        info.outcome = outcome
        info.archive_path = archive_path
        milestones.append(info)
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
            description="Granularity. POC supports 'tags' only (semver v*.*.*).",
        ),
        since: str | None = Field(
            None,
            description="Lower bound (inclusive) on tag commit date, format YYYY-MM-DD.",
        ),
        until: str | None = Field(
            None,
            description="Upper bound (inclusive) on tag commit date, format YYYY-MM-DD.",
        ),
    ) -> ArcheoGitResult:
        """Phase 3 of the triphasic archeo: reconstruct Git history as dated archives.

        Walks the repo's semver tags (v*.*.*) and writes one archive per tag in
        10-episodes/projects/{slug}/archives/. Each archive embeds AI files context
        at the time of the tag's commit. Idempotent on (project, source_milestone).
        Refuses non-Git directories.
        """
        config = get_config()
        return execute_git(
            vault=config.vault,
            repo=Path(repo_path).expanduser().resolve(),
            project=project,
            level=level,
            since=since,
            until=until,
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

    Uses `git for-each-ref` with format string. The `*committerdate` token
    dereferences annotated tag objects to give the *commit*'s date (rather
    than the tag object's tagger date); for lightweight tags this is empty,
    in which case we fall back to plain `committerdate`. Filters non-semver
    tags and applies --since / --until bounds (inclusive) on the date part
    YYYY-MM-DD.
    """
    cmd = [
        "git", "-C", str(repo), "for-each-ref",
        # 5 fields separated by '|': name | tag-object-sha | creatordate |
        # *committerdate (commit date for annotated) | committerdate (tagger
        # date for annotated, or commit date for lightweight)
        "--format=%(refname:short)|%(objectname)|%(creatordate:iso-strict)|%(*committerdate:iso-strict)|%(committerdate:iso-strict)",
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
        parts = line.split("|", 4)
        if len(parts) != 5:
            continue
        name, ref_sha, _creatordate, deref_committerdate, committerdate = parts
        if not _SEMVER_TAG_RE.match(name):
            continue
        # ref_sha is the tag object SHA for annotated tags; we want the COMMIT SHA.
        commit_sha = _rev_parse_commit(repo, name) or ref_sha
        # Prefer the dereferenced (= commit) date for filtering. Fallback to
        # plain committerdate for lightweight tags.
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


def _build_milestone_info(repo: Path, tag: _Tag) -> MilestoneInfo:
    """Extract the metadata for a tag's commit."""
    # Author + subject from `git show -s --format=...`
    cmd = [
        "git", "-C", str(repo), "show", "-s",
        "--format=%an|%ae|%aI|%s",
        tag.sha,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        parts = result.stdout.strip().split("|", 3)
    except (FileNotFoundError, subprocess.CalledProcessError):
        parts = ["", "", tag.date_iso, ""]
    if len(parts) < 4:
        parts = parts + [""] * (4 - len(parts))
    author_name, author_email, author_iso, subject = parts

    # Diff stats: count of files + insertions + deletions, vs first parent.
    # If the commit is the initial commit, fallback to git show --shortstat.
    files_changed = insertions = deletions = 0
    try:
        stat = subprocess.run(
            ["git", "-C", str(repo), "show", "--shortstat", "--format=", tag.sha],
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

    date_part = (author_iso or tag.date_iso)[:10]
    time_part = _extract_hhmm(author_iso or tag.date_iso)

    return MilestoneInfo(
        tag=tag.name,
        commit_sha=tag.sha,
        date=date_part,
        time=time_part,
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
    """Read a file's content at a given commit. Returns None if absent at that commit."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", f"{sha}:{file}"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


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


def _build_ai_context_section(repo: Path, sha: str) -> str:
    """Build the `## AI files context` section content. Always returns content
    matching the spec invariant (explicit fallback line if nothing extractable).
    """
    excerpts: list[str] = []
    for fname in _AI_FILES_TO_READ:
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


_TAG_SAN_RE = re.compile(r"[^a-z0-9-]+")


def _sanitize_tag_for_slug(tag: str) -> str:
    """Sanitize a tag name for use in a filename. v0.8.0 -> v0-8-0."""
    s = tag.lower().replace(".", "-")
    s = _TAG_SAN_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "tag"


def _archive_filename(slug: str, info: MilestoneInfo) -> str:
    tag_san = _sanitize_tag_for_slug(info.tag)
    time_part = info.time.replace(":", "h") if info.time else "00h00"
    return f"{info.date}-{time_part}-{slug}-archeo-git-{tag_san}.md"


def _build_body(repo: Path, slug: str, info: MilestoneInfo) -> str:
    """Build the archive body matching the spec invariant: Main + AI files
    context + Friction & Resolution sections, all present, with explicit
    fallback lines if empty."""
    ai_section = _build_ai_context_section(repo, info.commit_sha)

    return (
        f"# Milestone archive — {info.tag}\n\n"
        f"**Date** : {info.date} {info.time}\n"
        f"**Author** : {info.author_name} <{info.author_email}>\n"
        f"**Commit SHA** : `{info.commit_sha}`\n"
        f"**Subject** : {info.subject}\n"
        f"**Diff stats** : {info.files_changed} files changed, "
        f"+{info.insertions} / -{info.deletions}\n\n"
        f"## AI files context\n\n"
        f"{ai_section}\n"
        f"## Friction & Resolution\n\n"
        f"No friction detected for this milestone.\n\n"
        f"_(POC v0.8.x: friction detection deferred — "
        f"fall back to skill for ≥3 commits same theme heuristic.)_\n"
    )


def _write_archive(
    vault: Path,
    slug: str,
    repo: Path,
    tag: _Tag,
    info: MilestoneInfo,
    existing: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    """Write or skip the archive for a tag. Returns (outcome, archive_path)."""
    body = _build_body(repo, slug, info)
    new_hash = hash_content(body)

    archives_dir = vault / "10-episodes" / "projects" / slug / "archives"
    archives_dir.mkdir(parents=True, exist_ok=True)
    target = archives_dir / _archive_filename(slug, info)
    archive_rel = f"10-episodes/projects/{slug}/archives/{target.name}"

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
        "source_milestone": tag.name,
        "commit_sha": info.commit_sha,
        "friction_detected": False,
        "content_hash": new_hash,
        "previous_atom": "",
        "topology_snapshot_hash": "",
        "previous_topology_hash": "",
        # Branch-first fields kept as empty per spec invariant (always present in schema).
        "branch": "",
        "branch_base": "",
        "branch_base_sha": "",
        "author_email": info.author_email,
        "author_name": info.author_name,
        "co_authors": [],
        "granularity": "",
        "tags": [
            f"project/{slug}",
            "zone/episodes",
            "kind/archive",
            "scope/work",
            "source/archeo-git",
        ],
        "display": f"{slug} — {info.date} {info.time} {info.tag}",
        "derived_atoms": [],
    }

    if tag.name in existing:
        existing_entry = existing[tag.name]
        existing_hash = existing_entry["fm"].get("content_hash")
        if existing_hash == new_hash:
            return "skipped", str(existing_entry["path"])
        # Revision: link previous and write to a NEW filename so the old archive
        # remains immutable.
        previous_path: Path = existing_entry["path"]
        fm["previous_atom"] = f"[[{previous_path.stem}]]"
        # Suffix the new filename with -revision so we don't overwrite the
        # immutable old archive.
        revised = archives_dir / f"{target.stem}-revision{target.suffix}"
        # If even the revision filename collides, append a numeric suffix.
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
            lines.append(f"- {marker} **{m.tag}** ({m.date}) — {m.outcome} — {m.subject[:60]}")
    lines.append("")
    return "\n".join(lines)
