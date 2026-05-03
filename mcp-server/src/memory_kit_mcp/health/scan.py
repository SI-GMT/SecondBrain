"""Vault hygiene scan — 9-category audit (shared library).

Spec: core/procedures/mem-health-scan.md
Mirrors: scripts/mem-health-scan.py (versioned standalone CLI) for the first
8 categories. The 9th category (``mcp-tool-spec-drift``) is mcp-only by
design: it audits the *kit repo* (core/procedures vs ``sync.json``), not the
vault, so the standalone — which scans vaults from machines without the kit
installed — has no equivalent.

Read-only. Detects 9 categories of issues:

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

The function returns Pydantic HealthFinding objects (defined in
tools._models) so the MCP tool layer can serialize them directly.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from memory_kit_mcp.tools._models import HealthFinding

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
)

# Zones whose atoms are "transverse" — they live cross-project and require
# either a project/domain attachment OR an incoming wikilink to count as
# legitimately referenced.
_TRANSVERSE_ZONES: tuple[str, ...] = (
    "40-principles", "20-knowledge", "50-goals", "60-people",
)

_WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]\|#]+)(?:\|[^\]]*)?\]\]")


# ---- Helpers ----


def strip_code(body: str) -> str:
    """Remove fenced code blocks and inline code spans from a markdown body.

    Wikilinks inside code are not real references — they're literal string
    examples — and counting them leads to self-pollution (e.g. health
    reports tabulating dangling wikilinks would themselves trigger findings).
    """
    out_lines: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out_lines.append(line)
    no_fences = "\n".join(out_lines)
    no_inline = re.sub(r"(`+)([^`]|(?!\1).)*?\1", " ", no_fences)
    return no_inline


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
        for m in _WIKILINK_RE.finditer(plain_body):
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
            for m in _WIKILINK_RE.finditer(plain_body):
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

    # ---- Flatten in canonical category order ----------------------------
    findings: list[HealthFinding] = []
    for cat in CATEGORIES:
        findings.extend(findings_by_cat.get(cat, []))

    return findings, errors, files_scanned
