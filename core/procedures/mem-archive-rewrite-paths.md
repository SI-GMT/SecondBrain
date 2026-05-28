# Procedure: Archive Rewrite Paths

Goal: convert legacy absolute paths inside archive bodies (and `context.md` / `history.md`) to the canonical `<repo>/...` sigil form so the archives stay valid across any future disk relocation. Doctrine-permitted edition of immutable archive bodies because an absolute path is **infrastructure metadata**, not semantic content.

## Trigger

The user types `/mem-archive-rewrite-paths {slug}` or expresses intent in natural language: "fix paths in my archives", "rewrite old C:\\ paths to sigil form", "migrate paths after the disk move".

Arguments:
- `{slug}` (**required**): project (or domain) slug.
- `--old-root "{path}"`: legacy absolute root to rewrite. Defaults to the project's **current** `context.md:repo_path`. Pass explicitly when the relocation already happened (`repo_path` now points to the new root, but archives still reference the old one).
- `--confirm`: apply the mutations. Without it, the call is a **dry-run**.
- `--no-include-context-history`: limit the rewrite to files under `archives/` (skip `context.md` and `history.md`).

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault`.

## Procedure

### 1. Resolve `{slug}` to its vault folder

Look up `{slug}` in `10-episodes/projects/`, `10-episodes/archived/`, then `10-episodes/domains/`. Stop with a clear error if not found.

### 2. Resolve `{old-root}`

- If `--old-root` was passed, use it verbatim.
- Otherwise read `context.md:repo_path` from the project. If empty, refuse with a clear error asking the caller to pass `--old-root` explicitly.

### 3. Enumerate candidate files

- All `.md` files directly under `{folder}/archives/`.
- `{folder}/context.md` and `{folder}/history.md` unless `--no-include-context-history`.

### 4. Scan + plan

For each candidate :
- Parse YAML frontmatter. Body = everything after.
- Search for occurrences of `{old-root}` (case-insensitive on Windows) followed optionally by a separator and path-body characters (stops at whitespace, backticks, quotes, parentheses, brackets, commas, semicolons).
- Count occurrences and remember the rewritten body.

### 5. Dry-run summary

Show :
- Old root.
- Number of files to rewrite + total occurrence count.
- For the first ~5 affected files, a short before/after preview (changed lines only).
- A reminder that frontmatter is NOT touched.

Stop here if `--confirm` was not passed.

### 6. Apply

For each file with at least one match :
- Rewrite the body, swapping every `{old-root}/<tail>` for `<repo>/<tail>`. Bare `{old-root}` becomes `<repo>`.
- Re-write the file via the atomic write helper. Frontmatter unchanged.

### 7. Append audit entry to `99-meta/migrations/relocations.md`

Create the file with the standard header on first call. Append :

```
- **YYYY-MM-DD HH:MM** — `mem_archive_rewrite_paths` on `{slug}`
  - old root: `{old-root}`
  - files modified: {N} (total {M} path occurrences)
    - `{file1}` ({n1} occurrences)
    - …
```

### 8. Final summary

Return a markdown summary listing the rewrite counts and the audit entry. Mention that **the canonical resolution of `<repo>/...`** is now `context.md:repo_path` — if that field still points to the OLD root, run `/mem-relocate-project {slug} {new-root}` to finish the migration.

## Doctrine

- Absolute paths in archive bodies are infrastructure metadata, not semantic content. Rewriting them to sigil form is data preservation, not a content edit. The "archives are immutable" rule is preserved in spirit.
- Frontmatter is **never** touched by this skill. Use `mem-relocate-project` for `repo_path` changes.
- Rewrite is **lexical only** — no filesystem checks, no remote validation. The caller has decided what the old root was.
- The skill is idempotent: re-running after a successful rewrite is a no-op (the sigil form no longer matches the old-root pattern).
- Migration logs are append-only. Never rewrite past entries.
