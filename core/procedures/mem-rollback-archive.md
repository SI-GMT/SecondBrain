# Procedure: Rollback Archive (v0.5 brain-centric)

Goal: cancel the latest archive of a project/domain (or the global vault). Removes the archive file **AND its derived atoms** (chained via `derived_atoms`). Asks for confirmation if derived atoms would be orphaned.

**Known limit**: the project/domain `context.md` is **overwritten** at each full archive. The rollback does **not automatically restore** the previous `context.md` — the user can re-run `/mem-recall {slug}` to regenerate a context based on the second-to-last archive.

## Trigger

The user types `/mem-rollback-archive [{slug}]` or expresses the intent in natural language: "cancel the last archive", "forget the last session", "rollback the X archive".

Arguments:
- `{slug}` (optional): slug of the project/domain. If absent, rollback the latest global archive of the vault (all zones combined).
- `--with-derived`: also delete the derived atoms (by default, asks for confirmation).
- `--no-confirm`: apply without confirmation.

## Vault path resolution

Read {{CONFIG_FILE}} and extract `vault`. If absent, standard error message and stop.

## Procedure

### 1. Identify the archive to delete

- If `{slug}` provided: read `{VAULT}/10-episodes/{kind}/{slug}/history.md`, take the latest archive entry.
- Otherwise: scan all projects' and domains' `history.md`, find the most recent archive in the vault.

If no archive found: display "No archive to cancel." and stop.

### 2. Identify the derived atoms

Read the frontmatter of the target archive. Extract the `derived_atoms` field. For each derived atom, check whether it has other parent archives (`context_origin` field possibly multi-valued):

- If the atom has **a single** parent archive (= the one being deleted) → it will be orphaned.
- If the atom has **several** parent archives → update: remove our archive from its list, keep the atom.

### 3. Present the plan

Format:

```
## Rollback — {slug or "global vault"}

Archive to delete:
  {archive path}

Derived atoms ({N}):
  - [[atom 1]] — orphaned after rollback: {yes|no}
  - [[atom 2]] — orphaned after rollback: {yes|no}

Action on atoms:
  - {N orphaned} will be deleted (with --with-derived) or kept (default, unlinked)
  - {N non-orphaned}: reference to the deleted archive removed

Continue? [y/n]
```

### 4. Apply (if confirmed or `--no-confirm`)

{{INCLUDE _encoding}}

{{INCLUDE _concurrence}}

Steps:

1. **Delete the archive file**: `rm {archive-path}`.
2. **For each derived atom**:
   - If orphaned and `--with-derived`: delete the file.
   - If orphaned without `--with-derived`: remove the `context_origin` field (atom becomes standalone).
   - If non-orphaned: remove our reference in `context_origin` (may be multi-valued).
3. **Remove the line in `history.md`** of the project/domain. Pattern 2.
4. **Remove the entry in `index.md`**. Pattern 2.

### 5. Context warning

Display:

```
Rollback done.
Deleted archive: {path}
Derived atoms: {N deleted, N unlinked}

WARNING: the project/domain context.md was NOT restored (it represented
the state at the moment of the deleted archive). To regenerate a coherent context,
run /mem-recall {slug} which will rely on the second-to-last archive.
```
