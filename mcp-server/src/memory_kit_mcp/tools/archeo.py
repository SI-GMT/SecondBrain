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
from memory_kit_mcp.tools import archeo_git, archeo_stack
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
            description="Phase 3 granularity. POC supports 'tags' only.",
        ),
        since: str | None = Field(None, description="Phase 3 lower bound YYYY-MM-DD."),
        until: str | None = Field(None, description="Phase 3 upper bound YYYY-MM-DD."),
    ) -> ArcheoResult:
        """Triphasic archeo: Phase 0 + Phase 2 + Phase 3 (Phase 1 skipped — LLM territory).

        Scans the repo's topology once and runs Phase 2 (stack resolution) and
        Phase 3 (Git history reconstruction by tags) sharing the scan. Phase 1
        (context extraction) is intentionally skipped on the MCP path — run
        `mem-archeo-context` skill separately if needed. Refuses non-Git
        directories.
        """
        config = get_config()
        vault = config.vault
        repo = Path(repo_path).expanduser().resolve()

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
        phase_1_msg = (
            "Phase 1 (context) skipped on the MCP path — semantic span "
            "classification is LLM territory. Run `mem-archeo-context` "
            "skill separately if you want Phase 1 outputs (workflow / sync / "
            "multi-tenant / security / adr / goal extraction)."
        )
        warnings.append(phase_1_msg)

        return ArcheoResult(
            project=slug,
            repo_path=str(repo),
            phase_1_skipped=True,
            phase_1_message=phase_1_msg,
            stack=stack_result,
            git=git_result,
            topology_path=topology_rel_path,
            topology_outcome=topology_outcome,
            files_created=files_created,
            files_modified=files_modified,
            warnings=warnings,
            summary_md=_summary_md(slug, stack_result, git_result, topology_outcome),
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
) -> str:
    return (
        f"**mem_archeo** — {slug}\n\n"
        f"**Phase 0** (topology scan) : OK\n"
        f"**Phase 1** (context) : skipped (LLM territory — run `/mem-archeo-context` separately)\n"
        f"**Phase 2** (stack) : {getattr(stack, 'layers_resolved', 0)} layers resolved, "
        f"{getattr(stack, 'atoms_created', 0)} atoms created, "
        f"{getattr(stack, 'atoms_skipped', 0)} skipped\n"
        f"**Phase 3** (git) : {getattr(git, 'milestones_processed', 0)} tags processed, "
        f"{getattr(git, 'archives_created', 0)} archives created, "
        f"{getattr(git, 'archives_skipped', 0)} skipped\n"
        f"**Topology** : {topology_outcome}\n"
    )
