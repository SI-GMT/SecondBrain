"""Update check + plan + run tests — in-process model."""

from __future__ import annotations

import sys
import types
import json
from pathlib import Path

import pytest

from sb_desktop import update
from sb_desktop.config import KitConfig

from ._engine_fakes import FakeUpdateInfo


def _install_fake_check(monkeypatch: pytest.MonkeyPatch, info: FakeUpdateInfo | Exception):
    module = types.ModuleType("memory_kit_mcp.update_check")

    if isinstance(info, Exception):
        def fake(force_refresh: bool = False):
            raise info  # type: ignore[misc]
    else:
        def fake(force_refresh: bool = False):
            return info

    module.check_for_update = fake  # type: ignore[attr-defined]

    root = types.ModuleType("memory_kit_mcp")
    root.update_check = module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "memory_kit_mcp", root)
    monkeypatch.setitem(sys.modules, "memory_kit_mcp.update_check", module)


def test_check_engine_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "memory_kit_mcp.update_check", None)
    result = update.check_update()
    assert result.ok is False
    assert "engine missing" in (result.error or "")


def test_check_update_available(monkeypatch: pytest.MonkeyPatch):
    _install_fake_check(
        monkeypatch,
        FakeUpdateInfo(
            current_version="0.12.0",
            latest_version="0.12.1",
            update_available=True,
            last_checked=1_700_000_000.0,
        ),
    )
    result = update.check_update()
    assert result.ok
    assert result.update_available
    assert result.current_version == "0.12.0"
    assert result.latest_version == "0.12.1"


def test_check_engine_raises(monkeypatch: pytest.MonkeyPatch):
    _install_fake_check(monkeypatch, RuntimeError("kaboom"))
    result = update.check_update()
    assert result.ok is False
    assert "kaboom" in (result.error or "")


def test_check_desktop_update_selects_macos_dmg(monkeypatch: pytest.MonkeyPatch):
    release_payload = [
        {
            "tag_name": "sb-desktop-v0.10.9",
            "assets": [
                {
                    "name": "SecondBrainDesktop-0.10.9-setup.exe",
                    "browser_download_url": "https://example.test/setup.exe",
                },
                {
                    "name": "SecondBrainDesktop-0.10.9.dmg",
                    "browser_download_url": "https://example.test/mac.dmg",
                },
            ],
        }
    ]

    class FakeResponse:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(release_payload).encode("utf-8")

    monkeypatch.setattr(update.sys, "platform", "darwin")
    monkeypatch.setattr(update, "_current_desktop_version", lambda: "0.10.8")
    monkeypatch.setattr(update.urllib.request, "urlopen", lambda *a, **kw: FakeResponse())

    result = update.check_desktop_update(force_refresh=True)

    assert result.update_available
    assert result.asset_filename == "SecondBrainDesktop-0.10.9.dmg"
    assert result.asset_url == "https://example.test/mac.dmg"


def test_check_desktop_update_selects_windows_setup(monkeypatch: pytest.MonkeyPatch):
    release_payload = [
        {
            "tag_name": "sb-desktop-v0.10.9",
            "assets": [
                {
                    "name": "SecondBrainDesktop-0.10.9.dmg",
                    "browser_download_url": "https://example.test/mac.dmg",
                },
                {
                    "name": "SecondBrainDesktop-0.10.9-setup.exe",
                    "browser_download_url": "https://example.test/setup.exe",
                },
            ],
        }
    ]

    class FakeResponse:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(release_payload).encode("utf-8")

    monkeypatch.setattr(update.sys, "platform", "win32")
    monkeypatch.setattr(update, "_current_desktop_version", lambda: "0.10.8")
    monkeypatch.setattr(update.urllib.request, "urlopen", lambda *a, **kw: FakeResponse())

    result = update.check_desktop_update(force_refresh=True)

    assert result.update_available
    assert result.asset_filename == "SecondBrainDesktop-0.10.9-setup.exe"
    assert result.asset_url == "https://example.test/setup.exe"


def test_plan_missing_kit_repo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(update, "load_kit_config", lambda: None)
    plan = update.plan_update()
    assert plan.can_run is False
    assert "kit_repo" in (plan.blocker or "")


def test_plan_resolves_script(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    repo = tmp_path / "kit"
    repo.mkdir()
    script_name = "deploy.ps1" if sys.platform == "win32" else "deploy.sh"
    (repo / script_name).write_text("# deploy", encoding="utf-8")
    monkeypatch.setattr(
        update,
        "load_kit_config",
        lambda: KitConfig(vault=repo, language="en", kit_repo=repo),
    )
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/usr/bin/{name}")

    plan = update.plan_update()
    assert plan.can_run is True
    assert plan.deploy_script is not None
    assert plan.deploy_script.name == script_name


def test_run_refuses_without_confirmation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    repo = tmp_path / "kit"
    repo.mkdir()
    script_name = "deploy.ps1" if sys.platform == "win32" else "deploy.sh"
    (repo / script_name).write_text("# deploy", encoding="utf-8")
    monkeypatch.setattr(
        update,
        "load_kit_config",
        lambda: KitConfig(vault=repo, language="en", kit_repo=repo),
    )
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/usr/bin/{name}")

    result = update.run_update(confirmed=False)
    assert result.ok is False
    assert result.confirmed is False


def test_run_invokes_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    repo = tmp_path / "kit"
    repo.mkdir()
    script_name = "deploy.ps1" if sys.platform == "win32" else "deploy.sh"
    (repo / script_name).write_text("# deploy", encoding="utf-8")
    monkeypatch.setattr(
        update,
        "load_kit_config",
        lambda: KitConfig(vault=repo, language="en", kit_repo=repo),
    )
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/usr/bin/{name}")

    captured: dict = {}

    class FakeCompleted:
        returncode = 0
        stdout = "deploy ok"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeCompleted()

    monkeypatch.setattr(update.subprocess, "run", fake_run)

    result = update.run_update(confirmed=True)
    assert result.ok is True
    # The deploy script path is always the second-to-last argument:
    # [interpreter, …flags, script, autoupdate_flag]
    assert script_name in captured["cmd"][-2]
