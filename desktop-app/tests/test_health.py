"""Health scan + repair tests — engine wired via mocked mcp_client."""

from __future__ import annotations

import pytest

from sb_desktop import health
from sb_desktop.mcp_client import McpError, McpResponse, McpUnavailable


def test_scan_engine_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(health, "call_tool", lambda *a, **kw: McpUnavailable())
    report = health.scan_vault()
    assert report.ok is False
    assert "not installed" in (report.error or "")


def test_scan_engine_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        health,
        "call_tool",
        lambda *a, **kw: McpError(message="boom", detail="trace"),
    )
    report = health.scan_vault()
    assert report.ok is False
    assert report.error == "boom"


def test_scan_findings_flat_list(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "findings": [
            {"category": "missing-display", "severity": "info", "path": "a.md", "message": "m1"},
            {"category": "orphan-atoms", "severity": "warn", "path": "b.md", "message": "m2"},
        ]
    }
    monkeypatch.setattr(
        health,
        "call_tool",
        lambda *a, **kw: McpResponse(structured=payload, text="t", raw={}, elapsed_ms=10),
    )
    report = health.scan_vault()
    assert report.ok is True
    assert len(report.findings) == 2
    assert report.counts_by_category == {"missing-display": 1, "orphan-atoms": 1}
    assert report.has_findings()


def test_scan_findings_grouped_payload(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "findings_by_category": {
            "stray-zone-md": [
                {"severity": "warn", "path": "10.md", "message": "x"},
            ]
        }
    }
    monkeypatch.setattr(
        health,
        "call_tool",
        lambda *a, **kw: McpResponse(structured=payload, text="", raw={}, elapsed_ms=1),
    )
    report = health.scan_vault()
    assert report.ok
    assert report.counts_by_category == {"stray-zone-md": 1}


def test_repair_dry_run_default(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    def fake_call(tool, arguments=None, **kw):
        captured["tool"] = tool
        captured["arguments"] = arguments
        return McpResponse(
            structured={"applied": False, "fixed_count": 3, "skipped_count": 1, "fixed_paths": ["a"]},
            text="",
            raw={},
            elapsed_ms=1,
        )

    monkeypatch.setattr(health, "call_tool", fake_call)
    report = health.repair_vault()
    assert captured["arguments"] == {"apply": False}
    assert report.applied is False
    assert report.fixed_count == 3


def test_repair_apply_passes_through(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    def fake_call(tool, arguments=None, **kw):
        captured["arguments"] = arguments
        return McpResponse(
            structured={"applied": True, "fixed_count": 2, "skipped_count": 0},
            text="",
            raw={},
            elapsed_ms=1,
        )

    monkeypatch.setattr(health, "call_tool", fake_call)
    report = health.repair_vault(apply=True)
    assert captured["arguments"] == {"apply": True}
    assert report.applied is True
    assert report.fixed_count == 2
