"""mem_archeo_plan — Phase 0 interactive cadrage for archeo branch-first.

Spec: ``core/procedures/mem-archeo-git.md`` Phase 0.

Read-only — never writes the vault. Returns an :class:`ArcheoPlan` summarizing
what ``mem_archeo_git`` *would* do given the current repo / branch / vault
state, so the LLM can surface the plan to the user and get explicit
validation on slug, scope, granularity, filters, and project init before
any side-effect runs.

Replaces the 2026-05-08 case study where Gemini, freed from cadrage:

- mis-classified the slug (``user-prod-iris`` from path basename instead of
  reusing the existing ``ecosav`` project),
- picked ``--by-author --window=week`` granularity producing 73 mechanical
  archives,
- skipped ``context.md`` and ``history.md`` creation entirely.

The plan also captures the user's git identity (``user.email`` / ``user.name``)
so Phase 3 can prioritise the user's own commits when ``author_self_only`` is
on.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.archeo import enumerate_files
from memory_kit_mcp.archeo.topology import (
    _run_git,
    find_branch_merges_via_perimeter,
    find_merge_commit_for_branch,
)
from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import (
    ArcheoPlan,
    _BranchAuthor,
    _BranchInfo,
    _FilterProposal,
    _GranularityProposal,
    _ProjectInfo,
    _ScopeProposal,
    _SlugProposal,
    _UserSelf,
)
from memory_kit_mcp.tools.archeo_git import (
    _BRANCH_PREFIX_RE,
    _suggest_scope_from_branch_name,
)

# A slug candidate is "human-readable" if, after prefix-strip and lowercase,
# it matches kebab/snake casing with ≥3 chars and no JIRA-style ticket
# fragments. Used to decide whether mem_archeo_plan can trust the slug
# silently or must ask the user for confirmation.
_HUMAN_SLUG_RE = re.compile(r"^[a-z][a-z0-9]{1,}([-_][a-z0-9]+)*$")
# Cryptic patterns: ABC-123, JIRA-1234, ticket-style numeric IDs at start
# or end, hex strings, very long random-looking tokens.
_CRYPTIC_RE = re.compile(
    r"(\b[A-Z]+-\d+\b|\b[a-f0-9]{8,}\b|\b\d{4,}\b)",
    re.IGNORECASE,
)
_DEFAULT_BRANCH_CANDIDATES: tuple[str, ...] = ("main", "master", "develop")


def _git_config_get(repo: Path, key: str) -> str:
    """Read a single git config value; '' if unset."""
    try:
        return _run_git(["config", "--get", key], repo)[0]
    except (RuntimeError, IndexError):
        return ""


def _detect_default_branch(repo: Path) -> str:
    """Best-effort default branch detection.

    Order of attempts:

    1. ``git symbolic-ref refs/remotes/origin/HEAD`` (definitive when origin tracked).
    2. Probe ``main`` / ``master`` / ``develop`` via ``git rev-parse --verify``.

    Returns ``"main"`` as a last resort (matches the historical default of
    ``mem_archeo_git`` so behaviour is unchanged when nothing is detectable).
    """
    try:
        out = _run_git(
            ["symbolic-ref", "refs/remotes/origin/HEAD"], repo
        )
        if out:
            ref = out[0]  # e.g. 'refs/remotes/origin/master'
            return ref.rsplit("/", 1)[-1]
    except RuntimeError:
        pass
    for cand in _DEFAULT_BRANCH_CANDIDATES:
        try:
            _run_git(["rev-parse", "--verify", cand], repo)
            return cand
        except RuntimeError:
            continue
    return "main"


def _current_branch(repo: Path) -> str:
    """Resolve the current branch via ``git rev-parse --abbrev-ref HEAD``."""
    try:
        return _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo)[0]
    except (RuntimeError, IndexError):
        return ""


def _list_branch_authors(
    repo: Path, branch: str, base_sha: str
) -> list[_BranchAuthor]:
    """List authors and their commit counts in ``base_sha..branch`` range.

    Empty list when the range is empty (fully-merged branch with no
    by-files / auto-scope-by-name fallback) or when the git call fails.
    """
    if not base_sha:
        return []
    try:
        out = _run_git(
            ["log", f"{base_sha}..{branch}", "--format=%ae|%an"], repo
        )
    except RuntimeError:
        return []
    counts: dict[str, _BranchAuthor] = {}
    for line in out:
        if "|" not in line:
            continue
        email, name = line.split("|", 1)
        email, name = email.strip(), name.strip()
        if not email:
            continue
        if email not in counts:
            counts[email] = _BranchAuthor(email=email, name=name, commits=0)
        counts[email].commits += 1
    return sorted(counts.values(), key=lambda a: -a.commits)


def _commits_count(repo: Path, base_sha: str, branch: str) -> int:
    """Count commits in ``base_sha..branch``."""
    if not base_sha:
        return 0
    try:
        out = _run_git(
            ["rev-list", "--count", f"{base_sha}..{branch}"], repo
        )
        return int(out[0]) if out else 0
    except (RuntimeError, ValueError, IndexError):
        return 0


def _scope_glob_authors(
    repo: Path, scope_glob: str
) -> tuple[list[_BranchAuthor], int, bool]:
    """Walk ``git log -- {scope_glob}`` and aggregate (authors, commits_count, has_merges).

    Used when the branch is fully merged and Phase 3 will fall back to
    ``by-files`` / ``auto-scope-by-name`` lineage. The range ``base..branch``
    is empty in that case, so the standard author/commit walk returns
    nothing — this helper repopulates the data from the scope-glob lineage
    (every commit in the repo that touches a file matching the glob).
    """
    try:
        out = _run_git(
            [
                "log",
                "--no-merges",
                "--format=%ae|%an",
                "--",
                scope_glob,
            ],
            repo,
        )
    except RuntimeError:
        out = []
    try:
        merges_out = _run_git(
            [
                "log",
                "--merges",
                "--format=%H",
                "--",
                scope_glob,
            ],
            repo,
        )
    except RuntimeError:
        merges_out = []
    counts: dict[str, _BranchAuthor] = {}
    for line in out:
        if "|" not in line:
            continue
        email, name = line.split("|", 1)
        email, name = email.strip(), name.strip()
        if not email:
            continue
        if email not in counts:
            counts[email] = _BranchAuthor(email=email, name=name, commits=0)
        counts[email].commits += 1
    authors = sorted(counts.values(), key=lambda a: -a.commits)
    commits_count = sum(a.commits for a in authors)
    has_merges = bool(merges_out)
    return authors, commits_count, has_merges


def _has_merges_in_range(repo: Path, base_sha: str, branch: str) -> bool:
    if not base_sha:
        return False
    try:
        out = _run_git(
            ["log", "--merges", f"{base_sha}..{branch}", "--format=%H"], repo
        )
        return bool(out)
    except RuntimeError:
        return False


def _slugify_branch_name(branch: str) -> str:
    """Sanitize a branch name into a slug candidate (kebab-case, ASCII-fold)."""
    bare = _BRANCH_PREFIX_RE.sub("", branch).strip("-/_ ")
    bare = bare.lower()
    bare = re.sub(r"[^a-z0-9-]+", "-", bare)
    bare = re.sub(r"-+", "-", bare).strip("-")
    return bare or "branch"


def _is_human_readable_slug(slug: str) -> bool:
    if len(slug) < 3:
        return False
    if not _HUMAN_SLUG_RE.match(slug):
        return False
    if _CRYPTIC_RE.search(slug):
        return False
    return True


def _resolve_slug(
    repo: Path,
    branch: str,
    project_arg: str | None,
) -> _SlugProposal:
    if project_arg:
        return _SlugProposal(
            candidate=project_arg,
            source="project-arg",
            needs_confirmation=False,
            reason="Caller passed --project explicitly.",
        )
    candidate = _slugify_branch_name(branch)
    if _is_human_readable_slug(candidate):
        return _SlugProposal(
            candidate=candidate,
            source="branch-name",
            needs_confirmation=False,
            reason=(
                f"Branch name '{branch}' sanitises to '{candidate}' which "
                "is human-readable (kebab-case, ≥3 chars, no ticket-style "
                "fragments). Trusting heuristic."
            ),
        )
    return _SlugProposal(
        candidate=candidate,
        source="needs-prompt",
        needs_confirmation=True,
        reason=(
            f"Branch name '{branch}' produced cryptic slug '{candidate}' "
            "(JIRA-style ticket id, numeric prefix, or hash detected). "
            "MUST ask the user for an explicit slug before proceeding."
        ),
    )


def _resolve_project(vault: Path, slug: str) -> _ProjectInfo:
    candidate = vault / "10-episodes" / "projects" / slug
    archived = vault / "10-episodes" / "archived" / slug
    if candidate.is_dir() and (candidate / "context.md").is_file():
        return _ProjectInfo(
            slug=slug,
            exists=True,
            will_init=False,
            path=str(candidate.relative_to(vault).as_posix()),
        )
    if archived.is_dir():
        return _ProjectInfo(
            slug=slug,
            exists=False,
            will_init=False,
            path=str(archived.relative_to(vault).as_posix()),
        )
    return _ProjectInfo(
        slug=slug,
        exists=False,
        will_init=True,
        path=str(candidate.relative_to(vault).as_posix()),
    )


def _files_in_range(repo: Path, base_sha: str, head_ref: str) -> tuple[int, int]:
    """Return ``(files_count, files_bytes)`` for ``git log base..head --name-only``.

    Used by both the 'live' and 'merged-via-merge-commit' strategies — they
    share the same range semantics (base_sha..head), only differ on what
    base_sha points to.
    """
    try:
        files_out = _run_git(
            [
                "log",
                f"{base_sha}..{head_ref}",
                "--name-only",
                "--pretty=format:",
            ],
            repo,
        )
    except RuntimeError:
        files_out = []
    unique_files = {f.strip() for f in files_out if f.strip()}
    files_bytes = 0
    for rel in unique_files:
        p = repo / rel
        try:
            files_bytes += p.stat().st_size
        except OSError:
            continue
    return len(unique_files), files_bytes


def _resolve_scope(
    repo: Path,
    branch: str,
    base_sha: str,
    fully_merged: bool,
    base_branch: str = "",
) -> _ScopeProposal:
    """Resolve the Phase 3 scope strategy + estimate file count.

    Priority:

    1. Branch alive (``not fully_merged``) → mode='live', range = base..branch.
    2. Branch fully merged → try :func:`find_branch_merges_via_perimeter`
       (multi-signal walker capturing every merge cycle of the branch via
       file/author/subject scoring with reciprocal-overlap reciprocity).
       When ≥1 merge captured → mode='merged-via-perimeter', covers
       dev-reset workflows. Files = union of all captured merges' files.
    3. Fall back to single-tip :func:`find_merge_commit_for_branch` when
       perimeter walker captures nothing (single-cycle branch never reset)
       → mode='merged-via-merge-commit'.
    4. Fall back to auto-scope-by-name when no merge commit detectable
       (squash, rebase + ff, perimeter walker found nothing).
    5. Refusal when nothing matches.
    """
    if not fully_merged and base_sha:
        files_count, files_bytes = _files_in_range(repo, base_sha, branch)
        return _ScopeProposal(
            mode="live",
            scope_glob=None,
            files_count_estimate=files_count,
            files_bytes_estimate=files_bytes,
        )

    if fully_merged and base_branch:
        captured_merges = find_branch_merges_via_perimeter(
            repo, branch, base_branch
        )
        if captured_merges:
            union_files: set[str] = set()
            for bm in captured_merges:
                union_files.update(bm.files)
            files_bytes = 0
            for rel in union_files:
                p = repo / rel
                try:
                    files_bytes += p.stat().st_size
                except OSError:
                    continue
            return _ScopeProposal(
                mode="merged-via-perimeter",
                scope_glob=None,
                scope_globs=[],
                files_count_estimate=len(union_files),
                files_bytes_estimate=files_bytes,
            )

        merge_info = find_merge_commit_for_branch(repo, branch, base_branch)
        if merge_info is not None:
            m_sha, parent1, _parent2 = merge_info
            files_count, files_bytes = _files_in_range(repo, parent1, m_sha)
            return _ScopeProposal(
                mode="merged-via-merge-commit",
                scope_glob=None,
                scope_globs=[],
                files_count_estimate=files_count,
                files_bytes_estimate=files_bytes,
            )

    matches = _suggest_scope_from_branch_name(repo, branch)
    if matches:
        globs = [f"{m}/**" for m in matches]
        primary = globs[0]
        result = enumerate_files(repo, scope_glob=primary)
        return _ScopeProposal(
            mode="auto-scope-by-name",
            scope_glob=primary,
            scope_globs=globs,
            files_count_estimate=result.files_count,
            files_bytes_estimate=result.files_bytes,
        )

    return _ScopeProposal(
        mode="refusal",
        scope_glob=None,
        files_count_estimate=0,
        files_bytes_estimate=0,
    )


def _propose_granularity(
    commits_count: int,
    has_merges: bool,
    authors_count: int,
    is_solo: bool,
) -> _GranularityProposal:
    """Heuristic for the proposed Phase 3 granularity.

    Priority order, first match wins:

    - has merges → ``by-merge`` (most narrative, typically the user's
      preferred unit on long-lived feature branches).
    - solo author + ≥3 commits → ``by-window-month``.
    - multi-author + ≥10 commits → ``by-window-month``.
    - everything else → ``by-window-week``.

    Never proposes ``by-author-week`` by default — that level of detail is
    only useful for HR-style attribution and produces noisy archives. The
    user can still opt in explicitly.
    """
    if has_merges:
        return _GranularityProposal(
            proposed="by-merge",
            reason=(
                "Branch contains merge commits — by-merge groups archives "
                "around merged sub-features for narrative clarity."
            ),
        )
    if commits_count == 0:
        return _GranularityProposal(
            proposed="by-window-month",
            reason="No commits in scope; default granularity (no-op effectively).",
        )
    if is_solo and commits_count >= 3:
        return _GranularityProposal(
            proposed="by-window-month",
            reason=(
                f"Solo branch ({commits_count} commits, single author) — "
                "by-window-month groups commits per month for a narrative recap."
            ),
        )
    if authors_count > 1 and commits_count >= 10:
        return _GranularityProposal(
            proposed="by-window-month",
            reason=(
                f"Multi-author branch ({authors_count} authors, "
                f"{commits_count} commits) — by-window-month is more readable "
                "than by-author-week."
            ),
        )
    return _GranularityProposal(
        proposed="by-window-week",
        reason=(
            f"Small scope ({commits_count} commit(s), {authors_count} "
            "author(s)) — by-window-week keeps archives tight."
        ),
    )


def _propose_filters(is_solo: bool) -> _FilterProposal:
    if is_solo:
        return _FilterProposal(author_self_only=True, include_team=False)
    return _FilterProposal(author_self_only=False, include_team=True)


def _build_warnings(
    plan_inputs: dict,
) -> list[str]:
    warnings: list[str] = []
    if plan_inputs["slug"].needs_confirmation:
        warnings.append(
            f"Slug '{plan_inputs['slug'].candidate}' may be cryptic — "
            "ask the user for a meaningful project slug before proceeding."
        )
    if plan_inputs["project"].will_init:
        warnings.append(
            f"Project '{plan_inputs['project'].slug}' does not exist in the "
            "vault yet — will be initialized (context.md + history.md + "
            "archives/) at Phase 5."
        )
    if plan_inputs["branch"].fully_merged:
        if plan_inputs["scope"].mode == "merged-via-perimeter":
            warnings.append(
                f"Branch '{plan_inputs['branch'].name}' is fully merged into "
                f"'{plan_inputs['branch'].base}'. Scope resolved via perimeter "
                "walker — multi-signal scoring (files+authors+subject) "
                "captured every merge cycle of the branch (handles dev-reset "
                "workflows where HEAD(branch) was reset to origin/base "
                "between cycles). Audit per-merge scores via the archive "
                "frontmatter ``branch_merge_score`` field."
            )
        elif plan_inputs["scope"].mode == "merged-via-merge-commit":
            warnings.append(
                f"Branch '{plan_inputs['branch'].name}' is fully merged into "
                f"'{plan_inputs['branch'].base}'. Scope resolved deterministically "
                "via the absorbing merge commit on base first-parent (range = "
                "M^1..M^2). No name-matching heuristic involved."
            )
        elif plan_inputs["scope"].mode == "auto-scope-by-name":
            warnings.append(
                f"Branch '{plan_inputs['branch'].name}' is fully merged into "
                f"'{plan_inputs['branch'].base}' AND no merge commit absorbs "
                "the branch tip on base first-parent (squash or rebase + ff). "
                f"Scope falls back to auto-scope-by-name → "
                f"{plan_inputs['scope'].scope_glob} "
                f"(all matches: {plan_inputs['scope'].scope_globs}). "
                "Verify the heuristic captured the right directories."
            )
        elif plan_inputs["scope"].mode == "refusal":
            warnings.append(
                f"Branch '{plan_inputs['branch'].name}' is fully merged AND no "
                "merge commit detected AND no auto-scope-by-name match. Caller "
                "MUST pass --since-sha / --since-date / --scope-glob to "
                "mem_archeo_git, or refuse."
            )
    if (
        plan_inputs["scope"].files_count_estimate > 500
        and plan_inputs["granularity"].proposed != "by-merge"
    ):
        warnings.append(
            f"Scope is large ({plan_inputs['scope'].files_count_estimate} "
            "files) — consider --by-merge granularity for narrative archives."
        )
    if (
        len(plan_inputs["branch_authors"]) > 1
        and plan_inputs["filters"].author_self_only
    ):
        warnings.append(
            "Multi-author branch but author_self_only=true was proposed — "
            "verify with the user this is the intent (otherwise set "
            "author_self_only=false)."
        )
    return warnings


def _format_summary_md(plan: ArcheoPlan) -> str:
    lines = [
        f"## mem_archeo_plan — `{plan.project.slug}`\n",
        f"- Repo: `{plan.repo_path}`",
        f"- User: **{plan.user_self.name or '(no name)'}** "
        f"<{plan.user_self.email or 'no email'}>",
        f"- Branch: `{plan.branch.name}` (base: `{plan.branch.base}`"
        + (f", base SHA: `{plan.branch.base_sha[:12]}`)" if plan.branch.base_sha else ")"),
        f"- Fully merged: **{plan.branch.fully_merged}**",
        f"- Commits in scope: **{plan.branch.commits_count}**",
        "",
        "### Authors",
    ]
    if plan.branch_authors:
        for a in plan.branch_authors:
            tag = " *(self)*" if a.email == plan.user_self.email else ""
            lines.append(f"- {a.name} <{a.email}> — {a.commits} commit(s){tag}")
    else:
        lines.append("_(no authors detected — empty range)_")
    lines += [
        "",
        "### Slug proposal",
        f"- Candidate: **`{plan.slug.candidate}`**",
        f"- Source: `{plan.slug.source}`",
        f"- Needs confirmation: **{plan.slug.needs_confirmation}**",
        f"- Reason: {plan.slug.reason}",
        "",
        "### Project",
        f"- Path: `{plan.project.path}`",
        f"- Exists: **{plan.project.exists}**",
        f"- Will init: **{plan.project.will_init}**",
        "",
        "### Scope",
        f"- Mode: `{plan.scope.mode}`"
        + (f" — glob: `{plan.scope.scope_glob}`" if plan.scope.scope_glob else ""),
    ]
    if plan.scope.scope_globs and len(plan.scope.scope_globs) > 1:
        lines.append("- All matched globs:")
        for g in plan.scope.scope_globs:
            lines.append(f"  - `{g}`")
    lines += [
        f"- Files estimate: **{plan.scope.files_count_estimate}** "
        f"({plan.scope.files_bytes_estimate // 1024} KiB)",
        "",
        "### Granularity",
        f"- Proposed: **`{plan.granularity.proposed}`**",
        f"- Reason: {plan.granularity.reason}",
        "",
        "### Filters",
        f"- author_self_only: **{plan.filters.author_self_only}**",
        f"- include_team: **{plan.filters.include_team}**",
    ]
    if plan.warnings:
        lines += ["", "### Warnings"]
        for w in plan.warnings:
            lines.append(f"- {w}")
    if plan.next_call:
        tool_name = plan.next_call.get("tool", "mem_archeo")
        lines += [
            "",
            "### Next call (LITERAL — do not translate)",
            "",
            "```python",
            f"{tool_name}(",
        ]
        for k, v in plan.next_call.items():
            if k == "tool":
                continue
            if isinstance(v, str):
                lines.append(f'    {k}="{v}",')
            else:
                lines.append(f"    {k}={v!r},")
        lines += [")", "```"]
    lines += [
        "",
        "_Read-only — no vault writes. To proceed, validate this plan with the "
        "user, then invoke the tool named in ``next_call.tool`` with the EXACT "
        "remaining arguments. Do NOT call ``mem_archeo_git`` directly — the "
        "next_call targets the **orchestrator** so Phase 0 topology + Phase 2 "
        "stack + Phase 3 git + Phase 1 brief all chain. After the orchestrator "
        "returns, you MUST process ``context_brief`` (read every file in "
        "files_to_read) then call ``mem_archeo_context(phase='finalize', "
        "acknowledged_via_read=True, synthesis=...)`` to alimente "
        "context.md + write the project topology atom._",
    ]
    return "\n".join(lines)


def _build_plan(
    repo: Path,
    vault: Path,
    branch_arg: str | None,
    branch_base_arg: str | None,
    project_arg: str | None,
) -> ArcheoPlan:
    user_self = _UserSelf(
        email=_git_config_get(repo, "user.email"),
        name=_git_config_get(repo, "user.name"),
    )

    branch = branch_arg or _current_branch(repo)
    if not branch:
        raise RuntimeError(
            f"Cannot resolve current branch in {repo}. Pass branch=… explicitly."
        )

    base_branch = branch_base_arg or _detect_default_branch(repo)
    head_sha = ""
    merge_base_sha = ""
    fully_merged = False
    try:
        head_sha = _run_git(["rev-parse", branch], repo)[0]
    except (RuntimeError, IndexError):
        head_sha = ""

    try:
        merge_base_sha = _run_git(
            ["merge-base", base_branch, branch], repo
        )[0]
        if head_sha and merge_base_sha == head_sha:
            fully_merged = True
    except (RuntimeError, IndexError):
        pass

    # base_sha for downstream: empty when fully merged (so range-based queries
    # know to fall through), else the merge-base SHA. For BranchInfo we
    # always surface the merge-base SHA when known.
    range_base_sha = "" if fully_merged else merge_base_sha
    branch_authors = (
        _list_branch_authors(repo, branch, range_base_sha)
        if not fully_merged
        else []
    )
    is_solo = (
        len(branch_authors) == 1
        and bool(user_self.email)
        and branch_authors[0].email == user_self.email
    )
    commits_count = (
        _commits_count(repo, range_base_sha, branch) if not fully_merged else 0
    )
    has_merges = (
        _has_merges_in_range(repo, range_base_sha, branch)
        if not fully_merged
        else False
    )

    branch_info = _BranchInfo(
        name=branch,
        base=base_branch,
        base_sha=merge_base_sha,
        head_sha=head_sha,
        fully_merged=fully_merged,
        commits_count=commits_count,
    )

    slug = _resolve_slug(repo, branch, project_arg)
    project = _resolve_project(vault, slug.candidate)
    scope = _resolve_scope(
        repo, branch, range_base_sha, fully_merged, base_branch=base_branch
    )

    # When fully-merged scope was resolved via the perimeter walker,
    # repop authors / commits / has_merges from the union of all captured
    # merge cycles. has_merges is True by construction (≥1 merge commit
    # captured), so granularity will lean toward by-merge.
    if scope.mode == "merged-via-perimeter":
        captured = find_branch_merges_via_perimeter(repo, branch, base_branch)
        if captured:
            email_counts: dict[str, _BranchAuthor] = {}
            total_commits = 0
            for bm in captured:
                # _list_branch_authors over each cycle's range.
                for a in _list_branch_authors(repo, bm.sha, bm.parent1):
                    if a.email not in email_counts:
                        email_counts[a.email] = _BranchAuthor(
                            email=a.email, name=a.name, commits=0
                        )
                    email_counts[a.email].commits += a.commits
                total_commits += _commits_count(repo, bm.parent1, bm.sha)
            branch_authors = sorted(
                email_counts.values(), key=lambda a: -a.commits
            )
            commits_count = total_commits
            has_merges = True  # ≥1 merge captured
            is_solo = (
                len(branch_authors) == 1
                and bool(user_self.email)
                and branch_authors[0].email == user_self.email
            )

    # When fully-merged scope was resolved via the single-tip merge-commit
    # walker (no perimeter cycles captured), repop from the deterministic
    # range M^1..M^2.
    if scope.mode == "merged-via-merge-commit":
        merge_info = find_merge_commit_for_branch(repo, branch, base_branch)
        if merge_info is not None:
            m_sha, parent1, parent2 = merge_info
            branch_authors = _list_branch_authors(repo, m_sha, parent1)
            commits_count = _commits_count(repo, parent1, m_sha)
            has_merges = _has_merges_in_range(repo, parent1, m_sha)
            is_solo = (
                len(branch_authors) == 1
                and bool(user_self.email)
                and branch_authors[0].email == user_self.email
            )

    # Recompute authors / commits_count / has_merges from the scope-glob
    # lineage when the range is empty (fully merged + auto-scope-by-name
    # fallback). Otherwise the granularity proposal sees commits_count=0
    # and emits the misleading "no-op effectively" reason; the filters
    # never detect is_solo correctly. This pass populates the missing
    # data from the repo-wide history of the matched directory.
    if (
        scope.mode == "auto-scope-by-name"
        and scope.scope_glob
        and not branch_authors
    ):
        scope_authors, scope_commits, scope_has_merges = _scope_glob_authors(
            repo, scope.scope_glob
        )
        if scope_authors:
            branch_authors = scope_authors
            commits_count = scope_commits
            has_merges = scope_has_merges
            is_solo = (
                len(branch_authors) == 1
                and bool(user_self.email)
                and branch_authors[0].email == user_self.email
            )

    # Reflect the (possibly repopulated) commits_count back into BranchInfo
    # so the user sees the same number that drove the granularity proposal.
    branch_info = _BranchInfo(
        name=branch_info.name,
        base=branch_info.base,
        base_sha=branch_info.base_sha,
        head_sha=branch_info.head_sha,
        fully_merged=branch_info.fully_merged,
        commits_count=commits_count,
    )

    granularity = _propose_granularity(
        commits_count=commits_count,
        has_merges=has_merges,
        authors_count=len(branch_authors),
        is_solo=is_solo,
    )
    filters = _propose_filters(is_solo)

    warnings = _build_warnings(
        {
            "slug": slug,
            "project": project,
            "branch": branch_info,
            "scope": scope,
            "granularity": granularity,
            "filters": filters,
            "branch_authors": branch_authors,
        }
    )

    next_call = _build_next_call(
        repo=repo,
        slug=slug.candidate,
        branch=branch,
        base_branch=base_branch,
        scope=scope,
    )

    plan = ArcheoPlan(
        repo_path=str(repo),
        user_self=user_self,
        branch=branch_info,
        branch_authors=branch_authors,
        is_solo_branch=is_solo,
        slug=slug,
        project=project,
        scope=scope,
        granularity=granularity,
        filters=filters,
        warnings=warnings,
        summary_md="",
        next_call=next_call,
    )
    plan.summary_md = _format_summary_md(plan)
    return plan


def _build_next_call(
    repo: Path,
    slug: str,
    branch: str,
    base_branch: str,
    scope: _ScopeProposal,
) -> dict:
    """Build the exact mem_archeo arguments matching the resolved scope.

    Doctrine : target the **orchestrator** (``mem_archeo``) — NOT
    ``mem_archeo_git`` directly — so the full chain runs : Phase 0
    topology → Phase 2 stack → Phase 3 git → Phase 1 brief
    auto-prepared. The LLM caller then completes Phase 1 finalize via
    a separate ``mem_archeo_context`` call (round-trip).

    Case study 2026-05-09 IRIS USER : the previous next_call pointed to
    mem_archeo_git, which bypassed Phase 0 topology + Phase 2 stack +
    Phase 1 brief. Result : 30 perimeter-mode archives written but no
    topology atom, no stack atoms, no context.md content. The vault
    looked populated but carried zero functional knowledge of the
    project. Targeting the orchestrator forces every phase to fire.

    Per mode :

    - 'live' / 'merged-via-perimeter' / 'merged-via-merge-commit' /
      'auto-scope-by-name' → branch_first=branch, branch_base=base_branch.
      acknowledged_via_plan=True (token round-trip with the cadrage gate).
    - 'since-sha' / 'since-date' → adds since_sha/since_date.
    - 'refusal' → empty dict; caller MUST re-invoke mem_archeo_plan with
      explicit anchor.
    """
    base: dict = {
        "tool": "mem_archeo",
        "repo_path": str(repo),
        "project": slug,
    }
    if scope.mode == "refusal":
        return {}
    if scope.mode in (
        "live",
        "merged-via-perimeter",
        "merged-via-merge-commit",
        "auto-scope-by-name",
    ):
        base["branch_first"] = branch
        base["branch_base"] = base_branch
        base["acknowledged_via_plan"] = True
        # mem_archeo defaults level=tags but we want commits-by-author
        # for branch-first runs (matches what perimeter mode actually
        # uses — it ignores these but other modes lean on them).
        base["level"] = "commits"
        base["window"] = "week"
        base["by_author"] = True
        return base
    if scope.mode == "since-sha":
        base["branch_first"] = branch
        base["branch_base"] = base_branch
        base["acknowledged_via_plan"] = True
        base["level"] = "commits"
        return base
    if scope.mode == "since-date":
        base["branch_first"] = branch
        base["branch_base"] = base_branch
        base["acknowledged_via_plan"] = True
        base["level"] = "commits"
        return base
    return base


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def mem_archeo_plan(
        repo_path: str = Field(..., description="Absolute path to the local Git repo."),
        branch: str | None = Field(
            None,
            description=(
                "Branch to plan archeo for. Defaults to current HEAD branch."
            ),
        ),
        branch_base: str | None = Field(
            None,
            description=(
                "Base branch for divergence (default: auto-detected via "
                "origin/HEAD or probing main/master/develop)."
            ),
        ),
        project: str | None = Field(
            None,
            description=(
                "Force the project slug (skips heuristic). Use only when you "
                "know the slug should NOT match the branch name."
            ),
        ),
    ) -> ArcheoPlan:
        """Phase 0 interactive cadrage of a branch-first archeo run.

        Read-only — never writes the vault. Captures the user's git identity,
        resolves the branch + base, lists branch authors, proposes a slug
        + project init flag + scope + granularity + filters, and surfaces
        warnings the LLM caller MUST present to the user before invoking
        ``mem_archeo_git``.

        See ``core/procedures/mem-archeo-git.md`` Phase 0 for the doctrinal
        usage flow (plan → user validation → mem_archeo_git with validated
        params).
        """
        config = get_config()
        vault = config.vault
        repo = Path(repo_path).expanduser().resolve()
        if not repo.is_dir():
            raise FileNotFoundError(f"repo_path is not a directory: {repo}")
        return _build_plan(
            repo=repo,
            vault=vault,
            branch_arg=branch,
            branch_base_arg=branch_base,
            project_arg=project,
        )
