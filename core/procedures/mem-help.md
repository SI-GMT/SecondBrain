# Procedure: Help (v0.11.x — localized)

Goal: display localized help for SecondBrain `mem-*` commands. Two modes — categorized inventory (no argument) or detailed help for a specific command.

## Trigger

The user types `/mem-help [command]` or `[command]:help` or expresses intent in natural language:

- "what mem commands are available", "list the mem-* commands", "help"
- "help on mem-archeo", "syntaxe de /mem-recall", "qu'est-ce que mem-doc fait ?", "mem-archeo:help"
- "ayuda mem-search", "Hilfe mem-archive", "справка mem-list"

Arguments:

- `{command}` (optional): a `mem-*` command name (with or without the `mem-` prefix and the leading slash). Examples: `mem-archeo`, `archeo`, `/mem-archeo`. Without argument, returns the general inventory.
- `--lang {code}` (optional): override the conversational language. One of `en`, `fr`, `es`, `de`, `ru`. Without override, the language is read from `~/.memory-kit/config.json` (`language` field), with `en` as ultimate fallback.

## Vault and repo path resolution

Read `~/.memory-kit/config.json` and extract `kit_repo` (path to the SecondBrain kit checkout) and `language`. Both are required: `kit_repo` to locate the canonical procedure files, `language` to resolve the localized wrappers.

## Procedure

### General mode (no command)

Walk `{kit_repo}/core/procedures/mem-*.md`. Display as a table, one row per procedure file, with columns:

1. Extract the command name from the filename (e.g. `mem-archeo.md` → `mem-archeo`).
2. Extract the **first sentence of the `Goal:` paragraph** as the one-line description. If `Goal:` is absent, fall back to the first non-title paragraph.
3. Resolve the **category** from a hardcoded mapping (`session` / `capture` / `archeo` / `vault` / `hygiene` / `misc`).

Render a localized Markdown report grouping commands by category, with one bullet per command (`/mem-X — description`). Use the wrapper labels from `core/i18n/strings.yaml` under the `help.*` keys for the resolved language.

### Command-specific mode

Resolve the procedure file `{kit_repo}/core/procedures/{command}.md`. If absent, return the localized `unknown_command` error pointing the user back to `/mem-help` for the full list.

Extract the following sections from the procedure body:

- **Description**: first sentence of `Goal:` paragraph (same heuristic as general mode).
- **Triggers**: full body of the `## Trigger` section (natural-language phrases + slash invocations + arguments often live there).
- **Arguments**: body of `## Arguments` section when present (most procedures keep arguments inline in `## Trigger`).
- **Examples**: body of `## Examples` (or `## Example`) section when present.
- **See also**: hardcoded related-commands map (e.g. `mem-archeo` → `[mem-archeo-plan, mem-archeo-git, mem-archeo-stack, mem-archeo-context]`).

Render a localized Markdown report with section headers from `core/i18n/strings.yaml` (`description_label`, `triggers_label`, `arguments_label`, `examples_label`, `see_also_label`).

### Localization scope

**Only the chrome translates** — section labels, titles, error messages, navigation, footers. The **body content of the procedures stays in canonical English**. The procedures are read by LLMs that perform best on EN substrate, so translating them would hurt the LLM-side precision. The user-facing surface (wrappers + the LLM's conversational reply rephrasing the help) handles the language adaptation.

## Output

Pre-rendered Markdown directly displayable to the user. The structured payload (`HelpResult`) also carries the raw fields (description, triggers, arguments, examples, see_also, commands inventory) so the LLM can re-shape the presentation when the user asks follow-up questions like "give me only the arguments of mem-archeo".

## Invariants

- Help content is always derived from `core/procedures/mem-*.md` — single source of truth, no separate help corpus to keep in sync.
- The list of commands surfaced reflects the actual procedures present in the kit checkout — no hardcoded inventory drift.
- Wrapper localization is bounded by the 5 languages bundled in `core/i18n/strings.yaml` (`en`, `fr`, `es`, `de`, `ru`); unknown lang falls back to `en`.
- Language detection priority: explicit `--lang` argument > config file > `en`.
