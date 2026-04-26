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

### 4. Load attached items (new in v0.5)

The project/domain projects **transversally** into multiple zones via the tags `project/{slug}` or `domain/{slug}`. Load:

| Zone | Filter | Why |
|---|---|---|
| `40-principles/` | tag `project/{slug}` or `domain/{slug}`, **filtered by scope** if `--scope` | Active principles born in this project or applying to it — the LLM must respect them during the session. |
| `50-goals/` | tag `project/{slug}` + `status: open\|in-progress` | Active goals — to orient the next steps. |
| `60-people/` | mentioned in the last 3 archives or linked via project tag | Key people of the project — useful to preserve relational context. |

Implementation: grep on `{VAULT}/40-principles/`, `{VAULT}/50-goals/`, `{VAULT}/60-people/` for the relevant tags. Limit to 5 items per zone if too many (display "+N more" at the end).

### 5. Present the briefing

Reply format:

```
## Resume — {Project or Domain} ({kind})

**Last session**: {date} — {summary}
**Current phase**: {phase}
**Scope**: {personal|work}

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
