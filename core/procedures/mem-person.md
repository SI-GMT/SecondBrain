# Procedure: Person (new in v0.5)

Goal: ingest a person card (colleague, client, friend, family) into `60-people/`. Explicit shortcut. Always `sensitive: true` by default (forbids promotion to CollectiveBrain).

## Trigger

The user types `/mem-person {content}` or expresses intent in natural language: "add this person", "note this contact", "card for {name}".

Recognized options:
- `--scope personal|work`: forces the scope.
- `--category colleagues|clients|partners|family|friends|acquaintances`: forces the sub-category.
- `--no-confirm`, `--dry-run`: passed through to the router.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault` and `default_scope`. If missing, standard error message and stop.

## Procedure

### 1. Pre-format

Extract from the provided content:
- `name`: first name + LAST NAME (required, ask the user if missing).
- `role`: role or relationship ("CTO", "colleague", "family doctor", "childhood friend").
- `organization`: company/structure (for work).
- `contact`: email, phone if provided.
- Free-form notes: context, first interactions, notable points.

If `name` can be extracted from the first words of the content ("Jean DUPONT did..." → name = Jean DUPONT), do it automatically. Otherwise, ask.

### 2. Invoke the router with forced zone hint

Call the router with:
- `Content`: the structured card.
- `Hint zone`: `people`.
- `Hint source`: `manual`.
- `Metadata`: name, role, organization, contact, category if provided.

{{INCLUDE _router}}

The router:
- Determines the sub-category based on scope and cues ("my child" → family, "colleague" → colleagues, etc.).
- Writes into `{VAULT}/60-people/{scope}/{category}/{slug-name}.md`.
- Frontmatter with `type: person`, `name`, `role`, `organization`, `contact`, `last_interaction: today`, **`sensitive: true` (always)**.

### 3. Confirm

Router report. Mention explicitly that the card is `sensitive: true` (therefore never lifted into CollectiveBrain).
