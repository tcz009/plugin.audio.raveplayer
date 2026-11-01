# HARDENING — Rave Player Kodi add-on 3.9.11

**Branch:** `hardening/3.9.11` (created from tag `v3.9.10-review`, HEAD `b0f8c7f`)
**Base:** `plugin.audio.raveplayer` 3.9.10 · **Result:** 3.9.11, **259 offline tests OK** (was 207)
**Date:** 2026-11-01 · **Not pushed / not released.**

Scope: internal hardening only — real, provable defects in the runtime code and
their test coverage. No new features, no re-layout, no UX change beyond two
failure-path notifications and the removal of one destructive side effect.
Adversarial pre-review findings K1–K11 are folded in; every one is addressed
below, with explicit deferral notes where the Lead's "smallest safe version"
direction was followed. Nothing was deferred silently.

---

## 1. Result at a glance

| | |
|---|---|
| Suite | **259 tests OK** (was 207): +52 offline tests, no network/Kodi needed |
| P0/P1 findings | **0 open** (K1, K2, K3 fixed) |
| Adversarial findings | 11/11 addressed: 10 fixed in code/tests, K3's concurrent-feed refactor deferred (see §3) with the per-route wall-clock cap + notification implemented instead |
| Runtime code changed | `default.py`, `resources/lib/{archive,cache,feeds,favourites,http,kodi,legacy,radio,routes}.py` |
| Tests changed | `test/test_{archive,cache,compat,favourites,http,parsers,routes}.py`, `test/stubs/{xbmc,xbmcplugin}.py` |
| Docs | `docs/HARDENING.md` (this file), `docs/CODE-REVIEW.md`, `changelog.txt`, `addon.xml`; `AGENTS.md` fixed locally (git-excluded by design, never published) |
| Compatibility | Python 3.9 grammar floor enforced; no module/API removed in 3.9–3.14 is used; Kodi 22 (Python 3.14) not runnable in this environment (see §6) |

---

## 2. Adversarial findings K1–K11

### K1 — P1 — A handler exception escaped `dispatch`; the folder never finished
**Finding (proved by the reviewer):** `dispatch()` called the handler bare;
`endOfDirectory` was never called on an exception, so Kodi was left with an
unfinished directory and a traceback in the log.
**Fix:**
- `routes.dispatch()` now guards the handler, logs the full traceback at error
  level, notifies the user, and closes the route correctly: folder routes end
  `endOfDirectory(..., succeeded=False)` *unless the handler already ended*;
  playback routes report `setResolvedUrl(False)`; RunPlugin routes only notify.
- `kodi.end_directory()` records the handle (idempotent; `reset_directory()` /
  `directory_ended()`), so a directory is never ended twice.
- `default.py` gained a last-resort `main()` guard around `routes.dispatch()`.
- A per-invocation network budget is always cleared in `finally`.
**Tests:** `test_routes.DispatchFailureTests` (folder crash → notify + log +
`SUCCEEDED=[False]` + `directory_ended`, budget cleared; playback crash →
resolved `False`; RunPlugin crash → notify only without directory output);
`test_compat.EntryPointGuardTests` (`default.main` swallows a dispatch error and
passes argv through). **Status: fixed.**

### K2 — P1 — `OverflowError` from `inf`/`1e400` in duration metadata
**Finding (proved):** `feeds._duration()` and `archive._duration()` used
`int(float(text))` while catching only `TypeError`/`ValueError`; third-party
`inf`/`Infinity`/`1e400` metadata crashed the whole route.
**Fix:** catch `OverflowError` (and `TypeError`) in `archive._as_int`,
`archive._duration` (including the colon form and the very-long-digit form),
`feeds._duration` (colon and plain forms) and `radio._as_int`.
**Tests:** `test_archive.ArchiveUrlSafetyTests.test_infinite_durations_and_sizes_do_not_raise`
(`inf`, `-inf`, `"Infinity"`, `"inf"`, `"1e400"`, `"1e999"`, huge digit string);
`test_parsers.FeedTests.test_duration_overflow_is_safe` (`"Infinity"`, `"inf"`,
`"-inf"`, `"1e999"`, `"1e400"`); `test_parsers.RadioTests` display with
`bitrate=inf`. **Status: fixed.**

### K3 — P1 — Aggregate blocking I/O was unbounded (cold Latest ≈175 s, Podcasts ≈125 s, radio 60 s every visit, JungleTapes ≈85 s)
**Finding:** Kodi routes are synchronous; per-call timeouts did not bound the
sum, `urllib`'s timeout is per socket operation (slowloris), and radio had no
cache.
**Fix (smallest safe version, as directed by the Lead — no refactor):**
- New per-invocation **wall-clock network budget: 20 s**
  (`http.begin_route()` / `end_route()` / `remaining()`). Every fetch clamps its
  timeout to the remaining budget; once spent, further fetches return `None`
  immediately (cache hits are still served — see H7). `routes.dispatch()` starts
  and always clears the budget.
- All response bodies are read with a wall-clock deadline and byte cap (also K4),
  so a slow-drip upstream cannot outlive its clamped timeout.
- **Clear notification:** when a folder route finishes with the budget exhausted,
  `dispatch` shows "Some sources were slow — showing partial results." (playback
  and RunPlugin routes do not show it).
- Live radio: each mirror attempt is now **8 s** and station lists are cached for
  **10 minutes** (`radio.MIRROR_TIMEOUT`, `radio.STATIONS_TTL`) — previously 3 × 20 s
  on every visit with no cache.
- Worst-case cold screen is now one 20 s budget (was up to ~175 s), with a
  notification and a usable partial directory.
**Tests:** `test_http.ResponseHardeningTests.test_budget_clamps_the_request_timeout`,
`test_zero_budget_skips_the_request`, `test_route_budget_stops_a_sequence_of_fetches`,
`test_body_read_has_a_wall_clock_deadline`, `test_end_route_clears_the_budget`,
`test_cached_body_is_served_even_after_the_budget_is_gone`;
`test_routes.SlowSourceNoticeTests` (folder route notifies, playback route does
not); `test_parsers.RadioTests.test_mirror_attempts_use_a_short_timeout` (8 s +
TTL). **Status: fixed**, with the concurrent-feed-fetch part explicitly deferred
(§3).

### K4 — P2 — Unbounded response reads / gzip decompression
**Fix:** `http._read_limited` reads in 64 KiB chunks with an 8 MiB cap
(`http.MAX_BODY_BYTES`), rejects a declared `Content-Length` over the cap, and
enforces a wall-clock deadline per read loop; `http._decompress` caps gzip
(`GzipFile.read(cap+1)`) and deflate (`decompressobj(max_length)`) output too.
**Tests:** `test_http.ResponseHardeningTests.test_oversized_body_is_rejected`,
`test_gzip_bomb_is_rejected_after_decompression`,
`test_declared_content_length_over_the_cap_is_rejected`,
`test_body_read_has_a_wall_clock_deadline`. **Status: fixed.**

### K5 — P2 — XML entity expansion (billion laughs) on feeds
**Fix:** `feeds.parse()` rejects any document containing `<!ENTITY` before
`ElementTree` sees it (DOCTYPE without entity declarations is still accepted,
because legitimate podcast feeds ship it), and also catches `RecursionError`.
`http`'s 8 MiB cap is the second layer.
**Test:** `test_parsers.FeedTests.test_entity_declarations_are_rejected`.
**Status: fixed.**

### K6 — P2 — `play` resolved any URL it was handed
**Fix:** new `routes._playable_url()` accepts only `http`/`https` with a host;
`file:`, `special:`, `plugin:`, `smb:`, `javascript:` etc. are rejected with a
notification and a failed resolve. A Kodi `|Header=…` suffix is preserved (the
scheme check runs on the part before the pipe).
**Tests:** `test_routes.PlaybackFailureTests.test_play_rejects_non_http_urls`
(file/special/plugin/javascript), `test_play_accepts_http_urls_with_a_header_suffix`.
**Status: fixed.**

### K7 — P2 — Favourites read-modify-write races lost entries
**Fix:** `favourites.add()`/`remove()` now hold a best-effort advisory lock
around load-modify-save (`favourites.json.lock`, `fcntl.flock` where available,
`msvcrt.locking` on Windows, unlocked fallback where neither exists); writes
remain atomic (`temp + os.replace`). Proven effect: with the lock two concurrent
adds keep both entries; with the lock disabled the ad-hoc harness loses one.
**Test:** `test_favourites.FavouriteConcurrencyTests.test_two_concurrent_adds_keep_both_entries`
(widens the read-modify-write window with a slow `load` and runs two threads).
**Status: fixed.**

### K8 — P3 — Cache never evicted / grew without bound
**Fix:** `cache.maintain()` is run opportunistically every 64 writes: it removes
entries older than 30 days, deletes abandoned `.tmp-*` files older than an hour,
and caps live entries at 2000 (oldest first). Oversized entry files (>16 MiB)
are dropped on read instead of being loaded. Atomic write semantics unchanged.
**Tests:** `test_cache.CacheMaintenanceTests` (expired entry removal, entry cap,
stale vs live temp files, oversized entry not loaded, failed `os.replace` leaves
no temp, hostile key cannot escape the cache directory).
**Status: fixed.**

### K9 — P3 — Third-party titles composed into Kodi label markup unescaped
**Fix:** every third-party string used in a `ListItem` label now goes through
`ui.plain()` first — Archive search/`archive_item` titles, Latest titles and
sources, podcast episode titles/published dates, DNB titles/dates, radio station
names/meta, legacy pack/show/track names, favourites titles, Rave Nights names.
The add-on's own deliberate markup (`[COLOR gray](…)`, `[I]…[/I]`) is applied
afterwards, so it keeps working.
**Tests:** `test_routes.ThirdPartyLabelTests` (archive, Latest and feed titles
with `[B]`/`[CR]`/`[/COLOR]` → stripped, text retained).
**Status: fixed.**

### K10 — P3 — A failed resolve wiped the user's whole music queue
**Fix:** `_fail_playback()` no longer calls `PlayList(...).clear()`. It notifies,
stops the current playback attempt if one is running, and reports the failed
resolve. The "Latest" cascade remains fixed by the 3.9.8 design (directory typed
`files`, unresolvable DNB rows resolved/dropped at build time), so the destructive
queue clear is no longer needed.
**Tests:** `test_routes.PlaybackFailureTests` now assert `PlayList.clear` is
**not** called for unresolved/raising `dnb_play` or an empty `play`, and that the
resolve is `False`. **Status: fixed** (deliberate behaviour change; no cascade
regression — the 3.9.8 cascade tests still pass).

### K11 — P3 — Audit docs described a different add-on than the tag
**Fix:** `docs/CODE-REVIEW.md` no longer lists non-existent
`mixcloud.py`/`soundcloud.py` (module table now shows the real providers and adds
`nowplaying.py`), and says Kodi 20–22 with Kodi 22 on Python 3.14. `AGENTS.md`
now says version **3.9.10** at tag `v3.9.10-review`, hardening on
`hardening/3.9.11`, suite **259 tests** (207 at the tag) and records 3.9.8–3.9.11
in the recent-history line; its stale "expect 193 OK" rule was corrected too.
`addon.xml`/`changelog.txt` are at 3.9.11. (`AGENTS.md` is listed in
`.git/info/exclude` as never-published workspace instructions, so its correction
is local-only and not part of the branch diff.)
**Tests:** `test_compat` guards the runtime against the documented 3.9 floor and
removed stdlib modules; docs are not executable, so this is a documentation
correction verified by inspection. **Status: fixed.**

---

## 3. Deferred items (explicit)

1. **K3 — concurrent fetching of the five podcast feeds (deferred).** The Lead
   directed the "smallest safe version: per-route wall-clock cap + clear
   notification, not a refactor". That is implemented: a cold Podcasts/Latest
   screen is now capped at the 20 s invocation budget with a notification and a
   partial directory, instead of up to 125–175 s. Parallelising the feed loop
   would change the provider and route flow more than this pass warrants; it is
   a possible follow-up if the 20 s worst case proves too long on the Shield.
2. **K6 — private/link-local host blocking for `play` (deferred).** Only
   `http(s)` is allowed now; adding the web app's private-IP deny-list would need
   DNS-resolution handling in a synchronous Kodi route. The residual impact is
   device-local (a Kodi user can already play local files); the scheme allow-list
   is the proportionate fix for this repo.
3. **K9 — Kodi markup in `plot`/InfoTag text beyond `title` (not widened).**
   Reviewer's finding was about labels; labels are fixed. Plots are built from
   the same titles and ``ui`` already strips InfoTag titles; plot markup was not
   part of the finding and is not known to be exploitable in Kodi's plot field.

No other finding was deferred. All P1s are fixed with tests.

---

## 4. Additional findings fixed in this pass (not in the adversarial list)

| ID | Severity | Finding | Fix | Test |
|---|---|---|---|---|
| H1 | High (metadata trust) | Archive `files[].name` and metadata `dir`/storage node were interpolated into playback URLs with `quote(..., safe="/")` — a name like `../../evil.mp3` or `dir` like `/x/../../evil`, a `?`/`#`/control chars, or a node like `evil.com:80` could escape the item path or inject URL parts into the URL Kodi streams. | New `archive._relative_url_path()` (reject absolute/backslash/control/empty/"."/".." segments, quote each segment) and `archive._safe_directory()`/host validation for the direct storage node; unsafe metadata falls back to the `/download/` URL or is dropped. | `test_archive.ArchiveUrlSafetyTests` (traversal/absolute/backslash/control filenames dropped, valid names still quoted; hostile dirs/nodes rejected; fallback URL used; valid node preserved) |
| H2 | Medium | `archive._as_int` and the colon branch of `archive._duration` could still raise on float `inf` or a 6000-digit token. | `OverflowError`/`ValueError` caught; colon parse wrapped. | `test_archive` infinite/huge duration test |
| H3 | Medium (broken feature) | `rave_nights` pre-quoted catalogue names *before* `url_for()`'s `urlencode`, so names with spaces (`Rinse FM`, `World Dance`, `Renegade Hardware`…) failed to resolve on `rave_list` with "no longer in the catalogue"; page-2 links double-encoded too. | Pass raw catalogue names to `url_for()` (single encode/decode) in both places; `rave_list` also uses clamped `_rows_per_page()` and tolerates a non-numeric `page` without a traceback. | `test_routes.RaveRouteTests` (URL round-trips `"World Dance"`; `rave_list` resolves it; next-page key not double-encoded; invalid page safe) |
| H4 | Low-Medium | Legacy scrapers built URL paths from scraped HTML with `quote(safe="/")`: a `../` path could walk the site path, and JungleTapes MP3 links could be `file:`/`javascript:`. | `legacy._url_path()` rejects empty/"."/".." segments; JungleTapes track URLs must be `http(s)` with a host. | `test_parsers.LegacyTests.test_url_path_rejects_traversal`, `test_jungle_tracks_drop_non_http_links` |
| H5 | Medium | `radio.stream_url()` accepted any scheme (a hostile radio-browser row could be `file:`/`javascript:`), and station lookups were uncached and slow. | `http(s)` + host validation in `stream_url`; 8 s per mirror, 10 min TTL. | `test_parsers.RadioTests` scheme rejection + timeout/TTL assertions |
| H6 | Low | `http._request()` added request headers *outside* the `try`, so a non-string header value could raise `TypeError` past the failure boundary. | Header construction moved inside the guarded block and values stringified; `TypeError`/`UnicodeError` also counted as network failures. | `test_http.ResponseHardeningTests.test_non_string_header_values_do_not_raise` |
| H7 | Low | `http.fetch(..., ttl=…)` checked the route budget *before* the cache, so once the budget was spent even cached data was refused. | Cache is consulted first; the budget only gates the network call. | `test_http.FetchCacheTests.test_cached_body_is_served_even_after_the_budget_is_gone` |
| H8 | — | Python 3.9–3.14 compatibility audit (Kodi 22 ships 3.14). | No runtime incompatibility found: no module removed in the window is imported, no removed API is called, and the source parses under the 3.9 grammar. A guard test enforces both. | `test_compat` (grammar floor, removed-module/call scan, import smoke, `default.main` guard) |

---

## 5. Verification

```sh
cd raveplayer
python3 -m unittest discover -s test
# Ran 259 tests in 1.2s
# OK
```

Targeted evidence used in this document:

```sh
python3 -m unittest test.test_routes test.test_http test.test_cache \
    test.test_archive test.test_parsers test.test_favourites test.test_compat -v
```

Test count: 207 → 259 (+52). The suite remains fully offline (stubs in
`test/stubs`), needs no Kodi and no network, and runs in ≈1–2 s.

Notable reproductions that are now covered instead of escaping:
- handler crash → notification + log + `endOfDirectory(succeeded=False)`
  (previously exception escaped, no end);
- `inf`/`1e400` durations in Archive/feed metadata → `None` (previously
  `OverflowError` killed the route);
- oversized body / gzip bomb / slow read → `None` within caps (previously
  unbounded read);
- `<!ENTITY>` feed → rejected (previously expanded);
- `file:`/`javascript:` enclosure or `play` URL → rejected (previously passed to
  Kodi);
- Archive filename `../../evil.mp3` → dropped (previously produced a traversal
  URL);
- concurrent favourites adds → both kept (previously one lost);
- cache with 5 old entries/1 stale temp → pruned (previously never evicted);
- `[B]`/`[CR]` in a title → stripped from the label (previously rendered);
- non-http `play` URL → failed resolve (previously resolved blindly).

---

## 6. Compatibility

- Syntax floor: every runtime file parses with `ast.parse(..., feature_version=(3, 9))`.
- No import of a module removed in Python 3.9–3.14 (`cgi`, `imp`, `distutils`,
  `asyncore`, `telnetlib`, `pipes`, `crypt`, …) and no removed callable
  (`locale.getdefaultlocale`, `inspect.getargspec`, `time.clock`, …).
- New code stays stdlib-only and 3.9-compatible (no `match`, no `X | Y` types).
- This Mac runs Python 3.9.6 and cannot run Kodi 22 (Python 3.14); the check is a
  static guard plus import smoke test, not a device test. The add-on has no
  compiled extensions or third-party wheels, so the risk surface is the stdlib
  API checks above.

---

## 7. Files changed (no push, no release, no repo/ or dist/ changes)

```
resources/lib/http.py       + bounded reads/decompression, wall-clock route budget
resources/lib/cache.py      + maintenance/eviction, oversized-entry guard
resources/lib/archive.py    + filename/dir validation, host validation, overflow-safe numerics
resources/lib/feeds.py      + entity guard, http(s)-only enclosures, overflow-safe durations
resources/lib/radio.py      + scheme allow-list, 8 s mirror timeout, 10 min station cache
resources/lib/legacy.py     + URL-path traversal guard, http(s)-only JungleTapes media
resources/lib/favourites.py + advisory lock around load-modify-save
resources/lib/kodi.py       + idempotent end_directory tracking
resources/lib/routes.py     + top-level guard, route budget, play scheme gate, K9 escaping,
                              non-destructive failure path, rave_nights encoding fix
default.py                  + last-resort main() guard
test/…                      52 new tests + stub support
docs/HARDENING.md           this file
docs/CODE-REVIEW.md         K11 accuracy (module list, Kodi/Python note)
AGENTS.md                   K11 accuracy (local-only; git-excluded, not in the commit diff)
addon.xml / changelog.txt   3.9.11
```

Per the Lead's instruction the branch is committed locally but **not pushed**;
`dist/` and `repo/` were not touched (so the 3.9.11 repo zip/catalogue remain a
publish-time step).
