"""Status snapshot for the Memory Kit engine.

Two-channel probe per V1 spec:

* **(a) Static probe** — locate the binary, read ``--version``. Cheap, no
  side effect, runs every poll cycle. Tells us whether the kit is installed
  at all and which version is on disk.

* **(b) Live probe** — spawn the binary in stdio mode and exchange a single
  JSON-RPC ``initialize`` round-trip. Slightly more expensive but proves
  the binary actually starts on this machine (catches dependency drift,
  sandbox issues, antivirus quarantine, etc.). Run on demand or periodically
  at a longer cadence than (a).

Snapshots are immutable Pydantic models so they can be serialised to disk
for the log viewer / settings dialog without further plumbing.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from .engine import locate_binary, run_engine

log = logging.getLogger(__name__)

LIVE_PROBE_TIMEOUT = 8


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
    binary_path: Path | None = None
    version: str | None = None
    live_probe_ok: bool | None = None
    live_probe_latency_ms: float | None = None
    error: str | None = None
    probed_at: float = Field(default_factory=time.time)

    def is_ok(self) -> bool:
        return self.level == StatusLevel.OK

    def render_text(self) -> str:
        lines = [f"Status: {self.level.value.upper()}", f"  {self.summary}"]
        if self.binary_path:
            lines.append(f"  Binary: {self.binary_path}")
        if self.version:
            lines.append(f"  Version: {self.version}")
        if self.live_probe_ok is not None:
            tag = "OK" if self.live_probe_ok else "FAILED"
            latency = (
                f" ({self.live_probe_latency_ms:.0f} ms)"
                if self.live_probe_latency_ms is not None
                else ""
            )
            lines.append(f"  Live probe: {tag}{latency}")
        if self.error:
            lines.append(f"  Error: {self.error}")
        return "\n".join(lines)


def _static_probe() -> tuple[Path | None, str | None, str | None]:
    """Return (binary_path, version, error)."""
    binary = locate_binary()
    if binary is None:
        return None, None, "memory-kit-mcp binary not found on PATH or pipx"

    result = run_engine(["--version"], timeout=10)
    if result is None:
        return None, None, "engine resolution disappeared between checks"
    if not result.ok:
        return binary, None, f"version probe failed: rc={result.returncode}"

    parsed = result.stdout.strip().split()
    version = parsed[-1] if parsed else None
    return binary, version, None


def _live_probe(binary: Path) -> tuple[bool, float | None, str | None]:
    """Open stdio, send a JSON-RPC initialize, await the response.

    The engine is a FastMCP stdio server — handshake is the standard MCP
    initialize / initialized exchange. We don't keep the connection open;
    the round-trip itself is the proof of life.
    """
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "sb-desktop", "version": "probe"},
        },
    }
    payload = (json.dumps(init_request) + "\n").encode("utf-8")

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [str(binary)],
            input=payload,
            capture_output=True,
            timeout=LIVE_PROBE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, None, "live probe timed out"
    except OSError as exc:
        return False, None, f"live probe spawn error: {exc}"

    elapsed_ms = (time.perf_counter() - started) * 1000

    out = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
    if not out.strip():
        err = completed.stderr.decode("utf-8", errors="replace") if completed.stderr else ""
        return False, elapsed_ms, f"empty response (stderr: {err[:200]!r})"

    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            continue
        if response.get("id") == 1 and "result" in response:
            return True, elapsed_ms, None
        if response.get("id") == 1 and "error" in response:
            return False, elapsed_ms, str(response["error"])

    return False, elapsed_ms, "no JSON-RPC response with id=1 in stdout"


def probe_status(*, run_live: bool = True) -> StatusSnapshot:
    """Combined static + (optional) live probe.

    Setting ``run_live=False`` is appropriate for the periodic poll loop
    where we only need to know "is the binary still there at the right
    version?". The user-triggered "Status" menu entry uses ``True`` for the
    full handshake.
    """
    binary, version, static_err = _static_probe()
    if static_err and binary is None:
        return StatusSnapshot(
            level=StatusLevel.ERROR,
            summary="Memory Kit engine is not installed.",
            error=static_err,
        )
    if static_err:
        return StatusSnapshot(
            level=StatusLevel.WARNING,
            summary="Engine binary present but not responding to --version.",
            binary_path=binary,
            error=static_err,
        )

    if not run_live:
        return StatusSnapshot(
            level=StatusLevel.OK,
            summary=f"Engine v{version} ready.",
            binary_path=binary,
            version=version,
        )

    assert binary is not None
    live_ok, latency, live_err = _live_probe(binary)
    if not live_ok:
        return StatusSnapshot(
            level=StatusLevel.WARNING,
            summary="Engine installed but live probe failed.",
            binary_path=binary,
            version=version,
            live_probe_ok=False,
            live_probe_latency_ms=latency,
            error=live_err,
        )
    return StatusSnapshot(
        level=StatusLevel.OK,
        summary=f"Engine v{version} responding ({latency:.0f} ms).",
        binary_path=binary,
        version=version,
        live_probe_ok=True,
        live_probe_latency_ms=latency,
    )
