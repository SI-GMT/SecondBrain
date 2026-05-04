# Procedure: Search (v0.5 brain-centric)

Goal: full-text search in the memory vault with multidimensional filters (zone, scope, kind, modality, project, domain, type, source). Return occurrences with context, grouped by file and sorted by relevance.

## Trigger

The user types `/mem-search {query}` or expresses the intent in natural language: "search in memory X", "find notes that talk about Y", "where did we talk about Z?".

Recognized options:
- `--zone {list}`: limits to the given zones (e.g., `--zone principles`, `--zone episodes,knowledge`).
- `--scope personal|work|all`: filters by scope. Default: `all`.
- `--kind project|domain`: filters episodes by sub-logic.
- `--modality left|right`: filters by hemispheric modality.
- `--project {slug}`: filters by attached project.
- `--domain {slug}`: filters by attached domain.
- `--type {value}`: filters by note type (e.g., `--type principle`).
- `--source {value}`: filters by source (`lived|doc|archeo-context|archeo-stack|archeo-git|archeo-atlassian|manual`). Wildcard `archeo-*` matches any of the four archeo sources (v0.7.2).
- `--branch {name}`: filters by branch (frontmatter `branch:` field — only relevant for archeo-* atoms produced in branch-first mode, v0.7.2).
- `--extracted-category {value}`: filters archeo-context atoms by `extracted_category` (`workflow|sync|multi-tenant|security|adr|goal|other`, v0.7.2).
- `--detected-layer {value}`: filters archeo-stack atoms by `detected_layer` (`frontend|backend|db|ci|infra|tests|tooling|other|ambient`, v0.7.2).
- `--author {email-or-name}`: filters archeo-git atoms by `author_email` or `author_name` (v0.7.2). Substring match, case-insensitive.
- `--limit N`: max number of matches (default 50).
- `--case-sensitive`: opt-in for case-sensitive search (default is case-insensitive).
- `--include-archived` _(v0.7.4)_: also scan `10-episodes/archived/**`. Default behaviour skips it (see Archived projects handling below).
- `--archived-only` _(v0.7.4)_: search only inside `10-episodes/archived/**`. Mutually exclusive with `--include-archived`.

## Vault path resolution

Read {{CONFIG_FILE}} and extract the `vault` field. In what follows, `{VAULT}` denotes this value.

If the file is absent or unreadable, reply:
> Memory kit not configured. Expected file: {{CONFIG_FILE}}. Run `deploy.ps1` from the kit root.

Then stop.

## Procedure

### 1. Retrieve the query and filters

The query is the main argument (first non-option token). If empty: reply "Specify what you're looking for: `/mem-search {keyword or phrase}`." and stop.

- Case-insensitive search by default.
- Quote support for exact phrase.
- The `--xxx` options are parsed and used as filters in R3.

### 2. Default search scope

Recursively scan the 9 root zones:

```
{VAULT}/00-inbox/
{VAULT}/10-episodes/projects/
{VAULT}/10-episodes/domains/
{VAULT}/20-knowledge/
{VAULT}/30-procedures/
{VAULT}/40-principles/
{VAULT}/50-goals/
{VAULT}/60-people/
{VAULT}/70-cognition/
{VAULT}/99-meta/
```

If `--zone X` is provided, restrict to the listed zones.

**Always exclude**:

- `.obsidian/` and descendants.
- Files `*.canvas`, `*.excalidraw.md`, `*.base` (non-textual content).
- `.trash/` if present.

### 3. Run the search

Use a suitable search tool (Grep, ripgrep or equivalent):

- Mode: `content` with 2 lines of context before/after each match.
- Limit: `--limit` (default 50). If reached, signal it.

### 4. Filter by frontmatter

For each matching file, read its frontmatter and apply the filters:

- `--scope`: keep only files with `scope: {value}` (or `all` = all).
- `--kind`: keep only files with `kind: {value}`.
- `--modality`: keep only files with `modality: {value}`.
- `--project`: keep only files with `project: {slug}` or tag `project/{slug}`.
- `--domain`: keep only files with `domain: {slug}` or tag `domain/{slug}`.
- `--type`: keep only files with `type: {value}`.
- `--source`: keep only files with `source: {value}`. Wildcard `archeo-*` matches any of `archeo-context | archeo-stack | archeo-git | archeo-atlassian`.
- `--branch`: keep only files with `branch: {value}` (v0.7.2 — non-empty value match, useful to find atoms produced on a specific feature branch).
- `--extracted-category`: keep only archeo-context atoms with `extracted_category: {value}` (v0.7.2).
- `--detected-layer`: keep only archeo-stack atoms with `detected_layer: {value}` (v0.7.2).
- `--author`: keep only files where `author_email` OR `author_name` contains the substring (case-insensitive, v0.7.2).

### 5. Sort and group

- Group matches by file.
- Sort files: `episodes` zones first (recent archives at top), then other zones in alphabetical order. Within the same zone, timestamped archives sorted by date descending.

### 6. Display the report

Format:

```
## Search: "{query}" ({N active filters})

{N} occurrence(s) in {M} file(s).

### [{zone}] {path relative to vault} ({k} matches)
> line 42: ... {line with match} ...
> line 58: ... {line with match} ...

### [{zone}] {path} ({k} matches)
> ...

...
```

If no match:

```
## Search: "{query}"

No occurrence found in the vault (active filters: {list}).
```

### 7. Suggest what's next

If the results mostly concern a project/domain (recurring slug in the results), suggest: "Do you want me to load the context of `{slug}`?" — which will trigger `/mem-recall {slug}`.

## Archived projects handling (v0.7.4)

Per `core/procedures/_archived.md` (doctrinal block).

By default, `mem-search` **excludes** `10-episodes/archived/**` from the scan. The summary line should reflect this, e.g.:

```
Found {N} match(es) across {M} file(s). (Archived projects skipped — use --include-archived to include.)
```

If `--include-archived`, also scan archived/ and tag each archived-result line with `[archived]` after the file path. The grouping by file remains the same.

If `--archived-only`, scan only archived/ and report:

```
Found {N} match(es) across {M} file(s) in archived projects.
```

When the user invokes `mem-search` from inside an archived project (CWD match), neither flag is needed — search the project even if archived. This is the "explicit context wins" rule.
