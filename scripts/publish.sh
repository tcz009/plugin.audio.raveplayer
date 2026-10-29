#!/bin/sh
# Push the add-on to GitHub.
#
#   GITHUB_TOKEN=github_pat_xxx ./scripts/publish.sh
#
# The token never touches .git/config or the shell history: it is passed as a
# one-shot Authorization header and the remote stays a clean HTTPS URL.
set -eu
cd "$(dirname "$0")/.."

OWNER="${OWNER:-tcz009}"
REPO="${REPO:-plugin.audio.raveplayer}"
URL="https://github.com/$OWNER/$REPO.git"

if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "Set GITHUB_TOKEN, e.g.  GITHUB_TOKEN=github_pat_xxx ./scripts/publish.sh" >&2
    exit 1
fi

AUTH=$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64)

git branch -M main
git remote remove origin 2>/dev/null || true
git remote add origin "$URL"

echo "pushing $(git rev-parse --short HEAD) to $URL"
git -c http.extraHeader="Authorization: Basic $AUTH" push -u origin main

echo "published: https://github.com/$OWNER/$REPO"
