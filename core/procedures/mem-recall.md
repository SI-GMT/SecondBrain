# Procedure: Recall (v0.5 brain-centric)

Goal: retrieve the work context from the vault after a `/clear` or at the start of a new session. Allow the user to resume in 30 seconds without manual re-briefing. In v0.5, recall loads not only the session archives but also the **active principles**, **open goals** and **key people** attached to the project/domain — to give a complete context, not only an episodic one.

## Trigger

### Automatic (without the user typing `/mem-recall`)

Trigger the full procedure as soon as the user expresses, in natural language:

- A resume intent: "resume", "let's continue", "where were we on X", "shall we resume?", "let's get back to it".
- A need to consult memory: "do you remember…", "what did we decide for…", "what did we do again?", "remind me…".

If the signal is ambiguous (the target project or domain is unclear), ask: "Do you want me to load the context of {name}?" before executing.

### Explicit

The user invokes `/mem-recall` with or without an argument. The optional argument is the name of the project or domain to load.

Recognized options:
- `--scope personal|work|all`: filters attached items by scope. Default: `all`.
- `--zone {list}`: limits loading to certain zones (default: all zones attached to the project/domain).

## Vault path resolution

Before any read, read the memory kit configuration file ({{CONFIG_FILE}}) and extract the `vault` field. In what follows, `{VAULT}` denotes this value. Also read `default_scope` from the same file to know the default scope value.

If the file is absent or unreadable, reply:
> Memory kit not configured. Expected file: {{CONFIG_FILE}}. Run `deploy.ps1` from the kit root.

Then stop.

## Procedure

### 1. Identify the project or domain

In this order:

1. **Argument provided**: use the value given by the user. The router first searches in `{VAULT}/10-episodes/projects/{slug}/`, then in `{VAULT}/10-episodes/domains/{slug}/`.
2. **Auto-detection**: take the basename of the `cwd`. If this name matches an existing slug in `projects/` or `domains/`, use it.
3. **Interactive fallback**: read `{VAULT}/index.md`, display the list of projects AND domains, and ask the user which to load.
4. **Empty vault or no project/domain**: reply "No project/domain found. Memory initialized — {VAULT}/index.md is ready. Describe what you're working on and we'll start." then stop.

In what follows, `{kind}` denotes `projects` or `domains`, and `{slug}` the identified slug.

### 2. Load the current context (fast path)

**If `{VAULT}/10-episodes/{kind}/{slug}/context.md` exists**: read it first. It is the synthesized current state (mutable snapshot). Fast path.

**Otherwise**: read the latest archive listed in `history.md`. Extract: project state, decisions, next steps, assets.

### 3. Load the history

Read `{VAULT}/10-episodes/{kind}/{slug}/history.md` to see the chronological session thread.

### 3.5. Load repo topology (new in v0.7.0)

If `{VAULT}/99-meta/repo-topology/{slug}.md` exists, read it. Extract:

- The **resolved stack** (from the `## Stack résolue` section).
- The **detected conventions** (from `## Conventions détectées`).
- The **archeo coverage** counts (from `## Phases archeo couvertes`): how many atoms per phase, last pass dates.

This gives the LLM the full **stature** of the project — its shape and scaffolding — not just the last session. It's what keeps the briefing from being amnesic on technical context.

If the file is absent: skip the section. The briefing at step 5 will indicate: "Project topology not yet captured — run /mem-archeo to populate".

### 4. Load attached items (new in v0.5)

The project/domain projects **transversally** into multiple zones via the tags `project/{slug}` or `domain/{slug}`. Load:

| Zone | Filter | Why |
|---|---|---|
| `40-principles/` | tag `project/{slug}` or `domain/{slug}`, **filtered by scope** if `--scope` | Active principles born in this project or applying to it — the LLM must respect them during the session. |
| `50-goals/` | tag `project/{slug}` + `status: open\|in-progress` | Active goals — to orient the next steps. |
| `60-people/` | mentioned in the last 3 archives or linked via project tag | Key people of the project — useful to preserve relational context. |
| `20-knowledge/` | tag `project/{slug}` + `source: archeo-context\|archeo-stack` | Architectural decisions and resolved stack/patterns surfaced by the archeo. |

Implementation: grep on `{VAULT}/40-principles/`, `{VAULT}/50-goals/`, `{VAULT}/60-people/`, `{VAULT}/20-knowledge/` for the relevant tags. Limit to 5 items per zone if too many (display "+N more" at the end).

When the topology is present, the architectural knowledge listed under `Atomes dérivés des phases archeo` in the topology file gives the LLM the **direct list** of relevant atoms — no need to grep blindly.

### 5. Present the briefing

Reply format:

```
## Resume — {Project or Domain} ({kind})

**Last session**: {date} — {summary}
**Current phase**: {phase}
**Scope**: {personal|work}

### Project topology

**Stack** : {one-line synthesis from topology, or "Not yet captured"}
**Conventions** : {N items}
**Workspace member** : {workspace_member name from context.md if set, otherwise "standalone"}
**Archeo coverage** :
  - context: {N atoms}, last pass {date}
  - stack:   {N atoms}, last pass {date}
  - git:     {N archives}, last pass {date}
**Branch topologies known** : {N — list wikilinks if N > 0, or "none — only main"}

(If topology absent: "Not yet captured. Suggest: /mem-archeo to populate.")

### State
- Validated: …
- In progress: …

### Key decisions
- …

### Active principles ({N})
- {force} — {short title} → [[link]]
- …

### Open goals ({N})
- [{horizon}] {title} (deadline: {date}) → [[link]]
- …

### Architecture & stack atoms ({N})
- {detected_layer or extracted_category} — {short title} → [[link]]
- …

### Key people
- {name} ({role}) — last interaction {date} → [[link]]

### Next steps
1. …
2. …

### Available assets
- {URLs or "None"}
```

Adapt the briefing to the requested scope: if `--scope personal`, hide `work` items and conversely.

### 6. Propose what's next

Ask: "Do we resume at step {X}?"

If the user confirms, read the necessary project files and start the work.

## Archived projects handling (v0.7.4)

Per `core/procedures/_archived.md` (doctrinal block):

- **Without an explicit slug**, the auto-detection from CWD or the inventory used to disambiguate **excludes** projects under `10-episodes/archived/`. The implicit briefing flow never touches them.
- **With an explicit slug** (`/mem-recall {slug}` or natural-language equivalent like "reprends codemagdns"), look up the slug in BOTH `10-episodes/projects/{slug}/` and `10-episodes/archived/{slug}/`. The first match wins. If only the archived location matches, load it and signal in the briefing that the project is archived (date from `archived_at`).

When loading an archived project, prepend the briefing with:

```
ℹ️ Project '{slug}' is currently archived (since {archived_at}).
   Loaded for read-only retrospective. To resume actively, run:
     /mem-historize {slug} --revive --apply
```

After this notice, proceed with the standard briefing. The user can read, ask questions, navigate the history; if they want to write or commit changes via `mem-archive`, that skill will refuse with a hard error and re-suggest `--revive`.
