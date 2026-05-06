"""Vault hygiene scan — 15-category audit (shared library).

Spec: core/procedures/mem-health-scan.md
Mirrors: scripts/mem-health-scan.py (versioned standalone CLI) for the
12 vault categories. Categories ``mcp-tool-spec-drift``,
``skill-description-too-long`` and ``missing-zone-index-entry`` are mcp-only
by design: they audit the *kit repo* (core/procedures vs ``sync.json``, then
``adapters/`` SKILL.md templates) or rely on the vault zone-index machinery
that is bundled with the MCP server. The standalone — which scans vaults
from machines without the kit installed — has no equivalent for those.

Read-only. Detects 15 categories of issues:

- malformed-frontmatter  (error)  YAML frontmatter that fails to parse.
- stray-zone-md          (warn)   Empty MD at vault root named after a
                                  numbered zone (e.g. 20-knowledge.md).
                                  Created by Obsidian on click of a
                                  dangling wiki-link target.
- empty-md-at-root       (warn)   Other empty MDs at vault root.
- missing-zone-index     (warn)   Zone folder exists but lacks its
                                  {zone}/index.md hub.
- missing-display        (info)   Frontmatter without `display:` where
                                  universal conventions require it.
- dangling-wikilinks     (info)   [[X]] references whose target is not
                                  present anywhere in the vault.
- orphan-atoms           (warn)   Transverse atoms with no project/domain
                                  attachment AND zero incoming wikilinks.
- missing-archeo-hashes  (warn)   Atoms with source: archeo-* missing
                                  `content_hash` or (for repo-topology)
                                  `previous_topology_hash`.
- mcp-tool-spec-drift    (info)   Procedure body in core/procedures/mem-X.md
                                  diverges from the hash recorded in
                                  ``memory_kit_mcp/sync.json`` — signals
                                  that ``tools/X.py`` may need review.
                                  Skipped silently when ``kit_repo`` is not
                                  configured or ``sync.json`` is absent.
- skill-description-too-long (warn) SKILL.md (or *.template.md) frontmatter
                                  ``description`` exceeds the 1024-char
                                  Anthropic limit, breaking auto-trigger of
                                  the skill on Claude Code / Codex / Vibe /
                                  Copilot. Audits ``kit_repo/adapters/`` —
                                  Gemini excluded (TOML format). Skipped
                                  silently when ``kit_repo`` or
                                  ``adapters/`` is absent.
- missing-zone-index-entry (warn) Atom in a transverse zone (20-knowledge,
                                  40-principles, 50-goals, 60-people) is
                                  not listed in its ``{zone}/index.md``.
                                  v0.9.4 architecture: zone index is the
                                  authoritative listing of transverse atoms
                                  (root index points to zone indexes).
                                  Auto-fixable by ``mem_health_repair``
                                  (regenerates the affected zone index).
- missing-universal-frontmatter (warn) v0.10.0. Atom outside 00-inbox/ and
                                  99-meta/ without one of the universal
                                  MUST fields (scope, collective, modality).
                                  Documented in _frontmatter-universal.md.
                                  Surfaced after a less-rigorous LLM
                                  adapter produced batches of atoms with
                                  all three fields silently missing.
- missing-archeo-context-origin (warn) v0.10.0. Atom with source: archeo-*
                                  without context_origin OR with a
                                  context_origin not pointing to the
                                  required anchor (topology for
                                  archeo-context/stack, milestone archive
                                  for archeo-git derived atoms).
- archeo-derived-orphan         (warn) v0.10.0. Atom with source: archeo-git
                                  living outside 10-episodes/.../archives/
                                  but not referenced in derived_atoms of
                                  any milestone archive. The bidirectional
                                  link is broken (cf. mem-archeo-git.md §6).
- topology-archives-out-of-sync (info) v0.10.0. Topology in 99-meta/repo-
                                  topology/{slug}.md does not list one or
                                  more existing archives in 10-episodes/
                                  projects/{slug}/archives/ under its
                                  'Atomes dérivés' section.

The function returns Pydantic HealthFinding objects (defined in
tools._models) so the MCP tool layer can serialize them directly.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from memory_kit_mcp.tools._models import HealthFinding
from memory_kit_mcp.vault.wikilinks import WIKILINK_RE, strip_code

# ---- Constants ----

ZONES: tuple[str, ...] = (
    "00-inbox", "10-episodes", "20-knowledge", "30-procedures",
    "40-principles", "50-goals", "60-people", "70-cognition", "99-meta",
)

CATEGORIES: tuple[str, ...] = (
    "malformed-frontmatter",
    "stray-zone-md",
    "empty-md-at-root",
    "missing-zone-index",
    "missing-display",
    "dangling-wikilinks",
    "orphan-atoms",
    "missing-archeo-hashes",
    "mcp-tool-spec-drift",
    "skill-description-too-long",
    "missing-zone-index-entry",
    "missing-universal-frontmatter",
    "missing-archeo-context-origin",
    "archeo-derived-orphan",
    "topology-archives-out-of-sync",
)

# Universal frontmatter MUST fields per _frontmatter-universal.md
# (excluding inbox + meta zones which have their own minimal schemas).
UNIVERSAL_MUST: tuple[str, ...] = ("scope", "collective", "modality")

ARCHEO_SOURCES: tuple[str, ...] = ("archeo-context", "archeo-stack", "archeo-git")

# Adapters audited for the skill-description-too-long check. Each entry is a
# (adapter-name, glob relative to ``kit_repo/adapters/{adapter}/``).
# Gemini is excluded by design: its commands use TOML literal strings, not the
# Anthropic SKILL.md frontmatter format with the 1024-char description cap.
_SKILL_TEMPLATE_GLOBS: tuple[tuple[str, str], ...] = (
    ("claude-code", "skills/*.template.md"),
    ("codex", "skills/*/SKILL.md.template"),
    ("mistral-vibe", "skills/*/SKILL.md.template"),
    ("copilot-cli", "skills/*/SKILL.md.template"),
)

SKILL_DESCRIPTION_MAX = 1024

# Zones whose atoms are "transverse" — they live cross-project and require
# either a project/domain attachment OR an incoming wikilink to count as
# legitimately referenced.
_TRANSVERSE_ZONES: tuple[str, ...] = (
    "40-principles", "20-knowledge", "50-goals", "60-people",
)

# ---- Helpers ----


def _parse_fm(text: str) -> tuple[dict[str, Any], str, str | None]:
    """Return (fm_dict, body, parse_error). parse_error is the exception string
    if YAML parsing failed, else None. fm_dict is empty {} if no frontmatter
    is present (not an error)."""
    if not text.startswith("---"):
        return {}, text, None
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text, "frontmatter delimiter `---` opened but never closed"
    fm_block = text[4:end]
    body = text[end + 4:].lstrip("\n")
    try:
        fm = yaml.safe_load(fm_block) or {}
        if not isinstance(fm, dict):
            return {}, body, f"frontmatter is not a mapping (got {type(fm).__name__})"
        return fm, body, None
    except yaml.YAMLError as e:
        return {}, body, str(e).replace("\n", " ").strip()


def needs_display(rel_path: str) -> bool:
    """Return True if the universal frontmatter convention requires `display:`
    on this file. Mirrors the heuristic in scripts/mem-health-scan.py."""
    name = Path(rel_path).name
    parts = Path(rel_path).parts
    if name in ("context.md", "history.md"):
        return True
    if "archives" in parts and name.endswith(".md"):
        return True
    if parts and parts[0] in _TRANSVERSE_ZONES:
        return True
    if len(parts) >= 2 and parts[:2] == ("99-meta", "repo-topology"):
        return True
    if rel_path == "index.md":
        return True
    if name == "index.md" and len(parts) == 2 and parts[0] in ZONES:
        return True
    return False


def _finding(category: str, severity: str, path: str, message: str, auto_fixable: bool = False) -> HealthFinding:
    return HealthFinding(
        category=category,
        severity=severity,
        path=path,
        message=message,
        auto_fixable=auto_fixable,
    )


# ---- Main entry ----


def scan_vault(
    vault: Path,
    zones_filter: set[str] | None = None,
    only_filter: str | None = None,
    kit_repo: Path | None = None,
) -> tuple[list[HealthFinding], list[tuple[str, str]], int]:
    """Run all 9 category checks against `vault`.

    Args:
        vault: absolute path to the vault root.
        zones_filter: if non-empty, restrict scan to these zones (e.g.
            {"20-knowledge", "40-principles"}).
        only_filter: if set, restrict to this single category.
        kit_repo: optional path to the SecondBrain source repo. Required for
            the ``mcp-tool-spec-drift`` category (otherwise silently skipped).

    Returns:
        (findings, scan_errors, files_scanned)
        - findings: HealthFinding list grouped by category (insertion order
          matches CATEGORIES order).
        - scan_errors: list of (path, error_msg) for files that couldn't be
          read (encoding issues, permission denied, etc.).
        - files_scanned: total count of .md files visited (excluding
          .obsidian and .trash).
    """
    zones_filter = zones_filter or set()

    def cat_active(cat: str) -> bool:
        if only_filter and cat != only_filter:
            return False
        return True

    findings_by_cat: dict[str, list[HealthFinding]] = defaultdict(list)
    errors: list[tuple[str, str]] = []

    # ---- 1. stray-zone-md / empty-md-at-root ----------------------------
    if cat_active("stray-zone-md") or cat_active("empty-md-at-root"):
        zone_md_names = {f"{z}.md" for z in ZONES}
        for p in vault.glob("*.md"):
            if p.name == "index.md":
                continue
            try:
                content = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                errors.append((str(p), str(e)))
                continue
            if content.strip():
                continue
            if p.name in zone_md_names and cat_active("stray-zone-md"):
                zone = p.name[:-3]
                findings_by_cat["stray-zone-md"].append(_finding(
                    "stray-zone-md", "warning", p.name,
                    f"Empty MD at vault root, named after zone `{zone}`. "
                    "Likely created by Obsidian when clicking a dangling wikilink.",
                    auto_fixable=True,
                ))
            elif cat_active("empty-md-at-root"):
                findings_by_cat["empty-md-at-root"].append(_finding(
                    "empty-md-at-root", "warning", p.name,
                    "Empty MD at vault root.",
                    auto_fixable=True,
                ))

    # ---- 2. missing-zone-index ------------------------------------------
    if cat_active("missing-zone-index"):
        for zone in ZONES:
            if zones_filter and zone not in zones_filter:
                continue
            zd = vault / zone
            if not zd.exists():
                continue
            if not (zd / "index.md").exists():
                findings_by_cat["missing-zone-index"].append(_finding(
                    "missing-zone-index", "warning", f"{zone}/",
                    f"Zone hub `{zone}/index.md` is missing.",
                    auto_fixable=True,
                ))

    # ---- Build vault file index for wikilink resolution ----------------
    all_md = [
        p for p in vault.rglob("*.md")
        if ".obsidian" not in p.parts and ".trash" not in p.parts
    ]
    if zones_filter:
        all_md = [
            p for p in all_md
            if not p.relative_to(vault).parts
            or p.relative_to(vault).parts[0] in zones_filter
            or p.parent == vault
        ]
    files_scanned = len(all_md)

    basename_to_paths: dict[str, list[Path]] = defaultdict(list)
    relpath_set: set[str] = set()
    for p in all_md:
        basename_to_paths[p.stem].append(p)
        rel = p.relative_to(vault).as_posix()
        relpath_set.add(rel[:-3] if rel.endswith(".md") else rel)

    file_fm: dict[Path, tuple[dict[str, Any], str]] = {}
    incoming_links: dict[str, set[Path]] = defaultdict(set)
    malformed_paths: set[Path] = set()

    for p in all_md:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            errors.append((str(p), str(e)))
            continue
        fm, body, parse_err = _parse_fm(text)

        if parse_err and cat_active("malformed-frontmatter"):
            rel = p.relative_to(vault).as_posix()
            findings_by_cat["malformed-frontmatter"].append(_finding(
                "malformed-frontmatter", "error", rel,
                f"YAML frontmatter fails to parse: {parse_err}",
                auto_fixable=False,
            ))
            malformed_paths.add(p)
            file_fm[p] = ({}, body)
        else:
            file_fm[p] = (fm, body)

        # Outgoing wikilinks → reverse index for dangling + orphan checks
        plain_body = strip_code(body)
        for m in WIKILINK_RE.finditer(plain_body):
            target = m.group(1).strip()
            basename = target.split("/")[-1]
            stem = basename[:-3] if basename.endswith(".md") else basename
            incoming_links[stem].add(p)

    # ---- 3. missing-display ---------------------------------------------
    if cat_active("missing-display"):
        for p, (fm, _body) in file_fm.items():
            if p in malformed_paths:
                continue
            rel = p.relative_to(vault).as_posix()
            if not needs_display(rel):
                continue
            if not fm.get("display"):
                findings_by_cat["missing-display"].append(_finding(
                    "missing-display", "info", rel,
                    "Frontmatter missing `display:` (per universal conventions).",
                    auto_fixable=True,
                ))

    # ---- 4. dangling-wikilinks ------------------------------------------
    if cat_active("dangling-wikilinks"):
        SKIP_TARGETS = {"index"}
        seen: set[tuple[str, str]] = set()
        for p, (_fm, body) in file_fm.items():
            rel = p.relative_to(vault).as_posix()
            plain_body = strip_code(body)
            for m in WIKILINK_RE.finditer(plain_body):
                target = m.group(1).strip()
                basename = target.split("/")[-1]
                stem = basename[:-3] if basename.endswith(".md") else basename
                if stem in SKIP_TARGETS:
                    continue
                if stem in basename_to_paths:
                    continue
                target_no_ext = target[:-3] if target.endswith(".md") else target
                if target_no_ext in relpath_set:
                    continue
                key = (rel, target)
                if key in seen:
                    continue
                seen.add(key)
                findings_by_cat["dangling-wikilinks"].append(_finding(
                    "dangling-wikilinks", "info", rel,
                    f"Wikilink `[[{target}]]` does not resolve to any vault file.",
                    auto_fixable=False,
                ))

    # ---- 5. orphan-atoms ------------------------------------------------
    if cat_active("orphan-atoms"):
        projects_dir = vault / "10-episodes" / "projects"
        domains_dir = vault / "10-episodes" / "domains"
        existing_projects = (
            {d.name for d in projects_dir.iterdir() if d.is_dir()}
            if projects_dir.exists() else set()
        )
        existing_domains = (
            {d.name for d in domains_dir.iterdir() if d.is_dir()}
            if domains_dir.exists() else set()
        )
        for p, (fm, _body) in file_fm.items():
            if p in malformed_paths:
                continue
            rel = p.relative_to(vault).as_posix()
            parts = Path(rel).parts
            if not parts or parts[0] not in _TRANSVERSE_ZONES:
                continue
            project = fm.get("project")
            domain = fm.get("domain")
            if project:
                if project not in existing_projects:
                    findings_by_cat["orphan-atoms"].append(_finding(
                        "orphan-atoms", "warning", rel,
                        f"Orphan because target project '{project}' no longer exists.",
                        auto_fixable=False,
                    ))
                continue
            if domain:
                if domain not in existing_domains:
                    findings_by_cat["orphan-atoms"].append(_finding(
                        "orphan-atoms", "warning", rel,
                        f"Orphan because target domain '{domain}' no longer exists.",
                        auto_fixable=False,
                    ))
                continue
            incoming = incoming_links.get(p.stem, set()) - {p}
            if not incoming:
                # Also check for project/* or domain/* tags as backup attachment signal
                tags = fm.get("tags") or []
                has_tag_link = False
                if isinstance(tags, list):
                    for tag in tags:
                        if isinstance(tag, str) and (
                            tag.startswith("project/") or tag.startswith("domain/")
                        ):
                            has_tag_link = True
                            break
                if not has_tag_link:
                    findings_by_cat["orphan-atoms"].append(_finding(
                        "orphan-atoms", "warning", rel,
                        "No project/domain attachment + zero incoming wikilinks.",
                        auto_fixable=False,
                    ))

    # ---- 6. missing-archeo-hashes ---------------------------------------
    if cat_active("missing-archeo-hashes"):
        for p, (fm, _body) in file_fm.items():
            if p in malformed_paths:
                continue
            src = fm.get("source")
            if not isinstance(src, str) or not src.startswith("archeo-"):
                continue
            rel = p.relative_to(vault).as_posix()
            if not fm.get("content_hash"):
                findings_by_cat["missing-archeo-hashes"].append(_finding(
                    "missing-archeo-hashes", "warning", rel,
                    f"Missing `content_hash` for source: {src}",
                    auto_fixable=False,
                ))
            parts = Path(rel).parts
            if len(parts) >= 2 and parts[:2] == ("99-meta", "repo-topology"):
                if "previous_topology_hash" not in fm:
                    findings_by_cat["missing-archeo-hashes"].append(_finding(
                        "missing-archeo-hashes", "warning", rel,
                        "Missing `previous_topology_hash` key on a repo-topology atom.",
                        auto_fixable=False,
                    ))

    # ---- 7. mcp-tool-spec-drift -----------------------------------------
    # Audits the kit repo (not the vault). Silently skipped when kit_repo is
    # not configured or sync.json is absent — both are expected in deployments
    # where the user installed the wheel without the source tree.
    if cat_active("mcp-tool-spec-drift") and kit_repo is not None:
        try:
            from memory_kit_mcp.sync import (
                MANIFEST_PATH,
                compute_procedure_hash,
                load_manifest,
                procedures_dir,
            )

            manifest = load_manifest(MANIFEST_PATH)
            proc_dir = procedures_dir(kit_repo)
            if manifest and proc_dir.is_dir():
                for tool_name, entry in manifest.items():
                    proc_path = proc_dir / entry.procedure
                    if not proc_path.is_file():
                        findings_by_cat["mcp-tool-spec-drift"].append(_finding(
                            "mcp-tool-spec-drift", "info",
                            f"core/procedures/{entry.procedure}",
                            f"Procedure file missing for tool `{tool_name}`.",
                            auto_fixable=False,
                        ))
                        continue
                    current_hash = compute_procedure_hash(proc_path)
                    if current_hash != entry.last_synced_hash:
                        findings_by_cat["mcp-tool-spec-drift"].append(_finding(
                            "mcp-tool-spec-drift", "info",
                            f"core/procedures/{entry.procedure}",
                            f"Procedure has drifted since last sync — review the "
                            f"`{tool_name}` implementation in tools/ and run "
                            "`python -m memory_kit_mcp.sync update` after reconciling.",
                            auto_fixable=False,
                        ))
        except (FileNotFoundError, OSError, ValueError):
            # Manifest missing or unreadable — silent skip per design.
            pass

    # ---- 8. skill-description-too-long ---------------------------------
    # Audits the kit repo's adapter SKILL.md templates against the 1024-char
    # description limit (Anthropic format). Mcp-only by design — same
    # rationale as #7 above: silent skip if kit_repo / adapters/ absent.
    if cat_active("skill-description-too-long") and kit_repo is not None:
        adapters_dir = kit_repo / "adapters"
        if adapters_dir.is_dir():
            for adapter_name, glob_pattern in _SKILL_TEMPLATE_GLOBS:
                adapter_root = adapters_dir / adapter_name
                if not adapter_root.is_dir():
                    continue
                for tpl in adapter_root.glob(glob_pattern):
                    try:
                        text = tpl.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError) as e:
                        errors.append((str(tpl), str(e)))
                        continue
                    fm, _body, parse_err = _parse_fm(text)
                    if parse_err or not isinstance(fm, dict):
                        # Frontmatter unreadable — let other checks (or the
                        # build) catch it. Don't double-report here.
                        continue
                    description = fm.get("description")
                    if not isinstance(description, str):
                        continue
                    if len(description) > SKILL_DESCRIPTION_MAX:
                        rel = tpl.relative_to(kit_repo).as_posix()
                        findings_by_cat["skill-description-too-long"].append(_finding(
                            "skill-description-too-long", "warning", rel,
                            f"Frontmatter `description` is {len(description)} chars "
                            f"(> {SKILL_DESCRIPTION_MAX}-char Anthropic limit). "
                            f"The skill auto-trigger will break on Claude Code / Codex / "
                            f"Vibe / Copilot. Trim the description before deploying.",
                            auto_fixable=False,
                        ))

    # ---- 9. missing-zone-index-entry ------------------------------------
    # v0.9.4 architecture: each transverse zone (20-knowledge, 40-principles,
    # 50-goals, 60-people) has its own index.md that lists every atom of the
    # zone, grouped by attached project. An atom is "missing from index" if
    # the zone index file does not reference its relative path. Auto-fixable
    # by regenerating the zone index.
    if cat_active("missing-zone-index-entry"):
        from memory_kit_mcp.vault.zone_index import ATOM_ZONES, scan_zone_atoms

        for zone in ATOM_ZONES:
            zone_dir = vault / zone
            if not zone_dir.is_dir():
                continue
            zone_index_path = zone_dir / "index.md"
            if not zone_index_path.is_file():
                # The whole zone index is missing — already reported by the
                # missing-zone-index category above. Don't double-report.
                continue
            try:
                zone_index_text = zone_index_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                errors.append((str(zone_index_path), str(e)))
                continue
            atoms = scan_zone_atoms(vault, zone)
            for atom_path, _atom_fm in atoms:
                rel = atom_path.relative_to(vault).as_posix()
                # Index references the atom either by relpath or by stem in a
                # markdown link `[stem](relpath)`.
                if rel not in zone_index_text and atom_path.stem not in zone_index_text:
                    findings_by_cat["missing-zone-index-entry"].append(_finding(
                        "missing-zone-index-entry", "warning", rel,
                        f"Atom not listed in `{zone}/index.md`. "
                        f"Run `mem_health_repair --apply` to regenerate the zone index.",
                        auto_fixable=True,
                    ))

    # ---- 10. missing-universal-frontmatter ------------------------------
    # An atom outside 00-inbox/ and 99-meta/ MUST carry scope, collective and
    # modality (per _frontmatter-universal.md). LLM-driven runs by adapters
    # less rigorous than the reference client silently drop these because
    # YAML parses fine without them. Detect the drift here.
    if cat_active("missing-universal-frontmatter"):
        for p, (fm, _body) in file_fm.items():
            if p in malformed_paths:
                continue
            rel = p.relative_to(vault).as_posix()
            parts = Path(rel).parts
            if not parts:
                continue
            zone_dir = parts[0]
            if zone_dir in ("00-inbox", "99-meta"):
                continue
            if fm.get("zone") == "meta":
                continue
            if p.name in ("context.md", "history.md"):
                continue
            if fm.get("type") == "zone-index":
                continue
            missing = [k for k in UNIVERSAL_MUST if k not in fm]
            if missing:
                findings_by_cat["missing-universal-frontmatter"].append(_finding(
                    "missing-universal-frontmatter", "warning", rel,
                    f"Missing universal MUST field(s): {', '.join(missing)}. "
                    f"See _frontmatter-universal.md.",
                    auto_fixable=False,
                ))

    # ---- 11. missing-archeo-context-origin ------------------------------
    # archeo-context and archeo-stack atoms MUST point to the topology.
    # archeo-git derived atoms (outside archives/) MUST point to a milestone
    # archive. archeo-git archives themselves are exempt.
    if cat_active("missing-archeo-context-origin"):
        for p, (fm, _body) in file_fm.items():
            if p in malformed_paths:
                continue
            src = fm.get("source")
            if not isinstance(src, str) or src not in ARCHEO_SOURCES:
                continue
            rel = p.relative_to(vault).as_posix()
            parts = Path(rel).parts
            if (src == "archeo-git"
                    and len(parts) >= 4
                    and parts[0] == "10-episodes"
                    and parts[3] == "archives"):
                continue
            origin = fm.get("context_origin")
            if not origin or not isinstance(origin, str):
                findings_by_cat["missing-archeo-context-origin"].append(_finding(
                    "missing-archeo-context-origin", "warning", rel,
                    f"Missing `context_origin` for source: {src}. "
                    f"See _frontmatter-archeo.md.",
                    auto_fixable=False,
                ))
                continue
            slug = fm.get("project") or fm.get("domain")
            if src in ("archeo-context", "archeo-stack"):
                expected = f"[[99-meta/repo-topology/{slug}]]"
                if origin != expected:
                    findings_by_cat["missing-archeo-context-origin"].append(_finding(
                        "missing-archeo-context-origin", "warning", rel,
                        f"`context_origin` is {origin!r}, expected {expected!r}.",
                        auto_fixable=False,
                    ))
            elif src == "archeo-git":
                if not (origin.startswith("[[") and origin.endswith("]]")):
                    findings_by_cat["missing-archeo-context-origin"].append(_finding(
                        "missing-archeo-context-origin", "warning", rel,
                        f"`context_origin` is not a wikilink: {origin!r}.",
                        auto_fixable=False,
                    ))

    # ---- 12. archeo-derived-orphan --------------------------------------
    # archeo-git atoms living outside archives/ MUST be referenced in the
    # `derived_atoms:` list of a milestone archive. Otherwise the bidirectional
    # link is broken (cf. mem-archeo-git.md §6).
    if cat_active("archeo-derived-orphan"):
        derived_set: set[str] = set()
        for p, (fm, _body) in file_fm.items():
            if p in malformed_paths:
                continue
            rel_str = p.relative_to(vault).as_posix()
            parts = Path(rel_str).parts
            if not (len(parts) >= 4
                    and parts[0] == "10-episodes"
                    and parts[3] == "archives"
                    and fm.get("source") == "archeo-git"):
                continue
            derived = fm.get("derived_atoms", [])
            if not isinstance(derived, list):
                continue
            for entry in derived:
                if not isinstance(entry, str):
                    continue
                m = WIKILINK_RE.match(entry)
                target = m.group(1).strip() if m else entry.strip("[] ")
                derived_set.add(target.split("/")[-1])

        for p, (fm, _body) in file_fm.items():
            if p in malformed_paths:
                continue
            if fm.get("source") != "archeo-git":
                continue
            rel = p.relative_to(vault).as_posix()
            parts = Path(rel).parts
            if (len(parts) >= 4
                    and parts[0] == "10-episodes"
                    and parts[3] == "archives"):
                continue
            if p.stem not in derived_set:
                findings_by_cat["archeo-derived-orphan"].append(_finding(
                    "archeo-derived-orphan", "warning", rel,
                    "Atom has source: archeo-git but is not listed in "
                    "`derived_atoms` of any milestone archive. Bidirectional "
                    "link is broken — see mem-archeo-git.md §6.",
                    auto_fixable=False,
                ))

    # ---- 13. topology-archives-out-of-sync ------------------------------
    # For each persisted topology, ensure that all archives present in
    # 10-episodes/projects/{slug}/archives/ are referenced in the body
    # (typically under '## Atomes dérivés des phases archeo').
    if cat_active("topology-archives-out-of-sync"):
        topo_dir = vault / "99-meta" / "repo-topology"
        if topo_dir.is_dir():
            for topo_file in topo_dir.glob("*.md"):
                if topo_file.is_dir():
                    continue
                if topo_file in malformed_paths:
                    continue
                fm, body = file_fm.get(topo_file, ({}, ""))
                if fm.get("type") != "repo-topology":
                    continue
                slug = fm.get("project")
                if not slug:
                    continue
                arch_dir = (vault / "10-episodes" / "projects" / slug
                            / "archives")
                if not arch_dir.is_dir():
                    continue
                archives = sorted(
                    p.stem for p in arch_dir.glob("*.md") if p.is_file()
                )
                if not archives:
                    continue
                body_targets: set[str] = set()
                for m in WIKILINK_RE.finditer(strip_code(body)):
                    target = m.group(1).strip()
                    body_targets.add(target.split("/")[-1])
                missing_arch = [a for a in archives if a not in body_targets]
                if missing_arch:
                    rel = topo_file.relative_to(vault).as_posix()
                    findings_by_cat["topology-archives-out-of-sync"].append(_finding(
                        "topology-archives-out-of-sync", "info", rel,
                        f"{len(missing_arch)} archive(s) not referenced in "
                        f"topology body: {missing_arch[0]}"
                        + (f" + {len(missing_arch)-1} more"
                           if len(missing_arch) > 1 else ""),
                        auto_fixable=False,
                    ))

    # ---- Flatten in canonical category order ----------------------------
    findings: list[HealthFinding] = []
    for cat in CATEGORIES:
        findings.extend(findings_by_cat.get(cat, []))

    return findings, errors, files_scanned
