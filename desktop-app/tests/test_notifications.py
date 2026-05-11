"""Notifications fall-through tests."""

from __future__ import annotations

import pytest

from sb_desktop import notifications


def test_notify_returns_false_when_all_backends_fail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(notifications, "_notify_via_plyer", lambda *a, **kw: False)
    monkeypatch.setattr(notifications, "_notify_via_winrt", lambda *a, **kw: False)
    monkeypatch.setattr(notifications, "_notify_via_osascript", lambda *a, **kw: False)
    monkeypatch.setattr(notifications, "_notify_via_notify_send", lambda *a, **kw: False)
    assert notifications.notify("title", "body") is False


def test_notify_uses_plyer_when_available(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def fake_plyer(title, message, app_icon):
        calls.append((title, message))
        return True

    monkeypatch.setattr(notifications, "_notify_via_plyer", fake_plyer)
    assert notifications.notify("hello", "world") is True
    assert calls == [("hello", "world")]
