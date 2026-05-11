"""MCP config injection tests — JSON, TOML, TOML-array variants."""

from __future__ import annotations

import json
from pathlib import Path

from sb_desktop import mcp_injector
from sb_desktop.mcp_injector import InjectStatus


def test_inject_json_creates_file(tmp_path: Path):
    target = tmp_path / "settings.json"
    result = mcp_injector.inject_json_mcp_server(target, target_label="Test")
    assert result.status == InjectStatus.CREATED
    assert target.is_file()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert data["mcpServers"][mcp_injector.DEFAULT_SERVER_NAME]["command"] == "memory-kit-mcp"


def test_inject_json_unchanged_when_already_present(tmp_path: Path):
    target = tmp_path / "settings.json"
    mcp_injector.inject_json_mcp_server(target, target_label="Test")
    second = mcp_injector.inject_json_mcp_server(target, target_label="Test")
    assert second.status == InjectStatus.UNCHANGED


def test_inject_json_purges_legacy_name(tmp_path: Path):
    target = tmp_path / "settings.json"
    target.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "memory-kit": {"command": "memory-kit-mcp", "args": []},
                }
            }
        ),
        encoding="utf-8",
    )
    result = mcp_injector.inject_json_mcp_server(target, target_label="Test")
    assert result.ok
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "memory-kit" not in data["mcpServers"]
    assert mcp_injector.DEFAULT_SERVER_NAME in data["mcpServers"]


def test_inject_json_updates_command_drift(tmp_path: Path):
    target = tmp_path / "settings.json"
    target.write_text(
        json.dumps(
            {
                "mcpServers": {
                    mcp_injector.DEFAULT_SERVER_NAME: {
                        "command": "wrong-command",
                        "args": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    result = mcp_injector.inject_json_mcp_server(target, target_label="Test")
    assert result.status == InjectStatus.UPDATED
    data = json.loads(target.read_text(encoding="utf-8"))
    assert (
        data["mcpServers"][mcp_injector.DEFAULT_SERVER_NAME]["command"]
        == "memory-kit-mcp"
    )


def test_inject_codex_creates_block(tmp_path: Path):
    target = tmp_path / "config.toml"
    result = mcp_injector.inject_codex_mcp_server(target)
    assert result.status == InjectStatus.CREATED
    content = target.read_text(encoding="utf-8")
    assert mcp_injector.START_MARKER in content
    assert "[mcp_servers." in content
    assert "memory-kit-mcp" in content


def test_inject_codex_updates_in_place(tmp_path: Path):
    target = tmp_path / "config.toml"
    target.write_text(
        f"# other config\n[other]\nfoo = 1\n\n{mcp_injector.START_MARKER}\n"
        f"[mcp_servers.secondbrain-memory-kit]\n"
        f'command = "wrong"\n'
        f"args = []\n"
        f"{mcp_injector.END_MARKER}\n",
        encoding="utf-8",
    )
    result = mcp_injector.inject_codex_mcp_server(target)
    assert result.status == InjectStatus.UPDATED
    content = target.read_text(encoding="utf-8")
    assert 'command = "memory-kit-mcp"' in content
    assert "[other]" in content  # unrelated content preserved


def test_inject_codex_purges_orphan(tmp_path: Path):
    target = tmp_path / "config.toml"
    target.write_text(
        "[mcp_servers.secondbrain-memory-kit]\n"
        'command = "old"\n'
        "args = []\n",
        encoding="utf-8",
    )
    result = mcp_injector.inject_codex_mcp_server(target)
    assert result.status == InjectStatus.PURGED_ORPHAN
    content = target.read_text(encoding="utf-8")
    # Only one [mcp_servers.secondbrain-memory-kit] section.
    assert content.count("[mcp_servers.secondbrain-memory-kit]") == 1
    assert 'command = "memory-kit-mcp"' in content


def test_inject_vibe_creates_array_entry(tmp_path: Path):
    target = tmp_path / "config.toml"
    result = mcp_injector.inject_vibe_mcp_server(target)
    assert result.status == InjectStatus.CREATED
    content = target.read_text(encoding="utf-8")
    assert "[[mcp_servers]]" in content
    assert 'name = "secondbrain-memory-kit"' in content


def test_inject_vibe_updates_block(tmp_path: Path):
    target = tmp_path / "config.toml"
    mcp_injector.inject_vibe_mcp_server(target)
    # Re-running with same content = unchanged.
    second = mcp_injector.inject_vibe_mcp_server(target)
    assert second.status == InjectStatus.UNCHANGED


def test_write_kit_config(tmp_path: Path):
    target = tmp_path / "config.json"
    written = mcp_injector.write_kit_config(
        vault=tmp_path / "vault",
        kit_repo=tmp_path / "kit",
        language="fr",
        config_path=target,
    )
    assert written == target
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["vault"] == str(tmp_path / "vault")
    assert data["language"] == "fr"
    assert data["kit_repo"] == str(tmp_path / "kit")


def test_inject_json_unreadable_file(tmp_path: Path):
    target = tmp_path / "broken.json"
    target.write_text("not valid json", encoding="utf-8")
    result = mcp_injector.inject_json_mcp_server(target, target_label="Test")
    assert result.status == InjectStatus.SKIPPED
    assert "unreadable" in result.detail
