"""mem_archeo_index_files — Phase 0 preview tool (archeo v2).

Spec: ``core/procedures/mem-archeo-index-files.md``.
Doctrine: ``core/procedures/_archeo-architecture-v2.md``.

Returns the file list and pre-computed batches that Phase 1/2/3 would
operate on for a given repo + scope. Read-only — never writes the vault.

The LLM uses this tool to:

1. Preview the scope of an archeo before launching the heavier phases.
2. Detect scope overflows (``ScopeOverflowWarning`` in ``warnings``) and
   decide to batch over ``batches`` rather than monolithic invocation.
3. Drive batched ``mem_archeo_context`` calls explicitly via
   ``file_list_override`` (cap suivant once Phase 1 ports the v2 contract).
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.archeo import (
    BATCH_SIZE_DEFAULT,
    SOFT_CAP_BYTES_DEFAULT,
    SOFT_CAP_FILES_DEFAULT,
    EnumerateResult,
    enumerate_files,
)
from memory_kit_mcp.tools._models import ArcheoIndexResult


def _format_summary_md(
    project: str, repo_path: Path, result: EnumerateResult
) -> str:
    lines = [
        f"## mem_archeo_index_files — `{project}`\n",
        f"- Repo: `{repo_path}`",
        f"- Mode: **{result.source_mode}**",
    ]
    if result.scope_glob:
        lines.append(f"- Scope glob: `{result.scope_glob}`")
    if result.branch:
        lines.append(f"- Branch: `{result.branch}`")
        if result.base_ref:
            lines.append(
                f"- Base ref: `{result.base_ref[:12]}` "
                f"(strategy: `{result.merge_base_strategy}`)"
            )
    lines.append(
        f"- Files: **{result.files_count}** "
        f"({result.files_bytes // (1024 * 1024)} MiB)"
    )
    lines.append(f"- Files hash: `{result.files_hash[:16]}…`")
    lines.append(f"- Batches: **{len(result.batches)}**")
    if result.pass_b_files:
        lines.append(f"- Pass B (imports): **{len(result.pass_b_files)}** additional file(s)")
    if result.warnings:
        lines.append("")
        lines.append("### Warnings")
        for w in result.warnings:
            lines.append(f"- {w}")
    if result.trace:
        lines.append("")
        lines.append("### Trace")
        lines.append("```")
        for t in result.trace:
            lines.append(t)
        lines.append("```")
    if result.files_count == 0:
        lines.append("")
        lines.append("_No files matched. Check `scope_glob` or `repo_path`._")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def mem_archeo_index_files(
        project: str = Field(
            ..., description="Project slug (used in summary, no vault write)."
        ),
        repo_path: str = Field(
            ..., description="Absolute path to the repo to enumerate."
        ),
        mode: str = Field(
            "auto",
            description="'auto' (detect by .git/), 'git', or 'raw'.",
        ),
        scope_glob: str | None = Field(
            None,
            description="Optional fnmatch glob (e.g. 'src/api/**'). Applied after enumeration.",
        ),
        branch: str | None = Field(
            None,
            description=(
                "Branch-first mode (git only) — restrict to Pass A files of "
                "this branch. Ignored in raw mode."
            ),
        ),
        base_ref: str | None = Field(
            None,
            description=(
                "Explicit base SHA / ref for branch-first. Auto-resolved "
                "(merge-base + first-parent fallback) when None."
            ),
        ),
        fallback_base: str = Field(
            "main",
            description="Default branch for merge-base resolution.",
        ),
        pass_b: bool = Field(
            False,
            description=(
                "Resolve repo-local imports of Pass A files (Python + JS/TS, "
                "best effort). Off by default — heavier."
            ),
        ),
        max_files: int | None = Field(
            None,
            description=(
                f"Soft cap on file count. None = default {SOFT_CAP_FILES_DEFAULT}. "
                "0 = no cap."
            ),
        ),
        max_bytes: int | None = Field(
            None,
            description=(
                f"Soft cap on cumulative bytes. None = default "
                f"{SOFT_CAP_BYTES_DEFAULT // (1024 * 1024)} MiB. 0 = no cap."
            ),
        ),
        batch_size: int | None = Field(
            None,
            description=(
                f"Suggested batch size. None = default {BATCH_SIZE_DEFAULT}."
            ),
        ),
        hard_abort: bool = Field(
            False,
            description=(
                "If True, raise on overflow instead of warning. Default False."
            ),
        ),
        max_pass_b_files: int | None = Field(
            None,
            description=(
                "Cap on the number of files actually read for Pass B "
                "(default 200, 0 = no cap). Files of unscanned languages are "
                "skipped without I/O before this cap applies."
            ),
        ),
        pass_b_read_bytes: int | None = Field(
            None,
            description=(
                "Bytes read from the head of each Pass B file (default "
                "16384). 0 reads the full file (not recommended)."
            ),
        ),
    ) -> ArcheoIndexResult:
        """Preview the file list and batches Phase 1+ would consume.

        Phase 0 of archeo v2: shell-delegated enumeration (git or os.walk),
        scope filtering, soft caps with non-blocking warnings, pre-computed
        batch slicing. Read-only — never writes the vault.
        """
        repo = Path(repo_path).expanduser().resolve()
        result = enumerate_files(
            repo,
            mode=mode,  # type: ignore[arg-type]
            scope_glob=scope_glob,
            branch=branch,
            base_ref=base_ref,
            fallback_base=fallback_base,
            pass_b=pass_b,
            max_files=max_files,
            max_bytes=max_bytes,
            batch_size=batch_size,
            hard_abort=hard_abort,
            max_pass_b_files=max_pass_b_files,
            pass_b_read_bytes=pass_b_read_bytes,
        )
        return ArcheoIndexResult(
            project=project,
            repo_path=str(repo),
            source_mode=result.source_mode,
            scope_glob=result.scope_glob,
            branch=result.branch,
            base_ref=result.base_ref,
            merge_base_strategy=result.merge_base_strategy,
            files=[str(f) for f in result.files],
            files_count=result.files_count,
            files_bytes=result.files_bytes,
            files_hash=result.files_hash,
            batches=[[str(f) for f in batch] for batch in result.batches],
            pass_b_files=[str(f) for f in result.pass_b_files],
            warnings=result.warnings,
            trace=result.trace,
            summary_md=_format_summary_md(project, repo, result),
        )
