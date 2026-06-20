"""mem_relocate_project — Update a project's ``repo_path`` after a disk move.

Spec: core/procedures/mem-relocate-project.md

When the source tree of a project moves on disk (e.g. ``C:\\_PROJETS\\X`` ->
``D:\\_PROJETS\\X``), every archive that mentions the old path becomes
infrastructure-stale. The doctrinal answer is that archives should reference
paths as ``<repo>/...`` sigils (see ``vault.repo_paths``), and the absolute
root is resolved from ``context.md:repo_path``. This tool rewrites that ONE
field in ``context.md`` frontmatter and appends an audit entry — nothing else.

Companion tools:
- ``mem_vault_migrate`` — move the entire vault.
- ``mem_archive_rewrite_paths`` — convert legacy absolute paths in archive
  bodies to the ``<repo>/...`` sigil.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter, paths


def _git_remote_origin(repo: Path) -> str | None:
    """Return the ``origin`` remote URL of ``repo``, or None if unavailable."""
    git_dir = repo / ".git"
    if not git_dir.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _normalize_origin(url: str) -> str:
    """Normalize a Git remote URL for equivalence comparison.

    Strips ``.git`` suffix, lowercases the host part, normalizes
    ``https://`` ↔ ``git@host:`` form to a common shape.
    """
    s = url.strip()
    if s.endswith(".git"):
        s = s[:-4]
    # git@host:org/repo  ->  host/org/repo
    if s.startswith("git@"):
        s = s[4:].replace(":", "/", 1)
    # https://host/org/repo  ->  host/org/repo
    elif s.startswith("https://"):
        s = s[len("https://") :]
    elif s.startswith("http://"):
        s = s[len("http://") :]
    elif s.startswith("ssh://git@"):
        s = s[len("ssh://git@") :]
    # Lowercase the host (first segment) only; preserve case of org/repo.
    first, sep, rest = s.partition("/")
    return f"{first.lower()}{sep}{rest}"


def _paths_equal(a: Path | str, b: Path | str) -> bool:
    sa = str(a).replace("\\", "/").rstrip("/")
    sb = str(b).replace("\\", "/").rstrip("/")
    if os.name == "nt":
        sa, sb = sa.lower(), sb.lower()
    return sa == sb


def _append_relocation_log(
    vault: Path, slug: str, kind: str, old: str, new: str, reason: str | None
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
    entry = [
        f"- **{ts}** — `mem_relocate_project` on `{slug}` ({kind})",
        f"  - old `repo_path`: `{old or '(unset)'}`",
        f"  - new `repo_path`: `{new}`",
    ]
    if reason:
        entry.append(f"  - reason: {reason}")
    with log.open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(entry) + "\n\n")
    return str(log)


def register(mcp: FastMCP) -> None:
    """Register ``mem_relocate_project`` with the FastMCP instance."""

    @mcp.tool()
    def mem_relocate_project(
        slug: str = Field(..., description="Project (or domain) slug to relocate."),
        new_root: str = Field(..., description="New absolute path of the repo root on disk."),
        confirm: bool = Field(
            False,
            description="Without confirm=True the call is a dry-run (no FS mutation).",
        ),
        force: bool = Field(
            False,
            description="Skip the git-remote sanity check (use only if the new root "
            "has no .git or origin differs intentionally).",
        ),
        reason: str | None = Field(
            None,
            description="Free-text reason for the audit log entry.",
        ),
    ) -> ChangeReport:
        """Update ``repo_path`` in ``context.md`` frontmatter for one project.

        Effects (when ``confirm=True``):
        - Patches a single field in one file: ``context.md:repo_path``.
        - Appends an audit entry to ``99-meta/migrations/relocations.md``.
        - Nothing else. Archives, history, frontmatter elsewhere are untouched
          — by design, since they should reference paths via the ``<repo>/...``
          sigil (cf. ``mem_archive_rewrite_paths`` for legacy migration).

        Pre-conditions:
        - ``slug`` resolves to a project or domain in the vault.
        - ``new_root`` exists on disk and contains a ``.git`` directory.
        - The ``origin`` remote of ``new_root`` matches the one declared in the
          project's ``topology`` file (when available) — guard against
          accidentally pointing the project at the wrong repo.
        - ``force=True`` bypasses the git-remote sanity check.
        """
        config = get_config()
        vault = config.vault
        new_root_p = Path(new_root).expanduser().absolute()

        resolved = paths.resolve_slug(vault, slug)
        if resolved is None:
            raise FileNotFoundError(f"No project or domain '{slug}' in vault {vault}.")
        folder, kind, _archived = resolved
        context_md = folder / "context.md"
        if not context_md.exists():
            raise FileNotFoundError(f"context.md missing for {slug} at {context_md}.")

        # Read current repo_path
        fm, body = frontmatter.read(context_md)
        old_repo_path = fm.get("repo_path") or ""

        # ---- Pre-flight checks --------------------------------------------
        warnings: list[str] = []
        if not new_root_p.exists():
            raise FileNotFoundError(f"New root does not exist on disk: {new_root_p}")
        if not new_root_p.is_dir():
            raise NotADirectoryError(f"New root is not a directory: {new_root_p}")
        if _paths_equal(old_repo_path, new_root_p):
            return ChangeReport(
                skill="mem_relocate_project",
                success=True,
                summary_md=(
                    f"**mem_relocate_project** — no-op\n\n"
                    f"`{slug}` already has `repo_path: {new_root_p}` — nothing to do.\n"
                ),
            )

        new_origin = _git_remote_origin(new_root_p)
        if not new_origin and not force:
            raise RuntimeError(
                f"{new_root_p} has no ``.git`` directory with an ``origin`` remote. "
                "Pass force=True to skip this check."
            )

        # Compare origin with the topology file (if any).
        topology = paths.topology_file(vault, slug)
        if topology.exists() and new_origin:
            tfm, _ = frontmatter.read(topology)
            old_origin = tfm.get("repo_remote") or tfm.get("origin") or ""
            if old_origin and _normalize_origin(old_origin) != _normalize_origin(new_origin):
                if not force:
                    raise RuntimeError(
                        f"Git remote mismatch — new root's origin "
                        f"({new_origin}) does not match the project's recorded "
                        f"remote ({old_origin}). Pass force=True to override."
                    )
                warnings.append(
                    f"Origin mismatch overridden via force=True: "
                    f"topology={old_origin} new={new_origin}"
                )

        # ---- Dry-run -------------------------------------------------------
        plan = (
            f"**mem_relocate_project** (dry-run) — `{slug}` ({kind})\n\n"
            f"- old `repo_path`: `{old_repo_path or '(unset)'}`\n"
            f"- new `repo_path`: `{new_root_p}`\n"
            f"- file touched: `{context_md.relative_to(vault)}` (one frontmatter field)\n"
        )
        if warnings:
            plan += "\nWarnings:\n" + "\n".join(f"- {w}" for w in warnings) + "\n"
        if not confirm:
            return ChangeReport(
                skill="mem_relocate_project",
                success=True,
                warnings=warnings + ["Dry-run only — pass confirm=True to apply."],
                summary_md=plan,
            )

        # ---- Apply ---------------------------------------------------------
        fm["repo_path"] = str(new_root_p)
        frontmatter.write(context_md, fm, body)
        log_path = _append_relocation_log(vault, slug, kind, old_repo_path, str(new_root_p), reason)

        summary = (
            f"**mem_relocate_project** — `{slug}` ({kind})\n\n"
            f"- `repo_path`: `{old_repo_path or '(unset)'}` → `{new_root_p}`\n"
            f"- `{context_md.relative_to(vault)}` updated (single frontmatter field)\n"
            f"- audit entry appended to `99-meta/migrations/relocations.md`\n"
        )
        return ChangeReport(
            skill="mem_relocate_project",
            success=True,
            files_modified=[str(context_md), log_path],
            warnings=warnings,
            summary_md=summary,
        )
