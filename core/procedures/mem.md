# Procedure: Mem (universal router — new in v0.5)

Goal: zero-friction ingestion of free-form content into the vault. The semantic router segments, classifies and writes into the right zone(s) without the user having to think about classification.

This is the **default path** for 80% of ingestion cases. Specialized skills (`mem-archive`, `mem-note`, `mem-principle`, `mem-goal`, `mem-person`, `mem-doc`, `mem-archeo*`) are shortcuts that force a specific zone.

## Trigger

The user types `/mem {content}` or expresses the intent in natural language: "note this", "save", "capture this", "add to memory".

Recognized options:
- `--scope personal|work`: forces the scope. Default: `default_scope` from `memory-kit.json`.
- `--zone X`: forces the zone (equivalent to invoking the specialized skill). Bypass the heuristics cascade.
- `--project {slug}` or `--domain {slug}`: forces the episodic attachment.
- `--no-confirm`: forces fluid mode even on multi-atoms.
- `--dry-run`: shows the plan without writing.

## Vault path resolution

Read {{CONFIG_FILE}} and extract the `vault` and `default_scope` fields. In what follows, `{VAULT}` denotes the vault value.

If the file is absent or unreadable, reply:
> Memory kit not configured. Expected file: {{CONFIG_FILE}}. Run `deploy.ps1` from the kit root.

Then stop.

## Procedure

### 1. Preformatting by the adapter

The adapter (Claude Code, Gemini CLI, Codex, Vibe) has already:
- Normalized line endings (LF) and encoding (UTF-8 without BOM).
- Injected the invocation context: current project (CWD), Git branch, default scope.
- Pre-annotated scope clues if obvious.

### 2. Invoke the router

Pass to the router the content, with no zone hint (unless `--zone X` provided). Let the router decide segmentation, classification, writing.

{{INCLUDE _router}}

### 3. Report

The router produces its own report (see R9 of the router block). No additional action by the `mem` procedure.

---

Arguments to parse: the content is everything after `/mem` (or the natural sentence). The `--xxx` options are extracted before invoking the router.
