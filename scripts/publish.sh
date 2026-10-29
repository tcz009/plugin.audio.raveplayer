#!/bin/sh
# Publish Rave Player to GitHub.
#
#   GITHUB_TOKEN=ghp_xxx ./scripts/publish.sh
#
# Creates the repository if it does not exist, then pushes main.
set -eu
cd "$(dirname "$0")/.."

REPO="${REPO:-plugin.audio.raveplayer}"
OWNER="${OWNER:-tcz009}"

if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "No GITHUB_TOKEN set. Create one (repo scope) at https://github.com/settings/tokens" >&2
    echo "then:  GITHUB_TOKEN=ghp_xxx ./scripts/publish.sh" >&2
    exit 1
fi

echo "== checking $OWNER/$REPO =="
STATUS=$(curl -s -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer $GITHUB_TOKEN" \
    "https://api.github.com/repos/$OWNER/$REPO")

if [ "$STATUS" = "404" ]; then
    echo "creating $OWNER/$REPO"
    curl -sS -X POST \
        -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        -d "{\"name\":\"$REPO\",\"description\":\"Rave Player — oldskool rave, jungle and pirate radio for Kodi (2026 rebuild)\",\"private\":false}" \
        "https://api.github.com/user/repos" >/dev/null
elif [ "$STATUS" != "200" ]; then
    echo "unexpected API status $STATUS" >&2
    exit 1
fi

git remote remove origin 2>/dev/null || true
git remote add origin "https://$OWNER:$GITHUB_TOKEN@github.com/$OWNER/$REPO.git"
git branch -M main
git push -u origin main
git remote set-url origin "https://github.com/$OWNER/$REPO.git"
echo "published: https://github.com/$OWNER/$REPO"
