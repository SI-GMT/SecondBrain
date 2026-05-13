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


# Canonical SecondBrain zone layout — must stay aligned with
# ``memory_kit_mcp.health.scan.ZONES``. The kit emits a
# ``missing-zone-index`` health finding when a zone dir exists without
# an ``index.md``, so we ship one for every zone we create here.
VAULT_ZONES: tuple[tuple[str, str, str], ...] = (
    (
        "00-inbox",
        "Inbox",
        "Catch-all zone for documents ingested via `/mem-doc` and atoms\n"
        "not yet classified into a project or domain. The kit either\n"
        "auto-classifies them or surfaces them in `/mem-list` for manual\n"
        "reclassification (`/mem-reclass`).",
    ),
    (
        "10-episodes",
        "Episodes",
        "Project- and domain-bound history. Each project lives under\n"
        "`projects/{slug}/` with `context.md`, `history.md` and an\n"
        "`archives/` folder holding the immutable per-session entries.\n"
        "Domains use `domains/{slug}/` with the same shape.",
    ),
    (
        "20-knowledge",
        "Knowledge",
        "Transverse knowledge atoms (notes, snippets, references) that\n"
        "are not tied to a single project or session.",
    ),
    (
        "30-procedures",
        "Procedures",
        "Reusable procedures, checklists and runbooks the agent should\n"
        "follow consistently across sessions.",
    ),
    (
        "40-principles",
        "Principles",
        "Standing instructions and design principles. The LLM treats\n"
        "these as ground truth when reasoning across projects.",
    ),
    (
        "50-goals",
        "Goals",
        "Long-running objectives and outcomes. Reviewed during\n"
        "`/mem-recall` to anchor the session against the bigger picture.",
    ),
    (
        "60-people",
        "People",
        "Person cards documenting colleagues, clients and stakeholders.\n"
        "Surfaced when their names appear in the conversation.",
    ),
    (
        "70-cognition",
        "Cognition",
        "Meta-cognitive notes about how the user thinks, recurring biases\n"
        "and feedback patterns. The agent adapts its style accordingly.",
    ),
    (
        "99-meta",
        "Meta",
        "Vault meta-state: index, statistics, archeo manifests — the\n"
        "kit's own bookkeeping. Rarely edited by hand.",
    ),
)


VAULT_INDEX_BODY = """---
title: SecondBrain Vault
type: index
display: SecondBrain Vault
---

# SecondBrain - your second brain vault

This folder is your persistent memory for every LLM agent connected
to SecondBrain (Claude Code, Codex, Gemini CLI, Mistral Vibe, GitHub
Copilot CLI, Claude Desktop). Anything the agents archive lands here
in plain Markdown - open it in Obsidian, in your favourite editor, or
grep through it; it is just files.

## Layout

| Zone               | Purpose                                                                |
|--------------------|------------------------------------------------------------------------|
| `00-inbox/`        | Catch-all for ingested documents before classification.                |
| `10-episodes/`     | Project- and domain-bound history (context, archives, timeline).       |
| `20-knowledge/`    | Transverse knowledge atoms unrelated to a single project.              |
| `30-procedures/`   | Reusable procedures and runbooks.                                      |
| `40-principles/`   | Standing instructions and design principles.                           |
| `50-goals/`        | Long-running objectives.                                               |
| `60-people/`       | Person cards.                                                          |
| `70-cognition/`    | Meta-cognitive notes about how the user thinks.                        |
| `99-meta/`         | Kit-side meta-state (index, statistics, manifests).                    |

## First steps

1. Talk to your LLM agent normally - it can already write here.
2. Trigger `/mem-archive` at the end of a session to capture the state.
3. Run `/mem-recall` at the start of the next session to reload context.
4. Browse this folder in Obsidian to visualise the knowledge graph.

The desktop tray monitors this vault and surfaces health findings in
the notification icon. You never need to edit files here by hand.
"""


def _zone_index_body(slug: str, display: str, body: str) -> str:
    """Render the canonical frontmatter + body for a zone's ``index.md``."""
    return (
        "---\n"
        f"title: {display}\n"
        "type: zone\n"
        f"display: {display}\n"
        f"slug: {slug}\n"
        "---\n\n"
        f"# {display}\n\n"
        f"{body}\n"
    )


def _scaffold_base_structure(vault: Path) -> int:
    """Lay out the canonical SecondBrain zone structure under ``vault``.

    Creates every zone listed in :data:`VAULT_ZONES` (numbered prefix,
    aligned with ``memory_kit_mcp.health.scan.ZONES``) and writes an
    ``index.md`` hub per zone so the kit's ``missing-zone-index``
    health check stays clean from day one. Idempotent - never
    overwrites an existing file. Returns the number of fresh files
    written.
    """
    written = 0
    index = vault / "index.md"
    if not index.exists():
        index.write_text(VAULT_INDEX_BODY, encoding="utf-8", newline="\n")
        written += 1

    for slug, display, body in VAULT_ZONES:
        zone_dir = vault / slug
        zone_dir.mkdir(parents=True, exist_ok=True)
        zone_index = zone_dir / "index.md"
        if not zone_index.exists():
            zone_index.write_text(
                _zone_index_body(slug, display, body),
                encoding="utf-8",
                newline="\n",
            )
            written += 1
    return written


def scaffold_vault(
    vault: Path, obsidian_style_dir: Path | None = None
) -> VaultSetupResult:
    """Lay out the SecondBrain vault scaffold under ``vault``.

    Two layers:

    1. **Base structure** - canonical zone folders (``00-inbox``,
       ``10-episodes``, … ``99-meta``) each with their own
       ``index.md`` hub, plus a root ``index.md`` welcome page.
       Idempotent: never overwrites an existing file.
    2. **Obsidian config** - mirrors ``obsidian_style_dir`` (the
       kit's ``adapters/obsidian-style/``) into ``vault/.obsidian/``
       with the same canonical-marker discipline as ``deploy.ps1``'s
       ``Deploy-ObsidianStyle`` bridge.

    If ``obsidian_style_dir`` is missing the vault is still
    scaffolded - the kit works fine without the graph palette.
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


@dataclass
class VaultStructureAudit:
    """Snapshot of which canonical zones / hubs are missing from a vault.

    Returned by :func:`audit_vault_structure`. The Settings and Scan
    dialogs render the missing list and enable a "Repair structure"
    button when any element is missing.
    """

    vault: Path
    missing_zone_dirs: list[str]
    missing_zone_indexes: list[str]
    root_index_missing: bool
    non_canonical_top_level: list[str]  # info-only, surfaced for user awareness

    @property
    def needs_repair(self) -> bool:
        return (
            self.root_index_missing
            or bool(self.missing_zone_dirs)
            or bool(self.missing_zone_indexes)
        )

    def summary(self) -> str:
        if not self.needs_repair:
            return "Vault structure: complete."
        parts: list[str] = []
        if self.root_index_missing:
            parts.append("root index.md missing")
        if self.missing_zone_dirs:
            parts.append(
                f"{len(self.missing_zone_dirs)} missing zone dir(s)"
            )
        if self.missing_zone_indexes:
            parts.append(
                f"{len(self.missing_zone_indexes)} missing zone index(es)"
            )
        return "Vault structure incomplete: " + ", ".join(parts)


# Known non-canonical top-level entries we want to leave alone (Obsidian
# config + the kit's runtime caches). Anything else surfaced as
# "non-canonical" prompts the user to consider reclassifying its content.
_VAULT_NEUTRAL_TOP_LEVEL = {
    ".obsidian",
    ".trash",
    ".memory-kit",
    "index.md",
}


def audit_vault_structure(vault: Path) -> VaultStructureAudit:
    """Return which canonical zones / hubs the vault is missing.

    Pure-read: never touches the filesystem beyond ``Path.exists``
    probes. Safe to call from a UI handler.

    A vault is "complete" when:

    * ``vault/index.md`` exists.
    * Every zone slug in :data:`VAULT_ZONES` has its directory.
    * Every present zone directory has its ``index.md`` hub.

    Non-canonical top-level entries are surfaced separately as info
    only — they are not deleted, but the user may want to reclassify
    their content via ``/mem-reclass`` after the repair.
    """
    missing_dirs: list[str] = []
    missing_indexes: list[str] = []
    canonical_slugs = {slug for slug, _, _ in VAULT_ZONES}

    if not vault.is_dir():
        return VaultStructureAudit(
            vault=vault,
            missing_zone_dirs=[s for s, _, _ in VAULT_ZONES],
            missing_zone_indexes=[],
            root_index_missing=True,
            non_canonical_top_level=[],
        )

    for slug, _display, _body in VAULT_ZONES:
        zone_dir = vault / slug
        if not zone_dir.is_dir():
            missing_dirs.append(slug)
            continue
        if not (zone_dir / "index.md").is_file():
            missing_indexes.append(slug)

    non_canonical: list[str] = []
    try:
        for entry in vault.iterdir():
            name = entry.name
            if name in _VAULT_NEUTRAL_TOP_LEVEL:
                continue
            if name in canonical_slugs:
                continue
            non_canonical.append(name)
    except OSError:
        pass

    return VaultStructureAudit(
        vault=vault,
        missing_zone_dirs=missing_dirs,
        missing_zone_indexes=missing_indexes,
        root_index_missing=not (vault / "index.md").is_file(),
        non_canonical_top_level=sorted(non_canonical),
    )


def repair_vault_structure(
    vault: Path, *, obsidian_style_dir: Path | None = None
) -> VaultSetupResult:
    """Apply :func:`scaffold_vault` to fill in missing canonical pieces.

    Idempotent: existing files are never overwritten. Wraps the same
    scaffold function used at first-run so the Settings / Scan
    "Repair structure" buttons converge on the canonical layout.
    """
    return scaffold_vault(vault, obsidian_style_dir=obsidian_style_dir)


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
