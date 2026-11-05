#!/bin/sh
# Build both installable Kodi zips:
#   plugin.audio.raveplayer  (the audio plugin + fallback lists)
#   script.raveplayer.ui     (the full-screen Rave Screen window)
set -eu
cd "$(dirname "$0")/.."

PLUGIN_VERSION=$(python3 -c "import xml.etree.ElementTree as E;print(E.parse('addon.xml').getroot().get('version'))")
SCREEN_VERSION=$(python3 -c "import xml.etree.ElementTree as E;print(E.parse('script.raveplayer.ui/addon.xml').getroot().get('version'))")
mkdir -p dist
rm -f "dist/plugin.audio.raveplayer-${PLUGIN_VERSION}.zip" \
      "dist/script.raveplayer.ui-${SCREEN_VERSION}.zip"
find . -name __pycache__ -type d -prune -exec rm -rf {} +

PLUGIN_OUT="$PWD/dist/plugin.audio.raveplayer-${PLUGIN_VERSION}.zip"
tmp=$(mktemp -d)
mkdir -p "$tmp/plugin.audio.raveplayer"
cp -R addon.xml default.py icon.png fanart.jpg changelog.txt LICENSE.txt README.md resources "$tmp/plugin.audio.raveplayer/"
(cd "$tmp" && zip -qr "$PLUGIN_OUT" plugin.audio.raveplayer)
rm -rf "$tmp"

SCREEN_OUT="$PWD/dist/script.raveplayer.ui-${SCREEN_VERSION}.zip"
tmp=$(mktemp -d)
mkdir -p "$tmp/script.raveplayer.ui"
cp -R script.raveplayer.ui/addon.xml script.raveplayer.ui/default.py \
      script.raveplayer.ui/icon.png script.raveplayer.ui/fanart.jpg \
      script.raveplayer.ui/changelog.txt script.raveplayer.ui/LICENSE.txt \
      script.raveplayer.ui/README.md script.raveplayer.ui/resources \
      script.raveplayer.ui/raveui "$tmp/script.raveplayer.ui/"
(cd "$tmp" && zip -qr "$SCREEN_OUT" script.raveplayer.ui)
rm -rf "$tmp"

echo "built dist/plugin.audio.raveplayer-${PLUGIN_VERSION}.zip ($(du -h "$PLUGIN_OUT" | cut -f1))"
echo "built dist/script.raveplayer.ui-${SCREEN_VERSION}.zip ($(du -h "$SCREEN_OUT" | cut -f1))"
