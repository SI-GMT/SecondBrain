<p align="center">
  <img src="../docs/assets/secondbrain-lockup.svg" alt="SecondBrain Desktop" width="360">
</p>

# SecondBrain Desktop

Systray companion for the [SecondBrain Memory Kit](../README.md) engine.

A small, keyboard-and-eyeball-friendly tray icon that puts the kit's
most important operations one click away — for users who never want to
open a terminal.

## What it does

| Action                | What happens                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------- |
| **Status**            | Bundled engine version + pipx-installed engine version + drift detection (no subprocess).   |
| **Scan vault**        | Direct call into `memory_kit_mcp.health.scan.scan_vault`. Findings rendered in a table.     |
| **Repair vault**      | Direct call into `memory_kit_mcp.tools.health_repair`. Dry-run first, then confirm.         |
| **Check for updates** | Direct call into `memory_kit_mcp.update_check.check_for_update`. ~20 ms cache hit.          |
| **Run update**        | One-off subprocess: `deploy.ps1 -AutoUpdate` / `deploy.sh --auto-update`, after confirmation. |
| **Open vault folder** | Reveals your vault path in Explorer / Finder / xdg-open.                                    |
| **Open logs**         | Tails `sb-desktop.log` in a read-only viewer.                                               |
| **Settings**          | Autostart, language override, confirmation prompts, polling cadence.                        |

Tray icon colour mapping:

- **green** — bundled engine ready, installed kit on PATH, versions aligned.
- **amber** — installed kit missing, version drift, or update available.
- **red** — bundled engine import failed (broken install).
- **grey** — first probe in flight.

Brand glyph rasterised from the canonical SecondBrain SVG masters
under `src/sb_desktop/icons/` (commit-time bundled PNG variants under
`png/` + multi-size ICO for Windows). The runtime composes the brand
glyph + a coloured status disc per snapshot.

## Architecture (V2 — in-process)

```
SecondBrainTray.exe (PyInstaller bundle, ~80 MB)
    │
    ├── sb_desktop/         (tray + Tkinter dialogs)
    │     │
    │     └── direct Python imports:
    │           memory_kit_mcp.health.scan.scan_vault(vault)      ← ~10-50 ms
    │           memory_kit_mcp.tools.health_repair._fix_missing_display(...)
    │           memory_kit_mcp.update_check.check_for_update()    ← ~20 ms
    │
    └── memory_kit_mcp/     (engine, bundled in-process)
          ├── health/scan.py
          ├── tools/health_repair.py
          ├── update_check.py
          └── vault/

ONLY subprocess in steady state:
    deploy.ps1 -AutoUpdate  (Windows, on explicit user click)
    deploy.sh --auto-update (POSIX, on explicit user click)
    → spawned with CREATE_NO_WINDOW so no console flash.
```

The desktop app **bundles its own copy** of `memory_kit_mcp` via
PyInstaller. There is no inter-process communication for the menu
actions — they're plain function calls. The pipx-installed kit lives
alongside as the binary the LLM CLIs (Claude Code, Codex, Gemini, …)
use; the desktop app only reads its version from dist-info metadata to
detect drift.

Why in-process instead of the V1 stdio MCP client:

- Spawning the engine binary per click cold-starts Python + Pydantic +
  FastMCP every time (≈1-2 s on Windows). V1 menu opens took 3-5 s.
- Each subprocess on Windows flashed a console window unless every
  call site set `CREATE_NO_WINDOW` — easy to forget, ugly.
- An "engine status" indicator that probed via stdio handshake had to
  succeed on a cold start within a short timeout, which it frequently
  didn't.

Everything that mutates state (vault repair, code update) stays gated
behind an explicit confirmation dialog — a hard project rule.

## Reliable engine bootstrap (v0.8.3+)

The installer ships a self-contained engine bootstrap orchestrated by
`build/bootstrap_engine.py` (run once elevated at install time):

1. Patch `python*._pth` so `Lib/site-packages` + `Scripts` join
   `sys.path` and `import site` is enabled.
2. Run `get-pip.py --prefix={engine}` so pip lands at
   `engine/Lib/site-packages/` and entry points at `engine/Scripts/`
   (not at the embeddable's default `engine/python/...`).
3. `pip install --no-index --find-links wheels --prefix={engine}
   memory-kit-mcp` — fully offline.
4. Copy `pywin32_system32/*.dll` next to `python.exe` so
   `import pywintypes` resolves under the embeddable interpreter.
5. Merge every `Lib/site-packages/*.pth` into the main
   `python*._pth` because the embeddable's isolated mode bypasses
   `.pth` scanning (pywin32 needs `win32`, `win32/lib`, `Pythonwin`).
6. Verify `engine/Scripts/memory-kit-mcp.exe` exists; the Inno
   `CurStepChanged(ssPostInstall)` hook aborts the install with a
   clear MsgBox if it doesn't, so users never reach a wizard against
   a half-installed engine.

On uninstall the `[UninstallDelete]` block wipes the runtime-generated
content (`engine/Lib/`, `engine/Scripts/`, `engine/python/` —
including the pywin32 DLLs we copied — `__pycache__/`, ad-hoc `.pth`
edits) so nothing leaks under Program Files. `CurUninstallStepChanged`
also strips the engine `Scripts/` directory from the HKLM `Path`
value (Inno's [Registry] entry uses `preservestringtype noerror`
which doesn't carry `uninsdeletevalue`). The taskkill step now also
terminates any `memory-kit-mcp.exe` instances spawned by the user's
LLM CLIs, so file locks never block the cleanup.

## Versioning

`sb-desktop` ships on its own cadence. Tags follow the pattern
`sb-desktop-vX.Y.Z` (e.g. `sb-desktop-v0.8.7`). The kit (`memory-kit-mcp`)
keeps its own `vX.Y.Z` tag scheme.

The desktop app talks to **any** kit version compatible with the MCP
protocol contract it expects (`2024-11-05`). When the kit ships a
breaking protocol change, the desktop app gets a corresponding bump.

## Cross-OS PATH integration (v0.8+)

The engine binary (`memory-kit-mcp`) must be reachable from every
process that needs it — terminal CLIs (Claude Code, Codex, Gemini
CLI…) **and** GUI apps (Claude Desktop, IDE plugins). The desktop
app handles this automatically per-OS:

| OS | System install | User install |
|---|---|---|
| **Windows** | `HKLM\…\Environment\Path` (admin) → `WM_SETTINGCHANGE` broadcast | `HKCU\Environment\PATH` → broadcast |
| **macOS / Linux** | symlink in `/usr/local/bin/` (root) | symlink in `~/.local/bin/` + managed block in `~/.bashrc` / `~/.zshrc` |

POSIX uses the symlink layer specifically so GUI apps see the
binary — launchd / systemd-user processes never source shell rc
files, so a `PATH=` line in `.zshrc` alone doesn't help Claude
Desktop on macOS. The rc-file block remains a safety net for
non-login shells.

If the elevated layer can't be written (no admin/root), the
installer falls back to the per-user layer so the current user at
least retains access.

## Multi-user / RDP (v0.7+)

The installer is dual-mode at launch:

* **System install (admin)** — `%ProgramFiles%\SecondBrain`. The
  engine bootstrap (pip install into `engine\Lib\site-packages`,
  HKLM PATH update) happens once, elevated, at install time. Every
  user on the host shares the binaries. Each user's first launch of
  the tray pops the in-app wizard which only does per-user setup
  (vault picker → `~\Documents\SecondBrain`, language,
  `~\.memory-kit\config.json`, MCP wiring into the user's
  `~\.claude.json` / `~\.codex\config.toml` / etc.). No admin
  needed for per-user runs.
* **Per-user install** — `%LOCALAPPDATA%\Programs\SecondBrain`. The
  wizard does the engine bootstrap inline at first launch. Single-
  user laptops, no admin friction.

Per-user state lives in the user profile in both modes:

| Resource | Path |
|---|---|
| Settings (autostart, language, MCP targets) | `%APPDATA%\SecondBrain\settings.json` (roaming) |
| Cache (update-check, last engine probe) | `%LOCALAPPDATA%\SecondBrain\cache\` |
| Logs (one file per user) | `%LOCALAPPDATA%\SecondBrain\logs\sb-desktop.log` |
| Kit config (vault path, language) | `~\.memory-kit\config.json` |
| Vault | `~\Documents\SecondBrain\` (default, user-pickable) |
| MCP wiring | `~\.claude.json`, `~\.codex\config.toml`, `~\.gemini\settings.json`, … |

Process isolation: each user's tray spawns its own
`memory-kit-mcp.exe` instances. Engine processes inherit the user's
``USERPROFILE`` / ``APPDATA`` env vars, so they read each user's own
`~/.memory-kit/config.json` without any coordination. There is no
shared mutable state at engine level; concurrent users on the same
RDP host never block each other.

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
