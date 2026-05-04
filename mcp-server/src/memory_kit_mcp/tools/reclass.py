"""mem_reclass — Change scope or zone of an existing vault item.

Spec: core/procedures/mem-reclass.md

POC: patches the file's frontmatter (scope and/or zone), and moves the file
across zones if zone changes. Subdirectory layout (e.g. 40-principles/work/
security/) is preserved when scope changes within the same zone — the
{scope} segment is rewritten in the path.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter

_VALID_SCOPES = {"work", "personal", "all"}


def _swap_scope_in_path(rel_path: Path, old_scope: str | None, new_scope: str) -> Path:
    """Replace the scope segment in a vault-relative path.

    Convention: zones store atoms under {zone}/{scope}/... (e.g.
    40-principles/work/security/foo.md). If the file isn't laid out that way,
    the path is returned unchanged.
    """
    parts = list(rel_path.parts)
    if len(parts) < 3:
        return rel_path
    if old_scope and parts[1] == old_scope:
        parts[1] = new_scope
        return Path(*parts)
    return rel_path


def register(mcp: FastMCP) -> None:
    """Register mem_reclass with the FastMCP instance."""

    @mcp.tool()
    def mem_reclass(
        path: str = Field(..., description="Vault-relative path to the file to reclassify."),
        scope: str | None = Field(
            None,
            description="New scope: 'work', 'personal', or 'all'. None = keep current.",
        ),
        zone: str | None = Field(
            None,
            description=(
                "New top-level zone (e.g. '20-knowledge', '40-principles'). None = keep "
                "current. Moves the file across zones; the rest of the relative path is "
                "preserved."
            ),
        ),
    ) -> ChangeReport:
        """Change the scope and/or zone of a single vault file.

        - scope rewrite: patches frontmatter `scope:` and (if the file lives at
          {zone}/{scope}/...) renames the directory segment.
        - zone rewrite: patches frontmatter `zone:` and moves the file under
          the new top-level zone, preserving the rest of the path.

        At least one of scope/zone must be given.
        """
        if scope is None and zone is None:
            raise ValueError("Either scope or zone (or both) must be specified.")
        if scope is not None and scope not in _VALID_SCOPES:
            raise ValueError(f"scope must be one of {sorted(_VALID_SCOPES)}, got {scope!r}.")

        config = get_config()
        vault = config.vault
        rel = Path(path)
        src = vault / rel
        if not src.exists():
            raise FileNotFoundError(f"File not found: {src}")

        fm, body = frontmatter.read(src)
        old_scope = str(fm.get("scope")) if fm.get("scope") is not None else None
        old_zone = str(fm.get("zone")) if fm.get("zone") is not None else None

        new_rel = rel
        if scope is not None:
            fm["scope"] = scope
            new_rel = _swap_scope_in_path(new_rel, old_scope, scope)
        if zone is not None:
            fm["zone"] = zone
            # Replace the top-level zone segment
            parts = list(new_rel.parts)
            if parts:
                parts[0] = zone
                new_rel = Path(*parts)

        dst = vault / new_rel

        warnings: list[str] = []
        moved: list[tuple[str, str]] = []
        modified: list[str] = []

        if dst != src:
            # Atomic move via rename (same filesystem assumed within a vault)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                raise FileExistsError(f"Target {dst} already exists. Aborting.")
            # Write the patched frontmatter to the new location, then remove old
            frontmatter.write(dst, fm, body)
            src.unlink()
            moved.append((str(src), str(dst)))
            warnings.append(
                f"File moved from {old_zone or '?'} to {zone or old_zone}. "
                "Wikilinks pointing to the old path are NOT updated automatically."
            )
        else:
            frontmatter.write(src, fm, body)
            modified.append(str(src))

        return ChangeReport(
            skill="mem_reclass",
            success=True,
            files_modified=modified,
            files_moved=moved,
            warnings=warnings,
            summary_md=(
                f"**mem_reclass** — `{rel}`\n\n"
                f"- scope: {old_scope!r} → {scope!r}\n"
                f"- zone:  {old_zone!r} → {zone!r}\n"
                f"- new path: `{new_rel}`\n"
            ),
        )
