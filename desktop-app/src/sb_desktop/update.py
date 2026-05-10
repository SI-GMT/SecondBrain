"""Update check + run flow.

The check is delegated to ``mem_check_update`` (it owns the GitHub API
cache and version comparison). The actual update run shells out to the
kit's deploy script — which one depends on platform:

* Windows: ``deploy.ps1 -AutoUpdate`` (PowerShell) — invoked via ``pwsh``
  if available, otherwise ``powershell``.
* macOS / Linux: ``deploy.sh --auto-update`` (Bash).

Both deploy scripts already implement the ``git pull && reinstall``
sequence idempotently. We never duplicate that logic here; the desktop
app is a thin caller.

The ``run_update`` flow is **opt-in**: callers must pass an explicit
``confirmed=True`` flag to actually run. Passing without confirmation
returns a planned result describing what would happen — that's what the
tray menu surfaces before showing the confirmation dialog.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .config import load_kit_config
from .mcp_client import McpError, McpResponse, McpUnavailable, call_tool

log = logging.getLogger(__name__)

CHECK_TIMEOUT = 30
RUN_TIMEOUT = 600


class UpdateCheckResult(BaseModel):
    """Outcome of a non-mutating ``mem_check_update`` call."""

    ok: bool
    update_available: bool = False
    current_version: str | None = None
    latest_version: str | None = None
    error: str | None = None
    last_checked_iso: str | None = None
    summary_md: str = ""

    def render_text(self) -> str:
        if not self.ok:
            return f"Update check failed: {self.error or 'unknown error'}"
        if self.update_available:
            return (
                f"Update available: v{self.current_version} → "
                f"v{self.latest_version}"
            )
        return f"Up to date (v{self.current_version})."


class UpdateRunPlan(BaseModel):
    """Pre-flight description of an update execution."""

    can_run: bool
    deploy_script: Path | None = None
    interpreter: str | None = None
    args: list[str] = Field(default_factory=list)
    blocker: str | None = None

    def render_text(self) -> str:
        if not self.can_run:
            return f"Cannot run update: {self.blocker}"
        return f"Would run: {self.interpreter} {self.deploy_script} {' '.join(self.args)}"


class UpdateRunResult(BaseModel):
    """Outcome of an actual update execution."""

    ok: bool
    confirmed: bool
    plan: UpdateRunPlan
    returncode: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str | None = None

    def render_text(self) -> str:
        if not self.confirmed:
            return self.plan.render_text() + "\n(awaiting confirmation)"
        if not self.ok:
            return f"Update failed (rc={self.returncode}): {self.error or self.stderr_tail[:200]}"
        return "Update completed successfully."


def check_update(*, force_refresh: bool = False) -> UpdateCheckResult:
    """Query the engine for update status. Cached 1h server-side by default."""
    response = call_tool(
        "mem_check_update",
        {"force_refresh": force_refresh},
        timeout=CHECK_TIMEOUT,
    )

    if isinstance(response, McpUnavailable):
        return UpdateCheckResult(
            ok=False,
            error="Memory Kit engine is not installed.",
            summary_md="Install the kit then retry.",
        )
    if isinstance(response, McpError):
        return UpdateCheckResult(ok=False, error=response.message)

    assert isinstance(response, McpResponse)
    payload: dict[str, Any] = response.structured or {}
    return UpdateCheckResult(
        ok=True,
        update_available=bool(payload.get("update_available", False)),
        current_version=payload.get("current_version"),
        latest_version=payload.get("latest_version"),
        error=payload.get("error"),
        last_checked_iso=payload.get("last_checked_iso"),
        summary_md=response.text,
    )


def _resolve_deploy_script() -> tuple[Path | None, str]:
    kit = load_kit_config()
    if kit is None or not kit.kit_repo_exists:
        return None, "kit_repo not configured in ~/.memory-kit/config.json"
    assert kit.kit_repo is not None

    if sys.platform == "win32":
        candidate = kit.kit_repo / "deploy.ps1"
    else:
        candidate = kit.kit_repo / "deploy.sh"
    if not candidate.is_file():
        return None, f"deploy script not found at {candidate}"
    return candidate, ""


def _resolve_interpreter() -> tuple[str | None, list[str], str]:
    """Pick the right shell + flags for the current platform."""
    if sys.platform == "win32":
        for cmd in ("pwsh", "powershell"):
            path = shutil.which(cmd)
            if path:
                return path, ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"], ""
        return None, [], "neither pwsh nor powershell found on PATH"
    bash = shutil.which("bash") or "/bin/bash"
    return bash, [], ""


def plan_update() -> UpdateRunPlan:
    script, blocker = _resolve_deploy_script()
    if script is None:
        return UpdateRunPlan(can_run=False, blocker=blocker)
    interpreter, leading_args, interp_blocker = _resolve_interpreter()
    if interpreter is None:
        return UpdateRunPlan(can_run=False, blocker=interp_blocker)
    flag = "-AutoUpdate" if sys.platform == "win32" else "--auto-update"
    return UpdateRunPlan(
        can_run=True,
        deploy_script=script,
        interpreter=interpreter,
        args=[*leading_args, str(script), flag],
    )


def run_update(*, confirmed: bool = False) -> UpdateRunResult:
    """Execute the deploy script. Refuses to run unless ``confirmed=True``.

    The ``confirmed`` gate is a hard interlock: even if the UI dialog is
    skipped (programmatic invocation), this function will not run unless
    the caller is explicit. This matches the project rule "auto-update
    must be confirm-then-run".
    """
    plan = plan_update()
    if not plan.can_run:
        return UpdateRunResult(
            ok=False,
            confirmed=confirmed,
            plan=plan,
            error=plan.blocker,
        )
    if not confirmed:
        return UpdateRunResult(ok=False, confirmed=False, plan=plan)

    cmd = [plan.interpreter or "", *plan.args]
    log.info("running update: %s", " ".join(cmd))
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUN_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return UpdateRunResult(
            ok=False,
            confirmed=True,
            plan=plan,
            error=str(exc),
        )

    return UpdateRunResult(
        ok=completed.returncode == 0,
        confirmed=True,
        plan=plan,
        returncode=completed.returncode,
        stdout_tail=(completed.stdout or "")[-2000:],
        stderr_tail=(completed.stderr or "")[-2000:],
        error=None if completed.returncode == 0 else f"deploy script returned {completed.returncode}",
    )
