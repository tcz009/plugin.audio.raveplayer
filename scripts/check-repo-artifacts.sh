#!/bin/sh
# Fail when the committed repo/ catalogue is stale relative to addon.xml.
#
# Run after scripts/build-repo.sh (CI and locally before committing). It
# deliberately does NOT compare binary zips: zip timestamps change on every
# build. It checks the two text artifacts and that the versioned plugin zip
# is tracked by git.
set -eu
cd "$(dirname "$0")/.."
VERSION=$(python3 -c "import xml.etree.ElementTree as E;print(E.parse('addon.xml').getroot().get('version'))")
ZIP="repo/plugin.audio.raveplayer/plugin.audio.raveplayer-${VERSION}.zip"

if [ -n "$(git status --porcelain -- repo/addons.xml repo/addons.xml.md5)" ]; then
  echo "ERROR: repo/addons.xml or repo/addons.xml.md5 is modified/untracked." >&2
  echo "       Run ./scripts/build-repo.sh and commit the regenerated repo/." >&2
  git status --short -- repo/addons.xml repo/addons.xml.md5 >&2 || true
  exit 1
fi

if ! git ls-files --error-unmatch "$ZIP" >/dev/null 2>&1; then
  echo "ERROR: ${ZIP} is not tracked by git." >&2
  echo "       Run ./scripts/build-repo.sh and commit the regenerated repo/." >&2
  exit 1
fi

if [ ! -f "$ZIP" ]; then
  echo "ERROR: ${ZIP} is missing after the build." >&2
  exit 1
fi

echo "repo/ artifacts are current and committed for ${VERSION}"
