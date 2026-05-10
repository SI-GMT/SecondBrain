"""Read-only loader for the Memory Kit config + persistent app settings.

Two config sources, kept distinct on purpose:

1. **Kit config** (``~/.memory-kit/config.json``) — written by the kit's
   ``deploy.ps1`` / ``deploy.sh`` at install time. Holds the vault path,
   the conversational language, and the kit checkout location. We treat
   this as authoritative and never write to it from the desktop app.

2. **App settings** (``$DATA_DIR/settings.json``) — persisted by the
   desktop app for its own UI state: autostart preference, last-used
   notification policy, log viewer position, etc. Distinct file so we
   never clobber the kit config on a partial write.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import paths as _paths

log = logging.getLogger(__name__)


class KitConfig(BaseModel):
    """Subset of the kit config we actually consume."""

    vault: Path
    language: str = Field(default="en", min_length=2, max_length=5)
    kit_repo: Path | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    @property
    def vault_exists(self) -> bool:
        return self.vault.is_dir()

    @property
    def kit_repo_exists(self) -> bool:
        return self.kit_repo is not None and self.kit_repo.is_dir()


class AppSettings(BaseModel):
    """Persistent desktop-app preferences.

    Defaults are tuned for the non-tech audience: confirm everything that
    mutates state, surface notifications proactively.
    """

    autostart: bool = False
    language_override: str | None = None
    confirm_repair: bool = True
    confirm_update: bool = True
    notify_on_scan_findings: bool = True
    notify_on_update_available: bool = True
    poll_interval_seconds: int = Field(default=900, ge=60, le=3600)


def load_kit_config(path: Path | None = None) -> KitConfig | None:
    """Return the kit config or ``None`` if it can't be parsed.

    Returning ``None`` (rather than raising) keeps the tray app robust on a
    half-installed machine: the user lands on the tray with a red icon and
    a "kit not installed" hint instead of a crash dump.
    """
    target = path or _paths.memory_kit_config_path()
    if not target.is_file():
        log.warning("memory-kit config absent at %s", target)
        return None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("failed to parse memory-kit config %s: %s", target, exc)
        return None

    vault = raw.get("vault")
    if not vault:
        log.error("memory-kit config has no 'vault' key: %s", target)
        return None

    extras = {k: v for k, v in raw.items() if k not in {"vault", "language", "kit_repo"}}

    try:
        return KitConfig(
            vault=Path(vault).expanduser(),
            language=raw.get("language", "en"),
            kit_repo=Path(raw["kit_repo"]).expanduser() if raw.get("kit_repo") else None,
            extras=extras,
        )
    except Exception as exc:
        log.error("memory-kit config validation failed: %s", exc)
        return None


def load_settings(path: Path | None = None) -> AppSettings:
    target = path or _paths.settings_file_path()
    if not target.is_file():
        return AppSettings()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return AppSettings.model_validate(raw)
    except Exception as exc:
        log.warning("settings file unreadable, falling back to defaults: %s", exc)
        return AppSettings()


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    """Atomic write — settings always reflect a complete, validated state."""
    target = path or _paths.settings_file_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump_json(indent=2)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    tmp.replace(target)


def effective_language(kit: KitConfig | None, settings: AppSettings) -> str:
    """Resolve UI language with explicit precedence: override > kit > 'en'."""
    if settings.language_override:
        return settings.language_override
    if kit is not None:
        return kit.language
    return "en"
