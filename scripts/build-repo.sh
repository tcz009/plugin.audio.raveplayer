#!/bin/sh
# Build a Kodi repository layout (addons.xml + md5 + zips) so the add-on can
# be installed from a repo URL and auto-update.
set -eu
cd "$(dirname "$0")/.."
VERSION=$(python3 -c "import xml.etree.ElementTree as E;print(E.parse('addon.xml').getroot().get('version'))")
./scripts/build.sh >/dev/null

mkdir -p repo/plugin.audio.raveplayer
cp "dist/plugin.audio.raveplayer-${VERSION}.zip" repo/plugin.audio.raveplayer/

{
    echo '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    echo '<addons>'
    sed -n '/<addon /,$p' addon.xml | sed 's/^[[:space:]]*//' | sed '/^$/d'
    echo '</addons>'
} > repo/addons.xml

python3 - <<'PY'
import hashlib
data = open('repo/addons.xml', 'rb').read()
open('repo/addons.xml.md5', 'w').write(hashlib.md5(data).hexdigest())
print('repo/addons.xml + md5 written')
PY

echo "repo built: repo/addons.xml, repo/plugin.audio.raveplayer/plugin.audio.raveplayer-${VERSION}.zip"
