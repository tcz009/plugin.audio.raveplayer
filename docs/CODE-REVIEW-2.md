# Rave Player 3.6 — second code review

Scope: correctness and user experience of the working add-on, checked against
the live data shapes of every provider. Menu labels, section tables, source
queries and the add-on id were kept. `addon.xml`, the repository add-on,
artwork, `dist/`, `repo/` and the build scripts were not touched; the version
was not bumped.

**Suggested version bump: 3.6.0 → 3.7.0** (two user-visible features, new
settings, and a real playback-list fix). `changelog.txt` is deliberately
unchanged so the owner writes the release note.

## Verification

| Check | Result |
|---|---|
| `python3 -m unittest discover -s test -v` | **170 tests, all OK** (was 107) |
| Suite with HTTP blocked (`http_proxy=127.0.0.1:9`) | 170 tests OK, ~1.0 s — no live calls |
| Python 3.8 grammar (`ast.parse(..., feature_version=(3, 8))`) | OK, all `resources/lib/*.py` + `default.py` |
| `python3 test/run.py root` | 18 items, same section names as before |
| `python3 test/run.py media_menu` | 5 feeds, counts now match the lists |
| `python3 test/run.py latest` | 56 items, newest first |
| `python3 test/run.py filter_list key=kool` | live Kool item + Kool sets + Next page |
| `python3 test/run.py dnb_list` | 10 DNBRADIO shows |
| `python3 test/run.py archive_list key=rave page=1` | packs + Next page |
| `python3 test/run.py archive_item id=World_Dance_-_April_2nd__1994` | **7 tracks (was 14 duplicates)** |
| `python3 test/run.py legacy_packs`, `legacy_jt`, `radio_tag key=oldskool`, `year_list year=1994`, `play_all ... shuffle=1` | all produced plausible output, no exceptions |

## Changes, ranked

### 1. Archive items listed every track twice (real playback-list bug)

`archive.audio_files()` de-duplicated by *file name*, so the original
`Show.mp3` and its generated `Show.ogg` were treated as two recordings. Most
of the ravetapes collection has Archive-generated OGG derivatives, so most
multi-track packs showed each set twice. Verified live on
`World_Dance_-_April_2nd__1994`: 14 rows, 7 unique recordings.

Files are now keyed by **folder + stem**, ignoring the audio extension:

- `Show.mp3` / `Show.ogg` collapse to one, and the original (rank 0) wins;
- `Tape 1/01.mp3` / `Tape 2/01.mp3` stay separate (different folders);
- ordering is rank first, then filename, so track order is stable instead of
  depending on Archive's file-list order.

Tracks now also expose a parsed `duration` from Archive's `length` field, shown
in the Kodi list.

### 2. Favourites: stale lists, lost writes, and broken RaveTapePacks plays

- **Stale directory**: every list finished with `cacheToDisc=True` and nothing
  refreshed the container after `RunPlugin(fav_add/fav_remove)`, so removing a
  favourite could leave it on screen. `kodi.end_directory()` now defaults to
  `cacheToDisc=False` (the add-on has its own HTTP cache, so re-running a route
  is cheap), and add/remove call `Container.Refresh`.
- **Lost writes**: `favourites.save()` wrote in place; a Kodi kill mid-write
  left invalid JSON and silently emptied the list. It now writes a temporary
  file in the profile directory and `os.replace()`s it.
- **Crash on hand-edited data**: `fav_list()` indexed `entry["kind"]` directly,
  so a missing/unknown kind raised `KeyError`. `favourites.load()` now
  normalises every entry (kind, target, title, source), drops unusable ones and
  keeps a valid `kind` for back-compat.
- **403 on saved RaveTapePacks streams**: the favourite stored the bare MP3
  URL, losing the `|Referer=...` suffix that defeats the hotlink check. The
  context menu now saves `legacy.playable(url)`; `playable()` is also
  idempotent so a URL cannot collect the suffix twice.
- **Missing everywhere else**: "Add to favourites" now exists on DNBRADIO
  shows, live stations, Archive tracks, podcast episodes, "Latest" items,
  JungleTapes shows/tracks, Toronto tracks, and RaveTapePacks and JungleTapes
  folders (new `legacy_pack` / `legacy_jt` kinds, rendered by `fav_list` with
  their own routes). Existing saved entries still work.

### 3. Play all / Shuffle pack / Play all from here

New `play_all` route (`RunPlugin`) builds a Kodi music playlist from a pack:

- folder context menu: **Play all** and **Shuffle pack**;
- track context menu: **Play all from here** (starts at that track).

It reuses the same `audio_files()` call, carries titles, album and durations
into the playlist, and clamps an out-of-range start. This is the main
remote-friendly improvement for 16–24-track packs.

### 4. Pagination and counts that actually work

- **"More from 1994"** linked to the same page-1 URL and did nothing. It now
  carries `page=` and pages properly; page plots say "Page N of M · X items".
  A page that came back empty no longer offers a dead "Next page" link.
- **Search** ignored `results_per_page` and could only ever show 50 results.
  It now keeps the query in the URL and paginates (`q=` + `page=`), and skips
  the dialog when a query is already present.
- **`filter_list`** read the raw setting, so a `results_per_page=0` produced a
  zero-row query. All paging now goes through `_rows_per_page()`, clamped to
  1–200.
- **`latest.random_pack`** used `total // 50` instead of `ceil`, so the last
  partial page (24 of 724 packs) could never be chosen. It also now ignores a
  document with no identifier instead of returning `{"identifier": None}`.
- **Podcast counts** said "182 episodes" while the feed showed 60. The new
  `episode_limit` setting is used by both the menu count and the feed route, so
  the label matches the list.

### 5. Settings that matter (and their limits)

`resources/settings.xml` gains:

- `episode_limit` (default 60) — episodes per podcast feed;
- `hide_empty_feeds` (default false) — skip feeds returning nothing.

`results_per_page` is now capped at 200 and `episode_limit` at 500. Menu
notifications explain an empty result instead of leaving a blank folder:
missing Archive item, empty feed registry, all feeds empty, missing quick
filters, and an unknown live filter.

### 6. Metadata and "now playing" correctness

`ui.menu_item`/`ui.track_item` passed the *display label* (including
`[COLOR]`/`[I]` markup) into `setInfo("music", {"title": ...})`. Kodi renders
those tags literally in the OSD and other info panes. Metadata titles are now
stripped with `ui.plain()`, while the visible label keeps its markup. Durations
are passed for Archive tracks and feed episodes. Radio items pass a plain
station name as the title instead of "Name [I]GB · MP3 · 128 kbps[/I]".

### 6b. Feed plots are readable now

The live RSS.com descriptions are HTML (`<p>…<a href="…">…</a></p>`), so the
info dialog showed raw tags and unusable links. `feeds._description()` now
decodes entities and strips tags before the 400-character cut. This is a
deliberate reversal of the previous review's "leave feed descriptions raw"
decision, made because the raw markup was the thing users actually saw.

### 7. Provider robustness found while reading against live data

- **DNBRADIO**: a `title` without the `"date : show"` separator produced the
  same string as both title and date, and labels rendered as "(Title) Title".
  The date is only accepted when it is a real `YYYY-MM-DD`; otherwise the whole
  string is the title and the date is blank.
- **radio-browser**: `stations_by_name()` returned `[]` as soon as the first
  mirror answered with an empty list, unlike `stations()`. Both now try the
  next mirror and share one `_search()` helper; name searches also require a
  playable stream.
- **Legacy sites**: repeated MP3 links on one page are de-duplicated;
  RaveTapePacks' `href` regex also matches the non-`www` host; JungleTapes'
  own absolute `http://` stream URLs are upgraded to `https://` to save a
  redirect per play.
- **HTML stripping** used `<[^>]+>`, which also ate ordinary comparisons
  like "2 < 3 > 1"; both Archive plots and feed descriptions now require a
  tag-like name after `<`.
- **Cache**: a valid-looking entry with no `value` key made `_read()` return
  the internal `MISSING` sentinel as if it were data, which could reach
  `json.loads`. Missing/null values are now a clean miss. An empty HTTP 200
  body is no longer cached for the whole TTL, so a momentary server hiccup
  does not blank a feed until the cache expires.
- **`archive_item` without an id** ended the folder silently; it now notifies.
- **`archive.search()`** clamps `rows`/`page`, so a bad setting cannot ask the
  Archive for zero rows or page 0.

### 8. Smaller code-quality work

- `kodi.translate_path()` replaces the duplicated `special://` handling in
  `cache.py` and `favourites.py`.
- `archive.as_text()` is the one list/whitespace normaliser; `latest.py` uses it
  for Archive titles (which are sometimes lists).
- Station rendering, page-plot text and Archive track rendering are single
  helpers instead of copies in `radio_tag`/`filter_live`.
- `_play_tracks()` keeps playlist construction in one place; `play_all` stays
  a short handler.
- Removed the pointless `action = url_for(...)` local and the
  `__import__("datetime")` call; `years()` now uses a normal import.
- `feeds.py` routes description cleaning through one `_description()` helper;
  `http.py` gained a tiny cache producer so an empty body is not cached.

## Genuinely broken (found, now fixed)

1. Every Archive item with OGG derivatives listed each track twice (verified:
   14 → 7 tracks).
2. "More from YYYY" was a dead link that reloaded page 1.
3. The last page of the ravetapes collection could never be picked by
   "Surprise me".
4. A malformed favourites entry crashed the Favourites folder; a mid-write
   kill could erase all favourites; saved RaveTapePacks streams 403'd.
5. Removing a favourite could leave a stale list on screen.
6. Feed menus overstated episode counts (182 vs the 60 actually listed).
7. `results_per_page=0` produced empty filtered lists.
8. Kodi media titles contained display markup.
9. A corrupt cache entry could feed the cache sentinel into JSON parsing.
10. A DNBRADIO title without a date duplicated itself in the label.

## Deliberately not changed

- **Menu structure, labels, add-on id, section queries, playback resolver.**
  The `mode=play` + `setResolvedUrl` pattern and `setInfo("music", ...)` are
  kept for Kodi 19–22 compatibility.
- **Archive default sort** (`downloads desc`) and the existing original-before-
  derivative ranking. Changing them would reorder every pack list.
- **No new sources.** `docs/DISCOVERED.md` shows RaveTapePacks' WordPress RSS
  feed carries 49 episodes, but its enclosures are the same hotlink-protected
  MP3s; adding it would need provider-specific Referer handling, which is a
  product decision, not a review fix.
- **No stale-while-error cache fallback, no cache pruning, no TTL changes.**
- **No `container.Refresh` outside favourites** — other routes are re-entered
  normally, and refreshing on playback start would be disruptive.
- **Legacy show labels** still show raw sitemap slugs/numeric dates; changing
  them would alter 310 visible labels.
- **`_base_url()` still uses `sys.argv[0]`**, which is correct inside Kodi.
- **No version bump, no changelog edit, no `addon.xml`/repo change.**

## Tests added

Suite grew from **107 to 170**, still offline and under ~1 s with the network
blocked.

| File | Tests | New coverage |
|---|---|---|
| `test_archive.py` | 8 | OGG/MP3 stem de-duplication, multi-folder stems, rank ordering, length parsing, rows/page clamping |
| `test_ui.py` | 6 | Kodi markup stripping, metadata titles, duration/artist |
| `test_playlist.py` | 8 | play all, play from here, start clamping, shuffle, playlist metadata, empty pack |
| `test_routes.py` | 29 | setting caps, start index, page text, search pagination, year pagination, media-menu limits/hide-empty, favourites routing, context menus, empty-item notifications |
| `test_favourites.py` | 16 | normalisation, invalid entries, legacy kinds, atomic replacement, disk failure |
| `test_cache.py` | 15 | missing/null value, sentinel never returned |
| `test_parsers.py` | 56 | DNB missing/garbage date, radio name mirror fallback, legacy de-duplication, HTTPS upgrade, idempotent Referer |
| `test_latest.py` | 12 | last-page random pick, list titles, missing identifier |
| `test_kodi.py` | 7 | `cacheToDisc=False` default, `Container.Refresh`, path translation |
| `test_http.py` | 13 | empty HTTP 200 responses are not cached |
