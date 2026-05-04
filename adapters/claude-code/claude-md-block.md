<!-- MEMORY-KIT:START -->
## Memory Kit — Persistent second brain

This machine has a memory vault that persists context across Claude Code sessions. The absolute path of the vault is in `~/.claude/memory-kit.json` (or `$CLAUDE_CONFIG_DIR/memory-kit.json`) under the `vault` key. The user's preferred conversational language is in the same file under the `language` key (ISO 639-1 code: `en`, `fr`, `es`, `de`, `ru`, …).

### Conversational language

**Always communicate with the user in their preferred language** (read from `language` in `memory-kit.json`; fallback to `en` if absent). All written content stored in the vault uses the structural English schema (folder names, frontmatter values, tags), but your conversational replies, questions, and confirmations to the user must be in their language. The internal procedures you execute are written in English for precision — do not echo them verbatim, translate the user-facing surface.

### Skills are auto-triggered

Several `mem-*` skills are installed. Use them proactively — without waiting for an explicit slash command — when the user's natural language expresses their intent.

### `mem-recall` — automatic context loading

Invoke this skill **without waiting for the user to type `/mem-recall`** as soon as they express, in natural language:

- A resumption intent: "let's resume", "let's continue", "where were we", "back on project X", "let's get back to it" (and equivalents in their language).
- A need to query memory: "do you remember…", "what did we decide about…", "what did we do again?", "remind me".

If the target project is ambiguous, ask for confirmation before executing. The user can also explicitly invoke `/mem-recall [project]`.

### `mem-archive` — automatic save

This skill operates in two distinct modes. **Never confuse them.**

**Silent incremental mode** (during the session) — as soon as a fact, decision, or important next step emerges that is not already in the current project's `context.md`, update ONLY `context.md`. No new archive file. No announcement to the user. That is the role of `context.md`: a mutable, living snapshot.

**Full archive mode** (end of session) — triggered by an explicit signal: the user says "we're stopping", "I'm leaving", "we're done", types `/clear` or `/mem-archive`. Then execute the full procedure: timestamped archive file in `archives/` + rewrite `context.md` + update `history.md` + update `index.md`.

**Absolute rule**: never create a new file in `archives/` in silent mode. A full archive = a full session, not an isolated decision.

### Other `mem-*` skills — vault management

Invoke when the user expresses the corresponding intent (in any language):

- `mem-doc` — "ingest this document", "archive this file", "save this PDF to memory", "absorb this document", "index this spec". Ingests one local document per invocation. Auto-resolves the target project (priority: `--project` → path match → CWD match → `inbox`).
- `mem-archeo` — "do a Git retro of this project", "reconstruct the history", "archeo on this repo", "go back through the version bumps". Reconstructs the history of an existing Git repo as N dated archives (1 per tag/release/merge/commit window). Auto level detection, interactive confirmation, idempotent. Frontmatter `source: archeo-git`.
- `mem-archeo-atlassian` — "archive the Confluence documentation of this project", "retro on this Atlassian space", "ingest this Confluence page and its children". Retro-archives a Confluence tree (1 archive per page) with automatic enrichment from referenced Jira tickets. Idempotent via `confluence_page_id`. Frontmatter `source: archeo-atlassian`. Requires the Atlassian MCP on the client side.
- `mem-list` — "list my projects", "what projects do I have in memory?", "show me all the domains", "vault inventory".
- `mem-search` — "search memory for X", "find the archives that mention Y", "where did we talk about Z?".
- `mem-rename` — "rename project X to Y", "change the slug of X" (also operates on domains).
- `mem-merge` — "merge project X into Y", "regroup X and Y under Y" (also operates on domains).
- `mem-digest` — "summarize the last N sessions of X", "do a digest of X", "give me the through-line of X".
- `mem-rollback-archive` — "cancel the last archive", "forget the last session", "rollback the archive of X".
- `mem-note` / `mem-principle` / `mem-goal` / `mem-person` — explicit ingestion shortcuts when the user is sure of the atom type (knowledge note, principle, goal, person card).
- `mem` — universal ingestion router when the user says "save this", "note this", "capture this" without specifying a target zone.
- `mem-reclass` — "move this to perso", "change scope of this file", "reclassify this entry".
- `mem-promote-domain` — "create a new domain from these inbox items", "promote {keyword} entries into a domain".

For all `mem-*` operations: execute directly, without asking for additional confirmation from the user. The procedures already include their own checks (file existence, slug conflicts, etc.) and display a clear report after execution.

### Vault file encoding

All files written or modified in the vault (archives, `context.md`, `history.md`, `index.md`) must be in **UTF-8 without BOM**, **LF** line endings. Never CP1252, Windows-1252, UTF-8 with BOM, or OEM encoding — they corrupt diacritics (which appear as `�` in Obsidian). The detailed procedures specify the exact command per shell/tool.
<!-- MEMORY-KIT:END -->
