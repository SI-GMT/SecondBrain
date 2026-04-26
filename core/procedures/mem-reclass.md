# Procedure: Reclass (new in v0.5)

Goal: change the scope or zone of an existing piece of content. Updates the frontmatter + tags + physically moves the file + rewrites cross-references (`_index`, `history`, Obsidian links).

Skill confirmed in v0.5 by decision D3.4: a piece of content can switch personal ↔ work, or change zone (e.g. a knowledge note becoming a principle), via an explicit operation.

## Trigger

The user types `/mem-reclass {path} [options]` or expresses intent in natural language: "reclassify this note", "turn this principle into a heuristic", "switch this note to personal".

Arguments:
- `{path}` (**required**): absolute or relative path of a file inside the vault.
- `--zone X`: new target zone (among the 9). Optional if only `--scope` changes.
- `--scope personal|work`: new scope. Optional if only `--zone` changes.
- `--type X`: new type (depending on target zone).
- `--project {slug}` or `--domain {slug}`: new attachment.
- `--dry-run`: shows the reclass plan without applying.
- `--no-confirm`: applies without asking for confirmation (batch mode).

At least one of `--zone`, `--scope`, `--type`, `--project`, `--domain` is required.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault`. If missing, standard error message and stop.

## Procedure

### 1. Validate the source file

- Verify that `{path}` exists and is inside the vault.
- Read its frontmatter (state before).
- Verify that the requested changes are valid (cf. invariants section 7.3 of the scoping doc):
  - If `--scope personal` but the file has `collective: true` → force it to `false` (with a warning).
  - If `--zone episodes` without `kind` nor `project`/`domain` → ask the user.
  - If `--zone X` invalid → stop with the list of accepted zones.

### 2. Compute the new frontmatter and the new path

Build the target frontmatter:
- Keep all fields except those explicitly changed.
- Adapt `tags` to reflect the changes (`zone/*`, `scope/*`, `type/*`, etc.).

Compute the new path:
- If `--zone` changes: new path according to the mapping in section R5 of the router block.
- If `--scope` changes for a zone that has `{scope}/` in its path (procedures, principles, goals, people): new path with updated scope.
- If `--project`/`--domain` changes for `episodes` zone: new project/domain folder.

### 3. Present the plan

Format:

```
## Reclass — {source path}

Before:
  zone   : {old}
  scope  : {old}
  type   : {old}
  ...

After:
  zone   : {new}
  scope  : {new}
  type   : {new}
  ...

New path: {new-path}

Links to rewrite:
  - {N} [[...]] links in other vault files
  - Entries in index.md
  - Entries in history.md (if source or target zone = episodes)

Continue? [y/n]
```

If `--dry-run`: stop here.

### 4. Apply (if confirmed or `--no-confirm`)

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

Steps:

1. **Write the file at the new location** with the new frontmatter (atomic rename).
2. **Rewrite Obsidian links**: grep `[[old-name]]` or `[[path/old]]` across the whole vault, replace with `[[new-name]]`. Patterns 1+2 on each modified file.
3. **Update `index.md`**: remove the old entry, add the new one if applicable. Pattern 2.
4. **If source zone = episodes**: remove the line in `history.md` of the source project/domain. Pattern 2.
5. **If target zone = episodes**: add the line in `history.md` of the target project/domain. Pattern 2.
6. **Delete the source file** (after verifying the destination copy exists).

### 5. Confirm

Format:

```
Reclass done:
  Source: {old-path} (deleted)
  Target: {new-path}

Links rewritten: {N} files updated
Index updated
```
