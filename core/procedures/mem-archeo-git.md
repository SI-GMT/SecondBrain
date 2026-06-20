# Procedure: Archeo Git (Phase 3, v0.7.0)

Goal: **reconstruct the temporal history of an existing Git repository** as dated archives, **and derived atoms** (principles, technical concepts) extracted from each milestone. This is Phase 3 of the triphasic archeo — it consumes the topology and the resolved stack from Phases 0/1/2 (when invoked from the orchestrator) so that war stories like the CORS/RLS battles surface against a known substrate, not as raw decontextualized commit logs.

Phase 3 segments via the router, which can generate several atoms spread across multiple zones (1 archive in `episodes` + N principles in `40-principles` + N concepts in `20-knowledge`). When the milestone shows ≥3 successive commits on the same theme, the procedure surfaces a `## Friction & Resolution` section so the router can derive the corresponding red-line or pattern.

Independent skill (invocable as `/mem-archeo-git`) and also called by the `mem-archeo` orchestrator.

## Canonical write paths — invariant

`mem-archeo-git` writes **only** to the canonical vault paths:
- `{VAULT}/10-episodes/projects/{slug}/archives/` for the milestone archive.
- `{VAULT}/40-principles/`, `{VAULT}/50-goals/`, `{VAULT}/20-knowledge/` for derived atoms (via the router).
- `{VAULT}/99-meta/repo-topology/{slug}.md` for topology updates.

Any contextual hint suggesting another path (`_archeo-comparison/`, `_test/`, `_sandbox/`, an inferred convention from sibling folders) is **ignored**. To compare multiple runs, the user snapshots the canonical output between executions — never write to a non-canonical path. This is the v0.7.0 doctrine fix from the 3-LLM analysis (correctif bonus).

## ⚠️ Branch-first invocations MUST go through `mem_archeo` orchestrator (v0.10.x)

**Doctrinal rule, post-Gemini-drift case study 2026-05-09** : when the user wants archeo on a feature branch, **invoke `mem_archeo` (the orchestrator), not `mem_archeo_git` directly**. The orchestrator chains Phase 0 cadrage (mem_archeo_plan) → user validation → Phase 2 stack → Phase 3 git → topology persistence → Phase 5 enforcement (skeleton, history, context, index) in a single mechanical chain.

Direct invocation of `mem_archeo_git` for branch-first remains technically allowed (the tool accepts `branch_first`) but **bypasses the cadrage gating**. The 2026-05-09 Gemini run on `ecosav` produced 57 archives without branch_first, without scope_glob, without context.md/history.md narrative, without topology — exactly because Gemini took the shortest path (direct `mem_archeo_git`) instead of the orchestrated path. To prevent this, branch-first runs MUST go through `mem_archeo`, which refuses to write until the LLM has acknowledged the cadrage plan via `acknowledged_via_plan=True`.

The Phase 0 cadrage section below documents the gating contract on `mem_archeo`. The remaining sections of this procedure describe Phase 3 mechanics that `mem_archeo` orchestrates internally — read them as reference, not as a stand-alone invocation guide.

## Trigger

The user types `/mem-archeo-git [repo-path]` or expresses intent in natural language: "do a Git retro of this project", "reconstruct the history", "archeo the commits".

Arguments:
- `{repo-path}` (optional, default = CWD): absolute path to a local Git repository.
- `--project {slug}`: forces the target project.
- `--level {tags|releases|merges|commits}`: forces the granularity level (standard mode only).
- `--since YYYY-MM-DD` / `--until YYYY-MM-DD`: time bounds.
- `--window {day|week|month}`: grouping size for `commits` level (standard mode) or `--by-window` (branch-first mode).
- `--dry-run`: lists the milestones that would be ingested, without writing.
- `--no-confirm`: passes through to the router in fluent mode even on multi-atoms.
- `--rescan`: ignores any persisted topology and forces a fresh scan.

**Branch-first mode (v0.7.1, hardened in v0.9.x, amended v0.10.x post-Codex case study)**:

- `--branch-first {branch}`: scope Phase 3 to commits relevant to the branch. Resolution strategies, evaluated in priority order:

  - **Explicit anchor** — if `--since-sha {sha}`, `--since-date YYYY-MM-DD`, or `--scope-glob {glob}` is provided, use it verbatim. Bypasses merge-base detection. Always wins. Useful when the branch was rebased/squashed and the historical divergence point is known but not derivable from refs, or when a directory-level scope is desired.

  - **Live (range strict)** — `git merge-base {base} {branch}` distinct from `HEAD(branch)`. The branch is not fully merged, so `merge_base..branch` yields the proper rev-range. Standard path.

  - **Merged-via-perimeter** _(new in v0.10.x post-2026-05-09 — primary strategy when fully merged)_ — when the branch is fully merged, a multi-signal walker captures **all** merge cycles of the branch by walking `git log {base} --merges --first-parent` and scoring each merge `M` against the branch perimeter. Bootstrap : merges whose subject contains the branch name (e.g. `Merge branch 'ecosav'`, `Merge pull request #X from owner/ecosav`) are captured first as definite cycle merges, defining the authoritative perimeter (files) + author set (avoids HEAD-ancestor pollution from dev-reset workflows). Iterative widening : remaining merges are scored via `0.5 × file_score + 0.3 × author_score + 0.2 × subject_score`, where `file_score = min(|perim ∩ files_M|/|files_M|, |perim ∩ files_M|/|perim|)` (reciprocal overlap suppresses drive-by refactors), `author_score = |authors_M ∩ branch_authors|/|authors_M|` (signal off when foreign authors), `subject_score = 1.0` iff branch name in subject. Threshold `0.4`, `min_commits=2`. Each captured merge represents one full cycle of the branch — handles **dev-reset workflows** (`git reset --hard origin/base` between cycles) where the single-tip merge-commit walker would only find the latest cycle. Each cycle becomes one archive in Phase 3. Per-merge `score` + `breakdown` surfaced in archive frontmatter for audit.

  - **Merged-via-merge-commit** _(fallback for single-cycle branches when perimeter walker captures nothing)_ — when the perimeter walker returns empty AND the absorbing merge commit `M` is detectable on `base` first-parent (`M^2 == HEAD(branch)`), the tool uses range `M^1..M`. Triggered on branches whose merge subjects don't mention the branch name AND HEAD(branch) still points at the original tip (rare).

  - **By-files** — set `--by-files` to query commits **touching the files introduced by the branch** (detected via `--diff-filter=A` over `merge_base..branch`), repo-wide rather than constrained to the branch range. Captures creation, evolution **and** post-merge fixes on the same files. Recommended for archeology of long-lived feature branches whose post-merge maintenance happened on `main`. Tried only when `merged-via-merge-commit` could not detect M (squash/rebase scenarios).

  - **Auto-scope-by-name** _(new in v0.10.x; demoted to fallback in v0.10.x post-2026-05-09)_ — last-resort fallback when the branch is fully merged AND no merge commit M was detectable AND `by_files` did not produce a scope. Derives a scope from the **branch name**: variants are generated (kebab, snake, camelCase, PascalCase, UPPER, lower, prefix-stripped — `feat/eco-sav` strips to `eco-sav`, generates `EcoSav`, `ecosav`, `ECO-SAV`, etc.) and matched case-insensitively against the **last component** of every directory tracked at `HEAD`. The deepest match drives `scope_glob: '<dir>/**'`. Surfaced explicitly in the report warnings as `branch-first: branch fully merged into <base> AND no merge commit absorbs the branch tip on base first-parent (squash or rebase + ff); scope falls back to auto-scope-by-name → '<dir>'`. **Unreliable** by construction (name = scope is a heuristic) — the user MUST verify.

  - **Refusal (no fallback dérivant)** — when the branch is fully merged AND no merge commit AND no anchor AND no name match → the tool raises a `BranchScopeUnresolvedError` (surfaced as a structured warning, not a fatal). The caller (LLM or user) must re-invoke with `scope_glob` / `since_sha` / `since_date`. **No first-parent fallback is attempted** — the v0.10.0 `merged-fallback` strategy was retired because on long-lived absorbed branches it dove into the base branch's history (often 1000+ irrelevant commits) and produced sloppy archives. The Codex case study on `ecosav` of the IRIS USER repo (2026-05-08) made the pattern obvious enough to drop.

- `--branch-base {ref}`: base ref for the divergence calculation (default `main`; pass `master` if your repo uses that).
- `--by-author` (default in branch-first): granularity is `(author_email, time-window)`. Window defaults to `day`; configurable via `--window`.
- `--by-merge`: granularity is by merge commit on the branch (relevant for long-lived branches that absorbed sub-features).
- `--by-window`: granularity is the classic `--window` time grouping (overrides `--by-author`).

The resolution mode is reported in the archive frontmatter (`branch_resolution: live | merged-via-perimeter | merged-via-merge-commit | since-sha | since-date | by-files | auto-scope-by-name`) so the user can audit which strategy ran. The legacy value `merged-fallback` still appears on archives created before the v0.10.x amendment but is no longer produced for new runs.

## Vault and repo path resolution

Read {{CONFIG_FILE}} and extract `vault`, `default_scope`, and `kit_repo`. If `vault` is missing, standard error message and stop.

## Phase 0 — Interactive cadrage (REQUIRED for branch-first, v0.10.x)

**Doctrinal rule** : on a branch-first invocation (or any invocation that targets a long-lived feature branch with multiple authors / merges / no semver tags), no subprocess git fires for archive writing until the user has validated a structured plan. This eliminates the macro-drift class that frontmatter validation alone cannot prevent (case study : Gemini 2026-05-08 producing 73 mechanical archives under a wrong slug, no `context.md`/`history.md` created, granularity `--by-author --window=week` chosen silently, `--branch-first` not even passed → archeo of `master` instead of `ecosav`). The plan is the cadrage that surfaces those decisions before they become writes.

### 0.1 Invoke `mem_archeo_plan`

Call the MCP tool `mem_archeo_plan` with the repo path and (optionally) `branch`, `branch_base`, `project`. The tool is **read-only** — zero vault writes, zero side-effects. It returns an `ArcheoPlan` containing :

- `user_self` : email + name from `git config user.email|name` of the target repo. Anchor for the self-vs-team author filter.
- `branch` : resolved branch (defaults to current HEAD), resolved base (auto-detected via `origin/HEAD` or probe `main`/`master`/`develop`), `fully_merged` bool, `commits_count`.
- `branch_authors` : list of `(email, name, commits)` in the scope. `is_solo_branch` bool (true iff exactly one author == `user_self.email`).
- `slug` : `{candidate, source, needs_confirmation, reason}`. `source` is one of `project-arg | branch-name | needs-prompt | cwd-basename`.
- `project` : `{exists, will_init, path}`.
- `scope` : `{mode, scope_glob, scope_globs, files_count_estimate}`. `mode` is `live | merged-via-perimeter | merged-via-merge-commit | by-files | auto-scope-by-name | since-sha | since-date | refusal`. `scope_globs` lists every directory matched when `mode == 'auto-scope-by-name'`. When `mode == 'merged-via-perimeter'`, `files_count_estimate` is the union across all captured cycles.
- `granularity` : `{proposed, reason}`. Default heuristics : has-merges → `by-merge` ; solo + ≥3 commits → `by-window-month` ; multi-author + ≥10 → `by-window-month` ; small scope → `by-window-week`. **Never proposes `by-author-week` by default** — too noisy, only useful for HR-style attribution.
- `filters` : `{author_self_only, include_team}`. Default solo-branch → `author_self_only=true` ; multi-author → `include_team=true`.
- `warnings` : list of strings that the LLM MUST surface to the user.
- `summary_md` : pre-formatted Markdown briefing.

### 0.2 Surface plan to user, await validation

Display the plan's `summary_md` to the user. Ask for explicit validation, with override slots for at least :

- **slug** : when `needs_confirmation=true` (cryptic branch name like `JIRA-1234`, `feat/ABC-456`), MUST ask the user for a meaningful project slug. When `needs_confirmation=false` but `project.exists=false` AND a similarly-named project already exists in the vault (typo, plural, hyphen vs underscore), ALSO ask. Override : `--project {slug}`.
- **project init** : when `project.will_init=true`, announce explicitly that `context.md` + `history.md` + `archives/` will be created. The user may decline (e.g. choose to merge into an existing project instead). Override : `--project {existing-slug}`.
- **scope mode** : when `mode == 'refusal'`, the user MUST provide an anchor (`--since-sha`, `--since-date`, `--scope-glob`) — Phase 3 cannot proceed without it. When `mode == 'merged-via-perimeter'`, surface the **count of captured merge cycles** + per-cycle scores (from `branch-first` notes in `warnings`) so the user can spot any false positive (e.g. a cross-project refactor that scraped the threshold). When `mode == 'merged-via-merge-commit'`, surface the absorbing merge commit SHA + range (`M^1..M`) for transparency. When `mode == 'auto-scope-by-name'`, surface the resolved glob (and `scope_globs` list when several dirs matched) and ask the user to confirm or override — this fallback is heuristic.
- **granularity** : present the proposed value with the reason. Override : `--by-merge`, `--by-window-month`, `--by-window-week`, `--by-author-week`. The user may also accept the proposal silently (typical case).
- **filters** : present the `author_self_only` / `include_team` proposal. Override : `--author-self-only=true|false`, `--include-team=true|false`.
- **warnings** : every warning in `plan.warnings` MUST be acknowledged. Don't just print them — re-present them as questions when relevant ("the branch is fully merged into base, do you want me to proceed with the auto-scope-by-name resolution?").

The user may also abort (`/cancel`) — in which case nothing happens.

### 0.3 Pass validated plan to `mem_archeo_git`

Once the user has validated, invoke `mem_archeo_git` with the **exact arguments from `plan.next_call`** — literal copy, zero translation, zero reinterpretation. The plan field is structured precisely so the LLM does not have to translate "by-merge granularity" into a flag that does not exist (`mem_archeo_git` has no `by_merge` parameter — perimeter mode emits one archive per captured cycle natively, the granularity displayed in the plan is informational only).

Doctrinal rule, post-2026-05-09 IRIS USER case study :

- **Read `plan.next_call` (a `dict`).**
- **Invoke `mem_archeo_git` with literally those keyword arguments.** Do NOT add `since`/`until`/`scope_glob` filters that were not in `next_call`. Do NOT change `level` / `window` / `by_author`. Do NOT drop `branch_first` because the user said "by-merge" — the perimeter mode already produces one archive per cycle.
- **If the user explicitly overrides a field during validation** (e.g. picks a different slug, narrows scope to a sub-glob), update the corresponding key in `next_call` before invoking. Never re-derive the whole call from the user's text.

The 2026-05-09 case study : Gemini invoked `mem_archeo_plan` correctly (mode `merged-via-perimeter`, ~50 files, 30 absorbed merge cycles), then translated the validated plan freely into `mem_archeo_git(level='commits', window='week', by_author=True, scope_glob=…)` — **dropping `branch_first=ecosav`**. Result : standard discovery fired, 2 archives instead of ~30 cycles, frontmatter `branch: ''`, no perimeter metadata, no per-merge audit. The `next_call` dict eliminates this drift category.

If the user explicitly aborts (`/cancel`), nothing happens.

The Phases 1 → 6 below operate on the validated parameters. **No silent re-derivation of the slug or granularity inside Phases 1+** — if the LLM finds a discrepancy (e.g. the resolved slug doesn't match an existing project found mid-Phase 5), surface it back to the user, do not auto-correct.

### 0.4 Skip Phase 0 only when explicitly safe

The Phase 0 cadrage is doctrinally required for branch-first runs. It is OPTIONAL (and may be skipped) only when ALL of the following are true :

- standard mode (no `--branch-first` flag), AND
- the milestone source is `tags` or `releases` (semver tags or GitHub releases — well-defined boundaries), AND
- the project slug already exists in the vault (no init), AND
- `--no-confirm` was passed explicitly by the user.

In all other cases — branch-first, commit-windows, merges, missing project — Phase 0 is mandatory.

## Procedure

### 1. Validate the source repository

Verify that `{repo-path}` is a Git repository (`git -C {repo-path} rev-parse --git-dir`). If not, stop with a clear message.

### 2. Resolve the target project/domain

By priority:

1. Explicit `--project {slug}` or `--domain {slug}`.
2. Match `basename({repo-path})` against existing slugs in `{VAULT}/10-episodes/projects/` then `domains/`.
3. Match the repo's `git remote get-url origin` against existing `repo_remote` fields in any `99-meta/repo-topology/*.md`.
4. Ask the user (with `/mem-list` as support).
5. If new slug → create the structure `{VAULT}/10-episodes/{kind}/{slug}/` with `context.md` + `history.md` + `archives/`. Set `repo_path: {repo-path}` in the new context.md frontmatter.

### 3. Phase 0 — Topology (consume or scan)

If invoked from the `mem-archeo` orchestrator, the topology is **already in working memory** — skip the scan and use the passed topology object.

Otherwise (standalone invocation), perform the Phase 0 scan:

{{INCLUDE _repo-topology}}

Phase 3 specifically consumes:
- `topology.categories.ai_files` and `topology.categories.readme` — to enrich each milestone with the AI files at the time of commit (step 4b).
- `topology.stack_hints` — to know what stack the project runs on, so the LLM can recognize stack-typical battles (e.g. CORS issues are characteristic of self-hosted Supabase).
- The persisted topology `{VAULT}/99-meta/repo-topology/{slug}.md` if present — gives access to the resolved stack from a prior Phase 2.

### 4. Detect the granularity level

#### 4.a Standard mode

If `--level` not provided, choose automatically (first one returning >0):

1. **Semver tags** (`v*.*.*`) → 1 archive per tag.
2. **GitHub releases** (via `gh release list` if available) → 1 archive per release.
3. **Merges on mainline** (`git log --merges main`) → 1 archive per merge.
4. **Commit windows** (week/month) → 1 archive per window.

Display the choice to the user and ask for confirmation before proceeding.

#### 4.b Branch-first mode (v0.7.1)

When `--branch-first {branch}` is set, the granularity is one of:

- **`--by-author`** (default): enumerate commits via `git log --no-merges {branch_base}..{branch} --format="%H|%an|%ae|%aI|%s"`. Group commits by `(author_email, time-window)` where time-window is the day (default) or `--window {week|month}`. Each group becomes one archive.
- **`--by-merge`**: enumerate merge commits on the branch via `git log --merges {branch_base}..{branch}`. Each merge becomes one archive (the merge represents a sub-feature absorbed into the long-lived branch).
- **`--by-window`**: enumerate all commits via `git log --no-merges {branch_base}..{branch}`, group by `--window` ({day|week|month}, default `week` in this mode).

Co-Authored-By trailers are extracted via `git log --format="%(trailers:key=Co-authored-by)"` for each commit and aggregated at the group level. They are recorded as **metadata only** in the archive frontmatter (`co_authors: [email1, email2, ...]`), never as a separate archive — the attribution is the `author` of the primary commit.

Useful side-effect: `co_authors` captures LLM attributions when commits carry `Co-Authored-By: Claude Opus ...`, so the archive trail can distinguish human vs LLM contribution to the branch.

Display the chosen granularity, the divergence point (`branch_base_sha` + date), and the resulting archive count to the user. Ask for confirmation before proceeding.

### 5. For each milestone: prepare the content

For each milestone (tag, release, merge, window) within the time window `--since`/`--until`:

#### a. Verify idempotence

Search the vault for an existing atom with:
- `source: archeo-git`
- `source_milestone: {tag|sha|range}` matching the current milestone.

If found, **silent skip** (already ingested) unless the milestone has changed (e.g. moved tag) — in which case create a revision with `previous_atom: [[old]]` and tag `revision`.

#### b. Extract milestone information

Depending on the level:
- **Tag/release**: tag message, GitHub release note content (`gh release view`), commit SHA, date, main author, modified files (diff stats).
- **Merge**: merge message, source branch, files, referenced tickets (regex `[A-Z]+-\d+` for Jira, `#\d+` for PR).
- **Commit window**: aggregation of commit messages within the window, touched files, contributors.

Enrich **MUST**:
- **Root AI files** at the time of commit: read via `git show {sha}:{file}` for each file in `topology.categories.ai_files` AND `README.md`. Extract explicitly the following five categories from these files when present:
  - **Workflow methodology** (Speckit, ADR rituals, branch model, code review rules)
  - **Sync / offline-first strategy**
  - **Multi-tenant model + role scopes**
  - **Non-negotiable security constraints**
  - **Architectural decisions already recorded**

  These extracts must **directly inform** the archive body and the derived atoms. If nothing is extracted because the AI files are silent on these categories, mention explicitly in the archive: "no AI-files context extracted for milestone {ID}". Never silently skip the read — that would erase the doctrine fix from the 3-LLM analysis (correctif 1).

- **Jira/Linear tickets**: extract keys from the message + reference.
- **Linked PRs**: `gh pr view {number}` if available.

#### c. Detect friction patterns

If the milestone (especially commit windows) shows **≥3 successive commits** on the same file, feature, or theme (lexical clustering on commit messages: same prefix, same noun, same fix verb), tag the milestone as having **friction**. The router will surface this in the archive body via the `## Friction & Resolution` section (cf. step 5d).

This is the v0.7.0 doctrine fix — without active surfacing of friction, multi-round debug battles (e.g. CORS/auth-proxy chains in self-hosted stacks) stay invisible in the archives.

#### d. Build the content for the router

Prepare a structured Markdown with explicit delimiters to ease segmentation by the router. **Five sections are mandatory in the body — Main, Analyse fonctionnelle, Analyse technique, AI files context, Friction & Resolution. Each carries an explicit fallback marker if the LLM has nothing material to add.** Never omit a section without its fallback line. The 2 new analysis sections (Analyse fonctionnelle + Analyse technique) extend the v0.7.0 invariant in v0.10.x after the 2026-05-08 Gemini case study showed that purely mechanical archives (subject Git + diff stats) lose all narrative value. Forcing the LLM to either fill them with judgment OR explicitly mark them empty makes the silent omission impossible.

```
# Milestone archive — {tag|sha|range}

{Main section — dated event to archive in episodes. Include:}
- Date and authors
- Files modified (counts and notable paths)
- Linked tickets and PRs
- Summary of what shipped

## Analyse fonctionnelle

{What changed for the user / business: the feature delivered, the bug fixed,
the behaviour altered. Strip technical detail — that lives in the next
section. The audience here is the non-technical reader who wants to
understand the user-facing intent of this milestone in 30 seconds.

If the milestone has genuinely no functional impact (refactor, tooling, doc),
write a one-liner explicitly saying so:

  No user-facing functional change in this milestone — refactor / tooling / doc only.

Never omit the section.}

## Analyse technique

{How the change is implemented: layer touched, pattern introduced,
dependencies added/removed, side-effects, risks, perf implications.
Surface anything an experienced engineer reading the diff would want to
know in 30 seconds. Pull from the topology + stack context provided by
Phase 0 / Phase 2 — the LLM should recognise stack-typical patterns
(e.g. CORS issues are characteristic of self-hosted Supabase, RLS
patterns are characteristic of multi-tenant pgsql).

If the diff is trivial (typo, format, single-line config change), write
a one-liner explicitly saying so:

  Trivial change — typo / format / single-line config; no architectural impact.

Never omit the section.}

## AI files context

{Excerpts extracted from CLAUDE.md / AGENTS.md / GEMINI.md / README.md for the
five categories listed in step 5b. If nothing was extractable from any AI
file (none present, or none mentioning the five categories), write the literal
line:

  No AI-files context extracted for this milestone.

This explicit fallback is mandatory — never omit the section.}

## Friction & Resolution

{If friction was detected at step 5c, describe:
- The problem: what surfaced?
- Attempts: what was tried (chronologically)?
- Final insight: what was learned?

If no friction was detected, write the literal line:

  No friction detected for this milestone.

This explicit fallback is mandatory — never omit the section.}

## Author signature {only when granularity is --by-author, omit otherwise}

{Only in --by-author mode. Capture the **patterns of this author** observable
in the milestone's commits. Examples:
- Style of commit messages (concise vs verbose, conventional commits adherence,
  language).
- Recurring focus areas (this author works mostly on src/auth/, src/api/ but
  not docs/).
- Methodological signature (TDD discipline visible? small commits? big drops?
  early vs late refactor in the day?).
- Co-authorship with LLM tools (presence of "Claude Opus", "Gemini", "Codex"
  in Co-Authored-By trailers — useful to distinguish human vs AI-paired work).

This section is the value-add of --by-author granularity over --by-window.
If the author has only 1-2 commits in the window, this section can be one
line: "Single contribution to {area}, no broader pattern observable in this
window." Never omit the section in --by-author mode — always add the literal
fallback if there's nothing to say.}

## Principle: {short title}

{If the milestone surfaced an explicit principle (often the takeaway of a
friction sequence — "never X", "always Y"), formulate it here. The router
will route to 40-principles.}

## Concept: {short title}

{If the milestone introduces a reusable technical concept or architecture,
formulate it here. The router will route to 20-knowledge.}

## Goal: {short title}

{If the milestone introduces or clarifies a project goal (next feature
explicitly committed to, KPI target), formulate it here. The router will
route to 50-goals. This is the v0.7.0 doctrine fix from the 3-LLM analysis
(correctif 2).}
```

The `## Goal:` section is new in v0.7.0 — Phase 1 absorbs most goal extraction from the project docs, but Phase 3 still surfaces goals that emerge mid-Git-history (a feature shipped that opens a roadmap for follow-ups).

### 6. Invoke the router for this milestone

Call the router with:
- `Content`: structured Markdown of the milestone.
- `Hint zone`: `episodes` (forces the main section).
- `Hint source`: `archeo-git`.
- `Metadata`: resolved project/domain, **`source_milestone: {tag|sha|range}`**, `commit_sha`, `friction_detected: true|false`, scope.

**Frontmatter checklist for the resulting milestone archive — walk `_frontmatter-archeo.md` line by line before invoking the router**. The block below is included verbatim in this procedure and is the single canonical contract for archeo atoms (universal + archeo-specific MUST fields, exhaustive). **No silent omission tolerated** — any missing MUST field is a malformed archive.

{{INCLUDE _frontmatter-archeo}}

In standard (non-branch-first) mode, the branch-* fields (`branch`, `branch_base`, `branch_base_sha`) are **set to empty string `''`**, never omitted — they are part of the canonical schema for `archeo-git` archives in v0.7.1. Same for `co_authors: []` (empty list, never omitted).

**No duplicate keys.** YAML doesn't tolerate duplicate top-level keys reliably — duplicates are parser-implementation-defined. The router MUST emit each key exactly once. If two values are conceptually needed (e.g. multiple commits in a window), use a list (`source_commits: [...]`) rather than two `commit_sha:` keys.

**Bidirectional `derived_atoms` link is mandatory.** For each transverse atom this milestone produces (Principle, Concept, Goal sections of the body), the writer MUST :

1. Set the transverse atom's `context_origin` to `[[<milestone-archive-name-without-md>]]`.
2. Append the transverse atom's wikilink to the milestone archive's `derived_atoms:` field.

If a transverse atom has `source: archeo-git` but is not referenced in any milestone's `derived_atoms`, it is an `archeo-derived-orphan` (detected by `mem-health-scan`). The link must be bidirectional or the atom is malformed.

{{INCLUDE _router}}

The router:
- Writes the main archive into `{VAULT}/10-episodes/{kind}/{slug}/archives/`.
- For each derived section (`## Principle:`, `## Concept:`, `## Goal:`), classifies via the cascade. Atoms inherit `project: {slug}` and `context_origin: "[[<milestone-archive-name>]]"`.
- Bidirectional links via `derived_atoms` of the milestone archive.
- Idempotence via R10 with key `(project, source_milestone, source_atom_type, source_atom_subject)`.
- Collision detection via R11.

### 7. Loop over all milestones

If `--dry-run`: display the list of milestones that would be ingested (with planned derived atoms) + estimated total. Ask for confirmation to switch to `--apply`.

Otherwise: iterate over all milestones. The router handles user confirmation in safe mode (default), or direct write if `--no-confirm`.

### 7.5. Cross-link derived atoms

After all milestones are ingested, scan the atoms produced by this run for **semantic overlaps** (lexical signals on subject + body keywords). For each pair of atoms whose subjects share ≥2 significant terms (excluding stop words), add reciprocal wikilinks in a `## Related` section of each atom.

Heuristic: if atom A's subject mentions terms present in atom B's subject (and vice versa), create the link. This is intentionally simple — the goal is to break the "archipelago of atoms" failure mode from the 3-LLM analysis (correctif 3), not to build a perfect knowledge graph.

### 7.6 Phase 5 enforcement — context / history / index updates (v0.10.x)

After the per-milestone write loop, the MCP tool layer (`tools/archeo_git.py::_enforce_phase5`) automatically:

1. **Auto-init project skeleton** — if `{project}/context.md` or `{project}/history.md` is missing, create both via `execute_init_project`. The 2026-05-08 Gemini case study showed what happens when this is left to LLM judgement: 73 archives under `user-prod-iris/` with no skeleton at all. The doctrine is now mechanical: every archeo write lands inside a project with a complete skeleton, full stop. Existing archives in the folder are preserved during init (they get backed up + restored).

2. **Patch `{project}/history.md`** — prepend a new entry per archive created/revised, after the H1 header. Entries are minimal (`- [{stem}](archives/{filename})`) — the heavy narrative lives in the archive itself. Idempotent : entries already referenced are skipped, re-running the same archeo doesn't duplicate the history.

3. **Patch `{project}/context.md`** — rewrite `phase` to `archeo-git run on {today} — {N} archive(s) created branch {branch} ← {base} (sha {sha[:12]})` and bump `last-session`. Idempotent on (today, count, branch). The previous `phase` value is overwritten — Phase 3 archeo runs are themselves the meaningful "phase" for the project's recent state.

4. **Patch root `index.md`** — insert each new archive at the top of the `## Archives` section. Idempotent. Best-effort — if `## Archives` is not present (older vault layout), append at the end with the section header.

5. **Failure mode** — Phase 5 enforcement runs in a try/except. If anything raises (vault read-only, partial filesystem failure, etc.), the error is surfaced as a `warning` in the result, not as a tool error. The archives have already been written successfully ; the user can re-run `mem_health_repair` to reconcile the skeleton.

This step is **not optional**. The doctrinal rule is : every `mem_archeo_git` invocation that produces ≥1 archive MUST also leave `context.md` + `history.md` + `index.md` consistent. Skipping any of these reproduces the Gemini drift (no skeleton, no narrative recap, archives invisible to `mem_recall`).

### 8. Update the persisted topology

Same logic as `mem-archeo-context` step 7, but updating:
- `Phases archeo couvertes` line: `Phase 3 (archeo-git) — N archives — last pass: {today}`.
- `Atomes dérivés des phases archeo` section: append all atoms with `source: archeo-git` AND `project: {slug}` produced by this run.

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

{{INCLUDE _linking}}

{{INCLUDE _repo-paths}}

### 9. Final report

Display:

```
Phase 3 archeo-git — {slug}

Milestones processed : {N}
Archives created     : {N}
Archives revised     : {N}
Skipped (idempotent) : {N}
Derived atoms        : {N}  ({M} principles, {P} goals, {Q} knowledge)
Friction sequences   : {N}  surfaced as Friction & Resolution sections
Cross-links added    : {N}

Topology updated     : 99-meta/repo-topology/{slug}.md
```

If invoked from the `mem-archeo` orchestrator, return the structured result.

## Invariants

- **Canonical write paths only** — see header.
- **Always read AI files** at each milestone. Never silently skip.
- **AI files context section is ALWAYS present in the body**, with explicit fallback "No AI-files context extracted for this milestone." if empty. Same for Friction & Resolution.
- **Friction surfacing** — if ≥3 successive commits on same theme, surface in archive. No exception.
- **`source_milestone`, `commit_sha`, `friction_detected`, `content_hash`, `previous_atom` are mandatory** on every Phase 3 archive — never omitted, even with empty values.
- **No duplicate YAML keys.** Each frontmatter key appears exactly once. Use lists for multi-valued data.
- **Frontmatter values in canonical English** — `force` enum is `red-line | heuristic | preference`, never localized.

## Archived projects handling (v0.7.4)

Per `core/procedures/_archived.md` (doctrinal block). `mem-archeo-git` refuses by default on an archived target slug — see the override path in `mem-archeo.md` (`--allow-archived` flag forwarded from the orchestrator).
