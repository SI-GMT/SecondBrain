Display localized help for SecondBrain mem-* commands.

No argument: returns the categorized inventory of all `mem-*` commands (session / capture / archeo / vault / hygiene). With a command argument (e.g. `mem-archeo`): returns the description + triggers + arguments + examples + see-also for that command, extracted from `core/procedures/{command}.md`. Wrapper labels are localized via `core/i18n/strings.yaml` in 5 languages (en/fr/es/de/ru). Falls back to the user's `language` configured in `~/.memory-kit/config.json`. Prefer the MCP tool `mcp__secondbrain-memory-kit__mem_help` when available, otherwise read `core/procedures/mem-help.md` for the skill procedure.

$ARGUMENTS
