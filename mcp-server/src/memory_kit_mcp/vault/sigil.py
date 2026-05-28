"""Sigil convention enforcement at write time.

Phase E of the relocation suite: archives must store paths under a project's
source tree as ``<repo>/...`` sigils, not absolute paths. Phases B-D repair
the existing vault; this module closes the loop so *new* writes already emit
sigils.

The single entry point :func:`sigilize_project_body` reads the project's
``repo_path`` from its ``context.md`` frontmatter and rewrites every absolute
path under that root to the sigil form. It is a no-op when ``repo_path`` is
unset (legacy projects) — so it is always safe to call.

Kept separate from ``repo_paths`` (which stays filesystem-free and pure) so the
``frontmatter`` dependency lives here only.
"""

from __future__ import annotations

from pathlib import Path

from memory_kit_mcp.vault import frontmatter
from memory_kit_mcp.vault.repo_paths import rewrite_abs_paths_to_sigil


def project_repo_path(project_folder: Path) -> str | None:
    """Return the ``repo_path`` declared in ``{project_folder}/context.md``.

    Returns ``None`` when the file is missing, unparseable, or the field is
    unset/empty.
    """
    ctx = project_folder / "context.md"
    if not ctx.exists():
        return None
    try:
        fm, _ = frontmatter.read(ctx)
    except (ValueError, OSError):
        return None
    value = fm.get("repo_path")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def sigilize_project_body(body: str, project_folder: Path) -> tuple[str, int]:
    """Rewrite absolute paths under the project's ``repo_path`` to sigils.

    Reads ``repo_path`` from ``{project_folder}/context.md``. Returns
    ``(new_body, n_rewrites)``. No-op (``(body, 0)``) when ``repo_path`` is
    unset — legacy projects keep their absolute paths until a relocation runs.

    ``repo_path`` may also be passed explicitly via :func:`sigilize_with_root`
    when the caller already knows the root (e.g. archeo tools that take the
    analysed repo as input).
    """
    repo_path = project_repo_path(project_folder)
    if not repo_path:
        return body, 0
    return rewrite_abs_paths_to_sigil(body, repo_path)


def sigilize_with_root(body: str, repo_path: str | None) -> tuple[str, int]:
    """Rewrite absolute paths under an explicit ``repo_path`` to sigils.

    No-op when ``repo_path`` is falsy. Used by callers that already hold the
    root (no ``context.md`` round-trip needed).
    """
    if not repo_path:
        return body, 0
    return rewrite_abs_paths_to_sigil(body, str(repo_path))
