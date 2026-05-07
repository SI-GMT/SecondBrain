# Procedure: Archeo Index Files (v0.10.x — Phase 0 archeo v2)

Goal: enumerate the file list (and pre-computed batches) that Phase 1/2/3 of an archeo would consume for a given repo + scope, **without writing the vault** and **without launching the heavier phases**. Read-only preview.

This procedure implements the Phase 0 contract of the archeo v2 architecture. See the binding doctrine `_archeo-architecture-v2.md` for the full rationale (shell-delegated enumeration, deterministic branch-first, scope-tight + batch).

## Trigger

The user types `/mem-archeo-index-files` or expresses the intent in natural language: "list the files an archeo would touch", "preview the scope of an archeo on X", "how many files would mem-archeo work on for repo Y", "give me the batches before I launch a real archeo".

Arguments:

- `project`: project slug for the summary header (no vault write — the slug is informational).
- `repo_path`: absolute path to the repo to enumerate.
- `mode`: `'auto'` (default — detect by `.git/`), `'git'`, or `'raw'`.
- `scope_glob`: optional fnmatch-style glob applied after enumeration (e.g. `'src/api/**'`).
- `branch`: branch-first mode (git only). Restrict to Pass A files of this branch. Ignored in raw mode (a warning is added to `warnings`).
- `base_ref`: explicit base SHA / ref for branch-first. Auto-resolved (merge-base + first-parent fallback) when `branch` is set and `base_ref` is None.
- `fallback_base`: default branch for merge-base resolution (default `main`).
- `pass_b`: if True, resolve repo-local imports of Pass A files (Python + JS/TS, best effort regex). Off by default — heavier.
- `max_files`: soft cap on file count. None = default 500. 0 = no cap.
- `max_bytes`: soft cap on cumulative bytes. None = default 50 MiB. 0 = no cap.
- `batch_size`: suggested batch size for downstream consumers. None = default 200.
- `hard_abort`: if True, raise `ScopeOverflowError` instead of warning when caps are exceeded.
- `max_pass_b_files`: cap on the number of Pass B candidate files actually opened. None = default 200. 0 = no cap. Files of unscanned languages are filtered **before** this cap and never count against it.
- `pass_b_read_bytes`: bytes read from the head of each Pass B file (imports always live at the top). None = default 16 KiB. 0 reads the full file (legacy, not recommended).

## Procedure

### 1. Resolve the repo path

Expand and resolve `repo_path` to an absolute filesystem path. Refuse if the path does not exist or is not a directory (`FileNotFoundError`).

### 2. Detect the enumeration mode

If `mode == 'auto'`: return `'git'` when `(repo_path / '.git').exists()`, otherwise `'raw'`. Explicit `'git'` or `'raw'` overrides detection.

### 3. Enumerate (mode `git`)

Two cases depending on `branch`:

- **Without `branch`** — full inventory:
  - `git ls-files` (run with `cwd=repo_path`).
  - Output is gitignore-aware, naturally sorted by Git, decomposed into a list of `PurePosixPath`.

- **With `branch`** — Pass A:
  - If `base_ref` is None, resolve it via:
    1. `git merge-base {fallback_base} {branch}` — primary attempt.
    2. If `merge_base == HEAD(branch)` (fully merged branch), use `git rev-list --first-parent --max-parents=1 -n 1 {branch}~1` (first-parent fallback).
    3. If neither yields a parent (single-commit branch), fall back to the empty-tree SHA `4b825dc642cb6eb9a060e54bf8d69288fbee4904`.
  - Capture the strategy used (`merge-base`, `first-parent-fallback`, `empty-tree-fallback`, or `manual` if `base_ref` was provided).
  - `git diff --name-only {base_ref}..{branch}` — fichiers actuellement différents.
  - `git log --name-only --pretty="" {base_ref}..{branch}` — fichiers touchés par tout commit unique à la branche.
  - Pass A = sorted union of both outputs.

Any non-zero git exit raises `RuntimeError` with the exact stderr — surface it to the LLM rather than silently degrading.

### 4. Enumerate (mode `raw`)

- `os.walk(repo_path)` with **in-place** pruning of subdirectories matching `DEFAULT_IGNORE_DIRS` (canonical list — see doctrine).
- Skip files with extensions in `DEFAULT_IGNORE_SUFFIXES`.
- Convert each path to repo-relative `PurePosixPath` via `Path.relative_to(repo_path).as_posix()`.
- Sort the final list deterministically.

If `branch` is set in raw mode, ignore it and add a warning to the result: `"branch=<value> ignored in raw mode (no Git available)"`.

### 5. Apply ignore-list and scope

Even in git mode, apply `DEFAULT_IGNORE_DIRS` / `DEFAULT_IGNORE_SUFFIXES` as a safety net (catches files Git might track but the user almost never wants to analyse — minified bundles, compiled artifacts checked in by mistake).

Then apply `scope_glob` via `fnmatch.fnmatch(str(path), glob)` if provided.

### 6. Compute statistics

- `files_count = len(files)`.
- `files_bytes = sum(stat(repo / f).st_size for f in files)` — silently swallow `OSError` on individual files (broken symlink, race with deletion).
- `files_hash = sha256(LF-joined sorted file list)` — used by downstream phases to detect drift between Phase 0 and the moment they read the snapshot.

### 7. Apply soft caps

Resolve effective caps:

- `cap_files = max_files if max_files is not None else 500` (0 disables).
- `cap_bytes = max_bytes if max_bytes is not None else 50 * 1024 * 1024` (0 disables).
- `bs = batch_size if batch_size is not None else 200` (clamped to >= 1).

If `files_count > cap_files` (and `cap_files > 0`) OR `files_bytes > cap_bytes` (and `cap_bytes > 0`):

- Build the message:

  ```
  ScopeOverflowWarning: <N> files / <M> MiB matched
  (soft cap: <cap_files> / <cap_bytes_mib> MiB).
  Continuing without truncation. Recommended next step: split into batches
  of <batch_size=<bs>> via mem_archeo_index_files + per-batch
  mem_archeo_context calls.
  ```

- If `hard_abort=True`: raise `ScopeOverflowError` with the message (replacing `Warning` by `Error`).
- Otherwise: append the message to `warnings`. **Never truncate the file list silently.**

### 8. Build batches

`batches = [files[i:i+bs] for i in range(0, len(files), bs)]`, with the empty-list guard `[[]]` when `files` is empty. Always at least one batch so the consumer has a uniform contract.

### 9. Pass B (optional, opt-in)

If `pass_b=True`:

- **Pre-filter without I/O**: skip every file whose suffix is not in `{.py, .js, .jsx, .ts, .tsx, .mjs, .cjs}`. No `stat`, no `read`. Critical for monorepos with thousands of non-Pass-B files (ObjectScript `.cls`, Java `.class`, etc.).
- **Cap candidates**: if more than `max_pass_b_files` (default 200) remain after pre-filtering, keep only the first N (deterministic by sort order) and emit a warning `Pass B truncated: <N> candidate file(s)…`. The user can raise the cap explicitly or tighten `scope_glob`.
- **Read only the head**: for each retained candidate, read the first `pass_b_read_bytes` (default 16 KiB) — imports always live at the top of source files. This bounds the I/O cost per file regardless of file size.
- For each `.py` file: regex-scan for `^\s*(?:from\s+(\S+)\s+import|import\s+(\S+))` and resolve each module name to a repo-local file via the candidate anchors (repo root, `src/`, importer's parent dir) — best effort, drop unresolved.
- For each `.js` / `.jsx` / `.ts` / `.tsx` / `.mjs` / `.cjs` file: regex-scan for `import … from '…'` and `require('…')`. Resolve `./` and `/`-prefixed specifiers via candidate extensions (`.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`) and `index.*` files. Drop bare specifiers (external packages).
- Pass A files are excluded from the result — the caller can union both lists if desired.

Pass B is intentionally minimal (no AST, no resolver framework) — it provides a useful starting point for downstream batch decisions without pulling heavy dependencies. The performance contract above (suffix pre-filter, cap, head-only read) is **mandatory** to keep Pass B viable on large monolithic repos.

### 10. Return

`ArcheoIndexResult` with:

- `project`, `repo_path` (string), `source_mode` (`'git'` | `'raw'`).
- `scope_glob`, `branch`, `base_ref`, `merge_base_strategy` (all optional, populated when relevant).
- `files: list[str]` (POSIX-relative).
- `files_count`, `files_bytes`, `files_hash`.
- `batches: list[list[str]]`.
- `pass_b_files: list[str]` (empty if `pass_b=False`).
- `warnings: list[str]`.
- `trace: list[str]` — step-by-step trace of what enumerate_files did (mode detection, git commands, scope filtering, caps, hash, batches, Pass B). Constant size (~10-15 lines, never per-file). Lets the LLM see decisions without diving into MCP server stderr logs. Always populated.
- `summary_md`: human-readable Markdown summary (includes a fenced trace section).

The structured payload is the canonical contract — the Markdown summary is for direct LLM display.

## Side channel: standalone CLI

The same enumeration is available outside the MCP server via:

```
python -m memory_kit_mcp.archeo_topology --repo <path> [--branch <name>] [--scope-glob <glob>] [--mode auto|git|raw] [--pass-b] [--max-files N] [--max-bytes N] [--batch-size N] [--hard-abort] [--format md|json] [--out <file>]
```

Or via the installed entry-point `archeo-topology --repo …`. Useful for:

- CI/CD pipelines that want to generate a topology snapshot without an MCP server.
- Test harnesses isolating Phase 0.
- Working around per-tool MCP timeouts on large repos (output redirected to a file, the LLM reads it via `Read`).

## What this procedure does NOT do

- Does **not** write to the vault. Use `mem_attach_topology` (cap suivant once shipped) to persist a snapshot atom.
- Does **not** run Phase 1 (semantic context), Phase 2 (stack), or Phase 3 (git history). Those phases consume the file list produced here.
- Does **not** open the file contents (except for Pass B regex scan). Pure enumeration + metadata.
- Does **not** mutate the repo. Read-only on both git and filesystem.
