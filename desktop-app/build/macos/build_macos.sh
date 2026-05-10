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
MIN_OS="11.0"

echo "==> Building $APP_NAME $VERSION (build $BUILD_NUMBER)"

# 1. Refresh the build venv with PyInstaller + the desktop app + macos extras.
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip wheel
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

# 3. Run PyInstaller.
pyinstaller --noconfirm --clean "$BUILD_DIR/sb-desktop.spec"

# 4. Lay down the .app bundle structure.
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

cp -R "$DIST_DIR/SecondBrainTray/"* "$APP_BUNDLE/Contents/MacOS/"
cp "$ICONS_DIR/SecondBrain.icns" "$APP_BUNDLE/Contents/Resources/SecondBrain.icns"

sed \
    -e "s/@VERSION@/$VERSION/g" \
    -e "s/@BUILD_NUMBER@/$BUILD_NUMBER/g" \
    -e "s/@MIN_OS@/$MIN_OS/g" \
    "$BUILD_DIR/macos/Info.plist.template" > "$APP_BUNDLE/Contents/Info.plist"

# 5. Sign + harden runtime.
if [[ $DO_SIGN -eq 1 ]]; then
    echo "==> Signing with $DEV_ID"
    codesign --deep --force --options runtime --timestamp \
        --sign "$DEV_ID" \
        --identifier "$BUNDLE_ID" \
        "$APP_BUNDLE"
    codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"
fi

# 6. Build DMG via hdiutil.
DMG_PATH="$DIST_DIR/SecondBrainDesktop-$VERSION.dmg"
rm -f "$DMG_PATH"
hdiutil create -volname "$APP_NAME $VERSION" \
    -srcfolder "$APP_BUNDLE" \
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

echo "==> Artifact: $DMG_PATH"
