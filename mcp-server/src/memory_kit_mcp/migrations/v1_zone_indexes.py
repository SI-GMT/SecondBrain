"""v1 migration — move transverse-atom listings from root index.md to {zone}/index.md.

Pre-migration shape (v0.9.3 and earlier):
- ``index.md`` (root) carries ``## Principles``, ``## Knowledge``, ``## Goals``,
  ``## People`` sections grouped by project.
- ``{zone}/index.md`` is a stub (back-link only) for those zones.

Post-migration shape (v0.9.4+):
- ``index.md`` (root) keeps Zones / Projects / Domains / Archives / Health.
  The transverse sections are replaced by a single ``## Transverse atoms``
  pointer linking to each ``{zone}/index.md``.
- ``{zone}/index.md`` for the four transverse zones carries the per-atom
  listing grouped by project.

Idempotent: if the root already has the ``Transverse atoms`` pointer (or no
transverse sections at all), the migration is a no-op for the root part.
The zone indexes are always regenerated from a fresh scan — also idempotent.
"""

from __future__ import annotations

import re
from pathlib import Path

from memory_kit_mcp.migrations import MigrationStepReport
from memory_kit_mcp.vault import frontmatter
from memory_kit_mcp.vault.atomic_io import write_atomic
from memory_kit_mcp.vault.zone_index import ATOM_ZONES, regenerate_all_zone_indexes

_TRANSVERSE_SECTION_HEADINGS = (
    "## Principles", "## Principes",
    "## Knowledge", "## Connaissances",
    "## Goals", "## Objectifs",
    "## People", "## Personnes",
)


def is_needed(vault: Path) -> bool:
    """True if any transverse zone index is empty/stub OR if the root index
    still carries the old per-zone sections."""
    # Sub-condition 1: any zone index is missing or doesn't list its atoms.
    for zone in ATOM_ZONES:
        idx = vault / zone / "index.md"
        if not idx.is_file():
            # Will be created by the migration if there are atoms in the zone.
            zone_dir = vault / zone
            if zone_dir.is_dir():
                # If there are .md files (other than index.md) in the zone,
                # we need to materialise the listing.
                for f in zone_dir.rglob("*.md"):
                    if f.name != "index.md":
                        return True
        else:
            try:
                text = idx.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            # Heuristic: zone index without "## " in body (besides the H1)
            # = stub form. If the zone has atoms, listing is needed.
            zone_dir = vault / zone
            atom_count = sum(
                1 for f in zone_dir.rglob("*.md") if f.name != "index.md"
            )
            section_count = text.count("\n## ")
            if atom_count > 0 and section_count == 0:
                return True

    # Sub-condition 2: root index still has old transverse sections.
    root = vault / "index.md"
    if root.is_file():
        try:
            text = root.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        for heading in _TRANSVERSE_SECTION_HEADINGS:
            if heading in text:
                return True
    return False


def _strip_transverse_sections_from_root(text: str) -> tuple[str, bool]:
    """Remove old Principles / Knowledge / Goals / People sections from the
    root index. Inserts a new ``## Transverse atoms`` pointer if not already
    present.

    Returns (new_text, modified) where modified is True if any change was made.
    """
    original = text
    # Build a regex that matches each transverse heading + everything until
    # the next ``\n## `` heading (or end-of-file).
    section_pattern = re.compile(
        r"\n## (?:Principles|Principes|Knowledge|Connaissances|"
        r"Goals|Objectifs|People|Personnes)\b[^\n]*\n.*?(?=\n## |\Z)",
        re.DOTALL,
    )
    text = section_pattern.sub("\n", text)

    # Insert a "Transverse atoms" pointer just before "## Health" if present,
    # else at the end. Skip if a similar pointer already exists.
    if "## Transverse atoms" not in text and "## Atomes transverses" not in text:
        pointer_block = (
            "\n## Transverse atoms\n\n"
            + "\n".join(
                f"- [{z}/index.md]({z}/index.md)" for z in ATOM_ZONES
                if (z and True)  # static — every zone listed; user trims later if needed
            )
            + "\n"
        )
        if "\n## Health" in text:
            text = text.replace("\n## Health", pointer_block + "\n## Health", 1)
        else:
            # Append at the end (before any trailing whitespace).
            text = text.rstrip() + "\n" + pointer_block

    # Collapse any triple-newlines created by the substitution.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, text != original


def apply(vault: Path, dry_run: bool = True) -> MigrationStepReport:
    """Apply v1 migration. Idempotent."""
    files_modified: list[str] = []
    files_created: list[str] = []

    # Step 1: regenerate every transverse zone index from scan.
    if dry_run:
        for zone in ATOM_ZONES:
            zone_dir = vault / zone
            if not zone_dir.is_dir():
                continue
            target = zone_dir / "index.md"
            if target.is_file():
                files_modified.append(str(target.relative_to(vault).as_posix()))
            else:
                files_created.append(str(target.relative_to(vault).as_posix()))
    else:
        regenerated = regenerate_all_zone_indexes(vault)
        for p in regenerated:
            rel = p.relative_to(vault).as_posix()
            # We can't easily distinguish "newly created" vs "rewritten" without
            # checking pre-state, so report all as modified — it's accurate
            # enough for a migration report.
            files_modified.append(rel)

    # Step 2: strip old transverse sections from root index, insert pointer.
    root = vault / "index.md"
    if root.is_file():
        try:
            text = root.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = None
        if text is not None:
            new_text, changed = _strip_transverse_sections_from_root(text)
            if changed:
                if not dry_run:
                    fm, _body_old = frontmatter.read(root)
                    # Recover frontmatter + already-stripped body to write.
                    # We rebuild the file: original frontmatter + new body.
                    if new_text.startswith("---"):
                        # The file starts with frontmatter delimiters — we
                        # already have the full text including them.
                        write_atomic(root, new_text)
                    else:
                        # Defensive: should not happen on a well-formed root.
                        write_atomic(root, new_text)
                files_modified.append("index.md")

    summary_lines = []
    if files_modified or files_created:
        summary_lines.append(f"v1 zone-indexes migration — vault {vault}")
        if files_modified:
            summary_lines.append(f"  {len(files_modified)} file(s) rewritten:")
            for p in files_modified[:10]:
                summary_lines.append(f"    - {p}")
            if len(files_modified) > 10:
                summary_lines.append(f"    ... and {len(files_modified) - 10} more")
        if files_created:
            summary_lines.append(f"  {len(files_created)} file(s) created:")
            for p in files_created:
                summary_lines.append(f"    - {p}")
    else:
        summary_lines.append(
            "v1 zone-indexes migration — no changes needed (already migrated)."
        )

    return MigrationStepReport(
        target_version=1,
        module="v1_zone_indexes",
        needed=True,
        applied=(not dry_run) and bool(files_modified or files_created),
        dry_run=dry_run,
        files_modified=files_modified,
        files_created=files_created,
        summary="\n".join(summary_lines),
    )
