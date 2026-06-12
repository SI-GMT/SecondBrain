"""Tests for the cross-platform autostart backends."""

from __future__ import annotations

from pathlib import Path

import pytest

from sb_desktop import autostart


# ---------------------------------------------------------------------------
# Linux (XDG) backend — pure filesystem, runs on any platform
# ---------------------------------------------------------------------------


def test_linux_write_read_remove_cycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    target = tmp_path / "autostart" / autostart.LINUX_AUTOSTART_FILENAME
    monkeypatch.setattr(autostart, "_linux_autostart_path", lambda: target)

    assert autostart._linux_read() is False
    assert autostart._linux_write(Path("/usr/bin/tray")) is True
    assert target.is_file()
    content = target.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content and "Exec=" in content and "tray" in content
    assert autostart._linux_read() is True
    assert autostart._linux_remove() is True
    assert target.exists() is False
    # Removing an already-absent entry is a no-op success.
    assert autostart._linux_remove() is True


def test_linux_autostart_path_honours_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    p = autostart._linux_autostart_path()
    assert p == tmp_path / "autostart" / autostart.LINUX_AUTOSTART_FILENAME


# ---------------------------------------------------------------------------
# macOS backend — filesystem + launchctl (stubbed)
# ---------------------------------------------------------------------------


def test_macos_write_read_remove_cycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    plist = tmp_path / "LaunchAgents" / f"{autostart.MACOS_PLIST_LABEL}.plist"
    monkeypatch.setattr(autostart, "_macos_plist_path", lambda: plist)
    monkeypatch.setattr(autostart.shutil, "which", lambda name: None)

    assert autostart._macos_read() is False
    assert autostart._macos_write(Path("/Applications/Tray.app")) is True
    assert plist.is_file()
    assert autostart.MACOS_PLIST_LABEL in plist.read_text(encoding="utf-8")
    assert autostart._macos_read() is True
    assert autostart._macos_remove() is True
    assert plist.exists() is False
    assert autostart._macos_remove() is True  # already gone


def test_macos_write_invokes_launchctl_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    plist = tmp_path / "LaunchAgents" / f"{autostart.MACOS_PLIST_LABEL}.plist"
    monkeypatch.setattr(autostart, "_macos_plist_path", lambda: plist)
    monkeypatch.setattr(autostart.shutil, "which", lambda name: "/bin/launchctl")
    calls: list = []
    monkeypatch.setattr(
        autostart.subprocess, "run", lambda *a, **k: calls.append(a) or None
    )
    assert autostart._macos_write(Path("/Applications/Tray.app")) is True
    assert calls  # launchctl load attempted


# ---------------------------------------------------------------------------
# Windows backend — in-memory fake winreg
# ---------------------------------------------------------------------------


class _FakeKey:
    def __init__(self, store: dict):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 3

    def __init__(self):
        self.data: dict[str, dict] = {}

    def OpenKey(self, root, sub, idx, access):
        if sub not in self.data:
            raise FileNotFoundError(sub)
        return _FakeKey(self.data[sub])

    def CreateKey(self, root, sub):
        self.data.setdefault(sub, {})
        return _FakeKey(self.data[sub])

    def QueryValueEx(self, key, name):
        if name not in key.store:
            raise FileNotFoundError(name)
        return key.store[name], self.REG_SZ

    def SetValueEx(self, key, name, idx, typ, value):
        key.store[name] = value

    def DeleteValue(self, key, name):
        if name not in key.store:
            raise FileNotFoundError(name)
        del key.store[name]


@pytest.fixture
def fake_winreg(monkeypatch: pytest.MonkeyPatch) -> _FakeWinreg:
    fake = _FakeWinreg()
    monkeypatch.setitem(__import__("sys").modules, "winreg", fake)
    return fake


def test_windows_write_then_read(fake_winreg: _FakeWinreg):
    assert autostart._windows_read() is False  # key absent
    assert autostart._windows_write(Path(r"C:\app\Tray.exe")) is True
    assert autostart._windows_read() is True
    stored = fake_winreg.data[autostart.WINDOWS_RUN_KEY][autostart.WINDOWS_VALUE_NAME]
    assert stored == r'"C:\app\Tray.exe"'


def test_windows_remove(fake_winreg: _FakeWinreg):
    autostart._windows_write(Path(r"C:\app\Tray.exe"))
    assert autostart._windows_remove() is True
    assert autostart._windows_read() is False
    # Removing an absent value still succeeds (inner FileNotFoundError).
    assert autostart._windows_remove() is True


# ---------------------------------------------------------------------------
# Platform dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "platform,backend",
    [("win32", "_windows_read"), ("darwin", "_macos_read"), ("linux", "_linux_read")],
)
def test_is_enabled_dispatch(monkeypatch: pytest.MonkeyPatch, platform, backend):
    monkeypatch.setattr(autostart.sys, "platform", platform)
    monkeypatch.setattr(autostart, backend, lambda: True)
    assert autostart.is_autostart_enabled() is True


@pytest.mark.parametrize(
    "platform,backend",
    [("win32", "_windows_write"), ("darwin", "_macos_write"), ("linux", "_linux_write")],
)
def test_enable_dispatch(monkeypatch: pytest.MonkeyPatch, platform, backend):
    monkeypatch.setattr(autostart.sys, "platform", platform)
    monkeypatch.setattr(autostart, backend, lambda exe: True)
    monkeypatch.setattr(autostart, "_tray_executable", lambda: Path("/x"))
    assert autostart.enable_autostart() is True


@pytest.mark.parametrize(
    "platform,backend",
    [("win32", "_windows_remove"), ("darwin", "_macos_remove"), ("linux", "_linux_remove")],
)
def test_disable_dispatch(monkeypatch: pytest.MonkeyPatch, platform, backend):
    monkeypatch.setattr(autostart.sys, "platform", platform)
    monkeypatch.setattr(autostart, backend, lambda: True)
    assert autostart.disable_autostart() is True
