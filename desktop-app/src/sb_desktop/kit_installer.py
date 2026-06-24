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
import os
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
    """One LLM client we know how to wire MCP into.

    ``binary_name`` is the primary executable name we probe; alt names
    in ``binary_aliases`` cover the same CLI shipped under a different
    bin (e.g. ``gh-copilot`` next to ``gh``, ``codex.cmd`` on Windows
    when installed via npm).
    """

    identifier: str
    label: str
    description: str
    config_writer: str  # 'json' | 'codex-toml' | 'vibe-toml'
    config_path_segments: tuple[str, ...]
    binary_name: str | None = None
    binary_aliases: tuple[str, ...] = ()
    npm_package: str | None = None
    detection_segments: tuple[tuple[str, ...], ...] = ()
    binary_on_path: bool = False
    binary_path: Path | None = None
    config_present: bool = False
    config_path: Path | None = None

    @property
    def installed(self) -> bool:
        return self.binary_on_path or self.config_present


def _cli_targets() -> list[LlmCliInfo]:
    """Canonical list — same set deploy.ps1 wires.

    ``npm_package`` declarations cover the case where the CLI was
    installed via ``npm install -g …`` and lives in the user's npm
    global prefix rather than on the system PATH.
    """
    return [
        LlmCliInfo(
            identifier="claude-code",
            label="Claude Code CLI",
            description="Anthropic's terminal LLM (`claude` command).",
            config_writer="json",
            config_path_segments=(".claude.json",),
            binary_name="claude",
            binary_aliases=("claude.cmd", "claude.exe", "claude.ps1"),
            npm_package="@anthropic-ai/claude-code",
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
            binary_aliases=("codex.cmd", "codex.exe"),
            npm_package="@openai/codex",
            detection_segments=((".codex",),),
        ),
        LlmCliInfo(
            identifier="gemini-cli",
            label="Gemini CLI",
            description="Google's terminal LLM.",
            config_writer="json",
            config_path_segments=(".gemini", "settings.json"),
            binary_name="gemini",
            binary_aliases=("gemini.cmd", "gemini.exe", "gemini.ps1"),
            npm_package="@google/gemini-cli",
            detection_segments=((".gemini",),),
        ),
        LlmCliInfo(
            identifier="mistral-vibe",
            label="Mistral Vibe",
            description="Mistral's terminal LLM.",
            config_writer="vibe-toml",
            config_path_segments=(".vibe", "config.toml"),
            binary_name="vibe",
            binary_aliases=("vibe.cmd", "vibe.exe"),
            npm_package="@mistralai/vibe-cli",
            detection_segments=((".vibe",),),
        ),
        LlmCliInfo(
            identifier="copilot-cli",
            label="GitHub Copilot CLI",
            description="GitHub's terminal LLM (`copilot` / `gh copilot`).",
            config_writer="json",
            config_path_segments=(),  # resolved per-OS below
            # The new `copilot` v1+ binary is the canonical Copilot CLI;
            # the legacy `gh copilot` extension reuses the same config
            # directory and is still detected for back-compat.
            binary_name="copilot",
            binary_aliases=(
                "copilot.exe",
                "copilot.cmd",
                "gh",
                "gh.exe",
                "gh.cmd",
                "gh-copilot",
                "gh-copilot.exe",
            ),
            npm_package="@github/copilot-cli",
            # Canonical config dir is ``~/.copilot/`` on every platform
            # (same source-of-truth deploy.ps1 / deploy.sh use). The
            # legacy ``AppData\Local\github-copilot`` location was a
            # gh-copilot extension artefact, kept as a fallback probe.
            detection_segments=(
                (".copilot",),
                ("AppData", "Local", "github-copilot"),
                (".config", "github-copilot"),
            ),
        ),
        LlmCliInfo(
            identifier="opendesign",
            label="OpenDesign",
            description="OpenDesign application.",
            config_writer="json",
            config_path_segments=(".od", "mcp-config.json"),
            detection_segments=((".od",),),
        ),
        LlmCliInfo(
            identifier="antigravity-cli",
            label="Antigravity CLI",
            description="Gemini-based terminal LLM (`agy` command).",
            config_writer="json",
            config_path_segments=(".gemini", "antigravity-cli", "mcp_config.json"),
            binary_name="agy",
            binary_aliases=("agy.cmd", "agy.exe", "agy.ps1"),
            detection_segments=((".gemini", "antigravity-cli"),),
        ),
        LlmCliInfo(
            identifier="antigravity-desktop",
            label="Antigravity Desktop",
            description="Gemini-based desktop agent app.",
            config_writer="json",
            config_path_segments=(".gemini", "antigravity", "mcp_config.json"),
            detection_segments=((".gemini", "antigravity"),),
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
        # Canonical path per kit's deploy.ps1: ~/.copilot/mcp-config.json
        # (matches the dir GitHub's `copilot` CLI v1+ creates on first
        # run). ``$COPILOT_HOME`` env override is respected so power
        # users can move the dir.
        import os

        override = os.environ.get("COPILOT_HOME")
        if override:
            return Path(override) / "mcp-config.json"
        return home / ".copilot" / "mcp-config.json"
    if cli.identifier == "opendesign":
        if sys.platform == "darwin":
            # Le desktop OpenDesign sur macOS stocke sa config ici
            desktop_path = (
                home
                / "Library"
                / "Application Support"
                / "Open Design"
                / "namespaces"
                / "release-stable"
                / "data"
                / "mcp-config.json"
            )
            if desktop_path.exists():
                return desktop_path
        # Fallback générique pour la CLI ou autres OS
        return home / ".od" / "mcp-config.json"

    if cli.config_path_segments:
        return home.joinpath(*cli.config_path_segments)
    return None


def _npm_global_bin_dirs() -> list[Path]:
    """Best-effort enumeration of NPM global ``bin`` directories.

    Many LLM CLIs ship via ``npm install -g`` (Claude Code, Gemini CLI,
    Codex CLI, Copilot CLI, …) and land outside the default PATH on
    many systems — especially fresh Windows boxes where ``%APPDATA%
    \\npm`` isn't on PATH yet.

    Probes, in order:

    1. ``npm config get prefix`` (canonical answer) — synchronous
       subprocess, ~50 ms when ``npm`` is on PATH; otherwise skipped.
    2. Common defaults: ``%APPDATA%\\npm`` (Windows), ``~/.npm-global``,
       ``~/.npm-global/bin``, ``/usr/local/bin`` (POSIX system NPM),
       ``/opt/homebrew/bin`` (Apple Silicon Homebrew).
    3. Any explicit ``NPM_CONFIG_PREFIX`` env var override.

    Returns absolute directories that actually exist on disk —
    de-duplicated and ordered so the highest-precedence probe wins.
    """
    home = Path.home()
    raw: list[Path] = []

    npm_path = shutil.which("npm") or shutil.which("npm.cmd")
    if npm_path:
        try:
            completed = subprocess.run(
                [npm_path, "config", "get", "prefix"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
                **_silent_subprocess_kwargs(),
            )
            if completed.returncode == 0:
                prefix = Path(completed.stdout.strip())
                if sys.platform == "win32":
                    raw.append(prefix)  # npm.cmd lives directly under prefix
                else:
                    raw.append(prefix / "bin")
        except (OSError, subprocess.TimeoutExpired):
            pass

    env_prefix = os.environ.get("NPM_CONFIG_PREFIX")
    if env_prefix:
        p = Path(env_prefix)
        raw.append(p if sys.platform == "win32" else p / "bin")

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            raw.append(Path(appdata) / "npm")
    else:
        raw.extend([
            home / ".npm-global" / "bin",
            home / ".npm-packages" / "bin",
            Path("/usr/local/bin"),
            Path("/opt/homebrew/bin"),
            Path("/opt/local/bin"),
        ])

    seen: set[str] = set()
    out: list[Path] = []
    for candidate in raw:
        if not candidate:
            continue
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_dir():
            out.append(resolved)
    return out


def _alt_install_dirs() -> list[Path]:
    """Common non-NPM install dirs worth probing for CLI binaries.

    Pure-platform installers (Anthropic's macOS pkg, GitHub CLI's
    Windows MSI, Homebrew, …) sometimes drop binaries outside the
    user's PATH on first install. We probe these too so the wizard
    sees the CLI even before the user has refreshed their shell.
    """
    home = Path.home()
    out: list[Path] = []
    if sys.platform == "win32":
        for env in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base:
                out.extend([
                    Path(base) / "GitHub CLI",
                    Path(base) / "Programs" / "Claude",
                ])
        out.append(home / "AppData" / "Local" / "Programs" / "claude")
    elif sys.platform == "darwin":
        out.extend([
            Path("/Applications/Claude.app/Contents/MacOS"),
            Path("/usr/local/bin"),
            Path("/opt/homebrew/bin"),
        ])
    else:
        out.extend([
            Path("/usr/local/bin"),
            Path("/usr/bin"),
            home / ".local" / "bin",
        ])
    return [p for p in out if p.is_dir()]


def _find_binary(cli: LlmCliInfo, extra_dirs: list[Path]) -> Path | None:
    """Return the absolute path of the CLI binary if findable.

    Search order:

    1. ``shutil.which`` against the primary name (PATH-respecting).
    2. ``shutil.which`` against each alias (covers ``.cmd`` / ``.exe``
       suffixes Windows needs to disambiguate, plus the ``copilot``
       alias for GitHub Copilot CLI v1+).
    3. Direct probe of ``extra_dirs`` (NPM globals + alt install
       roots) for the primary and aliases.
    """
    if not cli.binary_name:
        return None

    candidates = [cli.binary_name, *cli.binary_aliases]
    for name in candidates:
        hit = shutil.which(name)
        if hit:
            return Path(hit)

    for directory in extra_dirs:
        for name in candidates:
            candidate = directory / name
            if candidate.is_file():
                return candidate.resolve()
    return None


def detect_llm_clis() -> list[LlmCliInfo]:
    """Run the install detection heuristics and return enriched info.

    Detection sources, combined:

    * Direct binary on PATH + aliases (``shutil.which`` for both the
      canonical name and platform variants like ``claude.cmd`` /
      ``claude.exe``).
    * NPM global bin directories (``npm config get prefix`` +
      ``%APPDATA%\\npm`` / ``~/.npm-global/bin`` / …) so users who
      installed via ``npm install -g`` are picked up even when their
      shell PATH lags.
    * Common alt install dirs (Program Files\\GitHub CLI,
      ``/Applications/Claude.app/Contents/MacOS``, ``/opt/homebrew/bin``,
      …).
    * Home-directory probes (``~/.claude``, ``~/.codex``, …) — the
      strongest signal a CLI was actually used at least once.

    A CLI counts as ``installed`` if EITHER the binary was found OR
    a config / home directory exists for it.
    """
    home = Path.home()
    targets = _cli_targets()
    extra_dirs = _npm_global_bin_dirs() + _alt_install_dirs()
    for cli in targets:
        binary_path = _find_binary(cli, extra_dirs)
        if binary_path is not None:
            cli.binary_on_path = True
            cli.binary_path = binary_path
        for segments in cli.detection_segments:
            candidate = home.joinpath(*segments)
            if candidate.is_dir() or candidate.is_file():
                cli.config_present = True
                cli.config_path = candidate
                break
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

    # macOS/V2 decoupling: where the assets are bundled (read-only)
    # vs where they are installed (writable).
    source_resources_dir: Path | None = None
    source_engine_dir: Path | None = None

    @classmethod
    def from_install_dir(
        cls,
        install_dir: Path,
        mode: InstallMode | None = None,
        source_dir: Path | None = None,
    ) -> "InstallLayout":
        """Build a layout, auto-detecting ``mode`` from ``install_dir`` if omitted."""
        install_dir = install_dir.resolve()
        if mode is None:
            mode = paths.detect_install_mode(install_dir / APP_BASENAME / "ignored.exe")

        engine = install_dir / ENGINE_BASENAME
        resources = install_dir / KIT_RESOURCES_BASENAME

        source_engine = None
        source_resources = None

        if source_dir:
            source_engine = source_dir / ENGINE_BASENAME
            source_resources = source_dir / KIT_RESOURCES_BASENAME

        # macOS USER install: suggested engine/resources location is in Application Support
        # to ensure it's writable even if the .app was placed in a restricted folder
        # or to avoid polluting the .app bundle.
        if sys.platform == "darwin" and mode == InstallMode.USER:
            support = paths.app_data_dir()
            # If we were not given an explicit source_dir, the install_dir (Contents)
            # is our asset source.
            if not source_engine:
                source_engine = engine
            if not source_resources:
                source_resources = resources

            engine = support / ENGINE_BASENAME
            resources = support / KIT_RESOURCES_BASENAME

        if sys.platform == "win32":
            scripts = engine / "Scripts"
            site_pkgs = engine / "Lib" / "site-packages"
        else:
            scripts = engine / "bin"
            # On POSIX, pip install --prefix lands in lib/pythonX.Y/site-packages
            # but for a simplified embedded layout we might want to stay flat.
            # However, the standard is lib/python<version>/site-packages.
            # POC: use 'lib' for now, matching the most common layout.
            site_pkgs = engine / "lib"

        return cls(
            install_dir=install_dir,
            app_dir=install_dir / APP_BASENAME,
            engine_dir=engine,
            python_dir=engine / "python",
            wheels_dir=engine / WHEELS_BASENAME,
            scripts_dir=scripts,
            site_packages_dir=site_pkgs,
            resources_dir=resources,
            mode=mode,
            source_engine_dir=source_engine,
            source_resources_dir=source_resources,
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

        bundled = self.python_dir / "bin" / "python"
        if bundled.is_file():
            return bundled

        # Source fallback: in DEV mode, the running interpreter is the best bet.
        if self.mode == InstallMode.DEV:
            return Path(sys.executable)

        # Production fallback on macOS/Linux: check if python3 is on PATH.
        # This allows the wizard to run even if we didn't bundle a full
        # portable Python distribution yet (V1 limitation).
        import shutil

        system_py = shutil.which("python3")
        if system_py:
            return Path(system_py)

        return bundled

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

    # Windows layout: {install}/app/SecondBrainTray.exe
    if exe.parent.name == APP_BASENAME:
        return InstallLayout.from_install_dir(exe.parent.parent, mode=mode)

    # macOS layout: {install}/SecondBrain.app/Contents/MacOS/SecondBrainTray
    if sys.platform == "darwin" and exe.parent.name == "MacOS" and exe.parents[1].name == "Contents":
        # On macOS, we can bundle engine/ and resources/ inside Contents/
        return InstallLayout.from_install_dir(exe.parents[1], mode=mode)

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


def stage_assets(
    layout: InstallLayout, on_progress: ProgressCallback = None
) -> StepResult:
    """Copy bundled assets to the target engine/resources dirs (macOS)."""
    if not layout.source_engine_dir and not layout.source_resources_dir:
        return StepResult(ok=True, label="Stage assets", detail="skipped (same location)")

    # Engine
    if layout.source_engine_dir and layout.source_engine_dir.is_dir():
        if on_progress:
            on_progress(f"Staging engine to {layout.engine_dir}…")
        try:
            if layout.engine_dir.exists():
                shutil.rmtree(layout.engine_dir)
            layout.engine_dir.parent.mkdir(parents=True, exist_ok=True)
            # Only copy wheels for now on macOS (no full portable python yet)
            wheels_src = layout.source_engine_dir / WHEELS_BASENAME
            if wheels_src.is_dir():
                layout.wheels_dir.mkdir(parents=True, exist_ok=True)
                for whl in wheels_src.glob("*.whl"):
                    shutil.copy2(whl, layout.wheels_dir / whl.name)
        except OSError as exc:
            return StepResult(ok=False, label="Stage assets", detail=f"engine copy failed: {exc}")

    # Resources
    if layout.source_resources_dir and layout.source_resources_dir.is_dir():
        if on_progress:
            on_progress(f"Staging resources to {layout.resources_dir}…")
        try:
            if layout.resources_dir.exists():
                shutil.rmtree(layout.resources_dir)
            layout.resources_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(layout.source_resources_dir, layout.resources_dir)
        except OSError as exc:
            return StepResult(ok=False, label="Stage assets", detail=f"resources copy failed: {exc}")

    return StepResult(ok=True, label="Stage assets", detail="OK")


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


def _engine_command(layout: InstallLayout) -> str:
    """Return the command string we inject into every MCP target.

    Prefer the **absolute** path of the engine binary so spawning
    succeeds regardless of the consuming process's PATH cache. On RDP
    or any session that pre-dated the install, the bare
    ``memory-kit-mcp`` lookup fails with "Connection closed" because
    the new PATH entry only reaches processes started AFTER the
    install's WM_SETTINGCHANGE broadcast.

    Falls back to the bare command name when the absolute path is
    unavailable (DEV layout, missing binary) so dev runs still work.
    """
    binary = layout.kit_binary_path
    if binary.is_file():
        return str(binary)
    return mcp_injector.DEFAULT_COMMAND


def wire_llm_clis(
    layout: InstallLayout,
    selected: list[LlmCliInfo],
    on_progress: ProgressCallback = None,
) -> list[WiringReport]:
    """Run the right injector for each selected target."""
    command = _engine_command(layout)
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
            # Copilot CLI requires extra fields (``type`` + ``tools``)
            # to actually register the server at runtime; without them
            # the entry parses but ``copilot mcp list`` ignores it.
            extras: dict | None = None
            if cli.identifier == "copilot-cli":
                extras = {"type": "local", "tools": ["*"]}
            result = mcp_injector.inject_json_mcp_server(
                target,
                target_label=cli.label,
                command=command,
                extra_entry_fields=extras,
            )
        elif cli.config_writer == "codex-toml":
            result = mcp_injector.inject_codex_mcp_server(
                target, target_label=cli.label, command=command
            )
        elif cli.config_writer == "vibe-toml":
            result = mcp_injector.inject_vibe_mcp_server(
                target, target_label=cli.label, command=command
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
        # Codex + Vibe expose tools but won't auto-approve them without an
        # explicit per-tool permission block (each in its own native schema).
        # JSON CLIs carry their allow-list inside the server entry already.
        perms_result: mcp_injector.InjectResult | None = None
        if cli.config_writer == "codex-toml":
            perms_result = mcp_injector.inject_codex_tool_permissions(
                target, target_label=cli.label
            )
        elif cli.config_writer == "vibe-toml":
            perms_result = mcp_injector.inject_vibe_tool_permissions(
                target, target_label=cli.label
            )
        if perms_result is not None:
            results.append(
                WiringReport(
                    label=f"{perms_result.target_label} (auto-approve)",
                    config_path=perms_result.config_path,
                    status=perms_result.status.value,
                    detail=perms_result.detail,
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
        stage_assets(layout, on_progress),
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
