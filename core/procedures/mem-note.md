# Procedure: Note (new in v0.5)

Goal: quickly ingest a knowledge note into `20-knowledge/`. Explicit shortcut when the user knows that what they are capturing is a fact, a concept, a card, or a stable synthesis.

## Trigger

The user types `/mem-note {content}` or expresses intent in natural language: "note this concept", "add this card", "save this definition".

Recognized options:
- `--scope personal|work`: forces the scope.
- `--family business|tech|life|methods`: forces the knowledge family. Otherwise, the router decides.
- `--type concept|card|glossary|synthesis|reference`: forces the type.
- `--no-confirm`, `--dry-run`: passed through to the router.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault` and `default_scope`. If missing, standard error message and stop.

## Procedure

### 1. Pre-format

Prepare the Markdown content of the note. If the user provided a clear title, use it. Otherwise, derive a short title from the first lines.

### 2. Invoke the router with forced zone hint

Call the router with:
- `Content`: the note content.
- `Hint zone`: `knowledge` (forces the zone, bypasses cascade).
- `Hint source`: `manual`.
- `Metadata`: forced family if provided, forced type if provided.

{{INCLUDE _router}}

The router:
- Determines the sub-family (`business`, `tech`, `life`, `methods`) if not forced, based on lexical cues.
- Writes into `{VAULT}/20-knowledge/{family}/{sub-domain}/{slug-title}.md`.
- Builds the frontmatter with `type`, `tags`, etc.
- If invocation happens from a current project/domain, the tag `project/{slug}` or `domain/{slug}` is added for cross-cutting attachment.

### 3. Confirm

The router produces its report. No additional action.
