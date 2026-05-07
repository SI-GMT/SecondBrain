"""CLI entry point for Phase 0 archeo enumeration — runs without an MCP client.

Doctrine: ``core/procedures/_archeo-architecture-v2.md``.

This is the in-package CLI. A standalone script at ``scripts/archeo-topology.py``
that does not require ``pip install memory-kit-mcp`` is planned (paire
cohérence #4, like ``scripts/doc-readers/*``) but not yet shipped.

Invocation::

    python -m memory_kit_mcp.archeo_topology --repo /path/to/repo
    archeo-topology --repo /path/to/repo --branch feature/x --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from memory_kit_mcp import __version__
from memory_kit_mcp._console import force_utf8_console
from memory_kit_mcp.archeo import enumerate_files


def _format_atom_md(repo_path: Path, project: str, result) -> str:  # type: ignore[no-untyped-def]
    """Render the EnumerateResult as a topology atom (Markdown + frontmatter)."""
    fm_lines = [
        "---",
        f"project: {project}",
        "zone: meta",
        "kind: repo-topology",
        f"slug: {project}",
        f"display: {project} — repo topology",
        "source: archeo-topology",
        f"source_mode: {result.source_mode}",
    ]
    if result.scope_glob:
        # Quote the glob if it contains anything ambiguous for YAML.
        fm_lines.append(f"scope_glob: {json.dumps(result.scope_glob)}")
    if result.branch:
        fm_lines.append(f"branch: {result.branch}")
    if result.base_ref:
        fm_lines.append(f"base_ref: {result.base_ref}")
    if result.merge_base_strategy:
        fm_lines.append(f"merge_base_strategy: {result.merge_base_strategy}")
    fm_lines.extend(
        [
            f"files_count: {result.files_count}",
            f"files_bytes: {result.files_bytes}",
            f"files_hash: {result.files_hash}",
            f"generated_at: {datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')}",
            f"generated_by: archeo-topology v{__version__}",
            "---",
        ]
    )

    body_lines = [
        "",
        f"# {project} — repo topology",
        "",
        f"> Phase 0 archeo v2 snapshot — {result.files_count} file(s), "
        f"{result.files_bytes // (1024 * 1024)} MiB.",
        "",
    ]
    if result.warnings:
        body_lines.append("## Warnings")
        body_lines.append("")
        for w in result.warnings:
            body_lines.append(f"- {w}")
        body_lines.append("")
    body_lines.append("## Inventory")
    body_lines.append("")
    body_lines.append("```")
    for f in result.files:
        body_lines.append(str(f))
    body_lines.append("```")
    body_lines.append("")
    if result.pass_b_files:
        body_lines.append("## Pass B — repo-local imports")
        body_lines.append("")
        body_lines.append("```")
        for f in result.pass_b_files:
            body_lines.append(str(f))
        body_lines.append("```")
        body_lines.append("")
    if result.trace:
        body_lines.append("## Trace")
        body_lines.append("")
        body_lines.append("```")
        for t in result.trace:
            body_lines.append(t)
        body_lines.append("```")
        body_lines.append("")
    return "\n".join(fm_lines + body_lines)


def _format_json(repo_path: Path, project: str, result) -> str:  # type: ignore[no-untyped-def]
    return json.dumps(
        {
            "project": project,
            "repo_path": str(repo_path),
            "source_mode": result.source_mode,
            "scope_glob": result.scope_glob,
            "branch": result.branch,
            "base_ref": result.base_ref,
            "merge_base_strategy": result.merge_base_strategy,
            "files_count": result.files_count,
            "files_bytes": result.files_bytes,
            "files_hash": result.files_hash,
            "files": [str(f) for f in result.files],
            "batches": [[str(f) for f in batch] for batch in result.batches],
            "pass_b_files": [str(f) for f in result.pass_b_files],
            "warnings": result.warnings,
            "trace": result.trace,
        },
        indent=2,
        ensure_ascii=False,
    )


def main(argv: list[str] | None = None) -> int:
    force_utf8_console()
    parser = argparse.ArgumentParser(
        prog="archeo-topology",
        description="Phase 0 archeo enumeration — runs outside the MCP server.",
    )
    parser.add_argument("--repo", required=True, help="Repo root path.")
    parser.add_argument(
        "--project",
        default="",
        help="Project slug for the atom frontmatter. Defaults to repo dir name.",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "git", "raw"),
        default="auto",
        help="Enumeration mode (default: auto-detect via .git/).",
    )
    parser.add_argument("--scope-glob", default=None, help="Optional fnmatch glob.")
    parser.add_argument("--branch", default=None, help="Branch-first mode (git only).")
    parser.add_argument(
        "--base-ref",
        default=None,
        help="Explicit base SHA / ref (auto-resolved when --branch is set without --base-ref).",
    )
    parser.add_argument(
        "--fallback-base",
        default="main",
        help="Default branch for merge-base resolution (default: main).",
    )
    parser.add_argument(
        "--pass-b",
        action="store_true",
        help="Resolve repo-local imports of Pass A files (Python + JS/TS).",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Soft cap on file count (default 500, 0 = no cap).",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=None,
        help="Soft cap on cumulative bytes (default 50 MiB, 0 = no cap).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Suggested batch size (default 200).",
    )
    parser.add_argument(
        "--hard-abort",
        action="store_true",
        help="Raise on overflow instead of warning.",
    )
    parser.add_argument(
        "--max-pass-b-files",
        type=int,
        default=None,
        help="Cap on Pass B file reads (default 200, 0 = no cap).",
    )
    parser.add_argument(
        "--pass-b-read-bytes",
        type=int,
        default=None,
        help="Bytes read from each Pass B file head (default 16384, 0 = full).",
    )
    parser.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="Output format (default: md, atom-shaped Markdown).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write output to this file instead of stdout.",
    )

    args = parser.parse_args(argv)

    repo = Path(args.repo).expanduser().resolve()
    project = args.project or repo.name

    try:
        result = enumerate_files(
            repo,
            mode=args.mode,
            scope_glob=args.scope_glob,
            branch=args.branch,
            base_ref=args.base_ref,
            fallback_base=args.fallback_base,
            pass_b=args.pass_b,
            max_files=args.max_files,
            max_bytes=args.max_bytes,
            batch_size=args.batch_size,
            hard_abort=args.hard_abort,
            max_pass_b_files=args.max_pass_b_files,
            pass_b_read_bytes=args.pass_b_read_bytes,
        )
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    payload = (
        _format_atom_md(repo, project, result)
        if args.format == "md"
        else _format_json(repo, project, result)
    )

    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8", newline="\n")
        print(f"wrote {out_path}", file=sys.stderr)
    else:
        sys.stdout.write(payload)
        if not payload.endswith("\n"):
            sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
