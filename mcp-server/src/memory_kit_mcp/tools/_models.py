"""Pydantic response models shared across tools.

Each tool returns a typed BaseModel — FastMCP serializes it to both
structuredContent (typed) and text (Markdown rendering) for the client LLM.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
    """

    project: str
    repo_path: str
    phase_1_skipped: bool = True
    phase_1_message: str
    stack: ArcheoStackResult
    git: ArcheoGitResult
    topology_path: str = ""  # vault-relative path of topology file (created or updated)
    topology_outcome: str = "skipped"  # 'created' | 'updated' | 'skipped'
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
