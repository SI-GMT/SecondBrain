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

**Branch-first mode (v0.7.1, hardened in v0.9.x)**:

- `--branch-first {branch}`: scope Phase 3 to commits relevant to the branch. Three resolution strategies, mix-and-matchable, evaluated in priority order:
  - **(C) Explicit anchor** — if `--since-sha {sha}` or `--since-date YYYY-MM-DD` is provided, use it verbatim. Bypasses merge-base detection. Useful when the branch was rebased/squashed and the historical divergence point is known but not derivable from refs.
  - **(A) Auto first-parent fallback** — when the branch has been **fully merged** into `--branch-base` (`merge-base == HEAD(branch)`, so the standard `merge-base..branch` rev-range yields zero commits), the tool transparently falls back to the first-parent divergence point. Gives a stable historical anchor that ignores the merge-back commit. No flag needed; surfaced as a `branch-first: branch fully merged...` warning in the report.
  - **(B) By-files** — set `--by-files` to query commits **touching the files introduced by the branch** (detected via `--diff-filter=A` on the first-parent lineage), repo-wide rather than constrained to the branch range. Captures creation, evolution **and** post-merge fixes on the same files. Recommended for archeology of long-lived feature branches whose post-merge maintenance happened on `main`.
- `--branch-base {ref}`: base ref for the divergence calculation (default `main`, fallback `master`).
- `--by-author` (default in branch-first): granularity is `(author_email, time-window)`. Window defaults to `day`; configurable via `--window`.
- `--by-merge`: granularity is by merge commit on the branch (relevant for long-lived branches that absorbed sub-features).
- `--by-window`: granularity is the classic `--window` time grouping (overrides `--by-author`).

The resolution mode is reported in the archive frontmatter (`branch_resolution: live | merged-fallback | since-sha | since-date | by-files`) so the user can audit which strategy ran.

## Vault and repo path resolution

Read {{CONFIG_FILE}} and extract `vault`, `default_scope`, and `kit_repo`. If `vault` is missing, standard error message and stop.

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

Prepare a structured Markdown with explicit delimiters to ease segmentation by the router. **The first three sections (Main, AI files context, Friction & Resolution) are mandatory in the body — `## AI files context` always present (with explicit fallback if empty), `## Friction & Resolution` always present too (with explicit fallback if no friction).** Never omit a section without its fallback line. This rule is a doctrine fix from the v0.7.0 first-run analysis (the LLM tends to silently drop empty sections).

```
# Milestone archive — {tag|sha|range}

{Main section — dated event to archive in episodes. Include:}
- Date and authors
- Files modified (counts and notable paths)
- Linked tickets and PRs
- Summary of what shipped

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

### 8. Update the persisted topology

Same logic as `mem-archeo-context` step 7, but updating:
- `Phases archeo couvertes` line: `Phase 3 (archeo-git) — N archives — last pass: {today}`.
- `Atomes dérivés des phases archeo` section: append all atoms with `source: archeo-git` AND `project: {slug}` produced by this run.

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

{{INCLUDE _linking}}

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
