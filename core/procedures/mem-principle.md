# Procedure: Principle (new in v0.5)

Goal: quickly ingest a principle (heuristic, red line, value, action rule) into `40-principles/`. Explicit shortcut when the user explicitly formulates a rule.

## Trigger

The user types `/mem-principle {content}` or expresses intent in natural language: "note this principle", "add this rule", "red line", "always / never".

Recognized options:
- `--scope personal|work`: forces the scope.
- `--force red-line|heuristic|preference`: forces the constraint level. Otherwise the router infers it from the tone ("never" = red-line, "prefer" = heuristic, "I like" = preference).
- `--domain X`: forces the sub-category (dev, communication, life, health, etc.).
- `--project {slug}`: forces attachment to the origin project. Otherwise, current project if detected.
- `--no-confirm`, `--dry-run`: passed through to the router.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault` and `default_scope`. If missing, standard error message and stop.

## Procedure

### 1. Pre-format

The principle title is extracted from the first significant words ("never X" → title "no-x"). The body is the full content, which can include the **origin context** (incident, reading, experience that surfaced the principle).

### 2. Invoke the router with forced zone hint

Call the router with:
- `Content`: the principle content.
- `Hint zone`: `principles`.
- `Hint source`: `manual` (unless extracted by `mem-archive` which will pass `lived`).
- `Metadata`: force, domain, origin project if provided.

{{INCLUDE _router}}

The router:
- Determines `force` (red-line / heuristic / preference) if not forced.
- Determines the domain sub-category.
- Writes into `{VAULT}/40-principles/{scope}/{domain}/{slug-title}.md`.
- Builds the frontmatter with `type: principle`, `force`, `origin_context` (if derived from an archive), `project`, `tags`.
- If invoked from a parent archive (case of `mem-archive` extracting principles), sets the bidirectional link `derived_atoms` ↔ `origin_context`.

### 3. Confirm

Router report.
