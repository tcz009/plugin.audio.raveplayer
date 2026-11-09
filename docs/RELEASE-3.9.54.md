# Release 3.9.54 — resolver + performance

**Status:** release **prepared, not released**. Branch `release/3.9.54` is
local only; `main`, the tag and the GitHub release are untouched, and nothing
was pushed or deployed in this pass.

**Prepared:** 9 November 2026 · **Branch:** `release/3.9.54`
**Release content:** `1510875` (`3.9.54: resolver wiring + speed pass`) plus the
release-docs/artifact commit on top of it. Take the live SHA from
`git rev-parse HEAD` — do not copy a literal from this document.

---

## 1. Versions

| Artifact | Version | Requires / notes |
|---|---|---|
| `plugin.audio.raveplayer` (`addon.xml`) | **3.9.54** | `xbmc.python` 3.0.1, `script.module.raveresolver` 1.1.0 |
| `script.raveplayer.ui` (`script.raveplayer.ui/addon.xml`) | **3.9.54** | `xbmc.python` 3.0.0, `plugin.audio.raveplayer` **3.9.54** (exact) |
| `script.module.raveresolver` | **1.1.0** | `xbmc.python` 3.0.0; unchanged code, now shipped in the repo catalogue |
| `repository.raveplayer` | 1.0.0 | unchanged; reads raw `main/repo/addons.xml` |
| `changelog.txt` (plugin) | 3.9.54 entry | merges the 3.9.52 perf pass and 3.9.53 resolver wiring |
| `script.raveplayer.ui/changelog.txt` | 3.9.54 entry | same release pair |
| `script.module.raveresolver/changelog.txt` | 1.1.0 entry | web resolver 1.6.64 signed Mega `stream` contract |
| `README.md`, `script.raveplayer.ui/README.md`, `PUBLISHING.md` | 3.9.54 / 3.9.54 / 1.1.0 | stale 3.9.53 / 3.9.50 / 923-test text corrected in this pass |
| `repo/addons.xml` | 3.9.54 / 3.9.54 / 1.1.0 / 1.0.0 | 4 entries; md5 `1cb691a45f8ee6f2116f2cfc55f73fd6` |

The screen pins the plugin exactly, so a mixed plugin/screen install cannot
happen through the repository. The plugin declares the resolver module, so Kodi
installs 1.1.0 first.

---

## 2. What ships

This is the first release that combines the two post-3.9.51 work streams:

**Performance (3.9.52).** Stale-while-revalidate paint for every Rave Screen
room (last good page per room on disk, painted immediately, refreshed on a
background thread, repainted only when rows changed); lazy plugin imports
(`load_plugin()` 322 ms → 50 ms, 1 module instead of 20); idle prefetch of
Latest and the RaveTapePacks index; and instant Back (one
`ActivateWindow(Home)`, 28–79 ms, replacing the twelve 200 ms attempts).

**Resolver wiring (3.9.53).** The plugin now requires
`script.module.raveresolver` 1.1.0. Provider pages (Mediafire, Google Drive,
Podomatic, Mega) are resolved once in `mode=play`, queued lazily per track in
Play all / Shuffle (never as raw pages or ciphertext), and downloaded from the
resolved direct URL. Non-Mega results keep Referer/User-Agent through Kodi's
`|Header=` suffix; Mega returns only the absolute signed
`<resolver-base>/api/mega/stream` URL, with no headers and no AES-CTR fallback.
Resolver failures log provider + exception class only — never the page URL,
token, cookie or signed stream.

No playback-failure policy changed: RTP failures remain silent, the loopback
bridge still applies after resolution, and the 500 MiB / 2 GiB / free-space /
Content-Length download guards are unchanged.

---

## 3. Device evidence

The 3.9.52 numbers and screens were captured on the Shield (Kodi 22.0 beta,
Estuary) and are unchanged by the release-docs pass:

- [`docs/PERF-3.9.52.md`](PERF-3.9.52.md) — method, before/after table and the
  honest >1 s list.
- [`docs/perf-3.9.52/home.png`](perf-3.9.52/home.png) — eleven rooms painted
  without importing a data module beyond `plugin.kodi`.
- [`docs/perf-3.9.52/latest-painted.png`](perf-3.9.52/latest-painted.png) —
  Latest painted from the saved page while the refresh runs.
- [`docs/KODI-RESOLVER-WIRING-3.9.53.md`](KODI-RESOLVER-WIRING-3.9.53.md) —
  resolver selection, Mega URL guard, play-all and download behaviour (code
  review evidence; **no device play test**).
- [`docs/KODI-RESOLVER.md`](KODI-RESOLVER.md) — module/service contract.
- [`docs/fullscreen-app-evidence/README.md`](fullscreen-app-evidence/README.md)
  and [`qa-checks.md`](fullscreen-app-evidence/qa-checks.md) — 3.9.51 shell
  baseline (eleven rooms, Search, Favourites, Downloads, About, Surprise).
- `test/test_resolver_wiring.py` — 37 offline tests for selection, headers,
  Mega stream URLs, play-all wrapping/offsets, downloads, quiet failures and
  the no-raw-page rule.

The Shield was checked read-only for this pass (see §6); no UI interaction and
no device change was made.

---

## 4. Verification in this pass

```sh
./scripts/check-repo-artifacts.sh
# plugin dependency: script.module.raveresolver 1.1.0
# repo/ artifacts are current and committed for plugin 3.9.54, screen 3.9.54, resolver 1.1.0

python3 -m unittest discover -s test     # run twice, fresh RAVEPLAYER_CACHE_DIR each time
```

| Run | Cache | Result |
|---|---|---|
| 1 | fresh temp dir | **1128 tests, OK** (23.0 s) |
| 2 | fresh temp dir | **1128 tests, OK** (22.4 s) |

The only non-dot output is the existing `ResourceWarning: unclosed file` from
test helpers; there are no failures, errors or skips. Local Python is 3.9.6;
CI (`build.yml`) runs 3.12 and is the authoritative matrix.

Release hygiene:

- 4 repo zips present and tracked: plugin, screen, resolver module and
  repository add-on.
- `repo/addons.xml` has 4 entries and its md5 matches `repo/addons.xml.md5`.
- Every zip's manifest version matches the filename and the catalogue; the
  screen requires plugin 3.9.54 and the plugin requires module 1.1.0.
- No `test/`, `__pycache__`, `.pyc`, `.DS_Store`, scratch or editor files in
  any shipped zip.
- No credentials in tracked files. `.git-auth/` is outside the repository and
  contains the workspace SSH key plus the 64-hex resolver service token; it is
  not tracked and no token is written into docs or code.
- A tracked scratch file, `special:/temp/raveplayer-live-7620df74c1b70356.m3u`
  (a Kool FM test playlist accidentally committed in 3.9.24), was removed so
  the tree contains no scratch artifacts.
- `git status` is clean after the release-docs/artifact commit.

### Release artifacts

| Asset | Bytes | SHA-256 |
|---|---:|---|
| `plugin.audio.raveplayer-3.9.54.zip` | 9,095,087 | `eb8cb9322e222e5a7f3351d895df032a48cb5bf9606af5bbf901af37e9810934` |
| `script.raveplayer.ui-3.9.54.zip` | 5,426,920 | `93eb442e55541995a226d7b41f70ec9abb01ea640f6a39182269fd33b31f3a22` |
| `script.module.raveresolver-1.1.0.zip` | 310,713 | `f0ccf3615ab5d0c0faaf2b56f474099fd1fd4e045488b7190a2e81643d2ed3bf` |
| `repository.raveplayer-1.0.0.zip` | 853,389 | `8ab30e4895f3f1f1e9d6d00cbec65b2a26b924f2e74aa0fa5234892ac700d609` |

`dist/` and `repo/` copies are byte-identical after the rebuild. Zip timestamps
change on every build, so a rebuild changes the hashes even when the contents
are identical; the hashes above describe the committed artifacts.

---

## 5. Known limitations (do not oversell)

1. **Plugin fallback lists are not row-cached.** The paint cache covers the
   Rave Screen rooms. `plugin.audio.raveplayer` Classic lists still pay Kodi's
   Python process start (~300 ms) and the source fetch on first use. This is
   unchanged and expected.
2. **Resident UI is deferred.** There is no always-on service or preloaded
   window. First paint is 556–629 ms script-internal (≈1.0–1.6 s externally,
   dominated by Kodi window activation); resident UI remains a follow-up, not a
   reverted experiment.
3. **Mega needs a reachable resolver and auth.** `resolver_service_url` is blank
   by default and `resolver_enable_mega` is off, so Mega links do not play out
   of the box. The user must set a LAN/Tailscale resolver base plus a Bearer
   token (or session cookie) and enable Mega. The service must expose both
   `/api/resolve` and `/api/mega/stream`; an unreachable service fails quietly
   by design.
4. **No audio Mega fixture.** End-to-end Mega audio playback was not tested;
   coverage is the 1.1.0 unit contract plus the plugin wiring tests (URL shape,
   prefix guard, no ciphertext, no headers). A real Mega track remains a
   post-release device check.
5. **Resolver wiring is code-only.** 3.9.53/3.9.54 were not played on the
   device as part of this pass. Mediafire/Drive/Podomatic/Mega playback and
   download need the owner's device check before being called device-verified.
6. **Classic search timeout is pre-existing.** The plugin search route can
   exceed 90 s; the screen Search room is the supported path. Not fixed here.
7. **Packaging observation.** `script.raveplayer.ui/raveui/screens/README-*.md`
   still ship inside the screen zip (known since 3.9.51); they are docs, not
   code, but a future packaging pass could exclude them.

---

## 6. Shield state — read-only check

ADB was used read-only through the workspace `platform-tools` binary; no UI
interaction and no device setting, file or add-on was changed.

| Check | Result |
|---|---|
| Kodi | `22.0-BETA1` |
| Rave add-on directories | `plugin.audio.raveplayer`, `script.raveplayer.ui`, `script.module.raveresolver`, `repository.raveplayer` |
| Orphan `*3.9.5x*` add-on dirs | **none** (the `addons.disabled-20261028` archive has no Rave entries) |
| Installed versions | plugin **3.9.54**, screen **3.9.54**, resolver **1.1.0**, repository 1.0.0 |
| Installed file hashes vs release zips | plugin 144/144 and screen 105/105 shipped code/assets identical (both `README.md` were updated after install); resolver 21/21 identical |
| Extra installed files | only runtime `__pycache__/*.pyc` (16 plugin, 15 screen), expected on Kodi 22 |
| Resolver settings | no `resolver_*` keys in the plugin settings file → URL/token blank, Mega off (defaults); no module settings file |
| Other | an old `plugin.audio.raveplayer-3.9.28.zip` remains in `addons/packages/` (installer leftover, not an add-on directory) |

Conclusion: the installed Shield package matches the 3.9.54 release code. The
only difference is the plugin/screen `README.md` inside the installed copies,
which predates this docs pass; the version manifests and all code/assets are
identical, so Kodi sees the same version and will not reinstall. This is not a
blocker.

---

## 7. Upgrade notes

- **Update the pair together.** Repository installs pull plugin 3.9.54, screen
  3.9.54 and resolver 1.1.0; the screen's exact plugin pin and the plugin's
  module dependency make a partial update fail visibly rather than mix versions.
- **Resolver settings start blank.** Existing installs have no `resolver_*`
  values, so:
  - direct, Mediafire, Google Drive and Podomatic pages resolve in-process
    without configuration;
  - Mega is **off** until the user enables it;
  - Podomatic/Mega service fallback needs `resolver_service_url` (LAN or
    Tailscale base, no trailing slash needed) and either
    `resolver_service_token` (Bearer, preferred) or
    `resolver_service_cookie` (`raveplayer_session=...`).
- **Restart Kodi once after updating** so the new plugin/screen processes load.
- **No userdata migration.** The paint cache is versioned by screen/plugin
  version, so old entries are ignored; it can be deleted safely at
  `special://profile/addon_data/script.raveplayer.ui/paint-cache` if a room ever
  paints stale rows.
- **RTP egress** settings are unchanged and remain user-configured; nothing in
  this release adds a default proxy.
- Rollback to 3.9.51/3.9.50 does not need the resolver module; 1.1.0 may stay
  installed unused or be removed afterwards.

---

## 8. Rollback

Previous good releases (both tagged locally and on the remote):

| Item | 3.9.51 pair | 3.9.50 pair |
|---|---|---|
| Tag | `v3.9.51` | `v3.9.50` |
| Commit | `1c0b9da9453849095529ba25ed380ed145a92f81` | `22cbf4d78a96b30b0663c97bf3121215a0ba2794` |
| Plugin / screen | 3.9.51 / 3.9.50 | 3.9.50 / 3.9.49 |
| Repo zips in the tag | plugin 3.9.51, screen 3.9.50, repository 1.0.0 | plugin 3.9.50, screen 3.9.49, repository 1.0.0 |

The 3.9.51 and 3.9.50 tags predate the resolver module, so their `repo/` has
three zips, not four. That is expected.

### Before the tag is pushed

If `main` was fast-forwarded and the release is rejected, restore `main` to the
previous release. Prefer a normal tree-restore commit (no force, works with
branch protection):

```sh
# in the main checkout, after `git fetch origin`
git checkout main
git status --short                         # must be clean
git read-tree -u --reset 1c0b9da           # 3.9.51 tree
git commit -m "Revert 3.9.54 release (tree restored to 3.9.51)"
git diff --stat 1c0b9da HEAD               # must be empty
git push origin main
```

For the 3.9.50 pair use `22cbf4d` instead. If force-with-lease is explicitly
allowed, `git push --force-with-lease=main:<current-main-sha> origin 1c0b9da:main`
is the shorter path; branch protection blocks it by default.

### After the tag/release exists

```sh
git push origin :refs/tags/v3.9.54          # delete the remote tag
# delete the GitHub release (UI or API) so no new downloads point at 3.9.54
# then restore main with the tree-restore commit above
```

Kodi clients that already updated keep 3.9.54 until the repository refreshes;
restoring the 3.9.51 tree makes the next daily check offer 3.9.51/3.9.50 again.

### Device rollback

The old zips are committed in the tags; extract them and install through Kodi:

```sh
git show v3.9.51:repo/plugin.audio.raveplayer/plugin.audio.raveplayer-3.9.51.zip > /tmp/plugin.audio.raveplayer-3.9.51.zip
git show v3.9.51:repo/script.raveplayer.ui/script.raveplayer.ui-3.9.50.zip > /tmp/script.raveplayer.ui-3.9.50.zip
```

Then Kodi → Add-ons → Install from zip file, in that order (plugin first,
screen second), and restart Kodi. Keep the resolver module installed or remove
it; 3.9.51 does not require it. No device action was taken in this pass.

---

## 9. Release commands (prepared — NOT executed)

Run from the `release/3.9.54` checkout after the release-docs commit, and only
with the Lead's explicit approval. Do **not** run these as part of the prep
pass.

```sh
# 0. Preconditions
git status --short                          # must be empty
./scripts/check-repo-artifacts.sh           # must pass
git fetch origin
git merge-base --is-ancestor origin/main HEAD && echo FF-OK
git rev-list --left-right --count origin/main...HEAD   # expect 0 <n>

# 1. Fast-forward main (this linked worktree keeps release/3.9.54 checked out)
git push origin HEAD:main
git ls-remote --heads origin main           # must equal HEAD

# 2. Tag the release commit and push (lightweight tag, like v3.9.50/v3.9.51)
git tag v3.9.54 HEAD
git push origin v3.9.54
```

Order matters: `main` first, then the tag. The tag push triggers
`.github/workflows/build.yml`, which runs the 1128 tests, rebuilds both trees,
checks the committed catalogue and creates the GitHub release with the four
assets (`softprops/action-gh-release@v2`). The Kodi update channel is the
committed `repo/` on `main`, not the release asset.

If branch protection is enabled as described in
[`docs/BRANCH-PROTECTION.md`](BRANCH-PROTECTION.md), the direct push in step 1
is rejected (PR + 1 approval + `test-and-package` required). In that case open
`release/3.9.54` → `main` as a PR, let `test-and-package` pass, merge with a fast
forward, then push the tag.

### GitHub release by API (only if a token exists)

**Current state: no GitHub API token is available.** The workspace
`.git-auth/` directory contains the SSH deploy key used by `core.sshCommand`
and the 64-hex resolver service token; neither is a GitHub API token. Prefer the
tag-triggered workflow. If the Lead supplies a token, use it from the
environment and never commit it:

```sh
export GITHUB_TOKEN=...    # supplied by the Lead; do not echo or commit
REPO=tcz009/plugin.audio.raveplayer

# Create only if the workflow did not already create the release.
RELEASE_ID=$(curl -sS -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/releases" \
  -d '{"tag_name":"v3.9.54","name":"3.9.54 — resolver + performance","draft":false,"prerelease":false}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

for f in dist/plugin.audio.raveplayer-3.9.54.zip \
         dist/script.raveplayer.ui-3.9.54.zip \
         dist/script.module.raveresolver-1.1.0.zip \
         repo/repository.raveplayer/repository.raveplayer-1.0.0.zip; do
  curl -sS -X POST \
    -H "Authorization: Bearer $GITHUB_TOKEN" \
    -H "Content-Type: application/zip" \
    --data-binary @"$f" \
    "https://uploads.github.com/repos/$REPO/releases/$RELEASE_ID/assets?name=$(basename "$f")"
done
```

If the workflow already created the release, uploading through the API will
return `422 already_exists`; use the release page or `gh release upload
v3.9.54 <files> --clobber` instead. Do not create a second release.

---

## 10. Release checklist

- [x] Plugin 3.9.54; screen 3.9.54 requiring plugin 3.9.54; resolver 1.1.0.
- [x] Plugin/screen/module changelogs, root README, screen README and
      `PUBLISHING.md` agree on 3.9.54 / 1.1.0.
- [x] `repo/addons.xml` + md5 current, 4 entries; `check-repo-artifacts.sh`
      passes.
- [x] 4 zips tracked and clean; no tests/bytecode/scratch inside.
- [x] 1128 tests green twice, fresh caches.
- [x] No secrets or scratch files in the tree; `git status` clean.
- [x] Shield read-only check: installed 3.9.54/3.9.54/1.1.0, no orphan 3.9.5x
      dirs, code hashes match the release zips.
- [ ] Lead approval to fast-forward `main`.
- [ ] Lead approval to push `v3.9.54`.
- [ ] GitHub API token, if the workflow release path is not used.
- [ ] Owner device check of Mediafire/Drive/Podomatic/Mega playback and
      download (resolver is code-only evidence today).
- [ ] Post-release: remote refs agree, raw `addons.xml` serves 3.9.54 and is
      self-consistent, both CI runs green, release has 4 assets, Kodi offers
      3.9.54/3.9.54/1.1.0.

---

## 11. Flags for the Lead

1. **No GitHub API token.** `.git-auth/` has an SSH key and a resolver token,
   not a GitHub token. The tag-triggered workflow is the intended release path;
   the API block above only applies if a token is supplied. Not a blocker for
   tag/push (SSH is configured).
2. **Branch protection.** If `main` protection is active, `git push HEAD:main`
   will be rejected and the PR route is required. Confirm the current repo
   setting before promising a direct fast-forward.
3. **The Shield already runs 3.9.54.** Installed code matches this package, so
   the "release" is effectively already on the device; rollback still works via
   the 3.9.51/3.9.50 zips. The installed plugin/screen `README.md` predates this
   docs pass (doc-only difference, same version).
4. **Resolver is not device-verified.** Treat Mega/Mediafire/Drive/Podomatic
   playback and Mega downloads as post-release checks until the owner runs them.
5. **Re-run artifact and test checks after any further edit.** Zip hashes change
   on every rebuild; update §4 if the tree changes again.
