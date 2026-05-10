"""Lightweight update-check against the SecondBrain GitHub releases API.

Called from server.py main() at startup (non-blocking — uses a 24h cache so
the GitHub API is hit at most once per day) and exposed as the
mem_check_update MCP tool for explicit interrogation by the LLM.

Design:
- urllib.request (stdlib, zero new deps).
- Cache at ~/.memory-kit/update-check.json with 24h TTL.
- Fails silently on network errors — the server must always start.
- Opt-out via env var MEMORY_KIT_NO_UPDATE_CHECK=1.
- Compares semver tuples (numeric prefix of each dotted chunk).
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from memory_kit_mcp import __version__

log = logging.getLogger(__name__)

GITHUB_LATEST_URL = "https://api.github.com/repos/SI-GMT/SecondBrain/releases/latest"
# 1 h default — reduced from 24 h (v0.10.x) so users see release notifications
# within an hour of cache hit during active release cycles. GitHub API anonymous
# limit is 60/h per IP, so worst-case (one CLI launch every minute) stays well
# below. Override via MEMORY_KIT_UPDATE_TTL_SECONDS env var (e.g. set to 0 to
# always force-refresh, or 86400 to restore the legacy 24 h behaviour).
DEFAULT_CACHE_TTL_SECONDS = 60 * 60
HTTP_TIMEOUT_SECONDS = 2.0
USER_AGENT = "memory-kit-mcp"


def _resolved_ttl_seconds() -> int:
    raw = os.environ.get("MEMORY_KIT_UPDATE_TTL_SECONDS")
    if raw is None:
        return DEFAULT_CACHE_TTL_SECONDS
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_CACHE_TTL_SECONDS


# Kept as a module-level alias for backward-compat with tests / external callers
# that imported the old constant. Reads via the env-aware resolver each access.
CACHE_TTL_SECONDS = DEFAULT_CACHE_TTL_SECONDS


@dataclass
class UpdateInfo:
    """Result of a single update check."""

    current_version: str
    latest_version: str | None
    update_available: bool
    last_checked: float
    error: str | None = None


def _cache_path() -> Path:
    env = os.environ.get("MEMORY_KIT_HOME")
    base = Path(env) if env else Path.home() / ".memory-kit"
    return base / "update-check.json"


def _read_cache() -> UpdateInfo | None:
    p = _cache_path()
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return UpdateInfo(**raw)
    except (json.JSONDecodeError, TypeError, OSError):
        return None


def _write_cache(info: UpdateInfo) -> None:
    p = _cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(info), indent=2), encoding="utf-8")
    except OSError:
        pass


def _normalize_version(v: str) -> str:
    return v.strip().lstrip("v")


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a semver-ish version into a tuple of ints. Non-numeric chunks stop parsing."""
    parts: list[int] = []
    for chunk in _normalize_version(v).split("."):
        digits = ""
        for c in chunk:
            if c.isdigit():
                digits += c
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _is_newer(remote: str, local: str) -> bool:
    try:
        return _parse_version(remote) > _parse_version(local)
    except Exception:
        return False


def _fetch_latest_tag(timeout: float = HTTP_TIMEOUT_SECONDS) -> str:
    req = urllib.request.Request(
        GITHUB_LATEST_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https URL hardcoded)
        data = json.loads(resp.read())
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not tag:
        raise ValueError("GitHub API response missing tag_name")
    return tag


def check_for_update(force_refresh: bool = False) -> UpdateInfo:
    """Return UpdateInfo. Honors 24h cache, env opt-out, fails silently on errors.

    Opt-out: returns UpdateInfo with update_available=False and error="opt-out"
    so callers can distinguish "no update" from "didn't check".
    """
    current = __version__

    if os.environ.get("MEMORY_KIT_NO_UPDATE_CHECK") == "1":
        return UpdateInfo(
            current_version=current,
            latest_version=None,
            update_available=False,
            last_checked=time.time(),
            error="opt-out",
        )

    if not force_refresh:
        cached = _read_cache()
        ttl = _resolved_ttl_seconds()
        if (
            cached is not None
            and ttl > 0
            and (time.time() - cached.last_checked) < ttl
        ):
            # Re-evaluate against the running version in case the user just upgraded.
            cached.current_version = current
            cached.update_available = bool(
                cached.latest_version and _is_newer(cached.latest_version, current)
            )
            return cached

    try:
        tag = _fetch_latest_tag()
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as e:
        return UpdateInfo(
            current_version=current,
            latest_version=None,
            update_available=False,
            last_checked=time.time(),
            error=f"{type(e).__name__}: {e}",
        )

    info = UpdateInfo(
        current_version=current,
        latest_version=_normalize_version(tag),
        update_available=_is_newer(tag, current),
        last_checked=time.time(),
        error=None,
    )
    _write_cache(info)
    return info


def emit_update_log(info: UpdateInfo, logger: logging.Logger | None = None) -> None:
    """Log a one-line update notification if an update is available."""
    if not info.update_available or not info.latest_version:
        return
    msg = (
        f"[memory-kit] v{info.latest_version} disponible "
        f"(actuelle : v{info.current_version}) — "
        "`git pull && deploy.ps1 -RepairMcp` (ou `deploy.sh --repair-mcp`)"
    )
    (logger or log).warning(msg)
