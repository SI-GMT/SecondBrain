# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for sb-desktop.

Build:

    cd desktop-app
    pyinstaller build/sb-desktop.spec --clean --noconfirm

Outputs ``dist/SecondBrainTray/`` (one-dir variant — recommended for
faster startup and smaller per-file signing surface). Pass ``--onefile``
on the CLI if you need a single-file binary instead, but be aware:

* ``--onefile`` extracts to a temp dir on every launch (slower)
* AV scanners flag onefile bundles more often than onedir
* Code signing only signs the launcher, not the inner payload

The spec embeds:

* The full ``sb_desktop`` package (auto-collected by PyInstaller).
* The Pillow + pystray + plyer + pydantic hidden imports (collect_all).
* A pre-rendered ICO at ``icons/app.ico`` so the executable + window have
  the brand glyph on Windows. Generate it before building via:
      python -m sb_desktop.icons --export build/generated-icons
"""

# pylint: disable=all
from PyInstaller.utils.hooks import collect_all, collect_submodules
import os
import sys
from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH).resolve().parent
src_root = project_root / "src"
if sys.platform == "darwin":
    icon_path = project_root / "build" / "generated-icons" / "SecondBrain.icns"
else:
    icon_path = project_root / "build" / "generated-icons" / "app.ico"
icon_arg = str(icon_path) if icon_path.exists() else None
bundle_version = os.environ.get("SB_DESKTOP_VERSION", "0.0.0")
bundle_build_number = os.environ.get("SB_DESKTOP_BUILD_NUMBER", "0")
bundle_min_os = os.environ.get("SB_DESKTOP_MIN_OS", "11.0")

hidden_imports: list[str] = []
collected_datas: list[tuple[str, str]] = []
collected_binaries: list[tuple[str, str]] = []

for pkg in (
    "pystray",
    "PIL",
    "plyer",
    "pydantic",
    "pydantic_core",
    "fastmcp",
    "memory_kit_mcp",
    "sb_desktop",
):
    datas, binaries, hidden = collect_all(pkg)
    collected_datas.extend(datas)
    collected_binaries.extend(binaries)
    hidden_imports.extend(hidden)

hidden_imports.extend(collect_submodules("sb_desktop"))
hidden_imports.extend(collect_submodules("memory_kit_mcp"))

# Tk is required for the dialog layer; PyInstaller usually picks it up but
# we add an explicit hidden import for safety on minimal Python builds.
hidden_imports.extend(["tkinter", "tkinter.ttk", "tkinter.filedialog"])

a = Analysis(
    [str(src_root / "sb_desktop" / "__main__.py")],
    pathex=[str(src_root)],
    binaries=collected_binaries,
    datas=collected_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "test",
        "tests",
        "pytest",
        "_pytest",
        "ruff",
        "setuptools",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SecondBrainTray",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SecondBrainTray",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="SecondBrain.app",
        icon=icon_arg,
        bundle_identifier="com.si-gmt.secondbrain.desktop",
        info_plist={
            "CFBundleDevelopmentRegion": "en",
            "CFBundleDisplayName": "SecondBrain",
            "CFBundleExecutable": "SecondBrainTray",
            "CFBundleIdentifier": "com.si-gmt.secondbrain.desktop",
            "CFBundleInfoDictionaryVersion": "6.0",
            "CFBundleName": "SecondBrain",
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": bundle_version,
            "CFBundleVersion": bundle_build_number,
            "LSMinimumSystemVersion": bundle_min_os,
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
            "NSPrincipalClass": "NSApplication",
            "NSHumanReadableCopyright": "© SI-GMT — AGPL-3.0-or-later",
        },
    )
