"""mem_archive — Archive the current work session into the vault.

Spec: core/procedures/mem-archive.md
Two modes:
- "incremental" (mid-session): rewrite context.md only, no new archive file.
- "full" (end-of-session): create a new dated archive + update history.md +
  rewrite context.md.

Per _archived.md doctrine: refuses to write to a project under
10-episodes/archived/. The user must /mem-historize --revive first.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter, paths

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify_subject(subject: str) -> str:
    """Normalize a subject string to a filesystem-safe slug."""
    s = subject.lower().strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = _SLUG_RE.sub("", s)
    return s.strip("-") or "session"


def _resolve_active(vault: Path, slug: str) -> tuple[Path, str]:
    """Resolve a slug to an *active* project or domain folder.

    Refuses archived projects per the _archived.md doctrine — for those, the
    LLM must call mem_historize with --revive first.
    """
    resolved = paths.resolve_slug(vault, slug)
    if resolved is None:
        raise FileNotFoundError(
            f"No project or domain '{slug}' in vault {vault}. "
            f"Available: {paths.list_projects(vault) + paths.list_domains(vault)}"
        )
    folder, kind, archived = resolved
    if archived:
        raise PermissionError(
            f"Project '{slug}' is archived. To resume active writes, run "
            f"mem_historize with revive=True first (see _archived.md doctrine)."
        )
    return folder, kind


def _do_incremental(
    vault: Path,
    slug: str,
    context_md: str,
    phase: str | None,
) -> ChangeReport:
    """Mid-session update — rewrite context.md only."""
    folder, kind = _resolve_active(vault, slug)
    ctx = folder / "context.md"

    fm: dict[str, Any] = {}
    if ctx.exists():
        fm, _ = frontmatter.read(ctx)
    if not fm:
        # Bootstrap minimal frontmatter for new contexts
        fm = {
            "project" if kind == "project" else "domain": slug,
            "tags": [f"{kind}/{slug}", "zone/episodes", f"kind/{kind}"],
            "zone": "episodes",
            "kind": kind,
            "slug": slug,
            "display": f"{slug} — context",
        }

    fm["last-session"] = datetime.now().date().isoformat()
    if phase is not None:
        fm["phase"] = phase

    frontmatter.write(ctx, fm, context_md)
    return ChangeReport(
        skill="mem_archive",
        success=True,
        files_modified=[str(ctx)],
        summary_md=(
            f"**mem_archive (incremental)** — `{slug}` ({kind})\n\n"
            f"- Updated `context.md` (last-session = {fm['last-session']}"
            f"{f', phase = {phase}' if phase is not None else ''})\n"
        ),
    )


def _do_full(
    vault: Path,
    slug: str,
    archive_subject: str,
    archive_body_md: str,
    new_context_md: str,
    phase: str | None,
) -> ChangeReport:
    """End-of-session — create a new archive + update history.md + reset context.md."""
    folder, kind = _resolve_active(vault, slug)

    now = datetime.now()
    date_iso = now.date().isoformat()
    timestamp = now.strftime("%Y-%m-%d-%Hh%M")
    subject_slug = _slugify_subject(archive_subject)
    archive_filename = f"{timestamp}-{slug}-{subject_slug}.md"

    archives_dir = folder / "archives"
    archives_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archives_dir / archive_filename

    archive_fm = {
        "project" if kind == "project" else "domain": slug,
        "tags": [f"{kind}/{slug}", "zone/episodes", "kind/archive"],
        "zone": "episodes",
        "kind": "archive",
        "slug": slug,
        "date": date_iso,
        "display": f"{slug} — {timestamp.replace('-', ' ', 1)} {archive_subject}",
    }
    frontmatter.write(archive_path, archive_fm, archive_body_md)

    # Update history.md — prepend the new archive line
    history_path = folder / "history.md"
    if history_path.exists():
        h_fm, h_body = frontmatter.read(history_path)
    else:
        h_fm = {
            "project" if kind == "project" else "domain": slug,
            "tags": [f"{kind}/{slug}", "zone/episodes", f"kind/{kind}"],
            "zone": "episodes",
            "kind": kind,
            "slug": slug,
            "display": f"{slug} — history",
        }
        h_body = (
            f"> Fil chronologique des sessions du projet. "
            f"Voir aussi : [contexte](context.md)\n\n# {slug} — Historique\n"
        )

    new_line = (
        f"- [{date_iso} {now.strftime('%Hh%M')} — {archive_subject}]"
        f"(archives/{archive_filename})"
    )
    # Insert after the "# {slug} — Historique" header if present, else at the end
    if "# " in h_body:
        # Insert after the first H1 line + blank line
        lines = h_body.splitlines()
        out: list[str] = []
        inserted = False
        for line in lines:
            out.append(line)
            if not inserted and line.startswith("# "):
                # peek ahead: if next non-blank line is a list item, prepend; else add a blank
                out.append("")
                out.append(new_line)
                inserted = True
        h_body = "\n".join(out) + "\n" if out else new_line + "\n"
    else:
        h_body = h_body.rstrip() + "\n\n" + new_line + "\n"

    frontmatter.write(history_path, h_fm, h_body)

    # Reset context.md
    ctx_path = folder / "context.md"
    if ctx_path.exists():
        ctx_fm, _ = frontmatter.read(ctx_path)
    else:
        ctx_fm = {
            "project" if kind == "project" else "domain": slug,
            "tags": [f"{kind}/{slug}", "zone/episodes", f"kind/{kind}", "scope/work"],
            "zone": "episodes",
            "kind": kind,
            "slug": slug,
            "scope": "work",
            "display": f"{slug} — context",
        }
    ctx_fm["last-session"] = date_iso
    if phase is not None:
        ctx_fm["phase"] = phase
    frontmatter.write(ctx_path, ctx_fm, new_context_md)

    return ChangeReport(
        skill="mem_archive",
        success=True,
        files_created=[str(archive_path)],
        files_modified=[str(history_path), str(ctx_path)],
        summary_md=(
            f"**mem_archive (full)** — `{slug}` ({kind})\n\n"
            f"- Created `{archive_path.relative_to(vault)}`\n"
            f"- Updated `{history_path.relative_to(vault)}` (prepended new entry)\n"
            f"- Reset `{ctx_path.relative_to(vault)}` (last-session = {date_iso}"
            f"{f', phase = {phase}' if phase is not None else ''})\n"
        ),
    )


def register(mcp: FastMCP) -> None:
    """Register mem_archive with the FastMCP instance."""

    @mcp.tool()
    def mem_archive(
        slug: str = Field(..., description="Project or domain slug."),
        mode: Literal["incremental", "full"] = Field(
            "incremental",
            description=(
                "incremental = rewrite context.md only (mid-session). "
                "full = create a new archive + update history.md + reset context.md "
                "(end-of-session)."
            ),
        ),
        context_md: str = Field(
            "",
            description=(
                "New body for context.md. Required in both modes (in full mode, "
                "this becomes the post-session reset state)."
            ),
        ),
        archive_subject: str | None = Field(
            None,
            description="full mode only: short subject for the archive filename and entry.",
        ),
        archive_body_md: str | None = Field(
            None,
            description="full mode only: body of the new archive file.",
        ),
        phase: str | None = Field(
            None, description="Optional new phase string to set in context.md frontmatter."
        ),
    ) -> ChangeReport:
        """Archive the current session into the vault.

        Two modes per the spec:

        - "incremental" (default, mid-session): rewrites context.md with the new
          body, updates last-session and (optionally) phase in the frontmatter.
          No new archive file.

        - "full" (end-of-session, requires archive_subject + archive_body_md):
          creates a new dated archive file under archives/, prepends an entry
          to history.md, and resets context.md to new_context_md.

        Refuses archived projects (per _archived.md). Use mem_historize with
        revive=True first.
        """
        config = get_config()
        vault = config.vault

        if mode == "incremental":
            return _do_incremental(vault, slug, context_md, phase)

        # full mode — validate required fields
        if not archive_subject or not archive_body_md:
            raise ValueError(
                "full mode requires both archive_subject and archive_body_md"
            )
        return _do_full(
            vault, slug, archive_subject, archive_body_md, context_md, phase
        )
