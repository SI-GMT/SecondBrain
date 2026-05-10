"""Locator + invoker for the Memory Kit MCP engine binary.

The desktop app never imports ``memory_kit_mcp`` — that would couple our
release cadence to the kit's. Instead we shell out to the installed binary
(via pipx, the bundled installer, or a developer's ``uv run``) and parse
JSON output.

Resolution order for the binary path:

1. ``MEMORY_KIT_MCP_BIN`` environment variable (lets a dev point at
   ``mcp-server/.venv/Scripts/memory-kit-mcp.exe`` for live work).
2. PATH lookup for ``memory-kit-mcp`` / ``memory-kit-mcp.exe``.
3. Default pipx install location (Windows: ``%USERPROFILE%/pipx/venvs/...``,
   POSIX: ``~/.local/pipx/venvs/...``) — last-resort fallback for users who
   don't have pipx exports on PATH.

Returns ``None`` when nothing is found; the caller (status / health /
update modules) is expected to surface that as "engine not installed"
rather than crashing.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

ENV_OVERRIDE = "MEMORY_KIT_MCP_BIN"
BIN_BASENAME = "memory-kit-mcp"
SUBPROCESS_TIMEOUT = 30


def _exe_name() -> str:
    return f"{BIN_BASENAME}.exe" if sys.platform == "win32" else BIN_BASENAME


def _candidate_pipx_paths() -> list[Path]:
    home = Path.home()
    if sys.platform == "win32":
        roots = [
            home / "pipx" / "venvs" / "memory-kit-mcp" / "Scripts",
            home / ".local" / "pipx" / "venvs" / "memory-kit-mcp" / "Scripts",
        ]
    else:
        roots = [
            home / ".local" / "pipx" / "venvs" / "memory-kit-mcp" / "bin",
            home / ".local" / "share" / "pipx" / "venvs" / "memory-kit-mcp" / "bin",
        ]
    return [r / _exe_name() for r in roots]


def locate_binary() -> Path | None:
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return candidate
        log.warning("%s points to %s but file not found", ENV_OVERRIDE, candidate)

    on_path = shutil.which(BIN_BASENAME)
    if on_path:
        return Path(on_path)

    for candidate in _candidate_pipx_paths():
        if candidate.is_file():
            return candidate

    return None


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured stdout/stderr + exit code, with parsing helpers."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_engine(args: list[str], timeout: int = SUBPROCESS_TIMEOUT) -> CommandResult | None:
    """Invoke the engine binary with ``args``. Returns ``None`` if the
    binary can't be located.
    """
    binary = locate_binary()
    if binary is None:
        return None
    try:
        completed = subprocess.run(
            [str(binary), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.error("engine subprocess failed: %s", exc)
        return CommandResult(returncode=-1, stdout="", stderr=str(exc))

    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
