"""Kit installer — pure Python orchestrator (V0.7 multi-user).

The end-to-end install flow lives here. No PowerShell, no
``deploy.ps1`` invocation: each step is a Python function the wizard
calls in order. The V0.6 single-user architecture is preserved as a
special case; V0.7 adds detection of system-wide installs so RDP
multi-user setups can share one engine.

Two install modes are supported, distinguished by where the running
Tray executable lives:

* **System install** — engine + binaries under ``%ProgramFiles%\\
  SecondBrain\\``, read-only for non-admin users. Engine bootstrap
  (Python embeddable extract + pip install) is run **once at install
  time by Inno Setup**, not by each user's wizard. Every per-user
  wizard run skips those steps and only does the per-user setup
  (vault picker + ``~/.memory-kit/config.json`` + MCP wiring).
* **User install** — engine + binaries under ``%LOCALAPPDATA%\\
  SecondBrain\\``. The wizard does the bootstrap because the user
  owns the install location.

```
{install_dir}\\
  app\\
    SecondBrainTray.exe
  engine\\
    python\\        Python embeddable runtime (~30 MB extracted)
    wheels\\        Pre-built memory-kit-mcp + transitive deps (offline)
    Lib\\           site-packages produced by pip install
    Scripts\\       memory-kit-mcp.exe + entry-points (added to user PATH)
    get-pip.py     Bootstrap script
  resources\\
    core\\          Procedures source-of-truth
    adapters\\      Skill templates
    i18n\\          Translation strings
```

Steps the wizard chains:

1. :func:`bootstrap_python_embeddable` — patches the embeddable's
   ``._pth`` file so ``Lib/site-packages`` is on ``sys.path``, then
   runs ``get-pip.py`` once.
2. :func:`install_kit_wheels` — ``python.exe -m pip install --no-index
   --find-links wheels memory-kit-mcp``. Offline install; the user
   doesn't need network access.
3. :func:`register_path` — appends ``{install_dir}/engine/Scripts`` to
   the user PATH (HKCU on Windows, rc files elsewhere) so the LLM
   CLIs can spawn ``memory-kit-mcp.exe``.
4. :func:`finalise_kit_config` — writes ``~/.memory-kit/config.json``
   with the user's vault path, language, and the bundled
   ``resources/`` directory as ``kit_repo``.
5. :func:`wire_llm_clis` — calls the JSON / TOML / TOML-array
   injectors in :mod:`sb_desktop.mcp_injector` for every selected
   target.

Each step returns a small status object the wizard renders inline.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import config as _config
from . import mcp_injector, paths, vault_setup
from .mcp_injector import InjectResult
from .path_env import (
    add_to_system_path,
    add_to_user_path,
    is_admin_windows,
)
from .paths import InstallMode

log = logging.getLogger(__name__)

EMBEDDABLE_ZIP_BASENAME = "python-embed.zip"
GET_PIP_BASENAME = "get-pip.py"
KIT_RESOURCES_BASENAME = "resources"
ENGINE_BASENAME = "engine"
APP_BASENAME = "app"
WHEELS_BASENAME = "wheels"

ProgressCallback = Callable[[str], None] | None


# ---------------------------------------------------------------------------
# Detected LLM CLIs (used by the wizard's checkbox page).
# ---------------------------------------------------------------------------


@dataclass
class LlmCliInfo:
    """One LLM client we know how to wire MCP into."""

    identifier: str
    label: str
    description: str
    config_writer: str  # 'json' | 'codex-toml' | 'vibe-toml'
    config_path_segments: tuple[str, ...]
    binary_name: str | None = None
    detection_segments: tuple[tuple[str, ...], ...] = ()
    binary_on_path: bool = False
    config_present: bool = False
    config_path: Path | None = None

    @property
    def installed(self) -> bool:
        return self.binary_on_path or self.config_present


def _cli_targets() -> list[LlmCliInfo]:
    """Canonical list — same set deploy.ps1 wires."""
    return [
        LlmCliInfo(
            identifier="claude-code",
            label="Claude Code CLI",
            description="Anthropic's terminal LLM (`claude` command).",
            config_writer="json",
            config_path_segments=(".claude.json",),
            binary_name="claude",
            detection_segments=((".claude",), (".claude.json",)),
        ),
        LlmCliInfo(
            identifier="claude-desktop",
            label="Claude Desktop",
            description="Anthropic's Mac / Windows desktop app.",
            config_writer="json",
            config_path_segments=(),  # resolved per-OS in _resolve_config_path
            detection_segments=(
                ("AppData", "Roaming", "Claude"),
                ("Library", "Application Support", "Claude"),
                (".config", "Claude"),
            ),
        ),
        LlmCliInfo(
            identifier="codex",
            label="Codex CLI",
            description="OpenAI's terminal LLM.",
            config_writer="codex-toml",
            config_path_segments=(".codex", "config.toml"),
            binary_name="codex",
            detection_segments=((".codex",),),
        ),
        LlmCliInfo(
            identifier="gemini-cli",
            label="Gemini CLI",
            description="Google's terminal LLM.",
            config_writer="json",
            config_path_segments=(".gemini", "settings.json"),
            binary_name="gemini",
            detection_segments=((".gemini",),),
        ),
        LlmCliInfo(
            identifier="mistral-vibe",
            label="Mistral Vibe",
            description="Mistral's terminal LLM.",
            config_writer="vibe-toml",
            config_path_segments=(".vibe", "config.toml"),
            binary_name="vibe",
            detection_segments=((".vibe",),),
        ),
        LlmCliInfo(
            identifier="copilot-cli",
            label="GitHub Copilot CLI",
            description="Microsoft's terminal LLM (`gh copilot`).",
            config_writer="json",
            config_path_segments=(),  # resolved per-OS
            binary_name="gh",
            detection_segments=(
                ("AppData", "Local", "github-copilot"),
                (".config", "github-copilot"),
            ),
        ),
    ]


def _resolve_config_path(cli: LlmCliInfo) -> Path | None:
    """Return the canonical config path for a CLI on the current host."""
    home = Path.home()
    if cli.identifier == "claude-desktop":
        if sys.platform == "win32":
            return home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
        if sys.platform == "darwin":
            return (
                home
                / "Library"
                / "Application Support"
                / "Claude"
                / "claude_desktop_config.json"
            )
        return home / ".config" / "Claude" / "claude_desktop_config.json"
    if cli.identifier == "copilot-cli":
        if sys.platform == "win32":
            return (
                home / "AppData" / "Local" / "github-copilot" / "mcp-config.json"
            )
        return home / ".config" / "github-copilot" / "mcp-config.json"
    if cli.config_path_segments:
        return home.joinpath(*cli.config_path_segments)
    return None


def detect_llm_clis() -> list[LlmCliInfo]:
    """Run the install detection heuristics and return enriched info."""
    home = Path.home()
    targets = _cli_targets()
    for cli in targets:
        if cli.binary_name:
            cli.binary_on_path = bool(shutil.which(cli.binary_name))
        for segments in cli.detection_segments:
            candidate = home.joinpath(*segments)
            if candidate.is_dir() or candidate.is_file():
                cli.config_present = True
                cli.config_path = candidate
                break
        # The "config_path" we store on the info is the detection probe; the
        # actual file we write to is computed separately in
        # ``_resolve_config_path`` so it always lands at the canonical path.
    return targets


# ---------------------------------------------------------------------------
# Install layout helpers.
# ---------------------------------------------------------------------------


@dataclass
class InstallLayout:
    """Resolved on-disk paths for a given install root."""

    install_dir: Path
    app_dir: Path
    engine_dir: Path
    python_dir: Path
    wheels_dir: Path
    scripts_dir: Path
    site_packages_dir: Path
    resources_dir: Path
    mode: InstallMode = InstallMode.USER

    @classmethod
    def from_install_dir(
        cls, install_dir: Path, mode: InstallMode | None = None
    ) -> "InstallLayout":
        """Build a layout, auto-detecting ``mode`` from ``install_dir`` if omitted.

        Auto-detection probes the canonical install roots
        (``%ProgramFiles%[\\ SecondBrain]``, ``%LOCALAPPDATA%[\\ SecondBrain]``)
        and falls back to a writability check on the engine directory
        for unknown layouts (read-only → SYSTEM). This keeps callers
        from passing the wrong mode and tripping the wizard's safety
        rails — a real bug we hit when the wizard ran a USER-default
        install flow against a Program Files install.
        """
        install_dir = install_dir.resolve()
        if mode is None:
            mode = paths.detect_install_mode(install_dir / APP_BASENAME / "ignored.exe")
        engine = install_dir / ENGINE_BASENAME
        return cls(
            install_dir=install_dir,
            app_dir=install_dir / APP_BASENAME,
            engine_dir=engine,
            python_dir=engine / "python",
            wheels_dir=engine / WHEELS_BASENAME,
            scripts_dir=engine / "Scripts",
            site_packages_dir=engine / "Lib" / "site-packages",
            resources_dir=install_dir / KIT_RESOURCES_BASENAME,
            mode=mode,
        )

    @property
    def kit_binary_path(self) -> Path:
        if sys.platform == "win32":
            return self.scripts_dir / "memory-kit-mcp.exe"
        return self.scripts_dir / "memory-kit-mcp"

    @property
    def python_exe(self) -> Path:
        if sys.platform == "win32":
            return self.python_dir / "python.exe"
        return self.python_dir / "bin" / "python"

    @property
    def engine_already_bootstrapped(self) -> bool:
        """True if the engine binary is already in place — skip pip install."""
        return self.kit_binary_path.is_file()

    @property
    def is_system_install(self) -> bool:
        return self.mode == InstallMode.SYSTEM


def find_install_layout() -> InstallLayout | None:
    """Locate the install layout for a running ``SecondBrainTray.exe``.

    The PyInstaller bundle launcher lives at ``{install}/app/SecondBrainTray.exe``,
    so ``sys.executable``'s grandparent is the install root. The
    install mode is inferred from the path (system / user / dev).
    """
    mode = paths.detect_install_mode()
    exe = Path(sys.executable).resolve()
    if exe.parent.name == APP_BASENAME:
        return InstallLayout.from_install_dir(exe.parent.parent, mode=mode)
    # Source checkout fallback for dev — return the desktop-app/ for tests.
    here = Path(__file__).resolve()
    return InstallLayout.from_install_dir(here.parents[3], mode=InstallMode.DEV)


# ---------------------------------------------------------------------------
# Step 1 — bootstrap the embedded Python (extract, patch _pth, run get-pip).
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    ok: bool
    label: str
    detail: str = ""


def _silent_subprocess_kwargs() -> dict[str, object]:
    if sys.platform != "win32":
        return {}
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
    }


def _python_dir_writable(python_dir: Path) -> bool:
    """True if the current process can create a file inside ``python_dir``.

    Probes by writing a temp file. We can't trust ``os.access`` on
    Windows — ACL inheritance lies — so we actually try the write.
    """
    if not python_dir.is_dir():
        return False
    probe = python_dir / ".secondbrain_write_probe.tmp"
    try:
        probe.write_text("", encoding="ascii")
    except (OSError, PermissionError):
        return False
    try:
        probe.unlink()
    except OSError:
        pass
    return True


def _patch_pth_file(python_dir: Path) -> None:
    """Make the embedded Python find ``Lib/site-packages``.

    The default ``pythonNNN._pth`` ships with ``#import site`` commented out
    and no reference to ``Lib/site-packages``. We enable both so a normal
    pip-install layout works.
    """
    pth_files = sorted(python_dir.glob("python*._pth"))
    if not pth_files:
        return
    pth = pth_files[0]
    lines = pth.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []
    has_site_packages = False
    for line in lines:
        stripped = line.strip()
        if stripped == "#import site":
            new_lines.append("import site")
        else:
            new_lines.append(line)
        if "Lib\\site-packages" in line or "Lib/site-packages" in line:
            has_site_packages = True
    if not has_site_packages:
        new_lines.append("..\\Lib\\site-packages")
        new_lines.append("..\\Scripts")
    pth.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def bootstrap_python_embeddable(
    layout: InstallLayout, on_progress: ProgressCallback = None
) -> StepResult:
    """Prepare the embedded Python so pip can install into Lib/site-packages.

    System install: the elevated installer owns the engine. The
    per-user wizard NEVER touches anything under ``engine_dir``,
    regardless of whether the engine looks ready. If the engine is
    actually missing we surface a clean actionable error instead of
    crashing on a PermissionError.

    User install: we own the engine. Patch the ``_pth`` file and run
    ``get-pip`` if needed.
    """
    if layout.is_system_install:
        if layout.engine_already_bootstrapped:
            if on_progress:
                on_progress("System engine already bootstrapped (skip).")
            return StepResult(
                ok=True,
                label="Bootstrap Python runtime",
                detail="skipped (system install, engine ready)",
            )
        return StepResult(
            ok=False,
            label="Bootstrap Python runtime",
            detail=(
                "engine not installed under "
                f"{layout.engine_dir} — re-run the SecondBrain installer "
                "as administrator to deploy the engine, then relaunch this "
                "wizard."
            ),
        )

    # ----- User install only past this point -----
    if not layout.python_exe.is_file():
        return StepResult(
            ok=False,
            label="Bootstrap Python runtime",
            detail=f"python executable not found at {layout.python_exe}",
        )

    if not _python_dir_writable(layout.python_dir):
        # Defensive: if detection mis-classified a Program Files-style
        # install as USER, refuse to attempt writes that will fail.
        return StepResult(
            ok=False,
            label="Bootstrap Python runtime",
            detail=(
                f"engine directory {layout.python_dir} is read-only for "
                "the current user — re-run the installer as administrator "
                "(system install) or pick a user-writable install location."
            ),
        )

    if on_progress:
        on_progress("Patching python _pth file…")
    try:
        _patch_pth_file(layout.python_dir)
    except OSError as exc:
        return StepResult(
            ok=False,
            label="Bootstrap Python runtime",
            detail=f"_pth patch failed: {exc}",
        )

    pip_marker = layout.scripts_dir / ("pip.exe" if sys.platform == "win32" else "pip")
    get_pip = layout.engine_dir / GET_PIP_BASENAME
    if not pip_marker.is_file() and get_pip.is_file():
        if on_progress:
            on_progress("Bootstrapping pip…")
        try:
            completed = subprocess.run(
                [str(layout.python_exe), str(get_pip), "--no-warn-script-location"],
                cwd=str(layout.engine_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
                **_silent_subprocess_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return StepResult(
                ok=False, label="Bootstrap pip", detail=str(exc)
            )
        if completed.returncode != 0:
            return StepResult(
                ok=False,
                label="Bootstrap pip",
                detail=(completed.stderr or completed.stdout)[-800:],
            )

    return StepResult(ok=True, label="Bootstrap Python runtime")


# ---------------------------------------------------------------------------
# Step 2 — pip install memory-kit-mcp from the bundled wheels (offline).
# ---------------------------------------------------------------------------


def install_kit_wheels(
    layout: InstallLayout, on_progress: ProgressCallback = None
) -> StepResult:
    if layout.is_system_install:
        # Wheels were installed by the elevated installer (or by an admin
        # re-run of the installer). The per-user wizard NEVER attempts to
        # pip-install under Program Files.
        if layout.engine_already_bootstrapped:
            if on_progress:
                on_progress("System wheels already installed (skip).")
            return StepResult(
                ok=True,
                label="Install kit wheels",
                detail="skipped (system install, engine ready)",
            )
        return StepResult(
            ok=False,
            label="Install kit wheels",
            detail=(
                f"engine binary missing at {layout.kit_binary_path} — "
                "the elevated installer did not finish bootstrapping the "
                "engine. Re-run setup as administrator."
            ),
        )
    if not _python_dir_writable(layout.engine_dir):
        return StepResult(
            ok=False,
            label="Install kit wheels",
            detail=(
                f"engine directory {layout.engine_dir} is read-only for "
                "the current user — re-run the installer as administrator."
            ),
        )
    if not layout.wheels_dir.is_dir():
        return StepResult(
            ok=False,
            label="Install kit wheels",
            detail=f"wheels directory missing: {layout.wheels_dir}",
        )
    if on_progress:
        on_progress("Installing memory-kit-mcp from bundled wheels…")
    try:
        completed = subprocess.run(
            [
                str(layout.python_exe),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(layout.wheels_dir),
                "--no-warn-script-location",
                "memory-kit-mcp",
            ],
            cwd=str(layout.engine_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
            **_silent_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return StepResult(ok=False, label="Install kit wheels", detail=str(exc))

    if completed.returncode != 0:
        return StepResult(
            ok=False,
            label="Install kit wheels",
            detail=(completed.stderr or completed.stdout)[-1200:],
        )

    if not layout.kit_binary_path.is_file():
        return StepResult(
            ok=False,
            label="Install kit wheels",
            detail=(
                f"pip install succeeded but {layout.kit_binary_path} is missing — "
                "check the bundled wheel exposes the memory-kit-mcp entry point."
            ),
        )
    return StepResult(ok=True, label="Install kit wheels")


# ---------------------------------------------------------------------------
# Step 3 — register the engine's Scripts dir on the user PATH.
# ---------------------------------------------------------------------------


def register_path(
    layout: InstallLayout, on_progress: ProgressCallback = None
) -> StepResult:
    """Ensure the engine binary is reachable from PATH on every OS.

    Windows
        System install + admin → HKLM PATH.
        System install non-admin → HKCU fallback (safety net).
        User install → HKCU.

    POSIX
        System install with root → symlink ``memory-kit-mcp`` into
        ``/usr/local/bin/``. Falls back to per-user ``~/.local/bin``
        + rc-file block if root is refused.
        User install → ``~/.local/bin`` symlink + rc-file block.

    The POSIX symlink layer is what makes the engine visible to GUI
    apps (Claude Desktop, etc.) that don't source shell rc files.
    """
    if on_progress:
        on_progress("Registering the engine on your PATH…")

    binary = layout.kit_binary_path if layout.kit_binary_path.is_file() else None

    if layout.is_system_install:
        if is_admin_windows() or sys.platform != "win32":
            try:
                changed = add_to_system_path(layout.scripts_dir, binary=binary)
                detail = "appended to system PATH" if changed else "already on system PATH"
                return StepResult(ok=True, label="Register PATH", detail=detail)
            except PermissionError:
                pass  # Fall through to per-user.
        try:
            changed = add_to_user_path(layout.scripts_dir, binary=binary)
        except Exception as exc:
            return StepResult(
                ok=False,
                label="Register PATH",
                detail=f"PATH update failed: {exc}",
            )
        detail = "appended to user PATH (no admin/root for system PATH)"
        if not changed:
            detail = "already on user PATH"
        return StepResult(ok=True, label="Register PATH", detail=detail)

    try:
        changed = add_to_user_path(layout.scripts_dir, binary=binary)
    except Exception as exc:
        return StepResult(
            ok=False, label="Register PATH", detail=f"PATH update failed: {exc}"
        )
    return StepResult(
        ok=True,
        label="Register PATH",
        detail="appended" if changed else "already on PATH",
    )


# ---------------------------------------------------------------------------
# Step 4 — write the kit's config.json.
# ---------------------------------------------------------------------------


def finalise_kit_config(
    layout: InstallLayout,
    vault: Path,
    language: str,
    on_progress: ProgressCallback = None,
) -> StepResult:
    if on_progress:
        on_progress("Writing ~/.memory-kit/config.json…")
    try:
        target = mcp_injector.write_kit_config(
            vault=vault,
            kit_repo=layout.resources_dir if layout.resources_dir.is_dir() else None,
            language=language,
        )
    except Exception as exc:
        return StepResult(
            ok=False, label="Kit config", detail=f"write failed: {exc}"
        )
    return StepResult(ok=True, label="Kit config", detail=str(target))


# ---------------------------------------------------------------------------
# Step 5 — wire MCP into each selected LLM CLI.
# ---------------------------------------------------------------------------


@dataclass
class WiringReport:
    label: str
    config_path: Path
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status != "skipped"


def wire_llm_clis(
    layout: InstallLayout,
    selected: list[LlmCliInfo],
    on_progress: ProgressCallback = None,
) -> list[WiringReport]:
    """Run the right injector for each selected target."""
    results: list[WiringReport] = []
    for cli in selected:
        if on_progress:
            on_progress(f"Configuring {cli.label}…")
        target = _resolve_config_path(cli)
        if target is None:
            results.append(
                WiringReport(
                    label=cli.label,
                    config_path=Path(),
                    status="skipped",
                    detail="no canonical config path resolved",
                )
            )
            continue
        if cli.config_writer == "json":
            result = mcp_injector.inject_json_mcp_server(
                target, target_label=cli.label
            )
        elif cli.config_writer == "codex-toml":
            result = mcp_injector.inject_codex_mcp_server(
                target, target_label=cli.label
            )
        elif cli.config_writer == "vibe-toml":
            result = mcp_injector.inject_vibe_mcp_server(
                target, target_label=cli.label
            )
        else:
            results.append(
                WiringReport(
                    label=cli.label,
                    config_path=target,
                    status="skipped",
                    detail=f"unknown writer: {cli.config_writer}",
                )
            )
            continue
        results.append(
            WiringReport(
                label=result.target_label,
                config_path=result.config_path,
                status=result.status.value,
                detail=result.detail,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Orchestrator — the wizard calls this for an end-to-end install.
# ---------------------------------------------------------------------------


@dataclass
class InstallPlan:
    vault: Path
    language: str
    install_dir: Path
    selected_clis: list[LlmCliInfo] = field(default_factory=list)


@dataclass
class InstallReport:
    ok: bool
    steps: list[StepResult] = field(default_factory=list)
    wiring: list[WiringReport] = field(default_factory=list)
    error: str | None = None

    def first_failure(self) -> StepResult | None:
        for step in self.steps:
            if not step.ok:
                return step
        return None


def default_vault_path() -> Path:
    return Path.home() / "Documents" / "SecondBrain"


def ensure_vault_exists(path: Path) -> None:
    path.expanduser().mkdir(parents=True, exist_ok=True)


def prepare_vault(
    layout: InstallLayout,
    new_vault: Path,
    *,
    on_progress: ProgressCallback = None,
) -> StepResult:
    """Migrate the existing vault if any, then scaffold ``new_vault``.

    Reads the canonical vault path from ``~/.memory-kit/config.json``.
    If it points at a non-empty directory **different** from
    ``new_vault``, every entry is moved into the new location before
    the Obsidian scaffold is laid out. Otherwise we just scaffold the
    target directory (creates it if missing).
    """
    if on_progress:
        on_progress("Preparing vault contents…")

    existing = _config.load_kit_config()
    old_vault = existing.vault.expanduser() if existing else None

    obsidian_style = layout.resources_dir / "adapters" / "obsidian-style"
    obsidian_style_dir = obsidian_style if obsidian_style.is_dir() else None

    try:
        result = vault_setup.setup_vault(
            new_vault.expanduser(),
            old_vault=old_vault,
            obsidian_style_dir=obsidian_style_dir,
        )
    except OSError as exc:
        return StepResult(
            ok=False,
            label="Prepare vault",
            detail=f"vault setup failed: {exc}",
        )
    return StepResult(
        ok=True,
        label="Prepare vault",
        detail=result.detail or result.action,
    )


def run_install(
    plan: InstallPlan, on_progress: ProgressCallback = None
) -> InstallReport:
    """Execute every step in order, short-circuit on the first failure."""
    layout = InstallLayout.from_install_dir(plan.install_dir)
    report = InstallReport(ok=True)

    for step in (
        bootstrap_python_embeddable(layout, on_progress),
        install_kit_wheels(layout, on_progress),
        register_path(layout, on_progress),
        prepare_vault(layout, plan.vault, on_progress=on_progress),
        finalise_kit_config(layout, plan.vault, plan.language, on_progress),
    ):
        report.steps.append(step)
        if not step.ok:
            report.ok = False
            report.error = f"{step.label}: {step.detail}"
            return report

    report.wiring = wire_llm_clis(layout, plan.selected_clis, on_progress)
    failed_wiring = [w for w in report.wiring if not w.ok]
    if failed_wiring:
        report.ok = False
        report.error = (
            f"{len(failed_wiring)} of {len(report.wiring)} CLI(s) could not be wired."
        )
    return report
