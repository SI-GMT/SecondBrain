"""Vault migration framework — versioned, idempotent, dry-run by default.

Pattern:

- Every migration is a module under ``memory_kit_mcp.migrations`` (e.g.
  ``v1_zone_indexes.py``) that exports two functions:

  - ``is_needed(vault: Path) -> bool``: True if the migration must run.
  - ``apply(vault: Path, dry_run: bool) -> MigrationStepReport``: applies
    the changes, returns a report. Idempotent — safe to run multiple times.

- The current target schema version is ``CURRENT_SCHEMA_VERSION``. A vault
  whose ``vault_schema_version`` (in ``~/.memory-kit/config.json``) is below
  the target needs the missing migrations chained in order.

- ``run_pending(vault, config_path, dry_run, ...)`` is the orchestrator:
  detects what's needed, runs them in order, takes a backup before any
  write, updates the version marker on success.

- A backup is taken automatically before any non-dry-run apply. Backup goes
  to ``~/.memory-kit/backups/vault-{timestamp}/`` as a directory copy, with
  size capped to avoid blowing disk on multi-GB vaults (warning + opt-in).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Schema version targeted by the current code. Bump when adding a migration.
CURRENT_SCHEMA_VERSION = 2

# Ordered list of migrations. Each entry is (target_version, module_name).
MIGRATIONS: tuple[tuple[int, str], ...] = (
    (1, "v1_zone_indexes"),
    (2, "v2_namespace_to_domain"),
)

# Soft cap on vault size for the auto-backup. Above this, the user must
# pass ``skip_backup=True`` explicitly (avoids surprise multi-GB copies).
MAX_AUTO_BACKUP_BYTES = 500 * 1024 * 1024  # 500 MiB


@dataclass
class MigrationStepReport:
    """Result of a single migration step."""

    target_version: int
    module: str
    needed: bool
    applied: bool
    dry_run: bool
    files_modified: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)
    summary: str = ""
    error: str = ""


@dataclass
class MigrationRunReport:
    """Aggregate report for a full ``run_pending`` invocation."""

    vault: str
    from_version: int
    to_version: int
    dry_run: bool
    backup_path: str = ""
    steps: list[MigrationStepReport] = field(default_factory=list)
    summary: str = ""


def get_vault_schema_version(config_path: Path) -> int:
    """Return the recorded vault schema version. Defaults to 0 (pre-migration)
    when the field is absent — so a fresh install or a vault never migrated
    is treated correctly without raising.
    """
    if not config_path.is_file():
        return 0
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return int(raw.get("vault_schema_version", 0))


def set_vault_schema_version(config_path: Path, version: int) -> None:
    """Update the vault schema version atomically in the config file. Creates
    the file if it doesn't exist (empty config + just the version field).
    """
    raw: dict = {}
    if config_path.is_file():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
    raw["vault_schema_version"] = version
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(config_path)


def _vault_size_bytes(vault: Path) -> int:
    total = 0
    for p in vault.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def make_backup(vault: Path, backup_root: Path) -> Path:
    """Take a backup of the vault as a directory copy. Returns the backup path.

    Backup location: ``{backup_root}/vault-{timestamp}/``. Excludes
    ``.obsidian/`` (large, regenerable) and any ``.trash/``.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d-%Hh%M%S")
    target = backup_root / f"vault-{timestamp}"
    target.parent.mkdir(parents=True, exist_ok=True)

    def _ignore(_dir: str, names: list[str]) -> list[str]:
        return [n for n in names if n in (".obsidian", ".trash")]

    shutil.copytree(vault, target, ignore=_ignore)
    return target


def _load_module(module_name: str):
    """Dynamic import of ``memory_kit_mcp.migrations.{module_name}``."""
    from importlib import import_module

    return import_module(f"memory_kit_mcp.migrations.{module_name}")


def run_pending(
    vault: Path,
    config_path: Path,
    *,
    dry_run: bool = True,
    skip_backup: bool = False,
    backup_root: Path | None = None,
) -> MigrationRunReport:
    """Run all migrations whose target_version > current vault_schema_version.

    Args:
        vault: vault root.
        config_path: path to ``~/.memory-kit/config.json`` (where the schema
            version is recorded).
        dry_run: when True, no writes happen. The reports describe what
            *would* change.
        skip_backup: when True, skip the auto-backup before applying. Use only
            when the user is fully aware (or vault size > MAX_AUTO_BACKUP_BYTES
            and they accept the risk).
        backup_root: override the backup location. Default is
            ``{config_path.parent}/backups/``.

    Returns:
        ``MigrationRunReport`` aggregating per-step reports.
    """
    current = get_vault_schema_version(config_path)
    target = CURRENT_SCHEMA_VERSION

    report = MigrationRunReport(
        vault=str(vault),
        from_version=current,
        to_version=current,
        dry_run=dry_run,
    )

    pending = [(v, m) for (v, m) in MIGRATIONS if v > current]
    if not pending:
        report.summary = (
            f"Vault already at schema version {current} (target = {target}). "
            "Nothing to migrate."
        )
        return report

    # Backup before any non-dry-run write.
    if not dry_run and not skip_backup:
        size = _vault_size_bytes(vault)
        if size > MAX_AUTO_BACKUP_BYTES:
            report.summary = (
                f"Vault size {size / (1024*1024):.0f} MiB exceeds the "
                f"{MAX_AUTO_BACKUP_BYTES / (1024*1024):.0f} MiB auto-backup cap. "
                "Pass skip_backup=True if you want to proceed without backup, "
                "or back up manually first."
            )
            return report
        bk_root = backup_root or (config_path.parent / "backups")
        backup_path = make_backup(vault, bk_root)
        report.backup_path = str(backup_path)

    # Apply each pending migration in order.
    for version, module_name in pending:
        try:
            module = _load_module(module_name)
            needed = bool(module.is_needed(vault))
            step = MigrationStepReport(
                target_version=version, module=module_name,
                needed=needed, applied=False, dry_run=dry_run,
            )
            if not needed:
                step.summary = "Step reports not needed (already migrated or no-op)."
                report.steps.append(step)
                # A no-op step still moves the chain forward — the vault is
                # effectively at this target_version even if no writes were
                # required (e.g. the migration was already applied by an
                # earlier run, or the vault doesn't carry the entities the
                # migration touches). Bump the recorded schema version so
                # downstream queries see the vault as up to date.
                if not dry_run:
                    set_vault_schema_version(config_path, version)
                report.to_version = version
                continue
            sub = module.apply(vault, dry_run=dry_run)
            # The submodule returns a MigrationStepReport-ish dict or object.
            if isinstance(sub, MigrationStepReport):
                step.applied = sub.applied
                step.files_modified = sub.files_modified
                step.files_created = sub.files_created
                step.files_deleted = sub.files_deleted
                step.summary = sub.summary
                step.error = sub.error
            elif isinstance(sub, dict):
                step.applied = bool(sub.get("applied", False))
                step.files_modified = list(sub.get("files_modified", []))
                step.files_created = list(sub.get("files_created", []))
                step.files_deleted = list(sub.get("files_deleted", []))
                step.summary = str(sub.get("summary", ""))
                step.error = str(sub.get("error", ""))
            report.steps.append(step)
            if step.applied and not dry_run:
                # Bump the version marker after each successful step.
                set_vault_schema_version(config_path, version)
                report.to_version = version
        except Exception as exc:  # noqa: BLE001 — we want to surface any failure
            step = MigrationStepReport(
                target_version=version, module=module_name,
                needed=True, applied=False, dry_run=dry_run,
                error=f"{type(exc).__name__}: {exc}",
                summary=f"Step failed: {exc}",
            )
            report.steps.append(step)
            break  # stop at the first failure to keep the chain clean

    # Final summary
    if dry_run:
        report.summary = (
            f"Dry-run from version {current} -> target {target}. "
            f"{len([s for s in report.steps if s.needed])} step(s) would run."
        )
    else:
        report.summary = (
            f"Migrated from version {current} -> {report.to_version}. "
            f"{sum(1 for s in report.steps if s.applied)} step(s) applied. "
            + (f"Backup at {report.backup_path}." if report.backup_path else "")
        )
    return report
