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

`dist/raveplayer-main.bundle` is a git bundle of the current `main` and all tags
(`dist/` is gitignored, so this is a local convenience copy). Regenerate it from
the current checkout, then clone it on any machine with write access:

```sh
git bundle create dist/raveplayer-main.bundle --all
git clone dist/raveplayer-main.bundle raveplayer
cd raveplayer
git remote set-url origin https://github.com/tcz009/plugin.audio.raveplayer.git
git push -u origin main --tags
```

## After pushing

The 3.9.x release flow is: bump `addon.xml` + `changelog.txt`; rebuild the
artifacts; commit the regenerated `repo/`; then tag. The current release is
**3.9.5** (source artefacts built; tag/release to be created by the owner).

```sh
# 1. version bump already in addon.xml/changelog.txt
./scripts/build.sh          # dist/plugin.audio.raveplayer-<version>.zip
./scripts/build-repo.sh     # repo/addons.xml(.md5) + versioned repo zip
./scripts/check-repo-artifacts.sh   # must pass before committing

# 2. commit source + generated repo/, push main
git add -A
git commit -m "<version> -- <summary>"
git push origin main

# 3. tag; the build workflow attaches the zips to the GitHub release
git tag v<version>
git push origin v<version>
```

- Actions → `build` runs the 192 unit tests, validates `addon.xml`, rebuilds
  `dist/` and `repo/`, and then fails if `repo/addons.xml`, `repo/addons.xml.md5`
  or the current versioned plugin zip are not committed
  (`scripts/check-repo-artifacts.sh`). Generated repo/ files must be committed or
  Kodi auto-updates stay on the old version even though the tag and release exist.
- Kodi install: download `plugin.audio.raveplayer-<version>.zip` from `dist/` or
  the GitHub release → Add-ons → Install from zip file. Alternatively keep
  `repository.raveplayer-1.0.0.zip` installed once and let Kodi update from
  `repo/addons.xml`.
- Kodi 20 (Nexus) through Kodi 22 (Piers); Kodi 19 Matrix is not supported
  (`xbmc.python` 3.0.1).

## Permission check

To test write access without pushing:

```sh
curl -s -o /dev/null -w '%{http_code}\n' -X PUT \
  -H "Authorization: Bearer $GITHUB_TOKEN" -H 'Accept: application/vnd.github+json' \
  -d '{"message":"probe","content":"dGVzdA=="}' \
  https://api.github.com/repos/tcz009/plugin.audio.raveplayer/contents/.probe.txt
```

`201` means write works; `403` means the token is still read-only.
