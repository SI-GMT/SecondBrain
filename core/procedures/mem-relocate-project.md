# Procedure: Relocate Project

Goal: update a single project's `repo_path` after the source tree has moved on disk (drive change, folder reorganization), **without** touching archive bodies. Archives stay valid because they reference paths via the `<repo>/...` sigil — the absolute root is resolved from `context.md:repo_path`. This skill rewrites that one field and appends an audit entry. Nothing else.

## Trigger

The user types `/mem-relocate-project {slug} {new-root}` or expresses intent in natural language: "le projet X est passé sur D:", "I moved repo Y to ~/work/proj-y", "update repo_path for Z".

Arguments:
- `{slug}` (**required**): project (or domain) slug in the vault.
- `{new-root}` (**required**): absolute path of the new source-tree root on disk.
- `--confirm`: apply the mutation. Without it, the call is a **dry-run**.
- `--force`: bypass the git-remote sanity check.
- `--reason "{text}"`: optional free-text reason recorded in the audit log.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault`. If missing, surface the standard error and stop.

## Procedure

### 1. Resolve `{slug}` to its vault folder

Look up `{slug}` in `10-episodes/projects/`, then `10-episodes/archived/`, then `10-episodes/domains/`. Stop with a clear error if not found. Note the `kind` (`project` or `domain`).

### 2. Read the current `repo_path`

Open `{folder}/context.md`, parse the YAML frontmatter, capture the current `repo_path` value (may be empty / unset for legacy projects).

### 3. Pre-flight checks (always run, dry-run and confirm modes)

- **New root exists and is a directory.** Refuse otherwise.
- **No-op detection.** If the new root equals the current `repo_path`, return a no-op success without touching anything.
- **Git remote sanity check.**
  - Run `git -C "{new-root}" remote get-url origin`. If no `.git` or no `origin`, refuse unless `--force`.
  - If the project has a topology file (`99-meta/repo-topology/{slug}.md`), compare its `repo_remote` field with the new origin. Normalize the comparison: strip `.git` suffix, lowercase host, normalize `https://` ↔ `git@host:` syntax. Mismatch refuses unless `--force`.

### 4. Dry-run summary

Show the planned edit :
- `old repo_path: {old}`
- `new repo_path: {new-root}`
- `file touched: 10-episodes/projects/{slug}/context.md` (one frontmatter field)
- any warnings.

Stop if `--confirm` was not passed.

### 5. Apply

- Rewrite `context.md` frontmatter `repo_path: {new-root}`. Other fields untouched. UTF-8 LF atomic write.
- Append an entry to `99-meta/migrations/relocations.md` (create file with header on first call):

```
- **YYYY-MM-DD HH:MM** — `mem_relocate_project` on `{slug}` ({kind})
  - old `repo_path`: `{old or '(unset)'}`
  - new `repo_path`: `{new-root}`
  - reason: {reason if provided}
```

### 6. Final summary

Return a markdown summary listing the path change and the audit entry. Note that **legacy archives still containing absolute paths under `{old}` are NOT rewritten** — that is the job of `mem-archive-rewrite-paths`.

## Doctrine

- `context.md:repo_path` is the **single source of truth** for the absolute root of a project. Archive bodies must reference paths via the `<repo>/...` sigil so they remain valid after any future relocation.
- This skill is **chirurgical** — exactly one frontmatter field, one audit entry, no folder rename, no body rewrite. Use it whenever the disk root moves; use `mem-rename` for slug changes; use `mem-archive-rewrite-paths` for legacy archives carrying obsolete absolute paths.
- The git-remote check is the safety net against pointing a project at the wrong tree. Override via `--force` only when you know the new root intentionally has no `.git` or a different remote (e.g. fork, mirror).
- Relocation logs are append-only. Never rewrite past entries.
