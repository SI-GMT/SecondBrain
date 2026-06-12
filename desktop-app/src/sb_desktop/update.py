"""Update check + run flow — engine + desktop, in-process.

Two independent update channels, queried in parallel:

* **Engine** (``memory-kit-mcp``) — checked via
  ``memory_kit_mcp.update_check.check_for_update`` which now filters
  GitHub releases by the ``vX.Y.Z`` tag pattern. When an engine
  update is available we can apply it **in place** under the
  installed engine directory (no installer re-run, no Program Files
  touch from the user surface — we re-elevate via ``ShellExecute``
  ``runas`` if needed).
* **Desktop** (``sb-desktop``) — checked by ``check_desktop_update``
  which queries the same GitHub releases endpoint but filters for
  the ``sb-desktop-vX.Y.Z`` tag pattern. When a desktop update is
  available we download the bundled installer asset and the user
  validates with a single click; the installer's own ``InitializeSetup``
  handles the upgrade prompt + tray shutdown.

The UX contract for both flows:

1. Background check (1 h cache per channel) on tray launch and via the
   tray menu's "Check for updates" entry.
2. If an update is available, auto-download the asset (installer or
   wheel) to ``app_cache_dir()/downloads/`` so the user only waits at
   install time.
3. Prompt the user with a confirmation dialog. **No automatic install
   without explicit Yes.** ``confirmed=True`` interlock.
4. On confirm, launch the installer (desktop) or run pip --upgrade
   against the bundled engine (engine).

Engine updates skip a full installer re-run when the desktop bundle
itself hasn't changed — exactly the workflow the user asked for.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import paths
from .config import load_kit_config

log = logging.getLogger(__name__)

RUN_TIMEOUT = 600
HTTP_TIMEOUT_SECONDS = 5.0
DOWNLOAD_TIMEOUT_SECONDS = 120.0
USER_AGENT = "sb-desktop-update-checker"
GITHUB_RELEASES_URL = (
    "https://api.github.com/repos/SI-GMT/SecondBrain/releases?per_page=30"
)
_DESKTOP_TAG_RE = re.compile(r"^sb-desktop-v(\d+\.\d+\.\d+)$")
INSTALLER_ASSET_RE = re.compile(r"SecondBrainDesktop-[\d\.]+-setup\.exe$", re.I)
_ENGINE_TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+)$")
# Offline wheelhouse asset for in-place engine updates: a zip of memory_kit_mcp
# + all its transitive deps as cp312 win_amd64 wheels. Built per engine release
# (see desktop-app/build/build_engine_wheelhouse.ps1). Pinned, no PyPI needed.
ENGINE_WHEELHOUSE_RE = re.compile(
    r"memory_kit_mcp-[\d\.]+-wheelhouse-win_amd64\.zip$", re.I
)


class UpdateCheckResult(BaseModel):
    """Outcome of a non-mutating version check (one channel)."""

    channel: str = "engine"
    ok: bool
    update_available: bool = False
    current_version: str | None = None
    latest_version: str | None = None
    asset_url: str | None = None
    asset_filename: str | None = None
    error: str | None = None
    last_checked_iso: str | None = None
    summary_md: str = ""

    def render_text(self) -> str:
        prefix = self.channel.title()
        if not self.ok:
            return f"{prefix} update check failed: {self.error or 'unknown error'}"
        if self.update_available:
            return (
                f"{prefix} update available: v{self.current_version} → "
                f"v{self.latest_version}"
            )
        return f"{prefix} up to date (v{self.current_version})."


class CombinedUpdateInfo(BaseModel):
    """Both update channels in one snapshot."""

    engine: UpdateCheckResult
    desktop: UpdateCheckResult

    @property
    def any_available(self) -> bool:
        return self.engine.update_available or self.desktop.update_available

    @property
    def actionable_channels(self) -> list[str]:
        out: list[str] = []
        if self.desktop.update_available:
            out.append("desktop")
        if self.engine.update_available:
            out.append("engine")
        return out

    def render_text(self) -> str:
        lines = [self.engine.render_text(), self.desktop.render_text()]
        return "\n".join(lines)


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


def _fetch_engine_asset(version: str) -> tuple[str | None, str | None]:
    """Resolve the wheelhouse asset of the engine release ``v{version}``.

    Returns ``(asset_url, asset_filename)`` or ``(None, None)`` when the
    release has no matching wheelhouse asset (or the network call fails).
    Best-effort — never raises: the version check stays usable even when the
    asset lookup is unavailable.
    """
    import json as _json

    try:
        req = urllib.request.Request(
            GITHUB_RELEASES_URL,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310
            releases = _json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        log.warning("engine asset lookup failed: %s", exc)
        return None, None

    target_tag = f"v{version}"
    for entry in releases or []:
        if entry.get("tag_name") != target_tag:
            continue
        for asset in entry.get("assets") or []:
            name = asset.get("name", "")
            if ENGINE_WHEELHOUSE_RE.search(name):
                return asset.get("browser_download_url"), name
        break
    return None, None


def _installed_engine_version() -> str | None:
    """Read the on-disk version of the engine that the in-place update targets.

    ``check_for_update`` reports ``memory_kit_mcp.__version__`` — a module-level
    constant resolved once at import time, which never changes for the life of
    the tray process even after an in-place pip upgrade. That made the dialog's
    "Current" version freeze at the pre-update value.

    The engine the in-place update actually rewrites is the one under
    ``find_install_layout().engine_dir`` (the bootstrapped engine on PATH).
    Reading its ``dist-info`` METADATA fresh on every check makes "Current"
    reflect what is really on disk, so the display refreshes after an update
    (no tray restart). Returns ``None`` when there is no install layout
    (running from source / dev), so the caller falls back to the import-time
    version.
    """
    try:
        from . import kit_installer
        from .status import _read_version_from_metadata
    except ImportError:
        return None
    try:
        layout = kit_installer.find_install_layout()
        if layout is None:
            return None
        return _read_version_from_metadata(layout.engine_dir)
    except Exception as exc:  # never let a probe error break the version check
        log.debug("installed engine version probe failed: %s", exc)
        return None


def check_update(*, force_refresh: bool = False) -> UpdateCheckResult:
    """In-process version probe. Cached by the engine itself (1 h default).

    "Current" is read fresh from the on-disk engine the in-place update targets
    (not the frozen import-time ``__version__``) so the display reflects an
    applied update. When an update is available, also resolves the release's
    offline wheelhouse asset so the dialog can offer an in-place upgrade.
    """
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

    # Prefer the on-disk engine version over the frozen import-time one, and
    # recompute update availability against it.
    current = _installed_engine_version() or info.current_version
    update_available = info.update_available
    if info.latest_version:
        update_available = _is_newer(info.latest_version, current)

    asset_url: str | None = None
    asset_filename: str | None = None
    if update_available and info.latest_version:
        asset_url, asset_filename = _fetch_engine_asset(info.latest_version)

    return UpdateCheckResult(
        channel="engine",
        ok=info.error is None or info.error == "opt-out",
        update_available=update_available,
        current_version=current,
        latest_version=info.latest_version,
        asset_url=asset_url,
        asset_filename=asset_filename,
        error=info.error,
        last_checked_iso=last_checked_iso,
        summary_md=(
            f"v{current}"
            + (f" → v{info.latest_version}" if update_available else "")
        ),
    )


def _parse_version(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in v.strip().lstrip("v").split("."):
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


def _desktop_update_cache_path() -> Path:
    return paths.app_cache_dir() / "desktop-update.json"


def _read_desktop_cache(ttl_seconds: int) -> UpdateCheckResult | None:
    import json
    import time

    p = _desktop_update_cache_path()
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    cached_at = raw.get("_cached_at", 0.0)
    if ttl_seconds > 0 and (time.time() - cached_at) >= ttl_seconds:
        return None
    raw.pop("_cached_at", None)
    try:
        return UpdateCheckResult(**raw)
    except Exception:
        return None


def _write_desktop_cache(result: UpdateCheckResult) -> None:
    import json
    import time

    p = _desktop_update_cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = result.model_dump()
        payload["_cached_at"] = time.time()
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def _current_desktop_version() -> str:
    try:
        from sb_desktop import __version__

        return __version__
    except ImportError:
        return "0.0.0"


def check_desktop_update(*, force_refresh: bool = False) -> UpdateCheckResult:
    """Probe GitHub for the latest ``sb-desktop-vX.Y.Z`` release.

    Filters releases by tag pattern so engine tags (``vX.Y.Z``) do not
    spoof a desktop update. The first matching release's installer
    asset URL is returned alongside the version so the caller can
    download it without a second round-trip.

    Cached on disk (1 h TTL) so the GitHub API rate limit (60/h for
    anonymous calls) stays unburdened.
    """
    current = _current_desktop_version()
    if not force_refresh:
        cached = _read_desktop_cache(ttl_seconds=3600)
        if cached is not None:
            cached.current_version = current
            cached.update_available = bool(
                cached.latest_version and _is_newer(cached.latest_version, current)
            )
            return cached

    last_checked_iso = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    try:
        req = urllib.request.Request(
            GITHUB_RELEASES_URL,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310
            import json as _json

            releases = _json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return UpdateCheckResult(
            channel="desktop",
            ok=False,
            current_version=current,
            error=f"{type(exc).__name__}: {exc}",
            last_checked_iso=last_checked_iso,
        )

    latest_tag: str | None = None
    latest_version: str | None = None
    asset_url: str | None = None
    asset_filename: str | None = None
    for entry in releases or []:
        tag = entry.get("tag_name")
        if not isinstance(tag, str):
            continue
        m = _DESKTOP_TAG_RE.match(tag)
        if not m:
            continue
        latest_tag = tag
        latest_version = m.group(1)
        for asset in entry.get("assets") or []:
            name = asset.get("name", "")
            if INSTALLER_ASSET_RE.search(name):
                asset_url = asset.get("browser_download_url")
                asset_filename = name
                break
        break

    if latest_version is None:
        result = UpdateCheckResult(
            channel="desktop",
            ok=True,
            current_version=current,
            latest_version=None,
            update_available=False,
            error="no desktop release found",
            last_checked_iso=last_checked_iso,
        )
        _write_desktop_cache(result)
        return result

    result = UpdateCheckResult(
        channel="desktop",
        ok=True,
        update_available=_is_newer(latest_version, current),
        current_version=current,
        latest_version=latest_version,
        asset_url=asset_url,
        asset_filename=asset_filename,
        last_checked_iso=last_checked_iso,
        summary_md=(
            f"v{current}"
            + (f" → v{latest_version}" if _is_newer(latest_version, current) else "")
        ),
    )
    _write_desktop_cache(result)
    return result


def check_all_updates(*, force_refresh: bool = False) -> CombinedUpdateInfo:
    """Both channels in one snapshot — used by the tray menu + dialog."""
    return CombinedUpdateInfo(
        engine=check_update(force_refresh=force_refresh),
        desktop=check_desktop_update(force_refresh=force_refresh),
    )


# ---------------------------------------------------------------------------
# Asset downloader (installer / wheel)
# ---------------------------------------------------------------------------


def _downloads_dir() -> Path:
    target = paths.app_cache_dir() / "downloads"
    target.mkdir(parents=True, exist_ok=True)
    return target


@dataclass
class DownloadResult:
    """Outcome of a single asset download."""

    ok: bool
    path: Path | None = None
    bytes_written: int = 0
    sha256: str | None = None
    error: str | None = None
    skipped: bool = False  # True if cached file reused


ProgressCallback = "object"  # Callable[[int, int | None], None] | None


def download_asset(
    url: str,
    filename: str,
    *,
    timeout: float = DOWNLOAD_TIMEOUT_SECONDS,
    on_progress=None,
    expected_size: int | None = None,
) -> DownloadResult:
    """Stream ``url`` into ``app_cache_dir()/downloads/{filename}``.

    Idempotent: if a file with the same name already exists and its
    size matches ``expected_size`` (or any size when ``expected_size``
    is None), the cached copy is reused and ``skipped=True``. Useful
    when the user closes the dialog mid-download and re-opens later.

    ``on_progress(received, total)`` fires periodically (every ~256 KiB)
    so the UI can render a progress bar. ``total`` is the HTTP Content-
    Length when the server provides one, ``None`` otherwise.
    """
    target = _downloads_dir() / filename
    if target.is_file():
        size = target.stat().st_size
        if expected_size is None or size == expected_size:
            return DownloadResult(
                ok=True,
                path=target,
                bytes_written=size,
                sha256=_sha256_of(target),
                skipped=True,
            )
        # Stale partial download — fall through and re-fetch.
        try:
            target.unlink()
        except OSError:
            pass

    log.info("downloading %s -> %s", url, target)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            total_header = resp.headers.get("Content-Length")
            total = int(total_header) if total_header and total_header.isdigit() else None
            sha = hashlib.sha256()
            tmp = target.with_suffix(target.suffix + ".part")
            received = 0
            chunk_size = 256 * 1024
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    fh.write(chunk)
                    sha.update(chunk)
                    received += len(chunk)
                    if on_progress is not None:
                        try:
                            on_progress(received, total)
                        except Exception:
                            pass
        tmp.replace(target)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return DownloadResult(ok=False, error=f"{type(exc).__name__}: {exc}")

    return DownloadResult(
        ok=True,
        path=target,
        bytes_written=received,
        sha256=sha.hexdigest(),
    )


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(256 * 1024)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Apply: desktop installer launcher + engine in-place pip upgrade
# ---------------------------------------------------------------------------


@dataclass
class ApplyResult:
    ok: bool
    detail: str = ""
    error: str | None = None


def launch_desktop_installer(installer_path: Path) -> ApplyResult:
    """Spawn the downloaded installer and let Inno take it from there.

    The installer's ``InitializeSetup`` detects the existing install,
    prompts for confirmation, kills the tray and the running engine
    sessions, and runs the upgrade. We launch via ``ShellExecuteW`` so
    UAC is triggered when the installer requires admin (system install).

    Returns as soon as the spawn succeeds — the installer continues
    asynchronously. The tray will be terminated by the installer.
    """
    if not installer_path.is_file():
        return ApplyResult(
            ok=False,
            error=f"installer not found at {installer_path}",
        )
    if sys.platform == "win32":
        try:
            import ctypes

            SW_SHOWNORMAL = 1
            res = ctypes.windll.shell32.ShellExecuteW(
                None,
                "open",
                str(installer_path),
                None,
                str(installer_path.parent),
                SW_SHOWNORMAL,
            )
            if int(res) <= 32:
                return ApplyResult(
                    ok=False,
                    error=f"ShellExecuteW failed (code {int(res)})",
                )
            return ApplyResult(
                ok=True, detail=f"installer launched: {installer_path}"
            )
        except Exception as exc:
            return ApplyResult(
                ok=False, error=f"failed to launch installer: {exc}"
            )
    # POSIX: best-effort — most users won't install via .exe; macOS DMG
    # flow lives in the macOS build and is handled separately.
    try:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(installer_path)])
        return ApplyResult(ok=True, detail=f"opened {installer_path}")
    except Exception as exc:
        return ApplyResult(ok=False, error=f"failed to open installer: {exc}")


def install_engine_update(
    wheels_dir: Path,
    *,
    on_progress=None,
) -> ApplyResult:
    """Run pip --upgrade against the bundled engine.

    Resolves the engine layout via :func:`kit_installer.find_install_layout`,
    then invokes the embedded ``python.exe`` to ``pip install --upgrade
    --no-index --find-links {wheels_dir} --prefix {engine_dir} memory-kit-mcp``.

    If the engine is under a write-protected system install AND the
    current process is not elevated, we re-spawn the same command via
    ``ShellExecuteW`` with the ``runas`` verb so Windows triggers a
    UAC prompt — single click for the user, no second installer.

    Returns once pip finishes (synchronous). On Windows the elevated
    subprocess runs hidden via ``CREATE_NO_WINDOW``.
    """
    from . import kit_installer
    from .path_env import is_admin_windows

    layout = kit_installer.find_install_layout()
    if layout is None:
        return ApplyResult(ok=False, error="install layout could not be resolved")
    if not layout.python_exe.is_file():
        return ApplyResult(
            ok=False, error=f"python.exe not found at {layout.python_exe}"
        )

    pip_args = [
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--no-index",
        "--find-links",
        str(wheels_dir),
        "--no-warn-script-location",
        "--prefix",
        str(layout.engine_dir),
        "memory-kit-mcp",
    ]

    if (
        sys.platform == "win32"
        and layout.is_system_install
        and not is_admin_windows()
    ):
        # Re-elevate via ShellExecute runas — Windows prompts the user
        # with UAC. Cannot capture stdout this way, so we rely on
        # post-flight check of the engine version + binary presence.
        try:
            import ctypes

            params = " ".join(_quote_arg(a) for a in pip_args)
            SW_HIDE = 0
            res = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                str(layout.python_exe),
                params,
                str(layout.engine_dir),
                SW_HIDE,
            )
            if int(res) <= 32:
                return ApplyResult(
                    ok=False,
                    error=(
                        f"elevation failed (ShellExecuteW code {int(res)}) — "
                        "the engine update needs administrator rights to "
                        "write under Program Files"
                    ),
                )
            return ApplyResult(
                ok=True,
                detail=(
                    "elevated pip install launched (see UAC prompt); "
                    "engine version will refresh once the operation completes"
                ),
            )
        except Exception as exc:
            return ApplyResult(
                ok=False, error=f"re-elevation failed: {exc}"
            )

    cmd = [str(layout.python_exe), *pip_args]
    log.info("running engine update: %s", " ".join(cmd))
    if on_progress is not None:
        try:
            on_progress("Installing engine wheels…")
        except Exception:
            pass
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(layout.engine_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUN_TIMEOUT,
            check=False,
            **_silent_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ApplyResult(ok=False, error=f"pip launch failed: {exc}")

    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "")[-1200:]
        return ApplyResult(
            ok=False,
            error=f"pip exited {completed.returncode}: {tail}",
        )

    if not layout.kit_binary_path.is_file():
        return ApplyResult(
            ok=False,
            error=(
                f"pip install succeeded but {layout.kit_binary_path} is "
                "missing — re-run the full installer"
            ),
        )

    # Invalidate the status probe so the tray refreshes the version.
    try:
        from .status import invalidate_pipx_cache

        invalidate_pipx_cache()
    except ImportError:
        pass

    return ApplyResult(
        ok=True, detail=f"engine updated in place at {layout.engine_dir}"
    )


def _locate_wheels_dir(root: Path) -> Path | None:
    """Find the directory holding the ``*.whl`` files inside an extracted
    wheelhouse. Returns ``root`` when wheels sit at the top level, else the
    first sub-directory that contains at least one wheel, else ``None``.
    """
    if any(root.glob("*.whl")):
        return root
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        if any(sub.glob("*.whl")):
            return sub
    return None


def download_and_install_engine(
    asset_url: str,
    asset_filename: str,
    *,
    on_download=None,
    on_status=None,
) -> ApplyResult:
    """Download the offline wheelhouse, extract it, and pip-install in place.

    ``on_download(received, total)`` drives the download progress bar;
    ``on_status(message)`` surfaces the extract/install phases. Both are
    optional and best-effort. The wheelhouse is a zip of ``memory_kit_mcp`` +
    its transitive deps as wheels; extraction feeds ``install_engine_update``
    which runs ``pip install --no-index --find-links`` against the embedded
    python (offline, version-pinned).
    """
    import zipfile

    dl = download_asset(asset_url, asset_filename, on_progress=on_download)
    if not dl.ok or dl.path is None:
        return ApplyResult(ok=False, error=f"download failed: {dl.error}")

    if on_status is not None:
        try:
            on_status("Extracting wheelhouse…")
        except Exception:
            pass

    extract_dir = _downloads_dir() / (asset_filename[:-4] if asset_filename.endswith(".zip") else asset_filename + ".d")
    try:
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dl.path) as zf:
            zf.extractall(extract_dir)
    except (OSError, zipfile.BadZipFile) as exc:
        return ApplyResult(ok=False, error=f"wheelhouse extract failed: {exc}")

    wheels_dir = _locate_wheels_dir(extract_dir)
    if wheels_dir is None:
        return ApplyResult(
            ok=False, error="no .whl files found inside the wheelhouse"
        )

    return install_engine_update(wheels_dir, on_progress=on_status)


def _quote_arg(arg: str) -> str:
    """Quote a command-line argument for Windows ShellExecute."""
    if not arg:
        return '""'
    if any(c in arg for c in (" ", "\t", '"')):
        escaped = arg.replace('"', '\\"')
        return f'"{escaped}"'
    return arg


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
