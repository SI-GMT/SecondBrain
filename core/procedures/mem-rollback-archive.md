# Procedure: Rollback Archive (v0.5 brain-centric)

Goal: cancel the latest archive of a project/domain (or the global vault). Removes the archive file **AND its derived atoms** (chained via `derived_atoms`). Asks for confirmation if derived atoms would be orphaned.

**Known limit**: the project/domain `context.md` is **overwritten** at each full archive. The rollback does **not automatically restore** the previous `context.md` — the user can re-run `/mem-recall {slug}` to regenerate a context based on the second-to-last archive.

## Trigger

The user types `/mem-rollback-archive [{slug}]` or expresses the intent in natural language: "cancel the last archive", "forget the last session", "rollback the X archive".

Arguments:
- `{slug}` (optional): slug of the project/domain. If absent, rollback the latest global archive of the vault (all zones combined).
- `--with-derived`: also delete the derived atoms (by default, asks for confirmation).
- `--with-topology` (new in v0.7.0): also rollback the topology snapshot taken at this archive. Off by default — topology rollbacks are easy to mistake for cascade rollbacks.
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

### 2.5. Identify the topology rollback target (new in v0.7.0)

Read the archive's frontmatter for the v0.7.0 fields:
- `topology_snapshot_hash` — the hash of the topology snapshot at the time of this archive.
- `previous_topology_hash` — the hash that the topology had before this archive (empty if this was the first snapshot).

Then, if `--with-topology` is set:

- Read the current topology file `{VAULT}/99-meta/repo-topology/{slug}.md` (if it exists). Compare its `content_hash` to the archive's `topology_snapshot_hash`:
  - **Equal** → safe to roll back. Either restore the previous snapshot or delete the topology file.
  - **Different** → the topology has evolved since this archive (a later archive or a `mem-archeo` run modified it). Rolling back would erase intermediate work. Display a warning and **abort the topology rollback step** (the rest of the rollback still proceeds).

- If `previous_topology_hash` is empty → this archive was the first to produce a topology. Rolling back deletes the topology file.
- If `previous_topology_hash` is set:
  - If the vault is Git-tracked, retrieve the body of the topology file at the commit where `content_hash == previous_topology_hash` (via `git log -p` on the topology path). Restore that body.
  - If the vault is **not** Git-tracked, restoration is impossible. Display a warning: "Cannot restore topology — vault not Git-tracked. Topology will be deleted instead, and re-running /mem-archeo on the project will recreate it." Confirm with the user before deleting.

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

Topology rollback (only if --with-topology):
  - Current topology hash: {hash}
  - Archive's topology_snapshot_hash: {hash}
  - Action: {restore previous | delete | abort (current evolved past this archive)}

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
5. **(v0.7.0) Topology rollback** if `--with-topology`:
   - If action is `restore previous`: write the restored body to `{VAULT}/99-meta/repo-topology/{slug}.md`, frontmatter updated (`content_hash` recomputed, `previous_topology_hash` reset to whatever the now-restored snapshot had as its previous).
   - If action is `delete`: `rm {VAULT}/99-meta/repo-topology/{slug}.md`.
   - If action is `abort` (current evolved past this archive): no-op, log in the report.

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
