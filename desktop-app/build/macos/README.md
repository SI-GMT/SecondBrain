# macOS DMG build — SecondBrain Desktop v0.6+

End-to-end instructions for building, signing, and notarizing the
macOS DMG installer of SecondBrain Desktop on a Mac.

The Windows installer is built from a Windows machine via
`desktop-app/build/build_windows.ps1`. The macOS DMG is built from a
Mac via `desktop-app/build/macos/build_macos.sh`. The two scripts
produce equivalent artifacts (same architecture, same engine wheels,
same per-CLI MCP injection) — they're just OS-specific because
codesign / hdiutil / notarytool are Apple-only.

## Prerequisites

### 1. Mac hardware + macOS

- Mac with Apple Silicon (M1/M2/M3) or Intel.
- macOS 12 (Monterey) or later. The produced `.app` targets
  macOS 11 (Big Sur) minimum (configurable via `MIN_OS` in
  `build_macos.sh`).

### 2. Xcode Command Line Tools

```bash
xcode-select --install
```

Provides `codesign`, `iconutil`, `hdiutil`, `xcrun`, `notarytool`.

### 3. Python 3.12+

Use one of:

```bash
# Option A — homebrew (recommended)
brew install python@3.12 python-tk@3.12

# Option B — python.org installer
# Download from https://www.python.org/downloads/macos/ and run the .pkg.

# Option C — pyenv
pyenv install 3.12.7 && pyenv shell 3.12.7
```

Verify:

```bash
python3 --version  # → Python 3.12.x
python3 -c "import tkinter; print(tkinter.TkVersion)"
```

`python-tk@3.12` is required with Homebrew Python because the desktop
first-run wizard and settings dialogs use Tkinter. The build script
fails early if `_tkinter` is missing, instead of producing a DMG whose
tray starts but whose dialogs crash.

### 4. Apple Developer ID certificate (for signed builds)

Required to produce a DMG that Gatekeeper accepts without warnings.
Without it, users will see "macOS cannot verify the developer" and
have to right-click → Open the first time.

Steps:

1. Enrol in the [Apple Developer Program](https://developer.apple.com/programs/)
   (99 USD/year). The personal account is fine — the Organization
   tier is not required.
2. In Xcode → Settings → Accounts, sign in with the Apple ID
   associated with the Developer Program.
3. Click "Manage Certificates" → `+` → **Developer ID Application**.
   Xcode generates the certificate and stores it in your login
   keychain.
4. Verify with:

   ```bash
   security find-identity -p codesigning -v
   # Should list "Developer ID Application: <Your Name> (TEAMID)"
   ```

5. Copy the exact identity string (e.g. `Developer ID Application:
   SI-GMT (XXXXXXXXXX)`) — you'll set it as `DEV_ID` below.

### 5. Notary credentials (for stapled DMGs)

```bash
xcrun notarytool store-credentials AC_PASSWORD \
    --apple-id you@example.com \
    --team-id XXXXXXXXXX \
    --password app-specific-password
```

`app-specific-password` is generated at https://appleid.apple.com →
Security → App-Specific Passwords. The keychain item `AC_PASSWORD`
is what `build_macos.sh` references via `--keychain-profile
AC_PASSWORD`.

## Repository layout the script expects

```
SecondBrain/           ← git checkout root
  desktop-app/         ← Python package + build/
    build/
      sb-desktop.spec
      macos/
        build_macos.sh
        Info.plist.template
        com.si-gmt.secondbrain.plist.template
        README.md       ← (this file)
  mcp-server/          ← memory-kit-mcp source (sibling of desktop-app/)
```

The script assumes `desktop-app/` and `mcp-server/` live alongside
each other inside the repo. It refuses to start if `mcp-server/` is
absent.

## Build steps

### Step 1 — clone the repo + checkout the tag

```bash
git clone https://github.com/SI-GMT/SecondBrain.git
cd SecondBrain
git checkout sb-desktop-v0.6.0   # or whichever tag you're building
```

### Step 2 — export your Apple identifiers

```bash
export DEV_ID="Developer ID Application: SI-GMT (XXXXXXXXXX)"
export TEAM_ID="XXXXXXXXXX"
```

(Or edit `build_macos.sh` directly if you don't want to set the env
each session. The values are read at the top of the script.)

### Step 3 — run the build

```bash
cd desktop-app
./build/macos/build_macos.sh
```

The script will:

1. Create `.venv-build/` inside `desktop-app/`.
2. Install the engine + the desktop app in editable mode there.
3. Render the icon set + `.icns` from `sb_desktop.icons`.
4. Run PyInstaller against `build/sb-desktop.spec`.
5. Let PyInstaller assemble the `.app` bundle at
   `desktop-app/dist/SecondBrain.app`.
6. Sign embedded Mach-O payloads, `Python.framework`, then the `.app`
   bundle with hardened runtime.
7. Create a DMG staging root containing `SecondBrain.app`, an
   `Applications` shortcut, and the SecondBrain volume icon.
8. Wrap that root in a DMG via `hdiutil`.
9. Sign the DMG itself.
10. Submit to Apple notary, wait for the result, staple the ticket.

End artifact: `desktop-app/dist/SecondBrainDesktop-<version>.dmg`.

Typical run time on an M-series Mac: 3–6 minutes (notarization is
the slow part).

### Escape hatches

```bash
./build/macos/build_macos.sh --no-notarize  # Skip notarization (still signs)
./build/macos/build_macos.sh --no-sign      # Skip codesign entirely
                                            # — DMG opens locally only.
```

Use `--no-sign` for fast in-house testing on the same Mac. Never
distribute an unsigned DMG: Gatekeeper will refuse to open it on any
other machine without explicit right-click → Open + Allow.

## Verifying a build before shipping it

```bash
DMG="desktop-app/dist/SecondBrainDesktop-0.6.0.dmg"

# 1. Codesign chain is intact.
codesign --verify --deep --strict --verbose=2 "$DMG"
spctl --assess --type install --verbose=2 "$DMG"

# 2. Notarization ticket is stapled (offline-checkable).
stapler validate "$DMG"

# 3. The .app inside the DMG launches.
hdiutil attach "$DMG"
open /Volumes/SecondBrain*/SecondBrain.app
hdiutil detach /Volumes/SecondBrain*
```

## Publishing the DMG

Upload to the matching GitHub release once the build is clean:

```bash
gh release upload sb-desktop-v0.6.0 \
    desktop-app/dist/SecondBrainDesktop-0.6.0.dmg \
    --clobber
```

## Troubleshooting

### `codesign` fails with "No identity found"

```bash
security find-identity -p codesigning -v
```

Should list at least one `Developer ID Application: …` entry. If the
list is empty, the certificate wasn't imported into the login
keychain — repeat the "Manage Certificates" step in Xcode.

### Notarization fails with `Invalid` or `Rejected`

```bash
# Pull the most recent failed submission's log.
xcrun notarytool history --keychain-profile AC_PASSWORD
xcrun notarytool log <submission-id> --keychain-profile AC_PASSWORD developer_log.json
cat developer_log.json | jq .issues
```

The common offenders are:

- A nested binary not signed with the same identity.
- Hardened runtime not enabled (the script sets `--options
  runtime`).
- A binary references the wrong Team ID.

Re-run with the offending file resigned, then resubmit.

### "Killed: 9" the first time `.app` launches on a fresh Mac

Quarantine bit not cleared because the DMG isn't notarized /
stapled. Either complete notarization or, for local testing, run
`xattr -dr com.apple.quarantine /Applications/SecondBrain.app`.

### Python build venv reuses an old `memory-kit-mcp` install

```bash
rm -rf desktop-app/.venv-build
./build/macos/build_macos.sh
```

The script creates the venv only if absent — wiping it forces a
clean reinstall.

### `iconutil` fails to produce `.icns`

The iconset directory has to contain files named exactly
`icon_{NN}x{NN}.png`. If `sb_desktop.icons --export` produces a
different naming, fix the loop in `build_macos.sh` step 2.

### PyInstaller says Tkinter is broken

Install the Tk bridge matching your Python version:

```bash
brew install python-tk@3.12
python3 -c "import tkinter; print(tkinter.TkVersion)"
```

Then remove the stale build venv and rebuild:

```bash
rm -rf desktop-app/.venv-build
cd desktop-app
./build/macos/build_macos.sh --no-sign --no-notarize
```

## Architecture parity with the Windows installer

On Windows the user picks the install directory in the Inno Setup
wizard (default `%LOCALAPPDATA%\SecondBrain`). On macOS the install
location is fixed at `/Applications/SecondBrain.app` — that's the
platform convention; users don't expect to pick a directory for an
`.app` bundle.

The engine bootstrap (Python embeddable extract → pip install
offline → PATH update → MCP wiring) is identical: when the first-run
wizard runs inside the `.app`, it locates its install root via
`sys.executable.parent.parent` (the `Contents/MacOS/` parent), then
unpacks the bundled engine into
`~/Library/Application Support/SecondBrain/engine/` and adds
`{that_dir}/Scripts/` to the user's PATH via the
`~/.bashrc` / `~/.zshrc` managed block.

The current `kit_installer.py` already handles the macOS path
detection — no code changes needed when the DMG-built `.app`
launches its wizard.
