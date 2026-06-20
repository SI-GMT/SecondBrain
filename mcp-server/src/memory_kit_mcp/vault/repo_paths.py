"""Repo-relative path sigil — single source of truth for archive paths.

Archives store paths under a project's source tree as `<repo>/src/foo.py`
sigil form. The absolute root is resolved lazily from the project's
`context.md` frontmatter `repo_path:` field. Moving the repo on disk only
requires updating `repo_path` in `context.md` (cf. mem-relocate-project) —
archives stay valid.

Sigil grammar:
- Exactly `<repo>` → repo root itself.
- `<repo>/<posix-tail>` → file or subdir under repo. Tail uses forward
  slashes regardless of OS for portability.

Lexical-only API: helpers do NOT touch the filesystem (no resolve(), no
exists()). This is on purpose — archives may reference paths that have
moved/disappeared. Comparison is case-insensitive on Windows, case-sensitive
elsewhere, and treats `/` and `\\` interchangeably.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

SIGIL = "<repo>"
_SIGIL_RE = re.compile(r"^<repo>(?:/|$)")
_CASE_INSENSITIVE = os.name == "nt"


def _normalize(p: str) -> str:
    """Normalize a path string for lexical comparison.

    - Backslashes → forward slashes.
    - Trailing slash stripped.
    - Lowercased on Windows.
    """
    s = p.replace("\\", "/").rstrip("/")
    if _CASE_INSENSITIVE:
        s = s.lower()
    return s


def to_repo_relative(abs_path: str | Path, repo_path: str | Path) -> str | None:
    """Convert ``abs_path`` to ``<repo>/...`` sigil form.

    Returns the sigil string if ``abs_path`` is under ``repo_path`` (or equal
    to it). Returns ``None`` if outside the repo.

    Lexical comparison only — does not check filesystem existence.
    """
    abs_raw = str(abs_path).replace("\\", "/").rstrip("/")
    root_raw = str(repo_path).replace("\\", "/").rstrip("/")
    abs_norm = abs_raw.lower() if _CASE_INSENSITIVE else abs_raw
    root_norm = root_raw.lower() if _CASE_INSENSITIVE else root_raw

    if abs_norm == root_norm:
        return SIGIL
    prefix = root_norm + "/"
    if not abs_norm.startswith(prefix):
        return None
    # Preserve original casing of the tail (use abs_raw, not abs_norm).
    tail = abs_raw[len(root_raw) + 1 :]
    return f"{SIGIL}/{tail}" if tail else SIGIL


def from_repo_relative(sigil_path: str, repo_path: str | Path) -> Path:
    """Expand ``<repo>/...`` sigil to an absolute :class:`Path`.

    Raises :class:`ValueError` if ``sigil_path`` does not start with the
    ``<repo>`` sigil.
    """
    if not _SIGIL_RE.match(sigil_path):
        raise ValueError(f"Not a repo-sigil path: {sigil_path!r}")
    tail = sigil_path[len(SIGIL) :].lstrip("/")
    base = Path(repo_path)
    if not tail:
        return base
    # PurePosixPath ensures tail uses forward slashes consistently before join.
    return base.joinpath(*PurePosixPath(tail).parts)


def is_repo_relative(s: str) -> bool:
    """Return True iff ``s`` starts with the ``<repo>`` sigil."""
    return bool(_SIGIL_RE.match(s))


# Pattern character class for absolute path body (after the root prefix).
# Stops at whitespace, common Markdown/code delimiters, and end of string.
_PATH_BODY = r"[^\s`\"'<>(){}\[\],;]"


def find_abs_paths_under_root(text: str, root: str) -> list[tuple[int, int, str]]:
    """Locate occurrences of absolute paths starting with ``root`` in ``text``.

    Returns a list of ``(start, end, matched_text)`` tuples (positions in the
    original ``text``). Matches accept both ``/`` and ``\\`` separators.
    Greedy on the tail, stopping at whitespace or typical delimiters.
    Case-insensitive on Windows.

    Useful for scanning archive bodies for absolute paths that should be
    rewritten to sigil form (cf. mem-archive-rewrite-paths).
    """
    root_norm = root.replace("\\", "/").rstrip("/")
    if not root_norm:
        return []
    # Split root into segments and rejoin allowing both separators.
    segments = root_norm.split("/")
    sep = r"[\\/]"
    root_pattern = sep.join(re.escape(seg) for seg in segments)
    # After root, optionally consume one separator + body characters (incl.
    # nested separators). Body must NOT start with another path-body char that
    # would extend an unrelated identifier (e.g. C:\Users\bdubois<extra>).
    pattern = root_pattern + rf"(?:{sep}{_PATH_BODY}*)?"
    flags = re.IGNORECASE if _CASE_INSENSITIVE else 0
    return [(m.start(), m.end(), m.group(0)) for m in re.finditer(pattern, text, flags)]


def rewrite_abs_paths_to_sigil(text: str, repo_path: str) -> tuple[str, int]:
    """Rewrite every absolute path under ``repo_path`` to the sigil form.

    Returns ``(new_text, n_replacements)``. Non-matching paths are left alone.
    Original separator/casing of the rewritten path is replaced with the
    canonical sigil + forward-slash tail.
    """
    matches = find_abs_paths_under_root(text, repo_path)
    if not matches:
        return text, 0
    out: list[str] = []
    cursor = 0
    n = 0
    for start, end, matched in matches:
        sigil = to_repo_relative(matched, repo_path)
        if sigil is None:
            continue
        out.append(text[cursor:start])
        out.append(sigil)
        cursor = end
        n += 1
    out.append(text[cursor:])
    return "".join(out), n
