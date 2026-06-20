"""Tests for the i18n translation runtime."""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from sb_desktop import i18n


@pytest.fixture(autouse=True)
def _reset_i18n(monkeypatch: pytest.MonkeyPatch):
    """Start every test with empty caches and a clean active language."""
    monkeypatch.setattr(i18n, "_catalogue_cache", {})
    i18n.reset_active_language()
    yield
    i18n.reset_active_language()


def _seed_catalogues(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **langs: dict):
    for lang, mapping in langs.items():
        (tmp_path / f"{lang}.json").write_text(
            json.dumps(mapping), encoding="utf-8"
        )
    monkeypatch.setattr(i18n, "_catalogue_dir", lambda: tmp_path)


def test_load_catalogue_missing_file_returns_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(i18n, "_catalogue_dir", lambda: tmp_path)
    assert i18n._load_catalogue("xx") == {}
    # Cached now — second call hits the cache branch.
    assert i18n._load_catalogue("xx") == {}


def test_load_catalogue_bad_json_returns_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    (tmp_path / "fr.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(i18n, "_catalogue_dir", lambda: tmp_path)
    assert i18n._load_catalogue("fr") == {}


def test_load_catalogue_non_object_returns_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    (tmp_path / "fr.json").write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(i18n, "_catalogue_dir", lambda: tmp_path)
    assert i18n._load_catalogue("fr") == {}


def test_t_returns_translation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _seed_catalogues(monkeypatch, tmp_path, en={"hello": "Hello"})
    monkeypatch.setattr(i18n, "_active_language", "en")
    assert i18n.t("hello") == "Hello"


def test_t_falls_back_to_english(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _seed_catalogues(
        monkeypatch, tmp_path, en={"hello": "Hello"}, fr={"bye": "Au revoir"}
    )
    monkeypatch.setattr(i18n, "_active_language", "fr")
    # 'hello' missing in fr → English fallback.
    assert i18n.t("hello") == "Hello"
    # present in fr → fr wins.
    assert i18n.t("bye") == "Au revoir"


def test_t_missing_everywhere_returns_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _seed_catalogues(monkeypatch, tmp_path, en={})
    monkeypatch.setattr(i18n, "_active_language", "en")
    assert i18n.t("nope") == "nope"


def test_t_interpolates_format(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _seed_catalogues(monkeypatch, tmp_path, en={"count": "You have {n} items"})
    monkeypatch.setattr(i18n, "_active_language", "en")
    assert i18n.t("count", n=3) == "You have 3 items"


def test_t_format_error_returns_template(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _seed_catalogues(monkeypatch, tmp_path, en={"count": "You have {missing} items"})
    monkeypatch.setattr(i18n, "_active_language", "en")
    # Wrong kwarg → format KeyError swallowed, raw template returned.
    assert i18n.t("count", n=3) == "You have {missing} items"


def _patch_config(monkeypatch, *, settings_lang=None, kit_lang=None):
    settings = types.SimpleNamespace(language_override=settings_lang)
    kit = types.SimpleNamespace(language=kit_lang) if kit_lang is not None else None
    fake = types.ModuleType("sb_desktop.config")
    fake.load_settings = lambda: settings
    fake.load_kit_config = lambda: kit
    monkeypatch.setitem(
        __import__("sys").modules, "sb_desktop.config", fake
    )


def test_resolve_language_settings_override_wins(monkeypatch: pytest.MonkeyPatch):
    _patch_config(monkeypatch, settings_lang="de", kit_lang="fr")
    assert i18n._resolve_language() == "de"


def test_resolve_language_kit_used_when_no_override(monkeypatch: pytest.MonkeyPatch):
    _patch_config(monkeypatch, settings_lang=None, kit_lang="ru")
    assert i18n._resolve_language() == "ru"


def test_resolve_language_env_fallback(monkeypatch: pytest.MonkeyPatch):
    _patch_config(monkeypatch, settings_lang=None, kit_lang=None)
    monkeypatch.setenv("MEMORY_KIT_LANG", "es")
    assert i18n._resolve_language() == "es"


def test_resolve_language_default_en(monkeypatch: pytest.MonkeyPatch):
    _patch_config(monkeypatch, settings_lang=None, kit_lang=None)
    monkeypatch.delenv("MEMORY_KIT_LANG", raising=False)
    monkeypatch.delenv("LANG", raising=False)
    assert i18n._resolve_language() == "en"


def test_resolve_language_handles_config_exception(monkeypatch: pytest.MonkeyPatch):
    fake = types.ModuleType("sb_desktop.config")

    def boom():
        raise RuntimeError("config broke")

    fake.load_settings = boom
    fake.load_kit_config = boom
    monkeypatch.setitem(__import__("sys").modules, "sb_desktop.config", fake)
    monkeypatch.delenv("MEMORY_KIT_LANG", raising=False)
    monkeypatch.delenv("LANG", raising=False)
    assert i18n._resolve_language() == "en"


def test_active_language_caches(monkeypatch: pytest.MonkeyPatch):
    calls = {"n": 0}

    def fake_resolve():
        calls["n"] += 1
        return "fr"

    monkeypatch.setattr(i18n, "_resolve_language", fake_resolve)
    assert i18n.active_language() == "fr"
    assert i18n.active_language() == "fr"
    assert calls["n"] == 1  # cached after first resolve
    i18n.reset_active_language()
    assert i18n.active_language() == "fr"
    assert calls["n"] == 2
