# Procedure: Archive (v0.5 brain-centric)

Goal: archive the current work session so the user can `/clear` without losing context. The archive must contain everything needed to resume in a future session.

In v0.5, `mem-archive` delegates to the **semantic router** with forced-zone hint `episodes` + source `lived`. The router may segment into multiple atoms (typically: 1 main archive + N derived atoms in `40-principles`, `50-goals`, `20-knowledge` depending on what the session produced).

## Two modes

### Silent incremental mode (during the session)

At any moment, as soon as an important fact or decision emerges and is not already present in the target `context.md`:

- Update **only** the `context.md` of the current project/domain — add the line in the appropriate section (Cumulative decisions, Next steps, Active assets).
- **Do not** create an archive file. **Do not** announce the action to the user unless asked.
- Rationale: `context.md` is a mutable snapshot, designed to evolve continuously; `archives/` is reserved for end-of-session snapshots.

### Full archive mode (end of session)

Triggered by an explicit signal:
- The user types `/mem-archive` or `/clear`.
- The user says in natural language "we're stopping", "I'm leaving", "we're done", "archive".

Then run the full procedure below.

## Vault path resolution

Before any write, read the memory kit configuration file ({{CONFIG_FILE}}) and extract the `vault` field. In what follows, `{VAULT}` denotes this value. Also read `default_scope` for the default scope value.

If the file is absent or unreadable, reply:
> Memory kit not configured. Expected file: {{CONFIG_FILE}}. Run `deploy.ps1` from the kit root.

Then stop.

## Detection of the target project/domain

To determine where to archive, identify the project OR domain:

1. If the user provided `--project {slug}` or `--domain {slug}` → use it.
2. Otherwise, basename of the `cwd` → match against `{VAULT}/10-episodes/projects/` then `{VAULT}/10-episodes/domains/`.
3. If no match, ask the user: "On which project/domain should I archive this session?" + list via `/mem-list`.
4. If reply = new slug, create it (create `{VAULT}/10-episodes/projects/{slug}/` with `context.md` + `history.md` skeletons).

Also detect the current Git branch:
- Mainlines (`main`, `master`, `recette`, `dev`, `hotfix/*`, `release/*`) → archive at the global project level.
- Other branches → archive in feature: `{VAULT}/10-episodes/projects/{slug}/features/{branch-san}/archives/`. Sanitization `/` → `--`.

## Procedure (full mode)

### 1. Collect the session context

Synthesize from the ongoing conversation:

- Project/domain involved (resolved above).
- Work performed (deliverables, files created/modified).
- Decisions made and their rationale.
- Current state: phase, validated, in progress.
- Planned next steps.
- Modified files with full paths.
- Generated assets (URLs or "None").
- **Derived atoms to extract**: if the session brought out stable principles, goals, or knowledge, identify them so the router can place them in their dedicated zones.

### 2. Build the content for the router

Prepare a structured Markdown that contains:

- A **main section** (heading `# Session ...`) which will be the lived session archive (episodes zone).
- Optional **derived sections** (headings `## Principle: ...`, `## Goal: ...`, `## Concept: ...`), one per identified derived atom.

This structure lets the router easily segment into multiple atoms via Markdown delimiters.

### 3. Invoke the router

Call the semantic router with:
- `Content`: the structured Markdown.
- `Zone hint`: `episodes` (forces the main section into the episodes zone).
- `Source hint`: `lived`.
- `Metadata`: resolved project/domain, branch, scope.

{{INCLUDE _router}}

The router:
- Writes the main archive into `{VAULT}/10-episodes/{kind}/{slug}/archives/{YYYY-MM-DD-HHhMM}-{slug}-{subject}.md`.
- For each derived atom, classifies via the heuristics cascade (`## Principle:` sections go to `40-principles`, etc.).
- Creates the bidirectional links `derived_atoms` ↔ `context_origin`.

### 4. Rewrite the target context

After the router writes, **always** rewrite the entire `{VAULT}/10-episodes/{kind}/{slug}/context.md` to reflect the current snapshot.

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

`context.md` format:

```markdown
---
zone: episodes
kind: {project|domain}
slug: {slug}
scope: {personal|work}
collective: false
phase: {current phase}
last-session: YYYY-MM-DD
tags: [zone/episodes, kind/*, {project|domain}/{slug}, scope/*]
---

# {Slug} — Active context

## Current state
- Phase: {phase}
- Validated: {completed items}
- In progress: {ongoing items}

## Cumulative decisions
- {decision} — {reason}

## Next steps
1. {step}

## Active assets (URLs)
{validated URLs}
```

### 5. Update the history

The router has already added the archive line to `history.md` (see R7.5 of the router block). No additional action here.

### 6. Update the global index

The router has already added the entry to `{VAULT}/index.md`. No additional action here.

### 7. Confirm

Display to the user:

```
Archive created: {path of the main archive}
{N} derived atom(s) created in: {list of touched zones}
Context updated: {context.md path}

The /clear is safe — use /mem-recall {slug} to resume.
```
