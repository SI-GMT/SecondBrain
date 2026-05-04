# Procedure: Rename (v0.5 brain-centric)

Goal: rename a project or domain in the vault. Rewrites the slug **everywhere** (physical folder, frontmatter of all archives, tags `project/{slug}` or `domain/{slug}`, Obsidian links, `index.md`, `history.md`).

Renamed from `mem-rename-project` in v0.5 since it now operates on both projects AND domains.

## Trigger

The user types `/mem-rename {old} {new}` or expresses intent in natural language: "rename project X to Y", "change the slug of domain X".

Arguments:
- `{old}` (**required**): current slug.
- `{new}` (**required**): new slug.
- `--dry-run`: shows the plan without applying.
- `--no-confirm`: applies without confirmation.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault`. If missing, standard error message and stop.

## Procedure

### 1. Identify kind (project or domain)

Search `{old}` in:
- `{VAULT}/10-episodes/projects/{old}/` → kind=project
- `{VAULT}/10-episodes/domains/{old}/` → kind=domain

If not found: stop with a clear message.
If found in both: stop, ask for clarification (extremely rare, but to be guarded against).

### 2. Check for conflict with the new slug

Verify that `{VAULT}/10-episodes/{kind}/{new}/` does not already exist. If conflict, stop with a clear message.

### 3. Enumerate all references to rewrite

- **Project/domain folder**: `{VAULT}/10-episodes/{kind}/{old}/` → `{VAULT}/10-episodes/{kind}/{new}/`
- **Frontmatter `project:` or `domain:`**: all vault files that have `project: {old}` or `domain: {old}`.
- **Tags `project/{old}` or `domain/{old}`**: all files with this tag (cross-cutting: can be in `40-principles/`, `50-goals/`, etc.).
- **Obsidian links**: `[[{old}]]`, `[[{old}/...]]`, `[[archives/...{old}...]]`.
- **`index.md`**: project/domain entry + archive entries.
- **`history.md`**: title + links.
- **`context.md`**: `slug:` field of the frontmatter.
- **Sub-folders `50-goals/work/projects/{old}/`** if it exists.
- **(v0.7.0) Topology file**: `{VAULT}/99-meta/repo-topology/{old}.md` → `{VAULT}/99-meta/repo-topology/{new}.md`. The frontmatter `project: {old}` and the title `# Topology — {old}` are also updated.
- **(v0.7.0) Archeo-* atoms**: all atoms with `source: archeo-context|archeo-stack|archeo-git` carrying `project: {old}`. Their frontmatter `project:`, tag `project/{old}`, and any `context_origin` referencing the renamed topology are updated.

### 4. Present the plan

Format:

```
## Rename — {old} → {new} ({kind})

Files affected: {N}
  - Main folder: {old-path} → {new-path}
  - Archives: {N} files (frontmatter + tags)
  - Cross-cutting atoms (40-principles, 50-goals, ...): {N} files
  - Obsidian links in the vault: {N} occurrences
  - Global index: 1 entry
  - History: 1 file

Continue? [y/n]
```

If `--dry-run`: stop here.

### 5. Apply (if confirmed or `--no-confirm`)

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

Steps (order matters):

1. **Rename the folder**: `mv {VAULT}/10-episodes/{kind}/{old}/ {VAULT}/10-episodes/{kind}/{new}/`
2. **Rename archive files** in `{new}/archives/` that contain `{old}` in their name: `2026-01-15-...-{old}-...md` → `2026-01-15-...-{new}-...md`
3. **Rewrite frontmatters and tags**: for each affected file, regex replace `project: {old}` → `project: {new}`, `domain: {old}` → `domain: {new}`, `project/{old}` → `project/{new}`, `domain/{old}` → `domain/{new}`. Pattern 1+2 on every write.
4. **Rewrite Obsidian links** across the whole vault: grep + replace `[[{old}` → `[[{new}` (prefix, beware of false positives in archive names).
5. **Update `index.md`**: project/domain entry + archive entries.
6. **Update `50-goals/work/projects/`** if affected.
7. **(v0.7.0) Rename topology file** if `{VAULT}/99-meta/repo-topology/{old}.md` exists: `mv {old}.md {new}.md`, then rewrite its frontmatter (`project: {new}`, tags) and title (`# Topology — {new}`). Recompute `content_hash` since the body changed.
8. **(v0.7.0) Rewrite archeo-* atoms** — for each atom with `source: archeo-*` carrying `project: {old}`: update frontmatter `project: {new}`, tag `project/{new}`, and any `context_origin` wikilink that points to the old topology (`[[99-meta/repo-topology/{old}]]` → `[[99-meta/repo-topology/{new}]]`).

### 6. Confirm

Format:

```
Rename done: {old} → {new} ({kind})
{N} files modified
{N} links rewritten

Check the result in Obsidian (Graph + tree).
```
