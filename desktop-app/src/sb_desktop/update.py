"""Update check + run flow — in-process check, single subprocess for run.

The version check now calls ``memory_kit_mcp.update_check.check_for_update``
directly. No subprocess, no JSON-RPC: ~10 ms when the GitHub cache is
warm (1 h default TTL), ~500 ms otherwise.

The actual update run is the only subprocess in the desktop app's
steady state — and only happens once, when the user explicitly
confirms an update via the dialog. We invoke the kit's deploy script
(``deploy.ps1 -AutoUpdate`` on Windows, ``deploy.sh --auto-update``
elsewhere) with :data:`subprocess.CREATE_NO_WINDOW` on Windows so the
shell window stays hidden.

``run_update`` is opt-in: callers must pass ``confirmed=True``. Without
the explicit flag we return the plan without executing — that's the
interlock the UI relies on to surface a confirmation dialog first.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .config import load_kit_config

log = logging.getLogger(__name__)

RUN_TIMEOUT = 600


class UpdateCheckResult(BaseModel):
    """Outcome of a non-mutating version check."""

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
            return (
                f"Update failed (rc={self.returncode}): "
                f"{self.error or self.stderr_tail[:200]}"
            )
        return "Update completed successfully."


def _silent_subprocess_kwargs() -> dict[str, Any]:
    if sys.platform != "win32":
        return {}
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
    }


def check_update(*, force_refresh: bool = False) -> UpdateCheckResult:
    """In-process version probe. Cached by the engine itself (1 h default)."""
    try:
        from memory_kit_mcp.update_check import check_for_update
    except ImportError as exc:
        return UpdateCheckResult(ok=False, error=f"bundled engine missing: {exc}")

    try:
        info = check_for_update(force_refresh=force_refresh)
    except Exception as exc:
        log.exception("check_for_update raised: %s", exc)
        return UpdateCheckResult(ok=False, error=f"engine raised: {exc}")

    last_checked_iso = (
        datetime.fromtimestamp(info.last_checked, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )

    return UpdateCheckResult(
        ok=info.error is None or info.error == "opt-out",
        update_available=info.update_available,
        current_version=info.current_version,
        latest_version=info.latest_version,
        error=info.error,
        last_checked_iso=last_checked_iso,
        summary_md=(
            f"v{info.current_version}"
            + (f" → v{info.latest_version}" if info.update_available else "")
        ),
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
    """Execute the deploy script. Hard interlock on ``confirmed``."""
    plan = plan_update()
    if not plan.can_run:
        return UpdateRunResult(
            ok=False, confirmed=confirmed, plan=plan, error=plan.blocker
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
            **_silent_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return UpdateRunResult(
            ok=False, confirmed=True, plan=plan, error=str(exc)
        )

    # The pipx binary may have been replaced — invalidate the cached probe so
    # the next status refresh reads the new version instead of the stale one.
    try:
        from .status import invalidate_pipx_cache

        invalidate_pipx_cache()
    except ImportError:
        pass

    return UpdateRunResult(
        ok=completed.returncode == 0,
        confirmed=True,
        plan=plan,
        returncode=completed.returncode,
        stdout_tail=(completed.stdout or "")[-2000:],
        stderr_tail=(completed.stderr or "")[-2000:],
        error=(
            None
            if completed.returncode == 0
            else f"deploy script returned {completed.returncode}"
        ),
    )
