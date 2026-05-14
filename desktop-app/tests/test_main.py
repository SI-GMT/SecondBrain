"""CLI entrypoint tests."""

from __future__ import annotations

import sys
import types

import pytest

from sb_desktop import __main__ as main
from sb_desktop.status import StatusLevel, StatusSnapshot


def test_version_exits_zero(capsys: pytest.CaptureFixture):
    with pytest.raises(SystemExit) as exc_info:
        main.main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "sb-desktop" in captured.out


def test_healthcheck_ok(monkeypatch: pytest.MonkeyPatch):
    snap = StatusSnapshot(level=StatusLevel.OK, summary="ok", bundled_version="0.12.1")
    monkeypatch.setattr("sb_desktop.status.probe_status", lambda *a, **kw: snap)
    rc = main.main(["--healthcheck"])
    assert rc == 0


def test_headless_status_action(monkeypatch: pytest.MonkeyPatch):
    snap = StatusSnapshot(level=StatusLevel.OK, summary="ok")
    monkeypatch.setattr("sb_desktop.status.probe_status", lambda *a, **kw: snap)
    rc = main.main(["--no-tray", "--action", "status"])
    assert rc == 0


def test_no_tray_without_action_returns_zero(monkeypatch: pytest.MonkeyPatch):
    rc = main.main(["--no-tray"])
    assert rc == 0


def test_missing_kit_runs_first_run_in_helper(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str | None]] = []
    fake_tray = types.ModuleType("sb_desktop.tray")
    fake_tray.run_tray = lambda: 0

    monkeypatch.setattr("sb_desktop.config.load_kit_config", lambda: None)
    monkeypatch.setattr(
        main,
        "_run_dialog_helper",
        lambda dialog, *, log_level=None: calls.append((dialog, log_level)) or 0,
    )
    monkeypatch.setitem(sys.modules, "sb_desktop.tray", fake_tray)

    rc = main.main([])

    assert rc == 0
    assert calls == [("wizard", "INFO")]


def test_skip_first_run_does_not_launch_helper(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    fake_tray = types.ModuleType("sb_desktop.tray")
    fake_tray.run_tray = lambda: 0

    monkeypatch.setattr("sb_desktop.config.load_kit_config", lambda: None)
    monkeypatch.setattr(
        main,
        "_run_dialog_helper",
        lambda dialog, *, log_level=None: calls.append(dialog) or 0,
    )
    monkeypatch.setitem(sys.modules, "sb_desktop.tray", fake_tray)

    rc = main.main(["--skip-first-run"])

    assert rc == 0
    assert calls == []
