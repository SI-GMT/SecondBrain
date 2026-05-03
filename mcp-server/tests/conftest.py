"""Pytest fixtures for the memory-kit MCP server.

Provides:
    vault_tmp — fresh copy of tests/fixtures/vault-skeleton in a tmp_path,
                with $MEMORY_KIT_HOME pointed at a matching ~/.memory-kit/.
                Cache-cleared so get_config() reloads cleanly.
    client    — fastmcp.Client wired in-memory to the FastMCP server instance,
                no subprocess, no stdio.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastmcp import Client

from memory_kit_mcp.config import get_config
from memory_kit_mcp.server import mcp

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "vault-skeleton"


@pytest.fixture
def vault_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Copy the canonical vault skeleton into a per-test tmp dir."""
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURES_DIR, vault)

    config_dir = tmp_path / ".memory-kit"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "vault": str(vault),
                "default_scope": "work",
                "language": "en",
                "kit_repo": str(tmp_path / "kit-stub"),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("MEMORY_KIT_HOME", str(config_dir))
    get_config.cache_clear()
    try:
        yield vault
    finally:
        get_config.cache_clear()


@pytest_asyncio.fixture
async def client(vault_tmp: Path) -> AsyncIterator[Client]:
    """In-memory fastmcp.Client connected directly to the FastMCP server.

    Depends on vault_tmp so $MEMORY_KIT_HOME is set before the server reads
    its config on the first tool invocation.
    """
    async with Client(mcp) as c:
        yield c
