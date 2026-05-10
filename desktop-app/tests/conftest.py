"""Test fixtures common to the sb-desktop suite.

We isolate every test from the host's real ``~/.memory-kit`` directory
and from the platform-specific user data dirs by redirecting the path
helpers to temporary directories per test. That keeps the suite hermetic
and re-runnable without manual cleanup.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture
def tmp_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect every path helper to per-test subdirectories."""
    data = tmp_path / "data"
    logs = tmp_path / "logs"
    cache = tmp_path / "cache"
    config_root = tmp_path / "config"
    data.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("sb_desktop.paths.app_data_dir", lambda: data)
    monkeypatch.setattr("sb_desktop.paths.app_log_dir", lambda: logs)
    monkeypatch.setattr("sb_desktop.paths.app_cache_dir", lambda: cache)
    monkeypatch.setattr(
        "sb_desktop.paths.memory_kit_config_path", lambda: config_root / "config.json"
    )
    monkeypatch.setattr("sb_desktop.paths.log_file_path", lambda: logs / "sb-desktop.log")
    monkeypatch.setattr("sb_desktop.paths.settings_file_path", lambda: data / "settings.json")
    yield tmp_path


@pytest.fixture
def kit_config(tmp_paths: Path) -> Path:
    """Drop a minimal valid kit config in the redirected location."""
    vault = tmp_paths / "vault"
    kit_repo = tmp_paths / "kit_repo"
    vault.mkdir(parents=True, exist_ok=True)
    kit_repo.mkdir(parents=True, exist_ok=True)
    config = {
        "vault": str(vault),
        "language": "fr",
        "kit_repo": str(kit_repo),
    }
    target = tmp_paths / "config" / "config.json"
    target.write_text(json.dumps(config), encoding="utf-8")
    return target
