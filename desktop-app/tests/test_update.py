"""Update flow tests — check + plan + run with subprocess mocked."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sb_desktop import update
from sb_desktop.config import KitConfig
from sb_desktop.mcp_client import McpError, McpResponse, McpUnavailable


def test_check_update_engine_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(update, "call_tool", lambda *a, **kw: McpUnavailable())
    result = update.check_update()
    assert result.ok is False


def test_check_update_returns_payload(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "update_available": True,
        "current_version": "0.12.0",
        "latest_version": "0.12.1",
        "last_checked_iso": "2026-05-10T12:00:00+00:00",
    }
    monkeypatch.setattr(
        update,
        "call_tool",
        lambda *a, **kw: McpResponse(structured=payload, text="md", raw={}, elapsed_ms=1),
    )
    result = update.check_update()
    assert result.ok
    assert result.update_available
    assert result.current_version == "0.12.0"


def test_plan_update_missing_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(update, "load_kit_config", lambda: None)
    plan = update.plan_update()
    assert plan.can_run is False
    assert "kit_repo" in (plan.blocker or "")


def test_plan_update_resolves_script(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    repo = tmp_path / "kit"
    repo.mkdir()
    script_name = "deploy.ps1" if sys.platform == "win32" else "deploy.sh"
    (repo / script_name).write_text("# deploy", encoding="utf-8")

    monkeypatch.setattr(
        update,
        "load_kit_config",
        lambda: KitConfig(vault=repo, language="en", kit_repo=repo),
    )
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/usr/bin/{name}")

    plan = update.plan_update()
    assert plan.can_run is True
    assert plan.deploy_script is not None
    assert plan.deploy_script.name == script_name


def test_run_update_refuses_without_confirmation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    repo = tmp_path / "kit"
    repo.mkdir()
    script_name = "deploy.ps1" if sys.platform == "win32" else "deploy.sh"
    (repo / script_name).write_text("# deploy", encoding="utf-8")
    monkeypatch.setattr(
        update,
        "load_kit_config",
        lambda: KitConfig(vault=repo, language="en", kit_repo=repo),
    )
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/usr/bin/{name}")

    result = update.run_update(confirmed=False)
    assert result.ok is False
    assert result.confirmed is False


def test_run_update_invokes_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    repo = tmp_path / "kit"
    repo.mkdir()
    script_name = "deploy.ps1" if sys.platform == "win32" else "deploy.sh"
    (repo / script_name).write_text("# deploy", encoding="utf-8")
    monkeypatch.setattr(
        update,
        "load_kit_config",
        lambda: KitConfig(vault=repo, language="en", kit_repo=repo),
    )
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/usr/bin/{name}")

    captured = {}

    class FakeCompleted:
        returncode = 0
        stdout = "deploy ok"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeCompleted()

    monkeypatch.setattr(update.subprocess, "run", fake_run)

    result = update.run_update(confirmed=True)
    assert result.ok is True
    assert "deploy" in (captured["cmd"][-2] if sys.platform == "win32" else captured["cmd"][-2])
