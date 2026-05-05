"""mem_init_project — Initialise an empty project or domain folder in the vault.

Spec: ``core/procedures/mem-init-project.md``.

Closes the UX gap where ``mem_archive`` refuses to write to a non-existent
slug (defensive behaviour to avoid typo-driven silent project creation),
forcing the LLM to handcraft ``context.md`` + ``history.md`` via filesystem
operations. After this call, ``mem_archive`` can be invoked normally on the
new slug.

The tool refuses to overwrite an existing project/domain (raises
``FileExistsError``) — opt-in creation only. It does NOT touch ``index.md``;
that is left to ``mem_archive`` (which appends the project naturally on the
first archive) or to ``scripts/rebuild-vault-index.py``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter, paths


def execute_init_project(
    vault: Path,
    slug: str,
    kind: Literal["project", "domain"] = "project",
    scope: Literal["work", "personal"] = "work",
    display: str | None = None,
    repo_path: str | None = None,
) -> ChangeReport:
    """Module-level entry — usable by orchestrators without going through MCP."""
    if not slug:
        raise ValueError("slug is required and must be non-empty")
    if "/" in slug or "\\" in slug or ".." in slug:
        raise ValueError(f"slug {slug!r} contains invalid characters (path separators)")

    # Refuse if the slug exists anywhere (active project, domain, or archived).
    if paths.resolve_slug(vault, slug) is not None:
        raise FileExistsError(
            f"A project or domain named {slug!r} already exists in {vault}. "
            "Pick a different slug, or use mem_archive on the existing one."
        )

    if kind == "project":
        folder = paths.project_dir(vault, slug)
    elif kind == "domain":
        folder = paths.domain_dir(vault, slug)
    else:
        raise ValueError(f"kind must be 'project' or 'domain', got {kind!r}")

    folder.mkdir(parents=True, exist_ok=False)
    archives_dir = folder / "archives"
    archives_dir.mkdir(parents=True, exist_ok=True)
    # Keep the empty archives/ folder under git for new projects.
    (archives_dir / ".gitkeep").write_text("", encoding="utf-8")

    display_resolved = display or slug.replace("-", " ").capitalize()
    today = datetime.now().date().isoformat()

    # context.md — minimal but conformant to the universal frontmatter convention.
    ctx_fm: dict[str, object] = {
        "project" if kind == "project" else "domain": slug,
        "tags": [f"{kind}/{slug}", "zone/episodes", f"kind/{kind}", f"scope/{scope}"],
        "zone": "episodes",
        "kind": kind,
        "slug": slug,
        "scope": scope,
        "collective": False,
        "phase": "initial",
        "last-session": today,
        "display": f"{display_resolved} — context",
    }
    if repo_path:
        ctx_fm["repo_path"] = repo_path
        ctx_fm["workspace_member"] = ""

    ctx_body = (
        "> Snapshot mutable du projet. "
        "Voir aussi : [historique](history.md) · [archives/](archives/)\n\n"
        f"# {display_resolved} — Active context\n\n"
        "## Current state\n"
        "- Phase : initial\n"
        "- Validated : (none yet)\n"
        "- In progress : (none yet)\n\n"
        "## Cumulative decisions\n"
        "_(none yet — will accumulate as the project evolves)_\n\n"
        "## Next steps\n"
        "_(none yet)_\n\n"
        "## Active assets (URLs)\n"
        "_(none yet)_\n"
    )
    ctx_path = folder / "context.md"
    frontmatter.write(ctx_path, ctx_fm, ctx_body)

    # history.md — minimal; mem_archive will prepend entries on each session.
    hist_fm: dict[str, object] = {
        "project" if kind == "project" else "domain": slug,
        "tags": [f"{kind}/{slug}", "zone/episodes", f"kind/{kind}"],
        "zone": "episodes",
        "kind": kind,
        "slug": slug,
        "display": f"{display_resolved} — history",
    }
    hist_body = (
        "> Fil chronologique des sessions du projet. "
        "Voir aussi : [contexte](context.md)\n\n"
        f"# {display_resolved} — Historique des sessions\n\n"
        "_(no sessions yet — mem_archive will prepend new entries here)_\n"
    )
    hist_path = folder / "history.md"
    frontmatter.write(hist_path, hist_fm, hist_body)

    rel_ctx = ctx_path.relative_to(vault).as_posix()
    rel_hist = hist_path.relative_to(vault).as_posix()
    rel_archives = (archives_dir / ".gitkeep").relative_to(vault).as_posix()

    return ChangeReport(
        skill="mem_init_project",
        success=True,
        files_created=[rel_ctx, rel_hist, rel_archives],
        summary_md=(
            f"**mem_init_project** — created {kind} `{slug}` "
            f"({scope}, display = {display_resolved!r})\n\n"
            f"- {rel_ctx}\n"
            f"- {rel_hist}\n"
            f"- {rel_archives}\n\n"
            f"Run `mem_archive` on `{slug}` to start tracking sessions."
        ),
    )


def register(mcp: FastMCP) -> None:
    """Register mem_init_project with the FastMCP instance."""

    @mcp.tool()
    def mem_init_project(
        slug: str = Field(..., description="New project or domain slug (kebab-case recommended)."),
        kind: Literal["project", "domain"] = Field(
            "project",
            description="'project' for active projects, 'domain' for cross-project transverse atoms.",
        ),
        scope: Literal["work", "personal"] = Field(
            "work",
            description="Scope tag: 'work' or 'personal'.",
        ),
        display: str | None = Field(
            None,
            description="Display name (defaults to capitalized slug).",
        ),
        repo_path: str | None = Field(
            None,
            description="Optional absolute path to the associated Git repo (sets repo_path in context.md frontmatter).",
        ),
    ) -> ChangeReport:
        """Create an empty project or domain folder in the vault.

        Initialises ``10-episodes/{kind}s/{slug}/`` with minimal ``context.md``
        and ``history.md`` skeletons (universal frontmatter, intro lines), plus
        an empty ``archives/`` folder. Refuses if the slug already exists
        anywhere (active, archived, or domain) — pick a different slug.

        After this call, ``mem_archive`` can write to the new slug normally.
        """
        config = get_config()
        return execute_init_project(
            vault=config.vault,
            slug=slug,
            kind=kind,
            scope=scope,
            display=display,
            repo_path=repo_path,
        )
