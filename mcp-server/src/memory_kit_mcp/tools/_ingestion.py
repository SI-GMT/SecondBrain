"""Helpers shared by ingestion tools (mem_note, mem_principle, mem_goal, mem_person, mem_doc, mem).

Provides:
- _slugify_title — normalize a free-form title to a filesystem-safe slug
- _write_atom — atomic write with standard frontmatter conventions
- _ensure_unique_path — disambiguate filename collisions
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from memory_kit_mcp.vault import frontmatter

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def slugify_title(title: str, max_len: int = 60) -> str:
    """Convert a title to a kebab-case slug truncated to max_len chars.

    Treats whitespace, underscores AND punctuation (.,/:;) as separators —
    so "Ship v0.8.0" → "ship-v0-8-0" rather than "ship-v080".
    """
    s = title.lower().strip()
    s = re.sub(r"[\s_./:;]+", "-", s)
    s = _SLUG_RE.sub("", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s or "atom")[:max_len].rstrip("-")


def ensure_unique_path(target: Path) -> Path:
    """If target exists, append -2, -3, ... before the extension."""
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    i = 2
    while True:
        candidate = parent / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def write_atom(
    path: Path,
    fm: dict[str, Any],
    body: str,
) -> Path:
    """Atomic write with hash-uniqueness on path. Returns the actual path written."""
    actual = ensure_unique_path(path)
    frontmatter.write(actual, fm, body)
    return actual


def standard_frontmatter(
    *,
    slug: str,
    zone_short: str,  # 'knowledge', 'principles', 'goals', 'people', 'inbox', etc.
    kind: str,
    scope: str = "work",
    project: str | None = None,
    domain: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a baseline frontmatter dict matching the universal convention."""
    tags = [f"kind/{kind}", f"zone/{zone_short}", f"scope/{scope}"]
    if project:
        tags.append(f"project/{project}")
    if domain:
        tags.append(f"domain/{domain}")
    fm: dict[str, Any] = {
        "slug": slug,
        "zone": zone_short,
        "kind": kind,
        "scope": scope,
        "tags": tags,
        "created_at": datetime.now().date().isoformat(),
        "display": slug,
    }
    if project:
        fm["project"] = project
    if domain:
        fm["domain"] = domain
    if extra:
        fm.update(extra)
    return fm
