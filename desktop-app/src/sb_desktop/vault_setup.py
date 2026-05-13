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


VAULT_BASE_FOLDERS = ("archives", "projets", "perso", "inbox")

VAULT_INDEX_BODY = """---
title: SecondBrain — Vault index
type: index
display: SecondBrain — Vault
---

# SecondBrain — your second brain vault

This folder is your **persistent memory** for every LLM agent connected
to SecondBrain (Claude Code, Codex, Gemini CLI, Mistral Vibe, GitHub
Copilot CLI, Claude Desktop, …). Anything the agents archive lands here
in plain Markdown — open it in Obsidian, in your favourite text editor,
or `grep` through it; it's just files.

## Layout

| Folder       | Purpose                                                                 |
|--------------|-------------------------------------------------------------------------|
| `archives/`  | Timestamped, immutable session archives. One per `/mem-archive` call.   |
| `projets/`   | Project-specific living context (`{slug}/context.md`, `history.md`).   |
| `perso/`     | Personal notes / personae / principles outside any single project.      |
| `inbox/`     | Catch-all for ingested documents (`/mem-doc`) before classification.    |

## First steps

1. Talk to your LLM agent normally — it can already write here.
2. Trigger `/mem-archive` at the end of a session to capture the state.
3. Run `/mem-recall` at the start of the next session to reload context.
4. Browse this folder in Obsidian to visualise the knowledge graph.

The desktop tray monitors this vault and surfaces health findings in the
notification icon. You never need to edit files here by hand.
"""

VAULT_INBOX_README = """---
title: Inbox
type: zone
display: Inbox
---

# Inbox

Catch-all zone for documents ingested via `/mem-doc` and atoms that
haven't been classified into a project or domain yet. The kit will
either auto-classify them or surface them in `/mem-list` so you can
reclass them with `/mem-reclass`.
"""

VAULT_ARCHIVES_README = """---
title: Archives
type: zone
display: Archives
---

# Archives

Timestamped, immutable archives — one per `/mem-archive` call. Each
file documents a single session: what was decided, what shipped, what's
next. Never edit by hand; the kit treats them as ground truth.
"""

VAULT_PROJETS_README = """---
title: Projects
type: zone
display: Projects
---

# Projects

Living per-project state. Each project lives under `{slug}/` and holds:

* `context.md` — mutable snapshot of the project's current state.
* `history.md` — chronological timeline of archived sessions.
* `index.md` — entry point linked from this folder's index.

Create new projects implicitly by archiving a session under a project
name; the kit scaffolds the folder automatically.
"""


def _scaffold_base_structure(vault: Path) -> int:
    """Lay out the canonical SecondBrain folder structure under ``vault``.

    Idempotent — never overwrites existing content. Returns the number
    of fresh files written so the caller can report a summary.
    """
    written = 0
    index = vault / "index.md"
    if not index.exists():
        index.write_text(VAULT_INDEX_BODY, encoding="utf-8", newline="\n")
        written += 1

    zone_readmes: dict[str, str] = {
        "archives": VAULT_ARCHIVES_README,
        "projets": VAULT_PROJETS_README,
        "inbox": VAULT_INBOX_README,
    }
    for folder in VAULT_BASE_FOLDERS:
        target_dir = vault / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        readme_body = zone_readmes.get(folder)
        if readme_body is None:
            continue
        readme = target_dir / "index.md"
        if not readme.exists():
            readme.write_text(readme_body, encoding="utf-8", newline="\n")
            written += 1
    return written


def scaffold_vault(
    vault: Path, obsidian_style_dir: Path | None = None
) -> VaultSetupResult:
    """Lay out the SecondBrain vault scaffold under ``vault``.

    Two layers:

    1. **Base structure** — ``index.md`` welcome page + the standard
       zone folders (``archives/``, ``projets/``, ``perso/``, ``inbox/``)
       each with their own ``index.md`` describing their purpose.
       Idempotent: never overwrites a file the user already has.
    2. **Obsidian config** — mirrors ``obsidian_style_dir`` (the kit's
       ``adapters/obsidian-style/``) into ``vault/.obsidian/`` with
       the same canonical-marker discipline as ``deploy.ps1``'s
       ``Deploy-ObsidianStyle`` bridge.

    If ``obsidian_style_dir`` is missing the vault is still scaffolded
    — the kit works fine without the graph palette, the user just
    doesn't get the recommended colour groups out of the box.
    """
    vault.mkdir(parents=True, exist_ok=True)
    base_written = _scaffold_base_structure(vault)

    if obsidian_style_dir is None or not obsidian_style_dir.is_dir():
        return VaultSetupResult(
            target=vault,
            action="scaffolded",
            scaffold_files=base_written,
            detail=(
                f"laid out SecondBrain base structure "
                f"({base_written} files written; no Obsidian style adapter bundled)"
            ),
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
        scaffold_files=written + base_written,
        skipped_files=skipped,
        backed_up_files=backed_up,
        detail=(
            f"wrote {base_written} base files + {written} Obsidian config files"
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
