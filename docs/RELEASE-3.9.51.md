# Release 3.9.51 — full-screen Rave app

**Status:** release **prepared, not released**. Branch `feat/app-integration` is
pushed; `main`, the tag and the GitHub release are deliberately untouched, and
nothing was deployed to the Shield or the NAS.

**Prepared:** 5 November 2026 · **Branch:** `feat/app-integration`
**Release content commit:** `437bcfa` (`3.9.51: align release docs with
3.9.51/3.9.50 and rebuild repo artifacts`)
**Remote branch:** <https://github.com/tcz009/plugin.audio.raveplayer/tree/feat/app-integration>

---

## 1. Versions

| Artifact | Version | Requires / notes |
|---|---|---|
| `plugin.audio.raveplayer` (`addon.xml`) | **3.9.51** | `xbmc.python` 3.0.1 |
| `script.raveplayer.ui` (`script.raveplayer.ui/addon.xml`) | **3.9.50** | `plugin.audio.raveplayer` **3.9.51** (exact), `xbmc.python` 3.0.0 |
| `repository.raveplayer` | 1.0.0 | unchanged; points Kodi at raw `main/repo/addons.xml` |
| `changelog.txt` (plugin) | 3.9.51 entry | top entry describes the full-screen app |
| `script.raveplayer.ui/changelog.txt` | 3.9.50 entry | the *screen* version; its first section documents the 3.9.51 shell pass |
| `README.md` | states plugin 3.9.51 + screen 3.9.50 | install section |
| `script.raveplayer.ui/README.md` | states screen 3.9.50 requiring plugin 3.9.51 | was stale at 3.9.48 before this pass |
| `docs/FULLSCREEN-APP.md` | 3.9.51 / 3.9.50 | architecture, device evidence |
| `docs/APP-INTEGRATION-3.9.51.md` | 3.9.51 / 3.9.50 | module ownership evidence |
| `repo/addons.xml` | 3.9.51 / 3.9.50 / 1.0.0 | 3 entries; md5 `3ab4bafbc55f872d56da1c669386bfb2` |
| `repo/addons.xml.md5` | `3ab4bafbc55f872d56da1c669386bfb2` | matches the committed `addons.xml` |

The screen version deliberately stays at 3.9.50: only the plugin version is
bumped by this integration, and the screen pins the 3.9.51 plugin so the pair
cannot be mixed accidentally.

---

## 2. Test evidence

Command (from the repo root):

```sh
RAVEPLAYER_CACHE_DIR="$(mktemp -d /tmp/rave-release-cache-XXXXXX)" \
  python3 -m unittest discover -s test
```

| Run | Cache | Result | Time |
|---|---|---|---|
| 1 (pre-doc tree) | fresh temp dir | **923 tests, OK** | 41.4 s |
| 2 (pre-doc tree) | fresh temp dir | **923 tests, OK** | 50.2 s |
| 3 (after doc/artifact rebuild) | fresh temp dir | **923 tests, OK** | 71.3 s |
| 4 (after doc/artifact rebuild) | fresh temp dir | **923 tests, OK** | 58.8 s |

- Local Python 3.9.6; CI (`build.yml`) uses 3.12. Both runs used a per-run
  `RAVEPLAYER_CACHE_DIR`, so no cache state carried between runs.
- The only output besides dots is `ResourceWarning: unclosed file` from test
  helpers; there are no failures, errors or skips reported.
- No behaviour changes were made in this pass. The only source edits were
  release-doc version text (`README.md`, `script.raveplayer.ui/README.md`,
  `PUBLISHING.md`).

Artifact check:

```sh
./scripts/check-repo-artifacts.sh
# repo/ artifacts are current and committed for plugin 3.9.51, screen 3.9.50
```

---

## 3. Artifact audit

Built with `./scripts/build.sh && ./scripts/build-repo.sh`; committed under
`repo/` and `dist/` (the latter is gitignored).

| Zip | Files | Tests/docs/pycache | Notes |
|---|---|---|---|
| `repo/plugin.audio.raveplayer/plugin.audio.raveplayer-3.9.51.zip` | 144 | none | byte-identical to the working tree |
| `repo/script.raveplayer.ui/script.raveplayer.ui-3.9.50.zip` | 103 | none | byte-identical to `script.raveplayer.ui/` |
| `repo/repository.raveplayer/repository.raveplayer-1.0.0.zip` | 3 | none | `addon.xml`, `icon.png`, `fanart.jpg` |

- Both add-on zips are present in `repo/` and `dist/`; `repo/addons.xml` lists
  all three add-ons (`plugin.audio.raveplayer`, `script.raveplayer.ui`,
  `repository.raveplayer`).
- Zip contents were compared file-by-file (SHA-256) with the working tree: no
  differences, no missing files, no extra files.
- The plugin zip contains `addon.xml` 3.9.51; the screen zip contains
  `addon.xml` 3.9.50 + `requires plugin.audio.raveplayer 3.9.51`.
- **Published raw `main` is still the previous release** (expected until this
  branch lands): plugin **3.9.50**, screen **3.9.49**, md5
  `83837125e407daa80054892aec23b8f2`, and the raw `addons.xml.md5` matches the
  raw `addons.xml` (self-consistent). The local 3.9.51 catalogue intentionally
  differs until `main` is fast-forwarded.

---

## 4. Git state and ancestry

```text
origin/main          22cbf4d  3.9.50: clamp out-of-range pages (advisor P3-1)
tag v3.9.50          22cbf4d  (lightweight tag; previous release)
feat/app-integration HEAD     release content 437bcfa + release notes commits
git merge-base --is-ancestor origin/main feat/app-integration  ->  exit 0
git rev-list --left-right --count origin/main...feat/app-integration  ->  0  N
```

`main` is a strict ancestor: the merge is a clean fast-forward, 0 commits
behind and only release commits ahead (14 ahead at the first push; the
release-notes commits add to that, so take the live count from git rather than
a literal). `origin/main` and local `main` both point at `22cbf4d`; no rebase
or merge commit is needed.

Pushed ref (done in this pass, nothing else):

```sh
git push -u origin feat/app-integration
# * [new branch] feat/app-integration -> feat/app-integration
```

---

## 5. Release steps (owner approval required — NOT yet executed)

Run from the repo root. The SSH `core.sshCommand` (workspace key) is already
configured, so plain `git push` works.

```sh
# 0. Preconditions
git status --short                       # must be clean
git fetch origin
git rev-list --count origin/main..feat/app-integration   # live count (0 behind)
git merge-base --is-ancestor origin/main feat/app-integration && echo FF-OK

# 1. Confirm the branch is pushed (done)
git ls-remote --heads origin feat/app-integration          # must equal HEAD

# 2. Fast-forward main only after explicit approval
git checkout main
git merge --ff-only origin/main
git merge --ff-only feat/app-integration
git push origin main

# 3. Tag the release commit (lightweight, matching v3.9.50 and earlier tags)
git tag v3.9.51 feat/app-integration
git push origin v3.9.51

# 4. No manual GitHub release: the tag-triggered build workflow creates it
#    and attaches dist/*.zip + repo/repository.raveplayer/*.zip.
```

Order matters: push `main` **before** the tag. Kodi's repository add-on reads
`raw.githubusercontent.com/.../main/repo/addons.xml`, so the repository channel
is live as soon as `main` is pushed; the tag only produces the GitHub release
and its assets.

> Do not run `scripts/publish.sh` for this release: it force-renames the branch
> to `main` and pushes with a token. The prepared flow above is the SSH path.

---

## 6. Rollback

Previous good release:

| Item | Value |
|---|---|
| Previous `main` | `22cbf4d78a96b30b0663c97bf3121215a0ba2794` |
| Previous tag | `v3.9.50` (points at `22cbf4d`) |
| Previous add-ons | plugin 3.9.50 / screen 3.9.49 |

Before the tag is pushed (main fast-forwarded, release rejected):

```sh
# Preferred when main allows force-with-lease; requires owner approval.
# <main-sha> = the value of `git rev-parse origin/main` immediately before this
# rollback (i.e. the fast-forwarded release commit, the tag's commit).
git push --force-with-lease=main:<main-sha> origin 22cbf4d:main
```

If force-pushing `main` is not allowed, publish a normal commit whose **tree** is
the previous release tree. This avoids the merge commits in the release range
(which make `git revert <range>` conflict) and needs no force:

```sh
git checkout main
git status --short                       # must be clean first
git read-tree -u --reset 22cbf4d         # index + working tree = v3.9.50 tree
git commit -m "Revert 3.9.51 release (tree restored to 3.9.50)"
git diff --stat 22cbf4d HEAD             # must be empty
git push origin main
```

After the tag/release exists:

```sh
git push origin :refs/tags/v3.9.51        # delete the remote tag
# then delete the CI-created GitHub release in the UI (Assets -> Delete)
# then roll main back with one of the two commands above
```

Kodi clients that already updated keep 3.9.51 until the repository refreshes;
restoring `repo/` to the 3.9.50 tree (force push or revert) makes the next
daily check offer 3.9.50 again. Force-pushing `main` rewrites published
history — only do it with explicit owner approval and after deleting the tag.

---

## 7. Release checklist

| Item | Status | Evidence |
|---|---|---|
| Stale `service.raveplayer.ui` removed | **PASS** | no tracked files; `repo/` contains only the plugin, screen and repository add-ons; `addons.xml` has 3 entries. `docs/RAVE-SCREEN-DIAGNOSIS.md` mentions the old service only as history. |
| Kodi web server on 8080, debug overlay/logging off | **OWNER/DEVICE CHECK** | cannot be verified from the repo and no device access is used in this pass. Device evidence records the web server restored to 8080 and the debug overlay turned off for the final frames (`docs/FULLSCREEN-APP.md` §10, `docs/fullscreen-app-evidence/README.md`). Re-check on the Shield before announcing. |
| Quiet RTP playback failures preserved | **PASS** | `resources/lib/routes.py` keeps `quiet=is_rtp` and `_fail_playback(..., quiet=True)`; `resources/lib/rtp_bridge.py` treats bridge failure as non-fatal. Covered by `test/test_rtp_bridge_routes.py` (`test_unplayable_rtp_resolve_is_quiet`, `test_bridge_failure_falls_back_to_direct_quietly`). |
| No hardcoded private proxy default | **PASS** | `resources/settings.xml`: `rtp_egress_proxy ... default=""` (blank = direct). No private proxy address in shipped code. LAN addresses appear only in tests (security fixtures) and historical/device docs. |
| GitHub release asset limitation documented | **PASS** | no API token is available locally; releases/assets are created only by the tag-triggered `build` workflow using its own `GITHUB_TOKEN`. The Kodi update path is committed `repo/` on `main`, not a hand-uploaded release asset. `PUBLISHING.md` now says this explicitly. |

### Other release checks

- [x] Plugin `addon.xml` 3.9.51; screen `addon.xml` 3.9.50 requiring 3.9.51.
- [x] Plugin changelog, screen changelog, root README, screen README,
      `FULLSCREEN-APP.md`, `APP-INTEGRATION-3.9.51.md` agree.
- [x] 923 tests green twice, fresh temp cache each run.
- [x] `repo/addons.xml` + md5 current; `check-repo-artifacts.sh` passes.
- [x] Both add-on zips present and byte-identical to the tree.
- [x] `main` is a clean ancestor (fast-forward possible).
- [ ] Owner approval to fast-forward `main`.
- [ ] Owner approval to push `v3.9.51`.
- [ ] Post-release verification (below).

---

## 8. Post-release verification

Run immediately after `main` + `v3.9.51` are pushed:

```sh
# 1. Remote refs agree
git ls-remote --heads origin main            # 437bcfa... (or this doc's commit)
git ls-remote --tags origin v3.9.51          # same commit
git rev-list --count origin/main..origin/v3.9.51   # 0

# 2. Raw catalogue serves the new pair and is self-consistent
curl -sSL https://raw.githubusercontent.com/tcz009/plugin.audio.raveplayer/main/repo/addons.xml \
  | grep -E 'id="(plugin.audio.raveplayer|script.raveplayer.ui)"' -A2
curl -sSL https://raw.githubusercontent.com/tcz009/plugin.audio.raveplayer/main/repo/addons.xml \
  | md5 -q                                  # equals the raw .md5 file
curl -sSL https://raw.githubusercontent.com/tcz009/plugin.audio.raveplayer/main/repo/addons.xml.md5

# 3. Versioned zips are downloadable from the repo channel
curl -sI https://raw.githubusercontent.com/tcz009/plugin.audio.raveplayer/main/repo/plugin.audio.raveplayer/plugin.audio.raveplayer-3.9.51.zip | head -1
curl -sI https://raw.githubusercontent.com/tcz009/plugin.audio.raveplayer/main/repo/script.raveplayer.ui/script.raveplayer.ui-3.9.50.zip | head -1
```

4. GitHub Actions: `build` green on the `main` push and on the `v3.9.51` tag;
   the release exists with the two `dist/*.zip` assets plus
   `repository.raveplayer-1.0.0.zip`.
5. Kodi (Shield, Kodi 22): force a repository refresh, confirm
   **3.9.51 / 3.9.50** offered, install/update the pair together, dependency
   shows satisfied, app launches from the first root row, Back exits to Home,
   Classic lists still open.
6. Kodi settings: web server 8080, debug off; no `service.raveplayer.ui` in the
   installed add-on list.
7. RTP failure behaviour: force a bad RTP playback — it must fail quietly (no
   dialog/banner), and `rtp_egress_proxy` must still be blank unless the owner
   deliberately set a proxy.
8. Watch the first daily Kodi repository update after release: it must find
   3.9.51 without a manual "install from zip".

---

## 9. Non-blocking observations

- `script.raveplayer.ui/raveui/screens/README-library.md` and `README-live.md`
  (702 lines of integration notes, including one example LAN ADB address) are
  shipped inside the screen zip because `build.sh` copies `raveui/` wholesale.
  They are not `docs/`, tests or bytecode, so the artifact audit passes, but a
  future packaging pass could exclude `raveui/**/README*.md`.
- Local Python is 3.9.6; CI runs 3.12. Both are supported, and the suite is
  green, but the 3.12 CI run on the `main` push is the authoritative check.
- The tag should be created on the final branch HEAD (this document's commit,
  one commit after `437bcfa`); the release content commit is otherwise
  identical in code and artifacts.
