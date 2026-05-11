"""Kit installer — orchestrates the engine install + MCP wiring.

The desktop app is responsible for the end-to-end install experience.
The user is never expected to open a PowerShell terminal, type
``deploy.ps1`` themselves, or know what pipx is.

Strategy (V0.5 — first iteration):

* Detect which LLM CLIs are installed locally (so we can show the user
  what will be wired up).
* Invoke the bundled ``deploy.ps1`` (Windows) or ``deploy.sh``
  (macOS/Linux) as a single subprocess with ``CREATE_NO_WINDOW`` and
  the user's choices passed as flags. The script already encapsulates
  every supported CLI, pipx bootstrap, version handling, and idempotent
  config injection — re-implementing that in Python would just create
  a second source of drift.
* Stream the script's stdout/stderr back to the caller line-by-line so
  the wizard's progress page can render real-time output.

A later iteration may replace the subprocess call with an in-process
Python implementation; the public functions below already hide the
details so the wizard UI does not need to change.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

log = logging.getLogger(__name__)


@dataclass
class LlmCliInfo:
    """A single LLM CLI target the kit can wire MCP into."""

    identifier: str
    label: str
    description: str
    binary_on_path: bool = False
    config_present: bool = False
    config_path: Path | None = None

    @property
    def installed(self) -> bool:
        return self.binary_on_path or self.config_present


# Tuples of (identifier, label, description, binary_name, candidate config
# directories as **paths relative to $HOME**). Resolved at call time inside
# :func:`detect_llm_clis` so tests can monkeypatch ``Path.home()`` to a tmp
# directory without the import-time values shadowing it.
_CLI_CHECKS: list[tuple[str, str, str, str | None, list[tuple[str, ...]]]] = [
    (
        "claude-code",
        "Claude Code CLI",
        "Anthropic's terminal LLM (`claude` command).",
        "claude",
        [(".claude",)],
    ),
    (
        "claude-desktop",
        "Claude Desktop",
        "Anthropic's Mac / Windows desktop app.",
        None,
        [
            ("AppData", "Roaming", "Claude"),
            ("Library", "Application Support", "Claude"),
            (".config", "Claude"),
        ],
    ),
    (
        "codex",
        "Codex CLI",
        "OpenAI's terminal LLM.",
        "codex",
        [(".codex",)],
    ),
    (
        "gemini-cli",
        "Gemini CLI",
        "Google's terminal LLM.",
        "gemini",
        [(".gemini",)],
    ),
    (
        "mistral-vibe",
        "Mistral Vibe",
        "Mistral's terminal LLM.",
        "vibe",
        [(".vibe",)],
    ),
    (
        "copilot-cli",
        "GitHub Copilot CLI",
        "Microsoft's terminal LLM (`gh copilot`).",
        "gh",
        [
            ("AppData", "Local", "github-copilot"),
            (".config", "github-copilot"),
        ],
    ),
]


def detect_llm_clis() -> list[LlmCliInfo]:
    """Probe every known CLI target and report what we find.

    A target is considered installed if its binary is on PATH OR its
    config directory exists locally (same heuristic deploy.ps1 uses).
    """
    home = Path.home()
    results: list[LlmCliInfo] = []
    for ident, label, descr, binary, candidate_segments in _CLI_CHECKS:
        has_binary = bool(binary and shutil.which(binary))
        config_path: Path | None = None
        for segments in candidate_segments:
            candidate = home.joinpath(*segments)
            if candidate.is_dir():
                config_path = candidate
                break
        results.append(
            LlmCliInfo(
                identifier=ident,
                label=label,
                description=descr,
                binary_on_path=has_binary,
                config_present=config_path is not None,
                config_path=config_path,
            )
        )
    return results


@dataclass
class InstallPlan:
    vault: Path
    language: str
    kit_repo: Path
    detected_clis: list[LlmCliInfo] = field(default_factory=list)

    @property
    def installed_clis(self) -> list[LlmCliInfo]:
        return [c for c in self.detected_clis if c.installed]


@dataclass
class InstallReport:
    ok: bool
    returncode: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str | None = None


def _silent_subprocess_kwargs() -> dict[str, object]:
    if sys.platform != "win32":
        return {}
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
    }


def _resolve_deploy_script(kit_repo: Path) -> tuple[Path | None, str]:
    if sys.platform == "win32":
        candidate = kit_repo / "deploy.ps1"
    else:
        candidate = kit_repo / "deploy.sh"
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


def find_bundled_kit_repo() -> Path | None:
    """Locate the kit source tree bundled by the installer.

    The Inno Setup ``installer.iss`` lays kit files under
    ``{app}/kit/``. In a PyInstaller one-dir bundle, ``sys.executable``
    is the launcher under ``{app}/SecondBrainTray.exe``; in a one-file
    bundle PyInstaller extracts to a temp dir and ``sys._MEIPASS`` is
    set — but ``{app}/kit/`` is still alongside the original launcher.

    Falls back to ``MEMORY_KIT_REPO`` env (dev convenience) and finally
    to the desktop-app's parent directory (running from a source
    checkout).
    """
    candidates: list[Path] = []

    env_override = os.environ.get("MEMORY_KIT_REPO")
    if env_override:
        candidates.append(Path(env_override).expanduser())

    # PyInstaller bundle: kit lives at {app}/kit alongside the launcher.
    exe = Path(sys.executable).resolve()
    candidates.append(exe.parent / "kit")
    candidates.append(exe.parent.parent / "kit")  # in case of nested layout

    # Source checkout fallback: desktop-app/../
    here = Path(__file__).resolve()
    candidates.append(here.parents[3])

    for candidate in candidates:
        if (candidate / "deploy.ps1").is_file() or (candidate / "deploy.sh").is_file():
            return candidate
    return None


def run_install(
    plan: InstallPlan,
    on_line: Callable[[str], None] | None = None,
    *,
    timeout: int = 900,
) -> InstallReport:
    """Execute the deploy script with the user's choices, streaming output.

    ``on_line`` is called once per line of combined stdout/stderr. The
    wizard plugs it into a Text widget to render progress live. We
    deliberately merge the two streams so the order matches what the
    user would see in a real terminal.
    """
    script, blocker = _resolve_deploy_script(plan.kit_repo)
    if script is None:
        return InstallReport(ok=False, error=blocker)

    interpreter, leading_args, interp_blocker = _resolve_interpreter()
    if interpreter is None:
        return InstallReport(ok=False, error=interp_blocker)

    args: list[str] = [*leading_args, str(script)]
    if sys.platform == "win32":
        args.extend(["-VaultPath", str(plan.vault), "-Language", plan.language])
    else:
        args.extend(["--vault-path", str(plan.vault), "--language", plan.language])

    cmd = [interpreter, *args]
    log.info("running deploy script: %s", " ".join(cmd))

    try:
        proc = subprocess.Popen(  # noqa: S603 — args fully controlled
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **_silent_subprocess_kwargs(),  # type: ignore[arg-type]
        )
    except OSError as exc:
        return InstallReport(ok=False, error=str(exc))

    collected: list[str] = []

    def _pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            stripped = line.rstrip("\n")
            collected.append(stripped)
            if on_line is not None:
                try:
                    on_line(stripped)
                except Exception as exc:
                    log.warning("on_line callback raised: %s", exc)

    pumper = threading.Thread(target=_pump, daemon=True)
    pumper.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return InstallReport(
            ok=False,
            error=f"deploy script timed out after {timeout}s",
        )
    pumper.join(timeout=5)

    tail = "\n".join(collected[-200:])

    # Invalidate the cached pipx probe so the next status refresh sees
    # the freshly-installed binary version.
    try:
        from .status import invalidate_pipx_cache

        invalidate_pipx_cache()
    except ImportError:
        pass

    return InstallReport(
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        stdout_tail=tail,
        error=(
            None
            if proc.returncode == 0
            else f"deploy script returned {proc.returncode}"
        ),
    )


def default_vault_path() -> Path:
    """Sensible default vault location for first-run users.

    ``~/Documents/SecondBrain`` works on Windows (Documents is a real
    folder), macOS (~ /Documents is conventional), and Linux (created
    on demand). Avoids dot-folders so the user can find it in a file
    manager.
    """
    return Path.home() / "Documents" / "SecondBrain"


def ensure_vault_exists(path: Path) -> None:
    """Create the vault directory if absent. Safe to call repeatedly."""
    path.expanduser().mkdir(parents=True, exist_ok=True)
