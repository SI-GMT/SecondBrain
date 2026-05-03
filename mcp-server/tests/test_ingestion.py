"""Tests for ingestion tools — mem_note, mem_principle, mem_goal, mem_person, mem, mem_doc."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.vault import frontmatter


# ---------- mem_note ----------


async def test_note_creates_atom_in_knowledge(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem_note",
        {"title": "MCP basics", "content": "JSON-RPC over stdio."},
    )
    assert res.data.success is True
    assert res.data.target_zone == "20-knowledge"
    files = list((vault_tmp / "20-knowledge").glob("mcp-basics*.md"))
    assert len(files) == 1
    fm, body = frontmatter.read(files[0])
    assert fm["kind"] == "knowledge"
    assert fm["scope"] == "work"
    assert "MCP basics" in body
    assert "JSON-RPC" in body


async def test_note_disambiguates_duplicate_titles(client: Client, vault_tmp: Path) -> None:
    await client.call_tool("mem_note", {"title": "X", "content": "first"})
    await client.call_tool("mem_note", {"title": "X", "content": "second"})
    files = sorted((vault_tmp / "20-knowledge").glob("x*.md"))
    assert len(files) == 2  # x.md + x-2.md


# ---------- mem_principle ----------


async def test_principle_creates_atom_with_force(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem_principle",
        {
            "title": "No force-push on main",
            "content": "Always merge via PR.",
            "force": "red-line",
        },
    )
    assert res.data.success is True
    files = list(
        (vault_tmp / "40-principles" / "work").glob("no-force-push-on-main*.md")
    )
    assert len(files) == 1
    fm, _ = frontmatter.read(files[0])
    assert fm["force"] == "red-line"
    assert fm["kind"] == "principle"


# ---------- mem_goal ----------


async def test_goal_creates_atom_with_horizon_and_status(
    client: Client, vault_tmp: Path
) -> None:
    res = await client.call_tool(
        "mem_goal",
        {
            "title": "Ship v0.8.0",
            "content": "MCP server live.",
            "horizon": "short",
            "deadline": "2026-06-30",
        },
    )
    assert res.data.success is True
    files = list((vault_tmp / "50-goals" / "short").glob("ship-v0-8-0*.md"))
    assert len(files) == 1
    fm, _ = frontmatter.read(files[0])
    assert fm["horizon"] == "short"
    assert fm["status"] == "open"
    assert fm["deadline"] == "2026-06-30"


# ---------- mem_person ----------


async def test_person_creates_card_under_relation(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem_person",
        {
            "name": "Jane Doe",
            "role": "Tech Lead",
            "relation": "colleague",
            "notes": "Working on the MCP migration.",
        },
    )
    assert res.data.success is True
    files = list((vault_tmp / "60-people" / "colleague").glob("jane-doe*.md"))
    assert len(files) == 1
    fm, _ = frontmatter.read(files[0])
    assert fm["name"] == "Jane Doe"
    assert fm["relation"] == "colleague"
    assert fm["sensitive"] is True


async def test_person_sensitive_can_be_disabled(client: Client, vault_tmp: Path) -> None:
    await client.call_tool(
        "mem_person",
        {"name": "Public Name", "relation": "client", "sensitive": False},
    )
    files = list((vault_tmp / "60-people" / "client").glob("public-name*.md"))
    fm, _ = frontmatter.read(files[0])
    assert fm["sensitive"] is False


# ---------- mem (router) ----------


async def test_mem_router_captures_to_inbox(client: Client, vault_tmp: Path) -> None:
    res = await client.call_tool(
        "mem", {"content": "Random thought to triage later."}
    )
    assert res.data.success is True
    assert res.data.target_zone == "00-inbox"
    files = list((vault_tmp / "00-inbox").glob("*.md"))
    assert len(files) >= 1
    fm, _ = frontmatter.read(files[0])
    assert fm["kind"] == "capture"


async def test_mem_router_records_hint(client: Client, vault_tmp: Path) -> None:
    await client.call_tool("mem", {"content": "Try X.", "hint": "idea"})
    files = list((vault_tmp / "00-inbox").glob("*.md"))
    fm, _ = frontmatter.read(files[-1])
    assert fm["hint"] == "idea"


# ---------- mem_doc ----------


async def test_doc_ingests_native_markdown(client: Client, tmp_path: Path, vault_tmp: Path) -> None:
    src = tmp_path / "external.md"
    src.write_text("# External doc\n\nSome content.\n", encoding="utf-8")
    res = await client.call_tool(
        "mem_doc", {"path": str(src), "title": "External doc"}
    )
    assert res.data.success is True
    files = list((vault_tmp / "00-inbox").glob("*-doc-external-doc*.md"))
    assert len(files) == 1
    fm, body = frontmatter.read(files[0])
    assert fm["kind"] == "doc-ingest"
    assert fm["source_format"] == "md"
    assert "External doc" in body
    assert "Some content" in body


async def test_doc_malformed_pdf_raises(
    client: Client, tmp_path: Path
) -> None:
    """A malformed/scanned PDF should raise so the LLM can fall back to native reading."""
    src = tmp_path / "report.pdf"
    src.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(ToolError):
        await client.call_tool("mem_doc", {"path": str(src)})


async def test_doc_unknown_suffix_raises(client: Client, tmp_path: Path) -> None:
    src = tmp_path / "blob.xyz"
    src.write_text("just bytes")
    with pytest.raises(ToolError):
        await client.call_tool("mem_doc", {"path": str(src)})


async def test_doc_ingests_docx_via_dispatcher(
    client: Client, tmp_path: Path, vault_tmp: Path
) -> None:
    docx_mod = pytest.importorskip("docx")
    src = tmp_path / "report.docx"
    doc = docx_mod.Document()
    doc.add_heading("Quarterly report", level=1)
    doc.add_paragraph("Body content with enough words to be meaningful.")
    doc.save(src)

    res = await client.call_tool(
        "mem_doc", {"path": str(src), "title": "Q-report"}
    )
    assert res.data.success is True
    files = list((vault_tmp / "00-inbox").glob("*-doc-q-report*.md"))
    assert len(files) == 1
    fm, body = frontmatter.read(files[0])
    assert fm["source_format"] == "docx"
    assert "# Quarterly report" in body
    assert "Body content" in body


async def test_doc_missing_path_raises(client: Client, tmp_path: Path) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_doc", {"path": str(tmp_path / "ghost.md")}
        )
