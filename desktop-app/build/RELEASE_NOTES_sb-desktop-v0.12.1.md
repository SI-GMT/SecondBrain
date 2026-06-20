# SecondBrain Desktop v0.12.1

## Fix — engine version display after an in-place update

The **SecondBrain Engine** panel in *Check for updates* now reads the engine's **on-disk** version, so an applied in-place update is reflected right away instead of staying stuck at the previous version.

Previously "Current" was taken from the engine's import-time `__version__` — a value frozen for the life of the tray process — so after a successful `Download & install` the displayed version never moved. It now reads the version of the engine the update actually rewrites (`{install}/engine`) and refreshes the row once the upgrade completes.

Bundles engine **v0.14.0**.

## Install

Download `SecondBrainDesktop-0.12.1-setup.exe` and run it over your existing install. Vault, settings and MCP wirings stay intact.

## Asset

- `SecondBrainDesktop-0.12.1-setup.exe`
