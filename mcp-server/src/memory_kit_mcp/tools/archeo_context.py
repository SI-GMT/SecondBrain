"""mem_archeo_context — Phase 1 LLM round-trip (v0.10.x post-2026-05-09).

Spec: core/procedures/mem-archeo-context.md

DESIGN PIVOT (2026-05-09 IRIS USER case study) : the previous v0.8.x stub
deferred Phase 1 to the skills procedure with the rationale that semantic
categorization is LLM territory. In practice that meant Phase 1 NEVER ran
on the MCP path — Gemini / Claude / Codex called mem_archeo_git directly,
extraction-only archives polluted the vault, and ``context.md`` stayed
empty (skeleton with no functional content).

The new design forces the LLM to actually read the project files via a
**two-phase round-trip** :

1. ``mem_archeo_context(phase='brief', project=...)`` — tool reads the
   archives written by Phase 3, collects the union of ``perimeter_files``
   per cycle, returns a paginated batch of files to read + an explicit
   instruction block + the synthesis schema. The LLM is told to open
   each file with its file-reading tool (Read / read_file / equivalent),
   group findings by sub-system, and fill the synthesis dict.

2. ``mem_archeo_context(phase='finalize', project=..., synthesis=...,
   acknowledged_via_read=True)`` — tool validates the synthesis, writes
   the project topology atom (``20-knowledge/architecture/{slug}-project-
   topology.md``), patches ``context.md`` sections (Current state /
   Cumulative decisions / Active assets) from the synthesis content, and
   returns a finalize report.

Without ``acknowledged_via_read=True``, the finalize phase refuses with a
structured error pointing back to brief — blocks free-form translation
drift (the same class of bug that previously dropped ``branch_first`` in
the plan→archeo handoff).

Pagination : if the union of ``perimeter_files`` exceeds the per-call
cap, the brief phase returns ``batch=N`` / ``total_batches=M`` and the
caller invokes brief multiple times (or finalize once with the full
synthesis aggregating all batches).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import (
    ArcheoContextBriefResult,
    ArcheoContextFinalizeResult,
    ArcheoContextSynthesis,
    _ArcheoCycleSummary,
)
from memory_kit_mcp.vault import frontmatter
from memory_kit_mcp.vault.atomic_io import hash_content


_PER_BATCH_FILE_CAP: int = 30


# ---------------------------------------------------------------------------
# Brief phase — collect cycles + perimeter from archives
# ---------------------------------------------------------------------------


def _collect_cycles(
    vault: Path, slug: str
) -> list[_ArcheoCycleSummary]:
    """Read all archives under projects/{slug}/archives/, extract cycle info.

    Filters to archives whose frontmatter has ``source: archeo-git`` and
    ``milestone_kind: merge`` — the perimeter walker output. Other
    milestone kinds (window/tag/release) don't carry perimeter_files and
    are useless for context synthesis.
    """
    arch_dir = vault / "10-episodes" / "projects" / slug / "archives"
    if not arch_dir.is_dir():
        return []
    out: list[_ArcheoCycleSummary] = []
    for path in sorted(arch_dir.glob("*.md")):
        try:
            fm, _body = frontmatter.read(path)
        except (OSError, ValueError):
            continue
        if fm.get("source") != "archeo-git":
            continue
        if fm.get("milestone_kind") != "merge":
            continue
        # perimeter_files lives in the body audit block, not frontmatter.
        # Re-derive from the audit section by parsing the body, OR fall back
        # to listing files via git diff if perimeter_range is in frontmatter.
        # For simplicity here we leave perimeter_files empty on the cycle
        # summary and let the orchestrator pass them via execute_brief direct
        # call (Phase 1 chained inside mem_archeo). Standalone callers can
        # still trigger the LLM read on the cycles' subjects.
        out.append(
            _ArcheoCycleSummary(
                sha=str(fm.get("commit_sha", "")),
                date=str(fm.get("date", "")),
                subject=str(fm.get("display", "")),
                files=[],
            )
        )
    return out


def _collect_perimeter_files(
    archives_dir: Path,
) -> tuple[list[str], list[_ArcheoCycleSummary]]:
    """Walk archives, parse body for perimeter file lists, return union + cycles.

    The perimeter list lives in the body's ``## Analyse technique`` section
    rendered by file_summary.render_technical_section — each file is a
    bullet starting with ``- **`...`**``. Falls back to empty when no merge
    archives exist.
    """
    if not archives_dir.is_dir():
        return [], []
    union: set[str] = set()
    cycles: list[_ArcheoCycleSummary] = []
    for path in sorted(archives_dir.glob("*.md")):
        try:
            fm, body = frontmatter.read(path)
        except (OSError, ValueError):
            continue
        if fm.get("source") != "archeo-git":
            continue
        if fm.get("milestone_kind") != "merge":
            continue
        cycle_files: list[str] = []
        in_technical = False
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                in_technical = stripped.startswith("## Analyse technique")
                continue
            if not in_technical:
                continue
            # Bullets emitted by render_technical_section : "- **`path`**"
            if stripped.startswith("- **`") and stripped.endswith("`**"):
                rel = stripped[len("- **`"): -len("`**")]
                if rel:
                    cycle_files.append(rel)
                    union.add(rel)
        cycles.append(
            _ArcheoCycleSummary(
                sha=str(fm.get("commit_sha", ""))[:12],
                date=str(fm.get("date", "")),
                subject=str(fm.get("display", "")),
                files=cycle_files,
            )
        )
    return sorted(union), cycles


def _build_synthesis_schema() -> dict[str, Any]:
    """Schema dict the LLM uses to structure its synthesis."""
    return {
        "components": {
            "<sub-system or directory>": {
                "role": "<one-line role of this sub-system>",
                "files": [
                    {
                        "path": "<repo-relative path>",
                        "role": "<one-line role of this file>",
                        "key_methods": ["<method name>", "..."],
                    }
                ],
            }
        },
        "domain_concepts": ["<one line per domain term>"],
        "patterns": ["<one line per recurring pattern>"],
        "decisions": ["<one line per implicit decision>"],
        "risks_or_friction": ["<one line per risk>"],
    }


def _build_brief_instructions(
    slug: str, files: list[str], cycles: list[_ArcheoCycleSummary],
    batch: int, total_batches: int,
) -> str:
    """Plain-text directive the LLM host MUST execute."""
    return (
        f"# Phase 1 — context synthesis for project '{slug}'\n\n"
        f"You MUST open every file in `files_to_read` "
        f"({len(files)} file(s), batch {batch}/{total_batches}) using "
        f"your file-reading tool (Read / read_file / equivalent). For each "
        f"file, capture: 1-line role, key class/function names, key methods. "
        f"Group your findings by sub-system (use directory paths as keys). "
        f"Do NOT skim. Do NOT sample. Read every file in this batch.\n\n"
        f"## STRICT schema requirements (synthesis is REJECTED otherwise)\n\n"
        f"For EVERY component you include in `synthesis.components` :\n"
        f"- `role` MUST be a non-empty one-line description of what the "
        f"sub-system does. NOT just a directory restated as a sentence.\n"
        f"- `files` MUST be a non-empty list. Each file entry MUST carry :\n"
        f"  - `path` : non-empty repo-relative path\n"
        f"  - `role` : one-line description of what the file does\n"
        f"  - `key_methods` : list of method/function names (can be empty "
        f"if the file is e.g. a config/data file)\n"
        f"- If you have nothing to say about a directory, DROP IT from "
        f"`components` entirely — do NOT include it with empty `files`.\n"
        f"- Component keys MUST be plain strings, NOT JSON-stringified "
        f"(no embedded `\"` or `'` quotes inside the key string).\n\n"
        f"The whole point of Phase 1 is the FILE-level mapping. A synthesis "
        f"with components that have role-but-no-files is rejected — it "
        f"produces a top-level dir summary which the user can already see "
        f"with `ls`, not the project topology.\n\n"
        f"Then aggregate across batches and call:\n\n"
        f"```\n"
        f"mem_archeo_project_topology(\n"
        f"    project='{slug}',\n"
        f"    acknowledged_via_read=True,\n"
        f"    synthesis={{...}}  # match the schema in `synthesis_schema`\n"
        f")\n"
        f"```\n\n"
        f"Cycle summaries (Phase 3 archives) for context grouping :\n"
        + "\n".join(
            f"- {c.date} `{c.sha}` — {c.subject} ({len(c.files)} file(s))"
            for c in cycles[:20]
        )
        + (
            f"\n... (+{len(cycles) - 20} more cycles)"
            if len(cycles) > 20
            else ""
        )
    )


def execute_brief(
    vault: Path, project: str, batch: int = 1
) -> ArcheoContextBriefResult:
    """Brief phase entrypoint — module-level for orchestrator chaining."""
    slug = project
    archives_dir = vault / "10-episodes" / "projects" / slug / "archives"
    union_files, cycles = _collect_perimeter_files(archives_dir)

    total_batches = max(
        1, (len(union_files) + _PER_BATCH_FILE_CAP - 1) // _PER_BATCH_FILE_CAP
    )
    batch = max(1, min(batch, total_batches))
    start = (batch - 1) * _PER_BATCH_FILE_CAP
    end = start + _PER_BATCH_FILE_CAP
    batch_files = union_files[start:end]

    if batch < total_batches:
        next_call: dict[str, Any] = {
            "tool": "mem_archeo_context",
            "args": {
                "project": slug,
                "batch": batch + 1,
            },
        }
    else:
        next_call = {
            "tool": "mem_archeo_project_topology",
            "args": {
                "project": slug,
                "acknowledged_via_read": True,
                "synthesis": "<fill from your reading of all batches>",
            },
        }

    schema = _build_synthesis_schema()
    instructions = _build_brief_instructions(
        slug, batch_files, cycles, batch, total_batches
    )

    summary = (
        f"## mem_archeo_context — brief phase\n\n"
        f"- Project : `{slug}`\n"
        f"- Batch : {batch}/{total_batches}\n"
        f"- Files in this batch : {len(batch_files)}\n"
        f"- Total perimeter files : {len(union_files)}\n"
        f"- Cycles : {len(cycles)}\n\n"
        f"_Read every file in `files_to_read`. Then "
        f"{'invoke next batch' if batch < total_batches else 'invoke finalize'} "
        f"via `next_call`._"
    )

    return ArcheoContextBriefResult(
        project=slug,
        needs_llm_read=True,
        batch=batch,
        total_batches=total_batches,
        files_to_read=batch_files,
        cycles=cycles,
        synthesis_schema=schema,
        instructions=instructions,
        next_call=next_call,
        summary_md=summary,
    )


# ---------------------------------------------------------------------------
# Finalize phase — write topology atom + patch context.md
# ---------------------------------------------------------------------------


def _clean_key(key: str) -> str:
    """Strip parasitic quote chars from synthesis dict keys.

    Some LLM hosts serialize dict keys with embedded quotes when round-tripped
    through JSON-in-string conversions, producing keys like ``'".vscode"'``
    or ``"'src/X'"``. This helper normalizes them so the renderer + zone
    index patches see clean paths.
    """
    return key.strip().strip('"').strip("'").strip()


def _render_topology_atom(
    slug: str, synthesis: ArcheoContextSynthesis, cycle_count: int
) -> str:
    """Hierarchical project-topology atom from synthesis.components.

    Skips components that have neither role nor files (extraction-empty
    placeholders sometimes produced by LLMs that listed top-level dirs
    without diving into their content).
    """
    lines = [
        f"# {slug} — project topology",
        "",
        f"_Synthesized from {cycle_count} archeo-git cycle(s) by Phase 1 LLM "
        f"round-trip._",
        "",
        "## Components",
        "",
    ]
    if not synthesis.components:
        lines.append("_(no components — synthesis empty)_")
    rendered_any = False
    for raw_name in sorted(synthesis.components):
        comp = synthesis.components[raw_name]
        if not isinstance(comp, dict):
            continue
        role = str(comp.get("role", "")).strip()
        files = comp.get("files", []) or []
        if not role and not files:
            # Skip placeholder-only components — empty atoms add no value.
            continue
        comp_name = _clean_key(str(raw_name))
        lines.append(f"### `{comp_name}`")
        if role:
            lines.append(f"_{role}_")
        lines.append("")
        if isinstance(files, list):
            for f in files:
                if not isinstance(f, dict):
                    continue
                path = _clean_key(str(f.get("path", "")))
                if not path:
                    continue
                f_role = str(f.get("role", "")).strip()
                methods = f.get("key_methods", []) or []
                lines.append(f"- **`{path}`**")
                if f_role:
                    lines.append(f"  - _role_ : {f_role}")
                if isinstance(methods, list) and methods:
                    lines.append(
                        "  - _key methods_ : "
                        + ", ".join(f"`{m}`" for m in methods[:8])
                    )
        lines.append("")
        rendered_any = True
    if not rendered_any and synthesis.components:
        lines.append(
            "_(all components were empty — synthesis components had neither "
            "role nor files. The LLM likely returned only top-level dir names "
            "without descending. Re-run mem_archeo_context brief and ensure "
            "each component carries role + ≥1 file.)_"
        )

    if synthesis.domain_concepts:
        lines.append("## Domain concepts")
        lines.append("")
        for c in synthesis.domain_concepts:
            lines.append(f"- {c}")
        lines.append("")
    if synthesis.patterns:
        lines.append("## Patterns")
        lines.append("")
        for p in synthesis.patterns:
            lines.append(f"- {p}")
        lines.append("")
    if synthesis.decisions:
        lines.append("## Decisions")
        lines.append("")
        for d in synthesis.decisions:
            lines.append(f"- {d}")
        lines.append("")
    if synthesis.risks_or_friction:
        lines.append("## Risks & friction")
        lines.append("")
        for r in synthesis.risks_or_friction:
            lines.append(f"- {r}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _patch_zone_index(
    vault: Path, slug: str, atom_rel: str
) -> bool:
    """Add the project-topology atom to 20-knowledge/index.md under the
    project's section. Creates the section if absent. Idempotent.
    """
    zone_index = vault / "20-knowledge" / "index.md"
    if not zone_index.is_file():
        return False
    fm, body = frontmatter.read(zone_index)
    atom_stem = Path(atom_rel).stem
    new_link = f"- [{atom_stem}]({atom_rel})"
    if new_link in body:
        return False

    section_header = f"### {slug}"
    lines = body.splitlines()
    out: list[str] = []
    inserted = False

    if section_header in body:
        # Insert under existing section, before next H3 / H2.
        in_section = False
        for line in lines:
            stripped = line.strip()
            if stripped == section_header:
                in_section = True
                out.append(line)
                continue
            if in_section and (
                stripped.startswith("### ") or stripped.startswith("## ")
            ):
                out.append(new_link)
                inserted = True
                in_section = False
            out.append(line)
        if in_section and not inserted:
            out.append(new_link)
            inserted = True
    else:
        # New section : append after "## Knowledge by project" header,
        # alphabetically among existing project sections (best-effort).
        section_block = ["", section_header, "", new_link, ""]
        in_kbp = False
        appended = False
        for line in lines:
            out.append(line)
            stripped = line.strip()
            if stripped.startswith("## Knowledge by project"):
                in_kbp = True
                continue
            if in_kbp and stripped.startswith("## ") and not appended:
                # Next H2 — insert before it (out already has the H2 line,
                # rewind by inserting before).
                out.insert(-1, "\n".join(section_block))
                appended = True
                in_kbp = False
        if in_kbp and not appended:
            out.append("\n".join(section_block))
            appended = True
        if not appended:
            # No "Knowledge by project" header found — fallback append.
            out.extend(section_block)
        inserted = True

    if not inserted:
        return False
    new_body = "\n".join(out) + ("\n" if not body.endswith("\n") else "")
    frontmatter.write(zone_index, fm, new_body)
    return True


def _write_topology_atom(
    vault: Path, slug: str, body: str
) -> tuple[str, bool]:
    """Write 20-knowledge/architecture/{slug}-project-topology.md atomic.

    Returns ``(vault_relative_path, created)`` where ``created`` is True
    if the file did not previously exist, False on update.
    """
    rel = f"20-knowledge/architecture/{slug}-project-topology.md"
    target = vault / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    created = not target.exists()
    fm = {
        "zone": "knowledge",
        "type": "project-topology",
        "project": slug,
        "tags": [
            f"project/{slug}",
            "zone/knowledge",
            "type/project-topology",
            "source/archeo-context",
        ],
        "display": f"{slug} — project topology (Phase 1 synthesis)",
        "content_hash": hash_content(body),
        "previous_topology_hash": "",
    }
    frontmatter.write(target, fm, body)
    return rel, created


def _patch_context_from_synthesis(
    vault: Path, slug: str, synthesis: ArcheoContextSynthesis,
    cycle_count: int,
) -> tuple[str, bool]:
    """Replace context.md skeleton placeholders with synthesis content."""
    rel = f"10-episodes/projects/{slug}/context.md"
    target = vault / rel
    if not target.is_file():
        return rel, False
    fm, _body = frontmatter.read(target)

    cumulative = synthesis.decisions + synthesis.patterns
    state_in_progress = []
    if synthesis.risks_or_friction:
        state_in_progress = [
            f"Verify : {r}" for r in synthesis.risks_or_friction[:5]
        ]

    body_lines = [
        "> Snapshot mutable du projet. Voir aussi : "
        "[historique](history.md) · [archives/](archives/) · "
        f"[topology](../../../20-knowledge/architecture/{slug}-project-topology.md)",
        "",
        f"# {slug.capitalize()} — Active context",
        "",
        "## Current state",
    ]
    body_lines.append(
        f"- Phase : archeo-context synthesized ({cycle_count} cycles)"
    )
    if synthesis.components:
        body_lines.append(
            f"- Components mapped : {len(synthesis.components)} sub-system(s)"
        )
    if state_in_progress:
        body_lines.append("- In progress (LLM-flagged) :")
        for s in state_in_progress:
            body_lines.append(f"  - {s}")
    else:
        body_lines.append("- In progress : (none surfaced by synthesis)")
    body_lines.append("")

    body_lines.append("## Cumulative decisions")
    if cumulative:
        for d in cumulative[:30]:
            body_lines.append(f"- {d}")
    else:
        body_lines.append("_(none surfaced by synthesis)_")
    body_lines.append("")

    body_lines.append("## Domain concepts")
    if synthesis.domain_concepts:
        for c in synthesis.domain_concepts[:30]:
            body_lines.append(f"- {c}")
    else:
        body_lines.append("_(none surfaced by synthesis)_")
    body_lines.append("")

    body_lines.append("## Next steps")
    body_lines.append("_(LLM TODO — derive from risks_or_friction or domain inputs)_")
    body_lines.append("")
    body_lines.append("## Active assets (URLs)")
    body_lines.append("_(none yet)_")
    body_lines.append("")

    body = "\n".join(body_lines)
    fm["phase"] = (
        f"archeo-context synthesized ({cycle_count} cycles, "
        f"{len(synthesis.components)} components)"
    )
    frontmatter.write(target, fm, body)
    return rel, True


def execute_finalize(
    vault: Path,
    project: str,
    synthesis: ArcheoContextSynthesis,
    acknowledged_via_read: bool,
) -> ArcheoContextFinalizeResult:
    """Finalize phase entrypoint — module-level for orchestrator chaining."""
    if not acknowledged_via_read:
        raise RuntimeError(
            "mem_archeo_context(phase='finalize') refused : "
            "acknowledged_via_read=False. The LLM caller MUST first invoke "
            "phase='brief', read every file in files_to_read with its file "
            "tool, then re-invoke finalize with synthesis filled and "
            "acknowledged_via_read=True. This token blocks the free-form "
            "translation drift class (case study 2026-05-09 IRIS USER : "
            "Gemini wrote 30 archives without ever reading the project "
            "files, leaving context.md skeleton-empty)."
        )

    slug = project
    archives_dir = vault / "10-episodes" / "projects" / slug / "archives"
    _, cycles = _collect_perimeter_files(archives_dir)
    cycle_count = len(cycles)

    files_created: list[str] = []
    files_modified: list[str] = []
    warnings: list[str] = []

    topology_body = _render_topology_atom(slug, synthesis, cycle_count)
    topo_rel, topo_created = _write_topology_atom(vault, slug, topology_body)
    if topo_created:
        files_created.append(topo_rel)
    else:
        files_modified.append(topo_rel)

    if _patch_zone_index(vault, slug, topo_rel):
        files_modified.append("20-knowledge/index.md")

    ctx_rel, ctx_patched = _patch_context_from_synthesis(
        vault, slug, synthesis, cycle_count
    )
    if ctx_patched:
        files_modified.append(ctx_rel)
    else:
        warnings.append(
            f"context.md not patched : {ctx_rel} does not exist (run Phase 5 "
            "skeleton first via mem_archeo_git or mem_archeo)."
        )

    summary = (
        f"## mem_archeo_context — finalize\n\n"
        f"- Project : `{slug}`\n"
        f"- Topology atom : `{topo_rel}` "
        f"({'created' if topo_created else 'updated'})\n"
        f"- Context patched : {ctx_patched}\n"
        f"- Components : {len(synthesis.components)}\n"
        f"- Domain concepts : {len(synthesis.domain_concepts)}\n"
        f"- Patterns : {len(synthesis.patterns)}\n"
        f"- Decisions : {len(synthesis.decisions)}\n"
        f"- Risks : {len(synthesis.risks_or_friction)}\n"
    )

    return ArcheoContextFinalizeResult(
        project=slug,
        success=True,
        files_created=files_created,
        files_modified=files_modified,
        warnings=warnings,
        summary_md=summary,
    )


# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def mem_archeo_context(
        project: str = Field(
            ..., description="Project slug (matches 10-episodes/projects/{slug})."
        ),
        batch: int = Field(
            1,
            description="Brief-phase batch number when files exceed per-call cap.",
        ),
    ) -> ArcheoContextBriefResult:
        """Phase 1 brief — list project files the LLM MUST read.

        Walks ``10-episodes/projects/{project}/archives/`` for merge-mode
        archives written by Phase 3 (perimeter walker), collects the union
        of perimeter files, returns a paginated batch + the synthesis
        schema + an explicit instruction block telling the LLM how to
        proceed. The LLM host MUST read every file in ``files_to_read``
        with its file-reading tool, then invoke
        ``mem_archeo_project_topology`` to finalize Phase 1.

        See ``core/procedures/mem-archeo-context.md`` for the doctrine.
        """
        config = get_config()
        vault = config.vault
        return execute_brief(vault, project, batch=batch)

    @mcp.tool()
    def mem_archeo_project_topology(
        project: str = Field(
            ..., description="Project slug (matches 10-episodes/projects/{slug})."
        ),
        synthesis: dict[str, Any] = Field(
            ...,
            description=(
                "LLM-produced synthesis matching the schema returned by "
                "``mem_archeo_context`` brief phase. Required keys : "
                "components, domain_concepts, patterns, decisions, "
                "risks_or_friction (any can be empty list / dict)."
            ),
        ),
        acknowledged_via_read: bool = Field(
            False,
            description=(
                "Token : MUST be True after the LLM read every file in "
                "the brief's files_to_read. Blocks the "
                "extraction-without-reading drift class (case study "
                "2026-05-09 IRIS USER : 30 archives written without ever "
                "reading project files)."
            ),
        ),
    ) -> ArcheoContextFinalizeResult:
        """Phase 1 finalize — write project-topology atom + patch context.md.

        Accepts the LLM's synthesis (filled per the schema returned by
        ``mem_archeo_context`` brief). Validates schema, then writes :

        - ``20-knowledge/architecture/{slug}-project-topology.md`` —
          hierarchical view of components / files / roles / domain
          concepts / patterns / decisions / risks.
        - Patches ``10-episodes/projects/{slug}/context.md`` :
          ``Current state``, ``Cumulative decisions``, ``Domain concepts``
          sections rebuilt from the synthesis (replaces the skeleton
          placeholders left by Phase 5).

        Refuses with a structured error when ``acknowledged_via_read=False``
        — that token is the only barrier between "LLM actually read the
        files" and "LLM made up plausible-looking content".
        """
        config = get_config()
        vault = config.vault
        try:
            synth_obj = ArcheoContextSynthesis.model_validate(
                synthesis or {}
            )
        except Exception as exc:
            raise ValueError(
                f"synthesis does not match ArcheoContextSynthesis schema: {exc}"
            ) from exc
        return execute_finalize(
            vault, project, synth_obj, acknowledged_via_read
        )
