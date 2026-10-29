#!/bin/sh
# Build the installable Kodi zip: a top-level plugin.audio.raveplayer/ folder.
set -eu
cd "$(dirname "$0")/.."
VERSION=$(python3 -c "import xml.etree.ElementTree as E;print(E.parse('addon.xml').getroot().get('version'))")
OUT="$PWD/dist/plugin.audio.raveplayer-${VERSION}.zip"
mkdir -p dist
rm -f "$OUT"
find . -name __pycache__ -type d -prune -exec rm -rf {} +
tmp=$(mktemp -d)
mkdir -p "$tmp/plugin.audio.raveplayer"
cp -R addon.xml default.py icon.png fanart.jpg changelog.txt LICENSE.txt README.md resources "$tmp/plugin.audio.raveplayer/"
(cd "$tmp" && zip -qr "$OUT" plugin.audio.raveplayer)
rm -rf "$tmp"
echo "built dist/plugin.audio.raveplayer-${VERSION}.zip ($(du -h "$OUT" | cut -f1))"
