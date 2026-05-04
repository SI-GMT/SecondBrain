# Procedure: Digest (v0.5 brain-centric)

Goal: synthesis of the last N archives of a project OR domain, or aggregation by zone (goals, principles, etc.). Useful for seeing the major arcs without re-reading every archive. **Read-only** — writes nothing in the vault.

## Trigger

The user types `/mem-digest {slug} [N]` or expresses the intent in natural language: "summarize the last N sessions of X", "do a digest of X", "give me the through-line of X", "status of open goals".

Recognized options:
- `{slug}`: slug of the project or domain. Required if no `--zone`.
- `{N}`: number of archives to synthesize. Default `5`.
- `--zone X`: digest on a whole zone instead of a project. E.g., `--zone goals --scope work` = status of work goals.
- `--scope personal|work|all`: filters by scope.
- `--since YYYY-MM-DD`: only consider archives after this date.

## Vault path resolution

Read {{CONFIG_FILE}} and extract the `vault` field. In what follows, `{VAULT}` denotes this value.

If the file is absent or unreadable, reply:
> Memory kit not configured. Expected file: {{CONFIG_FILE}}. Run `deploy.ps1` from the kit root.

Then stop.

## Procedure — project/domain mode (default)

### 1. Retrieve the arguments

- `{slug}`: slug of the project or domain. Required. If absent, ask the user via `/mem-list`.
- `{N}`: default 5.

### 2. Identify kind (project or domain)

First search in `{VAULT}/10-episodes/projects/{slug}/`, then in `{VAULT}/10-episodes/domains/{slug}/`. If not found, reply "Slug `{slug}` not found. Use `/mem-list` to see what's available." and stop.

### 3. Load the history

Read `{VAULT}/10-episodes/{kind}/{slug}/history.md`. Extract the last N archive lines (sort by date descending).

### 4. Read the selected archives

For each archive: read the content and extract **Summary**, **Decisions**, **Next steps**. Ignore **Work performed** and **Modified files** (too low-level for a digest).

### 5. Load derived atoms (new in v0.5)

For each selected archive, follow the `derived_atoms` field of the frontmatter. List the principles, goals, knowledge derived from the archives — they enrich the synthesis.

### 5.5. Load the project foundations (v0.7.2)

In addition to derived atoms born in lived sessions, load the **foundations** — atoms that frame the project but were not produced by sessions:

- `{VAULT}/99-meta/repo-topology/{slug}.md` (main topology) — gives the resolved stack, conventions, archeo coverage counts.
- Atoms with `project: {slug}` AND `source: archeo-context` — principles, goals, knowledge ADR extracted from the project's documentation.
- Atoms with `project: {slug}` AND `source: archeo-stack` — resolved layers (frontend, backend, db, ci, infra, ...).
- Branch topologies in `{VAULT}/99-meta/repo-topology/{slug}-branches/*.md` if any.

These are **not** session events — they are the **stature** of the project. Treat them separately in the synthesis (cf. step 7 format).

### 6. Synthesize

Produce a structured synthesis:

- **Major arcs**: large transitions (new phase, pivot, delivery) across successive summaries.
- **Structuring decisions**: decisions that had consequences over multiple sessions.
- **Derived atoms**: new principles / goals / concepts identified over the period.
- **Drift of next steps**: what was done vs what was abandoned/postponed.
- **Final state**: synthesis of where we stand now.

### 7. Display the report

Format:

```
## Digest — {slug} ({kind}) — last {N} sessions

Period: {start date} → {end date}

### Foundations (stable stature)

**Stack** : {one-line synthesis from main topology, or "not yet captured"}
**Conventions** : {N detected — comma-separated short list}
**archeo-context** : {N atom(s)} — {1-line summary of the dominant categories: e.g. "3 security red-lines, 2 ADR, 1 workflow heuristic"}
**archeo-stack** : {N atom(s)} — {1-line: e.g. "frontend Next.js 14, backend FastAPI, db Postgres+Supabase"}
**Workspace member** : {workspace_member or "standalone"}
**Branch topologies** : {N — list if any}

### Major arcs (sessions)
- ...

### Structuring decisions (sessions)
- ...

### Derived atoms born in sessions ({N})
- [{type}] {title} → [[link]]

### Evolution of next steps
- Announced: ...
- Done: ...
- Postponed / abandoned: ...

### Final state
{synthetic snapshot — combine foundations + last session state}
```

The **Foundations** section is the v0.7.2 fix: it captures what's **stable** about the project (its stature, its frame) — the stack, the architectural decisions, the conventions. The **session-derived** sections capture what's **moving** (decisions, deliverables, drift). The split is essential because sessions evolve fast while foundations are slow-moving — mixing them flattens the temporal signal.

## Procedure — zone mode (`--zone X`)

### 1. List the files of the zone

Recursively enumerate `{VAULT}/{NN-zone}/`. Filter by scope if applicable.

### 2. Synthesize

Depending on the zone:
- **principles**: group by `force` (red-line / heuristic / preference) then by category. Count per group. List the most recent principles.
- **goals**: group by `status` (open / in-progress / achieved / abandoned). Count per group. For open/in-progress, sort by deadline.
- **people**: group by category (colleagues / clients / family / friends). List people with recent interaction (< 30 days).
- **knowledge**: group by family (business / tech / life / methods). Count per group.
- **procedures**: group by category. List the most recent.
- **other**: flat list, sorted by date descending.

### 3. Display

Format adapted to the zone, always start with a global counter and the groupings.

## Archived projects handling (v0.7.4)

Per `core/procedures/_archived.md` (doctrinal block).

`mem-digest` **refuses by default** to digest an archived project. Surface the standard refusal:

```
✗ Project '{slug}' is archived (since {archived_at}).

  Digesting an archived project is a deliberate retrospective action,
  not a default. To proceed, re-run with --from-archived.

  Alternative: /mem-historize {slug} --revive --apply  (then digest as usual)
```

With `--from-archived` _(v0.7.4)_, proceed with the digest reading from `10-episodes/archived/{slug}/archives/`. Tag the digest output title with `(retrospective on archived project)` so the user is reminded of the context.
