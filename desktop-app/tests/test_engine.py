"""Engine binary locator tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from sb_desktop import engine


def test_locate_binary_via_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = tmp_path / "memory-kit-mcp"
    fake.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    monkeypatch.setenv(engine.ENV_OVERRIDE, str(fake))
    assert engine.locate_binary() == fake


def test_locate_binary_env_override_missing_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(engine.ENV_OVERRIDE, str(tmp_path / "does-not-exist"))
    monkeypatch.setattr(engine.shutil, "which", lambda _name: None)
    monkeypatch.setattr(engine, "_candidate_pipx_paths", lambda: [])
    assert engine.locate_binary() is None


def test_locate_binary_via_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = tmp_path / "memory-kit-mcp"
    fake.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    monkeypatch.delenv(engine.ENV_OVERRIDE, raising=False)
    monkeypatch.setattr(engine.shutil, "which", lambda _name: str(fake))
    assert engine.locate_binary() == fake


def test_run_engine_returns_none_when_binary_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(engine, "locate_binary", lambda: None)
    assert engine.run_engine(["--version"]) is None


def test_run_engine_captures_subprocess_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fake = tmp_path / "engine"
    monkeypatch.setattr(engine, "locate_binary", lambda: fake)

    class FakeCompleted:
        returncode = 0
        stdout = "memory-kit-mcp 0.12.1"
        stderr = ""

    monkeypatch.setattr(engine.subprocess, "run", lambda *a, **kw: FakeCompleted())
    result = engine.run_engine(["--version"])
    assert result is not None
    assert result.ok
    assert "0.12.1" in result.stdout
