"""Status snapshot tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sb_desktop import status
from sb_desktop.engine import CommandResult


def test_static_probe_no_binary(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status, "locate_binary", lambda: None)
    snap = status.probe_status(run_live=False)
    assert snap.level == status.StatusLevel.ERROR
    assert "not installed" in snap.summary


def test_static_probe_version_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = tmp_path / "engine"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(status, "locate_binary", lambda: fake)
    monkeypatch.setattr(
        status,
        "run_engine",
        lambda *a, **kw: CommandResult(returncode=0, stdout="memory-kit-mcp 0.12.1", stderr=""),
    )
    snap = status.probe_status(run_live=False)
    assert snap.level == status.StatusLevel.OK
    assert snap.version == "0.12.1"


def test_live_probe_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = tmp_path / "engine"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(status, "locate_binary", lambda: fake)
    monkeypatch.setattr(
        status,
        "run_engine",
        lambda *a, **kw: CommandResult(returncode=0, stdout="memory-kit-mcp 0.12.1", stderr=""),
    )

    response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}).encode("utf-8") + b"\n"

    class FakeCompleted:
        returncode = 0
        stdout = response
        stderr = b""

    monkeypatch.setattr(status.subprocess, "run", lambda *a, **kw: FakeCompleted())

    snap = status.probe_status(run_live=True)
    assert snap.level == status.StatusLevel.OK
    assert snap.live_probe_ok is True


def test_live_probe_no_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = tmp_path / "engine"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(status, "locate_binary", lambda: fake)
    monkeypatch.setattr(
        status,
        "run_engine",
        lambda *a, **kw: CommandResult(returncode=0, stdout="memory-kit-mcp 0.12.1", stderr=""),
    )

    class FakeCompleted:
        returncode = 0
        stdout = b""
        stderr = b"engine crashed"

    monkeypatch.setattr(status.subprocess, "run", lambda *a, **kw: FakeCompleted())

    snap = status.probe_status(run_live=True)
    assert snap.level == status.StatusLevel.WARNING
    assert snap.live_probe_ok is False
    assert snap.error is not None
