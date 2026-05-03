"""mem_rename — Rename a project or domain across the vault.

Spec: core/procedures/mem-rename.md

POC: renames the folder + patches `slug`, `project`/`domain`, and tags inside
every Markdown file under the renamed folder. Wikilinks elsewhere in the vault
that reference the old slug are NOT rewritten — surfaced as a warning.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter, paths


def _patch_frontmatter(fm: dict[str, Any], old_slug: str, new_slug: str, kind: str) -> bool:
    """Rewrite slug/project/domain/tags fields in-place. Returns True if changed."""
    changed = False
    if fm.get("slug") == old_slug:
        fm["slug"] = new_slug
        changed = True
    key = "project" if kind == "project" else "domain"
    if fm.get(key) == old_slug:
        fm[key] = new_slug
        changed = True
    if isinstance(fm.get("tags"), list):
        new_tags = []
        tags_changed = False
        for tag in fm["tags"]:
            if isinstance(tag, str) and tag == f"{kind}/{old_slug}":
                new_tags.append(f"{kind}/{new_slug}")
                tags_changed = True
            else:
                new_tags.append(tag)
        if tags_changed:
            fm["tags"] = new_tags
            changed = True
    if isinstance(fm.get("display"), str):
        if old_slug in fm["display"]:
            fm["display"] = fm["display"].replace(old_slug, new_slug, 1)
            changed = True
    return changed


def register(mcp: FastMCP) -> None:
    """Register mem_rename with the FastMCP instance."""

    @mcp.tool()
    def mem_rename(
        old_slug: str = Field(..., description="Current slug of the project/domain."),
        new_slug: str = Field(..., description="New slug (filesystem-safe lowercase + hyphens)."),
    ) -> ChangeReport:
        """Rename a project or domain everywhere it appears in its own folder.

        Effects:
        - Renames the folder.
        - Patches frontmatter (slug, project|domain, tags, display) in every
          .md file under the folder.

        Limitation: wikilinks elsewhere in the vault pointing to the old slug
        are NOT rewritten. Warning emitted in the report.
        """
        if old_slug == new_slug:
            raise ValueError("old_slug and new_slug are identical.")

        config = get_config()
        vault = config.vault

        resolved = paths.resolve_slug(vault, old_slug)
        if resolved is None:
            raise FileNotFoundError(f"No project or domain '{old_slug}' in vault {vault}.")
        src_folder, kind, archived = resolved

        # Resolve target folder location
        if kind == "project" and not archived:
            dst_folder = paths.project_dir(vault, new_slug)
        elif kind == "project" and archived:
            dst_folder = paths.archived_dir(vault, new_slug)
        else:  # domain
            dst_folder = paths.domain_dir(vault, new_slug)

        if dst_folder.exists():
            raise FileExistsError(f"Target {dst_folder} already exists. Aborting.")

        # Patch frontmatters in place first (still under the old folder), then move
        modified: list[str] = []
        for md in src_folder.rglob("*.md"):
            try:
                fm, body = frontmatter.read(md)
            except (ValueError, OSError):
                continue
            if _patch_frontmatter(fm, old_slug, new_slug, kind):
                frontmatter.write(md, fm, body)
                modified.append(str(md))

        import shutil

        shutil.move(str(src_folder), str(dst_folder))

        return ChangeReport(
            skill="mem_rename",
            success=True,
            files_moved=[(str(src_folder), str(dst_folder))],
            files_modified=[
                p.replace(str(src_folder), str(dst_folder)) for p in modified
            ],
            warnings=[
                "Wikilinks elsewhere in the vault that reference "
                f"[[...{old_slug}...]] were NOT rewritten."
            ],
            summary_md=(
                f"**mem_rename** — `{old_slug}` → `{new_slug}` ({kind})\n\n"
                f"- Renamed folder to `{dst_folder.relative_to(vault)}`\n"
                f"- Patched frontmatter in {len(modified)} file(s)\n"
                f"- ⚠ Wikilinks outside the folder NOT updated.\n"
            ),
        )
