# Procedure: Archeo (v0.5 brain-centric)

Goal: **reconstruct the history of an existing Git repository** as dated archives, **and derived atoms** (principles, technical concepts) extracted from each milestone. Lets you bootstrap a project in the memory kit with rich context reconstructed after the fact.

In v0.5, `mem-archeo` no longer produces a monolithic archive per milestone — it segments via the router, which can generate several atoms spread across multiple zones (1 archive in `episodes` + N principles in `40-principles` + N concepts in `20-knowledge`).

## Trigger

The user types `/mem-archeo [repo-path]` or expresses intent in natural language: "do a Git retro of this project", "reconstruct the history", "archeo on this repo".

Arguments:
- `{repo-path}` (optional, default = CWD): absolute path to a local Git repository.
- `--project {slug}`: forces the target project.
- `--level {tags|releases|merges|commits}`: forces the granularity level.
- `--since YYYY-MM-DD` / `--until YYYY-MM-DD`: time bounds.
- `--window {day|week|month}`: grouping size for `commits` level.
- `--dry-run`: lists the milestones that would be ingested, without writing.
- `--no-confirm`: passes through to the router in fluent mode even on multi-atoms.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault` and `default_scope`. If missing, standard error message and stop.

## Procedure

### 1. Validate the source repository

- Verify that `{repo-path}` is a Git repository (`git -C {path} rev-parse --git-dir`).
- Otherwise, stop with a clear message.

### 2. Resolve the target project/domain

By priority:
1. Explicit `--project {slug}` or `--domain {slug}`.
2. Match the repo basename against existing slugs in `{VAULT}/10-episodes/projects/` then `domains/`.
3. Ask the user (with `/mem-list` as support).
4. If new slug → create the structure `{VAULT}/10-episodes/projects/{slug}/context.md` + `history.md` + `archives/`.

### 3. Detect the granularity level

If `--level` not provided, choose automatically (first one returning >0):

1. **Semver tags** (`v*.*.*`) → 1 archive per tag.
2. **GitHub releases** (via `gh release list` if available) → 1 archive per release.
3. **Merges on mainline** (`git log --merges main`) → 1 archive per merge.
4. **Commit windows** (week/month) → 1 archive per window.

Display the choice to the user and ask for confirmation before proceeding.

### 4. For each milestone: prepare the content

For each milestone (tag, release, merge, window) within the time window `--since`/`--until`:

#### a. Verify idempotence

Search the vault for an existing atom with:
- `source: archeo-git`
- `source_milestone: {tag|sha|range}` matching the current milestone.

If found, **silent skip** (already ingested) unless the milestone has changed (e.g. moved tag) — in which case create a revision with `previous_atom: [[old]]`.

#### b. Extract milestone information

Depending on the level:
- **Tag/release**: tag message, GitHub release note content (`gh release view`), commit SHA, date, main author, modified files (diff stats).
- **Merge**: merge message, source branch, files, referenced tickets (regex `[A-Z]+-\d+` for Jira, `#\d+` for PR).
- **Commit window**: aggregation of commit messages within the window, touched files, contributors.

Enrich with:
- **Root AI files** at the time of commit: `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `MISTRAL.md`, `README.md`, `context.md`, `history.md` if present (read via `git show {sha}:{file}`).
- **Jira/Linear tickets**: extract keys from the message + reference.
- **Linked PRs**: `gh pr view {number}` if available.

#### c. Build the content for the router

Prepare a structured Markdown with Markdown delimiters to ease segmentation by the router:

```
# Milestone archive — {tag|sha|range}

[Main section — dated event to archive in episodes]

## Principle: [short title] [if extracted]

[If the milestone surfaced an explicit principle, formulate it here]

## Concept: [short title] [if extracted]

[If the milestone introduces a reusable technical concept, formulate it here]
```

### 5. Invoke the router for this milestone

Call the router with:
- `Content`: structured Markdown of the milestone.
- `Hint zone`: `episodes` (forces the main section).
- `Hint source`: `archeo-git`.
- `Metadata`: resolved project/domain, **`source_milestone: {tag|sha|range}`**, `commit_sha`, scope.

{{INCLUDE _router}}

The router:
- Writes the main archive into `{VAULT}/10-episodes/{kind}/{slug}/archives/`.
- For each derived section (`## Principle:`, `## Concept:`), classifies via the cascade.
- Creates bidirectional links.
- Verifies idempotence via `source_milestone + type + subject` (cf. R10 of the router block).

### 6. Loop over all milestones

If `--dry-run`: display the list of milestones that would be ingested (with planned derived atoms) + estimated total. Ask for confirmation to switch to `--apply`.

Otherwise: iterate over all milestones. The router handles user confirmation in safe mode (default), or direct write if `--no-confirm`.

### 7. Final report

Global synthesis: N milestones processed, N archives created, N derived atoms (per zone), N skips (idempotence).
