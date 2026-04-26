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

### Major arcs
- ...

### Structuring decisions
- ...

### Derived atoms ({N})
- [{type}] {title} → [[link]]

### Evolution of next steps
- Announced: ...
- Done: ...
- Postponed / abandoned: ...

### Final state
{synthetic snapshot}
```

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
