"""Update check + plan + run tests — in-process model."""

from __future__ import annotations

import sys
import types
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


# ---------------------------------------------------------------------------
# engine wheelhouse asset resolution + in-place install
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_releases_json(*entries) -> bytes:
    import json

    return json.dumps(list(entries)).encode()


def test_fetch_engine_asset_picks_wheelhouse(monkeypatch: pytest.MonkeyPatch):
    payload = _fake_releases_json(
        {
            "tag_name": "v0.14.0",
            "assets": [
                {
                    "name": "memory_kit_mcp-0.14.0-py3-none-any.whl",
                    "browser_download_url": "http://x/wheel.whl",
                },
                {
                    "name": "memory_kit_mcp-0.14.0-wheelhouse-win_amd64.zip",
                    "browser_download_url": "http://x/wheelhouse.zip",
                },
            ],
        }
    )
    monkeypatch.setattr(
        update.urllib.request,
        "urlopen",
        lambda req, timeout=0: _FakeResp(payload),
    )
    url, name = update._fetch_engine_asset("0.14.0")
    assert url == "http://x/wheelhouse.zip"
    assert name == "memory_kit_mcp-0.14.0-wheelhouse-win_amd64.zip"


def test_fetch_engine_asset_none_when_absent(monkeypatch: pytest.MonkeyPatch):
    payload = _fake_releases_json(
        {
            "tag_name": "v0.14.0",
            "assets": [
                {
                    "name": "memory_kit_mcp-0.14.0-py3-none-any.whl",
                    "browser_download_url": "http://x/wheel.whl",
                }
            ],
        }
    )
    monkeypatch.setattr(
        update.urllib.request,
        "urlopen",
        lambda req, timeout=0: _FakeResp(payload),
    )
    assert update._fetch_engine_asset("0.14.0") == (None, None)


def test_fetch_engine_asset_network_error_is_swallowed(
    monkeypatch: pytest.MonkeyPatch,
):
    def boom(req, timeout=0):
        raise OSError("offline")

    monkeypatch.setattr(update.urllib.request, "urlopen", boom)
    assert update._fetch_engine_asset("0.14.0") == (None, None)


def test_check_update_populates_wheelhouse_asset(monkeypatch: pytest.MonkeyPatch):
    _install_fake_check(
        monkeypatch,
        FakeUpdateInfo(
            current_version="0.13.2",
            latest_version="0.14.0",
            update_available=True,
            last_checked=1_700_000_000.0,
        ),
    )
    monkeypatch.setattr(
        update,
        "_fetch_engine_asset",
        lambda v: ("http://x/wh.zip", f"memory_kit_mcp-{v}-wheelhouse-win_amd64.zip"),
    )
    result = update.check_update()
    assert result.update_available
    assert result.asset_url == "http://x/wh.zip"
    assert result.asset_filename == "memory_kit_mcp-0.14.0-wheelhouse-win_amd64.zip"


def test_check_update_no_asset_lookup_when_up_to_date(
    monkeypatch: pytest.MonkeyPatch,
):
    _install_fake_check(
        monkeypatch,
        FakeUpdateInfo(
            current_version="0.14.0",
            latest_version="0.14.0",
            update_available=False,
            last_checked=1_700_000_000.0,
        ),
    )

    def fail(_v):  # must not be called
        raise AssertionError("asset lookup ran while up to date")

    monkeypatch.setattr(update, "_fetch_engine_asset", fail)
    result = update.check_update()
    assert result.update_available is False
    assert result.asset_url is None


def _make_wheelhouse_zip(path: Path, *, nested: bool = False) -> None:
    import zipfile

    arc = "wheelhouse/dep.whl" if nested else "dep.whl"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(arc, b"fake wheel bytes")


def test_download_and_install_engine_happy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    zip_path = tmp_path / "wh.zip"
    _make_wheelhouse_zip(zip_path)

    monkeypatch.setattr(update, "_downloads_dir", lambda: tmp_path)
    monkeypatch.setattr(
        update,
        "download_asset",
        lambda url, name, **kw: update.DownloadResult(ok=True, path=zip_path),
    )

    captured: dict = {}

    def fake_install(wheels_dir, *, on_progress=None):
        captured["wheels_dir"] = wheels_dir
        return update.ApplyResult(ok=True, detail="installed")

    monkeypatch.setattr(update, "install_engine_update", fake_install)

    res = update.download_and_install_engine(
        "http://x/wh.zip", "memory_kit_mcp-0.14.0-wheelhouse-win_amd64.zip"
    )
    assert res.ok
    assert list(captured["wheels_dir"].glob("*.whl"))


def test_download_and_install_engine_nested_wheels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    zip_path = tmp_path / "wh.zip"
    _make_wheelhouse_zip(zip_path, nested=True)
    monkeypatch.setattr(update, "_downloads_dir", lambda: tmp_path)
    monkeypatch.setattr(
        update,
        "download_asset",
        lambda url, name, **kw: update.DownloadResult(ok=True, path=zip_path),
    )
    captured: dict = {}
    monkeypatch.setattr(
        update,
        "install_engine_update",
        lambda wheels_dir, *, on_progress=None: (
            captured.update(wheels_dir=wheels_dir)
            or update.ApplyResult(ok=True)
        ),
    )
    res = update.download_and_install_engine(
        "http://x/wh.zip", "memory_kit_mcp-0.14.0-wheelhouse-win_amd64.zip"
    )
    assert res.ok
    assert captured["wheels_dir"].name == "wheelhouse"


def test_download_and_install_engine_download_fail(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        update,
        "download_asset",
        lambda url, name, **kw: update.DownloadResult(ok=False, error="404"),
    )
    res = update.download_and_install_engine("http://x/wh.zip", "wh.zip")
    assert res.ok is False
    assert "download failed" in (res.error or "")


def test_download_and_install_engine_empty_wheelhouse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    import zipfile

    zip_path = tmp_path / "wh.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("README.txt", b"no wheels here")
    monkeypatch.setattr(update, "_downloads_dir", lambda: tmp_path)
    monkeypatch.setattr(
        update,
        "download_asset",
        lambda url, name, **kw: update.DownloadResult(ok=True, path=zip_path),
    )
    res = update.download_and_install_engine(
        "http://x/wh.zip", "memory_kit_mcp-0.14.0-wheelhouse-win_amd64.zip"
    )
    assert res.ok is False
    assert "no .whl" in (res.error or "")


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


# ---------------------------------------------------------------------------
# desktop channel check + cache + version helpers
# ---------------------------------------------------------------------------


def test_check_desktop_update_picks_installer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(update.paths, "app_cache_dir", lambda: tmp_path)
    payload = _fake_releases_json(
        {
            "tag_name": "sb-desktop-v9.9.9",
            "assets": [
                {
                    "name": "SecondBrainDesktop-9.9.9-setup.exe",
                    "browser_download_url": "http://x/setup.exe",
                }
            ],
        }
    )
    monkeypatch.setattr(
        update.urllib.request,
        "urlopen",
        lambda req, timeout=0: _FakeResp(payload),
    )
    res = update.check_desktop_update(force_refresh=True)
    assert res.update_available is True
    assert res.asset_filename == "SecondBrainDesktop-9.9.9-setup.exe"
    assert res.asset_url == "http://x/setup.exe"


def test_check_desktop_update_no_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(update.paths, "app_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        update.urllib.request,
        "urlopen",
        lambda req, timeout=0: _FakeResp(_fake_releases_json()),
    )
    res = update.check_desktop_update(force_refresh=True)
    assert res.update_available is False
    assert "no desktop release" in (res.error or "")


def test_desktop_cache_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(update.paths, "app_cache_dir", lambda: tmp_path)
    assert update._read_desktop_cache(3600) is None  # nothing cached yet
    res = update.UpdateCheckResult(
        channel="desktop",
        ok=True,
        current_version="0.11.2",
        latest_version="0.12.0",
        update_available=True,
    )
    update._write_desktop_cache(res)
    cached = update._read_desktop_cache(3600)
    assert cached is not None
    assert cached.latest_version == "0.12.0"


def test_version_helpers():
    assert update._parse_version("v1.2.3") == (1, 2, 3)
    assert update._is_newer("0.14.0", "0.13.2") is True
    assert update._is_newer("0.13.2", "0.14.0") is False
    assert update._is_newer("garbage", "0.1.0") is False
