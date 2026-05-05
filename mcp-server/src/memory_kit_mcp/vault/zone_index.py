"""Zone index generation — single source of truth for ``{zone}/index.md``.

In v0.9.3 and earlier, the zone-level ``index.md`` files (``20-knowledge/index.md``,
``40-principles/index.md``, ``50-goals/index.md``, ``60-people/index.md``) were
empty stubs and the listing of every transverse atom lived in the **root**
``index.md``. That made the root index expensive to update on each ingestion
(every ingestion required rewriting the root) and forced ``rebuild-vault-index.py``
to be run manually.

v0.9.4 moves the per-atom listing **into the zone index** of each transverse
zone. The root index keeps only the high-level navigation (zones, projects,
domains, archives). This module is the canonical generator of zone index
bodies — both ingestion tools and the rebuild script consume it.

Idempotent. Atomic write via ``vault.atomic_io``. UTF-8 / LF.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from memory_kit_mcp.vault import frontmatter
from memory_kit_mcp.vault.atomic_io import write_atomic

# Zones whose atoms ARE listed in their own zone index (transverse atoms).
# Other zones (00-inbox, 10-episodes, 30-procedures, 70-cognition, 99-meta)
# have different listing semantics and stay out of this module's scope.
ATOM_ZONES: tuple[str, ...] = (
    "20-knowledge",
    "40-principles",
    "50-goals",
    "60-people",
)

# Display name per zone (zone -> headline) — neutral English. Translation,
# if ever needed, happens in the consuming layer (rebuild-vault-index.py
# uses this internally and can re-render with localized strings).
ZONE_DISPLAY_NAMES: dict[str, str] = {
    "20-knowledge": "Knowledge",
    "40-principles": "Principles",
    "50-goals": "Goals",
    "60-people": "People",
}

# Description blurb per zone (used as zone index intro)
ZONE_DESCRIPTIONS: dict[str, str] = {
    "20-knowledge": "Mémoire sémantique — connaissances stables (concepts, savoirs métier, références).",
    "40-principles": "Heuristiques et lignes rouges — règles d'action stables d'un projet ou transverses.",
    "50-goals": "Intentions prospectives — objectifs déclarés, à valider ou échus.",
    "60-people": "Carnet relationnel — collègues, clients, contacts.",
}


def scan_zone_atoms(vault: Path, zone: str) -> list[tuple[Path, dict[str, Any]]]:
    """Return ``[(atom_path, frontmatter)]`` for every atom in ``{vault}/{zone}/``.

    Excludes ``index.md`` (the zone hub itself), files under hidden directories,
    and files whose UTF-8 read fails. Recursive — captures atoms in subfolders
    (e.g. ``40-principles/work/security/foo.md``).
    """
    base = vault / zone
    if not base.is_dir():
        return []
    out: list[tuple[Path, dict[str, Any]]] = []
    for f in sorted(base.rglob("*.md")):
        if f.name == "index.md":
            continue
        if any(p.startswith(".") for p in f.parts):
            continue
        try:
            fm, _body = frontmatter.read(f)
        except (UnicodeDecodeError, OSError, ValueError):
            continue
        out.append((f, fm))
    return out


def group_atoms_by_project(
    atoms: list[tuple[Path, dict[str, Any]]],
) -> dict[str | None, list[Path]]:
    """Group atoms by their ``project`` (or ``domain``) frontmatter field.

    Atoms without ``project`` or ``domain`` are grouped under the ``None`` key
    (rendered as the "Unattached" section).
    """
    grouped: dict[str | None, list[Path]] = defaultdict(list)
    for path, fm in atoms:
        attachment = fm.get("project") or fm.get("domain") or None
        grouped[attachment].append(path)
    return grouped


def _render_atom_link(atom_path: Path, vault: Path) -> str:
    """Render one ``- [stem](relative-path)`` line. Stem is the filename
    without ``.md`` — Obsidian-friendly when the wikilink is enabled."""
    rel = atom_path.relative_to(vault).as_posix()
    return f"- [{atom_path.stem}]({rel})"


def render_zone_index_body(
    vault: Path,
    zone: str,
    atoms_by_project: dict[str | None, list[Path]],
) -> str:
    """Render the Markdown body of ``{zone}/index.md`` — sections grouped by
    project/domain, then unattached, alphabetic ordering inside each section.
    """
    display = ZONE_DISPLAY_NAMES.get(zone, zone)
    description = ZONE_DESCRIPTIONS.get(zone, "")

    lines: list[str] = [
        f"# {zone} — Index",
        "",
    ]
    if description:
        lines.append(f"_{description}_")
        lines.append("")
    lines.append("> Back to [[index|vault index]].")
    lines.append("")
    lines.append(f"## {display} by project")
    lines.append("")

    # Render attached atoms first (sorted by project slug), then unattached.
    attached = sorted((k, v) for k, v in atoms_by_project.items() if k)
    unattached = atoms_by_project.get(None, [])

    if not attached and not unattached:
        lines.append("_(none yet — atoms ingested via mem_note / mem_principle / "
                     "mem_goal / mem_person will appear here automatically)_")
        lines.append("")
    else:
        for project, paths in attached:
            lines.append(f"### {project}")
            lines.append("")
            for path in sorted(paths, key=lambda p: p.stem):
                lines.append(_render_atom_link(path, vault))
            lines.append("")

        if unattached:
            lines.append("### Unattached")
            lines.append("")
            for path in sorted(unattached, key=lambda p: p.stem):
                lines.append(_render_atom_link(path, vault))
            lines.append("")

    return "\n".join(lines)


def regenerate_zone_index(vault: Path, zone: str) -> Path:
    """Re-scan ``{zone}/`` and rewrite ``{zone}/index.md`` from scratch.

    Idempotent — calling twice in a row produces the same file. Atomic write
    (UTF-8 / LF / no BOM) via ``vault.atomic_io.write_atomic``.

    Returns the path of the regenerated index.
    """
    if zone not in ATOM_ZONES:
        raise ValueError(
            f"zone {zone!r} is not a transverse-atom zone. "
            f"Expected one of: {list(ATOM_ZONES)}"
        )

    atoms = scan_zone_atoms(vault, zone)
    grouped = group_atoms_by_project(atoms)
    body = render_zone_index_body(vault, zone, grouped)

    # Build the frontmatter — kept consistent with the existing zone hub schema.
    target = vault / zone / "index.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    fm: dict[str, Any] = {
        "zone": "meta",
        "type": "zone-index",
        "display": f"{zone} — index",
        "tags": ["zone/meta", "type/zone-index", f"target-zone/{zone}"],
    }
    # Atomic write of the full file (frontmatter + body)
    fm_lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}: [{', '.join(v)}]")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")
    full = "\n".join(fm_lines) + "\n\n" + body
    write_atomic(target, full)
    return target


def update_zone_index_for_atom(vault: Path, atom_path: Path) -> Path | None:
    """Convenience wrapper called after ingesting a single atom.

    Detects the zone from ``atom_path`` (must be under one of the transverse
    zones), then regenerates that zone's ``index.md``. Returns the index path
    on success, or ``None`` if the atom is not in a transverse-atom zone (e.g.
    ``00-inbox`` for ``mem_doc`` — those don't get auto-indexed at zone level).

    Resilient: never raises if the atom_path is outside the vault or in a
    non-transverse zone — just returns None. Callers can ignore the return
    value if they don't need to track which index was rewritten.
    """
    try:
        rel = atom_path.relative_to(vault)
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    zone = parts[0]
    if zone not in ATOM_ZONES:
        return None
    return regenerate_zone_index(vault, zone)


def regenerate_all_zone_indexes(vault: Path) -> list[Path]:
    """Regenerate every transverse-atom zone index. Returns the list of paths
    rewritten. Used by the migration tool and by ``rebuild-vault-index.py``.
    """
    written: list[Path] = []
    for zone in ATOM_ZONES:
        if (vault / zone).is_dir():
            written.append(regenerate_zone_index(vault, zone))
    return written
