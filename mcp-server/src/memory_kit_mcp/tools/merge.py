"""mem_merge — Merge source project/domain into target.

Spec: core/procedures/mem-merge.md

POC: re-tags every .md under the source folder to the target's slug, then
moves all archives from source/archives/ → target/archives/, and finally
deletes the source folder. context.md from the source is NOT auto-merged
into the target's context.md — the spec leaves manual reconciliation to the
user.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter, paths


def _retag_frontmatter(
    fm: dict[str, Any], src_slug: str, target_slug: str, kind: str
) -> bool:
    changed = False
    if fm.get("slug") == src_slug:
        fm["slug"] = target_slug
        changed = True
    key = "project" if kind == "project" else "domain"
    if fm.get(key) == src_slug:
        fm[key] = target_slug
        changed = True
    if isinstance(fm.get("tags"), list):
        new_tags = []
        tags_changed = False
        for tag in fm["tags"]:
            if isinstance(tag, str) and tag == f"{kind}/{src_slug}":
                new_tags.append(f"{kind}/{target_slug}")
                tags_changed = True
            else:
                new_tags.append(tag)
        if tags_changed:
            fm["tags"] = new_tags
            changed = True
    return changed


def register(mcp: FastMCP) -> None:
    """Register mem_merge with the FastMCP instance."""

    @mcp.tool()
    def mem_merge(
        source_slug: str = Field(..., description="Source project/domain slug (will be removed)."),
        target_slug: str = Field(..., description="Target project/domain slug (kept and enriched)."),
    ) -> ChangeReport:
        """Merge a source project/domain into a target.

        Re-tags all archives from the source to the target, moves them under
        target/archives/, and deletes the source folder.

        Limitations (per spec):
        - Source `context.md` is NOT merged. Reconcile manually if you want to
          carry decisions forward.
        - Source and target must be the same kind (both projects, or both
          domains).
        """
        if source_slug == target_slug:
            raise ValueError("Source and target slugs are identical.")

        config = get_config()
        vault = config.vault

        src_resolved = paths.resolve_slug(vault, source_slug)
        if src_resolved is None:
            raise FileNotFoundError(f"No project or domain '{source_slug}' in vault.")
        src_folder, src_kind, _ = src_resolved

        tgt_resolved = paths.resolve_slug(vault, target_slug)
        if tgt_resolved is None:
            raise FileNotFoundError(f"No project or domain '{target_slug}' in vault.")
        tgt_folder, tgt_kind, _ = tgt_resolved

        if src_kind != tgt_kind:
            raise ValueError(
                f"Cannot merge a {src_kind} into a {tgt_kind}. Both must match."
            )

        moved: list[tuple[str, str]] = []
        modified: list[str] = []
        warnings: list[str] = []

        # Re-tag archives in place under source first, then move them
        src_archives = src_folder / "archives"
        tgt_archives = tgt_folder / "archives"
        if src_archives.exists():
            tgt_archives.mkdir(parents=True, exist_ok=True)
            for archive in sorted(src_archives.glob("*.md")):
                try:
                    fm, body = frontmatter.read(archive)
                except (ValueError, OSError):
                    continue
                if _retag_frontmatter(fm, source_slug, target_slug, src_kind):
                    frontmatter.write(archive, fm, body)
                    modified.append(str(archive))
                # Move to target/archives/, avoid name collisions
                target_path = tgt_archives / archive.name
                if target_path.exists():
                    new_name = f"{archive.stem}-merged-from-{source_slug}{archive.suffix}"
                    target_path = tgt_archives / new_name
                    warnings.append(f"Filename collision — renamed {archive.name} → {new_name}")
                shutil.move(str(archive), str(target_path))
                moved.append((str(archive), str(target_path)))

        # Note: context.md and history.md from source are NOT carried over
        if (src_folder / "context.md").exists():
            warnings.append(
                f"Source `context.md` was NOT merged. Reconcile manually with "
                f"`{tgt_folder.relative_to(vault)}/context.md`."
            )

        # Delete source folder
        shutil.rmtree(src_folder)

        return ChangeReport(
            skill="mem_merge",
            success=True,
            files_moved=moved,
            files_modified=modified,
            files_deleted=[str(src_folder)],
            warnings=warnings,
            summary_md=(
                f"**mem_merge** — `{source_slug}` → `{target_slug}` ({src_kind})\n\n"
                f"- Re-tagged & moved {len(moved)} archive(s) to "
                f"`{tgt_folder.relative_to(vault)}/archives/`\n"
                f"- Deleted source folder `{src_folder.relative_to(vault)}`\n"
                f"- ⚠ {len(warnings)} warning(s) — see report.\n"
            ),
        )
