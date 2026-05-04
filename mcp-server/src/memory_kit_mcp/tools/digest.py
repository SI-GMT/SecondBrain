"""mem_digest — Synthesize the last N archives of a project or domain.

Spec: core/procedures/mem-digest.md

POC implementation: read-only walk of the project's archives/, sort by
filename (which encodes the date prefix), take the last N, return their
metadata + body excerpt + a Markdown chronological recap.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ArchiveDigest, DigestResult
from memory_kit_mcp.vault import frontmatter, paths

_DEFAULT_N = 5
_EXCERPT_CHARS = 300

# Filename pattern: 2026-04-30-14h00-{slug}-{subject}.md
_FILENAME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})-(?P<time>\d{2}h\d{2})-"
    r"(?P<slug>[^-]+(?:-[^-]+)*?)-(?P<subject>.+)\.md$"
)


def _parse_filename(filename: str) -> tuple[str | None, str | None]:
    """Extract (date, subject) from an archive filename. Best-effort."""
    m = _FILENAME_RE.match(filename)
    if not m:
        return None, None
    return m.group("date"), m.group("subject").replace("-", " ")


def _excerpt(body: str, max_chars: int = _EXCERPT_CHARS) -> str:
    """Take the first paragraph or up to max_chars, whichever is shorter."""
    cleaned = body.strip().lstrip("#").lstrip()
    # Skip leading blockquote lines (they're often disclaimers)
    lines = [
        line for line in cleaned.splitlines()
        if line.strip() and not line.strip().startswith(">")
    ]
    if not lines:
        return ""
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


def _format_summary_md(slug: str, kind: str, archives: list[ArchiveDigest], total: int) -> str:
    lines = [f"## Digest — {slug} ({kind})\n"]
    lines.append(f"_Showing {len(archives)} of {total} archive{'s' if total != 1 else ''}._\n")
    if not archives:
        lines.append("_(no archives yet)_")
        return "\n".join(lines)
    for a in archives:
        title = a.subject or a.filename
        date_prefix = f"**{a.date}** — " if a.date else ""
        lines.append(f"### {date_prefix}{title}")
        if a.body_excerpt:
            lines.append("")
            lines.append(a.body_excerpt)
        lines.append("")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    """Register mem_digest with the FastMCP instance."""

    @mcp.tool()
    def mem_digest(
        slug: str = Field(..., description="Project or domain slug to digest."),
        n: int = Field(
            _DEFAULT_N,
            ge=1,
            le=50,
            description="Number of most recent archives to include (default 5).",
        ),
        from_archived: bool = Field(
            False,
            description=(
                "Allow digesting an archived project (refused by default per "
                "the _archived.md doctrine)."
            ),
        ),
    ) -> DigestResult:
        """Synthesize the most recent N archives of a project or domain.

        Read-only: returns each archive's date, subject, and an excerpt of its
        body. The summary_md field renders a chronological recap suitable for
        direct display to the user.
        """
        config = get_config()
        vault = config.vault

        resolved = paths.resolve_slug(vault, slug)
        if resolved is None:
            raise FileNotFoundError(
                f"No project or domain '{slug}' found in vault {vault}."
            )
        folder, kind, archived = resolved
        if archived and not from_archived:
            raise PermissionError(
                f"Project '{slug}' is archived. Pass from_archived=True to digest "
                "an archived project (per _archived.md doctrine)."
            )

        archives_dir = folder / "archives"
        if not archives_dir.exists():
            return DigestResult(
                project=slug,
                kind=kind,
                archives_returned=0,
                archives_total=0,
                archives=[],
                summary_md=_format_summary_md(slug, kind, [], 0),
            )

        all_archives: list[Path] = sorted(archives_dir.glob("*.md"))
        total = len(all_archives)
        # Take the last N (most recent — sorted by date prefix)
        selected = all_archives[-n:][::-1]  # reverse so most recent first

        digests: list[ArchiveDigest] = []
        for archive_path in selected:
            try:
                _, body = frontmatter.read(archive_path)
            except (ValueError, OSError):
                body = ""
            date, subject = _parse_filename(archive_path.name)
            digests.append(
                ArchiveDigest(
                    filename=archive_path.name,
                    date=date,
                    subject=subject,
                    body_excerpt=_excerpt(body),
                )
            )

        return DigestResult(
            project=slug,
            kind=kind,
            archives_returned=len(digests),
            archives_total=total,
            archives=digests,
            summary_md=_format_summary_md(slug, kind, digests, total),
        )
