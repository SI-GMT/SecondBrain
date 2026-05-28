"""mem_archive_rewrite_paths — Convert legacy absolute paths in archive bodies
to the ``<repo>/...`` sigil.

Spec: core/procedures/mem-archive-rewrite-paths.md

After a disk reorganization, archives written before the sigil convention
existed still carry absolute paths like ``C:\\_PROJETS\\X\\src\\foo.py``. Those
references become infrastructure-stale when the repo moves. This skill rewrites
them, in place, to the canonical ``<repo>/src/foo.py`` sigil form so the
archives stay valid across every future relocation.

Doctrine permitted exception to "archives are immutable": an absolute path is
**infrastructure metadata** (not semantic content), so swapping it for a sigil
form is data-preservation, not content rewrite.

Companion tools:
- ``mem_relocate_project`` — updates ``repo_path`` in ``context.md``.
- ``mem_vault_migrate`` — moves the entire vault tree.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter, paths
from memory_kit_mcp.vault.atomic_io import write_atomic
from memory_kit_mcp.vault.repo_paths import (
    find_abs_paths_under_root,
    rewrite_abs_paths_to_sigil,
)


def _short_diff(original: str, rewritten: str, max_lines: int = 6) -> str:
    """Return a short side-by-side preview of changed lines."""
    orig_lines = original.splitlines()
    new_lines = rewritten.splitlines()
    pairs: list[str] = []
    for old, new in zip(orig_lines, new_lines):
        if old != new:
            pairs.append(f"  - `{old.strip()}`")
            pairs.append(f"  + `{new.strip()}`")
            if len(pairs) >= max_lines * 2:
                pairs.append("  …")
                break
    return "\n".join(pairs)


def _append_rewrite_log(
    vault: Path,
    slug: str,
    old_root: str,
    rewritten_files: list[tuple[str, int]],
) -> str:
    """Append an audit entry to ``99-meta/migrations/relocations.md``."""
    log = vault / "99-meta" / "migrations" / "relocations.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "---\n"
        "zone: meta\n"
        "kind: migration-log\n"
        "type: relocations\n"
        "tags: [zone/meta, kind/migration-log, type/relocations]\n"
        "display: relocations — migration log\n"
        "---\n\n"
        "# Project relocations — Migration log\n\n"
        "Append-only history of ``mem_relocate_project`` and "
        "``mem_archive_rewrite_paths`` operations.\n\n"
    )
    if not log.exists():
        log.write_text(header, encoding="utf-8", newline="\n")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = sum(n for _, n in rewritten_files)
    lines = [
        f"- **{ts}** — `mem_archive_rewrite_paths` on `{slug}`",
        f"  - old root: `{old_root}`",
        f"  - files modified: {len(rewritten_files)} (total {total} path occurrences)",
    ]
    for rel, n in rewritten_files[:10]:
        lines.append(f"    - `{rel}` ({n} occurrence{'s' if n != 1 else ''})")
    if len(rewritten_files) > 10:
        lines.append(f"    - … and {len(rewritten_files) - 10} more")
    with log.open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n\n")
    return str(log)


def register(mcp: FastMCP) -> None:
    """Register ``mem_archive_rewrite_paths`` with the FastMCP instance."""

    @mcp.tool()
    def mem_archive_rewrite_paths(
        slug: str = Field(..., description="Project slug whose archives should be rewritten."),
        old_root: str | None = Field(
            None,
            description="Legacy absolute root that should be rewritten. Defaults to "
            "the current ``context.md:repo_path`` of the project (useful right after "
            "relocating: pass the OLD root explicitly).",
        ),
        confirm: bool = Field(
            False,
            description="Without confirm=True the call is a dry-run (no FS mutation).",
        ),
        include_context_history: bool = Field(
            True,
            description="Also rewrite ``context.md`` and ``history.md`` bodies, not "
            "just archive files. Defaults to True.",
        ),
    ) -> ChangeReport:
        """Rewrite legacy absolute paths under ``old_root`` to the ``<repo>/...`` sigil.

        Effects (when ``confirm=True``):
        - Scans every ``.md`` file under the project folder (archives + the
          ``context.md`` / ``history.md`` files when ``include_context_history``).
        - In each body, replaces every occurrence of an absolute path that
          starts with ``old_root`` with the corresponding ``<repo>/...`` sigil.
        - Frontmatter is NOT touched (use ``mem_relocate_project`` for that).
        - Appends an audit entry to ``99-meta/migrations/relocations.md``.

        Dry-run mode (``confirm=False``) reports the list of files that would
        be rewritten plus the total occurrence count and a short preview, with
        no FS mutation.
        """
        config = get_config()
        vault = config.vault

        resolved = paths.resolve_slug(vault, slug)
        if resolved is None:
            raise FileNotFoundError(f"No project or domain '{slug}' in vault {vault}.")
        folder, kind, _archived = resolved

        # Resolve the legacy root to rewrite.
        if not old_root:
            ctx_fm, _ = frontmatter.read(folder / "context.md")
            old_root = (ctx_fm.get("repo_path") or "").strip()
            if not old_root:
                raise ValueError(
                    f"old_root not provided and {slug} has no repo_path in "
                    "context.md. Pass old_root explicitly."
                )

        # Scan files.
        candidates: list[Path] = []
        archives_dir = folder / "archives"
        if archives_dir.exists():
            candidates.extend(sorted(archives_dir.glob("*.md")))
        if include_context_history:
            for name in ("context.md", "history.md"):
                p = folder / name
                if p.exists():
                    candidates.append(p)

        results: list[tuple[str, int, str, str]] = []  # (rel, n, old_body, new_body)
        for md in candidates:
            try:
                fm, body = frontmatter.read(md)
            except (ValueError, OSError):
                continue
            occurrences = find_abs_paths_under_root(body, old_root)
            if not occurrences:
                continue
            new_body, n = rewrite_abs_paths_to_sigil(body, old_root)
            if n == 0:
                continue
            rel = str(md.relative_to(vault)).replace("\\", "/")
            results.append((rel, n, body, new_body))

        if not results:
            return ChangeReport(
                skill="mem_archive_rewrite_paths",
                success=True,
                summary_md=(
                    f"**mem_archive_rewrite_paths** — `{slug}`\n\n"
                    f"No absolute paths under `{old_root}` found in any archive "
                    f"or context/history file. Nothing to rewrite.\n"
                ),
            )

        total_occurrences = sum(n for _, n, _, _ in results)
        preview_lines = [f"**mem_archive_rewrite_paths** — `{slug}`\n"]
        preview_lines.append(
            f"- old root: `{old_root}`\n"
            f"- files to rewrite: **{len(results)}** "
            f"(total occurrences: **{total_occurrences}**)\n"
        )
        for rel, n, old_b, new_b in results[:5]:
            preview_lines.append(f"\n### `{rel}` ({n} occurrence{'s' if n != 1 else ''})\n")
            preview_lines.append(_short_diff(old_b, new_b))
        if len(results) > 5:
            preview_lines.append(f"\n… and {len(results) - 5} more file(s).")

        if not confirm:
            return ChangeReport(
                skill="mem_archive_rewrite_paths",
                success=True,
                warnings=["Dry-run only — pass confirm=True to apply."],
                summary_md="\n".join(preview_lines),
            )

        # ---- Apply ---------------------------------------------------------
        files_modified: list[str] = []
        for md in candidates:
            rel = str(md.relative_to(vault)).replace("\\", "/")
            match = next((r for r in results if r[0] == rel), None)
            if match is None:
                continue
            fm, body = frontmatter.read(md)
            new_body, n = rewrite_abs_paths_to_sigil(body, old_root)
            if n == 0:
                continue
            frontmatter.write(md, fm, new_body)
            files_modified.append(str(md))

        rewritten_summary = [(r[0], r[1]) for r in results]
        log_path = _append_rewrite_log(vault, slug, old_root, rewritten_summary)

        summary = (
            f"**mem_archive_rewrite_paths** — `{slug}`\n\n"
            f"- old root: `{old_root}`\n"
            f"- files rewritten: **{len(files_modified)}** "
            f"(total occurrences: **{total_occurrences}**)\n"
            f"- audit entry appended to `99-meta/migrations/relocations.md`\n"
        )
        return ChangeReport(
            skill="mem_archive_rewrite_paths",
            success=True,
            files_modified=files_modified + [log_path],
            summary_md=summary,
        )
