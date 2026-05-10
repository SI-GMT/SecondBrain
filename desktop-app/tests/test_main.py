"""CLI entrypoint tests."""

from __future__ import annotations

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
    snap = StatusSnapshot(level=StatusLevel.OK, summary="ok", version="0.12.1")
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
