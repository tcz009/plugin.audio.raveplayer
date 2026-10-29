#!/bin/sh
# Install Rave Player onto the Shield's Kodi 22 via ADB + JSON-RPC.
# Requires: ADB authorised (accept the prompt on the Shield once).
set -eu
cd "$(dirname "$0")/.."
WORKSPACE=$(cd .. && pwd)
ADB="$WORKSPACE/<tools-dir>/platform-tools/adb"
SHIELD=192.0.2.11
KODI_ADDONS=/sdcard/Android/data/org.xbmc.kodi/files/.kodi/addons
RPC=http://$SHIELD:8080/jsonrpc

export HOME="$WORKSPACE/.android-home"

echo "== adb state =="
"$ADB" connect $SHIELD:5555 >/dev/null 2>&1 || true
"$ADB" devices | tail -n +2

echo "== push add-on =="
"$ADB" shell mkdir -p "$KODI_ADDONS" 2>/dev/null || true
"$ADB" push stage/plugin.audio.raveplayer "$KODI_ADDONS/" | tail -1

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
