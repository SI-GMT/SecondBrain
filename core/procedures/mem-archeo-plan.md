# Procedure: Archeo Plan (v0.10.x — Phase 0 interactive cadrage)

Goal: build a structured plan of what an archeo run *would* do given the current repo + branch + vault state, **without writing the vault** and **without firing any subprocess git for archive writing**. The plan is then surfaced to the user for explicit validation before `mem_archeo_git` is invoked.

This procedure is the doctrinal answer to the macro-drift class that frontmatter validation alone cannot prevent (case study: Gemini 2026-05-08 producing 73 mechanical archives under wrong slug `user-prod-iris`, granularity `--by-author --window=week` chosen silently, `--branch-first` not even passed → archeo of `master` history instead of the `ecosav` branch). See the binding doctrine in `mem-archeo-git.md` Phase 0.

## Trigger

The user types `/mem-archeo-plan` or expresses the intent in natural language: "what would mem-archeo do on this branch?", "preview the archeo plan for branch X", "I want to see the slug + granularity it would pick before running it for real".

The procedure is also invoked automatically from `mem-archeo-git.md` Phase 0 — the LLM caller MUST run this before any branch-first archeo write.

Arguments:

- `repo_path`: absolute path to the local Git repository.
- `branch` (optional): branch to plan archeo for. Defaults to current `HEAD` branch.
- `branch_base` (optional): base branch for divergence detection. Default = auto-detected via `git symbolic-ref refs/remotes/origin/HEAD`, then probing `main` / `master` / `develop`, then fallback `main`.
- `project` (optional): force the project slug. Use only when you know the slug should NOT match the branch name. Skips the slug heuristic entirely.

## Procedure

### 1. Capture user identity (anchor for self-vs-team filter)

Read `git config --get user.email` and `git config --get user.name` from the **target repo** (not the global config — repo override may differ for the user's professional / personal contexts). Empty strings when unset. The captured identity is the anchor Phase 3 uses for the `author_self_only` filter.

### 2. Resolve branch + base + commits range

Default `branch` to `git rev-parse --abbrev-ref HEAD` if not provided. Default `branch_base` via:

1. `git symbolic-ref refs/remotes/origin/HEAD` (definitive when origin is tracked).
2. Probe `main` / `master` / `develop` via `git rev-parse --verify <name>`.
3. Fallback to literal `'main'` (matches the historical default of `mem_archeo_git`).

Resolve:

- `head_sha = git rev-parse {branch}`.
- `merge_base_sha = git merge-base {base} {branch}`.
- `fully_merged = (head_sha == merge_base_sha)` — the branch is fully absorbed into base, range queries `base..branch` would be empty.
- `commits_count = git rev-list --count {merge_base_sha}..{branch}` (zero when fully merged).

When `merge_base` cannot be resolved (typo on `branch_base`, branch not in local refs), surface the error to the caller — do NOT silently invent a fallback. The historical "first-parent" fallback was retired in v0.10.0 (Codex case study on `ecosav` showed it produces 1000+ irrelevant commits on absorbed branches).

### 3. List branch authors

`git log {merge_base_sha}..{branch} --format='%ae|%an'` (skipped when `fully_merged`). Aggregate into a list of `(email, name, commits)` sorted by commit count descending.

`is_solo_branch = (len(authors) == 1 AND authors[0].email == user_self.email)`. Drives the default for the `author_self_only` filter.

### 4. Decide slug proposal

Priority order:

1. If `project` arg was provided: use it verbatim. `source = 'project-arg'`. `needs_confirmation = False`.

2. Else: sanitise the branch name into a slug candidate (strip git-flow prefixes `feat/`, `fix/`, `hotfix/`, etc., lowercase, ASCII-fold separators to `-`). Then test for **human-readability**:
   - matches `^[a-z][a-z0-9]{1,}([-_][a-z0-9]+)*$` (kebab/snake casing, ≥3 chars), AND
   - does NOT contain a JIRA-style ticket fragment (`[A-Z]+-\d+`) or hex-only (`[a-f0-9]{8,}`) or numeric run (`\d{4,}`).

3. Human-readable → trust the heuristic, `source = 'branch-name'`, `needs_confirmation = False`. Examples : `ecosav`, `dev-compta`, `arrondis-2digits`.

4. NOT human-readable → `source = 'needs-prompt'`, `needs_confirmation = True`. The LLM caller MUST ask the user for an explicit slug. Examples that flag : `JIRA-1234`, `feat/ABC-456`, `bdc7e9a`, `2024-01-bugfix`.

### 5. Resolve project state in the vault

For the candidate slug, check:

- `{vault}/10-episodes/projects/{slug}/context.md` exists → `project.exists = True`, `will_init = False`.
- `{vault}/10-episodes/archived/{slug}/` exists → `exists = False`, `will_init = False` (archived projects are off-limits per `_archived.md` doctrine; surface a warning so the caller offers `mem_historize --revive`).
- Neither → `exists = False`, `will_init = True`. Phase 5 will initialise the skeleton at archive write time.

### 6. Resolve scope strategy

Given `fully_merged` + the existence of a directory matching the branch name :

- `fully_merged == False` → `mode = 'live'`. Estimate `files_count_estimate` via `git log {merge_base_sha}..{branch} --name-only --pretty=format:` and dedupe.
- `fully_merged == True` AND `_suggest_scope_from_branch_name(branch)` returns matches → `mode = 'auto-scope-by-name'`, `scope_glob = '{deepest-match}/**'`. Estimate via `enumerate_files(scope_glob=...)`.
- `fully_merged == True` AND no name match → `mode = 'refusal'`. Caller MUST provide an explicit anchor (`--since-sha`, `--since-date`, `--scope-glob`).

`_suggest_scope_from_branch_name` generates kebab/snake/camelCase/PascalCase/UPPER/lower variants of the branch name (after stripping git-flow prefixes), then matches case-insensitively against the *last* path component of every directory tracked at `HEAD` (`git ls-tree -r -d --name-only HEAD`). Deepest match wins.

### 7. Propose granularity

Heuristic, first match wins :

| Condition | Proposed |
|-----------|----------|
| has merge commits in range | `by-merge` |
| solo branch + ≥3 commits | `by-window-month` |
| multi-author + ≥10 commits | `by-window-month` |
| else | `by-window-week` |

**Never propose `by-author-week` by default.** Too noisy (1 archive per author per week → 73 mechanical archives in the Gemini case study). Only useful for HR-style attribution, and the user must opt in explicitly.

### 8. Propose filters

- `is_solo_branch == True` → `author_self_only = True`, `include_team = False`.
- multi-author → `author_self_only = False`, `include_team = True`.

The user can override either.

### 9. Build warnings list

Surface non-blocking warnings the caller MUST present to the user :

- slug needs confirmation (cryptic branch).
- project will be initialised (no existing project).
- branch is fully merged into base (with the resolved scope mode).
- scope is large (>500 files) AND granularity is not `by-merge` (recommend `--by-merge`).
- multi-author branch but `author_self_only = True` was proposed (verify intent).

### 10. Return ArcheoPlan

Return the structured `ArcheoPlan` with `summary_md` pre-formatted for direct user display.

The caller (LLM) is doctrinally required to:

1. Display `summary_md` to the user.
2. Wait for explicit validation (or override on slug / scope / granularity / filters).
3. Acknowledge each warning.
4. Only then invoke `mem_archeo_git` with the validated parameters.

No subprocess git fires for archive writing as long as the plan is not approved. Read-only — never writes the vault.

## Doctrine implications

- Phase 0 cadrage is REQUIRED for branch-first invocations. May be skipped only when ALL of: standard mode (no `--branch-first`), milestone source is `tags` or `releases`, project already exists, `--no-confirm` was passed.
- The plan does NOT make any decision permanent. It is informational + structured. The downstream Phase 3 (`mem_archeo_git`) is the actual writer and respects the validated parameters.
- The plan's slug + granularity proposals are heuristics — the user can always override. The point is to surface the decision, not to make it.

## Failure modes

- Repo not found → `FileNotFoundError`.
- `branch_base` typo → caller-facing error from `_run_git`, no silent fallback.
- Empty repo (no commits) → fields populated with empty strings / 0 counts ; warnings list a single "empty repo" entry.
- `git config user.email|name` unset → `user_self.email|name = ''` ; `is_solo_branch` cannot be true ; default filter falls back to `include_team = True`.
