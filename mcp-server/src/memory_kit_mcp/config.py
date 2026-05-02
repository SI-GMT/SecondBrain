"""Configuration loader for the memory-kit MCP server.

Reads ~/.memory-kit/config.json (override via $MEMORY_KIT_HOME) and exposes a
typed Config object. Cached per-process — call get_config.cache_clear() in tests
to force a reload after monkeypatching the env.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


class Config(BaseModel):
    """Resolved configuration of the memory-kit MCP server."""

    vault: Path = Field(..., description="Absolute path to the Markdown vault root.")
    default_scope: str = Field("work", description="Default scope: 'work' | 'personal' | 'all'.")
    language: str = Field("en", description="Conversational language code (en, fr, es, de, ru).")
    kit_repo: Path | None = Field(
        None,
        description="Absolute path to the SecondBrain kit repo (for i18n strings, doc-readers).",
    )


def _resolve_config_path() -> Path:
    """Locate ~/.memory-kit/config.json, honoring $MEMORY_KIT_HOME override."""
    env = os.environ.get("MEMORY_KIT_HOME")
    if env:
        return Path(env) / "config.json"
    return Path.home() / ".memory-kit" / "config.json"


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Load and validate the config file. Cached per-process."""
    config_path = _resolve_config_path()
    if not config_path.exists():
        raise FileNotFoundError(
            f"memory-kit config not found at {config_path}. "
            "Run deploy.ps1 / deploy.sh from the SecondBrain kit, "
            "or create the file manually with at least: "
            '{"vault": "/path/to/vault", "language": "en"}'
        )
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    # Resolve vault to absolute Path
    raw["vault"] = Path(raw["vault"]).expanduser().resolve()
    if "kit_repo" in raw and raw["kit_repo"]:
        raw["kit_repo"] = Path(raw["kit_repo"]).expanduser().resolve()
    return Config(**raw)
