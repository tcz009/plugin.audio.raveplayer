#!/bin/sh
# Fail when the committed repo/ catalogue is stale relative to addon.xml.
#
# Run after scripts/build-repo.sh (CI and locally before committing). It
# deliberately does NOT compare binary zips: zip timestamps change on every
# build. It checks the text artifacts and that the versioned add-on zips are
# tracked by git.
set -eu
cd "$(dirname "$0")/.."
VERSION=$(python3 -c "import xml.etree.ElementTree as E;print(E.parse('addon.xml').getroot().get('version'))")
SCREEN_VERSION=$(python3 -c "import xml.etree.ElementTree as E;print(E.parse('script.raveplayer.ui/addon.xml').getroot().get('version'))")
MODULE_VERSION=$(python3 -c "import xml.etree.ElementTree as E;print(E.parse('script.module.raveresolver/addon.xml').getroot().get('version'))")
PLUGIN_ZIP="repo/plugin.audio.raveplayer/plugin.audio.raveplayer-${VERSION}.zip"
SCREEN_ZIP="repo/script.raveplayer.ui/script.raveplayer.ui-${SCREEN_VERSION}.zip"
MODULE_ZIP="repo/script.module.raveresolver/script.module.raveresolver-${MODULE_VERSION}.zip"

if [ -n "$(git status --porcelain -- repo/addons.xml repo/addons.xml.md5)" ]; then
  echo "ERROR: repo/addons.xml or repo/addons.xml.md5 is modified/untracked." >&2
  echo "       Run ./scripts/build-repo.sh and commit the regenerated repo/." >&2
  git status --short -- repo/addons.xml repo/addons.xml.md5 >&2 || true
  exit 1
fi

for ZIP in "$PLUGIN_ZIP" "$SCREEN_ZIP" "$MODULE_ZIP"; do
  if ! git ls-files --error-unmatch "$ZIP" >/dev/null 2>&1; then
    echo "ERROR: ${ZIP} is not tracked by git." >&2
    echo "       Run ./scripts/build-repo.sh and commit the regenerated repo/." >&2
    exit 1
  fi
  if [ ! -f "$ZIP" ]; then
    echo "ERROR: ${ZIP} is missing after the build." >&2
    exit 1
  fi
done

python3 - <<'PY'
import xml.etree.ElementTree as ET

plugin = ET.parse("addon.xml").getroot()
module = ET.parse("script.module.raveresolver/addon.xml").getroot()
imports = {item.get("addon"): item.get("version")
           for item in plugin.findall("./requires/import")}
if imports.get("script.module.raveresolver") != module.get("version"):
    raise SystemExit(
        "ERROR: plugin addon.xml must require script.module.raveresolver %s"
        % module.get("version"))
print("plugin dependency: script.module.raveresolver %s" % module.get("version"))
PY

echo "repo/ artifacts are current and committed for plugin ${VERSION}, screen ${SCREEN_VERSION}, resolver ${MODULE_VERSION}"
