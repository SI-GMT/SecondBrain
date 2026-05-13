"""i18n — minimal translation runtime for the tray app.

Tray menu, dialog labels, and notifications resolve their strings via
:func:`t` against a JSON catalogue shipped at
``src/sb_desktop/i18n/{lang}.json``. The catalogue is loaded once per
process and cached; missing keys fall back to the English source so a
new string can ship before its translation does.

Language selection priority (first match wins):

1. ``AppSettings.language_override`` if set (per-user explicit choice
   in the Settings dialog).
2. ``KitConfig.language`` from ``~/.memory-kit/config.json`` (the kit's
   conversational language — same source of truth the LLM uses).
3. ``MEMORY_KIT_LANG`` env var (CI / scripted overrides).
4. ``en`` as the universal fallback.

Translations stay structurally close to English keys (slug-style
identifiers) so a missing translation is obvious in logs but never
crashes the UI.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "fr", "es", "de", "ru")

_catalogue_cache: dict[str, dict[str, str]] = {}
_active_language: str | None = None


def _catalogue_dir() -> Path:
    return Path(__file__).resolve().parent / "i18n"


def _load_catalogue(language: str) -> dict[str, str]:
    if language in _catalogue_cache:
        return _catalogue_cache[language]
    path = _catalogue_dir() / f"{language}.json"
    if not path.is_file():
        _catalogue_cache[language] = {}
        return _catalogue_cache[language]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("catalogue root must be an object")
        _catalogue_cache[language] = {
            str(k): str(v) for k, v in data.items()
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        log.warning("i18n: failed to load %s: %s", path, exc)
        _catalogue_cache[language] = {}
    return _catalogue_cache[language]


def _resolve_language() -> str:
    """Determine the active UI language. Order: settings → kit → env → en."""
    try:
        from .config import load_kit_config, load_settings

        settings = load_settings()
        if settings.language_override and settings.language_override in SUPPORTED_LANGUAGES:
            return settings.language_override
        kit = load_kit_config()
        if kit and kit.language in SUPPORTED_LANGUAGES:
            return kit.language
    except Exception as exc:
        log.debug("i18n: settings/kit lookup failed (%s) — falling back", exc)
    env = os.environ.get("MEMORY_KIT_LANG") or os.environ.get("LANG", "")
    short = env.split(".", 1)[0].split("_", 1)[0].lower()
    if short in SUPPORTED_LANGUAGES:
        return short
    return DEFAULT_LANGUAGE


def active_language() -> str:
    """Return (and cache) the active language code for this session."""
    global _active_language
    if _active_language is None:
        _active_language = _resolve_language()
    return _active_language


def reset_active_language() -> None:
    """Forget the cached language — used after the Settings dialog saves."""
    global _active_language
    _active_language = None


def t(key: str, /, **fmt: object) -> str:
    """Translate ``key`` and optionally interpolate ``fmt`` kwargs.

    Missing keys log a debug message and return the key itself — useful
    for spotting un-translated strings in QA. Use Python str.format
    placeholders (``{count}``) inside the catalogue values.
    """
    lang = active_language()
    catalogue = _load_catalogue(lang)
    template = catalogue.get(key)
    if template is None and lang != DEFAULT_LANGUAGE:
        template = _load_catalogue(DEFAULT_LANGUAGE).get(key)
    if template is None:
        log.debug("i18n: missing key '%s' in %s", key, lang)
        template = key
    if fmt:
        try:
            return template.format(**fmt)
        except (KeyError, IndexError) as exc:
            log.warning("i18n: format error for '%s' (%s)", key, exc)
            return template
    return template
