#!/bin/zsh
# Build Jarvis.app with py2app in alias mode: the bundle symlinks back to
# this folder, so code edits apply on next launch without rebuilding.
# (A hand-rolled script-launcher bundle does NOT work: when LaunchServices
# starts one, macOS parks the menu bar icon off-screen. py2app's compiled
# launcher keeps the app identity intact and the icon visible.)
#
#   ./build_app.sh                 -> installs to /Applications/Jarvis.app
#   ./build_app.sh ~/Applications  -> custom install dir
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")" && pwd)"
PY="$PROJECT/venv/bin/python"
DEST="${1:-/Applications}"
APP="$DEST/Jarvis.app"

[[ -x "$PY" ]] || { echo "venv missing - run the Setup steps in README.md first"; exit 1; }

# --- Icon: render the 🎙️ emoji into jarvis.icns (once) ---------------------
if [[ ! -f "$PROJECT/jarvis.icns" ]]; then
  ICONSET="$(mktemp -d)/jarvis.iconset"
  mkdir -p "$ICONSET"
  "$PY" - "$ICONSET" <<'EOF'
import sys
from AppKit import (NSFont, NSFontAttributeName, NSBitmapImageRep,
                    NSGraphicsContext, NSPNGFileType)
from Foundation import NSString

iconset = sys.argv[1]
for size in (16, 32, 64, 128, 256, 512, 1024):
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False, "NSCalibratedRGBColorSpace", 0, 0)
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.setCurrentContext_(ctx)
    text = NSString.stringWithString_("🎙️")
    attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(size * 0.78)}
    bounds = text.sizeWithAttributes_(attrs)
    text.drawAtPoint_withAttributes_(
        ((size - bounds.width) / 2, (size - bounds.height) / 2), attrs)
    ctx.flushGraphics()
    png = rep.representationUsingType_properties_(NSPNGFileType, None)
    names = {16: ["icon_16x16.png"], 32: ["icon_16x16@2x.png", "icon_32x32.png"],
             64: ["icon_32x32@2x.png"], 128: ["icon_128x128.png"],
             256: ["icon_128x128@2x.png", "icon_256x256.png"],
             512: ["icon_256x256@2x.png", "icon_512x512.png"],
             1024: ["icon_512x512@2x.png"]}
    for name in names[size]:
        png.writeToFile_atomically_(f"{iconset}/{name}", True)
EOF
  iconutil -c icns "$ICONSET" -o "$PROJECT/jarvis.icns"
fi

# --- Build & install ---------------------------------------------------------
cd "$PROJECT"
rm -rf build dist
"$PY" setup.py py2app -A
rm -rf "$APP"
cp -R "$PROJECT/dist/Jarvis.app" "$APP"
# Ad-hoc signature gives the app a stable identity so permission grants
# (mic, accessibility) survive rebuilds.
codesign --force --deep -s - "$APP"

echo "Done: $APP"
echo "Launch it from Spotlight/Finder, or:  open '$APP'"
echo ""
echo "NOTE: rebuilding changes the app's ad-hoc signature, which can silently"
echo "break the Microphone grant. If Jarvis stops hearing you, run:"
echo "  tccutil reset Microphone local.matt.jarvis"
echo "then relaunch and re-allow the mic prompt."
