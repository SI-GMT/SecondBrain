# Procedure: Vault Migrate

Goal: move the entire memory vault from one filesystem location to another (disk reorganization, drive replacement, sync provider change). Updates `~/.memory-kit/config.json` plus every per-CLI `memory-kit.json` and the Claude `additionalDirectories` allow-list so all clients pick up the new path on next launch.

## Trigger

The user types `/mem-vault-migrate {target}` or expresses intent in natural language: "déplace le vault sur D:", "move the vault to /mnt/work/memory", "change l'emplacement de la mémoire".

Arguments:
- `{target}` (**required**): absolute destination path of the new vault root.
- `--confirm`: apply mutations. Without it, the call is a **dry-run** (plan only, no FS change).

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault`. If missing, surface the standard error and stop. The current `vault` value is the **source** of the migration.

## Procedure

### 1. Pre-flight checks (always run, in dry-run and confirm modes)

- **Source exists.** `{source}` must be a directory on disk. Otherwise stop with `Current vault path does not exist on disk: {source}`.
- **Target differs from source.** Refuse `target == source`.
- **Target absent or empty.** If `{target}` exists, it must be an empty directory. Refuse to overwrite an existing tree.
- **Target parent reachable.** If `{target}.parent` does not exist, it will be created on confirm; warn during dry-run.
- **Vault not locked.** Scan `{source}/*.lock`, `{source}/**/.~lock.*`, `{source}/.obsidian/workspace.json.lock`. If any present, stop with `Vault is locked by Obsidian (close it first).` Listing the lock files in the error message.
- **Disk space on cross-volume.** If `{source}.drive != {target}.drive`, compute total tree size and compare with free space on the target volume. Require at least **10% headroom**. Refuse otherwise.

### 2. Present the plan (dry-run output)

Show a summary listing :
- `source` and `target` paths.
- Cross-volume yes/no.
- Approximate tree size (only when cross-volume).
- Number of per-CLI `memory-kit.json` files that will be patched.
- Whether `~/.claude/settings.json:permissions.additionalDirectories` will be touched.

Stop here if `--confirm` was not passed.

### 3. Move the vault tree

`shutil.move({source}, {target})` — handles same-volume rename (atomic) and cross-volume copy + delete (not atomic, but guarded by the disk-space pre-check).

### 4. Update `~/.memory-kit/config.json`

Rewrite the `vault` field to `{target}`. UTF-8 LF atomic write. Preserve other keys (`default_scope`, `language`, `kit_repo`, …).

### 5. Patch every per-CLI `memory-kit.json`

Candidate paths (read-only enumeration, skip silently if absent):

```
~/.claude/memory-kit.json
~/.codex/memory-kit.json
~/.copilot/memory-kit.json
~/.gemini/memory-kit.json
~/.gemini/antigravity/memory-kit.json
~/.gemini/antigravity-cli/memory-kit.json
~/.vibe/memory-kit.json
```

For each that exists:
- Parse JSON.
- If `vault` field equals `{source}` (case-insensitive compare on Windows), rewrite to `{target}` and write atomically.
- If `vault` field equals `{target}` already, skip (idempotent).
- If `vault` points elsewhere (foreign vault on this machine), **do NOT touch** — surface a warning instead.

### 6. Patch `~/.claude/settings.json:permissions.additionalDirectories`

- Read the list.
- Replace the entry equal to `{source}` with `{target}`.
- If neither `{source}` nor `{target}` is present, append `{target}`.
- If `{target}` already present, leave as-is.

### 7. Append audit entry to `{target}/99-meta/migrations/vault-migrations.md`

Create the file with a frontmatter header on first run. Append an entry of the form :

```
- **YYYY-MM-DD HH:MM** — vault moved
  - old: `{source}`
  - new: `{target}`
```

UTF-8 LF, append mode, no rewrite of the rest of the file.

### 8. Final summary

Return a markdown summary mentioning :
- The move performed.
- Configs updated (count + paths).
- Reminder to **restart Obsidian + any running MCP-host CLI** so they pick up the new vault path.

## Doctrine

- This skill is **destructive on disk** — refuse without `--confirm` unless the caller explicitly asked for a dry-run.
- Migration log entries are **append-only**. Never rewrite past entries.
- The vault filesystem layout (zones, archives, project folders) is **untouched** — only the root path moves.
- Cross-volume moves are not atomic. The 10% headroom check is a guardrail; for truly large vaults consider a manual copy + verify + cleanup pass instead.
- Companion to `mem-relocate-project` (which moves a single project's `repo_path`) and `mem-archive-rewrite-paths` (which converts in-archive absolute paths to the `<repo>/...` sigil).
