#!/usr/bin/env python
"""Profile the v1 archeo phases on a target repo.

Goal: identify the real bottlenecks of ``mem_archeo`` / ``mem_archeo_stack`` /
``mem_archeo_git`` on large codebases (case study: IRIS USER, ~1226 files,
30s+ MCP timeouts). Without a profile, optimisation is blind.

Usage::

    # Profile every phase on this very repo (small, ~1s total).
    python scripts/profile-archeo.py --repo .

    # Profile on a large repo, only Phase 0 + Phase 2 (skip slow git phase).
    python scripts/profile-archeo.py --repo C:/_PROJETS/IRIS/PROD/USER --skip-git

    # Profile only Phase 3 with branch-first mode.
    python scripts/profile-archeo.py --repo C:/_PROJETS/IRIS/PROD/USER \\
        --only git --git-branch ecosav --git-base master

The script bootstraps a throwaway vault under a temp dir so writes by
``execute_stack`` and ``execute_git`` don't touch the real vault.

Output: per-phase wall-clock timing + cProfile breakdown (top 25 by
cumulative time). Read the cumtime column to find hotspots — entries
spending most of their time in subprocess calls indicate git / external
process bottlenecks; entries in pure Python indicate algorithmic issues.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import os
import pstats
import shutil
import sys
import tempfile
import time
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_SRC = REPO_ROOT / "mcp-server" / "src"
SKELETON = REPO_ROOT / "mcp-server" / "tests" / "fixtures" / "vault-skeleton"


def _bootstrap_tmp_vault() -> tuple[Path, Path]:
    """Create a tmp vault skeleton + config and point ``MEMORY_KIT_HOME`` to it."""
    tmp_root = Path(tempfile.mkdtemp(prefix="archeo-profile-"))
    vault = tmp_root / "vault"
    if SKELETON.is_dir():
        shutil.copytree(SKELETON, vault)
    else:
        # Minimum scaffold so config validation passes.
        vault.mkdir()
        (vault / "10-episodes" / "projects").mkdir(parents=True)
        (vault / "99-meta" / "repo-topology").mkdir(parents=True)

    config_dir = tmp_root / ".memory-kit"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "vault": str(vault),
                "default_scope": "work",
                "language": "en",
                "kit_repo": str(REPO_ROOT),
            }
        ),
        encoding="utf-8",
    )

    os.environ["MEMORY_KIT_HOME"] = str(config_dir)
    return tmp_root, vault


def _print_section(label: str) -> None:
    print()
    print("=" * 72)
    print(label)
    print("=" * 72)


def _print_profile(profiler: cProfile.Profile, top: int = 25) -> None:
    buf = StringIO()
    stats = pstats.Stats(profiler, stream=buf).strip_dirs().sort_stats("cumulative")
    stats.print_stats(top)
    print(buf.getvalue())


def _profile_phase(label: str, fn) -> tuple[float, object]:
    profiler = cProfile.Profile()
    t0 = time.perf_counter()
    profiler.enable()
    try:
        result = fn()
    finally:
        profiler.disable()
    elapsed = time.perf_counter() - t0
    _print_section(f"{label} — wall-clock {elapsed:.3f}s")
    _print_profile(profiler)
    return elapsed, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="profile-archeo",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo", required=True, help="Absolute path to the repo to profile."
    )
    parser.add_argument(
        "--only",
        choices=("topology", "stack", "git", "all"),
        default="all",
        help="Restrict to a single phase. Default: all.",
    )
    parser.add_argument(
        "--skip-stack", action="store_true", help="Skip Phase 2 (stack)."
    )
    parser.add_argument(
        "--skip-git", action="store_true", help="Skip Phase 3 (git)."
    )
    parser.add_argument(
        "--git-level",
        default="tags",
        choices=("tags", "releases", "merges", "commits"),
        help="Phase 3 granularity (default: tags — cheapest).",
    )
    parser.add_argument(
        "--git-branch",
        default=None,
        help="Branch-first mode (Phase 3): scope to this branch.",
    )
    parser.add_argument(
        "--git-base",
        default="main",
        help="Phase 3 branch_base (default main; use 'master' for legacy repos).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="cProfile top N entries to print (default 25).",
    )
    parser.add_argument(
        "--project-slug",
        default="alpha",
        help=(
            "Project slug used by stack/git phases (must exist in the tmp "
            "vault skeleton — defaults to 'alpha' which is created by the "
            "fixture). Phase 2 + 3 write atoms under this slug."
        ),
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        print(f"error: --repo not a directory: {repo}", file=sys.stderr)
        return 2

    tmp_root, vault = _bootstrap_tmp_vault()
    sys.path.insert(0, str(MCP_SRC))

    # Reset config cache so MEMORY_KIT_HOME is picked up by future imports.
    from memory_kit_mcp.config import get_config

    get_config.cache_clear()

    print(f"repo:  {repo}")
    print(f"vault: {vault} (tmp)")
    print(f"only:  {args.only}")

    timings: dict[str, float] = {}
    topology = None

    try:
        if args.only in ("topology", "all"):
            from memory_kit_mcp.vault.topology_scanner import scan

            elapsed, topology = _profile_phase(
                "Phase 0 — topology_scanner.scan()",
                lambda: scan(repo, vault=vault),
            )
            timings["topology"] = elapsed

        if args.only in ("stack", "all") and not args.skip_stack:
            from memory_kit_mcp.tools.archeo_stack import execute_stack

            if topology is None:
                from memory_kit_mcp.vault.topology_scanner import scan

                topology = scan(repo, vault=vault)
            elapsed, _ = _profile_phase(
                "Phase 2 — execute_stack()",
                lambda: execute_stack(
                    vault, repo, project=args.project_slug, topology=topology
                ),
            )
            timings["stack"] = elapsed

        if args.only in ("git", "all") and not args.skip_git:
            from memory_kit_mcp.tools.archeo_git import execute_git

            label_parts = [f"level={args.git_level}"]
            if args.git_branch:
                label_parts.append(f"branch={args.git_branch}")
            label = "Phase 3 — execute_git(" + ", ".join(label_parts) + ")"
            elapsed, _ = _profile_phase(
                label,
                lambda: execute_git(
                    vault,
                    repo,
                    project=args.project_slug,
                    level=args.git_level,
                    branch_first=args.git_branch,
                    branch_base=args.git_base,
                    skip_repo_validation=True,
                ),
            )
            timings["git"] = elapsed

        # Final wall-clock summary so the user has a quick comparison view.
        _print_section("Wall-clock summary")
        for phase, elapsed in timings.items():
            print(f"  {phase:<12} {elapsed:>7.3f} s")
        if timings:
            total = sum(timings.values())
            print(f"  {'TOTAL':<12} {total:>7.3f} s")
    finally:
        # Aggressive cleanup so the script leaves no stray temp files behind
        # even on long IRIS-sized profiles.
        shutil.rmtree(tmp_root, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
