"""Status snapshot tests — in-process model."""

from __future__ import annotations

from pathlib import Path

import pytest

from sb_desktop import status


@pytest.fixture(autouse=True)
def _reset_pipx_cache():
    """Each test starts with a clean session-level cache."""
    status.invalidate_pipx_cache()
    yield
    status.invalidate_pipx_cache()


def test_bundled_engine_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status, "_bundled_version", lambda: (None, "fake error"))
    snap = status.probe_status()
    assert snap.level == status.StatusLevel.ERROR
    assert "missing" in snap.summary.lower()


def test_pipx_absent_yields_warning(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status, "_bundled_version", lambda: ("0.12.1", None))
    monkeypatch.setattr(status, "_probe_pipx_once", lambda: (None, None))
    snap = status.probe_status()
    assert snap.level == status.StatusLevel.WARNING
    assert "not on PATH" in snap.summary
    assert snap.bundled_version == "0.12.1"


def test_venv_root_accepts_secondbrain_engine_layout(tmp_path: Path):
    """SecondBrain bundled engine has Lib/site-packages but no pyvenv.cfg."""
    engine = tmp_path / "engine"
    scripts = engine / "Scripts"
    sp = engine / "Lib" / "site-packages"
    scripts.mkdir(parents=True)
    sp.mkdir(parents=True)
    binary = scripts / "memory-kit-mcp.exe"
    binary.write_text("")
    assert status._venv_root_from_binary(binary) == engine


def test_venv_root_accepts_classic_pipx_layout(tmp_path: Path):
    venv = tmp_path / "venvs" / "memory-kit-mcp"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = ...", encoding="utf-8")
    binary = venv / "Scripts" / "memory-kit-mcp.exe"
    binary.write_text("")
    assert status._venv_root_from_binary(binary) == venv


def test_versions_aligned_yields_ok(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status, "_bundled_version", lambda: ("0.12.1", None))
    monkeypatch.setattr(
        status, "_probe_pipx_once", lambda: ("C:/x/memory-kit-mcp.exe", "0.12.1")
    )
    snap = status.probe_status()
    assert snap.level == status.StatusLevel.OK
    assert snap.versions_match is True


def test_versions_drift_yields_warning(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status, "_bundled_version", lambda: ("0.12.1", None))
    monkeypatch.setattr(
        status, "_probe_pipx_once", lambda: ("C:/x/memory-kit-mcp.exe", "0.11.0")
    )
    snap = status.probe_status()
    assert snap.level == status.StatusLevel.WARNING
    assert snap.versions_match is False
    assert "0.11" in snap.summary


def test_pipx_version_probe_failed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(status, "_bundled_version", lambda: ("0.12.1", None))
    monkeypatch.setattr(
        status, "_probe_pipx_once", lambda: ("C:/x/memory-kit-mcp.exe", None)
    )
    snap = status.probe_status()
    assert snap.level == status.StatusLevel.WARNING
    assert "--version probe failed" in snap.summary


def test_render_text_includes_all_fields():
    snap = status.StatusSnapshot(
        level=status.StatusLevel.OK,
        summary="Engine v0.12.1 ready.",
        bundled_version="0.12.1",
        pipx_binary_path=Path("C:/x/memory-kit-mcp.exe"),
        pipx_version="0.12.1",
        versions_match=True,
    )
    text = snap.render_text()
    assert "Bundled engine: v0.12.1" in text
    assert "pipx version:  v0.12.1" in text
