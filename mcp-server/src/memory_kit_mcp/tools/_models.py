"""Pydantic response models shared across tools.

Each tool returns a typed BaseModel — FastMCP serializes it to both
structuredContent (typed) and text (Markdown rendering) for the client LLM.
"""

from __future__ import annotations

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
