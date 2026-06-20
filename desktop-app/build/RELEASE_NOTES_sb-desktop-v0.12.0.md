# SecondBrain Desktop v0.12.0

## In-place engine updates (offline, version-pinned)

The tray's **Check for updates → SecondBrain Engine** action now upgrades the engine **in place**. When an engine release ships a wheelhouse asset, the dialog downloads it, extracts it, and runs `pip --no-index --find-links` against the embedded Python — UAC prompt for system installs. No more "reinstall the whole desktop to move the engine forward".

- Offline & version-pinned: installs from the release's `memory_kit_mcp-*-wheelhouse-win_amd64.zip`, never touches PyPI at update time (corporate-network safe).
- Bundles engine **v0.14.0** — the new `mem-worklog` weekly worklog skill (41 tools).

Your vault, settings and MCP wirings stay intact across the update.

## Install

Download `SecondBrainDesktop-0.12.0-setup.exe` and run it. The installer detects an existing install and upgrades in place.

## Asset

- `SecondBrainDesktop-0.12.0-setup.exe`
