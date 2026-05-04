"""mem_list — Inventory of all projects and domains in the vault.

Spec: core/procedures/mem-list.md
"""

from __future__ import annotations

from fastmcp import FastMCP

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ListResult, ProjectListEntry
from memory_kit_mcp.vault import scanner


def _to_entry(s: scanner.ProjectSummary) -> ProjectListEntry:
    return ProjectListEntry(
        slug=s.slug,
        kind=s.kind,
        archived=s.archived,
        phase=s.phase,
        last_session=s.last_session,
        scope=s.scope,
        archived_at=s.archived_at,
        archives_count=s.archives_count,
    )


def _format_summary_md(
    vault: str,
    projects: list[ProjectListEntry],
    domains: list[ProjectListEntry],
    archived: list[ProjectListEntry],
    include_archived: bool,
) -> str:
    """Render the inventory as Markdown — same shape as the procedure expects."""
    lines: list[str] = [f"## Vault inventory — {vault}\n"]

    lines.append(f"### Projects ({len(projects)})")
    if not projects:
        lines.append("_(none)_\n")
    else:
        for p in projects:
            extras: list[str] = []
            if p.phase:
                extras.append(f"phase={p.phase}")
            if p.last_session:
                extras.append(f"last={p.last_session}")
            if p.scope:
                extras.append(f"scope={p.scope}")
            if p.archives_count:
                extras.append(f"{p.archives_count} archives")
            tail = f" — {', '.join(extras)}" if extras else ""
            lines.append(f"- **{p.slug}**{tail}")
        lines.append("")

    lines.append(f"### Domains ({len(domains)})")
    if not domains:
        lines.append("_(none)_\n")
    else:
        for d in domains:
            extras = []
            if d.phase:
                extras.append(f"phase={d.phase}")
            if d.last_session:
                extras.append(f"last={d.last_session}")
            tail = f" — {', '.join(extras)}" if extras else ""
            lines.append(f"- **{d.slug}**{tail}")
        lines.append("")

    if include_archived and archived:
        lines.append(f"### Archived projects ({len(archived)})")
        for a in archived:
            tail = f" — archived: {a.archived_at}" if a.archived_at else ""
            lines.append(f"- {a.slug}{tail}")
        lines.append("")
    elif archived:
        lines.append(f"### Archived projects ({len(archived)}, hidden)")
        lines.append("_use `include_archived=True` to expand_\n")

    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    """Register mem_list with the FastMCP instance."""

    @mcp.tool()
    def mem_list(
        include_archived: bool = False,
        archived_only: bool = False,
    ) -> ListResult:
        """List all projects and domains in the vault.

        By default returns active projects + domains and only the count of
        archived projects (per the _archived.md doctrine — archived projects
        are second-class for routine inventory).

        Args:
            include_archived: if True, include the full list of archived projects.
            archived_only: if True, return ONLY the archived projects (overrides
                include_archived).
        """
        config = get_config()
        vault = config.vault
        scanned_archived = [_to_entry(s) for s in scanner.scan_archived(vault)]

        if archived_only:
            return ListResult(
                vault=str(vault),
                projects=[],
                domains=[],
                archived=scanned_archived,
                summary_md=_format_summary_md(
                    str(vault), [], [], scanned_archived, include_archived=True
                ),
            )

        scanned_projects = [_to_entry(s) for s in scanner.scan_projects(vault)]
        scanned_domains = [_to_entry(s) for s in scanner.scan_domains(vault)]
        return ListResult(
            vault=str(vault),
            projects=scanned_projects,
            domains=scanned_domains,
            archived=scanned_archived if include_archived else [],
            summary_md=_format_summary_md(
                str(vault),
                scanned_projects,
                scanned_domains,
                scanned_archived,
                include_archived=include_archived,
            ),
        )
