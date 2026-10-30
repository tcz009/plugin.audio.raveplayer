# Rave Player 3.4 — code-quality review

Scope: correctness, structure and performance of the working add-on. No menu
labels, section tables, source URLs, queries or playback behaviour were changed
on purpose. `addon.xml`, the repository add-on, artwork, `dist/` and `scripts/`
were not touched, and the version was not bumped.

## Verification

| Check | Result |
|---|---|
| `python3 -m unittest discover -s test -v` | **88 tests, all OK** (was 21) |
| `python3 -m py_compile default.py resources/lib/*.py ...` | OK, 22 files |
| Python 3.8 grammar (`ast.parse(..., feature_version=(3, 8))`) | OK, 22 files |
| `python3 test/run.py root` | output identical to pre-change baseline |
| `python3 test/run.py media_menu` | output identical to pre-change baseline |
| `media_menu` cold/warm timing (local) | ~4.7–5.5 s → ~0.6 s warm |

The smoke runner still hits the network; the unit suite is entirely offline and
uses fixtures plus `unittest.mock`.

## Changes, ranked

### 1. On-disk cache for network responses (performance)
New `resources/lib/cache.py`, plus `ttl=` support in `http.fetch()` /
`http.fetch_json()`. The cache lives under the add-on profile
(`getAddonInfo("profile")/cache`, with `special://` translation when Kodi
provides one), one SHA-256-named JSON file per key, containing
`{"v": 1, "ts": ..., "value": ...}`. Writes use a temporary file and
`os.replace`, and every read/write failure is swallowed and logged at debug
level. `RAVEPLAYER_CACHE_DIR` overrides the location for tests.

This is the fix for `media_menu` making five feed downloads before drawing.
Fresh TTLs:

| Response | TTL |
|---|---|
| Podcast feed body | 15 min |
| Archive search page | 5 min |
| Archive item metadata | 1 h |
| RaveTapePacks index, JungleTapes show pages, Toronto index | 6 h |
| JungleTapes sitemap | 24 h |
| DNB Radio recordings index | 10 min |

`http.fetch()` uses `cache.remember()`, so `None`/failed responses are not
cached and a temporary outage does not stick for the whole TTL.

### 2. Crash-proofing bad server responses
- `archive.search()` now validates that the payload is a dict, that `response`
  is a dict, that `docs` is a list of dicts, and that `numFound` is parseable.
  Previously `int("nope")` or `docs: null` crashed the route.
- `archive.audio_files()` skips non-dict file entries and entries with a
  missing/null `name`; `_rank()` no longer calls `.lower()` on a null
  `format`; a null/odd `metadata.title` is handled.
- `archive.item()` URL-quotes the identifier; `thumb()` and download URLs are
  quoted too. `audio_files()` keeps slashes in multi-disc filenames.
- `radio.stations()` filters non-dict stations and tries the next mirror when
  one returns an empty/malformed list; `radio.display()` handles non-string
  names and zero/invalid bitrates.
- `routes._year_label()` no longer renders the string `None` when both `year`
  and `date` are absent; `_rows_per_page()` falls back to 50 when the setting
  is 0/negative, preventing a division-by-zero on the “Next page” label;
  documents without an identifier are skipped.
- `http._request()` now catches `http.client.HTTPException`, `OSError`,
  `EOFError` and `zlib.error` in addition to the previous exceptions, and
  closes `HTTPError` objects. A truncated/corrupt gzip response returns `None`
  instead of raising.
- Empty/absent route keys (`legacy_pack`, `legacy_jt_show`, `archive_item`,
  `dnb_play`, `play`) now notify and stop before doing network work.

### 3. Toronto Rave Mixtape Archive: `&amp;` bug (real playback bug)
The site returns paths such as
`/files/mixtape/Wolf &amp; Tranzit - Live at ...mp3`. The old code quoted the
literal `&amp;`, producing
`Wolf%20%26amp%3B%20Tranzit...` and a 404; the label also showed `&amp;`.
`html.unescape()` now runs before quoting, so the URL is
`Wolf%20%26%20Tranzit...` and the label is `Wolf & Tranzit`. Verified against
the live site (the current “Wolf & Tranzit” tape was affected).

The same entity/percent-decoding fix is applied to RaveTapePacks filenames,
JungleTapes MP3 URLs and DNB titles. `legacy._url_path()` decodes once and
re-encodes once, avoiding double-encoding of already-escaped hrefs.

### 4. HTTP text decoding / feed encoding
- `http._decode()` honours a UTF-8 BOM, UTF-16 BOMs and an XML declaration’s
  `encoding=` when the HTTP header has no charset; unknown charsets fall back
  to UTF-8 instead of raising `LookupError`.
- gzip and deflate are handled case-insensitively; gzip streams are closed.
- Feed parsing no longer does the redundant `.replace("&amp;", "&")` after
  ElementTree has already decoded XML entities (that could corrupt a literal
  `&amp;` in an enclosure URL).

### 5. RSS/Atom and duration correctness
- Atom support was effectively dead: the parser selected namespaced
  `{Atom}entry` elements but then looked for un-namespaced `title`, `link` and
  `summary`, so Atom feeds yielded no episodes. Lookups now try both plain and
  Atom namespaced names; Atom `<link rel="enclosure">`/audio links work.
- `_text()` joins nested elements, so titles like `Hello <b>World</b>` become
  `Hello World` instead of dropping the nested text.
- `itunes:duration` with fractional seconds (`1:02:03.500`) was parsed as
  days/hours/minutes/seconds and produced ~223,880 s. The fractional tail is
  now ignored; invalid durations return `None`, not `0`.
- `feeds.registry()` validates the JSON shape and normalises ids/names/plot
  text, so a malformed `feeds.json` cannot crash the menu.

### 6. Radio / DNB / legacy cleanup
- DNB’s MP3 regex now only matches `href`/`src` attributes, not any `.mp3`
  text on the page; mix ids are URL-quoted; the recordings index is cached.
- Radio station tags are quoted, and the station limit is clamped.
- `legacy._pretty()` and `_pack_name()` shared four copies of the camel-case
  logic; they now share `_space_words()`. Dead `_strip_tags()` was removed.
- `dnbradio.link()` is reused by `stream_url()` instead of duplicating the
  URL construction.

### 7. `routes.py` structure
The duplicate Archive-document rendering in `archive_list` and `search` is now
one `_archive_items()` helper. `_page_number()`, `_rows_per_page()`,
`_year_label()`, `_clean_description()` and `_as_text()` keep the handlers
short. `_clean_description()` now unescapes HTML entities, strips tags and
collapses whitespace before the 600-character cut; this fixes raw `<p>` markup
and `&amp;` appearing in plots.

`kodi.notify()` now removes commas and newlines from both arguments, since
they delimit the `Notification(...)` builtin, and tolerates a bad timeout.
`kodi.setting_bool()` accepts Kodi’s `true`/`1`/`yes`/`on` spellings.

## Tests added

- `test/test_cache.py` (12): round-trip, TTL, future timestamps, corrupt and
  wrong-version files, non-JSON-serialisable values, `remember()` success/failure,
  and disk errors.
- `test/test_http.py` (12): gzip/deflate, BOM/XML/unknown charsets, corrupt
  gzip, network errors, text/JSON caching, cache keys by header, bad JSON not
  cached, cache failure not breaking fetch.
- `test/test_routes.py` (12): description cleaning, year/page/rows edges,
  Archive item rendering, invalid dispatch, empty legacy keys.
- `test/test_kodi.py` (4): notification escaping and setting parsers.
- `test/test_parsers.py` expanded from 21 to 48: Archive bad payloads/null
  formats, Toronto/JungleTapes entity URLs, DNB regex, Atom feeds, fractional
  durations, radio mirror fallback, feed caching.

## Deliberately not changed

- **Menu structure, labels, source queries, playback wrapping.** The
  `mode=play` resolver pattern and the `collection:ravetapes` queries are
  untouched, as are all icons/plots.
- **Archive result ordering.** `_rank()` still puts originals before derived
  MP3s; changing it would reorder tracks for users.
- **Live radio is not cached, and DNB listen/stream pages are not cached.**
  Station lists change often and proxy stream URLs can be time-limited; a
  stale URL is worse than a request.
- **No stale-while-error cache fallback.** Serving an old feed during an
  outage would hide the failure; the add-on still notifies and shows an empty
  list.
- **No cache pruning or size cap.** One small file per key, bounded by the
  number of feeds/searches used; adding an eviction policy would be more code
  than the problem warrants.
- **No new settings for TTL.** Constants live next to each provider; the
  settings file is untouched.
- **No feed pagination and no change to the 200-episode count cap** in
  `media_menu`; both are existing product decisions.
- **`_base_url()` still uses `sys.argv[0]`.** That is correct inside Kodi; it
  only makes the offline smoke runner print its own path in generated URLs.
- **`setInfo("music", ...)` retained** rather than moving to newer InfoTag
  APIs, to keep Kodi 20–22 compatibility.
- **No new sources, browser automation or third-party packages.**

## Tempted but left alone

- Stripping HTML from *feed* descriptions (would change what users see in
  plots; only Archive plots are cleaned).
- Caching radio-browser results for a few minutes (would make the radio menu
  faster but can hide newly added stations).
- Switching Archive sorting to `addeddate desc` (a product change, not a
  cleanup).
- Adding a blanket `try/except` around `dispatch()` (would turn real coding
  errors into generic notifications).
- Reformatting `_jt_label()` dates (`20030211...`) into readable dates; that
  would change 300+ visible labels.
