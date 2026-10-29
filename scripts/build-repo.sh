#!/bin/sh
# Build the Kodi repository: installable zips for both add-ons plus addons.xml.
#
# Layout (this is what the repository add-on points Kodi at):
#   repo/addons.xml
#   repo/addons.xml.md5
#   repo/plugin.audio.raveplayer/plugin.audio.raveplayer-<ver>.zip
#   repo/repository.raveplayer/repository.raveplayer-<ver>.zip
set -eu
cd "$(dirname "$0")/.."

./scripts/build.sh >/dev/null

VERSION=$(python3 -c "import xml.etree.ElementTree as E;print(E.parse('addon.xml').getroot().get('version'))")
REPO_VERSION=$(python3 -c "import xml.etree.ElementTree as E;print(E.parse('repository.raveplayer/addon.xml').getroot().get('version'))")

rm -rf repo
mkdir -p repo/plugin.audio.raveplayer repo/repository.raveplayer

cp "dist/plugin.audio.raveplayer-${VERSION}.zip" repo/plugin.audio.raveplayer/

# The repository add-on itself, zipped the way Kodi expects to install it.
tmp=$(mktemp -d)
mkdir -p "$tmp/repository.raveplayer"
cp -R repository.raveplayer/addon.xml repository.raveplayer/icon.png repository.raveplayer/fanart.jpg "$tmp/repository.raveplayer/"
(cd "$tmp" && zip -qr "$OLDPWD/repo/repository.raveplayer/repository.raveplayer-${REPO_VERSION}.zip" repository.raveplayer)
rm -rf "$tmp"

# addons.xml is the catalogue Kodi downloads: both add-ons, full XML bodies.
python3 - <<'PY'
import hashlib
import xml.etree.ElementTree as ET

entries = []
for path in ("addon.xml", "repository.raveplayer/addon.xml"):
    root = ET.parse(path).getroot()
    ET.indent(root)
    entries.append(ET.tostring(root, encoding="unicode"))

with open("repo/addons.xml", "w", encoding="utf-8") as handle:
    handle.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n')
    handle.write("\n".join(entries))
    handle.write("\n</addons>\n")

data = open("repo/addons.xml", "rb").read()
open("repo/addons.xml.md5", "w").write(hashlib.md5(data).hexdigest())
print("addons.xml entries:", len(entries))
PY

echo "repo built: addons.xml (+md5), plugin ${VERSION}, repository ${REPO_VERSION}"
