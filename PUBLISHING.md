# Publishing Rave Player

The repository is ready locally: branch `main`, all commits, the installable zip
and the Kodi repo layout. Only the push needs credentials.

Target: <https://github.com/tcz009/plugin.audio.raveplayer>

## Option 1 — token with write access (fastest)

A fine-grained token needs **two** things set, and the first one is the usual
trap: a token created with *Public repositories (read-only)* reads everything
and writes nothing.

1. <https://github.com/settings/tokens?type=beta> → your token → **Edit**
2. **Repository access** → *Only select repositories* → `plugin.audio.raveplayer`
   → role **Read and write** (or *All repositories*)
3. **Permissions → Repository permissions → Contents → Read and write**
4. Save, then:

```sh
GITHUB_TOKEN=github_pat_xxx ./scripts/publish.sh
```

The token is sent as a one-shot `Authorization` header and is never written to
`.git/config`.

## Option 2 — SSH key

```sh
cat ~/.ssh/id_rsa.pub        # paste at https://github.com/settings/keys
git remote set-url origin git@github.com:tcz009/plugin.audio.raveplayer.git
git push -u origin main
```

## Option 3 — push from your own terminal

If you are already signed in locally (GitHub Desktop, `gh auth login`, or the
macOS credential helper):

```sh
cd ~/Documents/deepseek-harness/default-workspace/raveplayer
git push -u origin main
```

## Option 4 — carry the repo elsewhere

`dist/raveplayer-main.bundle` is a complete git bundle (all history). On any
machine with write access:

```sh
git clone raveplayer-main.bundle raveplayer
cd raveplayer
git remote set-url origin https://github.com/tcz009/plugin.audio.raveplayer.git
git push -u origin main
```

## After pushing

- Actions → `build` runs the 15 unit tests and attaches the zip to `v*` tags.
- Create a release: `git tag v3.3.0 && git push origin v3.3.0`.
- Kodi install: download `plugin.audio.raveplayer-3.3.0.zip` from `dist/` (or a
  release) → Add-ons → Install from zip file.

## Permission check

To test write access without pushing:

```sh
curl -s -o /dev/null -w '%{http_code}\n' -X PUT \
  -H "Authorization: Bearer $GITHUB_TOKEN" -H 'Accept: application/vnd.github+json' \
  -d '{"message":"probe","content":"dGVzdA=="}' \
  https://api.github.com/repos/tcz009/plugin.audio.raveplayer/contents/.probe.txt
```

`201` means write works; `403` means the token is still read-only.
