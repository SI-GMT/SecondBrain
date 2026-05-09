"""mem_archeo — Triphasic archeo orchestrator.

Spec: core/procedures/mem-archeo.md

Orchestrates Phase 1 + Phase 2 + Phase 3 sharing a single Phase 0 topology
scan. In v0.8.x:

- **Phase 1 (context)** is intentionally SKIPPED on the MCP path because
  semantic span classification is LLM territory (see archeo_context.py for
  the full decision rationale). The orchestrator surfaces a warning telling
  the LLM client to run `mem-archeo-context` skill separately if it wants
  Phase 1 outputs.
- **Phase 2 (stack)** is delegated to archeo_stack.execute_stack().
- **Phase 3 (git)** is delegated to archeo_git.execute_git().

Phase 0 is scanned once via vault.topology_scanner.scan() and reused by
both Phase 2 and Phase 3 (skip_repo_validation=True for Phase 3 since the
orchestrator validates upfront).

POC scope (v0.8.x):
- Standard mode only (no --branch-first / --skip-phase / --only-phase).
- Topology persistence: created if absent, left untouched if present.
  Full topology refresh logic deferred to v0.8.x continuation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools import (
    archeo_context,
    archeo_git,
    archeo_plan,
    archeo_stack,
)
from memory_kit_mcp.tools._models import ArcheoResult
from memory_kit_mcp.vault import frontmatter, paths
from memory_kit_mcp.vault.atomic_io import hash_content
from memory_kit_mcp.vault.topology_scanner import NotAGitRepoError, Topology, scan


def register(mcp: FastMCP) -> None:
    """Register mem_archeo orchestrator with the FastMCP instance."""

    @mcp.tool()
    def mem_archeo(
        repo_path: str = Field(..., description="Absolute path to the local Git repository."),
        project: str | None = Field(
            None,
            description="Target project slug. Defaults to basename(repo_path) if it matches an existing project.",
        ),
        depth: int = Field(2, ge=1, le=4, description="Topology scan depth."),
        level: str = Field(
            "tags",
            description=(
                "Phase 3 granularity: 'tags' (semver), 'releases' (GitHub Releases), "
                "'merges' (merged PRs), or 'commits' (time-windowed)."
            ),
        ),
        since: str | None = Field(None, description="Phase 3 lower bound YYYY-MM-DD."),
        until: str | None = Field(None, description="Phase 3 upper bound YYYY-MM-DD."),
        window: str = Field(
            "week",
            description="For level='commits': grouping window — one of day, week, month.",
        ),
        by_author: bool = Field(
            False,
            description=(
                "For level='commits' or branch-first: split each window per primary author. "
                "Co-authors recorded as metadata."
            ),
        ),
        branch_first: str | None = Field(
            None,
            description=(
                "If set, scope Phase 3 to commits unique to this branch since its "
                "divergence from branch_base. Activates branch-first mode + the "
                "Phase 0 cadrage gating (see acknowledged_via_plan)."
            ),
        ),
        branch_base: str = Field(
            "main",
            description="Branch-first mode: base branch to compute the divergence point from.",
        ),
        since_sha: str | None = Field(
            None,
            description=(
                "Branch-first escape hatch: explicit start SHA (passed through to "
                "Phase 3). Bypasses merge-base detection."
            ),
        ),
        since_date: str | None = Field(
            None,
            description=(
                "Branch-first escape hatch: YYYY-MM-DD floor (passed through to "
                "Phase 3)."
            ),
        ),
        by_files: bool = Field(
            False,
            description=(
                "Branch-first strategy B: query commits TOUCHING the files "
                "introduced by the branch (passed through to Phase 3)."
            ),
        ),
        acknowledged_via_plan: bool = Field(
            False,
            description=(
                "Phase 0 cadrage gating (v0.10.x post-Gemini-drift) : MUST be "
                "True for branch-first invocations. When False with branch_first "
                "set, the orchestrator returns the structured plan WITHOUT any "
                "writes, so the caller can present it to the user for "
                "validation. Re-invoke with acknowledged_via_plan=True after "
                "the user validates (or overrides) the slug / scope / "
                "granularity / filters."
            ),
        ),
    ) -> ArcheoResult:
        """Triphasic archeo: Phase 0 + Phase 2 + Phase 3 (Phase 1 skipped — LLM territory).

        Scans the repo's topology once and runs Phase 2 (stack resolution) and
        Phase 3 (Git history reconstruction at the chosen ``level``) sharing the
        scan. Branch-first mode (``branch_first``) restricts Phase 3 to commits
        unique to that branch.

        **Branch-first cadrage gating (v0.10.x)** : when ``branch_first`` is set
        and ``acknowledged_via_plan=False`` (the default), the orchestrator
        runs Phase 0 cadrage (mem_archeo_plan), returns the structured plan
        with ``needs_validation=True``, and writes nothing. The caller MUST
        surface the plan to the user, get explicit validation/override on the
        slug / scope / granularity / filters, then re-invoke with
        ``acknowledged_via_plan=True``. This eliminates the macro-drift class
        demonstrated by the 2026-05-08 Gemini case study.

        Phase 1 (context extraction) is intentionally skipped on the MCP path —
        run ``mem-archeo-context`` skill separately if needed. Refuses non-Git
        directories.
        """
        config = get_config()
        vault = config.vault
        repo = Path(repo_path).expanduser().resolve()

        # Branch-first cadrage gating: build the plan first; if not yet
        # acknowledged, return it for user validation without any writes.
        if branch_first and not acknowledged_via_plan:
            plan = archeo_plan._build_plan(
                repo=repo,
                vault=vault,
                branch_arg=branch_first,
                branch_base_arg=branch_base,
                project_arg=project,
            )
            return ArcheoResult(
                project=plan.slug.candidate,
                repo_path=str(repo),
                needs_validation=True,
                plan=plan,
                phase_1_skipped=True,
                phase_1_message="",
                stack=None,
                git=None,
                topology_path="",
                topology_outcome="skipped",
                files_created=[],
                files_modified=[],
                warnings=[
                    "Branch-first cadrage required — plan returned for "
                    "user validation. Re-invoke with acknowledged_via_plan="
                    "True after validation.",
                ],
                summary_md=plan.summary_md,
            )

        # Phase 0 — single topology scan shared by Phases 2 and 3
        try:
            topology = scan(repo, depth=depth, vault=vault)
        except NotAGitRepoError as e:
            raise NotAGitRepoError(str(e)) from e

        # Resolve slug once (used by both phases and topology persistence)
        slug = archeo_stack._resolve_project_slug(vault, repo, project)

        # Phase 2 — stack
        stack_result = archeo_stack.execute_stack(
            vault=vault,
            repo=repo,
            project=slug,
            depth=depth,
            topology=topology,
        )

        # Phase 3 — git (skip validation since Phase 0 already validated)
        git_result = archeo_git.execute_git(
            vault=vault,
            repo=repo,
            project=slug,
            level=level,
            since=since,
            until=until,
            window=window,
            by_author=by_author,
            branch_first=branch_first,
            branch_base=branch_base,
            since_sha=since_sha,
            since_date=since_date,
            by_files=by_files,
            skip_repo_validation=True,
        )

        # Topology persistence (best-effort)
        topology_outcome, topology_rel_path = _persist_topology(vault, slug, topology)

        # Aggregate
        files_created = list(stack_result.files_created) + list(git_result.files_created)
        files_modified = list(stack_result.files_modified) + list(git_result.files_modified)
        if topology_outcome == "created":
            files_created.append(topology_rel_path)
        elif topology_outcome == "updated":
            files_modified.append(topology_rel_path)

        warnings = list(stack_result.warnings) + list(git_result.warnings)

        # Phase 1 — auto-prepare brief from Phase 3 archives. The LLM caller
        # MUST then read files_to_read and invoke mem_archeo_context(
        # phase='finalize', acknowledged_via_read=True, synthesis=...)
        # to write the topology atom + patch context.md. Bypassing this
        # leaves context.md skeleton-empty (the 2026-05-09 IRIS USER drift
        # class : extraction without reading).
        context_brief = None
        needs_synthesis = False
        try:
            context_brief = archeo_context.execute_brief(
                vault=vault, project=slug, batch=1
            )
            if context_brief.files_to_read:
                needs_synthesis = True
                phase_1_msg = (
                    f"Phase 1 brief prepared : {len(context_brief.files_to_read)} "
                    f"file(s) in batch 1/{context_brief.total_batches}, "
                    f"{len(context_brief.cycles)} cycle(s). "
                    "READ every file in context_brief.files_to_read with your "
                    "file-reading tool, then invoke mem_archeo_context("
                    "phase='finalize', acknowledged_via_read=True, "
                    "synthesis=...) to finalize Phase 1."
                )
            else:
                phase_1_msg = (
                    "Phase 1 brief skipped : no perimeter files in archives "
                    "(Phase 3 produced 0 merge-mode milestones). Run "
                    "mem-archeo-context skill manually if you need Phase 1."
                )
        except Exception as exc:
            phase_1_msg = (
                f"Phase 1 brief failed : {exc}. Falling back to skill-only "
                "invocation (run /mem-archeo-context manually)."
            )
            warnings.append(phase_1_msg)
        warnings.append(phase_1_msg)

        return ArcheoResult(
            project=slug,
            repo_path=str(repo),
            phase_1_skipped=not needs_synthesis,
            phase_1_message=phase_1_msg,
            stack=stack_result,
            git=git_result,
            topology_path=topology_rel_path,
            topology_outcome=topology_outcome,
            needs_context_synthesis=needs_synthesis,
            context_brief=context_brief,
            files_created=files_created,
            files_modified=files_modified,
            warnings=warnings,
            summary_md=_summary_md(
                slug, stack_result, git_result, topology_outcome,
                needs_synthesis=needs_synthesis,
            ),
        )


# ----------------------------------------------------------------------
# Topology persistence
# ----------------------------------------------------------------------


def _persist_topology(vault: Path, slug: str, topology: Topology) -> tuple[str, str]:
    """Create the topology file if absent. Leave it untouched if present.

    Returns (outcome, vault_relative_path):
    - outcome: 'created' | 'skipped' (POC: 'updated' deferred)
    - path: e.g. '99-meta/repo-topology/{slug}.md'

    Per the spec, the persisted topology is what mem-recall reads to learn
    the project's structure. We populate the canonical sections so Phase 2
    and Phase 3 outputs can link to it via context_origin wikilinks.
    """
    target = paths.topology_file(vault, slug)
    rel_path = f"99-meta/repo-topology/{slug}.md"

    if target.is_file():
        # POC: don't try to merge with existing topology. The skill fallback
        # handles the full update workflow (insert/refresh sections idempotently).
        return "skipped", rel_path

    body = _render_topology_body(slug, topology)
    body_hash = hash_content(body)
    fm = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "zone": "meta",
        "type": "repo-topology",
        "project": slug,
        "repo_path": topology.repo_path,
        "repo_remote": topology.repo_remote,
        "content_hash": body_hash,
        "previous_topology_hash": "",
        "last_archive": "",
        "tags": [
            "zone/meta",
            "type/repo-topology",
            f"project/{slug}",
        ],
        "display": f"{slug} — repo topology",
    }
    frontmatter.write(target, fm, body)
    return "created", rel_path


def _render_topology_body(slug: str, topology: Topology) -> str:
    """Render the canonical topology body (sections per the spec §T6)."""
    lines = [
        f"# Topology — {slug}",
        "",
        f"_Scanned at: {topology.scanned_at} (depth {topology.depth_limit})._",
        "",
        "## Repo metadata",
        "",
        f"- **Path** : `{topology.repo_path}`",
        f"- **Remote** : {topology.repo_remote or '(none)'}",
        "",
        "## Categories",
        "",
    ]
    for cat in (
        "ai_files", "readme", "changelog", "docs", "sources", "tests",
        "ci", "infra", "manifests", "lockfiles", "config", "editor",
        "git_meta", "license", "other",
    ):
        entries = topology.categories.get(cat, [])
        if not entries:
            continue
        lines.append(f"### {cat}")
        for e in entries[:30]:
            lines.append(f"- `{e}`")
        lines.append("")

    lines.append("## Stack hints (Phase 0 lightweight)")
    lines.append("")
    for layer, hints in topology.stack_hints.items():
        if hints:
            lines.append(f"- **{layer}** : {', '.join(hints)}")
        else:
            lines.append(f"- **{layer}** : (none)")
    lines.append("")

    if topology.workspaces:
        lines.append("## Workspaces")
        lines.append("")
        for w in topology.workspaces:
            link = f" → [[10-episodes/projects/{w.vault_project}/context]]" if w.vault_project else " (no associated vault project)"
            implicit = " _(implicit)_" if w.workspace_implicit else ""
            lines.append(f"- `{w.name}` (`{w.path}`){link}{implicit}")
        lines.append("")

    lines.append("## Phases archeo couvertes")
    lines.append("")
    today = datetime.now(timezone.utc).date().isoformat()
    lines.append(f"- Phase 0 (topology scan) — {today}")
    lines.append(f"- Phase 2 (archeo-stack) — see derived atoms in `20-knowledge/architecture/{slug}-stack-*.md`")
    lines.append(f"- Phase 3 (archeo-git) — see archives in `10-episodes/projects/{slug}/archives/`")
    lines.append("")
    lines.append("_(Phase 1 archeo-context is skill-only — run `/mem-archeo-context` separately if needed.)_")
    lines.append("")

    if topology.warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in topology.warnings:
            lines.append(f"- {w}")
        lines.append("")

    return "\n".join(lines)


# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------


def _summary_md(
    slug: str,
    stack: object,
    git: object,
    topology_outcome: str,
    *,
    needs_synthesis: bool = False,
) -> str:
    p1 = (
        "brief prepared — LLM MUST read files + invoke mem_archeo_context"
        "(phase='finalize')"
        if needs_synthesis
        else "skipped (no merge-cycle archives produced)"
    )
    return (
        f"**mem_archeo** — {slug}\n\n"
        f"**Phase 0** (topology scan) : OK\n"
        f"**Phase 1** (context) : {p1}\n"
        f"**Phase 2** (stack) : {getattr(stack, 'layers_resolved', 0)} layers resolved, "
        f"{getattr(stack, 'atoms_created', 0)} atoms created, "
        f"{getattr(stack, 'atoms_skipped', 0)} skipped\n"
        f"**Phase 3** (git) : {getattr(git, 'milestones_processed', 0)} tags processed, "
        f"{getattr(git, 'archives_created', 0)} archives created, "
        f"{getattr(git, 'archives_skipped', 0)} skipped\n"
        f"**Topology** : {topology_outcome}\n"
    )
