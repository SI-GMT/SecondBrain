"""Vault scanner — walk the vault, collect projects/domains, expose metadata.

Used by mem_list, mem_search, mem_digest, and any tool that needs an inventory
of vault contents.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memory_kit_mcp.vault import frontmatter, paths


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    """One row in the project/domain inventory."""

    slug: str
    kind: str  # "project" | "domain"
    archived: bool
    phase: str | None
    last_session: str | None
    scope: str | None
    archived_at: str | None
    archives_count: int


def _load_summary(folder: Path, slug: str, kind: str, archived: bool) -> ProjectSummary:
    """Build a ProjectSummary from a folder. Reads context.md frontmatter if present."""
    ctx = folder / "context.md"
    fm: dict[str, Any] = {}
    if ctx.exists():
        try:
            fm, _ = frontmatter.read(ctx)
        except (ValueError, OSError):
            fm = {}
    archives_dir = folder / "archives"
    archives_count = (
        sum(1 for _ in archives_dir.glob("*.md")) if archives_dir.exists() else 0
    )
    return ProjectSummary(
        slug=slug,
        kind=kind,
        archived=archived,
        phase=str(fm.get("phase")) if fm.get("phase") is not None else None,
        last_session=str(fm.get("last-session")) if fm.get("last-session") is not None else None,
        scope=str(fm.get("scope")) if fm.get("scope") is not None else None,
        archived_at=str(fm.get("archived_at")) if fm.get("archived_at") is not None else None,
        archives_count=archives_count,
    )


def scan_projects(vault: Path) -> list[ProjectSummary]:
    """All active projects under 10-episodes/projects/."""
    return [
        _load_summary(paths.project_dir(vault, slug), slug, "project", archived=False)
        for slug in paths.list_projects(vault)
    ]


def scan_domains(vault: Path) -> list[ProjectSummary]:
    """All domains under 10-episodes/domains/."""
    return [
        _load_summary(paths.domain_dir(vault, slug), slug, "domain", archived=False)
        for slug in paths.list_domains(vault)
    ]


def scan_archived(vault: Path) -> list[ProjectSummary]:
    """All archived projects under 10-episodes/archived/."""
    return [
        _load_summary(paths.archived_dir(vault, slug), slug, "project", archived=True)
        for slug in paths.list_archived(vault)
    ]
