## Semantic router — ingestion procedure

The router is the central ingestion component of the SecondBrain v0.5 vault. It is invoked by all ingestion skills (`mem`, `mem-archive`, `mem-doc`, `mem-archeo`, `mem-archeo-atlassian`, `mem-note`, `mem-principle`, `mem-goal`, `mem-person`) with an optional **forced-zone hint** passed by the calling skill.

### R1. Reception and preformatting

The router receives as input:

- **Content**: Markdown text (may contain several heterogeneous atoms).
- **Forced-zone hint** (optional): one of `episodes`, `knowledge`, `procedures`, `principles`, `goals`, `people`, `cognition`. If present, **bypass the heuristics cascade** for the entire content (but segmentation may still produce multiple atoms within the zone).
- **Source hint** (optional): `lived | doc | archeo-git | archeo-atlassian | manual`. Set by the calling skill. Default: `manual`.
- **Context metadata** (optional): current project/domain detected by the adapter (CWD), Git branch, default scope (`default_scope` read in `~/.claude/memory-kit.json`).

Preparation:

1. Normalize content (LF, UTF-8 without BOM — adapters already did this, but verify again).
2. Establish the **default scope**: `default_scope` value from `memory-kit.json` (or `work` if absent), overridden by any `--scope personal|work` passed by the user.
3. Establish the **current date / time** in `YYYY-MM-DD` / `HH:MM` format.

### R2. Segmentation into atoms

An input may contain a single atom (most common case: "never X" → a single principle) or several (e.g., a dev session yielding a decision + 2 principles + 1 piece of knowledge).

Segmentation heuristics, applied in order:

1. **Explicit delimiters**: Markdown `---`, or top-level list bullets separated by blank lines → each section is a candidate atom.
2. **Markdown headings** (`#`, `##`): each section under a heading is a candidate atom.
3. **Distinct verbs / rhetorical structures** within the same paragraph: "decision", "rule", "note", "contact", "TODO" → candidate atoms even without an explicit delimiter.
4. **No segmentation detected**: the entire content = a single atom.

For each candidate atom, keep:
- Its **raw text** (preserved as-is, the LLM does not rephrase).
- Its **parent context** (the rest of the content, to give context for classification).

Limit: if the router detects more than **8 atoms** in a single input, consider segmentation suspicious → group everything into a single atom sent to `00-inbox/` with a message to the user ("Segmentation > 8 atoms refused, content placed in inbox for manual reclassification").

### R3. Classification heuristics cascade

For each atom (and if no forced-zone hint), apply the cascade in priority order — **first match wins**:

| Priority | Detected clue | Target zone | Type |
|---|---|---|---|
| 1 | Forced-zone hint by the calling skill | Forced zone | (depends on zone) |
| 2 | Past-dated event + identifiable project/domain context ("yesterday", "today", "on DD/MM", concrete past-tense verbs, hint `source: lived\|archeo-*`) | `10-episodes/{kind}/{slug}/archives/` | `archive` |
| 3 | Imperative verb or step-by-step structure ("how to", "for X: step 1, 2, 3", "playbook") | `30-procedures/{scope}/{category}/` | `procedure` |
| 4 | Rule / constraint / value ("always", "never", "prefer", "avoid", "red line", "do not") | `40-principles/{scope}/{domain}/` | `principle` |
| 5 | Future intent + time horizon ("goal", "aim", "by X", deadline date, "ambition") | `50-goals/{scope}/{horizon}/` | `goal` |
| 6 | Person card (proper noun + role/relation, "colleague", "client", "friend") | `60-people/{scope}/{category}/` | `person` |
| 7 | Non-verbal production or schema reference (Excalidraw, explicit metaphor, mention of `.canvas`/`.excalidraw`) | `70-cognition/{type}/` | `schema\|metaphor\|moodboard\|sketch` |
| 8 | Stable fact / concept / definition / synthesis (description, glossary, knowledge card) | `20-knowledge/{family}/{subdomain}/` | `concept\|card\|synthesis\|glossary\|reference` |
| 9 | No clear match, ambiguous | `00-inbox/` | (left empty) |

**Scope detection** by lexical clues:

| Clue | Inferred scope |
|---|---|
| "my team", "client", "colleague", "work project", company name | `work` |
| "my family", "my health", "my child", "my vacation" | `personal` |
| No clear clue | `default_scope` from `memory-kit.json` (default `work`) |

**Project/domain detection**: if the atom explicitly mentions an existing project slug (list via `{VAULT}/10-episodes/projects/` and `{VAULT}/10-episodes/domains/`), associate it. Otherwise, use the project/domain from the **invocation context** (CWD or metadata passed by the adapter). Otherwise, leave unattached (except for zone `episodes` which always requires a `kind` + slug).

### R4. Frontmatter enrichment

For each classified atom, build a frontmatter compliant with the target zone (see `_frontmatter-universal.md` for universal fields, and section 7 of the cadrage document `docs/architecture/brain-architecture-v0.5.md` for zone-specific fields).

Fields always set:
- `date`: current date.
- `zone`: target zone.
- `scope`: `personal` or `work`.
- `collective: false` (always at initial write).
- `modality: left` (by default), `right` only if zone = `cognition`.
- `tags`: list mirroring the frontmatter (`zone/*`, `scope/*`, `kind/*` if episodes, `type/*`, etc. — see section 6 of the cadrage doc).

Zone-specific fields (see section 7 of the doc):
- **episodes**: `kind`, `project` or `domain`, `time`, `source`, `derived_atoms` (empty at creation, filled if derived atoms).
- **knowledge**: `type` (`concept|card|synthesis|glossary|reference`), `sources: []`.
- **procedures**: `type: procedure`, `steps`, `estimated_duration`, `tools`.
- **principles**: `force` (`red-line|heuristic|preference`), `context_origin` (link to founding archive if derived), `project`.
- **goals**: `horizon` (`short|medium|long`), `deadline`, `status: open`, `project`.
- **people**: `name`, `role`, `organization`, `contact`, `last_interaction`, `sensitive: true`.
- **cognition**: `type` (`schema|metaphor|moodboard|sketch`), `project`.

### R5. Target path construction

The file path follows the zone and sub-tree:

| Zone | Path |
|---|---|
| `inbox` | `{VAULT}/00-inbox/{YYYY-MM-DD}-{slug-subject}.md` |
| `episodes` (project) | `{VAULT}/10-episodes/projects/{slug}/archives/{YYYY-MM-DD-HHhMM}-{slug}-{short-subject}.md` |
| `episodes` (domain) | `{VAULT}/10-episodes/domains/{slug}/archives/{YYYY-MM-DD-HHhMM}-{slug}-{short-subject}.md` |
| `knowledge` | `{VAULT}/20-knowledge/{family}/{subdomain}/{slug-subject}.md` |
| `procedures` | `{VAULT}/30-procedures/{scope}/{category}/{slug-subject}.md` |
| `principles` | `{VAULT}/40-principles/{scope}/{domain}/{slug-subject}.md` |
| `goals` (personal) | `{VAULT}/50-goals/personal/{category}/{slug-subject}.md` |
| `goals` (work project) | `{VAULT}/50-goals/work/projects/{project-slug}/{slug-subject}.md` |
| `people` | `{VAULT}/60-people/{scope}/{category}/{name-slug}.md` |
| `cognition` | `{VAULT}/70-cognition/{type}/{slug-subject}.md` |

`{slug-subject}` is derived from the atom's subject: lowercase, accents stripped, spaces → `-`, max 60 characters, FS-invalid characters (`/\:*?"<>|`) removed.

If the parent folder does not exist, create it before writing (`New-Item -ItemType Directory -Force` or equivalent).

### R6. Ingestion plan and conditional safe mode

**If segmentation = 1 atom** (most common case) → **fluid mode**: write directly, then display the report.

**If segmentation > 1 atom** → **safe mode**: first display the **ingestion plan** and wait for user confirmation:

```
Ingestion plan (N atoms detected):
  [1] {short summary of atom 1}
      → {target path 1}  (zone: {zone}, source: {source}, scope: {scope})
  [2] {short summary of atom 2}
      → {target path 2}  (zone: {zone}, source: {source}, scope: {scope})
  ...

Continue? [y/n/e(dit)]
```

- `y` (yes) → write all atoms per the plan.
- `n` (no) → cancel, write nothing.
- `e` (edit) → allow the user to modify an atom's classification (change zone, scope, or reject this atom) before writing.

**User flags**:
- `--no-confirm`: force fluid mode even on multi-atoms (useful in batch / scripts).
- `--dry-run`: force safe mode without writing (plan inspection only, automatic `n` return after display).

### R7. Writing

For each accepted atom in the plan:

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

{{INCLUDE _linking}}

Steps per atom:

1. **Build the final Markdown content**: frontmatter (R4) + note body (raw atom text with minimal formatting).
2. **Check invariants** (see `_frontmatter-universal.md` section "Invariants to check at write time") — if violated, report to the user and write to `00-inbox/` with tag `invariant-violation` instead of the target zone.
3. **Create the parent folder** if missing.
4. **Write via atomic rename** (Pattern 1).
5. If the target zone is `episodes`: update the project/domain `history.md` via **atomic rename + hash check** (Pattern 2). Add a line `- [YYYY-MM-DD HHhMM — {subject}](archives/{archive-name}.md)`.
6. If the atom has a `derived_atoms` (parent atom that generated this one): enrich the parent atom by adding `derived_atoms: [..., "[[new-atom]]"]`. Bidirectionality.
7. Update `index.md` (atomic rename + hash check): add an entry in the `Archives` section (episodes zone only) or simply maintain the global counter.

### R8. Bidirectional links (derived atoms)

When an atom A in zone `episodes` generates an atom B in **another zone** (principle, goal, knowledge, procedure, person card, cognitive production — regardless of the target zone), create a **bidirectional link**:

- In A (`10-episodes/...`): add to the frontmatter `derived_atoms: ["[[relative-path-to-B]]"]`.
- In B (target zone, **all zones combined**): set `context_origin: "[[relative-path-to-A]]"`.

**Universal rule** (clarified v0.5.0.1 following Gemini archeo mcp-iris-connector field feedback): `context_origin` is mandatory on **every derived atom**, not only on principles. This includes:

- Concepts in `20-knowledge/` extracted from an archive or a Confluence page.
- Procedures in `30-procedures/` extracted from a session archive.
- Principles in `40-principles/` extracted from an archive or a decision.
- Goals in `50-goals/` formulated within a lived session.
- Person cards in `60-people/` mentioned for the first time in an archive.
- Cognitive productions in `70-cognition/` linked to a session.

Without this symmetry, derived atoms become orphans: `mem-recall` can no longer go from the archive to the atoms or vice versa, and the Obsidian Graph view loses the lineage.

**Bidirectionality schema**:

```
Archive (10-episodes)              Derived atom (20-* to 70-*)
┌────────────────────┐             ┌─────────────────────────┐
│ frontmatter:       │             │ frontmatter:            │
│   derived_atoms: [ │ ─────────→  │   context_origin:     │
│     [[B1]],        │             │     "[[A]]"             │
│     [[B2]],        │ ←─────────  │                         │
│     ...            │             │                         │
└────────────────────┘             └─────────────────────────┘
```

Obsidian Graph will make the lineage visible in both directions. This bidirectionality is essential so that `mem-recall {project}` can load not only the archives but also the principles/goals/knowledge/people derived from the project.

### R9. User report

At the end of writing, display a **synthetic report**:

```
✓ {N} atom(s) ingested:
  [1] {subject} → {path}
  [2] {subject} → {path}
  ...

Links: {N} bidirectional links created (visible in Obsidian Graph).
Suggested next steps: {open the vault | reclassify via /mem-reclass | view the index}.
```

If some atoms were rejected (safe mode with `n` or `e`), list them in the report:

```
✗ {M} atom(s) not written (rejected by user):
  [3] {subject} — rejected
```

### R10. Idempotence (for `mem-archeo*` skills)

When the router is invoked by `mem-archeo` or `mem-archeo-atlassian` (retro-archiving), it must avoid **recreating atoms already ingested** during a previous pass.

Mechanism:
- The atom carries an origin identifier: `source_milestone` (commit SHA for archeo-git, page ID for archeo-atlassian) + `source_atom_type` (event/principle/concept/etc.) + `source_atom_subject` (short slug of the subject).
- Before writing, the router searches the vault for a file with the same 3 fields. If found:
  - If content identical → silent skip.
  - If content modified → create a new version with `previous_atom: [[old]]` + tag `revision`. Preserves the immutability of historical archives.

This logic does **not** apply to lived ingestion skills (`mem-archive`, `mem-note`, etc.): these skills always produce new content, no risk of duplicate.
