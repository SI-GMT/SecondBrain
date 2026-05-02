<!-- MEMORY-KIT:START -->
## Memory Kit — Persistent second brain

This machine has a memory vault that persists context across GitHub Copilot CLI sessions. The detailed procedures live in the `mem-*` skills auto-discovered from `~/.copilot/skills/`. Each skill is also invocable as a native slash command (`/mem-recall`, `/mem-archive`, …). This block sets the global rules that frame their execution.

### Conversational language

**Always communicate with the user in their preferred language** (read `language` from `~/.copilot/memory-kit.json`; fallback to `en` if absent). All written content stored in the vault uses the structural English schema (folder names, frontmatter values, tags), but your conversational replies, questions, and confirmations to the user must be in their language.

### ⚠ Golden rule — Vault

**VAULT = `{{VAULT_PATH}}`**

- This is an **absolute, immutable path, EXTERNAL to the current working directory**.
- **NEVER** list the cwd (`ls`, `pwd`, `dir`) to "find" the vault. It is **not** there.
- **NEVER** assume the vault is inside the current project.
- **NEVER** ask the user to confirm the path — it is hard-coded above at install time.
- **ALWAYS** attack directly with this absolute path, from the very first command.
- If doubt arises mid-operation, re-read this rule and start again from the absolute path.

### Recommended tool: system shell (absolute path)

For any memory operation, use the system shell tool with the **full absolute path**. The sandboxed file tools may refuse an external absolute path — the shell does not have this limit.

**Choose commands based on the available shell** (bash, PowerShell, cmd). Equivalents for common operations:

| Action | bash / macOS / Linux / git-bash | PowerShell / pwsh | cmd (Windows) |
|---|---|---|---|
| List a folder | `ls "{{VAULT_PATH}}/10-episodes/projects/"` | `Get-ChildItem "{{VAULT_PATH}}/10-episodes/projects/"` | `dir "{{VAULT_PATH}}\10-episodes\projects\"` |
| Read a file | `cat "{{VAULT_PATH}}/10-episodes/projects/X/context.md"` | `Get-Content "{{VAULT_PATH}}/10-episodes/projects/X/context.md"` | `type "{{VAULT_PATH}}\10-episodes\projects\X\context.md"` |
| Write a file | `cat > "…" <<'EOF' … EOF` | `Set-Content -Path "…" -Value …` | `echo …> "…"` (limited) |
| Recursive search | `grep -rni "query" "{{VAULT_PATH}}/"` | `Select-String -Path "{{VAULT_PATH}}/**/*.md" -Pattern "query"` | `findstr /s /i "query" "{{VAULT_PATH}}\*.md"` |
| Delete | `rm "{{VAULT_PATH}}/…"` | `Remove-Item "{{VAULT_PATH}}/…"` | `del "{{VAULT_PATH}}\…"` |
| Rename / move | `mv "…" "…"` | `Move-Item "…" "…"` | `move "…" "…"` |
| In-place edit | `sed -i 's/old/new/g' "…"` | `(Get-Content "…") -replace 'old','new' \| Set-Content "…"` | — (no direct equivalent) |

If a command fails ("command not found", "is not recognized"), **try the platform's native shell equivalent** before considering the operation impossible. On Windows, if `bash`/`ls`/`cat` fail, fall back directly to PowerShell or cmd — the vault is always accessible via an absolute path, regardless of the shell.

### Vault structure (v0.5)

- `{{VAULT_PATH}}/index.md` — master catalog (root).
- `{{VAULT_PATH}}/00-inbox/` — raw unqualified capture.
- `{{VAULT_PATH}}/10-episodes/projects/{slug}/context.md` — mutable project snapshot (always up-to-date, fast lane).
- `{{VAULT_PATH}}/10-episodes/projects/{slug}/history.md` — chronological session log.
- `{{VAULT_PATH}}/10-episodes/projects/{slug}/archives/YYYY-MM-DD-HHhMM-{slug}-{subject}.md` — end-of-session archives, **immutable** (filename and narrative body). Frontmatter may be modified by `mem-rename` and `mem-merge`.
- `{{VAULT_PATH}}/10-episodes/domains/{slug}/...` — long-running domains (no end date).
- `{{VAULT_PATH}}/20-knowledge/`, `30-procedures/`, `40-principles/`, `50-goals/`, `60-people/`, `70-cognition/`, `99-meta/` — other vault zones.

### Available skills

The `mem-*` skills are installed in `~/.copilot/skills/` and are **auto-discovered** by Copilot CLI. Each skill carries its own full procedure and is **also exposed as a slash command** (e.g. `/mem-recall`, `/mem-archive`, `/mem-doc`). Auto-trigger on natural language (in any language) is preferred:

| Skill | Natural intent (examples in English) |
|---|---|
| `mem-recall` | "resume [project]", "let's continue", "do you remember…", "where were we?" |
| `mem-archive` | "we're stopping", "I'm leaving", "we're done", `/clear` (full mode) — **mid-session**: silent update of `context.md` whenever a decision or important fact emerges |
| `mem-doc` | "ingest this document", "archive this file", "save this PDF to memory", "absorb this document" |
| `mem-archeo` | "do a Git retro of this project", "reconstruct the history", "go back through the version bumps" |
| `mem-archeo-atlassian` | "archive the Confluence documentation", "retro on this Atlassian space", "ingest this page and its children" |
| `mem-list` | "list my projects", "what projects do I have in memory?" |
| `mem-search` | "search memory for [X]", "find archives that mention Y" |
| `mem-digest` | "summarize the last N sessions of [project]", "through-line of [project]" |
| `mem-rename` | "rename project [old] to [new]" (also operates on domains) |
| `mem-merge` | "merge [source] into [target]" (also operates on domains) |
| `mem-rollback-archive` | "cancel the last archive", "rollback the archive of [project]" |
| `mem-historize` | "archive this finished project", "historize [project]" |
| `mem-health-scan` / `mem-health-repair` | "scan vault health", "repair vault" |
| `mem-promote-domain` | "create a new domain from these inbox items" |
| `mem-reclass` | "move this to personal", "change scope of this file" |
| `mem-note` / `mem-principle` / `mem-goal` / `mem-person` | explicit ingestion shortcuts |
| `mem` | universal ingestion router ("save this", "note this") |

### Canonical example — first expected action

User: "resume SecondBrain"
You, **immediately**, without prior exploration, depending on your shell:

```
# bash / macOS / Linux / git-bash
cat "{{VAULT_PATH}}/10-episodes/projects/secondbrain/context.md"

# PowerShell
Get-Content "{{VAULT_PATH}}/10-episodes/projects/secondbrain/context.md"

# cmd (Windows)
type "{{VAULT_PATH}}\10-episodes\projects\secondbrain\context.md"
```

**NO** `ls`/`dir`/`Get-ChildItem` of the cwd, **NO** `pwd`, **NO** question to the user. The file exists or it doesn't; in both cases the direct read gives the answer.

### Operational rules

- **Incremental vs full mode for `mem-archive`**: mid-session, update ONLY `context.md` without creating an archive or announcing the action. Only create a file in `archives/` on an explicit end-of-session signal.
- **Execute directly, without asking for additional confirmation**. The skills include their own checks and display a clear report after execution.
- **No cwd exploration**. No `pwd`, no `ls`/`dir`/`Get-ChildItem` of the current directory to find the vault.
- **Shell tolerance**. If a shell command fails because it is not recognized (e.g., `ls` on Windows without git-bash), **do not give up** — immediately fall back to the native equivalent (`dir` for cmd, `Get-ChildItem` for PowerShell) keeping the same absolute path.

### ⚙ Vault file encoding

All files written or modified in the vault (archives, `context.md`, `history.md`, `index.md`) must be in **UTF-8 without BOM**, **LF** line endings. Never CP1252, Windows-1252, UTF-8 with BOM, or OEM encoding — they corrupt diacritics (which appear as `�` in Obsidian).

| Shell | UTF-8 without BOM write |
|---|---|
| bash / macOS / Linux / git-bash | `cat > "path" <<'EOF' … EOF` (native UTF-8 without BOM) |
| PowerShell 7+ (pwsh) | `Set-Content -Path "path" -Value $content -Encoding utf8NoBOM` |
| Windows PowerShell 5.1 | `[System.IO.File]::WriteAllText("path", $content, [System.Text.UTF8Encoding]::new($false))` |
| cmd.exe | **avoid for accented Markdown** — fall back to PowerShell or bash |

If the available shell's write command adds a BOM or corrupts diacritics, **switch to a compatible shell** rather than try to produce the file that way.
<!-- MEMORY-KIT:END -->
