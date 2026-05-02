#!/usr/bin/env python3
"""
mem-health-scan.py — audit the SecondBrain vault for hygiene defects.

Read-only. Detects 8 categories of issues:

  - malformed-frontmatter  (error)  YAML frontmatter that fails to parse —
                                    typically unquoted [TAG] flow-sequences
                                    or stray colons. Detected first so it
                                    does NOT cascade into other categories
                                    as false positives.
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

Persists a structured report at {vault}/99-meta/health/scan-{ts}.md unless
--no-write is passed. Prints a parseable summary on stdout.

Idempotent. Read-only on the vault content (the report is the only write).
Exit code 1 if any `error`-severity finding is detected, else 0 — useful
for CI gating.

Usage:
    python scripts/mem-health-scan.py --vault /path/to/vault
    python scripts/mem-health-scan.py --vault /path/to/vault --only orphan-atoms
    python scripts/mem-health-scan.py --vault /path/to/vault --zones 40-principles,20-knowledge
    python scripts/mem-health-scan.py --vault /path/to/vault --quiet --no-write
    python scripts/mem-health-scan.py --vault /path/to/vault --json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import yaml
except ImportError:
    print("Error: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


ZONES = [
    "00-inbox", "10-episodes", "20-knowledge", "30-procedures",
    "40-principles", "50-goals", "60-people", "70-cognition", "99-meta",
]

CATEGORIES = [
    "malformed-frontmatter",
    "stray-zone-md",
    "empty-md-at-root",
    "missing-zone-index",
    "missing-display",
    "dangling-wikilinks",
    "orphan-atoms",
    "missing-archeo-hashes",
]

WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]\|#]+)(?:\|[^\]]*)?\]\]")


def strip_code(body: str) -> str:
    """Remove fenced code blocks (``` ... ```) and inline code spans
    (`...`) from a markdown body. Wikilinks inside code are not real
    references — they're literal string examples — and counting them
    leads to self-pollution (e.g. health reports tabulating dangling
    wikilinks would themselves trigger dangling-wikilink findings).

    Multi-backtick spans (``...``) are also stripped to be safe.
    Order matters: strip fences first, then inline spans.
    """
    # Fenced code blocks
    out_lines = []
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out_lines.append(line)
    no_fences = "\n".join(out_lines)
    # Inline code spans: handle 1-N backtick runs.
    # `..`, ``..``, ```..``` (within a line). Lazy match the same length.
    no_inline = re.sub(r"(`+)([^`]|(?!\1).)*?\1", " ", no_fences)
    return no_inline


def parse_fm(text):
    """Return (fm_dict, body, parse_error). parse_error is the exception
    string if YAML parsing failed, else None. fm_dict is empty {} if no
    frontmatter is present (not an error)."""
    if not text.startswith("---"):
        return {}, text, None
    end = text.find("\n---", 4)
    if end == -1:
        # Frontmatter delimiter open but never closed — malformed.
        return {}, text, "frontmatter delimiter `---` opened but never closed"
    fm_block = text[4:end]
    body = text[end + 4:].lstrip("\n")
    try:
        fm = yaml.safe_load(fm_block) or {}
        if not isinstance(fm, dict):
            return {}, body, f"frontmatter is not a mapping (got {type(fm).__name__})"
        return fm, body, None
    except yaml.YAMLError as e:
        # Compact the error message
        msg = str(e).replace("\n", " ").strip()
        return {}, body, msg


def needs_display(rel_path: str) -> bool:
    name = Path(rel_path).name
    parts = Path(rel_path).parts
    if name in ("context.md", "history.md"):
        return True
    if "archives" in parts and name.endswith(".md"):
        return True
    if parts and parts[0] in ("40-principles", "20-knowledge", "50-goals", "60-people"):
        return True
    if len(parts) >= 2 and parts[:2] == ("99-meta", "repo-topology"):
        return True
    if rel_path == "index.md":
        return True
    if name == "index.md" and len(parts) == 2 and parts[0] in ZONES:
        return True
    return False


def collect_findings(vault: Path, zones_filter, only_filter):
    """Run all checks. Returns (findings: dict[category, list], errors: list)."""
    findings = defaultdict(list)
    errors = []

    def cat_active(cat):
        if only_filter and cat != only_filter:
            return False
        return True

    # ---- 2.1 stray-zone-md & 2.2 empty-md-at-root --------------------------
    if cat_active("stray-zone-md") or cat_active("empty-md-at-root"):
        zone_md_names = {f"{z}.md" for z in ZONES}
        for p in vault.glob("*.md"):
            if p.name == "index.md":
                continue
            try:
                content = p.read_text(encoding="utf-8")
            except Exception as e:
                errors.append((str(p), str(e)))
                continue
            if content.strip():
                continue
            if p.name in zone_md_names and cat_active("stray-zone-md"):
                zone = p.name[:-3]
                findings["stray-zone-md"].append((
                    "warn", p.name,
                    f"empty MD at root, named after zone `{zone}`",
                    "delete-stray-zone-md",
                ))
            elif cat_active("empty-md-at-root"):
                findings["empty-md-at-root"].append((
                    "warn", p.name, "empty MD at vault root",
                    "delete-empty-root-md",
                ))

    # ---- 2.3 missing-zone-index --------------------------------------------
    if cat_active("missing-zone-index"):
        for zone in ZONES:
            if zones_filter and zone not in zones_filter:
                continue
            zd = vault / zone
            if not zd.exists():
                continue
            if not (zd / "index.md").exists():
                findings["missing-zone-index"].append((
                    "warn", f"{zone}/",
                    f"zone hub `{zone}/index.md` is missing",
                    "recreate-zone-index",
                ))

    # ---- Build vault file index for wikilink resolution & content scan -----
    all_md = [
        p for p in vault.rglob("*.md")
        if ".obsidian" not in p.parts and ".trash" not in p.parts
    ]
    if zones_filter:
        all_md = [p for p in all_md
                  if not p.relative_to(vault).parts
                  or p.relative_to(vault).parts[0] in zones_filter
                  or p.parent == vault]

    basename_to_paths = defaultdict(list)
    relpath_set = set()
    for p in all_md:
        basename_to_paths[p.stem].append(p)
        rel = p.relative_to(vault).as_posix()
        relpath_set.add(rel[:-3] if rel.endswith(".md") else rel)

    file_fm = {}      # path -> (fm_dict, body)
    incoming_links = defaultdict(set)  # target_basename -> set(source_paths)
    malformed_paths = set()

    for p in all_md:
        try:
            text = p.read_text(encoding="utf-8")
        except Exception as e:
            errors.append((str(p), str(e)))
            continue
        fm, body, parse_err = parse_fm(text)

        if parse_err and cat_active("malformed-frontmatter"):
            rel = p.relative_to(vault).as_posix()
            findings["malformed-frontmatter"].append((
                "error", rel, f"YAML frontmatter fails to parse: {parse_err}",
                "fix-frontmatter-quoting",
            ))
            malformed_paths.add(p)
            # Still capture body for wikilink scan, but skip dependent checks.
            file_fm[p] = ({}, body)
        else:
            file_fm[p] = (fm, body)

        # Collect outgoing wikilinks (skip fenced AND inline code blocks)
        plain_body = strip_code(body)
        for m in WIKILINK_RE.finditer(plain_body):
            target = m.group(1).strip()
            basename = target.split("/")[-1]
            incoming_links[basename].add(p)

    # ---- 2.4 missing-display -----------------------------------------------
    if cat_active("missing-display"):
        for p, (fm, _body) in file_fm.items():
            if p in malformed_paths:
                continue  # don't stack on top of a malformed frontmatter
            rel = p.relative_to(vault).as_posix()
            if not needs_display(rel):
                continue
            if not fm.get("display"):
                findings["missing-display"].append((
                    "info", rel,
                    "frontmatter missing `display:` (per universal conventions)",
                    "inject-display",
                ))

    # ---- 2.5 dangling-wikilinks --------------------------------------------
    if cat_active("dangling-wikilinks"):
        SKIP_TARGETS = {"index"}
        seen = set()
        for p, (_fm, body) in file_fm.items():
            rel = p.relative_to(vault).as_posix()
            plain_body = strip_code(body)
            for m in WIKILINK_RE.finditer(plain_body):
                target = m.group(1).strip()
                basename = target.split("/")[-1]
                # Strip optional .md from the basename (Obsidian accepts both
                # [[foo]] and [[foo.md]] for the same target).
                basename_stem = basename[:-3] if basename.endswith(".md") else basename
                if basename_stem in SKIP_TARGETS:
                    continue
                if basename_stem in basename_to_paths:
                    continue
                target_no_ext = target[:-3] if target.endswith(".md") else target
                if target_no_ext in relpath_set:
                    continue
                key = (rel, target)
                if key in seen:
                    continue
                seen.add(key)
                findings["dangling-wikilinks"].append((
                    "info", rel, f"wikilink `[[{target}]]` does not resolve",
                    "manual-review",
                ))

    # ---- 2.6 orphan-atoms --------------------------------------------------
    if cat_active("orphan-atoms"):
        TRANSVERSE_ZONES = ("40-principles", "20-knowledge", "50-goals", "60-people")
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
            if not parts or parts[0] not in TRANSVERSE_ZONES:
                continue
            project = fm.get("project")
            domain = fm.get("domain")
            if project:
                if project not in existing_projects:
                    findings["orphan-atoms"].append((
                        "warn", rel,
                        f"orphan because target project '{project}' no longer exists",
                        "reclassify-to-inbox",
                    ))
                continue
            if domain:
                if domain not in existing_domains:
                    findings["orphan-atoms"].append((
                        "warn", rel,
                        f"orphan because target domain '{domain}' no longer exists",
                        "reclassify-to-inbox",
                    ))
                continue
            incoming = incoming_links.get(p.stem, set()) - {p}
            if not incoming:
                findings["orphan-atoms"].append((
                    "warn", rel,
                    "no project/domain attachment + zero incoming wikilinks",
                    "reclassify-to-inbox",
                ))

    # ---- 2.7 missing-archeo-hashes -----------------------------------------
    if cat_active("missing-archeo-hashes"):
        for p, (fm, _body) in file_fm.items():
            if p in malformed_paths:
                continue
            src = fm.get("source")
            if not isinstance(src, str) or not src.startswith("archeo-"):
                continue
            rel = p.relative_to(vault).as_posix()
            if not fm.get("content_hash"):
                findings["missing-archeo-hashes"].append((
                    "warn", rel, f"missing `content_hash` for source: {src}",
                    "inject-archeo-hashes",
                ))
            parts = Path(rel).parts
            if len(parts) >= 2 and parts[:2] == ("99-meta", "repo-topology"):
                if "previous_topology_hash" not in fm:
                    findings["missing-archeo-hashes"].append((
                        "warn", rel, "missing `previous_topology_hash` key",
                        "inject-archeo-hashes",
                    ))

    return findings, errors


def render_report(vault: Path, findings, errors, ts: str, scope_note: str) -> str:
    sev_counts = {"info": 0, "warn": 0, "error": 0}
    cat_counts = {c: len(findings[c]) for c in CATEGORIES}
    for c in CATEGORIES:
        for f in findings[c]:
            sev_counts[f[0]] += 1
    total = sum(cat_counts.values())
    today = datetime.now().date().isoformat()

    lines = [
        "---",
        f"date: {today}",
        "zone: meta",
        "type: health-scan",
        f'display: "vault health scan {ts}"',
        "tags: [zone/meta, type/health-scan]",
        f'scan_timestamp: "{ts}"',
        f'vault_path: "{vault.as_posix()}"',
        f"findings_count_total: {total}",
        "findings_by_severity:",
        f'  info: {sev_counts["info"]}',
        f'  warn: {sev_counts["warn"]}',
        f'  error: {sev_counts["error"]}',
        "findings_by_category:",
    ]
    for c in CATEGORIES:
        lines.append(f"  {c}: {cat_counts[c]}")
    lines += [
        "---",
        "",
        f"# Vault health scan — {ts}",
        "",
        "> Read-only audit. Run `/mem-health-repair` to apply the suggested fixes.",
        "> Linked from [[index|vault index]].",
        "",
        "## Summary",
        "",
        f'- **Total findings**: {total} ({sev_counts["error"]} errors, {sev_counts["warn"]} warnings, {sev_counts["info"]} info)',
        f"- **Vault**: `{vault}`",
        f"- **Scan timestamp**: {ts}",
        f"- **Scope**: {scope_note}",
        "",
    ]
    for c in CATEGORIES:
        if not findings[c]:
            continue
        lines.append(f"## {c} ({len(findings[c])} finding(s))")
        lines.append("")
        lines.append("| Severity | File | Message | Fix |")
        lines.append("|---|---|---|---|")
        for sev, fpath, msg, fix in findings[c]:
            msg_e = msg.replace("|", "\\|")
            lines.append(f"| {sev} | `{fpath}` | {msg_e} | {fix} |")
        lines.append("")
    if errors:
        lines.append("## Scan errors")
        lines.append("")
        for path, err in errors:
            lines.append(f"- `{path}` — {err}")
        lines.append("")
    return "\n".join(lines)


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vault", required=True, help="Absolute path of the vault")
    ap.add_argument("--zones", default="",
                    help="Comma-separated list of zones to restrict the scan to")
    ap.add_argument("--only", default="",
                    help=f"Restrict to a single category. One of: {', '.join(CATEGORIES)}")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress the per-finding output, keep only the summary")
    ap.add_argument("--no-write", action="store_true",
                    help="Do not persist the report file under 99-meta/health/")
    ap.add_argument("--json", action="store_true",
                    help="Print a JSON summary on stdout instead of plain text")
    args = ap.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"Error: vault not found: {vault}", file=sys.stderr)
        return 2

    zones_filter = set(z.strip() for z in args.zones.split(",") if z.strip())
    if zones_filter:
        invalid = zones_filter - set(ZONES)
        if invalid:
            print(f"Error: unknown zones: {sorted(invalid)}", file=sys.stderr)
            return 2

    only_filter = args.only.strip()
    if only_filter and only_filter not in CATEGORIES:
        print(f"Error: unknown category: {only_filter}", file=sys.stderr)
        return 2

    scope_parts = []
    if zones_filter:
        scope_parts.append(f"zones={sorted(zones_filter)}")
    if only_filter:
        scope_parts.append(f"only={only_filter}")
    scope_note = ", ".join(scope_parts) if scope_parts else "all zones, all categories"

    findings, errors = collect_findings(vault, zones_filter, only_filter)

    sev_counts = {"info": 0, "warn": 0, "error": 0}
    cat_counts = {c: len(findings[c]) for c in CATEGORIES}
    for c in CATEGORIES:
        for f in findings[c]:
            sev_counts[f[0]] += 1
    total = sum(cat_counts.values())

    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    report_path = vault / "99-meta" / "health" / f"scan-{ts}.md"

    if not args.no_write:
        report_content = render_report(vault, findings, errors, ts, scope_note)
        write_atomic(report_path, report_content)

    if args.json:
        out = {
            "vault": vault.as_posix(),
            "scan_timestamp": ts,
            "scope": scope_note,
            "report_path": (report_path.as_posix() if not args.no_write else None),
            "findings_count_total": total,
            "findings_by_severity": sev_counts,
            "findings_by_category": cat_counts,
            "scan_errors": [{"path": p, "error": e} for p, e in errors],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"[i] Vault     : {vault}")
        print(f"[i] Scope     : {scope_note}")
        print(f"[i] Timestamp : {ts}")
        if not args.no_write:
            print(f"[i] Report    : {report_path.as_posix()}")
        else:
            print("[i] Report    : (not persisted, --no-write)")
        print()
        print(f"[=] Total findings: {total}  "
              f"(error={sev_counts['error']}, warn={sev_counts['warn']}, info={sev_counts['info']})")
        for c in CATEGORIES:
            if cat_counts[c] == 0 and args.quiet:
                continue
            line = f"    {c:<24} {cat_counts[c]}"
            if not args.quiet and cat_counts[c]:
                # show first 3 examples
                samples = findings[c][:3]
                for sev, fpath, msg, _fix in samples:
                    line += f"\n        [{sev}] {fpath} — {msg}"
                if len(findings[c]) > 3:
                    line += f"\n        ... +{len(findings[c]) - 3} more"
            print(line)
        if errors:
            print()
            print(f"[!] {len(errors)} scan error(s) (see report)")

    # Exit code: 1 if any error-severity finding, else 0
    return 1 if sev_counts["error"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
