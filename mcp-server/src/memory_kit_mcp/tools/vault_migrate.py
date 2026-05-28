"""mem_vault_migrate — Move the entire vault to a new filesystem location.

Spec: core/procedures/mem-vault-migrate.md

Typical use case: disk reorganization (e.g. ``C:\\_BDC\\GMT\\memory`` ->
``D:\\_BDC\\GMT\\memory``). The skill performs four steps:

1. Pre-flight checks (source exists, target free, no Obsidian lock, disk
   space if cross-volume, etc.).
2. Move the vault tree (``shutil.move`` — handles cross-volume copy + delete).
3. Update ``~/.memory-kit/config.json`` (authoritative) and every per-CLI
   ``memory-kit.json`` that mentions the old vault path.
4. Patch ``~/.claude/settings.json`` ``permissions.additionalDirectories``
   to swap the old vault path for the new one.

Idempotent on ``confirm=False`` (dry-run, no FS mutation).
Append-only audit entry written to ``99-meta/migrations/vault-migrations.md``
inside the (new) vault.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import _resolve_config_path, get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault.atomic_io import write_atomic

# Per-CLI ``memory-kit.json`` candidate paths (relative to ``$HOME``). These
# are written by ``deploy.ps1`` / ``deploy.sh`` and each one carries an
# independent ``vault`` field. We patch them all so a CLI that bypasses
# ``~/.memory-kit/config.json`` still sees the new path.
_CLI_CONFIG_CANDIDATES = (
    ".claude/memory-kit.json",
    ".codex/memory-kit.json",
    ".copilot/memory-kit.json",
    ".gemini/memory-kit.json",
    ".gemini/antigravity/memory-kit.json",
    ".gemini/antigravity-cli/memory-kit.json",
    ".vibe/memory-kit.json",
)


def _normalize_path(p: str | Path) -> Path:
    """Resolve to an absolute :class:`Path` with normalized separators.

    Does NOT call ``.resolve()`` (avoids requiring the path to exist on disk —
    target may not exist yet).
    """
    return Path(p).expanduser().absolute()


def _paths_equal(a: Path, b: Path) -> bool:
    """Compare two paths case-insensitively on Windows, exact elsewhere."""
    import os
    sa = str(a).replace("\\", "/")
    sb = str(b).replace("\\", "/")
    if os.name == "nt":
        sa, sb = sa.lower(), sb.lower()
    return sa.rstrip("/") == sb.rstrip("/")


def _vault_is_locked(vault: Path) -> list[str]:
    """Return the list of Obsidian-style lock files present in the vault."""
    if not vault.exists():
        return []
    lock_globs = ("*.lock", "**/.~lock.*", ".obsidian/workspace.json.lock")
    locks: list[Path] = []
    for pattern in lock_globs:
        locks.extend(vault.glob(pattern))
    return [str(p) for p in locks]


def _disk_free_bytes(target_parent: Path) -> int | None:
    """Return free bytes on ``target_parent`` volume (None on failure)."""
    try:
        return shutil.disk_usage(target_parent).free
    except (FileNotFoundError, OSError):
        return None


def _tree_size_bytes(path: Path) -> int:
    """Return total size of a tree (best-effort, no hard error on permission)."""
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def _patch_cli_configs(home: Path, old_vault: Path, new_vault: Path) -> list[str]:
    """Rewrite ``vault`` field in every per-CLI memory-kit.json file found.

    Returns the list of files actually modified.
    """
    modified: list[str] = []
    new_vault_str = str(new_vault)
    for rel in _CLI_CONFIG_CANDIDATES:
        p = home / rel
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        current = data.get("vault")
        if not isinstance(current, str):
            continue
        if _paths_equal(Path(current), new_vault):
            continue  # already up to date
        if not _paths_equal(Path(current), old_vault):
            continue  # points elsewhere (foreign vault), don't touch
        data["vault"] = new_vault_str
        write_atomic(p, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        modified.append(str(p))
    return modified


def _patch_claude_additional_dirs(
    home: Path, old_vault: Path, new_vault: Path
) -> str | None:
    """Swap old vault path for new one inside ``permissions.additionalDirectories``.

    Returns the path of the modified file or None if untouched.
    """
    p = home / ".claude" / "settings.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    perms = data.get("permissions") or {}
    dirs = perms.get("additionalDirectories")
    if not isinstance(dirs, list):
        return None
    changed = False
    new_dirs: list[str] = []
    new_vault_str = str(new_vault)
    seen_new = False
    for entry in dirs:
        if isinstance(entry, str) and _paths_equal(Path(entry), old_vault):
            new_dirs.append(new_vault_str)
            changed = True
            seen_new = True
        else:
            if isinstance(entry, str) and _paths_equal(Path(entry), new_vault):
                seen_new = True
            new_dirs.append(entry)
    if not changed and not seen_new:
        new_dirs.append(new_vault_str)
        changed = True
    if not changed:
        return None
    perms["additionalDirectories"] = new_dirs
    data["permissions"] = perms
    write_atomic(p, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return str(p)


def _append_migration_log(vault: Path, old_vault: Path, new_vault: Path) -> str:
    """Append an audit entry to ``99-meta/migrations/vault-migrations.md``.

    Creates the file with a header on first call.
    """
    from datetime import datetime

    log = vault / "99-meta" / "migrations" / "vault-migrations.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "---\n"
        "zone: meta\n"
        "kind: migration-log\n"
        "type: vault-migrations\n"
        "tags: [zone/meta, kind/migration-log, type/vault-migrations]\n"
        "display: vault — migration log\n"
        "---\n\n"
        "# Vault — Migration log\n\n"
        "Append-only history of ``mem_vault_migrate`` operations.\n\n"
    )
    if not log.exists():
        log.write_text(header, encoding="utf-8", newline="\n")
    entry = (
        f"- **{datetime.now().strftime('%Y-%m-%d %H:%M')}** — "
        f"vault moved\n"
        f"  - old: `{old_vault}`\n"
        f"  - new: `{new_vault}`\n"
    )
    with log.open("a", encoding="utf-8", newline="\n") as f:
        f.write(entry + "\n")
    return str(log)


def register(mcp: FastMCP) -> None:
    """Register ``mem_vault_migrate`` with the FastMCP instance."""

    @mcp.tool()
    def mem_vault_migrate(
        target: str = Field(..., description="Absolute path of the new vault location."),
        confirm: bool = Field(
            False,
            description="Without confirm=True the call is a dry-run (no FS mutation).",
        ),
    ) -> ChangeReport:
        """Move the entire vault tree to ``target`` and rewire every config.

        Effects (when ``confirm=True``):
        - Moves ``{source}`` -> ``{target}`` (cross-volume safe via ``shutil.move``).
        - Updates ``~/.memory-kit/config.json``.
        - Updates every per-CLI ``memory-kit.json`` (Claude, Codex, Copilot,
          Gemini, Antigravity CLI/Desktop, Vibe) that currently points to the
          old vault. Foreign vault references are left intact.
        - Patches ``~/.claude/settings.json`` ``permissions.additionalDirectories``.
        - Writes an audit entry to ``{target}/99-meta/migrations/vault-migrations.md``.

        On ``confirm=False`` the same checks run and the plan is returned with
        no mutation.

        Pre-conditions:
        - Source vault exists and matches ``~/.memory-kit/config.json:vault``.
        - Target either does not exist or is an empty directory.
        - No Obsidian lock files inside the vault (close Obsidian first).
        - On cross-volume moves, free space on the target volume covers the
          source size with a 10% safety margin.
        """
        config = get_config()
        source = _normalize_path(config.vault)
        target_p = _normalize_path(target)
        home = Path.home()

        warnings: list[str] = []

        # ---- Pre-flight checks --------------------------------------------
        if not source.exists():
            raise FileNotFoundError(
                f"Current vault path does not exist on disk: {source}"
            )
        if _paths_equal(source, target_p):
            raise ValueError("Target equals source — nothing to do.")
        if target_p.exists():
            if not target_p.is_dir():
                raise FileExistsError(f"Target exists and is not a directory: {target_p}")
            if any(target_p.iterdir()):
                raise FileExistsError(
                    f"Target directory is not empty: {target_p}. "
                    "Refusing to overwrite — pick another path or empty the dir."
                )
        # Make sure target parent exists or can be created.
        if not target_p.parent.exists():
            if confirm:
                target_p.parent.mkdir(parents=True, exist_ok=True)
            else:
                warnings.append(
                    f"Target parent does not exist (will be created on confirm): "
                    f"{target_p.parent}"
                )
        # Obsidian lock detection.
        locks = _vault_is_locked(source)
        if locks:
            raise RuntimeError(
                "Vault is locked by Obsidian (close it first). "
                f"Lock files found: {locks}"
            )
        # Disk space for cross-volume moves.
        src_drive = source.drive if source.drive else str(source.anchor)
        tgt_drive = target_p.drive if target_p.drive else str(target_p.anchor)
        cross_volume = src_drive.lower() != tgt_drive.lower() if src_drive else False
        size_bytes: int | None = None
        if cross_volume:
            size_bytes = _tree_size_bytes(source)
            free = _disk_free_bytes(target_p.parent if target_p.parent.exists() else target_p.anchor)
            if free is not None and size_bytes > free * 0.9:
                raise RuntimeError(
                    f"Insufficient free space on target volume. "
                    f"Source size ≈ {size_bytes / 1024 / 1024:.1f} MB, "
                    f"free ≈ {free / 1024 / 1024:.1f} MB. "
                    "Need a 10% headroom for safe cross-volume move."
                )
            warnings.append(
                f"Cross-volume move detected ({src_drive} -> {tgt_drive}): "
                f"~{(size_bytes or 0) / 1024 / 1024:.1f} MB to copy. Not atomic."
            )

        # ---- Dry-run -------------------------------------------------------
        plan = (
            f"**mem_vault_migrate** (dry-run)\n\n"
            f"- Source : `{source}`\n"
            f"- Target : `{target_p}`\n"
            f"- Cross-volume : {'yes' if cross_volume else 'no'}\n"
            + (f"- Size : ~{(size_bytes or 0) / 1024 / 1024:.1f} MB\n" if size_bytes else "")
            + f"- Per-CLI configs to patch : "
            f"{sum(1 for c in _CLI_CONFIG_CANDIDATES if (home / c).exists())}\n"
            f"- Will patch ``~/.claude/settings.json:permissions.additionalDirectories``\n"
            f"- Audit entry will be appended to ``{target_p}/99-meta/migrations/vault-migrations.md``\n"
        )

        if not confirm:
            return ChangeReport(
                skill="mem_vault_migrate",
                success=True,
                files_moved=[(str(source), str(target_p))],
                warnings=warnings + ["Dry-run only — pass confirm=True to apply."],
                summary_md=plan,
            )

        # ---- Apply ---------------------------------------------------------
        shutil.move(str(source), str(target_p))

        # Update authoritative ~/.memory-kit/config.json.
        cfg_path = _resolve_config_path()
        cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg_data["vault"] = str(target_p)
        write_atomic(cfg_path, json.dumps(cfg_data, indent=2, ensure_ascii=False) + "\n")

        # Patch per-CLI configs.
        cli_modified = _patch_cli_configs(home, source, target_p)

        # Patch Claude additional dirs.
        claude_modified = _patch_claude_additional_dirs(home, source, target_p)

        # Audit entry.
        log_file = _append_migration_log(target_p, source, target_p)

        files_modified = [str(cfg_path)] + cli_modified
        if claude_modified:
            files_modified.append(claude_modified)
        files_created = [log_file] if not Path(log_file).exists() else []

        summary = (
            f"**mem_vault_migrate** — vault moved\n\n"
            f"- `{source}` → `{target_p}`\n"
            f"- `~/.memory-kit/config.json` : `vault` field updated\n"
            f"- {len(cli_modified)} per-CLI `memory-kit.json` patched\n"
            f"- `~/.claude/settings.json` "
            f"`additionalDirectories` : {'patched' if claude_modified else 'unchanged'}\n"
            f"- Audit entry appended to `99-meta/migrations/vault-migrations.md`\n\n"
            f"Restart Obsidian + any running MCP client to pick up the new path.\n"
        )

        return ChangeReport(
            skill="mem_vault_migrate",
            success=True,
            files_moved=[(str(source), str(target_p))],
            files_modified=files_modified,
            files_created=files_created,
            warnings=warnings,
            summary_md=summary,
        )
