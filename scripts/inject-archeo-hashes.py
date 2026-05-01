#!/usr/bin/env python3
"""
inject-archeo-hashes.py — backfill content_hash + previous_atom (and topology
hashes) on archeo-* atoms and topology files that pre-date the v0.7.1 hardening.

For every atom in the vault carrying `source: archeo-context | archeo-stack |
archeo-git` and every file in 99-meta/repo-topology/, inject the missing
mandatory fields:
  - content_hash  : SHA-256 of the body (after frontmatter, normalized LF + UTF-8 no BOM)
  - previous_atom : "" if absent (no inference)
  - source_doc_hash (archeo-context only) : SHA-256 of the source doc if found on disk
  - previous_topology_hash (topology files) : "" if absent

Idempotent: a file already carrying valid hash fields is left untouched.
Dry-run by default (use --apply to write).

Usage:
    python scripts/inject-archeo-hashes.py --vault /path/to/vault [--repo-root /path/to/repo] [--apply]
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n(.*)$", re.DOTALL)
# Match values that are quoted strings or bare scalars (not lists or maps)
KEY_VALUE_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*?)\s*$")

# Enum value normalizations — common localized variants → canonical English value.
# Applied per known field. Add entries here when new localizations surface.
ENUM_NORMALIZATIONS = {
    "force": {
        "ligne-rouge": "red-line",
        "ligne_rouge": "red-line",
        "lignerouge": "red-line",
        "linea-roja": "red-line",
        "rote-linie": "red-line",
        "krasnaya-liniya": "red-line",
        "heuristique": "heuristic",
        "preferable": "preference",
        "preference-fr": "preference",
    },
    "horizon": {"court": "short", "moyen": "medium", "long-terme": "long"},
    "kind":    {"projet": "project", "domaine": "domain"},
    "scope":   {"perso": "personal", "personnel": "personal", "pro": "work"},
}

TAG_FROM_FILENAME_RE = re.compile(r"-(v\d+)-(\d+)-(\d+)(?:-|$)")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str, str] | None:
    """Return (fields, frontmatter_raw, body) or None if no frontmatter."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    raw_fm = m.group(1)
    body = m.group(2)
    fields: dict[str, str] = {}
    for line in raw_fm.splitlines():
        if not line or line.startswith(" ") or line.startswith("-"):
            continue
        km = KEY_VALUE_RE.match(line)
        if km:
            fields[km.group(1)] = km.group(2)
    return fields, raw_fm, body


def sha256_text(text: str) -> str:
    """Hash the body normalized to LF + UTF-8."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a file's bytes (no normalization for binary)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def is_absent(fields: dict[str, str], key: str) -> bool:
    """True if the key is not in the frontmatter at all."""
    return key not in fields


def is_empty_or_absent(fields: dict[str, str], key: str) -> bool:
    """True if the key is missing OR present with an empty/null value."""
    if key not in fields:
        return True
    v = fields[key].strip().strip('"').strip("'")
    return v in ("", "null", "~")


# Backward-compat alias used by older logic — defaults to the strict form.
needs_field = is_empty_or_absent


def normalize_enums(raw_fm: str) -> tuple[str, list[str]]:
    """Rewrite localized enum values to their canonical English form.
    Returns (cleaned_fm, list_of_field_names_normalized)."""
    out_lines: list[str] = []
    normalized: list[str] = []
    for line in raw_fm.splitlines():
        if line.startswith(" ") or line.startswith("\t") or line.startswith("-") or line.startswith("#"):
            out_lines.append(line)
            continue
        m = KEY_VALUE_RE.match(line)
        if not m:
            out_lines.append(line)
            continue
        key = m.group(1)
        value = m.group(2).strip().strip('"').strip("'")
        if key in ENUM_NORMALIZATIONS and value in ENUM_NORMALIZATIONS[key]:
            new_value = ENUM_NORMALIZATIONS[key][value]
            out_lines.append(f"{key}: {new_value}")
            normalized.append(f"{key}={value}->{new_value}")
        else:
            out_lines.append(line)
    return ("\n".join(out_lines) + "\n", normalized)


def resolve_commit_sha_from_tag(repo_root: Path, fields: dict, source_milestone_hint: str = "") -> str:
    """Best-effort: if the file has source_milestone like 'v0.3.2', resolve to commit sha via git."""
    import subprocess
    sm = source_milestone_hint or fields.get("source_milestone", "").strip().strip('"').strip("'")
    if not sm or not sm.startswith("v"):
        return ""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "-n", "1", sm],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            sha = r.stdout.strip()
            if re.match(r"^[0-9a-f]{40}$", sha):
                return sha
    except Exception:
        pass
    return ""


def dedup_keys(raw_fm: str) -> tuple[str, list[str]]:
    """
    Keep only the first occurrence of each top-level key. Returns (cleaned_fm, list_of_dropped_keys).
    Lists, comments, and indented lines are preserved as-is (they don't carry top-level keys).
    """
    seen: set[str] = set()
    dropped: list[str] = []
    out_lines: list[str] = []
    for line in raw_fm.splitlines():
        m = KEY_VALUE_RE.match(line) if not (line.startswith(" ") or line.startswith("\t") or line.startswith("-") or line.startswith("#")) else None
        if m:
            k = m.group(1)
            if k in seen:
                dropped.append(k)
                continue
            seen.add(k)
        out_lines.append(line)
    return ("\n".join(out_lines) + "\n", dropped)


def inject_fields(raw_fm: str, additions: dict[str, str]) -> str:
    """Insert missing keys at the end of the frontmatter block."""
    if not additions:
        return raw_fm
    lines = raw_fm.rstrip("\n").splitlines()
    for k, v in additions.items():
        if v == "" or v is None:
            lines.append(f'{k}: ""')
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"


def write_atomic(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def process_atom(path: Path, repo_root: Path | None, dry_run: bool) -> tuple[bool, str]:
    """Return (changed, message). changed=True if the file was modified (or would be in dry-run)."""
    text = path.read_text(encoding="utf-8")
    parsed = parse_frontmatter(text)
    if not parsed:
        return False, "no frontmatter"
    fields, raw_fm, body = parsed
    source = fields.get("source", "").strip().strip('"').strip("'")

    # Step 1: dedup duplicate top-level keys
    raw_fm, dropped = dedup_keys(raw_fm)

    # Step 2: normalize localized enum values
    raw_fm, normalized = normalize_enums(raw_fm)

    additions: dict[str, str] = {}

    # content_hash — recompute if absent OR empty (to handle migration runs)
    if is_empty_or_absent(fields, "content_hash"):
        additions["content_hash"] = sha256_text(body)

    # previous_atom — only inject if the key is entirely absent
    # (empty string is a legitimate "first write" value and must be preserved as-is)
    if is_absent(fields, "previous_atom"):
        additions["previous_atom"] = ""

    # archeo-context: source_doc_hash — fill if absent OR empty
    if source == "archeo-context" and is_empty_or_absent(fields, "source_doc_hash"):
        source_doc = fields.get("source_doc", "").strip().strip('"').strip("'")
        if source_doc and repo_root:
            doc_path = repo_root / source_doc
            if doc_path.exists() and doc_path.is_file():
                try:
                    additions["source_doc_hash"] = sha256_file(doc_path)
                except Exception:
                    additions["source_doc_hash"] = ""
            else:
                additions["source_doc_hash"] = ""
        else:
            additions["source_doc_hash"] = ""

    # archeo-git: friction_detected — only if absent (false is a legitimate value)
    if source == "archeo-git" and is_absent(fields, "friction_detected"):
        if re.search(r"##\s+Friction", body, re.IGNORECASE):
            additions["friction_detected"] = "true"
        else:
            additions["friction_detected"] = "false"

    # archeo-git: commit_sha — fill if absent OR empty
    if source == "archeo-git" and is_empty_or_absent(fields, "commit_sha") and repo_root:
        sha = resolve_commit_sha_from_tag(repo_root, fields)
        if sha:
            additions["commit_sha"] = sha

    if not additions and not dropped and not normalized:
        return False, "already has all required fields"

    new_fm = inject_fields(raw_fm, additions)
    new_text = f"---\n{new_fm}---\n{body}"
    if not dry_run:
        write_atomic(path, new_text)
    msg_parts = []
    if dropped:
        msg_parts.append(f"deduplicated {','.join(sorted(set(dropped)))}")
    if normalized:
        msg_parts.append(f"normalized {','.join(normalized)}")
    if additions:
        msg_parts.append(f"injected {','.join(additions.keys())}")
    return True, "; ".join(msg_parts)


def process_topology(path: Path, dry_run: bool) -> tuple[bool, str]:
    text = path.read_text(encoding="utf-8")
    parsed = parse_frontmatter(text)
    if not parsed:
        return False, "no frontmatter"
    fields, raw_fm, body = parsed
    raw_fm, dropped = dedup_keys(raw_fm)
    additions: dict[str, str] = {}
    if is_empty_or_absent(fields, "content_hash"):
        additions["content_hash"] = sha256_text(body)
    if is_absent(fields, "previous_topology_hash"):
        additions["previous_topology_hash"] = ""
    if not additions and not dropped:
        return False, "already has all required fields"
    new_fm = inject_fields(raw_fm, additions)
    new_text = f"---\n{new_fm}---\n{body}"
    if not dry_run:
        write_atomic(path, new_text)
    msg_parts = []
    if dropped:
        msg_parts.append(f"deduplicated {','.join(sorted(set(dropped)))}")
    if additions:
        msg_parts.append(f"injected {','.join(additions.keys())}")
    return True, "; ".join(msg_parts)


def find_archeo_atoms(vault: Path) -> list[Path]:
    """Find files with 'source: archeo-' in the frontmatter."""
    out: list[Path] = []
    for md in vault.rglob("*.md"):
        if ".obsidian" in md.parts or "99-meta/sources" in str(md).replace("\\", "/"):
            continue
        try:
            head = md.read_text(encoding="utf-8")[:2000]
        except Exception:
            continue
        if re.search(r"^source:\s*archeo-(context|stack|git|atlassian)", head, re.MULTILINE):
            out.append(md)
    return sorted(out)


def find_topologies(vault: Path) -> list[Path]:
    topo_dir = vault / "99-meta" / "repo-topology"
    if not topo_dir.exists():
        return []
    return sorted(topo_dir.glob("*.md"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, help="Vault root path")
    ap.add_argument("--repo-root", help="Repo root (for source_doc_hash resolution on archeo-context)")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = ap.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.exists():
        print(f"Error: vault not found: {vault}", file=sys.stderr)
        return 1
    repo_root = Path(args.repo_root).resolve() if args.repo_root else None
    dry_run = not args.apply

    print(f"[i] Vault    : {vault}")
    print(f"[i] Repo     : {repo_root or '(none — source_doc_hash will be empty for missing context atoms)'}")
    print(f"[i] Mode     : {'APPLY' if args.apply else 'DRY-RUN'}")
    print()

    atoms = find_archeo_atoms(vault)
    topos = find_topologies(vault)

    print(f"[i] Found {len(atoms)} archeo atoms, {len(topos)} topology files.")
    print()

    changed = unchanged = 0
    for path in topos:
        rel = path.relative_to(vault)
        modified, msg = process_topology(path, dry_run)
        if modified:
            changed += 1
            print(f"[*] {rel} — {msg}")
        else:
            unchanged += 1
    for path in atoms:
        rel = path.relative_to(vault)
        modified, msg = process_atom(path, repo_root, dry_run)
        if modified:
            changed += 1
            print(f"[*] {rel} — {msg}")
        else:
            unchanged += 1

    print()
    print(f"[=] {changed} file(s) {'would be' if dry_run else ''} modified, {unchanged} already compliant.")
    if dry_run and changed > 0:
        print("    Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
