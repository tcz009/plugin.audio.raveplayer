#!/bin/sh
# Install Rave Player onto the Shield's Kodi 22 via ADB + JSON-RPC.
#
# DEV-ONLY, with hardcoded defaults for the owner's Shield:
#   192.0.2.11, Kodi 22, ADB from ../<tools-dir>/platform-tools/adb.
# Override any of them in the environment if your box differs:
#   SHIELD=...  ADB=/path/to/adb  KODI_ADDONS=...  RPC=http://...:8080/jsonrpc
# Requires: ADB authorised (accept the prompt on the Shield once).
#
# The add-on is staged from the CURRENT working tree into a temporary
# directory, using the same file list scripts/build.sh ships. Nothing is read
# from the old stage/ copy, so this script can never install stale code.
set -eu
cd "$(dirname "$0")/.."
WORKSPACE=$(cd .. && pwd)
ADB="${ADB:-$WORKSPACE/<tools-dir>/platform-tools/adb}"
SHIELD="${SHIELD:-192.0.2.11}"
KODI_ADDONS="${KODI_ADDONS:-/sdcard/Android/data/org.xbmc.kodi/files/.kodi/addons}"
RPC="${RPC:-http://$SHIELD:8080/jsonrpc}"
VERSION=$(python3 -c "import xml.etree.ElementTree as E;print(E.parse('addon.xml').getroot().get('version'))")

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
STAGE="$TMP/plugin.audio.raveplayer"
mkdir -p "$STAGE"
cp -R addon.xml default.py icon.png fanart.jpg changelog.txt LICENSE.txt README.md resources "$STAGE/"
find "$STAGE" -name __pycache__ -type d -prune -exec rm -rf {} +

export HOME="$WORKSPACE/.android-home"

echo "== stage =="
echo "staged plugin.audio.raveplayer ${VERSION} from the working tree"
"$ADB" version | head -1 || true

echo "== adb state =="
"$ADB" connect "$SHIELD:5555" >/dev/null 2>&1 || true
"$ADB" devices | tail -n +2

echo "== push add-on =="
"$ADB" shell mkdir -p "$KODI_ADDONS" 2>/dev/null || true
"$ADB" push "$STAGE" "$KODI_ADDONS/" | tail -1

echo "== restart kodi =="
"$ADB" shell am force-stop org.xbmc.kodi
sleep 2
"$ADB" shell monkey -p org.xbmc.kodi -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || \
  "$ADB" shell am start -n org.xbmc.kodi/.Splash >/dev/null 2>&1 || true

echo "== wait for kodi =="
i=0
while [ $i -lt 30 ]; do
  if curl -s -m 2 -o /dev/null "$RPC"; then break; fi
  i=$((i+1)); sleep 2
done

echo "== enable add-on =="
curl -s -m 6 -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","params":{"addonid":"plugin.audio.raveplayer","enabled":true},"id":1}' \
  "$RPC"; echo

echo "== verify =="
curl -s -m 6 -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"Addons.GetAddonDetails","params":{"addonid":"plugin.audio.raveplayer"},"id":2}' \
  "$RPC"; echo
