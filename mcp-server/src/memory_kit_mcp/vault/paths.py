"""Zone path resolvers — single source of truth for vault layout."""

from __future__ import annotations

from pathlib import Path

# Canonical zone names (English, brain-centric v0.5+)
ZONE_INBOX = "00-inbox"
ZONE_EPISODES = "10-episodes"
ZONE_KNOWLEDGE = "20-knowledge"
ZONE_PROCEDURES = "30-procedures"
ZONE_PRINCIPLES = "40-principles"
ZONE_GOALS = "50-goals"
ZONE_PEOPLE = "60-people"
ZONE_COGNITION = "70-cognition"
ZONE_META = "99-meta"

ALL_ZONES = (
    ZONE_INBOX,
    ZONE_EPISODES,
    ZONE_KNOWLEDGE,
    ZONE_PROCEDURES,
    ZONE_PRINCIPLES,
    ZONE_GOALS,
    ZONE_PEOPLE,
    ZONE_COGNITION,
    ZONE_META,
)


def project_dir(vault: Path, slug: str) -> Path:
    """Active project folder: {vault}/10-episodes/projects/{slug}/"""
    return vault / ZONE_EPISODES / "projects" / slug


def domain_dir(vault: Path, slug: str) -> Path:
    """Domain folder: {vault}/10-episodes/domains/{slug}/"""
    return vault / ZONE_EPISODES / "domains" / slug


def archived_dir(vault: Path, slug: str) -> Path:
    """Archived project folder: {vault}/10-episodes/archived/{slug}/"""
    return vault / ZONE_EPISODES / "archived" / slug


def topology_file(vault: Path, slug: str) -> Path:
    """Repo topology file: {vault}/99-meta/repo-topology/{slug}.md"""
    return vault / ZONE_META / "repo-topology" / f"{slug}.md"


def index_file(vault: Path) -> Path:
    """Root index: {vault}/index.md"""
    return vault / "index.md"


def list_projects(vault: Path) -> list[str]:
    """List active project slugs (excluding archived)."""
    base = vault / ZONE_EPISODES / "projects"
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def list_domains(vault: Path) -> list[str]:
    """List domain slugs."""
    base = vault / ZONE_EPISODES / "domains"
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def list_archived(vault: Path) -> list[str]:
    """List archived project slugs."""
    base = vault / ZONE_EPISODES / "archived"
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def resolve_slug(vault: Path, slug: str) -> tuple[Path, str, bool] | None:
    """Find a slug across projects, domains, and archived locations.

    Returns (folder_path, kind, archived) where kind is 'project' | 'domain'
    and archived is True only for projects under 10-episodes/archived/.
    Resolution order per _archived.md doctrine: projects → archived → domains.
    Returns None if no match.
    """
    p = project_dir(vault, slug)
    if p.exists():
        return p, "project", False
    a = archived_dir(vault, slug)
    if a.exists():
        return a, "project", True
    d = domain_dir(vault, slug)
    if d.exists():
        return d, "domain", False
    return None
