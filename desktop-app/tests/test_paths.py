"""Sanity checks for the cross-platform path helpers."""

from __future__ import annotations

import pytest

from sb_desktop import paths


def test_memory_kit_config_path_uses_home(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    assert paths.memory_kit_config_path() == tmp_path / ".memory-kit" / "config.json"


def test_app_dirs_per_platform(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(paths.os.environ, "get", lambda key, default=None: None)

    monkeypatch.setattr(paths.sys, "platform", "win32")
    win_data = paths.app_data_dir()
    assert "SecondBrain" in str(win_data)
    assert win_data.name == "data"

    monkeypatch.setattr(paths.sys, "platform", "darwin")
    mac_data = paths.app_data_dir()
    assert mac_data == tmp_path / "Library" / "Application Support" / "SecondBrain"

    monkeypatch.setattr(paths.sys, "platform", "linux")
    linux_data = paths.app_data_dir()
    assert linux_data == tmp_path / ".local" / "share" / "SecondBrain"


def test_xdg_overrides_linux_paths(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(paths.sys, "platform", "linux")

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdgdata"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdgstate"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdgcache"))

    assert paths.app_data_dir() == tmp_path / "xdgdata" / "SecondBrain"
    assert paths.app_log_dir() == tmp_path / "xdgstate" / "SecondBrain" / "logs"
    assert paths.app_cache_dir() == tmp_path / "xdgcache" / "SecondBrain"
