"""Tests for mem_archeo_context_finalize.

Validates that Python enforces the canonical frontmatter on every atom,
no matter what the LLM hands in. The tests reproduce the silent-malformation
bug patterns observed when a less-rigorous adapter writes Phase 1 atoms
directly: missing scope/collective/modality, missing context_origin,
missing branch, missing source_doc_hash.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client

from memory_kit_mcp.tools.archeo_context_finalize import (
    ArcheoContextSpan,
    execute_finalize,
)
from memory_kit_mcp.vault import frontmatter


# ---- Fixture: minimal repo with one source doc ----


@pytest.fixture
def repo_with_doc(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text(
        "# CLAUDE.md\n\n## Workflow\n\nFollow the process X.\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("# Project\n", encoding="utf-8")
    return repo


# ---- Universal frontmatter enforced ----


def test_finalize_writes_universal_frontmatter(
    vault_tmp: Path, repo_with_doc: Path
) -> None:
    """Every atom MUST carry scope, collective, modality, branch, source_doc_hash, context_origin."""
    spans = [
        ArcheoContextSpan(
            subject="Workflow X",
            body="Follow the process X.",
            extracted_category="workflow",
            source_doc="CLAUDE.md",
        ),
    ]
    result = execute_finalize(
        vault=vault_tmp,
        project="alpha",
        repo_path=repo_with_doc,
        scope="work",
        spans=spans,
        today="2026-05-06",
    )
    assert result.files_created == 1
    written_rel = result.spans[0].written_path
    fm, _body = frontmatter.read(vault_tmp / written_rel)
    # Universal MUST fields
    assert fm["scope"] == "work"
    assert fm["collective"] is False
    assert fm["modality"] == "left"
    # Archeo MUST fields
    assert fm["source"] == "archeo-context"
    assert fm["source_doc"] == "CLAUDE.md"
    assert "source_doc_hash" in fm and len(fm["source_doc_hash"]) == 64
    assert fm["extracted_category"] == "workflow"
    assert fm["project"] == "alpha"
    assert fm["context_origin"] == "[[99-meta/repo-topology/alpha]]"
    assert fm["branch"] == ""  # empty string — never null/missing
    assert fm["previous_atom"] == ""
    assert "content_hash" in fm and len(fm["content_hash"]) == 64
    assert "display" in fm
    # Tag mirror
    assert "scope/work" in fm["tags"]
    assert "modality/left" in fm["tags"]
    assert "category/workflow" in fm["tags"]
    assert "project/alpha" in fm["tags"]


def test_finalize_routes_per_category(
    vault_tmp: Path, repo_with_doc: Path
) -> None:
    """Each category lands in the right zone."""
    spans = [
        ArcheoContextSpan(subject="W1", body="b", extracted_category="workflow",
                          source_doc="CLAUDE.md"),
        ArcheoContextSpan(subject="S1", body="b", extracted_category="security",
                          source_doc="CLAUDE.md"),
        ArcheoContextSpan(subject="A1", body="b", extracted_category="adr",
                          source_doc="CLAUDE.md"),
        ArcheoContextSpan(subject="G1", body="b", extracted_category="goal",
                          source_doc="CLAUDE.md"),
        ArcheoContextSpan(subject="K1", body="b", extracted_category="multi-tenant",
                          source_doc="CLAUDE.md"),
    ]
    result = execute_finalize(
        vault=vault_tmp, project="alpha", repo_path=repo_with_doc,
        scope="work", spans=spans, today="2026-05-06",
    )
    paths = {s.span_subject: s.written_path for s in result.spans}
    assert "40-principles/work/methodology" in paths["W1"]
    assert "40-principles/work/security" in paths["S1"]
    assert "20-knowledge/architecture/decisions" in paths["A1"]
    assert "50-goals/work/projects/alpha" in paths["G1"]
    assert "20-knowledge/architecture" in paths["K1"]


def test_finalize_principles_carry_force(
    vault_tmp: Path, repo_with_doc: Path
) -> None:
    """Workflow defaults to preference; security defaults to red-line; LLM may override."""
    spans = [
        ArcheoContextSpan(subject="W1", body="b", extracted_category="workflow",
                          source_doc="CLAUDE.md"),
        ArcheoContextSpan(subject="W2-strict", body="b", extracted_category="workflow",
                          source_doc="CLAUDE.md", force="red-line"),
        ArcheoContextSpan(subject="S1", body="b", extracted_category="security",
                          source_doc="CLAUDE.md"),
    ]
    result = execute_finalize(
        vault=vault_tmp, project="alpha", repo_path=repo_with_doc,
        scope="work", spans=spans, today="2026-05-06",
    )
    written = {s.span_subject: vault_tmp / s.written_path for s in result.spans}
    fm_w1, _ = frontmatter.read(written["W1"])
    fm_w2, _ = frontmatter.read(written["W2-strict"])
    fm_s1, _ = frontmatter.read(written["S1"])
    assert fm_w1["force"] == "preference"
    assert fm_w2["force"] == "red-line"  # LLM override respected
    assert fm_s1["force"] == "red-line"
    assert "force/preference" in fm_w1["tags"]
    assert "force/red-line" in fm_w2["tags"]
    assert "force/red-line" in fm_s1["tags"]


def test_finalize_goals_carry_horizon_and_status(
    vault_tmp: Path, repo_with_doc: Path
) -> None:
    spans = [
        ArcheoContextSpan(subject="G default", body="b", extracted_category="goal",
                          source_doc="CLAUDE.md"),
        ArcheoContextSpan(subject="G long term", body="b", extracted_category="goal",
                          source_doc="CLAUDE.md", horizon="long", status="in-progress"),
    ]
    result = execute_finalize(
        vault=vault_tmp, project="alpha", repo_path=repo_with_doc,
        scope="work", spans=spans, today="2026-05-06",
    )
    written = {s.span_subject: vault_tmp / s.written_path for s in result.spans}
    fm_def, _ = frontmatter.read(written["G default"])
    fm_long, _ = frontmatter.read(written["G long term"])
    assert fm_def["horizon"] == "medium"
    assert fm_def["status"] == "open"
    assert fm_long["horizon"] == "long"
    assert fm_long["status"] == "in-progress"
    assert "horizon/long" in fm_long["tags"]
    assert "status/in-progress" in fm_long["tags"]


# ---- Idempotence ----


def test_finalize_idempotent_on_unchanged_body(
    vault_tmp: Path, repo_with_doc: Path
) -> None:
    spans = [
        ArcheoContextSpan(subject="W1", body="same body",
                          extracted_category="workflow", source_doc="CLAUDE.md"),
    ]
    r1 = execute_finalize(vault=vault_tmp, project="alpha",
                          repo_path=repo_with_doc, scope="work",
                          spans=spans, today="2026-05-06")
    assert r1.files_created == 1
    r2 = execute_finalize(vault=vault_tmp, project="alpha",
                          repo_path=repo_with_doc, scope="work",
                          spans=spans, today="2026-05-06")
    assert r2.files_created == 0
    assert r2.files_skipped == 1
    assert r2.spans[0].outcome == "skipped"


def test_finalize_revises_on_changed_body(
    vault_tmp: Path, repo_with_doc: Path
) -> None:
    spans1 = [
        ArcheoContextSpan(subject="W1", body="version 1",
                          extracted_category="workflow", source_doc="CLAUDE.md"),
    ]
    execute_finalize(vault=vault_tmp, project="alpha", repo_path=repo_with_doc,
                     scope="work", spans=spans1, today="2026-05-06")
    spans2 = [
        ArcheoContextSpan(subject="W1", body="version 2 (changed)",
                          extracted_category="workflow", source_doc="CLAUDE.md"),
    ]
    r2 = execute_finalize(vault=vault_tmp, project="alpha",
                          repo_path=repo_with_doc, scope="work",
                          spans=spans2, today="2026-05-06")
    assert r2.files_revised == 1
    fm, _ = frontmatter.read(vault_tmp / r2.spans[0].written_path)
    assert fm["previous_atom"].startswith("[[")


# ---- Rejection paths ----


def test_finalize_rejects_invalid_category(
    vault_tmp: Path, repo_with_doc: Path
) -> None:
    spans = [
        ArcheoContextSpan(subject="bad", body="b",
                          extracted_category="not-a-category",
                          source_doc="CLAUDE.md"),
    ]
    result = execute_finalize(vault=vault_tmp, project="alpha",
                              repo_path=repo_with_doc, scope="work",
                              spans=spans, today="2026-05-06")
    assert result.files_rejected == 1
    assert result.spans[0].outcome == "rejected"
    assert "invalid extracted_category" in result.spans[0].reason


def test_finalize_rejects_missing_source_doc(
    vault_tmp: Path, repo_with_doc: Path
) -> None:
    spans = [
        ArcheoContextSpan(subject="ghost", body="b",
                          extracted_category="workflow",
                          source_doc="does-not-exist.md"),
    ]
    result = execute_finalize(vault=vault_tmp, project="alpha",
                              repo_path=repo_with_doc, scope="work",
                              spans=spans, today="2026-05-06")
    assert result.files_rejected == 1
    assert "source_doc unreadable" in result.spans[0].reason


# ---- MCP integration ----


async def test_finalize_via_mcp_client(
    client: Client, vault_tmp: Path, tmp_path: Path
) -> None:
    """Smoke test: invoke through the MCP transport."""
    repo = tmp_path / "repo-mcp"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("# C\n", encoding="utf-8")
    res = await client.call_tool(
        "mem_archeo_context_finalize",
        {
            "project": "alpha",
            "repo_path": str(repo),
            "scope": "work",
            "today": "2026-05-06",
            "spans": [
                {
                    "subject": "via MCP",
                    "body": "smoke test",
                    "extracted_category": "workflow",
                    "source_doc": "CLAUDE.md",
                },
            ],
        },
    )
    assert res.data.files_created == 1
    written = vault_tmp / res.data.spans[0].written_path
    fm, _ = frontmatter.read(written)
    # All universal MUST fields present
    for field in ("scope", "collective", "modality", "branch",
                  "source_doc_hash", "context_origin"):
        assert field in fm, f"missing universal MUST field: {field}"
