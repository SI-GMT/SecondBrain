# Procedure: List (v0.5 brain-centric)

Goal: display the vault inventory (projects, domains, contents by zone) with a synthetic state. Renamed from `mem-list-projects` in v0.5 because it now also lists domains and can filter by zone.

## Trigger

The user types `/mem-list` or expresses the intent in natural language: "list my projects", "what projects do I have in memory?", "show me all the domains", "vault inventory".

Recognized options:
- `--kind project|domain|all`: restricts the inventory. Default: `all` (projects + domains).
- `--scope personal|work|all`: filters by scope. Default: `all`.
- `--zone {list}`: lists the contents of the given zones instead of the projects/domains inventory (e.g., `--zone principles` = list of principles).
- `--detail`: also shows counters per zone and the latest event.

## Vault path resolution

Read {{CONFIG_FILE}} and extract the `vault` field. In what follows, `{VAULT}` denotes this value.

If the file is absent or unreadable, reply:
> Memory kit not configured. Expected file: {{CONFIG_FILE}}. Run `deploy.ps1` from the kit root.

Then stop.

## Procedure — inventory mode (default)

### 1. Enumerate projects and domains

List the subfolders of:
- `{VAULT}/10-episodes/projects/` → kind=project
- `{VAULT}/10-episodes/domains/` → kind=domain

For each slug, read its `context.md` to retrieve:
- `scope` (filter if `--scope` active).
- `phase` (frontmatter field or first line of the State section).
- `last-session` (frontmatter).
- Counter of archives in `archives/`.
- `repo_path` and `workspace_member` if present (v0.7.x signals).

Then enrich with **archeo coverage** (v0.7.2) by checking:

- Topology presence: `{VAULT}/99-meta/repo-topology/{slug}.md` → 1 if exists, 0 otherwise.
- Branch topologies: count files in `{VAULT}/99-meta/repo-topology/{slug}-branches/*.md`.
- Per-source archeo atom counts: grep across `40-principles/`, `50-goals/`, `20-knowledge/` for atoms carrying `project: {slug}` AND `source: archeo-context|archeo-stack|archeo-git`. Group by source.

### 2. Display the inventory

Base format:

```
## SecondBrain vault — Inventory

### Projects ({N}) — finite vocation
- **{slug}** ({scope}) — phase: {phase} — {N} archive(s) — last: {date} — archeo: {topology-flag}{branches-flag}{atoms-counts}
- ...

### Domains ({N}) — permanent
- **{slug}** ({scope}) — phase: {phase} — {N} archive(s) — last: {date}
- ...
```

The archeo annotation on the project line uses compact glyphs:

- `T` if main topology present, `-` otherwise.
- `B{N}` if N branch topologies known (omitted if 0).
- `[{C}c {S}s {G}g]` for atom counts: `C` archeo-context, `S` archeo-stack, `G` archeo-git. Omitted entirely if all zero.

Example: `archeo: T B2 [7c 4s 13g]` means main topology present, 2 branches tracked, 7 archeo-context + 4 archeo-stack + 13 archeo-git atoms.

If `--detail`:

```
- **{slug}** ({scope})
  Phase: {phase}
  Archives: {N}
  Attached principles: {N}
  Open goals: {N}
  Linked people: {N}
  Last session: {date}
  Repo: {repo_path or "—"}
  Workspace member: {workspace_member or "standalone"}
  Archeo coverage:
    Main topology: {present|absent}
    Branch topologies: {N} ({list of branch names if any})
    archeo-context: {N} atom(s)
    archeo-stack:   {N} atom(s) (incl. {N} ambient)
    archeo-git:     {N} archive(s) ({split: standard / branch-first if applicable})
```

## Procedure — zone list mode (`--zone X`)

If `--zone X` is provided, list the contents of the zone instead of the projects/domains inventory.

### 1. List the files of the zone

Recursively enumerate the `.md` under `{VAULT}/{NN-zone}/` and read their frontmatter.

### 2. Filter by scope if `--scope` active

### 3. Display

Format:

```
## SecondBrain vault — Zone {zone}

{N} item(s) found.

### {subfolder 1}
- [{title}]({path}) — {scope}, {date}
- ...

### {subfolder 2}
- ...
```

## Minimal output

If the vault is empty or contains neither projects nor domains:

```
Empty vault. Create your first project or domain via /mem-archive or /mem.
```
