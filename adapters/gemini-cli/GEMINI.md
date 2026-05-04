# Memory Kit — Persistent second brain (Gemini CLI)

This machine has a memory vault that persists context across Gemini sessions. The absolute vault path is in `~/.gemini/memory-kit.json` under the `vault` key. The user's preferred conversational language is in the same file under the `language` key (ISO 639-1: `en`, `fr`, `es`, `de`, `ru`, …).

## Conversational language

**Always communicate with the user in their preferred language** (read `language` from `~/.gemini/memory-kit.json`; fallback to `en` if absent). All written content stored in the vault uses the structural English schema (folder names, frontmatter values, tags), but your conversational replies, questions, and confirmations to the user must be in their language.

## Skills are auto-triggered

Several `mem-*` commands are available. Trigger them automatically when the user's natural language expresses their intent.

## `/mem-recall` — context loading

Invoke this logic **without waiting for `/mem-recall`** as soon as the user expresses, in natural language:

- A resumption intent: "let's resume", "let's continue", "where were we", "back on project X", "let's get back to it" (and equivalents in their language).
- A need to query memory: "do you remember…", "what did we decide about…", "what did we do again?", "remind me".

If the target project is ambiguous, ask for confirmation before executing.

## `/mem-archive` — save

Two distinct modes. **Never confuse them.**

**Silent incremental mode** (during the session) — as soon as a fact, decision, or important next step emerges that is not already in the current project's `context.md`, update ONLY `context.md`. No new archive file. No announcement to the user. That is the role of `context.md`: a mutable, living snapshot.

**Full archive mode** (end of session) — triggered by an explicit signal: the user says "we're stopping", "I'm leaving", "we're done", types `/clear` or `/mem-archive`. Then execute the full procedure: timestamped archive file in `archives/` + rewrite `context.md` + update `history.md` + update `index.md`.

**Absolute rule**: never create a new file in `archives/` in silent mode. A full archive = a full session, not an isolated decision.

## Other `/mem-*` commands — vault management

Trigger when the user expresses the corresponding intent (in any language):

- **`/mem-doc {path}`** — "ingest this document", "archive this file", "save this PDF to memory". Ingests one local document (PDF, Markdown, text, image, docx…) per invocation. Auto-resolves the target project. Options: `--project {slug}`, `--title "{text}"`.
- **`/mem-archeo [repo-path]`** — "do a Git retro of this project", "reconstruct the history", "go back through the version bumps". Reconstructs the history of an existing Git repo as N dated archives. Auto level detection, interactive confirmation, idempotent. Options: `--level tags|releases|merges|commits`, `--project {slug}`, `--since/--until YYYY-MM-DD`, `--window day|week|month`, `--dry-run`.
- **`/mem-archeo-atlassian {url}`** — "archive the Confluence documentation", "retro on this Atlassian space". Retro-archives a Confluence tree (root page + descendants, or full space) with automatic enrichment from referenced Jira tickets. 1 archive per page, idempotent via `confluence_page_id + confluence_updated`. Options: `--project {slug}`, `--depth N`, `--skip-children`, `--since YYYY-MM-DD`, `--skip-jira`, `--dry-run`. Requires the Atlassian MCP on the client.
- **`/mem-list`** — "list my projects", "what projects do I have in memory?", "show me all the domains". Displays projects + domains with phase, last session, session count.
- **`/mem-search {query}`** — "search memory for X", "find the archives that mention Y". Full-text search of the vault.
- **`/mem-rename {old} {new}`** — "rename project X to Y" (also operates on domains). Renames the slug everywhere in the vault (folder, frontmatters, tags, index). Preserves archive filenames and narrative content.
- **`/mem-merge {source} {target}`** — "merge project X into Y" (also operates on domains). Concatenates the two, retags archives, removes the source folder. The target's `context.md` must be merged manually.
- **`/mem-digest {project} [N]`** — "summarize the last N sessions of X", "do a digest of X". Through-line synthesis of major arcs and structural decisions. Read-only.
- **`/mem-rollback-archive [project]`** — "cancel the last archive", "rollback the archive of X". Removes the last archive + its references; does NOT auto-restore `context.md`.
- **`/mem-note` / `/mem-principle` / `/mem-goal` / `/mem-person`** — explicit ingestion shortcuts when the user knows what they're capturing (knowledge note, principle, goal, person card).
- **`/mem`** — universal ingestion router when the user says "save this", "note this" without specifying a target zone.
- **`/mem-reclass`** — "move this to personal", "change the scope of this file".
- **`/mem-promote-domain`** — "create a new domain from these inbox items".

For all `mem-*` operations: execute directly, without asking for additional confirmation. The procedures already include their own checks and display a clear report after execution.

## Vault structure (v0.5)

```
{{VAULT_PATH}}/
├── index.md                          ← master catalog (root)
├── 00-inbox/                         ← raw unqualified capture
├── 10-episodes/
│   ├── projects/{slug}/
│   │   ├── context.md                ← mutable snapshot (fast lane)
│   │   ├── history.md                ← chronological log
│   │   └── archives/YYYY-MM-DD-HHhMM-{slug}-{subject}.md
│   └── domains/{slug}/...            ← long-running domains (no end date)
├── 20-knowledge/                     ← semantic memory
├── 30-procedures/                    ← know-how
├── 40-principles/                    ← heuristics & red lines
├── 50-goals/                         ← prospective intentions
├── 60-people/                        ← relational notebook
├── 70-cognition/                     ← non-verbal productions
└── 99-meta/                          ← vault meta-memory (doctrine, taxonomy)
```

## Vault file encoding — CRITICAL

All files written or modified in the vault (archives, `context.md`, `history.md`, `index.md`) **MUST** be in **UTF-8 without BOM**, **LF** line endings.

### Bug to avoid at all costs

Gemini CLI on Windows has been observed producing **double-encoded UTF-8→CP1252→UTF-8** via its shell write tool: `é` becomes `Ã©`, `è` becomes `Ã¨`, `—` (em dash) becomes `â€"`. Cause: the Windows shell pipeline re-encodes to CP1252 when output encoding is not explicitly forced. The file looks "UTF-8" to `file`, but the content is corrupted. The characters `Ã`, `â€`, `Â ` (non-breaking space encoded) are the **bug signatures**.

### MANDATORY method — Python for all vault writes

On Windows (your main context), **bypass the native shell and write via Python** — this is the only reliable method:

```python
from pathlib import Path
# Atomic UTF-8 without BOM, LF
tmp = Path(target + ".tmp")
tmp.write_text(content, encoding="utf-8", newline="")
tmp.replace(target)  # cross-platform atomic rename
```

Or as a one-liner in `run_shell_command`:

```bash
python -c "from pathlib import Path; Path(r'{target}.tmp').write_text(r'''{content}''', encoding='utf-8', newline=''); Path(r'{target}.tmp').replace(r'{target}')"
```

### Per-platform shell commands (fallback if Python unavailable)

| Shell | UTF-8 without BOM write |
|---|---|
| bash / POSIX / git-bash | `printf '%s' "$content" > "$target.tmp" && mv -f "$target.tmp" "$target"` (native UTF-8 without BOM) |
| PowerShell 7+ (pwsh) | `Set-Content -Path "$target.tmp" -Value $content -Encoding utf8NoBOM -NoNewline; Move-Item -Path "$target.tmp" -Destination $target -Force` |
| Windows PowerShell 5.1 | **AVOID** — `-Encoding UTF8` injects a BOM. If no alternative: `[System.IO.File]::WriteAllText("$target", $content, [System.Text.UTF8Encoding]::new($false))` |

### FORBIDDEN commands on Windows for accented Markdown

- ❌ `echo "..." > file.md` (cmd.exe or Windows PowerShell) → OEM/CP1252 encoding, corrupts diacritics.
- ❌ `Out-File -Encoding UTF8` on PS5.1 → injects a BOM.
- ❌ `Set-Content -Value $x -Encoding UTF8` on PS5.1 → ditto (BOM).
- ❌ Any shell redirection (`>`, `>>`) without explicitly specifying output encoding.

### Post-write validation (recommended)

After any sensitive write, check that no corruption signature appears:

```bash
grep -c $'\xc3\x83\|â€\|Â ' "{path}" 2>/dev/null
# Must return 0. If > 0, the file was corrupted, rewrite via the Python method.
```

### Corruption symptoms to detect

If you see in a file you just wrote:
- `Ã©`, `Ã¨`, `Ãª`, `Ã§`, `Ã€`, `Ã‰` → double-encoding, rewrite via Python.
- `â€"`, `â€™`, `â€œ`, `â€`, `â€¦` → double-encoded dashes/quotes/ellipses.
- `Â ` (space preceded by A-circumflex) → double-encoded non-breaking space.
- `\"text\"` in YAML frontmatter (escaped quotes) → shell artifact, remove the backslashes.

In all these cases, the SecondBrain repo's `scripts/fix-double-encoding.py` retroactively fixes, but **prevention is mandatory**: go via Python from the first write.
