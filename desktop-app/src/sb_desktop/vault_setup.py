"""Vault relocation + Obsidian scaffolding.

When the canonical vault path changes (first-run wizard pick, settings
dialog edit), two outcomes are possible:

* **Old vault already has content** — move every entry (including the
  ``.obsidian/`` directory and any in-flight project state) into the
  new location. This preserves the user's archives, projects, and
  Obsidian config across the relocation.
* **Old vault is empty or absent** — create a fresh scaffold in the
  new location, including the Obsidian style adapter (graph palette,
  Front Matter Title config) so the directory opens as a working
  vault in Obsidian without any further manual setup.

Both paths are idempotent: re-running with the same source/target is a
no-op. The scaffolding never overwrites a user-customised Obsidian
config — it only touches files that carry the ``_secondbrain_canonical``
marker (parity with ``deploy.ps1``'s ``Deploy-ObsidianStyle`` bridge).
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

CANONICAL_MARKER_KEY = "_secondbrain_canonical"


@dataclass
class VaultSetupResult:
    """Outcome of one vault setup call — wizard renders this inline."""

    target: Path
    action: str           # "migrated" | "scaffolded" | "noop"
    moved_entries: int = 0
    scaffold_files: int = 0
    skipped_files: int = 0
    backed_up_files: int = 0
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.action != "error"


def _has_content(directory: Path) -> bool:
    """True if ``directory`` exists and contains at least one entry."""
    if not directory.is_dir():
        return False
    try:
        return any(directory.iterdir())
    except OSError:
        return False


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def migrate_vault(old_vault: Path, new_vault: Path) -> VaultSetupResult:
    """Move every entry from ``old_vault`` into ``new_vault``.

    The operation is best-effort and resilient:

    * ``new_vault`` is created if it doesn't exist.
    * Each top-level entry is moved with ``shutil.move``. If an entry
      already exists in the target we skip it and keep the source —
      manual reconciliation is safer than silent overwrite.
    * The old directory itself is removed once empty so the user
      doesn't end up with two confusingly similar folders.

    Returns a result describing what was moved.
    """
    if _same_path(old_vault, new_vault):
        return VaultSetupResult(
            target=new_vault, action="noop", detail="source equals target"
        )

    new_vault.mkdir(parents=True, exist_ok=True)
    moved = 0
    skipped = 0
    if old_vault.is_dir():
        for entry in list(old_vault.iterdir()):
            dest = new_vault / entry.name
            if dest.exists():
                log.warning("vault migrate: %s already exists, skipping", dest)
                skipped += 1
                continue
            try:
                shutil.move(str(entry), str(dest))
                moved += 1
            except OSError as exc:
                log.warning("vault migrate: could not move %s: %s", entry, exc)
                skipped += 1
        try:
            old_vault.rmdir()
        except OSError:
            # Non-empty (some skips) — leave it for the user to inspect.
            pass

    return VaultSetupResult(
        target=new_vault,
        action="migrated",
        moved_entries=moved,
        skipped_files=skipped,
        detail=(
            f"moved {moved} entries from {old_vault}"
            + (f" ({skipped} skipped)" if skipped else "")
        ),
    )


def _is_canonical_json(path: Path) -> bool:
    """True if a JSON file carries our ``_secondbrain_canonical`` marker."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and CANONICAL_MARKER_KEY in data


def _backup_path(target: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return target.with_name(f"{target.name}.bak-pre-style-{stamp}")


def scaffold_vault(
    vault: Path, obsidian_style_dir: Path | None = None
) -> VaultSetupResult:
    """Lay out the Obsidian-style adapter into ``vault/.obsidian/``.

    Mirrors the directory tree under ``obsidian_style_dir`` (recursive)
    into ``vault/.obsidian/`` with the same canonical-marker
    discipline as the kit's ``Deploy-ObsidianStyle`` bridge:

    * Missing target → write the canonical copy.
    * Existing canonical target (marker present) → back up + replace.
    * Existing customised target (marker absent) → skip silently.

    If ``obsidian_style_dir`` is ``None`` or missing we still create
    the vault directory (empty) — the kit will still work, the user
    just won't get the recommended graph palette out of the box.
    """
    vault.mkdir(parents=True, exist_ok=True)

    if obsidian_style_dir is None or not obsidian_style_dir.is_dir():
        return VaultSetupResult(
            target=vault,
            action="scaffolded",
            detail="vault directory created (no Obsidian style adapter bundled)",
        )

    obsidian_dir = vault / ".obsidian"
    obsidian_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    backed_up = 0

    for source in obsidian_style_dir.rglob("*"):
        if not source.is_file():
            continue
        if source.name.lower() == "readme.md":
            continue  # adapter doc, not a runtime artefact
        rel = source.relative_to(obsidian_style_dir)
        target = obsidian_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)

        if not target.exists():
            shutil.copy2(source, target)
            written += 1
            continue

        try:
            same = target.read_bytes() == source.read_bytes()
        except OSError:
            same = False
        if same:
            continue

        if target.suffix.lower() == ".json" and not _is_canonical_json(target):
            log.info("vault scaffold: %s is user-customised, skipping", target)
            skipped += 1
            continue

        try:
            backup = _backup_path(target)
            shutil.copy2(target, backup)
            backed_up += 1
        except OSError as exc:
            log.warning("vault scaffold: could not back up %s: %s", target, exc)

        shutil.copy2(source, target)
        written += 1

    return VaultSetupResult(
        target=vault,
        action="scaffolded",
        scaffold_files=written,
        skipped_files=skipped,
        backed_up_files=backed_up,
        detail=(
            f"wrote {written} Obsidian config files"
            + (f" ({skipped} user-customised skipped)" if skipped else "")
            + (f", {backed_up} backed up" if backed_up else "")
        ),
    )


def setup_vault(
    new_vault: Path,
    *,
    old_vault: Path | None = None,
    obsidian_style_dir: Path | None = None,
) -> VaultSetupResult:
    """End-to-end entry point used by the wizard and settings dialog.

    * If ``old_vault`` is given AND differs from ``new_vault`` AND has
      content → migrate, then scaffold the result (so a migrated
      vault still picks up newly-bundled Obsidian config files).
    * Otherwise → scaffold the new location directly.
    """
    if (
        old_vault is not None
        and not _same_path(old_vault, new_vault)
        and _has_content(old_vault)
    ):
        result = migrate_vault(old_vault, new_vault)
        scaffold = scaffold_vault(new_vault, obsidian_style_dir)
        result.scaffold_files = scaffold.scaffold_files
        result.backed_up_files = scaffold.backed_up_files
        result.skipped_files += scaffold.skipped_files
        result.detail = (
            f"{result.detail}; "
            f"then scaffolded {scaffold.scaffold_files} Obsidian files"
        )
        return result
    return scaffold_vault(new_vault, obsidian_style_dir)
