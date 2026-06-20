"""Zone path resolvers — single source of truth for vault layout."""

from __future__ import annotations

import re
from pathlib import Path


def _norm_slug(s: str) -> str:
    """Collapse a slug to its alphanumeric skeleton for tolerant matching.

    ``"Second Brain"``, ``"second-brain"`` and ``"secondbrain"`` all map to
    ``"secondbrain"`` — so a user typing the project name with spaces, dashes
    or mixed case still resolves to the on-disk folder instead of triggering a
    disambiguation loop.
    """
    return re.sub(r"[^a-z0-9]", "", s.lower())

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


def branch_topology_file(vault: Path, slug: str, branch: str) -> Path:
    """Branch-specific topology file: {vault}/99-meta/repo-topology/{slug}-branches/{branch-san}.md"""
    branch_san = branch.replace("/", "-").replace("\\", "-")
    return (
        vault
        / ZONE_META
        / "repo-topology"
        / f"{slug}-branches"
        / f"{branch_san}.md"
    )


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

    # Tolerant fallback: match on the alphanumeric skeleton so "Second Brain"
    # or "second-brain" resolve to the "secondbrain" folder. Resolution order
    # is preserved (projects → archived → domains); only an unambiguous single
    # match is accepted to avoid silently loading the wrong project.
    target = _norm_slug(slug)
    if target:
        for lister, base, kind, is_archived in (
            (list_projects, project_dir, "project", False),
            (list_archived, archived_dir, "project", True),
            (list_domains, domain_dir, "domain", False),
        ):
            hits = [name for name in lister(vault) if _norm_slug(name) == target]
            if len(hits) == 1:
                return base(vault, hits[0]), kind, is_archived
    return None
