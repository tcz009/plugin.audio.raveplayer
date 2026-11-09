# Independent audit — Rave Player 3.9.67

**Target:** commit `84c3e32b4a650cfa34aea5dc1139925b89f1977c` (tag `v3.9.67`), worktree
`raveplayer-worktrees/kodi-parity`, branch `feat/3.9.61-parity`.

**Audit type:** independent, read-only. No device/ADB, no source/code edits, no push, no new tag.
The only files written are this report. A stable snapshot of `84c3e32` was extracted with
`git archive` to `/tmp/kodi-3.9.67` because the live worktree moved on to 3.9.68/3.9.69
while the audit was running; all code references below are against `84c3e32`.

**Verdict: NEEDS-FIX.** Menus, menu parity, pagination mechanics, the 10-room home, waveform,
stop-at-home, icons, resolver wiring and cancel safety pass. Three user-facing blockers remain:
**EZ Garage / UK Raves playback is 401**, **web-row art is 401 (the reported magenta
placeholder)**, and **Favourites/Play-all for those same-origin rows is rejected as stale**.
A fourth high-priority issue (DejaVu first-page timeout) makes the DejaVu archive flaky on a
cold web cache.

---

## 1. Evidence base

### 1.1 Code and tests

| Check | Result |
|---|---|
| Snapshot | `git archive 84c3e32` → `/tmp/kodi-3.9.67` (clean 3.9.67 tree) |
| Full suite | `python3 -m unittest discover -s test` → **1231 tests, OK** (29.3 s) |
| Web unit suites | `python3 -m unittest test.test_webapi test.test_web_routes` → **22 tests, OK** |
| Compile/import | all modules import under the test stubs; no 3.9.67-specific traceback in the suite |
| Device | **not used** — no ADB, no Kodi launch, no screenshots, no userdata/settings touched |

### 1.2 Live web service (read-only probes)

The live service at `http://192.168.1.179:8097` reports
`{"ok":true,"version":"1.6.75","revision":"e2476e4"}`. Probes used the configured resolver
token from `.git-auth/resolver_token` (never printed, never copied into this report) and plain
`curl` GET/HEAD. No state was changed.

| Probe | With `Authorization: Bearer …` | Anonymous |
|---|---|---|
| `/healthz` | 200 | 200 |
| `/api/20bensons` | 200 | 401 |
| `/api/ukraves` | 200 | 401 |
| `/api/ezgarage` | 200 | 401 |
| `/api/podcast/dejavu-fm` | 200 | 401 |
| `/api/live` | 200 | 401 |
| `/api/ezgarage/72aswcrx4hlw2sh/stream` | **401** | 401 |
| `/api/ukraves/6948/stream` | **401** | 401 |
| `/static/art/20bensons.png` | **401** | 401 |
| `/static/art/djez.png` | **401** | 401 |
| `/static/art/icon.png` | 200 | 200 |

The 401s are by web design, not transient:

* `Rave Player/app.py:907-916` (`PUBLIC_PATHS`, `_public_static`) whitelists only
  `/static/art/icon*.png` (plus login assets). Every other `/static/art/*` needs a browser
  session.
* `Rave Player/app.py:942-975` deliberately scopes the resolver service token to the **list**
  GETs (`/api/20bensons`, `/api/ukraves`, `/api/ezgarage`, `/api/live`, `/api/latest`) and the
  `/api/live/` + `/api/podcast/` subtrees. The comment explicitly keeps the
  `/api/ezgarage` and `/api/ukraves` **stream/file children session-only**.
* `Rave Player/app.py:1012-1040` (`_auth_guard`) therefore returns 401 for those media and
  art paths before routing.

Kodi's player and image loader do not share the add-on's `urllib` request headers or the
web session cookie. A URL handed to `setResolvedUrl`/`setArt` is fetched by Kodi with no
Bearer token, so those 401s are exactly what a Kodi device receives.

### 1.3 Live API shape / counts

| Endpoint | Page 1 | Pager | Notes |
|---|---|---|---|
| `/api/20bensons` | 40 rows | page 1, pages 6, total 234, per-page 40, next yes | page 6 = 34 rows; true 234 / 6 pages |
| `/api/ukraves` | 34 rows | page 1, pages `null`, total `null`, per-page 40, next yes | cursor-paged; page 2 = 40 rows, next page 3; page 9 = 40 rows, next page 10. **34 is page 1, not a total.** |
| `/api/ezgarage` | 23 rows | no `pager` key | single page of 23 |
| `/api/podcast/dejavu-fm` | 40 rows | page 1, pages **110**, total **4382**, per-page 40, next yes | page 110 = 22 rows; **110 is pages, not episodes** |
| `/api/live` | 5 rows | no pager | includes DejaVu FM (`https://dejavufm.radioca.st/stream`) and OSA Radio (`https://osa.radioca.st/stream`) |

The `kodi`-side client (`resources/lib/webapi.py`) parses all of these correctly. A live
end-to-end call of `Client.page()` with the token produced the expected rows, absolute
resolved art, and pager metadata for all four lists; `webapi` itself is not the source of the
failures below.

Latency measured from this host (informational):

* warm: 20bensons 1.9 s, UK Raves 1.6 s, EZ 0.6 s, live 0.07–0.29 s, DejaVu 1.0–1.4 s;
* DejaVu page 1 after the web feed cache went cold: **11.36 s** (one probe exceeded 20 s),
  and page 110 was >20 s on the same cold cache. See D4.

---

## 2. PASS/FAIL matrix

Legend: **PASS** = meets the requirement in code/tests and, where relevant, against the live
service; **FAIL** = user-visible defect; **PARTIAL** = mechanics correct but a dependent
policy breaks the user path; **N/A** = not verifiable without a device.

### 1. Menus

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 1.1 | Tape Packs contains 20bensons, UK Raves, EZ Garage **plus the old 7** | **PASS** | Classic `packs_menu` `resources/lib/routes.py:1078-1086`; screen `_packs_entries` `data.py:504-519`; both have the same 10 rows in the same order. Old 7 (Toronto, JungleTapes, RaveTapePacks, Classic Pack Series, By Rave, By Year, Every Pack) intact. `test_sources`/`test_taxonomy_2026` assert the exact 10 labels. |
| 1.2 | Mixes includes the DejaVu archive | **PASS** | Classic `shows_menu` `routes.py:1117-1119`; screen `_mixes_entries` `data.py:944-951`; both label `DejaVu FM Archive`. |
| 1.3 | Live includes DejaVu FM + OSA + genre doors | **PASS** | Classic `radio_menu` `routes.py:1154-1157` (then `RADIO_SECTIONS` genre doors); screen `LiveRadio.rows()` appends `GENRE_ROWS` after the 5 stations + Pirate row (`screens/live.py:422-446`). Screen parity test asserts the 5-station prefix and the 6 genre rows. |
| 1.4 | Downloads / Favourites / Search / Surprise / About intact | **PASS (presence)** | `classic_root` rows `routes.py:1000-1026`; screen home rows; no removals in the merge. **Exception:** About content is incomplete (D10) and Favourites playback for EZ/UK rows fails (D3). |
| 1.5 | 10-room home unchanged | **PASS** | `data.home_rows()` returns exactly 10 rooms (`data.py:374-418`); controller subtitle changed 13→10 (`controller.py:95`). The old docs still say 13 (D6). |

### 2. `webapi` client

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 2.1 | Token/base settings | **PASS** | `_web_client()` reads `resolver_service_url` + `resolver_service_token` (`routes.py:457-474`); `Client` normalises the base, adds `Authorization: Bearer`, `Accept: application/json`, and a 10 s timeout (`webapi.py:481-519`). |
| 2.1b | Cookie-fallback installs | **FAIL (P2)** | `webapi.Client` only accepts a bearer token; `_web_client` never reads `resolver_service_cookie`. A user configured with the documented cookie fallback gets 401 on every web list (D5). |
| 2.2 | Public/private URL rules | **PASS in isolation / FAIL for the intended rows** | `normalise_base` rejects credentials/query/fragment/non-http (`webapi.py:72-99`); `resolve_url` resolves relative against base and rejects non-http(s) (`120-149`); `playable_url` allows absolute URLs only when public or same-origin private (`161-187`). The same-origin relative `/api/ezgarage|ukraves/.../stream` **passes this rule** but is 401 on the web, so the rule does not make it playable (D1). |
| 2.3 | Pagination | **PASS** | `parse_page` handles `items`/`rows`, bare lists, `pager`/`total`/`next`, clamps pages, and computes `pages` when only `total` exists (`webapi.py:317-379`). Live: 234/6, 34+cursor, 23, 4382/110 all parsed correctly. Page > range clamps; page nav works. |
| 2.4 | Art resolution | **PARTIAL** | URLs resolve correctly (`webapi.py:296-298`, `resolve_url`), but the resulting same-origin `/static/art/*` URL is **not loadable by Kodi** (401) and neither 3.9.67 path maps it to the bundled art (D2). |
| 2.5 | 401/errors as empty plates | **PASS (lists)** | `web_source_page` never raises; `web_list` shows “Nothing from … right now” + retry (`routes.py:1249-1268`); screen `_web_children` returns an empty `Page` and the controller paints the STANDBY/retry plate (`controller.py:1568-1580`). Playback and art are the two exceptions (D1/D2). |
| 2.6 | No SSRF / open proxy | **PASS** | The add-on process only fetches the operator-configured base + fixed API paths; `api_url` refuses an off-origin absolute URL (`webapi.py:495-510`); redirects are manual and same-origin only (`550-597`); the token is re-sent only to that origin. `web_play` gives the URL to Kodi; it does not proxy bytes. See observations O1–O3 for hardening notes. |
| 2.7 | No token leakage | **PASS** | The token is only an `Authorization` header inside `_headers` (`webapi.py:512-519`); the URL/token is never logged; errors contain only HTTP code/type (`550-597`); `web_source_page` logs source/page/exception class only; rows carry no token; `web_play`/favourites URLs carry no token. |
| 2.8 | Timeout fit for real sources | **FAIL (P2)** | `DEFAULT_TIMEOUT = 10.0` (`webapi.py:46`) is below the observed 11.36 s cold DejaVu page 1. The screen load runner allows 45 s (`controller.py:175-179`), so the client timeout is the binding limit and a cold first open fails/retries (D4). |

### 3. Playback

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 3.1 | Absolute web rows play directly (`web_play`) | **PASS** | 20bensons rows are absolute `https://20bensons.com/mp3/...`; DejaVu rows are absolute Podomatic enclosures; live rows are absolute radioca streams. `web_play` (`routes.py:3399-3439`) passes them to `setResolvedUrl` with no resolver/plugin wrap. Live probes: 20bensons `206 audio/mpeg`; radioca `200 audio/mpeg`. |
| 3.2 | Relative web paths same-origin allowed | **FAIL (P1)** | EZ and UK Raves return `/api/ezgarage/<id>/stream` / `/api/ukraves/<id>/stream`; `webapi` resolves them to the configured origin; `web_play` hands that URL to Kodi; the web returns **401 even with the token** (D1). All 23 EZ sets and the Mediafire UK Raves rows fail. |
| 3.3 | YouTube/external rows dropped | **PASS** | `EXTERNAL_HOSTS` + `is_external_play` (`webapi.py:58-62, 152-158`); `_row_from_json` returns `None` for external/`open`-only rows; `web_play` rejects them again. `test_webapi` covers YouTube + off-origin + non-http. |
| 3.4 | DejaVu episodes downloadable | **PASS (code)** | Classic: `config["download"]` for dejavu + `row["download"]` truthy → `_download_context(..., "Rave Resolver")` (`routes.py:1288-1289`); Podomatic is in `downloads.ALLOWED_SOURCES["Rave Resolver"]` (`downloads.py:46-48`); a live-shaped DejaVu row produced both “Add to favourites” and “Download” context items. Screen: `downloadable` via `downloads.eligible` (`data.py:1430-1431`), `download_source="Rave Resolver"` (`1416-1418`), test `test_dejavu_archive_is_a_paged_downloadable_web_room` passes. Device download not executed. |
| 3.5 | No double-resolve | **PASS** | `web_play` never calls `_resolve_stream`/the resolver; relative paths are resolved once by `webapi.resolve_url`, and the absolute result is idempotent. Screen web tracks set `Track.path=url` so `PlaybackService` does not wrap them in `mode=play`. |
| 3.6 | No `plugin://` for web URLs | **PASS** | Classic list items are `plugin://…?mode=web_play` *directory rows*; the resolved media URL passed to Kodi is the direct stream. Screen `Track.path` is the absolute stream. No `plugin://` is used as the media path. |
| 3.7 | Favourites / Play-all for web rows | **FAIL (P1)** | Classic `fav_list` sends every saved stream to `mode=play` (`routes.py:1564-1571`), whose `_playable_url` uses `http.safe_stream_url` and rejects the private web origin; screen `_favourite_row` uses `backend.playable_url` (same guard) and marks the row **stale** (`screens/library.py:1382-1410`). Saving an EZ/UK row therefore makes an unplayable “stale” row. Screen Play-all uses `Track.path` directly and also hits the same 401. (D3) |

### 4. Classic + screen parity / pagination counts

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 4.1 | 20bensons 234 / 6 pages | **PASS** | Live pager: page 1, pages 6, total 234, per-page 40; page 6 has 34 rows. Classic header “Page 1 of 6 · 234 sets”; screen “Page 1 of 6 · 234 items” + room count 234. |
| 4.2 | UK Raves 34 | **PASS (page 1), with label note** | Page 1 is 34 rows; it is **not** a total. `next` is present, page 2 has 40 rows, page 9 has 40 and next page 10. Classic nav renders Next; screen renders “Page 1 · more” + Next. Classic’s header says “Page 1 · 34 sets” using page-row count because `total=None` (D7). |
| 4.3 | EZ Garage 23 | **PASS (rows) / minor gap** | API has 23 items and no pager; the screen room count shows 23. Classic has no header/count for a single cursor-less page (D7, cosmetic). |
| 4.4 | DejaVu 110 | **PASS (pages) / timeout risk** | Live pager: pages 110, total 4382, per-page 40; page 110 has 22 rows. Classic “Page 1 of 110 · 4,382 episodes”; screen “Page 1 of 110 · 4,382 items” + room count 4,382. The cold first fetch exceeds the 10 s client timeout (D4). |
| 4.5 | Page clamp / previous / next / Back | **PASS** | `web_list` navigates from the page the server returned (`routes.py:1238-1243`); `_page_nav` adds Prev/Next only at the correct bounds; screen `_render_page` does the same. Tests cover page 2 and page bounds. |

### 5. Regressions from the merge

| # | Area | Result | Evidence |
|---|---|---|---|
| 5.1 | Wave animation | **PASS (code) / untested** | 3.9.67 merge carries `animate_wave` (`window.py:592-612`, loop `1012-1017`) and all four `np-wave-0..3.png` frames in the UI zip; control 607 is the waveform image (`skin xml:578-585`). Cycle 4×/s (250 ms throttle), only while `Player.Playing`, best-effort exceptions. No test exercises `animate_wave` or asserts the four frame files; `test_rave_screen` only checks the static `np-wave-340x28.png` texture (D9). |
| 5.2 | Stop-at-home | **PASS** | `on_back` at Home while playing calls `on_stop` and keeps the window open (`controller.py:488-496`); test `test_rave_screen.py` “Back to Home, then Back stops the audio” passes. |
| 5.3 | Icons | **PASS** | Every `MENU_ART` value and every screen `_art("…")` file used by the new rows exists in `resources/art/` (`20bensons.png`, `ukraves.png`, `ezgarage.png`, `dejavu.png`, `osa.png`, `djez.png`, `podcasts.png`); `test_taxonomy_2026` distinct/exists test passes. |
| 5.4 | Resolver wiring | **PASS** | No change to `routes.play`/resolver wiring in 3.9.67; `webapi` is an independent client; full resolver tests pass. |
| 5.5 | Cancel safety | **PASS** | `web_play` added to `PLAYBACK_MODES` (`routes.py:103`), so an unhandled error goes to `_fail_playback` (setResolvedUrl false, no stop of current audio); no spinner is started by web routes; full cancel/race tests pass. |
| 5.6 | Live-room first paint | **AT RISK / FAIL (P3)** | Screen `load_stations` calls `modules.routes.web_live_stations()` synchronously on the GUI path when there is no cached live paint (`screens/live.py:309-315`); a slow/down service can block up to the 10 s client timeout. Classic `web_live` fetches before playing (`routes.py:1194`). The fallback rows exist, but only after the timeout. (D8) |

### 6. Tests / artifacts / docs / release notes

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 6.1 | Full suite | **PASS** | 1231 tests OK at 3.9.67 (snapshot run; 29.3 s). |
| 6.2 | New web tests | **PASS** | `test_webapi` 13 tests + `test_web_routes` 9 tests; menu/parity/screen tests updated and green. |
| 6.3 | Coverage of the failing paths | **FAIL (P3)** | No test covers (a) art loadability/mapping, (b) same-origin stream auth, (c) favourites/Play-all for web rows, (d) cold DejaVu timeout, (e) cookie auth, (f) `animate_wave`. `test_webapi` asserts `art == BASE + "/static/art/..."` (correct client, unusable image); `test_web_routes` uses public `https://web.test/…`; `test_rave_screen` fake web rows have `art=""`. (D9) |
| 6.4 | Zips/manifests/checksums | **PASS** | `repo/addons.xml.md5` matches `repo/addons.xml`; plugin/screen zips contain `webapi.py`, the five web art files, `np-wave-0..3.png`, and `addon.xml` version 3.9.67; `dist` and `repo` zips are MD5-identical at 3.9.67. Plugin requires resolver 1.1.0; screen requires plugin 3.9.67 (`test_resolver_wiring`). |
| 6.5 | Release notes names/menus | **PASS** | `addon.xml` name “Rave Player”, screen “Rave Player App”, both 3.9.67; changelog/WEB-SOURCES list the three Tape Packs rows, DejaVu in Mixes & Shows, and DejaVu/OSA in Live. |
| 6.6 | Docs accuracy | **FAIL (P3)** | README still says “Current release … 3.9.61” (README.md:312-314, 352); PUBLISHING.md:63-66 says 3.9.61; FULLSCREEN-APP.md still says 13 rooms and 959 tests (271, 279, 314); no `docs/RELEASE-3.9.67.md`; WEB-SOURCES line 7 says “no … push or tag” but tag `v3.9.67` exists and the local `origin/main` ref contains the commit; WEB-SOURCES line 56 says “rows are playable”, which is false for EZ/UK; rollout section does not state the required web version (1.6.75) or the stream/art auth limits; About sources omit the four new sources. (D6/D10) |

**Overall: NEEDS-FIX.** Not because of menu/parity work (that is sound), but because the two
new web-proxied lists cannot play, the artwork the user specifically tested is not
loadable, and saved rows for those lists are classified stale.

---

## 3. Defects and exact fixes

Line numbers are `84c3e32`. Fixes are suggestions; none were applied.

### D1 — P1: EZ Garage (all 23) and UK Raves Mediafire rows play a 401 URL

**Symptom.** Selecting any of the 23 EZ Garage sets or a Mediafire UK Raves row resolves
`/api/ezgarage/<id>/stream` or `/api/ukraves/<id>/stream` on the configured web origin, then
Kodi receives 401 and playback fails.

**Where it breaks.**

* `resources/lib/routes.py:3399-3439` (`web_play`): resolves the same-origin URL and calls
  `xbmcplugin.setResolvedUrl(handle, True, item)` with that URL. It adds no auth header and
  cannot add the browser session.
* `resources/lib/webapi.py:161-187` (`playable_url`) correctly allows the same-origin private
  URL — but the server rejects it.
* Web `Rave Player/app.py:942-975` keeps `/api/ezgarage` and `/api/ukraves` **stream/file**
  children session-only. Live evidence: 401 with the resolver token for both real rows
  (`.../72aswcrx4hlw2sh/stream`, `.../6948/stream`).

This is not a URL-policy bug in `webapi`; it is an authentication mismatch between the
add-on's JSON client (which sends the Bearer) and Kodi's player (which cannot).

**Exact fix (recommended).** Make the stream URL self-authenticating, like the existing Mega
path: have the web row include a short-lived signed stream URL (HMAC + expiry, validated by a
new stream route or by extending `_stream_ok`), e.g. `/api/ezgarage/<id>/stream?sig=…&e=…`.
`web_play` then hands Kodi that URL with no headers and no long-lived token. This keeps the
curated-id-only server policy and does not put the service token in a playlist/log.

**Alternative (not recommended).** Add `/api/ezgarage/` and `/api/ukraves/` to
`RESOLVER_TOKEN_GET_PREFIXES` **and** append Kodi's `|Authorization=<urlencoded bearer>` to the media URL
in `web_play` (the resolver's `kodi_url()` form is `url|Key=Value&…`; `playable_url` currently rejects any `|`). This puts the long-lived bearer token into the Kodi playlist/now-playing URL
and logs; if used, at minimum restrict to the exact `…/stream` paths, not `/file`, and verify
Kodi's URL-option (`|`) handling for `Authorization` on the Shield. Do not make the `/file` download
children public.

**Also required:** after the stream itself works, fix D3 (favourites) so saved rows use the
same signed path.

### D2 — P1: web-row art is a 401 magenta placeholder (Classic and screen; also OSD)

**Symptom.** Every 20bensons/UK Raves/EZ/DejaVu **track** row (and its now-playing thumb)
shows the magenta missing-texture placeholder; the Tape Packs door icons themselves are
bundled and render correctly. This is the reported device symptom.

**Where it breaks.**

* `resources/lib/routes.py:497` (`web_source_page`): `rows = [row.as_kodi() for row in
  page_data.rows]` — no art normalisation. Rows carry
  `http://192.168.1.179:8097/static/art/<name>.png`.
* `resources/lib/routes.py:1286` (`web_list`): `published_thumb = _web_art(row.get("art"),
  icon)`.
* `resources/lib/routes.py:3293-3312` (`_web_art`): explicitly **keeps** a same-origin
  remote URL (`if base and same_origin(...): return text`). That is the 401 URL.
* `resources/lib/routes.py:3424` (`web_play`): the OSD thumb repeats the same remote URL.
* `script.raveplayer.ui/raveui/data.py:1432` (`_web_children`): `row_art = _text(
  row.get("art"), art)` — the screen keeps the remote URL too.
* The files themselves are not missing: `20bensons.png`, `ukraves.png`, `ezgarage.png`,
  `dejavu.png`, `osa.png`, `djez.png`, `podcasts.png` all ship in `resources/art/` and in the
  plugin zip. The failure is the auth-gated remote URL, not a missing file.

**Exact fix.** Normalise at the single choke point and accept local paths for playback art:

```python
# routes.py, near web_source_page
def _web_row_art(value, fallback=""):
    text = str(value or "").replace("\\", "/")
    marker = "/static/art/"
    if marker in text:
        name = text.split(marker, 1)[1].split("?", 1)[0].split("#", 1)[0]
        name = name.rsplit("/", 1)[-1]
        if name and not name.startswith("."):
            local = os.path.join(kodi.ADDON_PATH, "resources", "art", name)
            if os.path.isfile(local):
                return local
    return fallback          # never hand Kodi the 401 remote URL

# web_source_page, inside the row loop:
# fallback = art(MENU_ART[config["art"]])
# item["art"] = _web_row_art(item.get("art"), fallback)

# _web_art: before the http check
if os.path.isfile(text):
    return text
```

This fixes Classic list art, `web_play` OSD art (the thumb is now local), and the screen
`Entry.art`/`Track.art` in one place. Add tests: a fake client whose row art is
`BASE + "/static/art/djez.png"` must yield an existing local file in `web_source_page`,
`web_list`, and `_web_children`.

**Alternative (server-side).** Add the four/five art names to web `_public_static` so the
remote URL is anonymously loadable. This fixes the image but keeps a network round-trip and a
web deploy dependency; the bundled-art mapping is preferable and offline-safe.

### D3 — P1: Favourites (and Play-all) reject same-origin web rows as stale/unplayable

**Symptom.** A user saves an EZ Garage or UK Raves row (context menu works), then opens
Favourites: the row is marked stale in the screen, or in Classic it routes to `mode=play`
which refuses the private URL. Play-all on a web page has the same problem because the tracks
are `path=absolute`.

**Where it breaks.**

* `resources/lib/routes.py:1564-1571` (`fav_list`): every saved stream is rebuilt as
  `mode=play&url=...`. `_playable_url` (`routes.py:3100-3110`) delegates to
  `http.safe_stream_url`, which deliberately rejects the private/LAN web origin.
* `script.raveplayer.ui/raveui/screens/library.py:1382` (`_favourite_row`):
  `playable = self._playable(target)`; `_playable` is the same public-only guard. When it
  returns empty, the row becomes `ACTION_REMOVE`/“That link is no longer playable”.
* Screen `PlaybackService.play_collection` uses `Track.path` (the raw same-origin stream) and
  therefore also gets 401 (D1).

This is independent of D1: even if the stream endpoint were made token-scoped, Favourites
would still reject the private URL. This is the “favourites intact” regression for the new
rows.

**Exact fix.**

* Store the web source with a stream favourite (the Classic context already passes
  `source=config["label"]`; the screen payload already has `source`).
* In `fav_list`, if the favourite's source is one of `WEB_SOURCES` labels (or its target is
  same-origin with `resolver_service_url`), emit `mode=web_play` instead of `mode=play`.
* In `_favourite_row`, if `target` is same-origin with the configured web base, set the
  track/payload `url` (and `path` once signed URLs exist) directly instead of running the
  public-only `_playable`.
* Add a test: save an EZ row, load Favourites, assert the row is playable and resolves through
  `web_play`.

### D4 — P2: DejaVu first page exceeds the 10 s client timeout on a cold web cache

**Symptom.** First open of DejaVu FM Archive after the web feed cache expires shows the
“Nothing from DejaVu FM Archive” retry plate; a retry a few seconds later works. The
screen load runner has a 45 s budget, so the 10 s client timeout is the binding limit.

**Evidence.** Live `/api/podcast/dejavu-fm?page=1` cold: **11.36 s** (one probe >20 s); warm:
1.0–1.4 s; page 110 cold >20 s. `webapi.DEFAULT_TIMEOUT = 10.0` (`webapi.py:46`). The screen load runner’s budget is 45 s
(`controller.py:175-179`), so the client timeout is what fails first.

**Exact fix (choose one or both).**

1. Server/web: pre-warm/refresh the 4,382-episode DejaVu feed in the background so the first
   client page is warm (the web already caches parsed feeds for 15 min; make the refresh
   proactive rather than request-triggered).
2. Kodi: use a per-source timeout for `/api/podcast/` (e.g. 20–25 s); the screen load
   runner already allows 45 s, so no task-budget change is needed. Keep the 10 s default for
   the small lists. Add a slow-opener unit test proving the client surfaces a plate instead
   of a traceback when it still times out.

### D5 — P2: Cookie-auth installations cannot use web sources

**Symptom.** A user configured with `resolver_service_cookie` (documented fallback; settings
UI label “Web session cookie (fallback auth)”) gets empty plates for every web list, because
`webapi` only sends `Authorization: Bearer` and only receives `resolver_service_token`.

**Where.** `resources/lib/routes.py:464-469` reads only URL+token; `resources/lib/webapi.py:481-519` only has `token`/`Authorization`.

**Fix.** Either support the cookie:
`Client(base, token, cookie="")` → `_headers` falls back to `Cookie: <value>`; `_web_client`
reads `resolver_service_cookie`. Or explicitly remove/disable the cookie fallback for web
sources and document that web sources require `RAVEWEB_RESOLVER_TOKEN` (web ≥ 1.6.75). Do not
silently show an empty room for a user who has configured the documented alternate auth.

### D6 — P3: docs/versions/claims are stale or inaccurate

| File:line (84c3e32) | Problem | Fix |
|---|---|---|
| `README.md:312-314`, `352` | “Current release … 3.9.61”; “The 3.9.61 plugin declares…” | Update to 3.9.67 (or make it dynamic) |
| `PUBLISHING.md:63-66` | 3.9.61 release notes/branch names | Update to 3.9.67 release notes/matrix |
| `docs/FULLSCREEN-APP.md:271,279,314` | 959 tests; 13 rooms | 1231 tests; 10 rooms |
| `docs/WEB-SOURCES-3.9.67.md:7` | “No device, ADB, push or tag” | A `v3.9.67` tag exists and the commit is on `origin/main`; correct the claim or explain the local-only tag/push |
| `docs/WEB-SOURCES-3.9.67.md:56` | “rows are playable” | EZ/UK are not until D1 |
| `docs/WEB-SOURCES-3.9.67.md:88,111-116` | 10 s timeout and rollout dependency described as complete | State web ≥ 1.6.75 for list scope; state that stream/static art remain session-only; note D1/D2/D4 |
| `CONTENT-SOURCES.md:205` | “Mediafire sets play via web `/api/ukraves/<id>/stream`” | Until D1 is fixed this is false for Kodi |
| `changelog.txt:6-12`, `script.raveplayer.ui/changelog.txt:6-12` | “Rows keep the web's art”; “no … tag” | Map to local art (D2); remove/qualify tag claim |
| missing | no `docs/RELEASE-3.9.67.md` (3.9.64/65/66 each have one) | Add one with the names/menus/rollout facts |

### D7 — P3: cursor-source counts are mislabelled in Classic

**Where.** `resources/lib/routes.py:757-763` (`_page_label`) and `:1270-1276` (`shown_total =
len(rows) if total is None`).

**Symptom.** UK Raves page 1 header says “Page 1 · 34 sets” although there are more pages (page
2 has 40); EZ has no header/count in Classic because it is a single page with `pages=None`.
Screen is better (`ROWS 23` / “Page 1 · more”).

**Fix.** When `total is None`, render “Page N” without a total (or “Page N · more” when
`has_next`), and show a count header for a single-page source using `len(rows)` where known.
Add tests for the UK page 2 and EZ single page.

### D8 — P3: screen Live first open fetches the web API on the GUI path

**Where.** `script.raveplayer.ui/raveui/screens/live.py:309-315` (`load_stations` calls
`modules.routes.web_live_stations()`), and `routes.py:1194` (`web_live` fetches before
playing).

**Symptom.** If the web service is slow/unreachable, opening Live Radio can freeze the window
for up to 10 s before the canonical fallback rows paint; selecting a web live row can pause
the same way before playback. The fallback is correct, just late.

**Fix.** Paint the canonical five stations immediately; refresh `/api/live` in the existing
background refresh path (as the cached branch already does) and update only if the signature
changes. In `web_live`, prefer a cached `/api/live` row and fall back to the canonical URL
without a blocking fetch.

### D9 — P3: tests do not cover the failure modes that shipped

**Gaps.** No test for:
art mapping/loadability (Classic + screen), same-origin stream auth, Favourites/Play-all for
web rows, DejaVu cold timeout, cookie auth, `animate_wave` / the four frame files, and the
3.9.68 `_web_art` name collision. `test_webapi` asserts the remote art URL is correct (it is),
which masks the 401; `test_web_routes` uses a public `https://web.test`; `test_rave_screen`
uses `art=""`.

**Fix.** Add the assertions proposed in D2/D3/D4 and a screen test that a private-origin row
art is an existing local file and a saved web row stays playable.

### D10 — P3: About does not list the new sources

**Where.** `resources/lib/routes.py:3052-3093` (`about`) and
`script.raveplayer.ui/raveui/screens/library.py:320-334` (`ABOUT_SOURCES`).

**Symptom.** Both About screens claim to list the sources but omit 20bensons.com, UK Raves
Downloads, EZ Garage Sets and DejaVu FM (the four new 3.9.67 sources). The classic About row
count/facts are still the pre-3.9.67 15 rows.

**Fix.** Add the four sources (and a live “DejaVu FM / OSA Radio” line if desired) to both
lists and update the `facts` tuple in `about()`. Add a small test that the About source set is
distinct and includes every `WEB_SOURCES` label.

### D11 — P3: duplicate RP codes between live stations and web doors (screen only)

**Where.** `screens/live.py:181-186` gives DejaVu FM `RP-45` and OSA `RP-46`; the screen doors
use `RP-43`/`RP-44`/`RP-45` for 20bensons/UK/EZ and `RP-46` for DejaVu Archive
(`data.py:504-519`, `944-951`). Codes are print furniture, not routing keys, but duplicates
confuse the code column. Give the live rows unique codes (e.g. RP-47/RP-48) or use the source
codes consistently.

### Observations (non-blocking hardening)

* **O1 — `Client.get_url()` accepts any URL and sends the bearer.** It is not called with
  user input today, but it is public; a future caller could send the token to a foreign host.
  Make it private or reject off-origin URLs like `api_url` does (`webapi.py:599-609`).
* **O2 — `same_origin` treats an explicit default port as different** (`http://host:80` vs
  `http://host` have `port` 80 vs `None`); a same-origin redirect written that way is refused.
  Normalise default ports (`webapi.py:109-117`).
* **O3 — `is_external_play` misses some platform aliases** (`youtube-nocookie.com`,
  `on.soundcloud.com`, etc.). The web already omits them; extend the local list if it is meant
  as the last line of defence (`webapi.py:58-62`).
* **O4 — the “no Kodi import” claim is only top-level.** `playable_url` lazily imports
  `resources.lib.http` for absolute URLs, which imports `xbmc` (`webapi.py:183-187`); tests
  pass only because `test/stubs/xbmc.py` exists. The add-on runtime is fine; the isolated
  client claim is slightly overstated.

---

## 4. In-flight 3.9.68/3.9.69 (not part of the 3.9.67 verdict)

The audit workspace moved to 3.9.69 (`e60da68`, then further uncommitted edits) while the
audit ran. These notes are for the next build; they do not change the 3.9.67 verdict.

* **3.9.68** added a `_web_art` at `routes.py:476` intended to map `/static/art/<name>` to
  local art, but the existing `def _web_art(value, fallback=None)` at `routes.py:3316` is
  defined later and shadows it. `web_source_page` therefore still returns the remote 401 URL.
  Rename the new helper (e.g. `_web_row_art`) and call it from `web_source_page`.
* **3.9.69** added a screen-side `RaveData._web_art` (`data.py:288`, used at `1451`), which
  fixes the screen list art but not Classic `web_list` or `web_play` OSD art.
* The uncommitted play-signing patch calls `/api/webplay`, which does **not** exist on live web
  1.6.75 (probe returns 401 even with the token; no route in `Rave Player/app.py`), so
  `signed_play` returns empty and `web_play` falls back to the raw 401 URL. It needs a web-side
  route first.
* The uncommitted screen wrapper checks `str(url).startswith("/")`, but `web_source_page`
  returns absolute URLs, so the wrapper never fires; `data.py` also has no `urllib` import.
  Use a same-origin check against `resolver_service_url` and import `urllib.parse`.
* Favourites/Play-all (D3) and the DejaVu timeout (D4) are not addressed by 3.9.68/69 as of
  this writing.

---

## 5. What the evidence supports (short form)

**PASS:** menu structure and order (Classic + screen), 10-room home, DejaVu archive door,
DejaVu/OSA live rows, 20bensons/DejaVu/live absolute URLs, pagination parsing and page
navigation, page counts 234/6 and 4382/110, 34-row UK page 1 + Next, 23 EZ rows, relative
`play` resolution, external-row rejection, empty/retry plates for list failures, token only
to the service origin, same-origin redirect cap, byte/time caps, DejaVu download context,
screen Download eligibility, no double-resolve, no `plugin://` media path, waveform code,
stop-at-home, all icons, resolver wiring, cancel-safe failed playback, full test suite,
zips/manifests/md5, release names/menus.

**FAIL (must fix before READY):**

1. D1 — EZ Garage and UK Raves playback 401 (session-only web stream; Kodi can't auth).
2. D2 — web-row art 401/magenta (same-origin `/static/art` is session-only; no local mapping).
3. D3 — Favourites/Play-all for EZ/UK rejected as stale/unplayable by the public-only guard.
4. D4 — DejaVu first page can exceed the 10 s timeout on a cold web cache.

**SHOULD FIX:** D5 cookie auth, D6 docs, D7 counts, D8 live GUI fetch, D9 tests, D10 About.

**NOT VERIFIED (no device/ADB by instruction):** actual Shield playback/download, texture
appearance, and live-screen timing on the device. The 401/art conclusions are from code plus
read-only live HTTP probes, which are deterministic.

---

## 6. Reproduction

```sh
# Stable 3.9.67 tree
git archive 84c3e32 | tar -x -C /tmp/kodi-3.9.67
cd /tmp/kodi-3.9.67
python3 -m unittest test.test_webapi test.test_web_routes
python3 -m unittest discover -s test

# Read-only live service checks (do not echo the token)
TOKEN=$(cat /Users/theyid/Documents/deepseek-harness/default-workspace/.git-auth/resolver_token)
for u in /api/20bensons /api/ukraves /api/ezgarage /api/podcast/dejavu-fm /api/live \
         /api/ezgarage/72aswcrx4hlw2sh/stream /api/ukraves/6948/stream \
         /static/art/20bensons.png /static/art/djez.png; do
  curl -sS -m 15 -o /dev/null -w "%{http_code} $u\n" \
    -H "Authorization: Bearer $TOKEN" "http://192.168.1.179:8097$u"
done
```

Expected with live web 1.6.75 and the configured token: lists 200; the two stream children
and the two art files **401**. Without the token all nine are 401. This is the core of D1/D2.

---

*Report written read-only. No files outside this report were modified; no ADB/device access,
no Kodi launch, no push and no new tag were used.*
