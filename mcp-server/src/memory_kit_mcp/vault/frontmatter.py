"""YAML frontmatter parsing for vault Markdown files.

Conventions per core/procedures/_frontmatter-universal.md:
- Frontmatter is a single YAML block delimited by --- at the top of the file.
- Body follows immediately after the closing ---.
- UTF-8 without BOM, LF line endings.
- A file without frontmatter is valid (empty dict returned, full content as body).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from memory_kit_mcp.vault.atomic_io import write_atomic

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def parse(content: str) -> tuple[dict[str, Any], str]:
    """Split a Markdown file into (frontmatter_dict, body_str).

    Returns ({}, content) if no frontmatter block is detected.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content
    fm_raw, body = match.groups()
    try:
        fm = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML frontmatter: {e}") from e
    if not isinstance(fm, dict):
        raise ValueError(f"Frontmatter must be a mapping, got {type(fm).__name__}")
    return fm, body


def read(path: Path) -> tuple[dict[str, Any], str]:
    """Read a file from disk and split frontmatter / body."""
    return parse(path.read_text(encoding="utf-8"))


def serialize(fm: dict[str, Any], body: str) -> str:
    """Serialize a frontmatter dict + body back to a Markdown file string.

    YAML output uses block style (default_flow_style=False), preserves key order,
    and disables aliases (sort_keys=False). Quotes only when necessary.
    """
    if not fm:
        return body
    fm_yaml = yaml.safe_dump(
        fm,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=10_000,  # avoid line wrapping in long descriptions
    )
    # body can be empty or start with a newline — normalize so output is consistent
    body_norm = body.lstrip("\n")
    return f"---\n{fm_yaml}---\n\n{body_norm}" if body_norm else f"---\n{fm_yaml}---\n"


def write(path: Path, fm: dict[str, Any], body: str) -> None:
    """Atomic write of (frontmatter, body) to a Markdown file.

    UTF-8 without BOM, LF line endings (cf. atomic_io.write_atomic).
    """
    write_atomic(path, serialize(fm, body))
