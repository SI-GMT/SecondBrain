# Procedure: Merge (v0.5 brain-centric)

Goal: merge two projects OR two domains in the memory vault. Reassigns archives, principles, goals, people linked to the source over to the target. Removes the source from the index.

Renamed from `mem-merge-projects` in v0.5. **Restriction**: you cannot mix project ↔ domain (their nature differs: a project ends, a domain does not). To turn a project into a domain, use `mem-promote-domain`.

## Trigger

The user types `/mem-merge {source} {target}` or expresses intent in natural language: "merge project X into Y", "group domains X and Y under Y".

Arguments:
- `{source}` (**required**): slug to merge (will be removed after merge).
- `{target}` (**required**): slug that absorbs (kept).
- `--dry-run`: shows the plan without applying.
- `--no-confirm`: applies without confirmation.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault`. If missing, standard error message and stop.

## Procedure

### 1. Identify the kind of both slugs

Search each in `projects/` then `domains/`. Verify they share **the same kind** (both projects, or both domains). Otherwise, stop with a clear message.

### 2. Enumerate items to transfer

- **Archives**: `{VAULT}/10-episodes/{kind}/{source}/archives/*.md` → target.
- **Source `history.md`**: to be merged at the end of the target `history.md` (chronological order preserved).
- **Source `context.md`**: DO NOT overwrite the target. Append the source's "Cumulative decisions" and "Next steps" sections into the target with a note `(merged from {source} on YYYY-MM-DD)`.
- **Cross-cutting atoms** (40-principles, 50-goals, 60-people, 20-knowledge) with tag `project/{source}` or `domain/{source}`: retag to `project/{target}` or `domain/{target}`. The `project:` / `domain:` frontmatter is also updated. **Includes archeo-* atoms** (`source: archeo-context|archeo-stack|archeo-git`).
- **(v0.7.0) Topology files**: if both `{VAULT}/99-meta/repo-topology/{source}.md` and `{target}.md` exist → topology merge required (cf. step 4). If only `{source}.md` exists → renamed to `{target}.md`. If only `{target}.md` exists → kept as-is, source archeo atoms retag onto it.
- **Obsidian links**: `[[{source}]]` → `[[{target}]]`. Includes wikilinks to the source topology.
- **`index.md`**: remove source, update target.

### 3. Present the plan

Format:

```
## Merge — {source} → {target} ({kind})

To transfer:
  - {N} archives → {VAULT}/10-episodes/{kind}/{target}/archives/
  - {N} history.md entries
  - {N} principles, {N} goals, {N} people, {N} knowledge notes retagged
  - {N} Obsidian links rewritten

To delete after merge:
  - Folder {VAULT}/10-episodes/{kind}/{source}/

target context.md: appending "Cumulative decisions" and "Next steps" sections

Continue? [y/n]
```

If `--dry-run`: stop here.

### 4. Apply (if confirmed or `--no-confirm`)

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

Steps:

1. **Move archives**: `mv {source}/archives/*.md {target}/archives/`. If name conflict (extremely rare with different timestamps), rename to `{name}-from-{source}.md`.
2. **Rename archive files** containing `{source}` in their name: `2026-01-15-...-{source}-...md` → `2026-01-15-...-{target}-...md`.
3. **Rewrite frontmatters**: replace `project: {source}` → `project: {target}` (and same for `domain:`) in all transferred files and in all cross-cutting atoms.
4. **Rewrite tags**: `project/{source}` → `project/{target}` (same for domain).
5. **Rewrite Obsidian links**: `[[{source}` → `[[{target}` across the whole vault.
6. **Merge `history.md`**: append source entries at the end of the target (preserve global chronological order → resort by date after merge).
7. **Append `context.md`**: add to the end of the target `context.md` a section "## Merged from {source} on YYYY-MM-DD" with the source's key sections.
8. **Delete the source folder**: `rm -rf {VAULT}/10-episodes/{kind}/{source}/` after verifying that all archives have been transferred.
9. **(v0.7.0) Topology merge**:
   - If only `{target}.md` exists → no action needed; source archeo atoms retagged at step 3 already reference the target.
   - If only `{source}.md` exists → `mv {source}.md {target}.md`, then update its frontmatter (`project: {target}`) and title.
   - If both exist → **union merge**:
     - Categories (sources, docs, manifests, ...) → set union (deduplicate).
     - `repo_path` and `repo_remote` → if values differ, **prompt the user** to pick one. Log the unkept one in a comment in the merged topology body. If `--no-confirm`, default to `{target}` values and log the conflict.
     - `Stack résolue` → keep `{target}`'s value, log `{source}`'s as a `## Stack alternative (merged from {source})` section in the body.
     - `Phases archeo couvertes` and `Atomes dérivés des phases archeo` → recomputed from the post-merge state of the vault (atoms now tagged `project/{target}`).
     - Recompute `content_hash`. The previous `{target}` hash goes into `previous_topology_hash`. The `{source}` topology file is deleted.
   - If a conflict cannot be resolved automatically and `--no-confirm` is set: write a `99-meta/merge-conflicts/{YYYY-MM-DD}-{source}-into-{target}.md` file with the diff, and abort the topology merge step (other steps still complete).
10. **Update `index.md`**: remove source entry, keep target.

### 5. Confirm

Format:

```
Merge done: {source} → {target} ({kind})
  Archives transferred: {N}
  Atoms retagged: {N}
  Links rewritten: {N}
  Source folder removed.
```
