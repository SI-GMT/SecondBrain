"""mem_promote_domain — Promote a coherent set of items into a permanent domain.

Spec: core/procedures/mem-promote-domain.md

POC: creates a new domain folder under 10-episodes/domains/{slug}/ with
empty context.md + history.md scaffolding, then moves the listed source files
(typically inbox notes) into archives/ and re-tags their frontmatter to
attach them to the new domain.

Anti-drift guard: refuses to promote if fewer than 3 items unless
allow_2_items=True.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from memory_kit_mcp.config import get_config
from memory_kit_mcp.tools._models import ChangeReport
from memory_kit_mcp.vault import frontmatter, paths


def _build_context_scaffold(slug: str) -> tuple[dict[str, Any], str]:
    fm = {
        "domain": slug,
        "phase": "active",
        "last-session": datetime.now().date().isoformat(),
        "tags": [f"domain/{slug}", "zone/episodes", "kind/domain", "scope/work"],
        "zone": "episodes",
        "kind": "domain",
        "slug": slug,
        "scope": "work",
        "display": f"{slug} — context",
    }
    body = (
        f"> Snapshot mutable du domaine. Voir aussi : [historique](history.md) · [archives/](archives/)\n\n"
        f"# {slug} — Contexte actif\n\n"
        f"## État courant\n\n_Promoted from inbox on "
        f"{datetime.now().date().isoformat()}._\n"
    )
    return fm, body


def _build_history_scaffold(slug: str, archives: list[str]) -> tuple[dict[str, Any], str]:
    fm = {
        "domain": slug,
        "tags": [f"domain/{slug}", "zone/episodes", "kind/domain"],
        "zone": "episodes",
        "kind": "domain",
        "slug": slug,
        "display": f"{slug} — history",
    }
    lines = [
        f"> Fil chronologique du domaine. Voir aussi : [contexte](context.md)\n",
        f"# {slug} — Historique\n",
    ]
    for name in archives:
        lines.append(f"- [{name}](archives/{name})")
    return fm, "\n".join(lines) + "\n"


def register(mcp: FastMCP) -> None:
    """Register mem_promote_domain with the FastMCP instance."""

    @mcp.tool()
    def mem_promote_domain(
        slug: str = Field(..., description="Slug of the new domain (lowercase + hyphens)."),
        sources: list[str] = Field(
            ...,
            description=(
                "List of vault-relative paths to promote (typically files under "
                "00-inbox/). Files are moved to domains/{slug}/archives/ and "
                "re-tagged."
            ),
        ),
        allow_2_items: bool = Field(
            False,
            description=(
                "Bypass the anti-drift check that requires ≥3 items. Use only "
                "when you know the domain is justified by its theme."
            ),
        ),
    ) -> ChangeReport:
        """Promote a set of source files into a new permanent domain.

        Creates 10-episodes/domains/{slug}/ with context.md + history.md
        scaffolding, then moves each source file into archives/ and re-tags
        its frontmatter (`domain`, `tags`, `slug`, `kind: archive`).

        Refuses if the new slug already exists, or if fewer than 3 sources
        without allow_2_items=True.
        """
        if not sources:
            raise ValueError("At least one source file is required.")
        if len(sources) < 3 and not allow_2_items:
            raise ValueError(
                f"{len(sources)} sources is below the anti-drift threshold of 3. "
                "Pass allow_2_items=True to override (justify the theme)."
            )

        config = get_config()
        vault = config.vault

        domain_folder = paths.domain_dir(vault, slug)
        if domain_folder.exists():
            raise FileExistsError(f"Domain '{slug}' already exists at {domain_folder}.")

        archives_dir = domain_folder / "archives"
        archives_dir.mkdir(parents=True)

        moved: list[tuple[str, str]] = []
        modified: list[str] = []
        archive_filenames: list[str] = []

        for src_rel in sources:
            src = vault / src_rel
            if not src.exists():
                raise FileNotFoundError(f"Source file not found: {src}")
            target_name = src.name
            target = archives_dir / target_name
            if target.exists():
                target_name = f"{src.stem}-from-{Path(src_rel).parent.name}{src.suffix}"
                target = archives_dir / target_name

            # Patch frontmatter then move
            try:
                fm, body = frontmatter.read(src)
            except (ValueError, OSError):
                fm, body = {}, src.read_text(encoding="utf-8")
            fm["domain"] = slug
            fm["zone"] = "episodes"
            fm["kind"] = "archive"
            fm["context_origin"] = src_rel
            existing_tags = fm.get("tags") or []
            if isinstance(existing_tags, list):
                tag_set = set(existing_tags)
                tag_set.add(f"domain/{slug}")
                tag_set.add("zone/episodes")
                tag_set.add("kind/archive")
                fm["tags"] = sorted(tag_set)
            frontmatter.write(target, fm, body)
            src.unlink()
            moved.append((str(src), str(target)))
            modified.append(str(target))
            archive_filenames.append(target_name)

        # Scaffold context.md + history.md
        ctx_fm, ctx_body = _build_context_scaffold(slug)
        frontmatter.write(domain_folder / "context.md", ctx_fm, ctx_body)
        h_fm, h_body = _build_history_scaffold(slug, archive_filenames)
        frontmatter.write(domain_folder / "history.md", h_fm, h_body)

        return ChangeReport(
            skill="mem_promote_domain",
            success=True,
            files_created=[
                str(domain_folder / "context.md"),
                str(domain_folder / "history.md"),
            ],
            files_modified=modified,
            files_moved=moved,
            summary_md=(
                f"**mem_promote_domain** — `{slug}` ({len(moved)} item(s))\n\n"
                f"- Created `{domain_folder.relative_to(vault)}/` with context.md + history.md\n"
                f"- Moved & re-tagged {len(moved)} source(s) into archives/\n"
            ),
        )
