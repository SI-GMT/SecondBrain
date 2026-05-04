"""Tests for mem_promote_domain."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from memory_kit_mcp.vault import frontmatter


def _seed_inbox(vault: Path, names: list[str]) -> list[str]:
    inbox = vault / "00-inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for name in names:
        p = inbox / f"{name}.md"
        frontmatter.write(p, {"slug": name, "zone": "inbox"}, f"# {name}\n")
        paths.append(f"00-inbox/{name}.md")
    return paths


async def test_promote_domain_creates_scaffold_and_moves_sources(
    client: Client, vault_tmp: Path
) -> None:
    sources = _seed_inbox(vault_tmp, ["item-a", "item-b", "item-c"])
    res = await client.call_tool(
        "mem_promote_domain",
        {"slug": "new-domain", "sources": sources},
    )
    d = res.data
    assert d.success is True
    domain_dir = vault_tmp / "10-episodes" / "domains" / "new-domain"
    assert (domain_dir / "context.md").exists()
    assert (domain_dir / "history.md").exists()
    assert (domain_dir / "archives" / "item-a.md").exists()
    # Source removed from inbox
    assert not (vault_tmp / "00-inbox" / "item-a.md").exists()
    # Frontmatter retagged
    fm, _ = frontmatter.read(domain_dir / "archives" / "item-a.md")
    assert fm["domain"] == "new-domain"
    assert fm["kind"] == "archive"
    assert "domain/new-domain" in fm["tags"]


async def test_promote_domain_refuses_2_items_without_override(
    client: Client, vault_tmp: Path
) -> None:
    sources = _seed_inbox(vault_tmp, ["only-a", "only-b"])
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_promote_domain", {"slug": "small", "sources": sources}
        )


async def test_promote_domain_allow_2_items_override(
    client: Client, vault_tmp: Path
) -> None:
    sources = _seed_inbox(vault_tmp, ["only-x", "only-y"])
    res = await client.call_tool(
        "mem_promote_domain",
        {"slug": "small-ok", "sources": sources, "allow_2_items": True},
    )
    assert res.data.success is True


async def test_promote_domain_existing_slug_raises(
    client: Client, vault_tmp: Path
) -> None:
    sources = _seed_inbox(vault_tmp, ["a", "b", "c"])
    with pytest.raises(ToolError):
        # shared-infra already exists
        await client.call_tool(
            "mem_promote_domain", {"slug": "shared-infra", "sources": sources}
        )


async def test_promote_domain_no_sources_raises(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool(
            "mem_promote_domain", {"slug": "empty", "sources": []}
        )
