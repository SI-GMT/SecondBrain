# Procedure: `mem-migrate` (v0.9.4)

Goal: run pending vault schema migrations. The vault has a recorded schema version in ``~/.memory-kit/config.json`` (``vault_schema_version`` field, defaulting to 0). The kit code targets a specific version (``CURRENT_SCHEMA_VERSION`` constant). Whenever a structural change to the vault is shipped, a numbered migration is added — ``mem-migrate`` is the entry point that runs the missing migrations in order.

## When to invoke

- Right after a kit upgrade that bumps the target schema version (the deploy hook calls this automatically).
- Manually if a pilot wants to verify their vault is on the current schema (``apply=False`` for dry-run).
- After restoring a backup of an older vault state (the schema version is restored too — re-running the migration brings it forward).

## Arguments

- `apply` (bool, default False) — dry-run by default. Pass True to actually run.
- `skip_backup` (bool, default False) — skip the auto-backup. Use only when you've manually backed up or for vaults > 500 MiB (auto-backup is capped at 500 MiB to avoid surprise multi-GB copies).

## Behaviour

1. Read the recorded ``vault_schema_version`` from ``~/.memory-kit/config.json`` (or the override). Defaults to 0 if absent.
2. Compute pending migrations: every entry in ``MIGRATIONS`` with target_version > current.
3. If nothing pending → return a "nothing to migrate" report. No-op.
4. If ``apply=True`` AND ``skip_backup=False`` → take a backup of the vault to ``{config_dir}/backups/vault-{timestamp}/`` (excludes ``.obsidian/`` and ``.trash/``). Refuse if the vault size exceeds 500 MiB without ``skip_backup=True``.
5. Run each pending migration in order. Each is **idempotent** — safe to re-run. After each successful step, bump the recorded version.
6. Stop at the first failure (returns the partial report so the user can see what went wrong).
7. Return ``MigrationResult`` with per-step details.

## Doctrinal notes

- **Dry-run by default** — never writes anything unless ``apply=True``. Same pattern as ``mem-health-repair``.
- **Auto-backup before any apply** — defensive, since migrations modify multiple files. Easy rollback by copying the backup back over the vault.
- **Idempotent** — re-running on an already-migrated vault is a no-op. The deploy hook can call it unconditionally without risk.
- **Not transactional across multiple migrations** — if step 2 of a 2-step chain fails, step 1 is already applied. Recovery: fix the cause, re-run; step 1 is a no-op (idempotent), step 2 retries.
- **Schema version is per-vault, not per-machine** — the marker lives in ``~/.memory-kit/config.json`` which is per-machine. If a user has multiple vaults, each must be migrated separately.

## Migrations registered

| Version | Module | Description |
|---|---|---|
| 1 | ``v1_zone_indexes`` | Move transverse-atom listings (Principles / Knowledge / Goals / People) from the root ``index.md`` into each ``{zone}/index.md``. Adds a ``## Transverse atoms`` pointer to the root. |

## Output expected

```
## mem_migrate — {vault}

- From schema version: **{N}**
- Target schema version: **{CURRENT}**
- Mode: **dry-run** | **apply**
- Backup: `{path}` (apply mode only)

### Steps

- ✓ **v1** (`v1_zone_indexes`) — needed=True, applied=True
  - 4 file(s) modified
  - 0 file(s) created

Migrated from version 0 → 1. 1 step(s) applied. Backup at /path/to/backup.
```

## CLI alternative

For headless usage (deploy hook, CI):

```
python -m memory_kit_mcp.migrate                    # dry-run
python -m memory_kit_mcp.migrate --apply            # apply with backup
python -m memory_kit_mcp.migrate --apply --skip-backup
python -m memory_kit_mcp.migrate --vault /path      # explicit vault
python -m memory_kit_mcp.migrate --config /path     # explicit config
```

## Encoding

Backups are full directory copies (preserve original encoding). The migration writes new files in UTF-8 / LF / no BOM, like the rest of the kit.
