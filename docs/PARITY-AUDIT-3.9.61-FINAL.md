# PARITY AUDIT — Rave Player 3.9.61 (FINAL)

**Audited commit:** `3de8125e4a5cdece989c4629e79ef380b9c5c37b`
(`3.9.61: direct-launch fix, RAVE PLAYER branding, launcher tests`), branch
`feat/3.9.61-parity`.

**Exact-commit method:** the worktree was clean at `3de8125` when the audit
began. It advanced during the audit (see §8). Every result below for
`3de8125` was re-run against an exact `git archive 3de8125` snapshot in
`/tmp/parity-audit-361/snapshot` (no `.git`, no other process writing to it),
so the primary findings are not affected by the later worktree movement.

**No device, no ADB, no source edits, no push, no tag.** Only this report was
created. Tests, a controller harness with the repo's own fake plugin modules,
and read-only queries to the public radio-browser API were used. The API
queries were used solely to prove whether a station-tag string returns stations.

**Compared:** `docs/PARITY-AUDIT-3.9.60.md` (in `kodi-cancel-safe`),
`docs/PARITY-3.9.61.md`, `docs/RELEASE-3.9.61.md`, `routes.py` (classic tree),
`script.raveplayer.ui/raveui/**`, `default.py`, skin XML, `addon.xml`,
`repo/addons.xml` and the shipped zips.

---

## 0. Verdict

| Question | 3de8125 (audited commit) | 18c2572 (parity-fix commit; later HEAD 5acbe7c, §8.3) |
|---|---|---|
| Launcher correct? | **PASS** (bare + `?mode=root` launch; every other mode dispatches) | **PASS**, but `?mode=root` now dispatches (spec deviation — see §1.4) |
| Every classic destination reachable? | **FAIL** — 46 PASS + 1 PARTIAL; the one FAIL row is 3 of 6 Live genre doors loading no stations | **PASS against the task checklist** — 6/6 genres now load; one matrix row (`pirate_station`) remains content-different |
| Branding consistent? | **FAIL** — window/skin fixed; notifications, About row, add-on metadata still "Rave Screen" | **PARTIAL** — notifications + About row fixed; add-on metadata and `routes.py` notifications still "Rave Screen" |
| Quality (dead rows, duplicates, About links, art) | **FAIL** — About links dead; ungated Mixcloud rows; duplicate Licence; caps | **PARTIAL** — About links dead; two "Rave Player" + two "Licence" rows; ungated Mixcloud rows |
| Release hygiene | **PARTIAL** — versions/artifacts/tests/secrets OK; RELEASE doc hashes/count stale | **PARTIAL** — 1206 OK, plugin hash corrected; screen/resolver hashes still stale |
| **Verdict** | **NOT COMPLETE** | **PARITY COMPLETE (destinations), release polish incomplete** |
| Safe for the one install? | **Yes** (no crash/data-loss regression; 3 empty genre doors) | **Yes** (recommended build; no crash/data-loss regression) |

`18c2572` fixes the one P1 parity defect found in `3de8125`
(`script.raveplayer.ui/raveui/controller.py:2008`, live-genre tag) and the
in-window branding/About label. It does **not** fix the About links, the
ungated Mixcloud rave rows, the add-on metadata, the content caps, or the
release-document hashes.

---

## 1. Direct launch — PASS at 3de8125

### 1.1 Code

`default.py:11` imports `xbmc`. `_maybe_launch_screen` (`default.py:16-37`)
parses `argv[2:]`, strips a leading `?` (`default.py:25,28`), and launches only
when `mode in (None, "", "root")` (`default.py:30`), then runs
`RunScript(script.raveplayer.ui)` only if
`System.AddonIsEnabled(script.raveplayer.ui)` is true. Any exception returns
`False`, so dispatch still happens.

### 1.2 Independent runtime probe (exact 3de8125 snapshot, fake `xbmc`)

`main()` was called with a fake `xbmc` that records `executebuiltin` and
`getCondVisibility`; `routes.dispatch` was replaced by a recorder.

| argv query | RunScript? | dispatch? |
|---|---|---|
| `""` (bare launch) | **yes** | no |
| `?mode=root` | **yes** | no |
| `?mode=play&url=…` | no | **yes** (`play`) |
| `?mode=classic_root` | no | **yes** |
| `?mode=archive_item&id=…` | no | **yes** |
| `?mode=download_start&url=…` | no | **yes** |
| `?mode=fav_remove&id=…` | no | **yes** |
| `?mode=root&extra=1` | no | **yes** |
| `mode=play` without a leading `?` | no | **yes** |
| bare launch, screen add-on disabled | no | **yes** (2-row root) |

**App playback still reaches the plugin.** Building the real
`PlaybackService._plugin_path()` URL
(`plugin://plugin.audio.raveplayer/?mode=play&url=…`) and feeding it to
`main()` dispatches `mode=play`; `executebuiltin` is not called. This was
tested for both an archive track and a live station.

### 1.3 Tests

`python3 -m unittest test.test_compat` → **10 tests, OK** (3 new
`DirectLaunchTests`). The shipped tests cover bare, `?mode=root` and
`?mode=play`; they do **not** cover `?mode=classic_root` or
`?mode=archive_item` — the independent probe above does.

### 1.4 Known deviations / caveats

* **`?mode=root` at 18c2572 now dispatches** (`default.py:30` changed to
  `mode not in (None, "")`). Bare launch still opens the app. This fixes the
  `classic_root` Back-row loop (§8.2) but no longer matches the task's literal
  "launches for no-mode/root". It is a product decision, not a crash.
* At 3de8125, `classic_root`'s Back row targets `?mode=root`
  (`routes.py:857`), which the launcher intercepts. Pressing the explicit
  Back row in Classic lists therefore launches the app, and Back from the app
  returns to Classic lists: a repeatable toggle rather than "up". 18c2572
  changes `?mode=root` to a real directory and removes the toggle.
* `routes.root` (the 2-row directory) is only reachable when the screen
  add-on is disabled (or at 18c2572 via `?mode=root`). With the screen
  enabled, the root's "Rave Player" (`mode=screen`) row is not normally
  reached. Harmless dead code.

---

## 2. Destination parity matrix

Status legend: **PASS** = page/row renders with real routing (controller
harness + fake plugin modules; real `filters.json`/`rave-catalog.json` where
noted). **PARTIAL** = reachable but the old content shape is not reproduced.
**FAIL** = opens but yields no content / the destination is effectively dead.

| # | Destination | Screen path | 3de8125 | 18c2572 | Evidence |
|---|---|---|---|---|---|
| 1 | Latest | Home → Latest | PASS | PASS | 1 pack row with fake `latest.recent_packs`; content is packs only (see §4.2) |
| 2 | Tape Packs hub | Home → Tape Packs | PASS | PASS | 7 rows: Toronto, JungleTapes, RaveTapePacks, Classic Pack Series, By Rave, By Year, Every Pack |
| 3 | Toronto | Packs → Toronto | PASS | PASS | genre rows render |
| 4 | Toronto genre | Packs → Toronto → genre | PASS | PASS | track rows render |
| 5 | JungleTapes | Packs → JungleTapes | PASS | PASS | show rows render |
| 6 | JungleTapes show | Packs → JungleTapes → show | PASS | PASS | track rows render |
| 7 | RaveTapePacks | Packs → RaveTapePacks | PASS | PASS | 5 index rows (By Event/DJ/MC/Year, All Packs) |
| 8 | RTP index | RaveTapePacks → index | PASS | PASS | category rows render |
| 9 | RTP category | index → category | PASS | PASS | post rows render |
| 10 | RTP pack / saved pack | pack / Favourites | PASS | PASS | track rows; saved `legacy_pack` opens via library route |
| 11 | RTP All Packs | RaveTapePacks → All Packs | PASS | PASS | post rows + cursor page |
| 12 | Classic Pack Series | Packs → Classic Pack Series | PASS | PASS | **16** real filters (`filters.json`), Kool→World Dance |
| 13 | Classic filter | Series → series | PASS | PASS | archive rows render |
| 14 | Filter live door | Series → series → live now | PASS | PASS | Kool FM first row is `▶ Kool FM — live now`; opening gives stations |
| 15 | By Rave, Venue & Promoter | Packs → By Rave | PASS | PASS | **55** real catalogue entries |
| 16 | One rave | By Rave → rave | PASS | PASS | archive packs render; Mixcloud row is ungated (§4.3) |
| 17 | By Year | Packs → By Year | PASS | PASS | **40** years, 2026→1987 |
| 18 | One year | By Year → year | PASS | PASS | archive rows via `latest.year_query` |
| 19 | Every Pack | Packs → Every Pack | PASS | PASS | `tapepacks` archive query; rows render |
| 20 | Archive pack detail | Every Pack/Latest → pack | PASS | PASS | track rows render |
| 21 | Pirate Radio hub | Home → Pirate Radio | PASS | PASS | 3 rows: Hardscore, Archives, Kool FM Sets |
| 22 | Hardscore | Hub → Hardscore | PASS | PASS | post row renders |
| 23 | Hardscore post | Hub → Hardscore → post | PASS | PASS | media rows render |
| 24 | Pirate Radio Archives | Hub → Archives | PASS | PASS | recording rows render |
| 25 | Pirate station | Hub → Archives → station | **PARTIAL** | **PARTIAL** | flat recording list; no station page, DJs/credit/note dropped (§4.4) |
| 26 | Kool FM Sets | Hub → Kool FM Sets | PASS | PASS | live row + archive sets |
| 27 | Mixes & Shows | Home → Mixes & Shows | PASS | PASS | 8 rows (adds Hardscore, Archives vs classic 6) |
| 28 | Podcasts & Mixes | Mixes → Podcasts | PASS | PASS | feed rows render |
| 29 | Podcast feed | Podcasts → feed | PASS | PASS | episode rows render |
| 30 | DNBRADIO | Mixes → DNBRADIO | PASS | PASS | show rows render |
| 31 | DNBRADIO show | DNBRADIO → show | PASS | PASS | resolves/plays via `_resolve_and_play` |
| 32 | GetDarker | Mixes → GetDarker | PASS | PASS | rows render with fake hand-off |
| 33 | GetDarker set | GetDarker → set | PASS | PASS | external row; empty state generic when Mixcloud absent (§4.3) |
| 34 | Moxser | Mixes → Moxser | PASS | PASS | mix rows render |
| 35 | Moxser mix | Moxser → mix | PASS | PASS | resolves/plays; no favourite/download (§4.2) |
| 36 | Mikus Musik | Mixes → Mikus Musik | PASS | PASS | post rows render |
| 37 | Mikus post | Mikus → post | PASS | PASS | media + Mixcloud hand-off rows |
| 38 | Demodulated | Mixes → Demodulated | PASS | PASS | post rows render |
| 39 | Demodulated post | Demodulated → post | PASS | PASS | direct preview MP3 row |
| 40 | Live Radio | Home → Live Radio | PASS | PASS | **10** rows: 3 stations + Pirate + 6 genres |
| 41 | Curated station | Live → Kool/Rinse/Centreforce | PASS | PASS | play/stop path tested |
| 42 | Live genre doors | Live → genre → stations | **FAIL** | **PASS** | 3de8125: 3 of 6 query slugs → 0 stations; 18c2572: 6/6 canonical tags |
| 43 | Favourites | Home → Favourites | PASS | PASS | library room, saved rows render |
| 44 | Downloads | Home → Downloads | PASS | PASS | library room, queue/index rows render |
| 45 | Search | Home → Search | PASS | PASS | in-window keyboard opens and renders |
| 46 | Spinning Surprise | Home → Spinning Surprise | PASS | PASS | surprise run starts |
| 47 | About & Sources | Home → About | PASS | PASS | 20 rows; links dead (§4.1) |
| 48 | Classic lists | About → Classic lists | PASS | PASS | executes `ActivateWindow(Programs,plugin://plugin.audio.raveplayer/?mode=classic_root,return)`; window behaviour unverified on device |

**Summary at 3de8125:** 46 PASS, 1 PARTIAL (#25), 1 FAIL (#42).
**Summary at 18c2572:** 47 PASS, 1 PARTIAL (#25), 0 FAIL.

### 2.1 The 3de8125 Live genre defect (P1)

`GENRE_ROWS` (`screens/live.py:192-211`) carries both a canonical
radio-browser `tag` and a UI `target` slug. `controller.py:2008` built the
room from `action.get("target") or action.get("tag")`, and
`data.py:1609` passed that string straight to `radio.stations()`:

```
tag='drum and bass' target='drum-and-bass' → radio.stations('drum-and-bass')
tag='uk garage'     target='uk-garage'     → radio.stations('uk-garage')
tag='dubstep'       target='dubstep-grime' → radio.stations('dubstep-grime')
```

Controller harness, exact 3de8125 (fake `radio.stations` that only answers
canonical tags, mirroring radio-browser):

```
Hardcore         tag='hardcore'      target='hardcore'      plate=''
Jungle           tag='jungle'        target='jungle'        plate=''
Drum & Bass      tag='drum and bass' target='drum-and-bass' plate='empty'  STANDBY · Nothing in Drum & Bass right now…
House            tag='house'         target='house'         plate=''
UK Garage        tag='uk garage'     target='uk-garage'     plate='empty'  STANDBY · Nothing in UK Garage right now…
Dubstep & Grime  tag='dubstep'       target='dubstep-grime' plate='empty'  STANDBY · Nothing in Dubstep & Grime right now…
radio.stations calls: ['hardcore','jungle','drum-and-bass','house','uk-garage','dubstep-grime']
```

This is not a fake artefact: a read-only query to the same API the plugin
uses (`resources/lib/radio.py:20-27`, `de1.api.radio-browser.info`) returned
**0** stations for each slug and **20/17/20** for the three canonical tags
(limit 20, `hidebroken=true`). So three of the six new genre doors were
empty in production.

**Fixed at 18c2572** by reversing the order
(`controller.py:2008`: `action.get("tag") or action.get("target")`). The
same harness now calls `['hardcore','jungle','drum and bass','house','uk garage','dubstep']`
and all six render a station. No test covered this before; `test_screens_live`
only checks `action["tag"]`, and the controller test used `tag == target`
(`test_rave_screen.py:675-688`).

---

## 3. Branding

| Surface | 3de8125 | 18c2572 |
|---|---|---|
| In-window home title (`HOME_TITLE`) | **RAVE PLAYER** (PASS) | **RAVE PLAYER** (PASS) |
| Skin header label + surprise label | **RAVE PLAYER** (PASS) | **RAVE PLAYER** (PASS) |
| Notifications / status (`window.py:476,547,548,687,960,974`) | "Rave Screen" (**FAIL**) | "Rave Player" (**PASS**) |
| About version row (`library.py:906`) | "Rave Screen" (**FAIL**) | "Rave Player" (**PASS**, but duplicates the data row — §4.1) |
| Plugin `addon.xml:16-17` description | "the Rave Screen is the primary shell" (**FAIL**) | unchanged (**FAIL**) |
| Screen `addon.xml:18` disclaimer | "Rave Screen does not host…" (**FAIL**) | unchanged (**FAIL**) |
| `repo/addons.xml:14-15,42` | same two strings (**FAIL**) | unchanged (**FAIL**) |
| `resources/lib/routes.py:884,887` notifications | "Rave Screen is installed/not installed" (**FAIL**) | unchanged (**FAIL**) |
| Add-on name / version | Rave Player / Rave Player UI, 3.9.61 (PASS) | unchanged (PASS) |

The 3.9.60 audit's §13 recommendation was one product name everywhere. At
3de8125 the in-window brand was fixed but the metadata, the About label and
the notifications were not. 18c2572 fixes the notifications and the About
label only. Kodi's add-on information still calls the shell "Rave Screen",
and the two shipped metadata files still contain the old brand.

---

## 4. Quality

### 4.1 About links are still dead (P2)

`library.py:1539-1550` (`_about_row`) gives every version/licence/link/source
row `payload={"action": ACTION_OPEN, "url": …}`. `controller.py:1797-1800`
handles `ACTION_OPEN` by writing `Source: <url>` to the status line and
returning `False` — it never opens anything. Controller harness at 3de8125
and 18c2572:

```
Rave Player      action=open     status='Source: https://github.com/tcz009/plugin.audio.raveplayer'
Licence          action=open     status='Source: https://www.gnu.org/licenses/gpl-3.0.html'
Internet Archive action=open     status='Source: https://archive.org'
Classic lists    action=classic  builtins=['ActivateWindow(Programs,plugin://plugin.audio.raveplayer/?mode=classic_root,return)']
```

So 19 of the 20 About rows look actionable but do nothing; only the new
"Classic lists" action works. This is the old audit's P2-5, still open. The
fix should either call an opener (e.g. `RunPlugin`/`PlayMedia` of the URL, or
the Kodi web browser) or make these rows visually read-only (`kind="info"`).

At 18c2572 the About screen also has two rows labelled **"Rave Player"**
(plugin and screen version; both fact `3.9.61`, both the same project URL) and
two labelled **"Licence"** (version row and link row; both the GPL URL). The
test now enshrines `["Rave Player", "Rave Player", "Kodi", …]`
(`test/test_screens_library.py:763`). Duplicate destinations are exactly what
the task asked to avoid.

### 4.2 Content/feature gaps still open (from the 3.9.60 audit)

| Gap | Evidence | Status |
|---|---|---|
| Latest is packs only (classic merges on-air + podcast + DNB) | `data.py:642` `recent_packs(rows=100)`; home plot still promises "packs, shows and radio rips" (`data.py:373`) | open |
| Silent 200-row caps (classic 5000/setting) | `data.py:1016,1038,1071,1182` | open |
| Search loses the title-scoped widen (<10 results) | `library.py:search` has no widen pass; classic `routes.py:2722-2729` | open |
| About credits 12 vs classic 14 | `library.py:320-333` vs `routes.py:2751-2784`; missing "Podcast & mix RSS feeds" and "Live radio: Kool FM & Rinse FM" | open |
| Pirate station grouping + DJs/credit/note | `data.py:_mixes_children` uses `pirate.entries()` flat; `pirate.stations()` unused by the screen | open |
| Rows-per-page is session-only | `controller.py:_cycle_rows_per_page` writes no setting | open |
| "Play all from here" | absent from `_build_context` | open |
| Moxser favourite + download | `favourite_payload` returns `None` for `moxser_mix`; download only for `track`/`external` | open |
| GetDarker / Mixcloud-only empty state | generic "source may be blocked" plate; classic names the missing Mixcloud add-on | open |
| Hard-coded "310 shows" | `data.py:385,501` | open |
| Hard-coded Live subtitle "Kool FM · Rinse FM · Centreforce · pirate" | `controller.py` live room; six genre rows now exist | open |
| Classic `years` vs shared helper | `routes.years` uses `range(year, 1987, -1)` (2026→1988); `classic_years()` returns 2026→1987, so the screen shows 1987 and classic does not | open/inconsistent |
| Context menu for new folder kinds | `_build_context` has no "Open" for `filter_index`, `rave_index`, `year_index`, `archive_search`, `live_tag`, `filter`, `rave`, `year`, `blog_source`, `blog_post`; long-press says "No actions on that row" | open |
| Dead `live_tags` room | `data.py:453,621`; no home row targets it (tests only) | cosmetic |
| `_year_children` broad `except (TypeError, ValueError, Exception)` | `data.py:1605` | cosmetic |
| README says "Since 3.9.51 … full-screen Rave Screen" | `README.md:103`; direct launch is 3.9.60 and the name is Rave Player | doc |

### 4.3 Ungated Mixcloud rave rows (P2)

`data.py:_rave_children` appends an "Open … sets in the Kodi Mixcloud add-on"
row whenever the catalogue has a `mixcloud_count`, without checking
`handoff.available("mixcloud")`. Classic `rave_list` gates on
`handoff.available("mixcloud")` (`routes.py:1368-1375`). The real
`handoff.mixcloud_search()` only builds a `plugin://plugin.audio.mixcloud/`
URL, so the row is offered even when that add-on is absent. Controller
harness with `available()` forced to `False`:

```
The Sanctuary  children=2 kinds=['pack','external']  avail_checked=[]
Biology        children=1 kinds=['external']         avail_checked=[]
Conflict FM    children=1 kinds=['external']         avail_checked=[]
handoff.available calls: []
```

`resources/rave-catalog.json` has 55 entries: 33 archive-backed and **22
Mixcloud-only**. Without the Mixcloud add-on, those 22 rooms contain only a
dead hand-off row (and the archive-backed rooms show an extra dead row).
This is both a dead-row and a parity defect.

### 4.4 Pirate station page

Matrix row #25 is not a real screen destination. `data._mixes_children` maps
`pirate_source` to a flat recordings list; classic `pirate_menu` groups by
station and `pirate_station` shows DJs/year/credit/note. The curated data has
5 recordings across 3 stations. The app's plot is generic ("1990s
pirate-radio recording"), so the old audit's DIFFERENT verdict still applies.
Everything in the task's hub list is reachable; only the station page is not.

### 4.5 Art, labels and empty rows

* Every art file referenced by the new rooms exists (`tapepacks.png`,
  `series.png`, `rave-nights.png`, `years.png`, `tapepacks-all.png`,
  `kool.png`, `hardscore.png`, `pirate-archive.png`, `mixcloud.png`,
  `radio-*.png`, all `fanart-*`).
* A recursive sweep of the 90 reachable `(kind,target)` nodes found no blank
  label/art/fact and no duplicate key within a room. The `EMPTY` nodes are
  expected: live/library-owned rooms and leaf action rows
  (`dnb_show`/`moxser_mix`), which are resolved, not expanded.
* The only same-screen duplicate labels are About's "Licence" (3de8125) and
  "Licence"/"Rave Player" (18c2572).
* No TODO/FIXME/placeholder text in the runtime code.

---

## 5. Release hygiene

### 5.1 Versions and metadata

All consistent: `plugin.audio.raveplayer` **3.9.61**, `script.raveplayer.ui`
**3.9.61** (requires plugin 3.9.61), `script.module.raveresolver` **1.1.0**,
`repository.raveplayer` **1.0.0**. The metadata blocks in `repo/addons.xml`
match both `addon.xml` files field-for-field, and
`repo/addons.xml.md5` holds the correct MD5. The repo zips contain the
committed source (`default.py`, screen `controller.py`/`window.py`/`library.py`
verified byte-for-byte), with no `__pycache__`, tests or `.DS_Store`.

### 5.2 Tests

Exact `3de8125` snapshot: `python3 -m unittest discover -s test -p 'test_*.py'`
→ **1206 tests, OK** (25.6 s), matching the expected 1206; the first
clean-worktree run also returned 1206 OK. `18c2572`: **1206, OK**
(23.2 s). `test_parity_3_9_61` + `test_app_integration` → 47 OK;
`test_legacyblog` → 5 OK; `test_compat` → 10 OK.

### 5.3 Stale release document (P2 for publishing)

`docs/RELEASE-3.9.61.md` was written at `ec37357`. At `3de8125` it still said
**1203 tests** and listed the `ec37357` zip hashes:

| Zip | Doc value | Actual 3de8125 |
|---|---|---|
| plugin | `7fd1ed54…` | **`08655ff3…`** |
| screen | `5c2da730…` | **`41aaaecd…`** |
| resolver | `b1c52646…` | **`c0040b02…`** |

The `repo/addons.xml` and `.md5` values in the document were correct. At
`18c2572` the test count and plugin hash were corrected, but the screen and
resolver hashes are still `ec37357` values:

| Zip | Doc at 18c2572 | Actual 18c2572 |
|---|---|---|
| plugin | `5ee033d7…` | `5ee033d7…` ✔ |
| screen | `5c2da730…` | **`240e150f…`** |
| resolver | `b1c52646…` | **`9ab1e28c…`** |

So the document cannot be used to verify a downloaded build, and it would
fail the release checklist at either commit. `scripts/check-repo-artifacts.sh`
passes because it deliberately does not hash the zips.

### 5.4 Junk / secrets

* No secrets or credentials found in runtime/test/docs files; the only
  "token"/"secret" hits are test fixtures and documentation.
* No tracked junk files or unexpected binaries (712 tracked files; largest
  tracked files are the expected repo zips and design PNGs).
* **During the audit** two untracked duplicate copies appeared in the
  worktree: `repo/repository.raveplayer/repository.raveplayer-1.0.0 2.zip`
  and `repo/script.module.raveresolver/script.module.raveresolver-1.1.0 2.zip`
  (content-identical to the real zips, macOS-style " 2" names, `-rw-------`
  permissions, 16:06 mtime, dir mtime 16:30). They were not in commit
  `3de8125` and are absent from the 18c2572 tree (HEAD is clean). They should
  not exist in a published repo checkout; delete them if they reappear.

### 5.5 Repo artifacts

`scripts/check-repo-artifacts.sh` at 18c2572: "repo/ artifacts are current
and committed for plugin 3.9.61, screen 3.9.61, resolver 1.1.0". `dist/` is
gitignored and its three zips are byte-identical to the repo zips. No tag
points at `3de8125`; the audit performed no push.

---

## 6. Remaining gaps, ranked

### P1 — parity blocker (fixed in 18c2572, not in 3de8125)

1. **Three Live genre doors were dead** — Drum & Bass, UK Garage and Dubstep
   & Grime queried radio-browser with slug tags (`drum-and-bass`,
   `uk-garage`, `dubstep-grime`) and returned 0 stations; Hardcore, Jungle
   and House worked. One-line fix: prefer `action["tag"]` over
   `action["target"]` (18c2572), ideally with a test that asserts the
   canonical tag reaches `radio.stations`.

### P2 — should ship with the install

2. **About links are dead** (both commits): 19 rows use `ACTION_OPEN` and
   only echo the URL; the task's "About links work" is not met. Either open
   the URL or make the rows read-only/`info`.
3. **Branding metadata is inconsistent** (both): plugin/screen `addon.xml`
   descriptions/disclaimer, `repo/addons.xml` and two `routes.py` notifications
   still say "Rave Screen". 18c2572 fixed the in-window notifications and the
   About label, not the metadata.
4. **Rave Mixcloud rows are ungated** (both): 22 of 55 raves are
   Mixcloud-only; without the Mixcloud add-on those rooms show a dead row.
   Gate on `handoff.available("mixcloud")` as classic `rave_list` does.
5. **Classic Back semantics** (3de8125): `classic_root` Back → `?mode=root`
   relaunches the app. 18c2572 fixes this by making `?mode=root` a directory;
   confirm the intended launcher contract if `?mode=root` must launch.
6. **Release document hashes** (both): screen/resolver hashes are stale at
   18c2572; all three were stale at 3de8125. Regenerate the block after the
   final build.

### P3 — polish / long-tail parity

7. About duplicate rows: two "Rave Player" and two "Licence" rows at
   18c2572; same project/GPL URLs, same facts.
8. Pirate station grouping and DJs/credit/note still missing (flat list).
9. Latest remains packs-only while its home plot promises shows and radio;
   no on-air/podcast/DNB merge.
10. Silent 200-row caps for Moxser/Hardscore/GetDarker/feeds (classic 5000 or
    the setting).
11. Search loses the classic title-scoped widen.
12. About is missing the Podcast RSS and Kool/Rinse live credits (12 vs 14).
13. Rows-per-page is session-only; no "Play all from here"; no Moxser
    favourite/download.
14. GetDarker/Mixcloud-only empty states say "source may be blocked" instead
    of naming the missing Mixcloud add-on.
15. Hard-coded "310 shows" (twice); hard-coded Live subtitle; `classic_years`
    (1987) vs classic `years` (1988) mismatch.
16. Long-press context menu has no "Open" for the new folder kinds.
17. Dead `live_tags` room; redundant `except (TypeError, ValueError,
    Exception)`; `DirectLaunchTests` placed after `if __name__ ==
    "__main__"` in `test_compat.py` (discovery is fine, direct execution
    skips it).
18. `README.md` still says "Since 3.9.51 … the full-screen Rave Screen".

---

## 7. What is genuinely better (do not regress)

Uniform 25/50/100 paging, in-window keyboard search, top-level Downloads,
explicit live play/stop with ON AIR state, now-playing footer, stale-while-
revalidate cache and prefetch, single-instance window, retry plates, separate
version rows, and 1206 offline tests. The 3.9.61 additions (Tape Packs hub,
Pirate hub, Classic Pack Series/raves/years/Every Pack, live genre doors,
Mikus/Demodulated, About→Classic lists) are a real superset of the classic
top-level tree, and the controller harness walks all of them.

---

## 8. Worktree movement during the audit (must know)

### 8.1 Timeline

* Audit start: `git rev-parse HEAD` = **3de8125**, `git status` clean.
* During the audit: five files were modified in the worktree
  (`default.py`, screen `controller.py`, `screens/library.py`, `window.py`,
  `test_compat.py`), the repo zips were rebuilt, and two untracked " 2" zips
  appeared.
* During the audit the branch advanced to **18c2572**
  (`3.9.61: fix live genre tags, launcher root semantics, branding`),
  worktree clean. `dist/` was rebuilt at 16:36 and matches the repo zips.
* Because of this, all 3de8125 results in this report were re-run against a
  `git archive 3de8125` snapshot. The 18c2572 column is a separate delta
  audit of that commit (also from a `git archive` snapshot).
* **After 18c2572 (16:41)** a further uncommitted launcher change appeared:
  `default.py` now calls `routes.rave_screen(handle, {})` instead of
  `xbmc.executebuiltin("RunScript(...)")`, and the four repo zips were
  rebuilt but not committed. At report time the tree is dirty (`default.py`
  + four repo zips + this report). This change is **not** in `3de8125` or
  `18c2572` and was not audited; re-run `test_compat` and the launcher probe
  after it settles. Note that `rave_screen(handle, {})` calls
  `kodi.end_directory(handle, "files")` when `handle >= 0`, which the old
  `executebuiltin` path did not do — check that bare launches and the
  fallback root still behave. Quick probe of the 16:41 tree still shows
  bare→RunScript and root/play/classic_root→dispatch, and `test_compat`
  is 10 OK; the `end_directory` side effect is the open question.

### 8.2 18c2572 delta (verified, not assumed)

* Live genre tags: `controller.py:2008` now prefers `tag`; harness calls
  `['hardcore','jungle','drum and bass','house','uk garage','dubstep']`; all
  six doors return stations. **P1 fixed.**
* Launcher: `default.py:30` is now `mode not in (None, "")`; `?mode=root`
  dispatches to the 2-row root. Bare launch still opens the app. This fixes
  the `classic_root` Back toggle but is a deviation from the task's literal
  "launches for root" acceptance.
* Branding: window notifications/status and the About version label now say
  "Rave Player". Add-on metadata, `repo/addons.xml` and `routes.py`
  notifications still say "Rave Screen".
* About: still dead links; now two "Rave Player" and two "Licence" rows.
* Mixcloud gating, caps, Latest, widen, credits, pirate grouping: unchanged.
* Tests: 1206 OK; zips rebuilt and committed; `check-repo-artifacts.sh`
  passes; screen/resolver hashes in `docs/RELEASE-3.9.61.md` remain stale.
* No new junk at 18c2572; the 18c2572 snapshot is clean. The 16:41
  launcher change was later committed as `5acbe7c` (§8.3).

### 8.3 Post-report commit 5acbe7c (current HEAD)

The 16:41 launcher change was committed as **`5acbe7c`**
(`3.9.61: launch through routes.rave_screen (clean directory close)`),
together with this report. Verified from a `git archive 5acbe7c` snapshot:

* **1206 tests OK**; `test_compat` 10 OK.
* Launcher probe: bare → `RunScript` (via `routes.rave_screen`);
  `?mode=root`, `?mode=play`, `?mode=classic_root`, `?mode=archive_item`,
  `?mode=download_start` and `?mode=fav_remove` → dispatch. `rave_screen`
  calls `kodi.end_directory(handle, "files")` for `handle >= 0` (the intended
  "clean directory close"); that side effect is not device-tested.
* All four repo zips were rebuilt. `docs/RELEASE-3.9.61.md` is now stale for
  **all three** add-on zips: plugin doc `5ee033d7…` vs actual `328cac1e…`,
  screen `5c2da730…` vs `7ede628d…`, resolver `b1c52646…` vs `1494228d…`.
  `repo/addons.xml`/`.md5` values remain correct.
* No parity, branding or quality finding changes: the 3de8125 verdict and the
  18c2572 delta stand. 5acbe7c is the recommended committed build if the
  launcher side effect is accepted.

---

## 9. Install recommendation (the one install)

**Safe to install: yes — install a committed build (current HEAD is
`5acbe7c`, §8.3), not 3de8125.** There is no crash,
data-loss, playback or launcher regression in either commit; downloads and
favourites are untouched; the launcher and the app's plugin playback path
were both exercised without a device. The differences are user-visible
incompleteness, not instability:

* 3de8125 would give three empty Live genre doors (Drum & Bass, UK Garage,
  Dubstep & Grime) and still calls the shell "Rave Screen" in metadata.
* 18c2572 fixes those genre doors and the in-window branding; About links
  still do nothing, rave Mixcloud rows are still offered without the Mixcloud
  add-on, and the release document's screen/resolver hashes are wrong.

**Do not publish/deploy a release artifact until:** the About links are made
truthful, the add-on metadata is rebranded, the Rave Mixcloud rows are gated,
and `docs/RELEASE-3.9.61.md` hashes/test count match the final build. None of
those require a device; all are offline-testable.

---

## Appendix A — Evidence commands (exact 3de8125 snapshot unless stated)

```sh
# exact-commit snapshot
git archive 3de8125 | tar -x -C /tmp/parity-audit-361/snapshot

# tests
cd /tmp/parity-audit-361/snapshot && python3 -m unittest discover -s test -p 'test_*.py'
#   -> Ran 1206 tests ... OK

# launcher probe (fake xbmc; records RunScript vs dispatch)
python3 /tmp/parity-audit-361/launch_check_snap.py
#   bare/root -> RunScript; play/classic_root/archive_item/download_start/fav_remove -> dispatch

# live genre probe (fake radio.stations, tag-aware)
python3 /tmp/parity-audit-361/genre_check_snap.py
#   radio.stations calls: ['hardcore','jungle','drum-and-bass','house','uk-garage','dubstep-grime']
#   Drum & Bass / UK Garage / Dubstep & Grime -> plate='empty' STANDBY

# radio-browser tag check (read-only external)
#   tag='drum and bass' 20, 'drum-and-bass' 0
#   tag='uk garage'     17, 'uk-garage'     0
#   tag='dubstep'       20, 'dubstep-grime' 0

# About probe
python3 /tmp/parity-audit-361/about_check_snap.py
#   Rave Screen row; ACTION_OPEN rows only change status; Classic lists executes ActivateWindow

# app routing walk (all hubs, Mixes, Live, About)
python3 /tmp/parity-audit-361/walk_snap.py

# real taxonomy through the screen data
python3 /tmp/parity-audit-361/real_data_check_snap.py
#   16 filters / 55 raves / 40 years / 8 archive sections / 6 radio sections

# classic routes
python3 /tmp/parity-audit-361/classic_routes_snap.py
#   classic_root 9+Back, packs_menu 7+Back, pirate_radio 3+Back,
#   radio_menu 3+6+Back, shows_menu 6+Back, filters_menu 16+Back, years 39+Back

# artifacts
shasum -a 256 repo/*/*.zip repo/addons.xml repo/addons.xml.md5
sh scripts/check-repo-artifacts.sh   # at 18c2572 (git repo)
```

## Appendix B — Key file/line index

| Item | Location |
|---|---|
| Launcher | `default.py:16-37` (3de8125 `:30` root launches; 18c2572 `:30` root dispatches) |
| Live genre rows | `script.raveplayer.ui/raveui/screens/live.py:192-211` |
| Genre action → tag | `script.raveplayer.ui/raveui/controller.py:2008` |
| Genre → radio.stations | `script.raveplayer.ui/raveui/data.py:1608-1615` |
| Rave Mixcloud row | `script.raveplayer.ui/raveui/data.py:1567-1588` |
| About rows / links | `script.raveplayer.ui/raveui/screens/library.py:900-931,1539-1550` |
| About action | `script.raveplayer.ui/raveui/controller.py:1797-1814` |
| Notifications | `script.raveplayer.ui/raveui/window.py:476,547,548,687,960,974` |
| Plugin metadata | `addon.xml:16-17`; `script.raveplayer.ui/addon.xml:18`; `repo/addons.xml:14-15,42` |
| Plugin notifications | `resources/lib/routes.py:884,887` |
| Classic Back rows | `resources/lib/routes.py:857,928,957,987,1325,1374,1580,1629,2170,2243,2304,2444,2464,2492,2793` |
| Classic years | `resources/lib/routes.py:1573-1581`; helper `:373-377` |
| Content caps | `script.raveplayer.ui/raveui/data.py:1016,1038,1071,1182` |
| Latest | `script.raveplayer.ui/raveui/data.py:642` |
| About sources | `script.raveplayer.ui/raveui/screens/library.py:320-333` (12) vs `resources/lib/routes.py:2751-2784` (14) |
| Release doc | `docs/RELEASE-3.9.61.md:63,75-86` |
| Parity matrix | `docs/PARITY-3.9.61.md`; `test/test_parity_3_9_61.py` |
| Launcher tests | `test/test_compat.py:128-165` |
