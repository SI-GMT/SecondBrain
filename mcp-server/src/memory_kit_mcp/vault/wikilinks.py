"""Wikilink utilities — single source of truth for parsing and resolution.

Per the linking invariant in ``core/procedures/_linking.md``: every
``[[wikilink]]`` written into a persisted vault file must resolve to an
existing target at the time of writing. The scanner (``health/scan.py``)
detects violations after the fact; the writers (``tools/archive.py`` etc.)
must enforce the invariant before persisting.

Both consumers must apply the same parsing and the same resolution
strategy — otherwise a writer could create wikilinks the scanner later
flags, or vice versa. This module is the canonical implementation of:

- the wikilink regex (catches ``[[X]]``, ``[[X|alias]]``, but not
  ``![[X]]`` embeds),
- ``strip_code`` — strips fenced and inline code so wikilinks inside
  ``` ``[[X]]`` ``` (the doctrinal bypass) are ignored,
- target resolution — a wikilink resolves if a file with stem ``X``
  exists anywhere in the vault, OR a relative path ``X.md`` exists.

Mirrors ``scripts/mem-health-scan.py`` — the standalone keeps its own
copy on purpose (autonomy without ``pip install``). Any change here must
be co-committed in the standalone (3rd cohesion pair, per ``CLAUDE.md``).
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]\|#]+)(?:\|[^\]]*)?\]\]")


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


def find_wikilinks(body: str) -> list[str]:
    """Return wikilink targets present in ``body``, ignoring those inside code.

    Targets are returned in document order; duplicates are preserved (callers
    can dedupe if they need to).
    """
    plain = strip_code(body)
    return [m.group(1).strip() for m in WIKILINK_RE.finditer(plain)]


def build_vault_index(vault: Path) -> tuple[set[str], set[str]]:
    """Build the indices used to resolve wikilinks against ``vault``.

    Returns ``(basenames, relpaths_no_ext)``:

    - ``basenames``: stems of every .md file in the vault (e.g. ``context``).
    - ``relpaths_no_ext``: vault-relative POSIX paths without the .md suffix
      (e.g. ``10-episodes/projects/secondbrain/context``).

    Excludes ``.obsidian/`` and ``.trash/`` to mirror the scanner's behaviour.
    """
    basenames: set[str] = set()
    relpaths: set[str] = set()
    for p in vault.rglob("*.md"):
        if ".obsidian" in p.parts or ".trash" in p.parts:
            continue
        basenames.add(p.stem)
        rel = p.relative_to(vault).as_posix()
        relpaths.add(rel[:-3] if rel.endswith(".md") else rel)
    return basenames, relpaths


def resolve_wikilink(
    target: str,
    basenames: set[str],
    relpaths_no_ext: set[str],
) -> bool:
    """Return True if ``target`` resolves to a vault file.

    A wikilink target resolves if:
    - its basename (last path segment, with .md stripped) matches a file stem
      anywhere in the vault, OR
    - its full text (with .md stripped) matches a relative path of an existing
      vault file.

    The convention ``index`` is always considered resolved — Obsidian treats
    bare ``[[index]]`` as the vault root index, and per the scanner this
    target is in ``SKIP_TARGETS``.
    """
    if target == "index":
        return True
    basename = target.split("/")[-1]
    stem = basename[:-3] if basename.endswith(".md") else basename
    if stem in basenames:
        return True
    target_no_ext = target[:-3] if target.endswith(".md") else target
    if target_no_ext in relpaths_no_ext:
        return True
    return False


def find_dangling(body: str, vault: Path, exempt: set[str] | None = None) -> list[str]:
    """Return the de-duplicated list of wikilink targets in ``body`` that do
    NOT resolve to any vault file.

    Args:
        body: Markdown body to scan.
        vault: vault root.
        exempt: optional set of targets to never report as dangling (e.g. read
            from a file's ``dangling_intentional`` frontmatter). Resolution is
            still attempted; exempt targets are simply filtered from the
            output if they would otherwise be reported.

    Returns:
        List of unique unresolved targets in first-occurrence order.
    """
    exempt = exempt or set()
    basenames, relpaths = build_vault_index(vault)
    seen: set[str] = set()
    out: list[str] = []
    for target in find_wikilinks(body):
        if target in seen or target in exempt:
            seen.add(target)
            continue
        if resolve_wikilink(target, basenames, relpaths):
            continue
        seen.add(target)
        out.append(target)
    return out


def build_incoming_index(
    vault_files: list[Path], vault: Path
) -> dict[str, set[Path]]:
    """For each file stem, return the set of vault files whose body contains a
    wikilink to that stem. Used by the scanner to compute orphan atoms.

    Files that fail to read (encoding errors etc.) are silently skipped — the
    scanner already reports them in its own error channel.
    """
    incoming: dict[str, set[Path]] = defaultdict(set)
    for p in vault_files:
        if ".obsidian" in p.parts or ".trash" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if text.startswith("---"):
            end = text.find("\n---", 4)
            body = text[end + 4:] if end != -1 else text
        else:
            body = text
        for target in find_wikilinks(body):
            basename = target.split("/")[-1]
            stem = basename[:-3] if basename.endswith(".md") else basename
            incoming[stem].add(p)
    return incoming
