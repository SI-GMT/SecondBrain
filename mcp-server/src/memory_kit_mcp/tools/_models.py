"""Pydantic response models shared across tools.

Each tool returns a typed BaseModel — FastMCP serializes it to both
structuredContent (typed) and text (Markdown rendering) for the client LLM.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class LinkRef(BaseModel):
    """A wikilink-style reference to a vault file."""

    title: str
    target: str  # wikilink target without [[ ]] brackets
    extra: str | None = None  # optional inline qualifier (date, force, horizon, ...)


class PersonRef(BaseModel):
    """A person card reference."""

    name: str
    role: str | None = None
    last_interaction: str | None = None
    target: str  # wikilink target


class RecallResult(BaseModel):
    """Result of mem_recall — full project/domain briefing."""

    project: str = Field(..., description="Slug of the loaded project or domain.")
    kind: str = Field(..., description="'project' or 'domain'.")
    archived: bool = Field(False, description="True if loaded from 10-episodes/archived/.")
    archived_at: str | None = None
    last_session: str | None = None
    phase: str | None = None
    scope: str | None = None
    state_validated: list[str] = Field(default_factory=list)
    state_in_progress: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    active_principles: list[LinkRef] = Field(default_factory=list)
    open_goals: list[LinkRef] = Field(default_factory=list)
    architecture_atoms: list[LinkRef] = Field(default_factory=list)
    key_people: list[PersonRef] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    topology_present: bool = False
    workspace_member: str | None = None
    briefing_md: str = Field(..., description="Pre-formatted Markdown briefing for direct display.")


class InventoryEntry(BaseModel):
    """An entry in the disambiguation inventory returned when no slug is given."""

    slug: str
    kind: str  # 'project' | 'domain'
    archived: bool = False


class RecallInventory(BaseModel):
    """Returned when mem_recall is called without a slug and multiple candidates exist."""

    needs_disambiguation: bool = True
    projects: list[InventoryEntry] = Field(default_factory=list)
    domains: list[InventoryEntry] = Field(default_factory=list)
    archived_count: int = 0
    message: str


class ChangeReport(BaseModel):
    """Standardized result for tools that mutate the vault.

    Returned by mem_archive, mem_rename, mem_merge, mem_reclass, etc. Lets the
    LLM client surface a uniform diff summary to the user.
    """

    skill: str
    success: bool
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    files_deleted: list[str] = Field(default_factory=list)
    files_moved: list[tuple[str, str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_md: str


class ProjectListEntry(BaseModel):
    """One row in the inventory returned by mem_list."""

    slug: str
    kind: str  # "project" | "domain"
    archived: bool = False
    phase: str | None = None
    last_session: str | None = None
    scope: str | None = None
    archived_at: str | None = None
    archives_count: int = 0


class ListResult(BaseModel):
    """Result of mem_list — a snapshot of the vault inventory."""

    vault: str
    projects: list[ProjectListEntry] = Field(default_factory=list)
    domains: list[ProjectListEntry] = Field(default_factory=list)
    archived: list[ProjectListEntry] = Field(default_factory=list)
    summary_md: str


class SearchHit(BaseModel):
    """One match returned by mem_search."""

    path: str  # vault-relative path
    zone: str  # "00-inbox" / "10-episodes" / etc.
    line_number: int
    line: str
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Result of mem_search — ranked matches with context snippets."""

    query: str
    total_hits: int
    truncated: bool = False
    hits: list[SearchHit] = Field(default_factory=list)
    summary_md: str


class ArchiveDigest(BaseModel):
    """One archive entry summarized in mem_digest output."""

    filename: str  # e.g. "2026-04-30-14h00-alpha-initial.md"
    date: str | None = None
    subject: str | None = None
    body_excerpt: str  # first ~300 chars of the archive body


class DigestResult(BaseModel):
    """Result of mem_digest — synthesis of the last N archives."""

    project: str
    kind: str
    archives_returned: int
    archives_total: int
    archives: list[ArchiveDigest] = Field(default_factory=list)
    summary_md: str


class HealthFinding(BaseModel):
    """One finding produced by mem_health_scan."""

    category: str  # malformed-frontmatter | missing-display | empty-md | orphan-atom
    severity: str  # 'error' | 'warning' | 'info'
    path: str  # vault-relative
    message: str
    auto_fixable: bool = False


class HealthScanResult(BaseModel):
    """Result of mem_health_scan — vault audit (read-only)."""

    vault: str
    files_scanned: int
    findings_total: int
    by_category: dict[str, int] = Field(default_factory=dict)
    findings: list[HealthFinding] = Field(default_factory=list)
    summary_md: str


class HealthRepairResult(BaseModel):
    """Result of mem_health_repair — applies idempotent fixes."""

    vault: str
    dry_run: bool
    fixes_applied: int
    fixes_skipped: int
    findings_remaining: int
    files_modified: list[str] = Field(default_factory=list)
    summary_md: str


class IngestionResult(BaseModel):
    """Result of an ingestion tool (mem_note, mem_principle, mem_goal, mem_person, mem_doc, mem)."""

    skill: str
    success: bool
    atoms_created: int
    files_created: list[str] = Field(default_factory=list)
    target_zone: str
    summary_md: str


# ---------- Read tools (v0.9.3 — direct vault file readers) ----------


class VaultReadResult(BaseModel):
    """Generic result for read-only access to a vault Markdown file.

    Used by ``mem_read_archive``, ``mem_read_context``, ``mem_read_history`` —
    every tool that needs to surface the raw content of a single vault file
    with its parsed frontmatter, without going through ``mem_recall``'s full
    briefing synthesis.
    """

    path: str = Field(..., description="Vault-relative POSIX path of the file read.")
    slug: str = Field(..., description="Project or domain slug the file belongs to.")
    kind: str = Field(..., description="'project' or 'domain' or 'archive' or 'context' or 'history'.")
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    body: str = Field("", description="Full body of the file, frontmatter stripped.")
    summary_md: str = Field("", description="Short Markdown summary describing what was read.")


class TopologyReadResult(BaseModel):
    """Result of ``mem_get_topology`` — surface the persisted topology snapshot
    of a project (``99-meta/repo-topology/{slug}.md``) without re-scanning the
    repo. Useful for LLM-driven tasks (Phase 1 archeo, semantic analysis) that
    want the topology metadata without the cost of a fresh scan.
    """

    project: str
    topology_path: str = Field("", description="Vault-relative path. Empty if no topology persisted.")
    exists: bool = False
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    body: str = ""
    repo_path: str = ""
    repo_remote: str = ""
    content_hash: str = ""
    last_archive: str = ""
    summary_md: str


# ---------- Archeo (v0.8.x progressive port) ----------


class LayerResolution(BaseModel):
    """One resolved layer for mem_archeo_stack (Phase 2)."""

    layer: str  # frontend | backend | db | ci | infra | tests | tooling | other
    source_manifest: str  # repo-relative path of the main manifest
    technos: list[str] = Field(default_factory=list)
    summary_md: str  # ready-to-render body for the layer atom


class ArcheoStackResult(BaseModel):
    """Result of mem_archeo_stack — Phase 2 stack resolution."""

    project: str
    repo_path: str
    layers_resolved: int
    atoms_created: int
    atoms_revised: int
    atoms_skipped: int
    layers: list[LayerResolution] = Field(default_factory=list)
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_md: str


class MilestoneInfo(BaseModel):
    """One milestone processed by mem_archeo_git (Phase 3).

    Covers all four granularity levels: tags, releases (GitHub Releases),
    merges (GitHub PRs mergées), commits (commit windows). Fields specific
    to a given level remain empty for the others — keeps the schema flat
    and easy to render in summary tables.
    """

    # Common identification
    milestone_kind: str = "tag"  # 'tag' | 'release' | 'merge' | 'window'
    tag: str = ""  # e.g. "v0.8.0" (empty for non-tag milestones)
    commit_sha: str = ""  # full SHA (representative commit for windows / merge commit for merges)
    date: str = ""  # YYYY-MM-DD
    time: str = ""  # HH:MM
    author_name: str = ""
    author_email: str = ""
    subject: str = ""  # short tag/commit/release/PR subject
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0

    # Level=releases specific
    release_tag: str = ""  # e.g. "v0.9.0" (the tag the release points at)
    release_url: str = ""
    release_is_prerelease: bool = False
    release_is_draft: bool = False

    # Level=merges specific
    pr_number: int = 0
    pr_url: str = ""
    pr_base: str = ""  # base branch (target)
    pr_head: str = ""  # head branch (source)
    pr_merged_at: str = ""  # ISO timestamp

    # Level=commits specific
    window_label: str = ""  # e.g. "2026-W18" or "2026-05" or "2026-05-04"
    window_start: str = ""  # YYYY-MM-DD inclusive
    window_end: str = ""  # YYYY-MM-DD inclusive
    commit_count: int = 0  # commits aggregated in this window
    co_authors: list[str] = Field(default_factory=list)  # for --by-author granularity

    # Branch-first perimeter mode (one milestone per captured cycle)
    perimeter_score: float = 0.0
    perimeter_breakdown: dict[str, float] = Field(default_factory=dict)
    perimeter_files: list[str] = Field(default_factory=list)
    perimeter_range: str = ""  # M^1..M

    # Bookkeeping
    archive_path: str = ""  # vault-relative path of the resulting archive (empty if skipped)
    outcome: str = "skipped"  # 'created' | 'revised' | 'skipped'


class ArcheoGitResult(BaseModel):
    """Result of mem_archeo_git — Phase 3 Git history reconstruction."""

    project: str
    repo_path: str
    level: str  # 'tags' (others deferred)
    milestones_processed: int
    archives_created: int
    archives_revised: int
    archives_skipped: int
    milestones: list[MilestoneInfo] = Field(default_factory=list)
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_md: str


class ArcheoResult(BaseModel):
    """Result of mem_archeo — triphasic archeo orchestrator.

    Phase 1 (context) is intentionally skipped — semantic categorization is
    LLM territory. Phase 2 (stack) and Phase 3 (git) are run sequentially
    sharing a single Phase 0 topology scan.

    Branch-first cadrage gating (v0.10.x post-Gemini-drift) : when the
    orchestrator is invoked with ``branch_first=…`` and the caller has NOT
    yet acknowledged the plan (``acknowledged_via_plan=False``, the
    default), no writes happen — instead, ``needs_validation=True`` is set
    and ``plan`` carries the structured plan that the caller MUST surface
    to the user. The caller then re-invokes with the validated parameters
    and ``acknowledged_via_plan=True``. The empty stack/git/topology fields
    in that case are populated with default-empty placeholders.
    """

    project: str
    repo_path: str
    needs_validation: bool = Field(
        default=False,
        description=(
            "True when branch_first was set but acknowledged_via_plan=False. "
            "Caller MUST surface plan + get user validation, then re-invoke "
            "with acknowledged_via_plan=True. No writes happened in this "
            "response."
        ),
    )
    plan: ArcheoPlan | None = Field(
        default=None,
        description=(
            "Populated when needs_validation=True : the Phase 0 cadrage to "
            "present to the user."
        ),
    )
    phase_1_skipped: bool = True
    phase_1_message: str = ""
    stack: ArcheoStackResult | None = None
    git: ArcheoGitResult | None = None
    topology_path: str = ""  # vault-relative path of topology file (created or updated)
    topology_outcome: str = "skipped"  # 'created' | 'updated' | 'skipped'
    needs_context_synthesis: bool = Field(
        default=False,
        description=(
            "v0.10.x post-2026-05-09 : True after Phase 3 succeeded and "
            "Phase 1 brief was auto-prepared. The LLM caller MUST read the "
            "files in ``context_brief.files_to_read`` then invoke "
            "``mem_archeo_context(phase='finalize', ...)`` to write the "
            "topology atom + patch context.md. Bypassing this leaves "
            "context.md skeleton-empty (extraction-without-reading drift)."
        ),
    )
    context_brief: ArcheoContextBriefResult | None = Field(
        default=None,
        description=(
            "Populated when needs_context_synthesis=True : the Phase 1 "
            "brief result the LLM must process before context.md is "
            "considered alive."
        ),
    )
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_md: str


class UpdateCheckResult(BaseModel):
    """Result of mem_check_update — current vs latest GitHub release tag."""

    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    last_checked: float
    error: str | None = None
    summary_md: str


class ArcheoIndexResult(BaseModel):
    """Result of mem_archeo_index_files — Phase 0 file enumeration.

    Doctrine: ``core/procedures/_archeo-architecture-v2.md``.

    The list ``files`` is always the full enumeration (never truncated
    silently). When soft caps are exceeded, ``warnings`` carries a
    ``ScopeOverflowWarning`` line with batching guidance, but the list
    itself is intact. Use ``hard_abort=True`` on the input to refuse
    rather than warn.

    ``batches`` is a pre-computed slicing of ``files`` into chunks of
    ``batch_size`` (default 200). Always at least one batch (possibly
    empty) so downstream consumers have a uniform contract.
    """

    project: str
    repo_path: str
    source_mode: str  # 'git' | 'raw'
    scope_glob: str | None = None
    branch: str | None = None
    base_ref: str | None = None
    merge_base_strategy: str | None = None
    files: list[str]
    files_count: int
    files_bytes: int
    files_hash: str
    batches: list[list[str]]
    pass_b_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace: list[str] = Field(
        default_factory=list,
        description=(
            "Step-by-step trace of what enumerate_files did (mode detection, "
            "git commands, scope filtering, caps, hash, batches, Pass B). "
            "Constant size (~10-15 lines). Lets the LLM see decisions "
            "without diving into MCP server stderr logs."
        ),
    )
    summary_md: str


# ----------------------------------------------------------------------
# mem_archeo_plan (Phase 0 interactive cadrage, v0.10.x)
# ----------------------------------------------------------------------


class _UserSelf(BaseModel):
    """Identity of the user invoking mem_archeo_plan, captured from git config.

    Anchor for the 'self vs team' filter applied by Phase 3 archeo-git.
    Empty strings when git config is not set in the target repo.
    """

    email: str = Field(default="", description="git config user.email")
    name: str = Field(default="", description="git config user.name")


class _BranchInfo(BaseModel):
    """Resolved branch context for the archeo plan."""

    name: str = Field(..., description="Branch name (e.g. 'ecosav', 'feat/foo').")
    base: str = Field(..., description="Base ref used for divergence (e.g. 'master', 'main').")
    base_sha: str = Field(default="", description="Resolved base SHA, '' if unresolved.")
    head_sha: str = Field(default="", description="HEAD of the branch.")
    fully_merged: bool = Field(
        default=False,
        description=(
            "True if the branch is fully merged into ``base`` (merge-base == HEAD). "
            "Triggers auto-scope-by-name / by-files heuristic in downstream Phase 3."
        ),
    )
    commits_count: int = Field(
        default=0,
        description=(
            "Number of commits in the resolved scope (0 when fully merged + no "
            "by-files/auto-scope-by-name fallback)."
        ),
    )


class _BranchAuthor(BaseModel):
    """One author present in the branch scope."""

    email: str
    name: str
    commits: int = Field(default=0, description="Commits authored by this email in the scope.")


class _SlugProposal(BaseModel):
    """Proposed slug for the project the archeo will write under."""

    candidate: str = Field(
        ..., description="Proposed slug (kebab-case, ASCII-fold, ≥3 chars)."
    )
    source: str = Field(
        ...,
        description=(
            "How the slug was derived: 'project-arg' (user passed --project), "
            "'branch-name' (sanitized branch name, human-readable), "
            "'cwd-basename' (fallback: basename of repo_path), "
            "'needs-prompt' (cryptic branch — caller MUST ask the user)."
        ),
    )
    needs_confirmation: bool = Field(
        default=False,
        description=(
            "True if the LLM caller MUST surface the candidate to the user for "
            "confirmation before any side-effect runs. False = trust the heuristic."
        ),
    )
    reason: str = Field(
        default="",
        description="Human-readable reason behind the slug choice.",
    )


class _ProjectInfo(BaseModel):
    """State of the target project in the vault."""

    slug: str
    exists: bool = Field(
        default=False,
        description=(
            "True if {vault}/10-episodes/projects/{slug}/ already exists "
            "(with context.md + history.md)."
        ),
    )
    will_init: bool = Field(
        default=False,
        description=(
            "True if a fresh project skeleton will be created during Phase 5 "
            "(context.md + history.md + archives/). Implies exists=False."
        ),
    )
    path: str = Field(
        default="",
        description="Vault-relative path to the project (resolved or candidate).",
    )


class _ScopeProposal(BaseModel):
    """Resolution strategy + scope estimate for Phase 0 file enumeration."""

    mode: str = Field(
        ...,
        description=(
            "Strategy: 'live' (range-strict merge_base..branch), "
            "'merged-via-perimeter' (fully merged AND multi-signal walker "
            "captured ≥1 merge cycle via file/author/subject scoring with "
            "reciprocal-overlap reciprocity — primary strategy when "
            "fully_merged, handles dev-reset cycles where HEAD(branch) was "
            "reset to origin/base between cycles), "
            "'merged-via-merge-commit' (single absorbing merge commit M "
            "detectable on base first-parent — exact range = M^1..M^2, "
            "fallback when perimeter walker captures nothing), 'by-files' "
            "(commits touching files introduced by branch, repo-wide), "
            "'auto-scope-by-name' (every dir whose last component matches "
            "the branch name, repo-wide — fallback when no merge commit "
            "detectable, lost to squash/rebase), 'since-sha' / 'since-date' "
            "(explicit anchor), 'refusal' (fully merged + nothing matches — "
            "caller must override)."
        ),
    )
    scope_glob: str | None = Field(
        default=None,
        description=(
            "Backward-compatible single glob (= scope_globs[0] when populated). "
            "Legacy callers that only inspect one glob still work; new callers "
            "should read ``scope_globs`` to capture every matched dir."
        ),
    )
    scope_globs: list[str] = Field(
        default_factory=list,
        description=(
            "All directory globs matched by auto-scope-by-name (e.g. "
            "['src/Components/EcoSAV/**', 'src/REST/EcoSAV/**', "
            "'src/Models/EcoSAV/**']). Empty list when mode != 'auto-scope-by-name'. "
            "Phase 3 unions these via ``git log -- glob1 glob2 ...`` to capture "
            "every directory whose last component matches the branch name. The "
            "2026-05-09 case study showed taking only the deepest match drops "
            "4 of 5 EcoSAV directories on the IRIS USER repo."
        ),
    )
    files_count_estimate: int = Field(
        default=0,
        description="Files matched by the scope (Phase 0 enumeration estimate, union across all globs).",
    )
    files_bytes_estimate: int = Field(default=0)


class _GranularityProposal(BaseModel):
    """Proposed Phase 3 granularity, with reasoning."""

    proposed: str = Field(
        ...,
        description=(
            "One of: 'by-merge' (1 archive per merge in branch — narrative), "
            "'by-window-month' (1 archive per month, all authors), "
            "'by-window-week' (1 archive per week, all authors), "
            "'by-author-week' (1 archive per (author, week), fine-grained — "
            "use only when explicitly needed for HR-style attribution)."
        ),
    )
    reason: str = Field(
        default="",
        description=(
            "Heuristic reasoning. Examples: 'solo branch with merges → by-merge', "
            "'multi-author branch with no merges → by-window-month', etc."
        ),
    )


class _FilterProposal(BaseModel):
    """Proposed author-filter Phase 3 will apply."""

    author_self_only: bool = Field(
        default=False,
        description=(
            "True when only commits of user_self.email are kept. Default true on "
            "solo personal branches, false on collective branches — caller can "
            "override."
        ),
    )
    include_team: bool = Field(
        default=True,
        description=(
            "True keeps commits from all branch_authors. Mutually exclusive with "
            "author_self_only=True (the latter wins if both are set)."
        ),
    )


class ArcheoPlan(BaseModel):
    """Result of mem_archeo_plan — interactive Phase 0 cadrage.

    Doctrine: ``core/procedures/mem-archeo-git.md`` Phase 0 (v0.10.x).

    Read-only — never writes the vault. The LLM caller MUST surface this
    plan to the user, get explicit validation/override on the surfaced
    fields (slug, granularity, filters, project init), then invoke
    ``mem_archeo_git`` with the validated parameters. No subprocess git
    fires for archive writing as long as the plan is not approved.

    Tradeoff: 1 round-trip user (friction) — exactly the friction needed
    on operations with large blast radius (writing 50+ archives in the
    vault). Replaces the 2026-05-08 case study where Gemini mis-classified
    the slug, picked too-fine granularity, and skipped context/history
    creation entirely.
    """

    repo_path: str
    user_self: _UserSelf
    branch: _BranchInfo
    branch_authors: list[_BranchAuthor] = Field(default_factory=list)
    is_solo_branch: bool = Field(
        default=False,
        description="True iff branch_authors has exactly one entry == user_self.email.",
    )
    slug: _SlugProposal
    project: _ProjectInfo
    scope: _ScopeProposal
    granularity: _GranularityProposal
    filters: _FilterProposal
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Non-blocking warnings the caller should surface to the user before "
            "validation. Examples: 'branch name is cryptic, please confirm slug', "
            "'branch fully merged into base, scope resolved via auto-scope-by-name', "
            "'project does not exist yet, will be initialized', 'scope > 500 files, "
            "consider --by-merge granularity'."
        ),
    )
    summary_md: str = Field(
        ...,
        description=(
            "Pre-formatted Markdown summary of the plan, suitable for direct "
            "display to the user. Lists the proposed slug + reason, the project "
            "init flag, the scope estimate, the granularity + reason, the filters, "
            "and the warnings — in that order."
        ),
    )
    next_call: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Exact MCP arguments to pass to ``mem_archeo_git`` to execute the "
            "validated plan. The LLM caller MUST invoke ``mem_archeo_git`` with "
            "these arguments **literally** — no translation, no interpretation, "
            "no extra filters. The 2026-05-09 IRIS USER case study showed that "
            "free-form translation drops ``branch_first`` from the call when the "
            "plan proposes ``--by-merge`` granularity (the API has no "
            "``--by-merge`` flag — the perimeter mode produces one archive per "
            "cycle natively, granularity input is informational). Always carries "
            "``branch_first`` when ``scope.mode`` ∈ "
            "{'merged-via-perimeter', 'merged-via-merge-commit', "
            "'auto-scope-by-name', 'live'}."
        ),
    )


# ---------------------------------------------------------------------------
# mem_archeo_context — Phase 1 (LLM round-trip)
# ---------------------------------------------------------------------------


class _ArcheoCycleSummary(BaseModel):
    """One cycle's summary surfaced to the LLM during the brief phase."""

    sha: str
    date: str
    subject: str
    files: list[str] = Field(default_factory=list)


class ArcheoContextBriefResult(BaseModel):
    """Result of ``mem_archeo_context(phase='brief')``.

    Round-trip Phase 1 doctrine (v0.10.x post-2026-05-09 IRIS USER case
    study) : extraction-only archives lose all functional value. The LLM
    host (Claude / Gemini / Codex) MUST read the actual files in the
    project's perimeter and synthesize the result before the archeo cycle
    is considered finalized.

    The tool returns a paginated list of files to read + an instruction
    block + the synthesis schema the LLM is expected to fill. The LLM
    then re-invokes ``mem_archeo_context(phase='finalize',
    acknowledged_via_read=True, synthesis={...})`` to write the topology
    atom + patch context.md.
    """

    project: str
    needs_llm_read: bool = True
    batch: int = Field(
        default=1,
        description="1-indexed batch number when files exceed the per-call cap.",
    )
    total_batches: int = 1
    files_to_read: list[str] = Field(
        default_factory=list,
        description=(
            "Repo-relative paths the LLM MUST open with its file-reading tool "
            "(Read / read_file / equivalent). Capped per-batch to keep the LLM "
            "context budget reasonable. Read EVERY file in the batch — do not "
            "sample or skim."
        ),
    )
    cycles: list[_ArcheoCycleSummary] = Field(
        default_factory=list,
        description=(
            "Discovered merge cycles with their per-cycle files — context "
            "for the LLM to group its synthesis by sub-system."
        ),
    )
    synthesis_schema: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "JSON schema-like dict describing the structure expected in the "
            "``synthesis`` argument of the finalize call."
        ),
    )
    instructions: str = Field(
        default="",
        description=(
            "Plain-text directive executable by any LLM host. Lists exactly "
            "what to read, how to group, what schema to fill."
        ),
    )
    next_call: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Exact MCP arguments for the next call (either next brief batch "
            "or the finalize phase). Literal — do not translate."
        ),
    )
    summary_md: str = ""


class ArcheoContextSynthesis(BaseModel):
    """Schema the LLM MUST fill after reading files_to_read.

    Keys are intentionally generic so the schema works across project kinds
    (IRIS .cls components, Python modules, JS apps, SQL schemas, etc.).

    Strict validation (v0.10.x post-2026-05-09 IRIS USER) : ``components``
    must either be empty (LLM had nothing to surface) OR every component
    entry must carry a non-empty ``role`` AND a non-empty ``files`` list,
    each file with a non-empty ``path``. Half-filled entries (role only,
    no files; or files-without-paths) are rejected — the whole point of
    Phase 1 is the file-level mapping, not a top-level dir summary.
    """

    components: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Hierarchical component map. Keys = directories or sub-system "
            "names. Values = {role: str (REQUIRED, one-line), files: list of "
            "{path: str (REQUIRED), role: str, key_methods: list[str]}} — "
            "files MUST be non-empty when the component is included. "
            "Example: {'src/Components/EcoSAV/DossierDon': {'role': 'Storage "
            "layer for donation files', 'files': [{'path': 'Detail.cls', "
            "'role': 'Stores per-donation detail records', 'key_methods': "
            "['ValidateDossier']}]}}."
        ),
    )

    @field_validator("components")
    @classmethod
    def _validate_components(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("components must be a dict")
        for raw_name, comp in v.items():
            name = str(raw_name).strip().strip('"').strip("'").strip()
            if not isinstance(comp, dict):
                raise ValueError(
                    f"components[{name!r}] must be a dict with 'role' and 'files'"
                )
            role = str(comp.get("role", "")).strip()
            files = comp.get("files", [])
            if not role:
                raise ValueError(
                    f"components[{name!r}].role is empty — every component "
                    "MUST carry a one-line role (the LLM must explain what "
                    "this sub-system does, not just list its directory)."
                )
            if not isinstance(files, list) or not files:
                raise ValueError(
                    f"components[{name!r}].files is empty — every component "
                    "MUST list ≥1 file with a non-empty path. The whole "
                    "point of Phase 1 is the file-level mapping. If you "
                    "have nothing to say about this directory, drop it from "
                    "components entirely."
                )
            for i, f in enumerate(files):
                if not isinstance(f, dict):
                    raise ValueError(
                        f"components[{name!r}].files[{i}] must be a dict"
                    )
                path = str(f.get("path", "")).strip().strip('"').strip("'").strip()
                if not path:
                    raise ValueError(
                        f"components[{name!r}].files[{i}].path is empty — "
                        "every file entry MUST carry a non-empty repo-relative "
                        "path."
                    )
        return v
    domain_concepts: list[str] = Field(
        default_factory=list,
        description=(
            "Business / domain vocabulary the LLM extracted from file "
            "contents (one line per concept). Example: 'DOSSIERDON = "
            "donation file flag, default 0', 'savRegion = SAV region "
            "reference table'."
        ),
    )
    patterns: list[str] = Field(
        default_factory=list,
        description=(
            "Recurring code/architectural patterns. Example: '3-layer split "
            "(Components/Models/Interface)', 'JSON adapter pattern via "
            "%JSON.Adaptor'."
        ),
    )
    decisions: list[str] = Field(
        default_factory=list,
        description=(
            "Implicit decisions surfaced by the file contents. Example: "
            "'Anonymisation enforced at sync layer, not storage', "
            "'CODEETABLISSEMENT used as cross-cutting partition key'."
        ),
    )
    risks_or_friction: list[str] = Field(
        default_factory=list,
        description=(
            "Risks / friction points the LLM noticed while reading. Example: "
            "'No validation on DOSSIERDON setter — set silently'."
        ),
    )


class ArcheoContextFinalizeResult(BaseModel):
    """Result of ``mem_archeo_context(phase='finalize')``."""

    project: str
    success: bool
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_md: str = ""


# ---------------------------------------------------------------------------
# mem_help — localized help for mem-* commands
# ---------------------------------------------------------------------------


class _CommandEntry(BaseModel):
    """One mem-* command surfaced in the general help index."""

    command: str = Field(..., description="Kebab-case command name, e.g. 'mem-archeo'.")
    description: str = Field(default="", description="One-line description (from procedure frontmatter).")
    category: str = Field(
        default="misc",
        description="Category key : 'session' | 'capture' | 'archeo' | 'vault' | 'hygiene' | 'misc'.",
    )


class HelpResult(BaseModel):
    """Result of ``mem_help`` — either general help or command-specific help.

    When called without ``command``, returns the general index of all
    ``mem-*`` commands grouped by category. When called with a specific
    ``command``, returns its description + triggers + arguments + examples
    + see-also extracted from ``core/procedures/{command}.md``.

    All wrapper labels are localized via ``core/i18n/strings.yaml``
    (en / fr / es / de / ru). The procedure body content remains in its
    canonical English (the procedures are the LLM-side source of truth and
    stay in EN for precision); only the surrounding chrome translates.
    """

    command: str | None = Field(
        default=None,
        description="The command this help is about. None = general help.",
    )
    language: str = Field(
        default="en",
        description="Resolved language code (en/fr/es/de/ru) used for wrapper labels.",
    )
    title: str = Field(default="", description="Localized title.")
    description: str = Field(
        default="",
        description=(
            "One-line description from the procedure's frontmatter "
            "``description`` field. Empty when general help."
        ),
    )
    triggers: str = Field(
        default="",
        description=(
            "Markdown body of the procedure's ``## Trigger`` section "
            "(natural-language phrases + slash invocations)."
        ),
    )
    arguments: str = Field(
        default="",
        description="Markdown body of the procedure's ``## Arguments`` (or equivalent) section.",
    )
    examples: str = Field(
        default="",
        description="Markdown body of the procedure's ``## Examples`` section, when present.",
    )
    see_also: list[str] = Field(
        default_factory=list,
        description="Related commands surfaced for navigation.",
    )
    commands: list[_CommandEntry] = Field(
        default_factory=list,
        description="General help only : full inventory grouped by category.",
    )
    summary_md: str = Field(
        default="",
        description="Pre-formatted Markdown ready for direct display.",
    )
