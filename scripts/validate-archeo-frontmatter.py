#!/usr/bin/env python3
"""
validate-archeo-frontmatter.py — lint the frontmatter of archeo-* atoms and
topology files against the v0.7.0 schema.

Checks:
  - No duplicate top-level YAML keys.
  - All MUST fields present (per source).
  - Enum values in canonical English (force, horizon, kind, scope, modality, zone).
  - Fields that should never be empty unless the schema allows.

Read-only. Exits 0 if no issues, 1 if any issue, 2 on script error.

Usage:
    python scripts/validate-archeo-frontmatter.py --vault /path/to/vault
"""

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)
KEY_VALUE_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:")

# Per-source MUST fields (in addition to universal date/zone/scope/tags etc.)
MUST_BY_SOURCE = {
    "archeo-context": ["source", "source_doc", "source_doc_hash", "extracted_category", "content_hash", "previous_atom", "project", "context_origin"],
    "archeo-stack":   ["source", "source_manifest", "detected_layer", "detected_techno", "content_hash", "previous_atom", "project", "context_origin"],
    "archeo-git":     ["source", "source_milestone", "commit_sha", "friction_detected", "content_hash", "previous_atom", "project"],
}

TOPOLOGY_MUST = ["date", "zone", "type", "project", "repo_path", "content_hash", "previous_topology_hash", "tags"]

ENUMS_EN = {
    "force":    ["red-line", "heuristic", "preference"],
    "horizon":  ["short", "medium", "long"],
    "kind":     ["project", "domain"],
    "scope":    ["personal", "work"],
    "modality": ["left", "right"],
    "zone":     ["inbox", "episodes", "knowledge", "procedures", "principles", "goals", "people", "cognition", "meta"],
    "extracted_category": ["workflow", "sync", "multi-tenant", "security", "adr", "goal", "other"],
    "detected_layer":     ["frontend", "backend", "db", "ci", "infra", "tests", "tooling", "other"],
}


def extract_frontmatter_block(text: str) -> str | None:
    m = FRONTMATTER_RE.match(text)
    return m.group(1) if m else None


def parse_keys(fm_text: str) -> tuple[list[str], dict[str, str]]:
    """
    Return (ordered_keys_list_with_duplicates, last_value_per_key).
    Keys list preserves duplicates so the caller can detect them.
    """
    keys: list[str] = []
    values: dict[str, str] = {}
    for line in fm_text.splitlines():
        if not line or line.startswith(" ") or line.startswith("\t") or line.startswith("-") or line.startswith("#"):
            continue
        m = KEY_VALUE_RE.match(line)
        if m:
            k = m.group(1)
            keys.append(k)
            after = line.split(":", 1)[1].strip()
            values[k] = after
    return keys, values


def is_empty_value(v: str) -> bool:
    s = v.strip().strip('"').strip("'")
    return s in ("", "null", "~")


def check_atom(path: Path, source: str, fm: str) -> list[str]:
    issues: list[str] = []
    keys, values = parse_keys(fm)

    # Duplicate keys
    seen: set[str] = set()
    dups: set[str] = set()
    for k in keys:
        if k in seen:
            dups.add(k)
        seen.add(k)
    for d in sorted(dups):
        issues.append(f"duplicate key: {d}")

    # MUST fields
    must = MUST_BY_SOURCE.get(source, [])
    for k in must:
        if k not in values:
            issues.append(f"missing MUST field: {k}")
        elif is_empty_value(values[k]) and k not in ("previous_atom",):
            # previous_atom can be empty on first write
            issues.append(f"empty MUST field: {k}")

    # Enum checks
    for k, allowed in ENUMS_EN.items():
        if k in values:
            v = values[k].strip().strip('"').strip("'").strip("[]")
            # detected_techno is sometimes a list; skip if value starts with '['
            if k == "detected_techno":
                continue
            if v and v not in allowed:
                issues.append(f"non-canonical enum {k}: '{v}' (expected one of {allowed})")

    return issues


def check_topology(path: Path, fm: str) -> list[str]:
    issues: list[str] = []
    keys, values = parse_keys(fm)

    seen: set[str] = set()
    dups: set[str] = set()
    for k in keys:
        if k in seen:
            dups.add(k)
        seen.add(k)
    for d in sorted(dups):
        issues.append(f"duplicate key: {d}")

    for k in TOPOLOGY_MUST:
        if k not in values:
            issues.append(f"missing MUST field: {k}")
        elif k not in ("previous_topology_hash",) and is_empty_value(values[k]):
            issues.append(f"empty MUST field: {k}")

    if "type" in values and values["type"].strip().strip('"').strip("'") != "repo-topology":
        issues.append(f"type should be 'repo-topology' (got '{values['type']}')")

    return issues


def find_targets(vault: Path) -> tuple[list[tuple[Path, str]], list[Path]]:
    """Return (atoms_with_source, topology_files)."""
    atoms: list[tuple[Path, str]] = []
    for md in vault.rglob("*.md"):
        if ".obsidian" in md.parts or "99-meta/sources" in str(md).replace("\\", "/"):
            continue
        try:
            head = md.read_text(encoding="utf-8")[:2000]
        except Exception:
            continue
        msrc = re.search(r"^source:\s*(archeo-(?:context|stack|git))", head, re.MULTILINE)
        if msrc:
            atoms.append((md, msrc.group(1)))

    topo_dir = vault / "99-meta" / "repo-topology"
    topos = sorted(topo_dir.glob("*.md")) if topo_dir.exists() else []
    return sorted(atoms), topos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    args = ap.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.exists():
        print(f"Error: vault not found: {vault}", file=sys.stderr)
        return 2

    atoms, topos = find_targets(vault)
    print(f"[i] Vault   : {vault}")
    print(f"[i] Targets : {len(atoms)} archeo atom(s), {len(topos)} topology file(s)")
    print()

    total_issues = 0
    files_with_issues = 0

    for path in topos:
        text = path.read_text(encoding="utf-8")
        fm = extract_frontmatter_block(text)
        if fm is None:
            print(f"[!] {path.relative_to(vault)} — no frontmatter")
            files_with_issues += 1
            total_issues += 1
            continue
        issues = check_topology(path, fm)
        if issues:
            files_with_issues += 1
            total_issues += len(issues)
            print(f"[!] {path.relative_to(vault)}")
            for i in issues:
                print(f"      - {i}")

    for path, source in atoms:
        text = path.read_text(encoding="utf-8")
        fm = extract_frontmatter_block(text)
        if fm is None:
            print(f"[!] {path.relative_to(vault)} ({source}) — no frontmatter")
            files_with_issues += 1
            total_issues += 1
            continue
        issues = check_atom(path, source, fm)
        if issues:
            files_with_issues += 1
            total_issues += len(issues)
            print(f"[!] {path.relative_to(vault)} ({source})")
            for i in issues:
                print(f"      - {i}")

    print()
    print(f"[=] {files_with_issues} file(s) with issues, {total_issues} issue(s) total.")
    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
