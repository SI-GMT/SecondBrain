"""mem_recall — Load a project/domain context from the vault to resume a session.

Spec: core/procedures/mem-recall.md
Shared blocks: _frontmatter-universal.md, _archived.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import (
    InventoryEntry,
    RecallInventory,
    RecallResult,
)
from memory_kit_mcp.vault import frontmatter, paths


def _load_context(folder: Path) -> tuple[dict[str, Any], str]:
    """Load context.md (fast path) or fall back to last archive."""
    ctx_file = folder / "context.md"
    if ctx_file.exists():
        return frontmatter.read(ctx_file)
    # Fallback: last archive
    archives_dir = folder / "archives"
    if archives_dir.exists():
        archives = sorted(archives_dir.glob("*.md"))
        if archives:
            return frontmatter.read(archives[-1])
    return {}, ""


def _load_topology(vault: Path, slug: str) -> dict[str, Any] | None:
    """Load 99-meta/repo-topology/{slug}.md frontmatter if present."""
    topo = paths.topology_file(vault, slug)
    if not topo.exists():
        return None
    fm, _ = frontmatter.read(topo)
    return fm


def _build_briefing_md(
    slug: str,
    kind: str,
    fm: dict[str, Any],
    body: str,
    archived: bool,
    topology_present: bool,
) -> str:
    """Render the briefing as Markdown — same shape as the procedure expects."""
    lines: list[str] = []
    if archived:
        lines.append(
            f"ℹ️ Project '{slug}' is currently archived "
            f"(since {fm.get('archived_at', 'unknown')}).\n"
            "   Loaded for read-only retrospective. To resume actively, run:\n"
            f"     /mem-historize {slug} --revive --apply\n"
        )
    lines.append(f"## Resume — {slug} ({kind})\n")
    if last := fm.get("last-session"):
        lines.append(f"**Last session**: {last!s}")
    if phase := fm.get("phase"):
        lines.append(f"**Current phase**: {phase!s}")
    if scope := fm.get("scope"):
        lines.append(f"**Scope**: {scope!s}")
    if topology_present:
        lines.append("\n*Topology captured — see `99-meta/repo-topology/` for details.*")
    else:
        lines.append("\n*Topology not yet captured — run /mem-archeo to populate.*")
    if body.strip():
        lines.append("\n---\n")
        lines.append(body.rstrip())
    return "\n".join(lines)


def _str_or_none(value: object) -> str | None:
    """PyYAML coerces ISO dates to datetime.date — normalize back to str for the API."""
    if value is None:
        return None
    return str(value)


def _do_recall(slug: str | None) -> RecallResult | RecallInventory:
    """Core implementation — pure function over a config + slug."""
    config = get_config()
    vault = config.vault

    if slug is None:
        # No slug given: try cwd-based auto-detect would require knowing client cwd,
        # which the MCP transport doesn't expose. Return inventory for disambiguation.
        projects = [
            InventoryEntry(slug=s, kind="project", archived=False)
            for s in paths.list_projects(vault)
        ]
        domains = [
            InventoryEntry(slug=s, kind="domain", archived=False)
            for s in paths.list_domains(vault)
        ]
        archived_count = len(paths.list_archived(vault))
        if not projects and not domains:
            msg = (
                f"No project/domain found in vault {vault}. "
                "Memory initialized — describe what you're working on and we'll start."
            )
        else:
            msg = (
                f"Multiple candidates available ({len(projects)} projects, "
                f"{len(domains)} domains, {archived_count} archived). "
                "Re-invoke mem_recall with an explicit slug."
            )
        return RecallInventory(
            projects=projects,
            domains=domains,
            archived_count=archived_count,
            message=msg,
        )

    # Slug given: resolve across projects → archived → domains
    resolved = paths.resolve_slug(vault, slug)
    if resolved is None:
        raise FileNotFoundError(
            f"No project or domain '{slug}' found in vault {vault}. "
            "Available: " + ", ".join(paths.list_projects(vault) + paths.list_domains(vault))
        )
    folder, kind, archived = resolved

    fm, body = _load_context(folder)
    topology = _load_topology(vault, slug) if kind == "project" else None
    topology_present = topology is not None

    briefing_md = _build_briefing_md(slug, kind, fm, body, archived, topology_present)

    return RecallResult(
        project=slug,
        kind=kind,
        archived=archived,
        archived_at=_str_or_none(fm.get("archived_at")),
        last_session=_str_or_none(fm.get("last-session")),
        phase=_str_or_none(fm.get("phase")),
        scope=_str_or_none(fm.get("scope")),
        topology_present=topology_present,
        workspace_member=_str_or_none(fm.get("workspace_member")) or None,
        briefing_md=briefing_md,
    )


def register(mcp: FastMCP) -> None:
    """Register mem_recall with the FastMCP instance."""

    @mcp.tool()
    def mem_recall(
        slug: str | None = Field(
            None,
            description=(
                "Slug of the project or domain to load. If omitted, returns the "
                "vault inventory for disambiguation. Resolution order: active "
                "projects → archived projects → domains."
            ),
        ),
    ) -> RecallResult | RecallInventory:
        """Load a project's context from the vault to resume a previous session.

        Reads the project's context.md (fast path) or falls back to the latest
        archive. Loads topology metadata if present. Returns a structured
        briefing that lets the LLM resume work without re-briefing.

        Auto-trigger when the user expresses a resumption intent ("let's
        resume", "where were we on X", "do you remember...") or asks to query
        memory.

        For archived projects, the slug must be given explicitly — they are
        not surfaced in implicit auto-detection per the _archived.md doctrine.
        """
        return _do_recall(slug)
