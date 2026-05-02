"""mem_search — Full-text search across the vault.

Spec: core/procedures/mem-search.md

POC implementation: regex-compatible substring search across all .md files in
the vault, with filters on zone, scope, kind, and archived inclusion. Returns
ranked hits with line context. No external grep tool — pure Python walk +
re.search() for portability across Windows/macOS/Linux.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import SearchHit, SearchResult
from memory_kit_mcp.vault import paths

_DEFAULT_LIMIT = 50
_CONTEXT_LINES = 1


def _zone_of(rel_path: Path) -> str:
    """Return the top-level zone of a vault-relative path (e.g. '10-episodes')."""
    parts = rel_path.parts
    return parts[0] if parts else ""


def _is_in_archived(rel_path: Path) -> bool:
    parts = rel_path.parts
    return len(parts) >= 2 and parts[0] == paths.ZONE_EPISODES and parts[1] == "archived"


def _match_lines(
    path: Path,
    rel_path: Path,
    pattern: re.Pattern[str],
) -> list[SearchHit]:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    lines = content.splitlines()
    hits: list[SearchHit] = []
    zone = _zone_of(rel_path)
    for i, line in enumerate(lines):
        if pattern.search(line):
            hits.append(
                SearchHit(
                    path=str(rel_path).replace("\\", "/"),
                    zone=zone,
                    line_number=i + 1,
                    line=line.rstrip(),
                    context_before=[
                        lines[j].rstrip()
                        for j in range(max(0, i - _CONTEXT_LINES), i)
                    ],
                    context_after=[
                        lines[j].rstrip()
                        for j in range(i + 1, min(len(lines), i + 1 + _CONTEXT_LINES))
                    ],
                )
            )
    return hits


def _format_summary_md(query: str, hits: list[SearchHit], total: int, truncated: bool) -> str:
    lines = [f"## Search results for `{query}` ({total} hit{'s' if total != 1 else ''})"]
    if truncated:
        lines.append(f"_(truncated — showing first {len(hits)})_")
    lines.append("")
    by_path: dict[str, list[SearchHit]] = {}
    for h in hits:
        by_path.setdefault(h.path, []).append(h)
    for path_key, path_hits in by_path.items():
        lines.append(f"### `{path_key}` ({len(path_hits)} match{'es' if len(path_hits) > 1 else ''})")
        for h in path_hits[:3]:  # cap inline context to 3 per file
            lines.append(f"- L{h.line_number}: {h.line.strip()}")
        if len(path_hits) > 3:
            lines.append(f"- _(+{len(path_hits) - 3} more in this file)_")
        lines.append("")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    """Register mem_search with the FastMCP instance."""

    @mcp.tool()
    def mem_search(
        query: str = Field(..., description="Pattern to search for (regex syntax)."),
        zone: str | None = Field(
            None,
            description=(
                "Restrict to one zone: 00-inbox, 10-episodes, 20-knowledge, ... "
                "If omitted, searches all zones."
            ),
        ),
        include_archived: bool = Field(
            False,
            description=(
                "Include 10-episodes/archived/ in the search. Excluded by default "
                "per the _archived.md doctrine."
            ),
        ),
        case_insensitive: bool = True,
        limit: int = Field(_DEFAULT_LIMIT, ge=1, le=500),
    ) -> SearchResult:
        """Full-text regex search across the vault.

        Returns ranked hits (one per matching line) with one line of context
        before and after, plus a Markdown summary grouped by file.
        """
        config = get_config()
        vault = config.vault
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            pattern = re.compile(query, flags)
        except re.error as e:
            raise ValueError(f"Invalid regex {query!r}: {e}") from e

        all_hits: list[SearchHit] = []
        for md_path in vault.rglob("*.md"):
            try:
                rel = md_path.relative_to(vault)
            except ValueError:
                continue
            if zone is not None and _zone_of(rel) != zone:
                continue
            if not include_archived and _is_in_archived(rel):
                continue
            all_hits.extend(_match_lines(md_path, rel, pattern))

        total = len(all_hits)
        truncated = total > limit
        kept = all_hits[:limit]
        return SearchResult(
            query=query,
            total_hits=total,
            truncated=truncated,
            hits=kept,
            summary_md=_format_summary_md(query, kept, total, truncated),
        )
