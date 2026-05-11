"""User PATH update tests — POSIX rc-file path; Windows registry stubbed."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sb_desktop import path_env


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test")
def test_posix_add_to_user_path_appends_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(path_env.Path, "home", classmethod(lambda cls: tmp_path))
    bashrc = tmp_path / ".bashrc"
    bashrc.write_text("# existing rc\nexport FOO=1\n", encoding="utf-8")

    changed = path_env.add_to_user_path_posix(tmp_path / "engine" / "Scripts")
    assert changed is True
    content = bashrc.read_text(encoding="utf-8")
    assert path_env.POSIX_MARKER_START in content
    assert "engine/Scripts" in content
    assert "FOO=1" in content  # original preserved


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test")
def test_posix_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(path_env.Path, "home", classmethod(lambda cls: tmp_path))
    bashrc = tmp_path / ".bashrc"
    bashrc.write_text("# existing\n", encoding="utf-8")
    scripts = tmp_path / "engine" / "Scripts"

    first = path_env.add_to_user_path_posix(scripts)
    second = path_env.add_to_user_path_posix(scripts)
    assert first is True
    assert second is False
    # Block appears only once.
    assert bashrc.read_text(encoding="utf-8").count(path_env.POSIX_MARKER_START) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test")
def test_posix_remove_strips_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(path_env.Path, "home", classmethod(lambda cls: tmp_path))
    bashrc = tmp_path / ".bashrc"
    bashrc.write_text("# existing\n", encoding="utf-8")
    scripts = tmp_path / "engine" / "Scripts"
    path_env.add_to_user_path_posix(scripts)
    assert path_env.remove_from_user_path_posix(scripts) is True
    assert path_env.POSIX_MARKER_START not in bashrc.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_add_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    state = {"value": "", "type": 1}

    def fake_read():
        return state["value"], state["type"]

    def fake_write(new_value: str, value_type: int):
        state["value"] = new_value
        state["type"] = value_type

    monkeypatch.setattr(path_env, "_read_user_path_windows", fake_read)
    monkeypatch.setattr(path_env, "_write_user_path_windows", fake_write)
    monkeypatch.setattr(path_env, "_broadcast_environment_change", lambda: None)

    target = tmp_path / "engine" / "Scripts"
    target.mkdir(parents=True)

    first = path_env.add_to_user_path_windows(target)
    second = path_env.add_to_user_path_windows(target)
    assert first is True
    assert second is False
    assert str(target.resolve()) in state["value"]
