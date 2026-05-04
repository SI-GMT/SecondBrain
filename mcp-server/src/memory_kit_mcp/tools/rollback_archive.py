"""mem_rollback_archive — Delete the most recent archive of a project.

Spec: core/procedures/mem-rollback-archive.md

Removes the latest .md file from {project}/archives/ and strips its line from
history.md. Does NOT auto-restore context.md (per the spec — the user is
expected to handle context recovery manually if needed).
"""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter, paths


def register(mcp: FastMCP) -> None:
    """Register mem_rollback_archive with the FastMCP instance."""

    @mcp.tool()
    def mem_rollback_archive(
        slug: str = Field(..., description="Project or domain slug to roll back."),
    ) -> ChangeReport:
        """Cancel the most recent archive of a project or domain.

        Deletes the latest .md from {project}/archives/ and removes its
        reference line from history.md. context.md is NOT restored — the
        spec leaves recovery to the user.

        Refuses if no archives exist.
        """
        config = get_config()
        vault = config.vault

        resolved = paths.resolve_slug(vault, slug)
        if resolved is None:
            raise FileNotFoundError(f"No project or domain '{slug}' in vault {vault}.")
        folder, _kind, _archived = resolved

        archives_dir = folder / "archives"
        if not archives_dir.exists():
            raise FileNotFoundError(f"No archives/ folder for '{slug}'.")
        archives = sorted(archives_dir.glob("*.md"))
        if not archives:
            raise FileNotFoundError(f"No archive to roll back for '{slug}'.")

        latest = archives[-1]
        latest_name = latest.name
        latest.unlink()

        # Strip the matching line from history.md (best-effort substring match
        # on the archive filename inside parentheses).
        history_file = folder / "history.md"
        modified_history = False
        if history_file.exists():
            fm, body = frontmatter.read(history_file)
            new_lines = [
                line for line in body.splitlines() if latest_name not in line
            ]
            if len(new_lines) != len(body.splitlines()):
                # Collapse runs of consecutive blank lines so removal is clean
                cleaned: list[str] = []
                prev_blank = False
                for line in new_lines:
                    is_blank = not line.strip()
                    if is_blank and prev_blank:
                        continue
                    cleaned.append(line)
                    prev_blank = is_blank
                frontmatter.write(history_file, fm, "\n".join(cleaned).rstrip() + "\n")
                modified_history = True

        return ChangeReport(
            skill="mem_rollback_archive",
            success=True,
            files_deleted=[str(latest)],
            files_modified=[str(history_file)] if modified_history else [],
            summary_md=(
                f"**mem_rollback_archive** — `{slug}`\n\n"
                f"- Deleted `archives/{latest_name}`\n"
                f"- {'Updated' if modified_history else 'No change to'} `history.md`\n"
                "- `context.md` was NOT restored (per spec). Recover manually if needed.\n"
            ),
        )
