#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Build the macOS .app bundle and a signed + notarized DMG.
#
# Run on a Mac with:
#   * Xcode CLT installed (codesign, productbuild, xcrun)
#   * An Apple Developer ID certificate in the login keychain
#   * App-specific password stored in keychain item "AC_PASSWORD" for
#     xcrun notarytool (set via: xcrun notarytool store-credentials AC_PASSWORD)
#
# Usage:
#   ./build/macos/build_macos.sh [--no-notarize] [--no-sign]
#
# The flags are escape hatches for in-house testing on a Mac without an
# Apple Dev account. By default both sign + notarize run.
# -----------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
BUILD_DIR="$REPO_ROOT/build"
ICONS_DIR="$BUILD_DIR/generated-icons"
VENV_DIR="$REPO_ROOT/.venv-build"
DMG_ROOT="$DIST_DIR/dmg-root"

DEV_ID="${DEV_ID:-Developer ID Application: SI-GMT (XXXXXXXXXX)}"
TEAM_ID="${TEAM_ID:-XXXXXXXXXX}"
BUNDLE_ID="com.si-gmt.secondbrain.desktop"
APP_NAME="SecondBrain"
APP_BUNDLE="$DIST_DIR/${APP_NAME}.app"

DO_SIGN=1
DO_NOTARIZE=1

for arg in "$@"; do
    case "$arg" in
        --no-sign)      DO_SIGN=0 ;;
        --no-notarize)  DO_NOTARIZE=0 ;;
        *) echo "unknown flag: $arg" >&2; exit 64 ;;
    esac
done

VERSION="$(grep -E '^version\s*=\s*' "$REPO_ROOT/pyproject.toml" | head -1 | cut -d'"' -f2)"
BUILD_NUMBER="$(git -C "$REPO_ROOT/.." rev-parse --short HEAD 2>/dev/null || echo 0)"
MIN_OS="${MIN_OS:-11.0}"

# The DMG filename matches the Windows setup.exe pattern so the two
# release-artifacts read consistently on the GitHub release page.
DMG_BASENAME="SecondBrainDesktop-$VERSION"

echo "==> Building $APP_NAME $VERSION (build $BUILD_NUMBER)"

if ! python3 - <<'PY'
import sys

if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12+ is required")

try:
    import tkinter  # noqa: F401
except Exception as exc:
    raise SystemExit(
        "Python was built without a working Tkinter/_tkinter module. "
        "Install a Python 3.12 build with Tcl/Tk support before building "
        "the macOS DMG."
    ) from exc
PY
then
    echo "macOS build prerequisite failed: use a Python 3.12+ interpreter with Tkinter support." >&2
    echo "Examples: python.org Python 3.12, pyenv built with Tcl/Tk, or Homebrew Python plus python-tk." >&2
    exit 2
fi

# 1. Refresh the build venv with PyInstaller + the desktop app + macos extras.
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip wheel

# Engine first (in-process bundle), desktop second. memory-kit-mcp is not
# on PyPI; install from the sibling mcp-server/ source tree.
MCP_SERVER_DIR="$REPO_ROOT/../mcp-server"
if [[ ! -d "$MCP_SERVER_DIR" ]]; then
    echo "memory-kit-mcp source not found at $MCP_SERVER_DIR" >&2
    exit 2
fi
pip install -e "$MCP_SERVER_DIR"
pip install -e "$REPO_ROOT[macos,build]"

# 2. Generate icons + .icns.
python -m sb_desktop.icons --export "$ICONS_DIR"
ICONSET_DIR="$ICONS_DIR/SecondBrain.iconset"
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"
for size in 16 32 64 128 256 512; do
    cp "$ICONS_DIR/app-${size}.png" "$ICONSET_DIR/icon_${size}x${size}.png"
done
iconutil -c icns -o "$ICONS_DIR/SecondBrain.icns" "$ICONSET_DIR"

# 3. Run PyInstaller. CWD must be desktop-app/ so dist/ + build/ land
#    where the rest of this script and the .iss installer expect them.
(
    cd "$REPO_ROOT"
    SB_DESKTOP_VERSION="$VERSION" \
        SB_DESKTOP_BUILD_NUMBER="$BUILD_NUMBER" \
        SB_DESKTOP_MIN_OS="$MIN_OS" \
        pyinstaller --noconfirm --clean "$BUILD_DIR/sb-desktop.spec"
)

# 4. PyInstaller creates the .app bundle on macOS. Keep the old manual layout
# fallback for older spec files or non-standard PyInstaller behavior.
if [[ ! -d "$APP_BUNDLE" ]]; then
    rm -rf "$APP_BUNDLE"
    mkdir -p "$APP_BUNDLE/Contents/MacOS"
    mkdir -p "$APP_BUNDLE/Contents/Resources"
    mkdir -p "$APP_BUNDLE/Contents/Frameworks"

    cp "$DIST_DIR/SecondBrainTray/SecondBrainTray" "$APP_BUNDLE/Contents/MacOS/"
    cp -R "$DIST_DIR/SecondBrainTray/_internal/"* "$APP_BUNDLE/Contents/Frameworks/"
    cp "$ICONS_DIR/SecondBrain.icns" "$APP_BUNDLE/Contents/Resources/SecondBrain.icns"

    sed \
        -e "s/@VERSION@/$VERSION/g" \
        -e "s/@BUILD_NUMBER@/$BUILD_NUMBER/g" \
        -e "s/@MIN_OS@/$MIN_OS/g" \
        "$BUILD_DIR/macos/Info.plist.template" > "$APP_BUNDLE/Contents/Info.plist"
fi

# 5. Sign + harden runtime.
if [[ $DO_SIGN -eq 1 ]]; then
    echo "==> Signing with $DEV_ID"

    while IFS= read -r -d '' payload_path; do
        if file "$payload_path" | grep -q "Mach-O"; then
            codesign --force --options runtime --timestamp \
                --sign "$DEV_ID" \
                "$payload_path"
        fi
    done < <(find "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Frameworks" -type f -print0)

    if [[ -d "$APP_BUNDLE/Contents/Frameworks/Python.framework" ]]; then
        codesign --force --options runtime --timestamp \
            --sign "$DEV_ID" \
            "$APP_BUNDLE/Contents/Frameworks/Python.framework"
    fi

    codesign --force --options runtime --timestamp \
        --sign "$DEV_ID" \
        --identifier "$BUNDLE_ID" \
        "$APP_BUNDLE"
    codesign --verify --strict --verbose=2 "$APP_BUNDLE"
fi

# 6. Build DMG via hdiutil.
DMG_PATH="$DIST_DIR/${DMG_BASENAME}.dmg"
rm -f "$DMG_PATH"
rm -rf "$DMG_ROOT"
mkdir -p "$DMG_ROOT"
ditto --noextattr --noqtn "$APP_BUNDLE" "$DMG_ROOT/$APP_NAME.app"
xattr -cr "$DMG_ROOT/$APP_NAME.app" 2>/dev/null || true
ln -s /Applications "$DMG_ROOT/Applications"
cp "$ICONS_DIR/SecondBrain.icns" "$DMG_ROOT/.VolumeIcon.icns"
if command -v SetFile >/dev/null 2>&1; then
    SetFile -a C "$DMG_ROOT"
fi
hdiutil create -volname "$APP_NAME $VERSION" \
    -srcfolder "$DMG_ROOT" \
    -ov -format UDZO \
    "$DMG_PATH"

if [[ $DO_SIGN -eq 1 ]]; then
    codesign --force --sign "$DEV_ID" --timestamp "$DMG_PATH"
fi

# 7. Notarize.
if [[ $DO_NOTARIZE -eq 1 && $DO_SIGN -eq 1 ]]; then
    echo "==> Submitting for notarization (this can take a few minutes)..."
    xcrun notarytool submit "$DMG_PATH" \
        --keychain-profile AC_PASSWORD \
        --wait
    xcrun stapler staple "$DMG_PATH"
fi

# Keep Spotlight clean on developer machines. The distributable artifact is
# the DMG; the loose .app and staging root otherwise appear as duplicate apps.
if [[ "${KEEP_MACOS_BUILD_PRODUCTS:-0}" != "1" ]]; then
    rm -rf "$DMG_ROOT" "$APP_BUNDLE" "$DIST_DIR/SecondBrainTray"
fi

echo "==> Build complete."
echo "    Artifact: $DMG_PATH"
echo ""
echo "    Publish with:"
echo "      gh release upload sb-desktop-v$VERSION \"$DMG_PATH\" --clobber"
