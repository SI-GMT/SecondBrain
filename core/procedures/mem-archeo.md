# Procedure: Archeo orchestrator (v0.7.0)

Goal: orchestrate the **three phases** of the v0.7.0 archeo on a Git repository — Phase 1 organizational/decisional/functional context, Phase 2 technical stack, Phase 3 temporal Git history. Produces a coherent set of atoms that contextualize the project across organizational, technical and temporal dimensions, and persists a topology snapshot.

This is the entry point for users who want a complete archeo. The three sub-skills (`mem-archeo-context`, `mem-archeo-stack`, `mem-archeo-git`) remain individually invocable for targeted runs, but the orchestrator is the recommended path on a fresh project — it shares the Phase 0 topology scan across all three phases (single source of truth) and produces a unified report.

## Why three phases

The 3-LLM comparative analysis (`docs/analyses/2026-04-28-mem-archeo-comparatif-3-llm.md`) showed that running archeo on Git history alone produces inconsistent results across LLMs because each one extrapolates the missing organizational and technical context differently. Phases 1 and 2 establish that context **before** Phase 3 reads the commits, so Phase 3 atoms contextualize commits against a known substrate (e.g. CORS commits read as a known battle when the stack is "self-hosted Supabase + separate frontend"). The result becomes deterministic across LLMs.

## Trigger

The user types `/mem-archeo [repo-path]` or expresses intent in natural language: "do a full archeo of this project", "reconstruct the project context, stack and history".

Arguments:
- `{repo-path}` (optional, default = CWD): absolute path to a local Git repository.
- `--project {slug}`: forces the target project.
- `--depth {N}`: max recursion depth for the topology scan (default 2).
- `--skip-phase {context|stack|git}`: skip one or more phases (comma-separated, e.g. `--skip-phase context,stack`).
- `--only-phase {context|stack|git}`: shortcut for executing a single phase (mutually exclusive with `--skip-phase`).
- `--level {tags|releases|merges|commits}`: passed through to Phase 3.
- `--since YYYY-MM-DD` / `--until YYYY-MM-DD`: time bounds for Phase 3.
- `--window {day|week|month}`: grouping size for Phase 3.
- `--dry-run`: lists what would be done in each phase without writing.
- `--no-confirm`: passes through to the router in fluent mode for all phases.
- `--rescan`: ignores any persisted topology and forces a fresh scan.

## Vault and repo path resolution

Read {{CONFIG_FILE}} and extract `vault`, `default_scope`, and `kit_repo`. If `vault` is missing, standard error message and stop.

## Procedure

### 1. Validate the source repository

Verify that `{repo-path}` is a Git repository (`git -C {repo-path} rev-parse --git-dir`). If not, stop with a clear message.

### 2. Resolve the target project

By priority:

1. Explicit `--project {slug}`.
2. Match `basename({repo-path})` against existing slugs in `{VAULT}/10-episodes/projects/`.
3. Match the repo's `git remote get-url origin` against existing `repo_remote` fields in any `99-meta/repo-topology/*.md`.
4. Ask the user (with `/mem-list` as support).
5. If new slug → create the structure `{VAULT}/10-episodes/projects/{slug}/` with `context.md` + `history.md` skeletons. Set `repo_path: {repo-path}` in the new context.md frontmatter.

### 3. Phase 0 — Topology scan (shared)

{{INCLUDE _repo-topology}}

Phase 0 is run **once** by the orchestrator and the resulting in-memory `topology` object is passed to each sub-phase. This avoids triplicated scans.

If `{VAULT}/99-meta/repo-topology/{slug}.md` already exists and `--rescan` is not set, load it instead of re-scanning.

### 4. Run the phases in sequence

Execute the phases in the order: **context → stack → git**. The order matters because:

- Phase 2 (stack) authoritatively resolves the stack and overwrites the lightweight `stack_hints` from Phase 0. If we ran Phase 3 first, friction detection would lack the stack context.
- Phase 1 (context) extracts goals and principles from docs. Phase 3 may reference these (e.g. a commit that addresses a known cadrage goal). If we ran Phase 3 first, the cross-referencing would be partial.

If `--only-phase {phase}` is set, run only that phase. If `--skip-phase {list}` is set, exclude those phases.

#### a. Phase 1 — `mem-archeo-context`

Invoke the procedure described in `mem-archeo-context.md` with:
- The shared `topology` object (skip its own Phase 0 scan).
- The resolved `{slug}`.
- All passed-through arguments (`--depth`, `--no-confirm`, `--dry-run`).
- Phase-specific arguments if any (`--only-categories`, but the orchestrator does not pass per-phase scoping unless explicitly given).

Capture the structured result: list of atoms created/revised/skipped, by category.

#### b. Phase 2 — `mem-archeo-stack`

Invoke the procedure described in `mem-archeo-stack.md` with the shared topology and the resolved slug.

Capture the structured result: list of atoms created/revised/skipped, by layer. After Phase 2, the `stack_hints` are superseded by the resolved stack — the orchestrator updates its working memory with the resolved values for use by Phase 3.

#### c. Phase 3 — `mem-archeo-git`

Invoke the procedure described in `mem-archeo-git.md` with the shared topology, the resolved slug, the resolved stack from Phase 2, and the level/since/until/window arguments.

Capture the structured result: list of milestones processed, archives created, derived atoms, friction sequences surfaced, cross-links added.

### 5. Update the persisted topology

After all enabled phases have completed, write or update `{VAULT}/99-meta/repo-topology/{slug}.md` with:

- Frontmatter per `docs/architecture/v0.7.0-archeo-and-base-skills-alignment.md` §2.2:
  - `date`, `zone: meta`, `type: repo-topology`, `project: {slug}`.
  - `repo_path`, `repo_remote`.
  - `content_hash` of the body.
  - `previous_topology_hash` from the existing file if any.
  - `last_archive` empty (Phase 3 hasn't been called from `mem-archive` here).
- Body per §2.3:
  - Categories from the in-memory topology.
  - Stack résolue from Phase 2 (or the `stack_hints` from Phase 0 if Phase 2 was skipped).
  - Conventions détectées.
  - **Phases archeo couvertes** — one line per phase that ran in this orchestrator invocation, with count and timestamp.
  - **Atomes dérivés des phases archeo** — full list of atoms produced (across all phases that ran), as wikilinks.

If the topology already exists with a different `content_hash`, capture the old hash in `previous_topology_hash` and atomically rename-write the new file.

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

{{INCLUDE _linking}}

### 6. Unified final report

Display:

```
mem-archeo orchestrator — {slug}

Repo                  : {repo_path}
Topology              : {created | updated | unchanged}
Phases executed       : {context, stack, git}  (skipped: {list})

Phase 1 — archeo-context
  Documents read      : {N}
  Atoms created       : {N}
  Atoms revised       : {N}
  Atoms skipped       : {N}

Phase 2 — archeo-stack
  Layers resolved     : {N}
  Atoms created       : {N}
  Atoms revised       : {N}
  Atoms skipped       : {N}
  Stack résolue       : {one-line synthesis}

Phase 3 — archeo-git
  Milestones          : {N}
  Archives created    : {N}
  Archives revised    : {N}
  Derived atoms       : {N}
  Friction sequences  : {N}
  Cross-links added   : {N}

Total atoms in vault  : {N}
Project briefing      : run /mem-recall {slug} to see the full picture
```

## Invariants

- **Phase 0 runs once.** Sub-phases consume the in-memory topology; they do not re-scan unless explicitly invoked standalone with `--rescan`.
- **Order context → stack → git** is fixed. Reordering breaks the contextualization chain.
- **Topology is persisted at the end**, after all enabled phases have completed. A failure mid-phase leaves the topology in its previous state (no partial write of the topology summary).
- **Canonical write paths only.** Same invariant as the sub-phases.
