"""Status snapshot for the Memory Kit engine — in-process model.

V2 architecture: the desktop app **bundles** ``memory_kit_mcp`` as a
regular Python dependency, so the engine is always reachable via direct
function call. There is no JSON-RPC stdio handshake to fail, no
subprocess to spawn per click.

What the user actually wants to know at a glance has therefore shifted.
We surface three facts:

1. **In-process engine version** — the copy bundled inside this
   executable. Always available; failure here would mean a broken
   install.
2. **pipx-installed engine reachability** — whether
   ``memory-kit-mcp`` is on PATH, because that's the binary the LLM
   CLIs (Claude Code, Codex, Gemini, …) actually call. If the user
   has the desktop but not the pipx install, the tray app works but
   the LLMs won't see their vault — worth flagging.
3. **Version alignment** — when both are present, whether the
   pipx-installed version matches the bundled one. Drift is the
   common cause of "the app says update available but my LLM still
   complains about an old kit."

The pipx version is read from the venv's ``dist-info/METADATA`` file —
**no subprocess**. Spawning the binary just to read ``--version`` would
mean a Pydantic + FastMCP cold start (≈5-15 s on Windows), which is
unacceptable for a tray app. Parsing the metadata file is sub-ms and
gives us the same answer the package itself would report.
"""

from __future__ import annotations

import logging
import re
import shutil
import sys
import time
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

_VERSION_LINE = re.compile(r"^Version:\s*(.+)$", re.MULTILINE)

_pipx_probe_cache: tuple[str | None, str | None] | None = None  # (path, version)


class StatusLevel(str, Enum):
    """Tray icon colour mapping."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    UNKNOWN = "unknown"


class StatusSnapshot(BaseModel):
    """Frozen-in-time view of the engine's reachability."""

    level: StatusLevel
    summary: str
    bundled_version: str | None = None
    pipx_binary_path: Path | None = None
    pipx_version: str | None = None
    versions_match: bool | None = None
    error: str | None = None
    probed_at: float = Field(default_factory=time.time)

    def is_ok(self) -> bool:
        return self.level == StatusLevel.OK

    def render_text(self) -> str:
        lines = [f"Status: {self.level.value.upper()}", f"  {self.summary}"]
        if self.bundled_version:
            lines.append(f"  Bundled engine: v{self.bundled_version}")
        if self.pipx_binary_path:
            lines.append(f"  pipx binary:   {self.pipx_binary_path}")
        if self.pipx_version:
            lines.append(f"  pipx version:  v{self.pipx_version}")
        if self.versions_match is False:
            lines.append("  pipx and bundled versions differ.")
        if self.error:
            lines.append(f"  Error: {self.error}")
        return "\n".join(lines)


def _bundled_version() -> tuple[str | None, str | None]:
    """Return (version, error). Import is cheap — already in memory."""
    try:
        from memory_kit_mcp import __version__ as kit_version
    except ImportError as exc:
        return None, f"bundled memory_kit_mcp import failed: {exc}"
    return kit_version, None


def _pipx_default_venvs() -> list[Path]:
    """Common pipx venv paths for memory-kit-mcp on this host.

    pipx has used several layouts across versions and platforms. The
    desktop app should not report a false drift warning just because
    ``memory-kit-mcp`` is exposed through a ``~/.local/bin`` shim.
    """
    home = Path.home()
    return [
        home / ".local" / "pipx" / "venvs" / "memory-kit-mcp",
        home / ".local" / "share" / "pipx" / "venvs" / "memory-kit-mcp",
        home / "pipx" / "venvs" / "memory-kit-mcp",
    ]


def _looks_like_install_root(candidate: Path) -> bool:
    """True if ``candidate`` looks like a Python install layout that
    holds ``memory_kit_mcp`` site-packages.

    Accepts both:
    * Standard pipx venvs (``pyvenv.cfg`` at the root).
    * SecondBrain Desktop bundled engines (``Lib/site-packages``
      under ``{install}/engine/`` with no ``pyvenv.cfg`` because the
      embeddable Python doesn't ship one).
    """
    if (candidate / "pyvenv.cfg").is_file():
        return True
    if (candidate / "Lib" / "site-packages").is_dir():
        return True
    if (candidate / "lib").is_dir():
        # POSIX shape: lib/pythonX.Y/site-packages somewhere underneath.
        return any(
            child.is_dir() and child.name.startswith("python")
            for child in (candidate / "lib").iterdir()
        )
    return False


def _venv_root_from_binary(binary: Path) -> Path | None:
    """Derive the venv root from the binary path, with a pipx-default fallback.

    Standard pipx layout puts the binary in ``{venv}/Scripts`` (Windows)
    or ``{venv}/bin`` (POSIX). SecondBrain Desktop bundles its engine
    under ``{install}/engine/Scripts/`` with site-packages directly at
    ``{install}/engine/Lib/site-packages/`` (no ``pyvenv.cfg`` because
    embedded Python distributions don't ship one). Both are accepted.

    For ``~/.local/bin/`` shims (where ``shutil.which`` may land), resolve
    the symlink target first, then fall back to common pipx venv roots.
    """
    try:
        binary = binary.resolve()
    except OSError:
        pass
    parent = binary.parent
    if parent.name.lower() in {"scripts", "bin"}:
        candidate = parent.parent
        if _looks_like_install_root(candidate):
            return candidate

    for fallback in _pipx_default_venvs():
        if fallback.is_dir():
            return fallback
    return None


def _read_version_from_metadata(venv_root: Path) -> str | None:
    """Read the installed ``memory-kit-mcp`` version from its dist-info."""
    if sys.platform == "win32":
        site_packages = venv_root / "Lib" / "site-packages"
    else:
        site_packages = venv_root / "lib"
        if site_packages.is_dir():
            # Find python3.X subdir.
            for child in site_packages.iterdir():
                if child.is_dir() and child.name.startswith("python"):
                    site_packages = child / "site-packages"
                    break

    if not site_packages.is_dir():
        return None

    candidates = list(site_packages.glob("memory_kit_mcp-*.dist-info"))
    if not candidates:
        return None
    metadata = candidates[0] / "METADATA"
    if not metadata.is_file():
        return None
    try:
        text = metadata.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("could not read pipx METADATA: %s", exc)
        return None
    match = _VERSION_LINE.search(text)
    if not match:
        return None
    return match.group(1).strip()


def _probe_pipx_once() -> tuple[str | None, str | None]:
    """Locate the pipx binary and read its version from dist-info metadata.

    Cached for the session. Never spawns a subprocess: a Pydantic +
    FastMCP cold start on Windows can exceed 10 s, which is unacceptable
    UX for an icon refresh.
    """
    global _pipx_probe_cache
    if _pipx_probe_cache is not None:
        return _pipx_probe_cache

    binary_str = shutil.which("memory-kit-mcp")

    if binary_str is None:
        # If not on PATH, probe the canonical install locations directly.
        # This avoids false warnings in GUI apps that don't source shell PATH.
        from . import path_env, paths

        candidates = [
            paths.user_engine_scripts_dir() / "memory-kit-mcp",
            paths.system_engine_scripts_dir() / "memory-kit-mcp",
            path_env.user_local_bin() / "memory-kit-mcp",
            path_env.system_local_bin() / "memory-kit-mcp",
        ]
        if sys.platform == "win32":
            candidates = [
                paths.user_engine_scripts_dir() / "memory-kit-mcp.exe",
                paths.system_engine_scripts_dir() / "memory-kit-mcp.exe",
            ]

        for cand in candidates:
            if cand.is_file():
                binary_str = str(cand)
                break

    if binary_str is None:
        _pipx_probe_cache = (None, None)
        return _pipx_probe_cache

    binary = Path(binary_str)
    venv_root = _venv_root_from_binary(binary)
    if venv_root is None:
        log.warning("could not derive venv root from %s", binary)
        _pipx_probe_cache = (binary_str, None)
        return _pipx_probe_cache

    version = _read_version_from_metadata(venv_root)
    _pipx_probe_cache = (binary_str, version)
    return _pipx_probe_cache


def invalidate_pipx_cache() -> None:
    """Force the next probe to re-run — e.g. after an update."""
    global _pipx_probe_cache
    _pipx_probe_cache = None


def probe_status() -> StatusSnapshot:
    """Compose the current status snapshot. Always returns; never raises."""
    bundled, bundled_err = _bundled_version()
    if bundled is None:
        return StatusSnapshot(
            level=StatusLevel.ERROR,
            summary="Bundled engine missing — broken install.",
            error=bundled_err,
        )

    pipx_path_str, pipx_version = _probe_pipx_once()
    pipx_path = Path(pipx_path_str) if pipx_path_str else None

    if pipx_path is None:
        return StatusSnapshot(
            level=StatusLevel.WARNING,
            summary="Engine not found. Run the wizard to install the Memory Kit.",
            bundled_version=bundled,
        )

    # Check if it's on the PATH of the current process
    on_path = shutil.which("memory-kit-mcp") is not None

    if pipx_version is None:
        return StatusSnapshot(
            level=StatusLevel.WARNING,
            summary="Engine binary present but its version probe failed.",
            bundled_version=bundled,
            pipx_binary_path=pipx_path,
        )

    versions_match = pipx_version == bundled
    if not versions_match:
        return StatusSnapshot(
            level=StatusLevel.WARNING,
            summary=(
                f"Desktop bundles v{bundled}, but the installed engine is "
                f"v{pipx_version}. Run an update to align them."
            ),
            bundled_version=bundled,
            pipx_binary_path=pipx_path,
            pipx_version=pipx_version,
            versions_match=False,
        )

    if not on_path:
        return StatusSnapshot(
            level=StatusLevel.OK,
            summary=(
                f"Engine v{bundled} ready. (Note: using absolute path as "
                "it is not on your shell's PATH)."
            ),
            bundled_version=bundled,
            pipx_binary_path=pipx_path,
            pipx_version=pipx_version,
            versions_match=True,
        )

    return StatusSnapshot(
        level=StatusLevel.OK,
        summary=f"Engine v{bundled} ready.",
        bundled_version=bundled,
        pipx_binary_path=pipx_path,
        pipx_version=pipx_version,
        versions_match=True,
    )
