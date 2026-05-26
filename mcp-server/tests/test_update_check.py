"""Tests for memory_kit_mcp.update_check + the mem_check_update MCP tool."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastmcp import Client

from memory_kit_mcp import update_check
from memory_kit_mcp.update_check import (
    UpdateInfo,
    _is_newer,
    _parse_version,
    check_for_update,
    emit_update_log,
)


# ---- Pure helpers ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0.10.0", (0, 10, 0)),
        ("v0.10.0", (0, 10, 0)),
        ("  v0.9.7 ", (0, 9, 7)),
        ("0.10.1-rc1", (0, 10, 1)),
        ("0.10", (0, 10)),
        ("", ()),
    ],
)
def test_parse_version(raw: str, expected: tuple[int, ...]) -> None:
    assert _parse_version(raw) == expected


@pytest.mark.parametrize(
    "remote, local, expected",
    [
        ("v0.10.1", "0.10.0", True),
        ("v0.10.0", "0.9.7", True),
        ("v1.0.0", "0.99.99", True),
        ("v0.10.0", "0.10.0", False),
        ("v0.9.7", "0.10.0", False),
        ("v0.10.0", "0.11.0-dev", False),  # local ahead of remote
    ],
)
def test_is_newer(remote: str, local: str, expected: bool) -> None:
    assert _is_newer(remote, local) is expected


# ---- check_for_update — happy paths --------------------------------------


def _mock_urlopen_factory(payload: dict[str, Any]) -> Any:
    """Return a callable suitable for monkeypatching urllib.request.urlopen."""

    def _fake_urlopen(req, timeout=None):  # noqa: ARG001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "releases?per_page=" in url or ("/releases" in url and not url.endswith("/latest")):
            data = [payload]
        else:
            data = payload
        cm = MagicMock()
        cm.__enter__ = lambda self: self
        cm.__exit__ = lambda self, *a: None
        cm.read = lambda: json.dumps(data).encode("utf-8")
        return cm

    return _fake_urlopen


def test_check_for_update_flags_remote_newer(
    monkeypatch: pytest.MonkeyPatch, vault_tmp
) -> None:
    monkeypatch.setattr(update_check, "__version__", "0.10.0")
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        _mock_urlopen_factory({"tag_name": "v0.11.0"}),
    )

    info = check_for_update(force_refresh=True)

    assert info.current_version == "0.10.0"
    assert info.latest_version == "0.11.0"
    assert info.update_available is True
    assert info.error is None


def test_check_for_update_no_update_when_equal(
    monkeypatch: pytest.MonkeyPatch, vault_tmp
) -> None:
    monkeypatch.setattr(update_check, "__version__", "0.10.0")
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        _mock_urlopen_factory({"tag_name": "v0.10.0"}),
    )

    info = check_for_update(force_refresh=True)

    assert info.update_available is False
    assert info.latest_version == "0.10.0"
    assert info.error is None


def test_check_for_update_no_update_when_local_ahead(
    monkeypatch: pytest.MonkeyPatch, vault_tmp
) -> None:
    """Dev case: local version > latest tag (e.g., on a feature branch)."""
    monkeypatch.setattr(update_check, "__version__", "0.11.0")
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        _mock_urlopen_factory({"tag_name": "v0.10.0"}),
    )

    info = check_for_update(force_refresh=True)

    assert info.update_available is False
    assert info.latest_version == "0.10.0"


# ---- Cache behaviour ------------------------------------------------------


def test_cache_avoids_network_within_ttl(
    monkeypatch: pytest.MonkeyPatch, vault_tmp
) -> None:
    monkeypatch.setattr(update_check, "__version__", "0.10.0")
    call_count = {"n": 0}

    def counting_urlopen(req, timeout=None):  # noqa: ARG001
        call_count["n"] += 1
        cm = MagicMock()
        cm.__enter__ = lambda self: self
        cm.__exit__ = lambda self, *a: None
        cm.read = lambda: json.dumps([{"tag_name": "v0.11.0"}]).encode("utf-8")
        return cm

    monkeypatch.setattr(update_check.urllib.request, "urlopen", counting_urlopen)

    check_for_update(force_refresh=True)
    check_for_update(force_refresh=False)
    check_for_update(force_refresh=False)

    assert call_count["n"] == 1


def test_env_ttl_zero_disables_cache(
    monkeypatch: pytest.MonkeyPatch, vault_tmp
) -> None:
    """MEMORY_KIT_UPDATE_TTL_SECONDS=0 → always refetch."""
    monkeypatch.setattr(update_check, "__version__", "0.10.0")
    monkeypatch.setenv("MEMORY_KIT_UPDATE_TTL_SECONDS", "0")
    call_count = {"n": 0}

    def counting_urlopen(req, timeout=None):  # noqa: ARG001
        call_count["n"] += 1
        cm = MagicMock()
        cm.__enter__ = lambda self: self
        cm.__exit__ = lambda self, *a: None
        cm.read = lambda: json.dumps([{"tag_name": "v0.11.0"}]).encode("utf-8")
        return cm

    monkeypatch.setattr(update_check.urllib.request, "urlopen", counting_urlopen)
    check_for_update(force_refresh=False)
    check_for_update(force_refresh=False)
    check_for_update(force_refresh=False)
    assert call_count["n"] == 3, "TTL=0 must bypass cache every call"


def test_default_ttl_is_one_hour() -> None:
    """v0.11.x reduces TTL from 24h to 1h for active release cycles."""
    assert update_check.DEFAULT_CACHE_TTL_SECONDS == 60 * 60


def test_force_refresh_bypasses_cache(
    monkeypatch: pytest.MonkeyPatch, vault_tmp
) -> None:
    monkeypatch.setattr(update_check, "__version__", "0.10.0")
    call_count = {"n": 0}

    def counting_urlopen(req, timeout=None):  # noqa: ARG001
        call_count["n"] += 1
        cm = MagicMock()
        cm.__enter__ = lambda self: self
        cm.__exit__ = lambda self, *a: None
        cm.read = lambda: json.dumps([{"tag_name": "v0.11.0"}]).encode("utf-8")
        return cm

    monkeypatch.setattr(update_check.urllib.request, "urlopen", counting_urlopen)

    check_for_update(force_refresh=True)
    check_for_update(force_refresh=True)

    assert call_count["n"] == 2


def test_cache_revalidates_against_running_version(
    monkeypatch: pytest.MonkeyPatch, vault_tmp
) -> None:
    """Once the cache is warm, bumping __version__ must clear update_available."""
    monkeypatch.setattr(update_check, "__version__", "0.10.0")
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        _mock_urlopen_factory({"tag_name": "v0.11.0"}),
    )

    first = check_for_update(force_refresh=True)
    assert first.update_available is True

    # Simulate a successful upgrade — bump the running version.
    monkeypatch.setattr(update_check, "__version__", "0.11.0")
    second = check_for_update(force_refresh=False)

    assert second.current_version == "0.11.0"
    assert second.update_available is False


# ---- Failure modes --------------------------------------------------------


def test_offline_failure_returns_error_silently(
    monkeypatch: pytest.MonkeyPatch, vault_tmp
) -> None:
    monkeypatch.setattr(update_check, "__version__", "0.10.0")

    def boom(req, timeout=None):  # noqa: ARG001
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(update_check.urllib.request, "urlopen", boom)

    info = check_for_update(force_refresh=True)

    assert info.update_available is False
    assert info.latest_version is None
    assert info.error is not None
    assert "URLError" in info.error


def test_offline_failure_does_not_write_cache(
    monkeypatch: pytest.MonkeyPatch, vault_tmp
) -> None:
    monkeypatch.setattr(update_check, "__version__", "0.10.0")
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(TimeoutError("slow")),
    )

    check_for_update(force_refresh=True)

    assert not update_check._cache_path().exists()


def test_opt_out_env_var_skips_network(
    monkeypatch: pytest.MonkeyPatch, vault_tmp
) -> None:
    monkeypatch.setenv("MEMORY_KIT_NO_UPDATE_CHECK", "1")
    monkeypatch.setattr(update_check, "__version__", "0.10.0")

    call_count = {"n": 0}

    def counting_urlopen(*a, **kw):  # noqa: ARG001
        call_count["n"] += 1
        return MagicMock()

    monkeypatch.setattr(update_check.urllib.request, "urlopen", counting_urlopen)

    info = check_for_update(force_refresh=True)

    assert call_count["n"] == 0
    assert info.error == "opt-out"
    assert info.update_available is False


def test_malformed_response_returns_error(
    monkeypatch: pytest.MonkeyPatch, vault_tmp
) -> None:
    monkeypatch.setattr(update_check, "__version__", "0.10.0")
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        _mock_urlopen_factory({"not_a_tag": "garbage"}),
    )

    info = check_for_update(force_refresh=True)

    assert info.update_available is False
    assert info.error is not None


# ---- emit_update_log -----------------------------------------------------


def test_emit_update_log_warns_when_update_available(
    caplog: pytest.LogCaptureFixture,
) -> None:
    info = UpdateInfo(
        current_version="0.10.0",
        latest_version="0.11.0",
        update_available=True,
        last_checked=time.time(),
    )

    with caplog.at_level(logging.WARNING, logger="memory_kit_mcp.update_check"):
        emit_update_log(info)

    assert any("0.11.0" in r.message and "memory-kit" in r.message for r in caplog.records)


def test_emit_update_log_silent_when_up_to_date(
    caplog: pytest.LogCaptureFixture,
) -> None:
    info = UpdateInfo(
        current_version="0.10.0",
        latest_version="0.10.0",
        update_available=False,
        last_checked=time.time(),
    )

    with caplog.at_level(logging.WARNING, logger="memory_kit_mcp.update_check"):
        emit_update_log(info)

    assert not caplog.records


# ---- MCP tool surface ----------------------------------------------------


async def test_mem_check_update_appears_in_inventory(client: Client) -> None:
    tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "mem_check_update" in names


async def test_mem_check_update_returns_structured_result(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(update_check, "__version__", "0.10.0")
    monkeypatch.setattr(
        update_check.urllib.request,
        "urlopen",
        _mock_urlopen_factory({"tag_name": "v0.11.0"}),
    )

    result = await client.call_tool("mem_check_update", {"force_refresh": True})

    payload = result.structured_content or {}
    assert payload.get("current_version") == "0.10.0"
    assert payload.get("latest_version") == "0.11.0"
    assert payload.get("update_available") is True
    assert "summary_md" in payload
    assert "0.11.0" in payload["summary_md"]


async def test_mem_check_update_opt_out(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEMORY_KIT_NO_UPDATE_CHECK", "1")

    result = await client.call_tool("mem_check_update", {"force_refresh": True})

    payload = result.structured_content or {}
    assert payload.get("error") == "opt-out"
    assert payload.get("update_available") is False
