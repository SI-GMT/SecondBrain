"""mem_migrate — Run pending vault schema migrations.

Spec: ``core/procedures/mem-migrate.md``.

Wraps ``memory_kit_mcp.migrations.run_pending`` as an MCP tool. Dry-run by
default — returns a report describing what would change without writing.
Pass ``apply=True`` to actually run the migrations. Auto-backup of the vault
is taken before any non-dry-run apply.

Idempotent: re-invoking on an already-migrated vault is a no-op (the report
just confirms "nothing to migrate").
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from memory_kit_mcp.config import _resolve_config_path, get_config
from memory_kit_mcp.migrations import (
    CURRENT_SCHEMA_VERSION,
    MigrationRunReport,
    run_pending,
)


class MigrationStepResult(BaseModel):
    target_version: int
    module: str
    needed: bool
    applied: bool
    files_modified: list[str] = Field(default_factory=list)
    files_created: list[str] = Field(default_factory=list)
    files_deleted: list[str] = Field(default_factory=list)
    summary: str = ""
    error: str = ""


class MigrationResult(BaseModel):
    """Public surface of ``mem_migrate``."""

    vault: str
    dry_run: bool
    from_version: int
    to_version: int
    target_version: int
    backup_path: str = ""
    steps: list[MigrationStepResult] = Field(default_factory=list)
    summary_md: str


def _to_pydantic(report: MigrationRunReport) -> MigrationResult:
    return MigrationResult(
        vault=report.vault,
        dry_run=report.dry_run,
        from_version=report.from_version,
        to_version=report.to_version,
        target_version=CURRENT_SCHEMA_VERSION,
        backup_path=report.backup_path,
        steps=[
            MigrationStepResult(
                target_version=s.target_version,
                module=s.module,
                needed=s.needed,
                applied=s.applied,
                files_modified=s.files_modified,
                files_created=s.files_created,
                files_deleted=s.files_deleted,
                summary=s.summary,
                error=s.error,
            )
            for s in report.steps
        ],
        summary_md=_render_summary(report),
    )


def _render_summary(report: MigrationRunReport) -> str:
    lines = [
        f"## mem_migrate — {report.vault}",
        "",
        f"- From schema version: **{report.from_version}**",
        f"- Target schema version: **{CURRENT_SCHEMA_VERSION}**",
        f"- Mode: **{'dry-run' if report.dry_run else 'apply'}**",
    ]
    if report.backup_path:
        lines.append(f"- Backup: `{report.backup_path}`")
    lines.append("")
    if not report.steps:
        lines.append("_No pending migrations._")
        return "\n".join(lines)
    lines.append("### Steps")
    lines.append("")
    for step in report.steps:
        marker = "✓" if step.applied else ("→" if step.needed else "·")
        lines.append(f"- {marker} **v{step.target_version}** (`{step.module}`) — "
                     f"needed={step.needed}, applied={step.applied}")
        if step.files_modified:
            lines.append(f"  - {len(step.files_modified)} file(s) modified")
        if step.files_created:
            lines.append(f"  - {len(step.files_created)} file(s) created")
        if step.error:
            lines.append(f"  - **error**: `{step.error}`")
    lines.append("")
    lines.append(report.summary)
    return "\n".join(lines)


def execute_migrate(
    vault: Path,
    config_path: Path,
    *,
    apply: bool = False,
    skip_backup: bool = False,
) -> MigrationResult:
    """Module-level entry — usable by the CLI without going through MCP."""
    report = run_pending(
        vault=vault,
        config_path=config_path,
        dry_run=not apply,
        skip_backup=skip_backup,
    )
    return _to_pydantic(report)


def register(mcp: FastMCP) -> None:
    """Register mem_migrate with the FastMCP instance."""

    @mcp.tool()
    def mem_migrate(
        apply: bool = Field(
            False,
            description=(
                "If False (default), only report what would be migrated (dry-run). "
                "If True, actually run the migrations after taking an automatic backup."
            ),
        ),
        skip_backup: bool = Field(
            False,
            description=(
                "Skip the automatic backup before applying. Use only for vaults > 500 MiB "
                "where the auto-backup would be impractical, or when you've made a manual "
                "backup. Ignored when apply=False."
            ),
        ),
    ) -> MigrationResult:
        """Run pending vault schema migrations.

        Dry-run by default. The vault is auto-backed-up before any apply (unless
        ``skip_backup=True``). Idempotent — calling twice in a row on an
        already-migrated vault is a no-op.

        Backups are stored under ``{config_dir}/backups/vault-{timestamp}/``
        as a directory copy (``.obsidian/`` and ``.trash/`` excluded).
        """
        config = get_config()
        config_path = _resolve_config_path()
        return execute_migrate(
            vault=config.vault,
            config_path=config_path,
            apply=apply,
            skip_backup=skip_backup,
        )
