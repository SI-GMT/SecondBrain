"""mem_historize — Move a finished project to the archived zone (or revive it).

Spec: core/procedures/mem-historize.md
Scripted reference: scripts/mem-historize.py (in the kit repo)

Idempotent on three axes:
- Already archived (no-op with explanatory message).
- Already active (no-op when archive is requested but already in projects/).
- Revive on a non-archived project (no-op).

Refuses to archive a project without context.md.
"""

from __future__ import annotations

import shutil
from datetime import datetime

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter, paths


def register(mcp: FastMCP) -> None:
    """Register mem_historize with the FastMCP instance."""

    @mcp.tool()
    def mem_historize(
        slug: str = Field(..., description="Project slug to archive (or revive)."),
        revive: bool = Field(
            False,
            description="If True, move the project back from archived/ to projects/.",
        ),
    ) -> ChangeReport:
        """Move a finished project to 10-episodes/archived/{slug}/ (or back).

        Patches context.md frontmatter:
        - On archive: phase = 'archived', archived_at = today, display gets
          ' [archived]' suffix.
        - On revive: removes phase 'archived' and archived_at, strips ' [archived]'
          from display.

        Folder move is atomic (shutil.move). Refuses to archive a project
        without context.md (per the spec).
        """
        config = get_config()
        vault = config.vault

        active_dir = paths.project_dir(vault, slug)
        archived_dir_path = paths.archived_dir(vault, slug)

        if revive:
            # Move from archived/ → projects/
            if not archived_dir_path.exists():
                if active_dir.exists():
                    return ChangeReport(
                        skill="mem_historize",
                        success=True,
                        warnings=[f"Project '{slug}' is already active — nothing to revive."],
                        summary_md=f"**mem_historize (revive)** — `{slug}` already active. No-op.\n",
                    )
                raise FileNotFoundError(
                    f"No project '{slug}' in projects/ or archived/."
                )
            if active_dir.exists():
                raise FileExistsError(
                    f"Conflict: '{slug}' exists in BOTH projects/ and archived/. "
                    "Resolve manually before reviving."
                )
            ctx = archived_dir_path / "context.md"
            if ctx.exists():
                fm, body = frontmatter.read(ctx)
                fm.pop("archived_at", None)
                if fm.get("phase") == "archived":
                    fm.pop("phase", None)
                if isinstance(fm.get("display"), str):
                    fm["display"] = fm["display"].replace(" [archived]", "").rstrip()
                frontmatter.write(ctx, fm, body)
            shutil.move(str(archived_dir_path), str(active_dir))
            return ChangeReport(
                skill="mem_historize",
                success=True,
                files_moved=[(str(archived_dir_path), str(active_dir))],
                summary_md=f"**mem_historize (revive)** — `{slug}` moved back to projects/.\n",
            )

        # Archive flow
        if archived_dir_path.exists():
            return ChangeReport(
                skill="mem_historize",
                success=True,
                warnings=[f"Project '{slug}' is already archived — nothing to do."],
                summary_md=f"**mem_historize** — `{slug}` already archived. No-op.\n",
            )
        if not active_dir.exists():
            raise FileNotFoundError(f"No active project '{slug}' in projects/.")
        ctx = active_dir / "context.md"
        if not ctx.exists():
            raise ValueError(
                f"Project '{slug}' has no context.md — refusing to archive a "
                "project without a snapshot. Run mem_archive first."
            )

        date_iso = datetime.now().date().isoformat()
        fm, body = frontmatter.read(ctx)
        fm["phase"] = "archived"
        fm["archived_at"] = date_iso
        if isinstance(fm.get("display"), str):
            disp = fm["display"]
            if "[archived]" not in disp:
                fm["display"] = f"{disp} [archived]"
        else:
            fm["display"] = f"{slug} — context [archived]"
        frontmatter.write(ctx, fm, body)
        shutil.move(str(active_dir), str(archived_dir_path))

        return ChangeReport(
            skill="mem_historize",
            success=True,
            files_moved=[(str(active_dir), str(archived_dir_path))],
            files_modified=[str(archived_dir_path / "context.md")],
            summary_md=(
                f"**mem_historize** — `{slug}` archived (archived_at={date_iso}).\n"
                f"Moved to `{archived_dir_path.relative_to(vault)}`.\n"
            ),
        )
