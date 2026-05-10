# SecondBrain Desktop

Systray companion for the [SecondBrain Memory Kit](../README.md) MCP server.

A small, keyboard-and-eyeball-friendly tray icon that puts the kit's three
most important operations one click away — for users who never want to open
a terminal.

## What it does

| Action                  | What happens                                                                             |
| ----------------------- | ---------------------------------------------------------------------------------------- |
| **Status**              | Combined static (`memory-kit-mcp --version`) + live JSON-RPC handshake against the engine. |
| **Scan vault**          | Calls `mem_health_scan`. Renders findings in a sortable table.                           |
| **Repair vault**        | Calls `mem_health_repair` dry-run; you confirm before any write happens.                 |
| **Check for updates**   | Calls `mem_check_update`. Shows current → latest version.                                |
| **Run update**          | Re-runs `deploy.ps1 -AutoUpdate` / `deploy.sh --auto-update` after explicit confirmation. |
| **Open vault folder**   | Reveals your vault path in Explorer / Finder / xdg-open.                                 |
| **Open logs**           | Tails `sb-desktop.log` in a read-only viewer.                                            |
| **Settings**            | Autostart, language override, confirmation prompts, polling cadence.                     |

The tray icon colour reflects the engine state at a glance:

- 🟢 **green** — engine reachable, version up to date.
- 🟡 **amber** — engine present but a probe failed, or an update is available.
- 🔴 **red** — engine binary not found.
- ⚪ **grey** — first probe in flight.

## Architecture

```
sb-desktop (PyInstaller bundle)
    │
    ├─► subprocess: memory-kit-mcp --version            (static probe)
    ├─► subprocess: memory-kit-mcp <stdio>              (live JSON-RPC probe + tools/call)
    └─► subprocess: deploy.ps1 -AutoUpdate              (Windows)
        subprocess: deploy.sh --auto-update             (macOS / Linux)
```

The desktop app **never imports** `memory_kit_mcp`. It shells out to the
installed binary so the two release cadences stay decoupled. Everything
that mutates state (vault repair, code update) is gated behind an
explicit confirmation dialog — a hard project rule.

## Versioning

`sb-desktop` ships on its own cadence. Tags follow the pattern
`sb-desktop-vX.Y.Z` (e.g. `sb-desktop-v0.1.0`). The kit (`memory-kit-mcp`)
keeps its own `vX.Y.Z` tag scheme.

The desktop app talks to **any** kit version compatible with the MCP
protocol contract it expects (`2024-11-05`). When the kit ships a
breaking protocol change, the desktop app gets a corresponding bump.

## Layout

```
desktop-app/
├── pyproject.toml            ← package definition + tooling config
├── src/sb_desktop/
│   ├── __init__.py           ← __version__ resolved via importlib.metadata
│   ├── __main__.py           ← CLI: tray loop, --healthcheck, --action
│   ├── config.py             ← KitConfig + AppSettings loaders
│   ├── paths.py              ← cross-platform user data / log / cache dirs
│   ├── engine.py             ← memory-kit-mcp binary locator
│   ├── mcp_client.py         ← one-shot JSON-RPC stdio client
│   ├── status.py             ← static + live probe → StatusSnapshot
│   ├── health.py             ← scan + repair via mcp_client
│   ├── update.py             ← check + plan + run via mcp_client + deploy script
│   ├── notifications.py      ← plyer + native fallbacks
│   ├── tray.py               ← pystray Icon + dynamic menu builder
│   ├── icons.py              ← Pillow-rendered tray + app icons
│   ├── logging_setup.py      ← rotating file handler + stderr stream
│   └── ui/                   ← Tkinter dialogs (settings, logs, scan, update)
├── tests/                    ← pytest, hermetic via conftest path redirection
└── build/
    ├── sb-desktop.spec       ← PyInstaller spec
    ├── installer.iss         ← Inno Setup script
    ├── build_windows.ps1     ← end-to-end Windows build
    └── macos/
        ├── build_macos.sh    ← .app bundle + DMG + sign + notarize
        ├── Info.plist.template
        └── com.si-gmt.secondbrain.plist.template
```

## Development

Bootstrap a venv, install in editable mode, run the test suite:

```powershell
# from desktop-app/
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,windows]"
pytest
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Run the tray app locally (it will pick up the kit on PATH or the
`MEMORY_KIT_MCP_BIN` override):

```bash
sb-desktop                      # full tray loop
sb-desktop --healthcheck        # one-shot probe, exits 0/1
sb-desktop --action scan        # headless scan, prints to stdout
```

## Building installers

### Windows (Inno Setup)

```powershell
cd desktop-app
.\build\build_windows.ps1 -Clean
# artefact: dist\SecondBrainDesktop-0.1.0-setup.exe
```

Requirements:
- Python 3.12+ on PATH
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) installed (or pass
  `-IsccPath` to the build script)

The MVP installer is **unsigned** — Windows SmartScreen will warn the
first time a user runs it. Sign with Authenticode later when the
certificate is in place.

### macOS (DMG)

```bash
cd desktop-app
./build/macos/build_macos.sh           # signs + notarizes
./build/macos/build_macos.sh --no-sign # in-house only
# artefact: dist/SecondBrainDesktop-0.1.0.dmg
```

Requirements:
- Apple Developer ID Application certificate in the login keychain
- Notary credentials stored as keychain item `AC_PASSWORD` (see
  `xcrun notarytool store-credentials`)
- Xcode CLT (`codesign`, `iconutil`, `hdiutil`, `xcrun`)

## Roadmap

V1 (this release) is intentionally Python-only — same language as the
engine, fastest path to working software, leverages the existing test
ecosystem. The companion strategy memo
(`project_secondbrain_desktop_app_strategy.md` in the project memory)
captures the path: **V2 will be a full Kotlin Compose Multiplatform
rewrite** for both the desktop UI and the engine, once the Python V1 has
proven the product against real non-tech users.
