"""MCP stdio client tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sb_desktop import mcp_client


class _FakeCompleted:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _build_responses() -> bytes:
    init = {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}
    call = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "content": [{"type": "text", "text": "All good."}],
            "structuredContent": {"answer": 42},
        },
    }
    return (json.dumps(init) + "\n" + json.dumps(call) + "\n").encode("utf-8")


def test_call_tool_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mcp_client, "locate_binary", lambda: None)
    response = mcp_client.call_tool("anything")
    assert isinstance(response, mcp_client.McpUnavailable)


def test_call_tool_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_bin = tmp_path / "engine"
    fake_bin.write_text("", encoding="utf-8")
    monkeypatch.setattr(mcp_client, "locate_binary", lambda: fake_bin)
    monkeypatch.setattr(
        mcp_client.subprocess,
        "run",
        lambda *a, **kw: _FakeCompleted(stdout=_build_responses()),
    )

    response = mcp_client.call_tool("mem_check_update", {"force_refresh": False})
    assert isinstance(response, mcp_client.McpResponse)
    assert response.text == "All good."
    assert response.structured == {"answer": 42}


def test_call_tool_transport_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_bin = tmp_path / "engine"
    fake_bin.write_text("", encoding="utf-8")
    monkeypatch.setattr(mcp_client, "locate_binary", lambda: fake_bin)
    monkeypatch.setattr(
        mcp_client.subprocess,
        "run",
        lambda *a, **kw: _FakeCompleted(stderr=b"boom", returncode=1),
    )

    response = mcp_client.call_tool("mem_check_update")
    assert isinstance(response, mcp_client.McpError)
    assert response.transport is True


def test_call_tool_tool_level_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_bin = tmp_path / "engine"
    fake_bin.write_text("", encoding="utf-8")
    monkeypatch.setattr(mcp_client, "locate_binary", lambda: fake_bin)

    init = {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}
    call = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "isError": True,
            "content": [{"type": "text", "text": "tool exploded"}],
        },
    }
    payload = (json.dumps(init) + "\n" + json.dumps(call) + "\n").encode("utf-8")
    monkeypatch.setattr(
        mcp_client.subprocess,
        "run",
        lambda *a, **kw: _FakeCompleted(stdout=payload),
    )

    response = mcp_client.call_tool("mem_health_repair")
    assert isinstance(response, mcp_client.McpError)
    assert response.transport is False
    assert "exploded" in (response.detail or "")


def test_call_tool_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_bin = tmp_path / "engine"
    fake_bin.write_text("", encoding="utf-8")
    monkeypatch.setattr(mcp_client, "locate_binary", lambda: fake_bin)

    def _raise(*_a, **_kw):
        raise mcp_client.subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(mcp_client.subprocess, "run", _raise)
    response = mcp_client.call_tool("mem_health_scan", timeout=1)
    assert isinstance(response, mcp_client.McpError)
    assert "timed out" in response.message
