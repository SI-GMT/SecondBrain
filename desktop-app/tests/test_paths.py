"""Sanity checks for the cross-platform path helpers + install-mode detection."""

from __future__ import annotations

import pytest

from sb_desktop import paths
from sb_desktop.paths import InstallMode


def test_memory_kit_config_path_uses_home(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    assert paths.memory_kit_config_path() == tmp_path / ".memory-kit" / "config.json"


def test_app_data_dir_uses_roaming_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    win_data = paths.app_data_dir()
    # Windows fallback path when %APPDATA% is unset.
    assert "Roaming" in str(win_data)
    assert win_data.name == "SecondBrain"


def test_app_data_dir_honours_appdata_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert paths.app_data_dir() == tmp_path / "Roaming" / "SecondBrain"


def test_app_dirs_per_platform(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))

    monkeypatch.setattr(paths.sys, "platform", "darwin")
    mac_data = paths.app_data_dir()
    assert mac_data == tmp_path / "Library" / "Application Support" / "SecondBrain"

    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
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


def test_detect_install_mode_system_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    pf_install = tmp_path / "Program Files" / "SecondBrain" / "app" / "Tray.exe"
    pf_install.parent.mkdir(parents=True)
    pf_install.write_text("")
    assert paths.detect_install_mode(pf_install) == InstallMode.SYSTEM


def test_detect_install_mode_user_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    user_install = tmp_path / "Local" / "SecondBrain" / "app" / "Tray.exe"
    user_install.parent.mkdir(parents=True)
    user_install.write_text("")
    assert paths.detect_install_mode(user_install) == InstallMode.USER


def test_detect_install_mode_dev_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    dev_path = tmp_path / "some" / "checkout" / "python.exe"
    dev_path.parent.mkdir(parents=True)
    dev_path.write_text("")
    assert paths.detect_install_mode(dev_path) == InstallMode.DEV


def test_engine_scripts_dirs_per_platform(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert (
        paths.system_engine_scripts_dir()
        == tmp_path / "Program Files" / "SecondBrain" / "engine" / "Scripts"
    )
    assert (
        paths.user_engine_scripts_dir()
        == tmp_path / "Local" / "SecondBrain" / "engine" / "Scripts"
    )
