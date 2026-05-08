"""Phase 0 — shell-delegated file enumeration for archeo v2.

See ``core/procedures/_archeo-architecture-v2.md`` for the full doctrine.

This module provides ``enumerate_files()``, the canonical entry point that
returns a deterministic, scope-bounded list of repo-relative file paths
ready for Phase 1/2/3 consumption — without running any Python recursive
scan that could time out an MCP client.

Two modes, auto-detected by the presence of ``.git/``:

- ``git``: subprocess to ``git ls-files`` / ``git diff`` / ``git log``
  (gitignore-aware, fast, deterministic).
- ``raw``: stdlib ``os.walk`` filtered by a hard ignore-list (no external
  binary required).

Both modes return ``list[PurePosixPath]`` (POSIX paths, even on Windows)
plus a ``files_hash`` SHA-256 of the sorted list, used by downstream
phases to detect drift between Phase 0 and the moment they read the
snapshot.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Hard ignore-list applied in raw mode (and as a safety net even in git mode
# for files Git might track but the user almost certainly does not want to
# analyse — e.g. minified bundles checked in by mistake).
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        "coverage",
        "htmlcov",
        ".nyc_output",
        ".cache",
        ".gradle",
        ".terraform",
    }
)

DEFAULT_IGNORE_SUFFIXES: tuple[str, ...] = (
    ".pyc",
    ".pyo",
    ".class",
    ".o",
    ".obj",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".min.js",
    ".min.css",
    ".map",
)

SOFT_CAP_FILES_DEFAULT: int = 500
SOFT_CAP_BYTES_DEFAULT: int = 50 * 1024 * 1024  # 50 MiB
BATCH_SIZE_DEFAULT: int = 200

# Pass B safety net — never read more than this many files for import scan,
# and never read more than this many bytes per file (imports are at the top).
# Both can be raised explicitly via parameters; defaults protect against
# accidental wholesale I/O on a large monolithic repo.
PASS_B_MAX_FILES_DEFAULT: int = 200
PASS_B_READ_BYTES_DEFAULT: int = 16 * 1024  # 16 KiB

# Suffixes Pass B actually scans. Anything else is skipped without I/O.
_PASS_B_SCANNED_SUFFIXES: frozenset[str] = frozenset(
    {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ScopeOverflowError(RuntimeError):
    """Raised when ``hard_abort=True`` and the scope exceeds soft caps."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class EnumerateResult:
    """Output of :func:`enumerate_files`."""

    files: list[PurePosixPath]
    files_count: int
    files_bytes: int
    files_hash: str  # sha256 of sorted file list (one per line, LF-joined)
    batches: list[list[PurePosixPath]]
    source_mode: Literal["git", "raw"]
    scope_glob: str | None = None
    branch: str | None = None
    base_ref: str | None = None
    merge_base_strategy: str | None = None
    pass_b_files: list[PurePosixPath] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Step-by-step trace of what enumerate_files did. Constant size (~10-15
    # lines, never per-file) so it costs nothing in the structured payload
    # but lets the LLM see decisions without diving into MCP server stderr.
    trace: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------


def detect_mode(repo_path: Path) -> Literal["git", "raw"]:
    """Return ``'git'`` if ``.git/`` exists at the repo root, else ``'raw'``."""
    return "git" if (repo_path / ".git").exists() else "raw"


# ---------------------------------------------------------------------------
# Git mode
# ---------------------------------------------------------------------------


def _run_git(args: list[str], cwd: Path) -> list[str]:
    """Run ``git <args>`` in ``cwd`` and return non-empty stdout lines.

    Raises ``RuntimeError`` on non-zero exit so callers can surface the
    underlying git error to the user instead of silently degrading.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}): "
            f"{result.stderr.strip() or '(no stderr)'}"
        )
    return [ln for ln in result.stdout.splitlines() if ln.strip()]


def _git_branch_files(
    repo_path: Path,
    branch: str,
    base_ref: str,
    trace: list[str] | None = None,
) -> list[PurePosixPath]:
    """Pass A — files modified on ``branch`` relative to ``base_ref``.

    Union of ``git diff --name-only base..branch`` and
    ``git log --name-only --pretty="" base..branch``. Captures both
    currently-different files and files touched by intermediate commits
    (including those later removed or rewritten via squash).
    """
    rev_range = f"{base_ref}..{branch}"
    diff_files = _run_git(["diff", "--name-only", rev_range], repo_path)
    log_files = _run_git(
        ["log", "--name-only", "--pretty=", rev_range], repo_path
    )
    union = sorted(set(diff_files) | set(log_files))
    if trace is not None:
        trace.append(
            f"[git] Pass A {rev_range}: diff={len(diff_files)}, "
            f"log={len(log_files)}, union={len(union)}"
        )
    return [PurePosixPath(f) for f in union]


def _git_ls_files(
    repo_path: Path, trace: list[str] | None = None
) -> list[PurePosixPath]:
    """Full inventory via ``git ls-files`` (gitignore-aware, sorted)."""
    out = _run_git(["ls-files"], repo_path)
    if trace is not None:
        trace.append(f"[git] git ls-files -> {len(out)} file(s)")
    return [PurePosixPath(f) for f in sorted(out)]


class BranchScopeUnresolvedError(RuntimeError):
    """Raised when a branch is fully merged into ``fallback_base`` and the
    caller didn't provide an explicit ``base_ref``.

    Replaces the v0.10.0 ``first-parent-fallback`` strategy that silently
    dove into the base branch's history (often 1000+ irrelevant commits —
    case study: ``ecosav`` on the IRIS USER repo). The caller is now
    expected to provide a meaningful anchor or scope themselves; the
    enumeration library will not invent one.

    See ``core/procedures/_archeo-architecture-v2.md`` Principe 2 amendment.
    """


def _git_resolve_base_ref(
    repo_path: Path,
    branch: str,
    fallback_base: str = "main",
    trace: list[str] | None = None,
) -> tuple[str, str]:
    """Resolve a base ref for ``branch`` via merge-base only.

    Returns ``(base_sha, strategy)`` where ``strategy`` is ``"merge-base"``.

    Raises :class:`BranchScopeUnresolvedError` when the branch is fully
    merged into ``fallback_base`` (``merge_base == HEAD(branch)``). The
    previous v0.10.0 fallbacks (``first-parent-fallback``,
    ``empty-tree-fallback``) used to silently dive into the base branch's
    history at this point — sometimes 1000+ commits, almost never the
    scope the user wanted. The Codex case study on ``ecosav`` made the
    pattern visible enough to retire it. Higher-level callers
    (``mem_archeo_git`` / ``mem_archeo_index_files``) now hold the
    branch-name heuristic + by-files fallback policy and decide what to
    do with a fully-merged branch.

    Hint surfacing: when ``fallback_base`` doesn't resolve at all (typo,
    or the default branch is ``master`` not ``main``), the error lists
    the local branches so the caller can fix their invocation.
    """
    try:
        merge_base = _run_git(
            ["merge-base", fallback_base, branch], repo_path
        )[0]
    except (RuntimeError, IndexError) as exc:
        try:
            branches = _run_git(["branch", "--list"], repo_path)
            local_names = [b.lstrip("* ").strip() for b in branches]
        except RuntimeError:
            local_names = []
        hint = ""
        if fallback_base not in local_names and local_names:
            hint = (
                f" Hint: '{fallback_base}' is not in local branches "
                f"({', '.join(local_names[:8])}"
                f"{'…' if len(local_names) > 8 else ''}). "
                f"Pass fallback_base='master' (or the actual default) "
                f"if your repo's default branch differs."
            )
        raise RuntimeError(
            f"Cannot resolve merge-base of '{fallback_base}' and '{branch}': "
            f"{exc}{hint}"
        ) from exc

    branch_head = _run_git(["rev-parse", branch], repo_path)[0]
    if merge_base != branch_head:
        if trace is not None:
            trace.append(
                f"[git] merge-base {fallback_base}..{branch} -> "
                f"{merge_base[:12]} (strategy: merge-base)"
            )
        return merge_base, "merge-base"

    # Fully merged branch: refuse to invent a fallback. The retired
    # first-parent strategy used to return the commit before the branch's
    # tip here, but on absorbed long-lived branches that commit lives in
    # the base's history and produces sloppy archeo scopes. The caller
    # must provide ``base_ref`` (or a higher-level layer must apply the
    # by-files / by-name heuristic).
    if trace is not None:
        trace.append(
            f"[git] branch '{branch}' fully merged into '{fallback_base}' "
            "(merge-base == HEAD); no fallback attempted"
        )
    raise BranchScopeUnresolvedError(
        f"branch '{branch}' is fully merged into '{fallback_base}' "
        f"(merge-base == HEAD(branch)). Provide an explicit base_ref to "
        f"anchor the scope, or use a higher-level tool (mem_archeo_git) "
        f"that applies by-files / by-name heuristics. "
        f"No first-parent or empty-tree fallback is attempted (retired "
        f"v0.10.x post-Codex case study — produced sloppy scopes diving "
        f"into the base branch history)."
    )


# ---------------------------------------------------------------------------
# Raw mode
# ---------------------------------------------------------------------------


def _raw_walk_files(
    repo_path: Path, trace: list[str] | None = None
) -> list[PurePosixPath]:
    """Recursive enumeration via ``os.walk`` with hard ignore-list."""
    out: list[PurePosixPath] = []
    pruned_dir_count = 0
    for root, dirs, files in os.walk(repo_path):
        # In-place mutation prunes recursion under ignored dirs.
        original_dirs = list(dirs)
        dirs[:] = sorted(d for d in dirs if d not in DEFAULT_IGNORE_DIRS)
        pruned_dir_count += len(original_dirs) - len(dirs)
        for fname in sorted(files):
            if fname.endswith(DEFAULT_IGNORE_SUFFIXES):
                continue
            full = Path(root) / fname
            try:
                rel = full.relative_to(repo_path)
            except ValueError:
                continue
            out.append(PurePosixPath(rel.as_posix()))
    sorted_out = sorted(out)
    if trace is not None:
        trace.append(
            f"[raw] os.walk -> {len(sorted_out)} file(s) "
            f"({pruned_dir_count} dir(s) pruned by default ignore-list)"
        )
    return sorted_out


# ---------------------------------------------------------------------------
# Pass B — language-aware import resolution (best effort)
# ---------------------------------------------------------------------------

_PY_IMPORT_RE = re.compile(
    r"""^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))""",
    re.MULTILINE,
)
_JS_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*(?:"""
    r"""import\s+[^;\n]*?\s+from\s+['"]([^'"]+)['"]"""
    r"""|"""
    r"""(?:const|let|var)\s+[^=]+=\s*require\(\s*['"]([^'"]+)['"]\s*\)"""
    r""")"""
)


def _resolve_python_module(
    repo_path: Path, importer: PurePosixPath, module: str
) -> PurePosixPath | None:
    """Best-effort resolution of a Python module name to a repo file."""
    parts = module.split(".")
    candidates: list[PurePosixPath] = []
    # Anchors: repo root, ``src/``, parent dir of importer.
    anchors: list[PurePosixPath] = [PurePosixPath()]
    importer_parent = importer.parent
    if importer_parent.parts:
        anchors.append(importer_parent)
    if (repo_path / "src").is_dir():
        anchors.append(PurePosixPath("src"))

    for anchor in anchors:
        candidates.append(anchor / "/".join(parts) / "__init__.py")
        candidates.append(anchor / ("/".join(parts) + ".py"))

    for c in candidates:
        full = repo_path / str(c)
        if full.is_file():
            return c
    return None


def _resolve_js_module(
    repo_path: Path, importer: PurePosixPath, spec: str
) -> PurePosixPath | None:
    """Best-effort resolution of a JS/TS module specifier."""
    if not spec.startswith((".", "/")):
        return None  # bare specifier — likely a package, ignore
    base = importer.parent / spec
    extensions = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
    for ext in extensions:
        candidate = PurePosixPath(str(base) + ext)
        if (repo_path / str(candidate)).is_file():
            return candidate
    # Try as directory with index file.
    for index_name in ("index.ts", "index.tsx", "index.js", "index.jsx"):
        candidate = base / index_name
        if (repo_path / str(candidate)).is_file():
            return candidate
    return None


def _read_head(path: Path, max_bytes: int) -> str | None:
    """Read at most ``max_bytes`` from the start of ``path``. Imports live at
    the top of source files — reading the head is enough and avoids wholesale
    I/O on large vendored bundles.
    """
    try:
        with path.open("rb") as fh:
            chunk = fh.read(max_bytes)
        return chunk.decode("utf-8", errors="ignore")
    except OSError:
        return None


def _compute_pass_b(
    files: list[PurePosixPath],
    repo_path: Path,
    *,
    max_files: int = PASS_B_MAX_FILES_DEFAULT,
    read_bytes: int = PASS_B_READ_BYTES_DEFAULT,
    trace: list[str] | None = None,
) -> tuple[list[PurePosixPath], list[str]]:
    """Scan Pass A files for imports and return additional repo-local files.

    Best-effort — silently drops imports that don't resolve to a repo-local
    file (almost always external dependencies). Pass A files are excluded
    from the result so the caller can simply union both lists if desired.

    Performance contract:

    1. Files whose suffix is not a known Pass B language are skipped
       **without I/O** (no ``stat``, no ``read``).
    2. Of the remaining candidates, at most ``max_files`` are actually
       scanned. If more match, the extras are skipped and an
       ``info`` warning is returned to the caller.
    3. Each scanned file reads only the first ``read_bytes`` (default 16 KiB)
       — imports are always at the top.

    Returns ``(discovered_files, warnings)``.
    """
    pass_a = set(files)
    discovered: set[PurePosixPath] = set()
    warnings: list[str] = []

    # Cheap pre-filter — pure path inspection, no syscalls.
    candidates = [f for f in files if f.suffix.lower() in _PASS_B_SCANNED_SUFFIXES]
    skipped_unscanned = len(files) - len(candidates)
    if trace is not None:
        trace.append(
            f"[pass-b] {len(candidates)} candidate(s) in scanned languages, "
            f"{skipped_unscanned} skipped without I/O"
        )

    truncated = False
    if max_files > 0 and len(candidates) > max_files:
        warnings.append(
            f"Pass B truncated: {len(candidates)} candidate file(s) matched a "
            f"scanned language but only the first {max_files} were read "
            f"(max_pass_b_files={max_files}). Tighten scope_glob or raise "
            f"max_pass_b_files explicitly."
        )
        candidates = candidates[:max_files]
        truncated = True

    for f in candidates:
        full = repo_path / str(f)
        if not full.is_file():
            continue
        content = _read_head(full, read_bytes)
        if content is None:
            continue

        suffix = full.suffix.lower()
        if suffix == ".py":
            for m in _PY_IMPORT_RE.finditer(content):
                module = m.group(1) or m.group(2)
                if not module:
                    continue
                resolved = _resolve_python_module(repo_path, f, module)
                if resolved and resolved not in pass_a:
                    discovered.add(resolved)
        else:  # js / jsx / ts / tsx / mjs / cjs (already filtered).
            for m in _JS_IMPORT_RE.finditer(content):
                spec = m.group(1) or m.group(2)
                if not spec:
                    continue
                resolved = _resolve_js_module(repo_path, f, spec)
                if resolved and resolved not in pass_a:
                    discovered.add(resolved)

    sorted_discovered = sorted(discovered)
    if trace is not None:
        trace.append(
            f"[pass-b] read {len(candidates)} file(s) "
            f"(head_bytes={read_bytes}, truncated={truncated}); "
            f"resolved {len(sorted_discovered)} repo-local import(s)"
        )
    return sorted_discovered, warnings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_scope(
    files: list[PurePosixPath], scope_glob: str | None
) -> list[PurePosixPath]:
    if not scope_glob:
        return files
    return [f for f in files if fnmatch.fnmatch(str(f), scope_glob)]


def _apply_default_ignore(
    files: list[PurePosixPath],
) -> list[PurePosixPath]:
    """Belt-and-braces filter even in git mode — drop ignored dirs & suffixes."""
    out: list[PurePosixPath] = []
    for f in files:
        parts = set(f.parts)
        if parts & DEFAULT_IGNORE_DIRS:
            continue
        if str(f).endswith(DEFAULT_IGNORE_SUFFIXES):
            continue
        out.append(f)
    return out


def _compute_files_hash(files: list[PurePosixPath]) -> str:
    h = hashlib.sha256()
    for f in files:
        h.update(str(f).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _compute_total_bytes(
    files: list[PurePosixPath], repo_path: Path
) -> int:
    total = 0
    for f in files:
        try:
            total += (repo_path / str(f)).stat().st_size
        except OSError:
            pass
    return total


def _build_batches(
    files: list[PurePosixPath], batch_size: int
) -> list[list[PurePosixPath]]:
    if not files:
        return [[]]
    return [files[i : i + batch_size] for i in range(0, len(files), batch_size)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enumerate_files(
    repo_path: Path | str,
    *,
    mode: Literal["auto", "git", "raw"] = "auto",
    scope_glob: str | None = None,
    branch: str | None = None,
    base_ref: str | None = None,
    fallback_base: str = "main",
    pass_b: bool = False,
    max_files: int | None = None,
    max_bytes: int | None = None,
    batch_size: int | None = None,
    hard_abort: bool = False,
    max_pass_b_files: int | None = None,
    pass_b_read_bytes: int | None = None,
) -> EnumerateResult:
    """Enumerate files for archeo Phase 0.

    Args:
        repo_path: Repo root.
        mode: ``'auto'`` (detect by ``.git/``), ``'git'``, or ``'raw'``.
        scope_glob: Optional fnmatch-style glob applied after enumeration.
        branch: When in git mode, restrict to Pass A files of this branch.
            Ignored in raw mode (added to ``warnings`` if both set).
        base_ref: Optional explicit base SHA / ref for branch-first.
            Resolved automatically (merge-base + first-parent fallback)
            when ``branch`` is set and ``base_ref`` is None.
        fallback_base: Default base branch for merge-base resolution.
        pass_b: If True, also resolve repo-local imports of Pass A files
            (best-effort, Python + JS/TS regex-based).
        max_files: Soft cap on file count. None = default 500. 0 = no cap.
        max_bytes: Soft cap on cumulative bytes. None = default 50 MiB.
            0 = no cap.
        batch_size: Suggested batch size for downstream consumers.
            None = default 200.
        hard_abort: If True, raise ``ScopeOverflowError`` instead of warning
            when caps are exceeded.
        max_pass_b_files: Cap on the number of files actually read for
            Pass B import scan. None = default 200. 0 = no cap. Files
            beyond the cap are skipped with an explicit warning. Note that
            files whose suffix is not a Pass B language are filtered
            **before** this cap and never count.
        pass_b_read_bytes: Bytes to read from the head of each Pass B file
            (imports live at the top). None = default 16 KiB. 0 reads the
            full file (legacy behaviour, not recommended on large repos).

    Returns:
        :class:`EnumerateResult`.

    Raises:
        FileNotFoundError: ``repo_path`` does not exist or is not a directory.
        ValueError: Conflicting parameters (e.g. invalid ``mode``).
        ScopeOverflowError: Caps exceeded and ``hard_abort=True``.
        RuntimeError: Underlying ``git`` command failed (git mode).
    """
    repo_path = Path(repo_path).expanduser().resolve()
    if not repo_path.is_dir():
        raise FileNotFoundError(f"repo_path not a directory: {repo_path}")

    if mode not in ("auto", "git", "raw"):
        raise ValueError(f"mode must be 'auto'|'git'|'raw', got {mode!r}")

    trace: list[str] = []
    trace.append(f"[start] repo={repo_path}")

    actual_mode: Literal["git", "raw"]
    if mode == "auto":
        actual_mode = detect_mode(repo_path)
        trace.append(
            f"[mode] auto-detected: {actual_mode} "
            f"({'.git/ present' if actual_mode == 'git' else 'no .git/'})"
        )
    else:
        actual_mode = mode
        trace.append(f"[mode] forced: {actual_mode}")

    warnings: list[str] = []
    branch_recorded: str | None = None
    base_ref_recorded: str | None = None
    strategy_recorded: str | None = None

    if actual_mode == "git":
        if branch:
            if base_ref is None:
                trace.append(
                    f"[git] resolving base_ref for branch={branch!r} "
                    f"(fallback_base={fallback_base!r})"
                )
                base_ref_recorded, strategy_recorded = _git_resolve_base_ref(
                    repo_path, branch, fallback_base=fallback_base, trace=trace
                )
            else:
                base_ref_recorded = base_ref
                strategy_recorded = "manual"
                trace.append(
                    f"[git] base_ref provided manually: {base_ref[:12]}"
                )
            files = _git_branch_files(
                repo_path, branch, base_ref_recorded, trace=trace
            )
            branch_recorded = branch
        else:
            files = _git_ls_files(repo_path, trace=trace)
    else:
        if branch:
            warnings.append(
                f"branch={branch!r} ignored in raw mode (no Git available)"
            )
            trace.append(
                f"[raw] branch={branch!r} ignored (no .git/ directory)"
            )
        files = _raw_walk_files(repo_path, trace=trace)

    before_ignore = len(files)
    files = _apply_default_ignore(files)
    after_ignore = len(files)
    if before_ignore != after_ignore:
        trace.append(
            f"[ignore] default ignore-list dropped "
            f"{before_ignore - after_ignore} file(s) ({before_ignore} -> {after_ignore})"
        )
    if scope_glob:
        before_scope = len(files)
        files = _apply_scope(files, scope_glob)
        trace.append(
            f"[scope] glob={scope_glob!r}: {before_scope} -> {len(files)} file(s)"
        )

    files_count = len(files)
    files_bytes = _compute_total_bytes(files, repo_path)
    trace.append(
        f"[stats] {files_count} file(s), {files_bytes // 1024} KiB total"
    )

    cap_files = SOFT_CAP_FILES_DEFAULT if max_files is None else max_files
    cap_bytes = SOFT_CAP_BYTES_DEFAULT if max_bytes is None else max_bytes
    bs = BATCH_SIZE_DEFAULT if batch_size is None else max(1, batch_size)

    overflow_files = cap_files > 0 and files_count > cap_files
    overflow_bytes = cap_bytes > 0 and files_bytes > cap_bytes
    if overflow_files or overflow_bytes:
        msg = (
            f"ScopeOverflowWarning: {files_count} files / "
            f"{files_bytes // (1024 * 1024)} MiB matched "
            f"(soft cap: {cap_files} / {cap_bytes // (1024 * 1024)} MiB). "
            f"Continuing without truncation. Recommended next step: split "
            f"into batches of <batch_size={bs}> via mem_archeo_index_files "
            f"+ per-batch mem_archeo_context calls."
        )
        if hard_abort:
            trace.append(
                f"[caps] OVER cap and hard_abort=True -> ScopeOverflowError"
            )
            raise ScopeOverflowError(
                msg.replace("ScopeOverflowWarning", "ScopeOverflowError")
                + " (hard_abort=True)"
            )
        warnings.append(msg)
        trace.append(
            f"[caps] OVER soft cap "
            f"(files={files_count}/{cap_files}, "
            f"bytes={files_bytes // (1024 * 1024)}/{cap_bytes // (1024 * 1024)} MiB) "
            f"— warning emitted, list intact"
        )
    else:
        trace.append(
            f"[caps] under soft cap "
            f"({files_count}/{cap_files} files, "
            f"{files_bytes // (1024 * 1024)}/{cap_bytes // (1024 * 1024)} MiB)"
        )

    files_hash = _compute_files_hash(files)
    trace.append(f"[hash] files_hash={files_hash[:12]}…")

    batches = _build_batches(files, bs)
    trace.append(f"[batches] {len(batches)} batch(es) of size {bs}")

    pass_b_files: list[PurePosixPath] = []
    if pass_b:
        pb_max = (
            PASS_B_MAX_FILES_DEFAULT
            if max_pass_b_files is None
            else max_pass_b_files
        )
        pb_read = (
            PASS_B_READ_BYTES_DEFAULT
            if pass_b_read_bytes is None
            else pass_b_read_bytes
        )
        pass_b_files, pass_b_warnings = _compute_pass_b(
            files,
            repo_path,
            max_files=pb_max,
            read_bytes=pb_read if pb_read > 0 else 1_000_000_000,
            trace=trace,
        )
        warnings.extend(pass_b_warnings)
    else:
        trace.append("[pass-b] disabled (pass_b=False)")

    trace.append(
        f"[done] files={files_count}, batches={len(batches)}, "
        f"warnings={len(warnings)}, pass_b={len(pass_b_files)}"
    )

    return EnumerateResult(
        files=files,
        files_count=files_count,
        files_bytes=files_bytes,
        files_hash=files_hash,
        batches=batches,
        source_mode=actual_mode,
        scope_glob=scope_glob,
        branch=branch_recorded,
        base_ref=base_ref_recorded,
        merge_base_strategy=strategy_recorded,
        pass_b_files=pass_b_files,
        warnings=warnings,
        trace=trace,
    )
