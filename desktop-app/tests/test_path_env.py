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


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test")
def test_posix_symlink_into_user_local_bin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(path_env.Path, "home", classmethod(lambda cls: tmp_path))
    # Real binary on disk.
    scripts = tmp_path / "engine" / "Scripts"
    scripts.mkdir(parents=True)
    binary = scripts / "memory-kit-mcp"
    binary.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    binary.chmod(0o755)

    changed = path_env.add_to_user_path_posix(scripts, binary=binary)
    link = tmp_path / ".local" / "bin" / "memory-kit-mcp"
    assert changed is True
    assert link.is_symlink()
    assert link.resolve() == binary.resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test")
def test_posix_symlink_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(path_env.Path, "home", classmethod(lambda cls: tmp_path))
    scripts = tmp_path / "engine" / "Scripts"
    scripts.mkdir(parents=True)
    binary = scripts / "memory-kit-mcp"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")

    first = path_env.add_to_user_path_posix(scripts, binary=binary)
    second = path_env.add_to_user_path_posix(scripts, binary=binary)
    assert first is True
    # Second call: symlink unchanged AND rc block already up-to-date.
    assert second is False


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test")
def test_posix_symlink_repoints_when_source_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(path_env.Path, "home", classmethod(lambda cls: tmp_path))
    old = tmp_path / "old" / "memory-kit-mcp"
    new = tmp_path / "new" / "memory-kit-mcp"
    old.parent.mkdir(parents=True)
    new.parent.mkdir(parents=True)
    old.write_text("#!/bin/sh\n")
    new.write_text("#!/bin/sh\n")

    link = tmp_path / ".local" / "bin" / "memory-kit-mcp"
    assert path_env.ensure_symlink(old, link) is True
    assert path_env.ensure_symlink(new, link) is True
    assert link.resolve() == new.resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test")
def test_posix_remove_symlink_only_when_ours(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(path_env.Path, "home", classmethod(lambda cls: tmp_path))
    ours = tmp_path / "ours" / "memory-kit-mcp"
    theirs = tmp_path / "theirs" / "memory-kit-mcp"
    ours.parent.mkdir(parents=True)
    theirs.parent.mkdir(parents=True)
    ours.write_text("#!/bin/sh\n")
    theirs.write_text("#!/bin/sh\n")

    link = tmp_path / ".local" / "bin" / "memory-kit-mcp"
    link.parent.mkdir(parents=True)
    link.symlink_to(theirs)
    # Trying to remove "ours" when the link points to theirs → no-op.
    assert path_env.remove_symlink_if_ours(link, ours) is False
    assert link.is_symlink()
    # Pointing the right source removes the link.
    assert path_env.remove_symlink_if_ours(link, theirs) is True
    assert not link.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test")
def test_posix_ensure_symlink_refuses_real_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(path_env.Path, "home", classmethod(lambda cls: tmp_path))
    source = tmp_path / "engine" / "memory-kit-mcp"
    source.parent.mkdir(parents=True)
    source.write_text("#!/bin/sh\n")
    link = tmp_path / ".local" / "bin" / "memory-kit-mcp"
    link.parent.mkdir(parents=True)
    link.write_text("real file content")  # not a symlink
    with pytest.raises(FileExistsError):
        path_env.ensure_symlink(source, link)


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
