"""Config loader tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sb_desktop import config


def test_load_kit_config_happy_path(kit_config: Path):
    cfg = config.load_kit_config()
    assert cfg is not None
    assert cfg.language == "fr"
    assert cfg.vault.is_dir()
    assert cfg.kit_repo_exists


def test_load_kit_config_missing(tmp_paths: Path):
    cfg = config.load_kit_config()
    assert cfg is None


def test_load_kit_config_malformed(tmp_paths: Path):
    target = tmp_paths / "config" / "config.json"
    target.write_text("{not valid json", encoding="utf-8")
    cfg = config.load_kit_config()
    assert cfg is None


def test_load_kit_config_missing_vault_key(tmp_paths: Path):
    target = tmp_paths / "config" / "config.json"
    target.write_text(json.dumps({"language": "en"}), encoding="utf-8")
    cfg = config.load_kit_config()
    assert cfg is None


def test_save_and_reload_settings(tmp_paths: Path):
    settings = config.AppSettings(autostart=True, poll_interval_seconds=300)
    config.save_settings(settings)

    loaded = config.load_settings()
    assert loaded.autostart is True
    assert loaded.poll_interval_seconds == 300


def test_load_settings_falls_back_on_corrupt(tmp_paths: Path):
    target = tmp_paths / "data" / "settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("garbage", encoding="utf-8")

    loaded = config.load_settings()
    assert loaded == config.AppSettings()


def test_effective_language_precedence():
    kit = config.KitConfig(vault=Path("."), language="de", kit_repo=None)
    settings = config.AppSettings(language_override="es")
    assert config.effective_language(kit, settings) == "es"

    settings_no_override = config.AppSettings()
    assert config.effective_language(kit, settings_no_override) == "de"

    assert config.effective_language(None, settings_no_override) == "en"


def test_settings_validates_poll_interval():
    with pytest.raises(Exception):
        config.AppSettings(poll_interval_seconds=10)
    with pytest.raises(Exception):
        config.AppSettings(poll_interval_seconds=10000)
