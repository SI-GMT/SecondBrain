"""Engine bootstrap — invoked by the Inno [Run] step under admin context.

Lives alongside ``python.exe`` + ``get-pip.py`` + ``wheels/`` inside the
installed ``engine/`` directory. The Inno installer runs this script as

    python.exe bootstrap_engine.py

once at install time, elevated. It is responsible for getting the
embedded Python from "raw distribution" to "fully-installed
memory-kit-mcp ready to spawn":

1. Patch ``python*._pth`` so ``Lib/site-packages`` and ``Scripts`` are
   on ``sys.path`` and ``import site`` is enabled. The stock embeddable
   ships with both disabled, which would prevent the bundled pip from
   importing properly.
2. Bootstrap pip from ``get-pip.py``.
3. Install ``memory-kit-mcp`` from the bundled wheels directory
   (``--no-index --find-links wheels``) so the install works offline.
4. Verify ``Scripts/memory-kit-mcp.exe`` exists at the end — if not,
   exit non-zero so the installer can surface a clear error instead of
   leaving a half-baked install.

Standalone Python script — no third-party imports — so it runs against
the freshly-extracted embedded interpreter before pip is even
available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _engine_dir() -> Path:
    """The directory containing this script (= ``{install}/engine/``)."""
    return Path(__file__).resolve().parent


def _python_dir() -> Path:
    return _engine_dir() / "python"


def _wheels_dir() -> Path:
    return _engine_dir() / "wheels"


def _scripts_dir() -> Path:
    return _engine_dir() / "Scripts"


def _kit_binary() -> Path:
    return _scripts_dir() / "memory-kit-mcp.exe"


def _python_exe() -> Path:
    return _python_dir() / "python.exe"


def patch_pth(python_dir: Path) -> None:
    """Enable ``site`` + add ``Lib/site-packages`` and ``Scripts`` to sys.path.

    Idempotent — re-running on a patched file is a no-op.
    """
    pth_files = sorted(python_dir.glob("python*._pth"))
    if not pth_files:
        print(f"[bootstrap] no _pth file under {python_dir} — skipping patch")
        return
    pth = pth_files[0]
    lines = pth.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []
    has_site_packages = False
    has_scripts = False
    for line in lines:
        stripped = line.strip()
        if stripped == "#import site":
            new_lines.append("import site")
            continue
        new_lines.append(line)
        norm = line.strip().replace("/", "\\").lower()
        if norm.endswith("lib\\site-packages"):
            has_site_packages = True
        if norm.endswith("scripts"):
            has_scripts = True
    if not has_site_packages:
        new_lines.append("..\\Lib\\site-packages")
    if not has_scripts:
        new_lines.append("..\\Scripts")
    pth.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"[bootstrap] patched {pth}")


def merge_site_pth_into_main(python_dir: Path, engine_dir: Path) -> int:
    """Roll every ``*.pth`` entry from ``Lib/site-packages/`` into ``_pth``.

    The Windows embeddable distribution honours ``python*._pth`` as the
    canonical sys.path source and refuses to process ``.pth`` files
    under listed directories (a deliberate "isolation" behaviour).
    Packages that rely on a ``.pth`` to extend sys.path — pywin32 is
    the famous one with ``win32`` and ``win32/lib`` — would otherwise
    be invisible.

    We work around this by scanning every ``*.pth`` in
    ``engine/Lib/site-packages``, parsing its non-comment entries, and
    appending each one as a relative path (anchored at ``..\\Lib\\
    site-packages\\``) to the main ``_pth`` file. Idempotent.
    """
    pth_files = sorted(python_dir.glob("python*._pth"))
    if not pth_files:
        return 0
    main_pth = pth_files[0]
    site_pkgs = engine_dir / "Lib" / "site-packages"
    if not site_pkgs.is_dir():
        return 0

    existing = set(
        line.strip().replace("/", "\\").lower()
        for line in main_pth.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    appended: list[str] = []
    for pth_file in sorted(site_pkgs.glob("*.pth")):
        try:
            raw = pth_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in raw.splitlines():
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            if entry.startswith("import "):
                # Side-effecting imports (rare; e.g. pywin32_bootstrap).
                # Leave them to site.py to discover when it scans the
                # site-packages dir — embeddable still processes those.
                continue
            normalised = entry.replace("/", "\\")
            full = "..\\Lib\\site-packages\\" + normalised
            if full.lower() in existing:
                continue
            appended.append(full)
            existing.add(full.lower())

    if not appended:
        return 0
    body = main_pth.read_text(encoding="utf-8").rstrip("\n")
    main_pth.write_text(
        body + "\n" + "\n".join(appended) + "\n", encoding="utf-8"
    )
    print(
        f"[bootstrap] appended {len(appended)} .pth entry(ies) into "
        f"{main_pth.name}: {appended}"
    )
    return len(appended)


def run_get_pip(python_exe: Path, engine_dir: Path) -> int:
    """Run ``get-pip.py`` against the embedded interpreter.

    ``--prefix=engine_dir`` redirects pip's install layout so it lands
    at ``engine/Lib/site-packages`` + ``engine/Scripts``, NOT at the
    embeddable's default ``engine/python/Lib`` + ``engine/python/Scripts``.
    The ``_pth`` patch maps ``..\\Lib\\site-packages`` + ``..\\Scripts``
    onto exactly those locations, so the runtime finds them naturally.
    """
    get_pip = engine_dir / "get-pip.py"
    if not get_pip.is_file():
        print(f"[bootstrap] ERROR: get-pip.py missing at {get_pip}", file=sys.stderr)
        return 2
    print(f"[bootstrap] running get-pip.py (prefix={engine_dir}) …")
    return subprocess.call(
        [
            str(python_exe),
            str(get_pip),
            "--no-warn-script-location",
            "--prefix",
            str(engine_dir),
        ],
        cwd=str(engine_dir),
    )


def run_pywin32_postinstall(python_exe: Path, engine_dir: Path) -> int:
    """Run pywin32's postinstall hook so ``pywintypes`` is importable.

    pywin32 ships DLLs under ``Lib/site-packages/pywin32_system32`` that
    must be on the DLL search path before ``import pywintypes`` works.
    On a regular Python install pip's setup hook handles that; on the
    embeddable it does NOT, so we:

    1. Copy ``pywin32_system32\\*.dll`` next to ``python.exe`` (the
       interpreter directory is always on the DLL search path).
    2. Run ``pywin32_postinstall.py -install -silent`` best-effort,
       which writes registry entries and may copy DLLs to System32 if
       admin — non-fatal if it fails.

    The DLL copy step is what actually makes ``import pywintypes`` work
    against the embeddable; the postinstall script is a courtesy.
    """
    dll_src = engine_dir / "Lib" / "site-packages" / "pywin32_system32"
    python_dir = python_exe.parent
    copied = 0
    if dll_src.is_dir():
        for dll in dll_src.glob("*.dll"):
            try:
                shutil.copy2(dll, python_dir / dll.name)
                copied += 1
            except OSError as exc:
                print(
                    f"[bootstrap] WARNING: could not copy {dll.name}: {exc}",
                    file=sys.stderr,
                )
        print(f"[bootstrap] copied {copied} pywin32 DLL(s) into {python_dir}")
    else:
        print(f"[bootstrap] pywin32_system32 dir absent at {dll_src} — skipping DLL copy")

    candidates = [
        engine_dir / "Scripts" / "pywin32_postinstall.py",
        engine_dir / "Lib" / "site-packages" / "win32" / "scripts" / "pywin32_postinstall.py",
        engine_dir / "Lib" / "site-packages" / "pywin32_postinstall.py",
    ]
    script = next((c for c in candidates if c.is_file()), None)
    if script is None:
        print("[bootstrap] pywin32_postinstall.py not found — skipping registry hook")
        return 0
    print(f"[bootstrap] running pywin32 postinstall ({script}) …")
    rc = subprocess.call(
        [str(python_exe), str(script), "-install", "-silent"],
        cwd=str(engine_dir),
    )
    if rc != 0:
        print(
            f"[bootstrap] pywin32 postinstall exited {rc} — non-fatal",
            file=sys.stderr,
        )
    return 0


def run_pip_install(python_exe: Path, engine_dir: Path, wheels: Path) -> int:
    """Offline install of memory-kit-mcp from the bundled wheelhouse."""
    if not wheels.is_dir():
        print(f"[bootstrap] ERROR: wheels dir missing at {wheels}", file=sys.stderr)
        return 2
    print(f"[bootstrap] pip install memory-kit-mcp from {wheels} (prefix={engine_dir}) …")
    return subprocess.call(
        [
            str(python_exe),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheels),
            "--no-warn-script-location",
            "--prefix",
            str(engine_dir),
            "memory-kit-mcp",
        ],
        cwd=str(engine_dir),
    )


def main(argv: list[str] | None = None) -> int:
    engine = _engine_dir()
    python_dir = _python_dir()
    python_exe = _python_exe()
    wheels = _wheels_dir()
    kit_binary = _kit_binary()

    print(f"[bootstrap] engine dir: {engine}")
    print(f"[bootstrap] python:     {python_exe}")
    print(f"[bootstrap] wheels:     {wheels}")
    print(f"[bootstrap] target:     {kit_binary}")

    if not python_exe.is_file():
        print(f"[bootstrap] ERROR: python.exe missing at {python_exe}", file=sys.stderr)
        return 2

    try:
        patch_pth(python_dir)
    except OSError as exc:
        print(f"[bootstrap] ERROR: _pth patch failed: {exc}", file=sys.stderr)
        return 3

    if kit_binary.is_file():
        print("[bootstrap] kit binary already present — re-running install to refresh wheels")

    rc = run_get_pip(python_exe, engine)
    if rc != 0:
        print(f"[bootstrap] ERROR: get-pip exited {rc}", file=sys.stderr)
        return 4

    rc = run_pip_install(python_exe, engine, wheels)
    if rc != 0:
        print(f"[bootstrap] ERROR: pip install exited {rc}", file=sys.stderr)
        return 5

    rc = run_pywin32_postinstall(python_exe, engine)
    if rc != 0:
        print(
            f"[bootstrap] WARNING: pywin32 postinstall exited {rc} — "
            "engine may still work but pywintypes import could fail later",
            file=sys.stderr,
        )

    # Roll every site-packages/*.pth into the main _pth so embedded
    # Python's isolated mode picks up extension dirs (pywin32, …).
    try:
        merge_site_pth_into_main(python_dir, engine)
    except OSError as exc:
        print(
            f"[bootstrap] WARNING: could not merge .pth entries: {exc}",
            file=sys.stderr,
        )

    if not kit_binary.is_file():
        print(
            f"[bootstrap] ERROR: pip install succeeded but {kit_binary} is missing",
            file=sys.stderr,
        )
        return 6

    print(f"[bootstrap] OK — engine ready at {kit_binary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
