"""v2 migration — split namespace projects into domain + branch-projects.

Pre-amendment v0.10.x, ``mem_archeo`` archived branches under the namespace
project slug (e.g. ``gmt-user`` for the IRIS USER repo's branches like
``ecosav`` and ``dev-compta``). Post-Codex case study (2026-05-08), the
convention is fixed by ``core/procedures/_memory-structure.md``:

    Namespace -> domain (functional scope) + topology (organisational scope)
    Branch    -> project / feature, linked to a domain

This migration detects projects whose ``archives/`` carries ≥ 2 archives
with distinct ``branch:`` frontmatter values (the namespace heuristic) and
splits them:

- ``10-episodes/projects/<namespace>/`` is left untouched. The user can
  remove it manually once they've reviewed the new structure — the
  migration deliberately avoids destructive moves so the original
  remains traceable during the transition.

- ``10-episodes/domains/<namespace>/`` is created with a minimal
  ``context.md`` + ``history.md`` linking to the new branch projects.

- ``10-episodes/projects/<branch-slug>/`` is created for each distinct
  branch found in the archives. Slug is derived from the branch name
  (``slugify``), prefixed by the namespace if it would collide with an
  existing project. Each branch project gets ``context.md`` + ``history.md``
  + an ``archives/`` directory populated by **copying** the matching archives
  from the namespace project, with frontmatter updated:

  - ``project: <branch-slug>`` (was: ``<namespace>``)
  - ``domain: <namespace>`` (added — links the archive back up)

Idempotent: re-running the migration after a partial completion only
fills in what's missing. Skips items that already exist.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from memory_kit_mcp.migrations import MigrationStepReport
from memory_kit_mcp.vault import frontmatter
from memory_kit_mcp.vault.atomic_io import write_atomic


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def is_needed(vault: Path) -> bool:
    """True iff at least one namespace candidate has missing domain or branch projects."""
    candidates = _detect_namespace_projects(vault)
    if not candidates:
        return False
    for slug, branches_info in candidates:
        domain_dir = vault / "10-episodes" / "domains" / slug
        if not domain_dir.is_dir():
            return True
        for branch, _ in branches_info:
            branch_slug = _resolve_branch_project_slug(vault, slug, branch)
            project_dir = vault / "10-episodes" / "projects" / branch_slug
            if not project_dir.is_dir():
                return True
    return False


def apply(vault: Path, dry_run: bool) -> MigrationStepReport:
    """Create the domain + branch projects for every detected namespace.

    Conservative: never deletes the original namespace project. The user
    decides when (if ever) to drop it manually.
    """
    report = MigrationStepReport(
        target_version=2,
        module="v2_namespace_to_domain",
        needed=True,
        applied=False,
        dry_run=dry_run,
    )

    candidates = _detect_namespace_projects(vault)
    if not candidates:
        report.summary = "No namespace candidate detected."
        return report

    summary_lines: list[str] = []

    for slug, branches_info in candidates:
        domain_dir = vault / "10-episodes" / "domains" / slug
        domain_created = False
        if not domain_dir.is_dir():
            if dry_run:
                report.files_created.append(
                    str((domain_dir / "context.md").relative_to(vault).as_posix())
                )
                report.files_created.append(
                    str((domain_dir / "history.md").relative_to(vault).as_posix())
                )
                domain_created = True
            else:
                _create_domain_skeleton(vault, slug, branches_info)
                report.files_created.append(
                    f"10-episodes/domains/{slug}/context.md"
                )
                report.files_created.append(
                    f"10-episodes/domains/{slug}/history.md"
                )
                domain_created = True

        for branch, archive_paths in branches_info:
            branch_slug = _resolve_branch_project_slug(vault, slug, branch)
            project_dir = vault / "10-episodes" / "projects" / branch_slug
            project_created = False
            if not project_dir.is_dir():
                if dry_run:
                    report.files_created.append(
                        f"10-episodes/projects/{branch_slug}/context.md"
                    )
                    report.files_created.append(
                        f"10-episodes/projects/{branch_slug}/history.md"
                    )
                    project_created = True
                else:
                    _create_project_skeleton(vault, branch_slug, slug, branch)
                    report.files_created.append(
                        f"10-episodes/projects/{branch_slug}/context.md"
                    )
                    report.files_created.append(
                        f"10-episodes/projects/{branch_slug}/history.md"
                    )
                    project_created = True

            for archive_src in archive_paths:
                archive_dst = project_dir / "archives" / archive_src.name
                if archive_dst.is_file():
                    continue
                rel_dst = (
                    f"10-episodes/projects/{branch_slug}/archives/{archive_src.name}"
                )
                if dry_run:
                    report.files_created.append(rel_dst)
                else:
                    _copy_archive_with_updated_frontmatter(
                        archive_src, archive_dst,
                        branch_slug=branch_slug, namespace=slug,
                    )
                    report.files_created.append(rel_dst)

            if project_created or any(
                p.startswith(f"10-episodes/projects/{branch_slug}/archives/")
                for p in report.files_created
            ):
                summary_lines.append(
                    f"  - {slug}/{branch} -> projects/{branch_slug}/ "
                    f"({len(archive_paths)} archive(s))"
                )

        if domain_created:
            summary_lines.append(f"  - domains/{slug}/ created")

    if dry_run:
        report.summary = (
            f"Would migrate {len(candidates)} namespace(s):\n"
            + "\n".join(summary_lines)
            + "\n(dry-run — no files written)"
        )
    else:
        report.applied = True
        report.summary = (
            f"Migrated {len(candidates)} namespace(s):\n"
            + "\n".join(summary_lines)
        )
    return report


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _detect_namespace_projects(
    vault: Path,
) -> list[tuple[str, list[tuple[str, list[Path]]]]]:
    """Scan ``10-episodes/projects/`` and return namespace candidates.

    A project ``<slug>`` is a candidate iff its ``archives/`` directory
    contains ≥ 2 archives with frontmatter ``source: archeo-git`` whose
    ``branch:`` values are distinct (and non-empty).

    Returns ``[(namespace_slug, [(branch_name, [archive_path, ...]), ...]), ...]``,
    sorted by namespace slug. The branches are also sorted by name.
    """
    projects_dir = vault / "10-episodes" / "projects"
    if not projects_dir.is_dir():
        return []

    out: list[tuple[str, list[tuple[str, list[Path]]]]] = []
    for project_dir in sorted(projects_dir.iterdir(), key=lambda p: p.name):
        if not project_dir.is_dir():
            continue
        archives_dir = project_dir / "archives"
        if not archives_dir.is_dir():
            continue

        # Group archives by branch name (only those carrying source=archeo-git
        # and a non-empty branch field).
        by_branch: dict[str, list[Path]] = {}
        for arc in sorted(archives_dir.glob("*.md")):
            try:
                fm, _ = frontmatter.read(arc)
            except (OSError, ValueError):
                continue
            if str(fm.get("source") or "") != "archeo-git":
                continue
            branch = str(fm.get("branch") or "").strip()
            if not branch:
                continue
            by_branch.setdefault(branch, []).append(arc)

        if len(by_branch) >= 2:
            branches_sorted = sorted(by_branch.items(), key=lambda kv: kv[0])
            out.append((project_dir.name, branches_sorted))

    return out


# ---------------------------------------------------------------------------
# Slug resolution
# ---------------------------------------------------------------------------


_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9-]+")


def _slugify(value: str) -> str:
    """Sanitize a string into a vault-safe slug.

    Rules:
    - ASCII fold (drop accents).
    - Lowercase.
    - Replace ``/`` and whitespace with ``-``.
    - Drop any character outside ``[a-z0-9-]``.
    - Collapse repeated dashes, strip leading / trailing dashes.
    """
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", errors="ignore").decode("ascii")
    lowered = ascii_only.lower().replace("/", "-").replace(" ", "-").replace("_", "-")
    cleaned = _SLUG_NON_ALNUM.sub("-", lowered)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "branch"


def _resolve_branch_project_slug(
    vault: Path, namespace: str, branch: str
) -> str:
    """Return the slug to use for the branch project, with collision avoidance.

    First tries the bare slugified branch name. If a project with that name
    already exists AND is not the candidate for this same namespace (i.e.
    not already migrated), prefixes with the namespace to disambiguate.
    """
    bare = _slugify(branch)
    project_dir = vault / "10-episodes" / "projects" / bare
    if not project_dir.is_dir():
        return bare
    # Existing project — check if it's the one we previously migrated for
    # this namespace (idempotent re-run).
    context = project_dir / "context.md"
    if context.is_file():
        try:
            fm, _ = frontmatter.read(context)
        except (OSError, ValueError):
            fm = {}
        if str(fm.get("domain") or "") == namespace and str(fm.get("branch") or "") == branch:
            return bare
    # Collision with an unrelated project — namespace it.
    return f"{namespace}-{bare}"


# ---------------------------------------------------------------------------
# Skeleton writers
# ---------------------------------------------------------------------------


def _create_domain_skeleton(
    vault: Path,
    slug: str,
    branches_info: list[tuple[str, list[Path]]],
) -> None:
    """Write ``10-episodes/domains/<slug>/{context.md,history.md}`` if missing."""
    domain_dir = vault / "10-episodes" / "domains" / slug
    domain_dir.mkdir(parents=True, exist_ok=True)

    related_projects = [
        _resolve_branch_project_slug(vault, slug, branch)
        for branch, _ in branches_info
    ]

    context_fm: dict[str, Any] = {
        "zone": "episodes",
        "kind": "domain",
        "slug": slug,
        "scope": "work",
        "collective": False,
        "display": f"{slug} — domain",
        "tags": [
            f"domain/{slug}",
            "zone/episodes",
            "kind/domain",
        ],
        "related_projects": related_projects,
        "related_topology": f"99-meta/repo-topology/{slug}.md",
    }
    context_body = (
        f"# {slug} — domain\n\n"
        f"> Migré depuis `10-episodes/projects/{slug}/` via la migration v2 "
        f"(post-Codex case study, doctrine `_memory-structure.md`). Le project "
        f"namespace original n'a pas été supprimé — l'utilisateur le retire "
        f"quand satisfait du nouveau découpage.\n\n"
        f"## Projets de branche rattachés\n\n"
    )
    for slug_b in related_projects:
        context_body += f"- [[10-episodes/projects/{slug_b}/context|{slug_b}]]\n"
    context_body += (
        f"\n## Topologie\n\n"
        f"- [[99-meta/repo-topology/{slug}|topology]] _(si présente)_\n"
    )
    frontmatter.write(domain_dir / "context.md", context_fm, context_body)

    history_fm: dict[str, Any] = {
        "zone": "episodes",
        "kind": "domain",
        "slug": slug,
        "display": f"{slug} — history",
        "tags": [
            f"domain/{slug}",
            "zone/episodes",
            "kind/domain",
        ],
    }
    history_body = (
        f"# {slug} — historique du domain\n\n"
        f"> Fil chronologique meta-projets sous ce domain. Voir aussi : "
        f"[contexte](context.md)\n\n"
        f"_(Les sessions sont archivées par projet de branche, pas ici.)_\n"
    )
    frontmatter.write(domain_dir / "history.md", history_fm, history_body)


def _create_project_skeleton(
    vault: Path, branch_slug: str, namespace: str, branch: str
) -> None:
    """Write ``10-episodes/projects/<branch_slug>/{context.md,history.md}`` if missing."""
    project_dir = vault / "10-episodes" / "projects" / branch_slug
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "archives").mkdir(parents=True, exist_ok=True)

    context_fm: dict[str, Any] = {
        "zone": "episodes",
        "kind": "project",
        "slug": branch_slug,
        "scope": "work",
        "collective": False,
        "domain": namespace,
        "branch": branch,
        "display": f"{branch_slug} — project",
        "tags": [
            f"project/{branch_slug}",
            "zone/episodes",
            "kind/project",
            f"domain/{namespace}",
            f"branch/{branch}",
        ],
        "workspace_member": "",
    }
    context_body = (
        f"# {branch_slug} — project\n\n"
        f"> Project rattaché au domain "
        f"[[10-episodes/domains/{namespace}/context|{namespace}]]. "
        f"Issu de la migration v2 (`_memory-structure.md`).\n\n"
        f"## Branche source\n\n"
        f"- Branche Git : `{branch}`\n"
        f"- Domain parent : `{namespace}`\n"
        f"- Archives : voir `archives/`.\n"
    )
    frontmatter.write(project_dir / "context.md", context_fm, context_body)

    history_fm: dict[str, Any] = {
        "zone": "episodes",
        "kind": "project",
        "slug": branch_slug,
        "display": f"{branch_slug} — history",
        "tags": [
            f"project/{branch_slug}",
            "zone/episodes",
            "kind/project",
        ],
    }
    history_body = (
        f"# {branch_slug} — historique des sessions\n\n"
        f"> Fil chronologique des sessions du project. Voir aussi : "
        f"[contexte](context.md)\n\n"
        f"_(mem_archive prepend les nouvelles entrées ici.)_\n"
    )
    frontmatter.write(project_dir / "history.md", history_fm, history_body)


def _copy_archive_with_updated_frontmatter(
    src: Path, dst: Path, *, branch_slug: str, namespace: str
) -> None:
    """Copy ``src`` to ``dst`` rewriting its frontmatter:

    - ``project: <namespace>`` -> ``project: <branch_slug>``.
    - Add / set ``domain: <namespace>``.
    - Update ``tags`` to swap ``project/<namespace>`` -> ``project/<branch_slug>``
      and add ``domain/<namespace>`` if absent.

    All other fields are preserved as-is. Atomic write.
    """
    fm, body = frontmatter.read(src)
    fm = dict(fm)  # avoid mutating shared state
    fm["project"] = branch_slug
    fm["domain"] = namespace

    raw_tags = fm.get("tags") or []
    if isinstance(raw_tags, list):
        rewritten: list[str] = []
        for t in raw_tags:
            if isinstance(t, str) and t == f"project/{namespace}":
                rewritten.append(f"project/{branch_slug}")
            elif isinstance(t, str):
                rewritten.append(t)
        domain_tag = f"domain/{namespace}"
        if domain_tag not in rewritten:
            rewritten.append(domain_tag)
        fm["tags"] = rewritten

    dst.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(dst, frontmatter.serialize(fm, body))
