# HARDENING — Rave Player Kodi add-on 3.9.22

**Branches:** `hardening/3.9.11` (tag `v3.9.10-review`), `hardening/3.9.12` (from 3.9.11 `main`), and
`hardening/3.9.13` (from 3.9.12 `main` at `7ff12e6`) and `hardening/3.9.14` (from 3.9.13 `main` at `4f5cbe2`) and
`hardening/3.9.15` (from 3.9.14 `main` at `dc4cd9c`) and
`hardening/3.9.16` (from 3.9.15 `main` at `b0a515a`) and
`hardening/3.9.17` (from 3.9.16 `main` at `614e6ad`) and
`hardening/3.9.18` (from 3.9.17 `main` at `4007f52`) and
`hardening/3.9.19` (from 3.9.18 `main` at `c413a3d`) and
`hardening/3.9.20` (from 3.9.19 `main` at `1141748`) and
`hardening/3.9.21` (from 3.9.20 `main` at `3ec49b6`) and
`hardening/3.9.22` (from 3.9.21 `6745a15`; playback audit).
**Base:** `plugin.audio.raveplayer` 3.9.10 → 3.9.22 · **Result:** 3.9.22, **409 offline tests OK** (403 + 6 playback-audit tests)
**Date:** 2026-11-01 · **Not pushed / not released.**

Scope: 3.9.11–3.9.13 were internal hardening passes — real, provable defects
in the runtime code and their test coverage, with no UX change beyond failure
notifications and the removal of one destructive side effect. 3.9.14 is the
one feature pass in this document: it adds the Moxser, Hardscore, Rave Archive
UK and GetDarker sources plus the curated Pirate Radio Archives, all built on
the same HTTP/route guards (§10). Adversarial review K1–K11 and independent
review A1–A13 are folded in; every item is addressed below, with explicit
deferral notes where the Lead's "smallest safe version" direction was followed.
Nothing was deferred silently.

---

## 1. Result at a glance

| | |
|---|---|
| Suite | **403 tests OK** (unchanged; no network/Kodi needed) |
| P0/P1 findings | **0 open** (K1, K2, K3 fixed) |
| Review findings | Adversarial K1–K11 all addressed (3.9.11/3.9.12); independent-review A1–A5, A7–A9, A11, A12 fixed in 3.9.13 (§9); A8 was already fixed and re-tested; A10/A13 remain known/accepted residuals. |
| Runtime code changed | `default.py`, `resources/lib/{archive,cache,feeds,favourites,getdarker,handoff,hardscore,http,kodi,latest,legacy,mixcloud,moxser,pirate,radio,routes,ui}.py`, `resources/pirate-radio.json` |
| Tests changed | `test/test_{archive,cache,compat,favourites,http,latest,parsers,routes,playlist,ui}.py` plus new `test_{handoff,moxser,hardscore,mixcloud,pirate,sources}.py`, `test/stubs/{xbmc,xbmcplugin}.py` |
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
`addon.xml`/`changelog.txt` are at 3.9.13 for this pass (§9). (`AGENTS.md` is listed in
`.git/info/exclude` as never-published workspace instructions, so its correction
is local-only and not part of the branch diff.)
**Tests:** `test_compat` guards the runtime against the documented 3.9 floor and
removed stdlib modules; docs are not executable, so this is a documentation
correction verified by inspection. **Status: fixed.**

---

## 3. Deferred items (explicit)

1. **K3 parallel feeds — CLOSED in 3.9.12 (§8).** The 3.9.11 "smallest safe
   version" (20 s wall-clock cap + notification) is still in place; 3.9.12 adds
   the bounded ThreadPoolExecutor on top at the Lead's request.
2. **K6 private-IP guard — CLOSED in 3.9.12 (§8).** Scheme allow-list kept;
   DNS resolution + private/loopback/link-local/metadata deny-list added. LAN
   self-hosting trade-off is documented in §8.2.
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

Test count: 207 → 259 at 3.9.11 → 272 at 3.9.12 → 295 at 3.9.13 → 328 at 3.9.14 → 334 at 3.9.15 → 360 at 3.9.16 → 369 at 3.9.17 → 394 at 3.9.18 → 403 at 3.9.19 → 403 at 3.9.20 → 403 at 3.9.21 → **409 at 3.9.22** (+6 playback audit). The suite remains
fully offline (stubs in `test/stubs`), needs no Kodi and no network, and runs
in ≈1–2 s.

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
- non-http `play` URL → failed resolve (previously resolved blindly);
- private/loopback/metadata `play` host → failed resolve (3.9.12, §8.2);
- three feeds fetch concurrently and a slow feed is clamped by the shared
  route budget (3.9.12, §8.1).

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
resources/lib/http.py       + read1 slow-drip bound, public/budgeted redirects, injective cache keys,
                              per-route DNS memo, bounded reads/decompression
resources/lib/cache.py      + maintenance/eviction, oversized-entry guard, thread-safe counter
resources/lib/archive.py    + filename/dir validation, archive.org-only storage nodes, overflow-safe numerics
resources/lib/feeds.py      + entity guard (UTF-16/bytes refused), bounded descriptions,
                              episodes_many bounded thread pool
resources/lib/radio.py      + scheme allow-list, 8 s mirror timeout, 10 min station cache
resources/lib/legacy.py     + URL-path traversal guard, http(s)-only JungleTapes media
resources/lib/favourites.py + advisory lock around load-modify-save, fsync before rename
resources/lib/kodi.py       + idempotent end_directory tracking
resources/lib/routes.py     + top-level guard, route budget, play + play_all public-host gate,
                              art-URL gate, linear descriptions, K9 escaping, non-destructive failure
resources/lib/latest.py     + parallel feed fetch (3.9.12)
resources/lib/moxser.py     + Moxser sitemap/page -> direct MP3 (3.9.14)
resources/lib/hardscore.py  + Hardscore RSS + post-page media (3.9.14)
resources/lib/getdarker.py  + GetDarker RSS pages (3.9.14)
resources/lib/mixcloud.py   + curated Mixcloud accounts (Kodi add-on hand-off, 3.9.16)
resources/lib/pirate.py     + Pirate Radio Archives data loader (3.9.14)
resources/lib/handoff.py    + official Kodi add-on detection + plugin:// URLs (3.9.16)
resources/lib/downloads.py  + explicit offline downloads, metadata, storage guard (3.9.18)
resources/lib/spinner.py    + spinning-head overlay/frame math/fallback (3.9.19)
scripts/benchmark.py        + reproducible route benchmark (3.9.20)
resources/skins/Default/720p/raveplayer-spinner.xml
resources/art/spinner/      + 20 pre-rendered head frames (3.9.19)
resources/pirate-radio.json + curated Risk FM / Weekend Rush / Flava FM data (3.9.14)
default.py                  + last-resort main() guard
test/…                      121 new tests + stub support (+ slow-drip/redirect/art/description regressions)
docs/HARDENING.md           this file
docs/CODE-REVIEW.md         K11 accuracy (module list, Kodi/Python note)
AGENTS.md                   K11 accuracy (local-only; git-excluded, not in the commit diff)
addon.xml / changelog.txt   3.9.22 (3.9.11–3.9.21 earlier passes)
```

Per the Lead's instruction the branch is committed locally but **not pushed**;
`dist/` and `repo/` were rebuilt for 3.9.22 after the playback audit.

> Branch note: `hardening/3.9.12` also contains an unrelated docs/CI commit
> `d323075` that landed on the shared worktree while this branch was checked
> out (README/workflow/stream-check files, plus an in-progress copy of the
> http/cache thread-safety edits). It is flagged to the Lead rather than
> rewritten; the 3.9.12 parallel-feed and private-IP changes are commit
> `1f32d46`.

---

## 8. 3.9.12 follow-ups (closing the two deferred items)

### 8.1 K3 follow-up — parallel feed fetch

**Finding:** `latest.recent_episodes()` fetched feeds serially; even after the
3.9.11 wall-clock cap, a single slow feed could consume the whole 20 s budget
before the remaining feeds were even attempted, shortening Latest/Podcasts.

**Fix:**
- New `feeds.episodes_many(entries, limit, workers=5)` — bounded
  `ThreadPoolExecutor`, results returned in registry order (deterministic
  rendering), per-feed failure isolation (`[]` for that entry), and a serial
  fallback if the executor cannot be created.
- `latest.recent_episodes()` and `routes.media_menu()` use it; all feeds start
  together, so a slow one is clamped by its own per-fetch timeout rather than
  starving the rest.
- The **20 s per-route wall clock is unchanged**: every worker calls the same
  `http.fetch`, which clamps to `http.remaining()`. The route-budget globals are
  now guarded by a `threading.Lock` (begin/end/remaining/exhausted), and the
  cache maintenance counter is locked too, so concurrent workers cannot corrupt
  the budget or the cache bookkeeping. Cache reads/writes remain atomic and
  cached bodies are still served after the budget is gone.
- Live check (dev network, cold): Latest **9.9 s** vs 15.5 s with serial feeds
  and ~175 s before any hardening.

**Tests:**
`test_latest.ParallelFeedTests` — a `threading.Barrier(3)` inside the mocked
feed fetcher proves concurrent execution (a serial implementation cannot pass);
one raising feed is isolated; a deliberately slow feed with a 0.3 s route budget
finishes with all three feeds represented and elapsed < 0.8 s while every
observed request timeout is ≤ 0.35 s; empty registry does not fetch.
`test_parsers.FeedBatchTests` — empty entries, per-feed failure isolation and
serial fallback when the executor is unavailable. `test_routes` updated for the
parallel media menu (`feeds.episodes_many`).

**Status: fixed.**

### 8.2 K6 follow-up — private-IP playback guard

**Finding:** `play` limited the URL scheme only; a query string or favourite
could point at `http://127.0.0.1/…`, `http://192.168.1.10/…`,
`http://169.254.169.254/…` etc. and make the device fetch itself/the LAN.

**Fix:** `routes._playable_url()` now:
- validates `http(s)` + host as before;
- resolves the host with `socket.getaddrinfo` (literal IPs are checked without a
  lookup) and rejects if **any** answer is loopback, link-local, private,
  multicast, reserved or unspecified — covering 127/8, ::1, 169.254/16, 10/8,
  172.16/12, 192.168/16, fc00::/7 and IPv4-mapped loopback;
- also rejects unresolvable hosts (Kodi could not play them anyway) and mixed
  public/private DNS answers (rebinding guard);
- returns the original string, so the Kodi `|Header=…` suffix is intact.
  Failures show a clear notification and report a failed resolve.

**LAN self-host trade-off (documented):** a stream served from the user's own
private network (e.g. a self-hosted Rave Player web server at
`http://192.168.x.x:84xx/…`, or `localhost`) can no longer be played through the
add-on's `play` route. That is deliberate: the add-on only needs public sources,
and private URLs arriving from metadata/favourites would otherwise trigger
requests into the user's local network. Users with a LAN-only source can use
Kodi's own library/local files or the web app directly; a future
"allow private/LAN hosts" setting would be the way to restore it.

**Residual:** `getaddrinfo` is a synchronous OS call inside the play route and is
not itself bounded by the HTTP budget. In normal use it is milliseconds, but a
broken resolver can delay a single play attempt. A resolved-host cache/async
lookup is a possible follow-up (not needed for the deliverable sources, which are
public names).

**Tests:** `test_routes.PlaybackHostGuardTests` — literal ranges incl.
`169.254.169.254`, hostname resolving private, mixed public/private answers,
unresolvable host all rejected with notify + failed resolve; public host allowed;
`|Header=` suffix preserved. DNS is monkeypatched (`getaddrinfo`) in every test.

**Status: fixed.**

---

## 9. Independent review 2026-11 — add-on findings (3.9.13)

The independent reviewer held 3.9.12; the add-on findings and their disposition
are below. A6 was explicitly withdrawn by the reviewer (Kodi ships Python 3.11+
and the py3.9 int limit does not reach the supported targets); A10/A13 remain
known/accepted residuals (documented, not silently dropped).

### A1 — P1 — `_read_limited` did not actually bound a slow-drip body

**Finding:** the deadline was checked only between `response.read(65536)` calls;
because `HTTPResponse.read(n)` blocks until n bytes/EOF/socket timeout, a server
dripping one byte per interval could hold Kodi's plugin thread far past the 2 s
budget (reviewer reproduced 12.09 s). This made the K3/K4 wall-clock claim false.

**Fix:** `_read_limited` now calls `read1()` (one recv's worth per wake-up),
recomputes the wall-clock deadline before every read, and clamps the underlying
socket timeout to the remaining deadline (`_set_read_timeout` best-effort; body
caps and decompression caps unchanged). A slow-drip response can no longer
outlive its deadline by more than one recv.

**Tests:** `test_http.ReadBoundTests` — `SlowDripResponse` (1 byte per 20 ms)
abandoned at a 0.12 s deadline, and `fetch` under a 0.15 s route budget returns
`None` in <0.8 s. The old implementation returned the slow body / blocked and
fails these tests.

### A2 — P2 — Redirects were unvalidated and unbudgeted

**Finding:** `urllib` followed redirects automatically: a public URL could
redirect to loopback/LAN (SSRF-ish) and a 10-hop chain escaped the 20 s budget;
`ftp:` was followed too.

**Fix:** automatic redirects are disabled (`_NoRedirectHandler`); `_request`
follows redirects manually, at most 3 hops. Every target is resolved as a public
http(s) URL via the same host guard as playback (mixed/private/unresolvable
answers refused) and each hop gets a fresh `_effective_timeout` clamp, so the
route budget is charged across the whole chain. Redirect response bodies are
closed; a refused/non-public hop returns `None` with a log line.

**Tests:** `test_http.RedirectHardeningTests` — public redirect followed; loopback
redirect refused; `ftp:` refused; hostname resolving private refused; 4th hop
refused after 3 redirects; mid-chain slow hops bounded by a 0.25 s budget; the
auto-redirect handler is confirmed absent from the opener. All redirect targets
are DNS-mocked, so the suite stays offline.

### A3 — P2 — `play_all` / `_play_tracks` bypassed the private-IP guard

**Finding:** `play` had the 3.9.12 public-host guard, but `play_all` built the
music playlist directly from `archive.audio_files()` URLs, so hostile Archive
metadata (`d1=127.0.0.1`, etc.) could still point Kodi at loopback/LAN/an
arbitrary host.

**Fix:**
- `_play_tracks` re-validates every track URL through the shared
  `http.safe_stream_url` guard, skips bad rows with a notification, and returns
  `False` when nothing is playable (`play_all` then notifies as before).
- Defence in depth: `archive._direct_base` accepts storage nodes only under
  `archive.org` (real nodes are `*.archive.org`), so hostile metadata cannot use
  the direct-node optimisation at all; it falls back to the public
  `archive.org/download/` URL.
- The host guard is memoised per route, so a pack with many tracks on one host
  does not do one DNS lookup per track.

**Tests:** `test_playlist.PlayAllUrlGuardTests` — a private track is skipped and
never reaches `xbmc.PlayList` while public tracks still play; an all-private pack
does not start playback and notifies. `test_archive.ArchiveUrlSafetyTests` —
`evil.example.com`, `127.0.0.1`, `localhost`, `192.168.1.10` storage nodes are
rejected; `ia*.us.archive.org` is kept.

### A4 — P2 — Quadratic tag-stripping regexes

**Finding:** `routes._clean_description`, `feeds._description` and `ui._MARKUP_RE`
used unbounded `[^>]*` / `[^\]]*` after an opening token; hostile
`"<a" * 131072` or `"[COLOR" * N` input made the regex engine rescan to
end-of-string each time (16.7 s for 256 KiB; a hang for larger input).

**Fix:** every scan is capped (descriptions 8 KiB, labels 1 KiB) and repetition
inside the tag pattern is bounded (`[^>]{0,512}` / `[^\]]{0,100}?`), making the
substitution linear in the capped input. Final output limits are unchanged
(600/400 chars; markup-stripped labels).

**Tests:** `test_routes.DescriptionBoundTests` (131 KiB of `<a` returns ≤600
chars in <0.5 s), `test_parsers.FeedHardeningTests` (130 KiB description returns
≤`DESCRIPTION_LIMIT` in <0.5 s), `test_ui` (`"[COLOR" * 70000` capped and <0.5 s).

### A5 — P3 — UTF-16 entity-declaration bypass

**Finding:** `feeds.parse` scanned bytes with `decode("ascii", "replace")` for
`<!ENTITY`; UTF-16 XML has interleaved NULs so the marker was missed and
ElementTree auto-detected UTF-16 and expanded the entities.

**Fix:** `feeds.parse` refuses `bytes`/`bytearray` input outright (the HTTP layer
always returns decoded text). The existing entity-marker guard now only ever
sees `str`, so UTF-16/other byte encodings cannot bypass it.

**Tests:** `test_parsers.FeedHardeningTests.test_utf16_byte_xml_is_refused`
(UTF-16 and UTF-16-LE both `[]`).

### A7 — P3 — Favourites atomic write lacked fsync

**Fix:** the temporary JSON file is flushed and `os.fsync`ed before
`os.replace`, so a sudden power loss cannot leave the rename pointing at
unflushed data.

**Test:** `test_favourites.FavouriteTests.test_save_fsyncs_before_the_atomic_rename`.

### A8 — P3 — `stations_by_name` exposed stations without a stream URL

**Status: already fixed in 3.9.11/3.9.12.** `radio._search()` (used by both
`stations()` and `stations_by_name()`) drops entries whose `stream_url()` is
empty. Re-verified by the existing
`test_parsers.RadioTests.test_stations_by_name_tries_next_mirror_and_needs_a_stream`;
no code change was needed.

### A9 — P3 — Cache key was ambiguous for hostile header values

**Finding:** the key joined `k=v` pairs with `&`, so header
`{"Referer": "a&b=c"}` collided with `{"Referer": "a", "b": "c"}`; a poisoned
cache entry could be served for a different header set.

**Fix:** header pairs are lower-cased and JSON-encoded with sorted keys into the
key (`json.dumps`, compact separators), which is injective. Existing cache
entries become misses on upgrade (self-healing; TTLs are short).

**Tests:** `test_http.CacheKeyTests` — the colliding pairs now differ; header
case remains normalised.

### A11 — P3 — Unvalidated art URLs reached Kodi's image loader

**Finding:** station favicons and the `thumb`/`fanart` plugin parameters were
passed to `setArt` unvalidated, so metadata could ask Kodi to fetch
`http://127.0.0.1/…` or a `file:` path as artwork.

**Fix:** `_safe_art` accepts only public http(s) URLs (same host guard as
playback) and otherwise falls back to the add-on icon; applied to station
favicons, `play`'s thumb/fanart, and the play URL's thumb parameter.

**Tests:** `test_routes.ArtUrlGuardTests` — a loopback station favicon becomes
the add-on icon; `play` with `file:///etc/passwd` thumb and a public stream
resolves but uses the add-on icon.

### A12 — P3 — Stale review/docs claims

**Fix:** `docs/CODE-REVIEW.md` now says 3.9.13, 295 tests, and describes the
current behaviour (20 s budget, validated redirects, shared play/play_all guard,
no queue clear, current cache key/eviction, Kodi 22 `plot` warning accepted).
This file records the independent-review fixes and corrects the earlier K4
blanket claim: response reads are now genuinely bounded (A1).

### A10 / A13 — known/accepted residuals

- **A10 — DNS resolution in the play/redirect guard is synchronous.** The first
  lookup for a host can still block on the OS resolver; repeated lookups within
  one route are memoised. The guard is required for the private-IP protection;
  an async/resolved-host cache remains a possible follow-up (documented in
  CODE-REVIEW and here).
- **A13 — Kodi 22 logs an "Unknown Music Info Key" warning for the legacy
  `plot` field on music InfoTags.** `comment` is the supported field and is set
  as well; removing `plot` would break older consumers, so this is accepted and
  documented in CODE-REVIEW.

---

## 10. New sources (3.9.14)

Fifth pass: add the Moxser, Hardscore, Rave Archive UK and GetDarker sources
plus the curated **Pirate Radio Archives** menu. All provider HTTP goes through
the existing `http.fetch` contract, so the 20 s route budget, public-host and
redirect guards, cache and fail-soft handling apply unchanged. Tests are
fixture/mock-only; no live network in the suite.

### 10.1 Moxser — sitemap/page adapter

**What:** `resources/lib/moxser.py` fetches
`https://moxser.com/sitemaps-1-sitemap.xml`, selects the
`sitemaps-1-section-mixes-*.xml` entries (max 4), parses mix page URLs plus the
sitemap `image:image` title/flyer and date, then on selection fetches one mix
page and extracts `og:title`/`og:image`/first public `.mp3` link (e.g. the
`enceladus.feralhosting.com/moxser/...mp3` host; the files are `audio/mpeg`
with Range support).

**Guards/politeness:** 6 h TTL for sitemaps and mix pages, a hard ≤1
request/second throttle, browser User-Agent, page URLs restricted to
`https://moxser.com/mixes/…`, MP3 candidates go through
`http.safe_stream_url`, and every failure returns `[]`/`{}` (no traceback).
The list route fetches only the two sitemaps; the per-mix page fetch happens
when the user opens a row, so the 20 s route budget is respected.

**Tests:** `test/test_moxser.py` — sitemap index selection, sitemap
title/date/flyer parsing, cache TTL + browser UA assertions, page title/date/
flyer/MP3 extraction, unsafe MP3 dropped, foreign page URLs never fetched,
fail-soft, throttle sleeps.

**Menu:** `Pirate Radio Archives` is independent; Moxser is
`plugin://plugin.audio.raveplayer/?mode=moxser`, detail
`?mode=moxser_mix&page=<mix-page>`.

### 10.2 Hardscore — RSS + post pages

**What:** `resources/lib/hardscore.py` parses the WordPress RSS
(`https://www.hardscore.com/?feed=rss2`) into title/page URL/date/direct media
(enclosure or MP3/M4A link in the description). Rows with media play in Kodi;
rows without media open `?mode=hardscore_event&page=…`, which extracts media
and outbound SoundCloud/Mixcloud/YouTube links from the post page and falls
back to opening the post.

**Gotcha found live:** Hardscore's “Bad Behavior” filter returns HTTP 403 to a
bare urllib request even with a browser UA; the adapter adds an
`Accept: application/rss+xml,application/xml,text/xml,*/*` header (verified
live) and keeps the browser UA for page fetches.

**Tests:** `test/test_hardscore.py` — feed enclosure/page-only rows, date,
cache/UA assertions, post-page media/link extraction, foreign-host refusal,
fail-soft. **Menu:** `?mode=hardscore` / `?mode=hardscore_event`.

### 10.3 Rave Archive UK and GetDarker — curated Mixcloud

**What:** `resources/lib/mixcloud.py` wraps the public Mixcloud API
(`api.mixcloud.com/<account>/cloudcasts/`) for the two curated accounts
(`ravearchiveuk`, `getdarker`) with a 1 h TTL; `resources/lib/getdarker.py`
also lists the GetDarker RSS set pages via the shared Hardscore parser.

**Deliberate limitation:** Mixcloud audio is HLS and the sanctioned player is
their iframe widget; there is no legitimate direct stream for Kodi. Rows
therefore validate the page URL and call `kodi.open_external` (Android VIEW
intent; dialog with the URL on other platforms) instead of pretending to
resolve audio. Rave Archive UK is surfaced through its Mixcloud account; its
WordPress RSS has no enclosures.

**Tests:** `test/test_mixcloud.py` (curated registry, API mapping, hostile/
malformed account and URL filtering, TTL, fail-soft);
`test/test_sources.py` routes for both accounts and `open_url`.
**Menu:** `?mode=mixcloud_account&key=rave-archive-uk` and
`?mode=mixcloud_account&key=getdarker`; GetDarker RSS at `?mode=getdarker`.

### 10.4 Pirate Radio Archives — data + menu

**What:** `resources/pirate-radio.json` uses the web app's exact schema:
`station, year, title, djs, source_url, stream_url, credit` (plus optional
`note` when a page URL could not be confirmed). `resources/lib/pirate.py`
validates/loads and groups by station; routes list stations then their
recordings: direct `stream_url` → play, `source_url` → open page, neither →
show the metadata/note.

Seeded data:
- **Risk FM 107.1** — Beat Sanctuary, Andy Campbell / Daniel James / Fat Daddy
  Zak and the David Morris December 1996 SoundCloud link. The exact Beat
  Sanctuary/SoundCloud URLs could not be confirmed, so `source_url`/
  `stream_url` are empty and the row carries a note (known metadata kept, as
  required); the closest confirmed recording (David Morris, Risk 107.1, 29 July
  1995, Mixcloud) is named in the note.
- **Weekend Rush 92.3** — Force of One Crew (June 1993) and DJ Infinity & DJ
  Freedom with MCs Trojan & Concrete (25 June 1995), both with confirmed
  Hardscore post URLs and direct MP3s.
- **Flava FM** — A-Team old-school Mixcloud playlist; the original MegaUpload
  links are dead and no stable playlist URL could be confirmed, so the row has
  empty URLs, `year: null` and a note.

**Tests:** `test/test_pirate.py` — exact field-name/schema set, station order
and grouping, confirmed Hardscore source/stream URLs, unconfirmed rows have
empty URLs + note, malformed/missing data ignored. `test/test_sources.py` —
menu/station routes, metadata-only rows notify and never offer fake playback.
**Menu:** `?mode=pirate_menu` → `?mode=pirate_station&station=…` →
`?mode=pirate_note&station=…&title=…` for metadata-only rows;
`?mode=open_url&url=…` for source pages; direct MP3s use the existing
`?mode=play&url=…` route.

### 10.5 Root menu paths added

```
Latest
...
Podcasts & Mixes
DNB Radio Archive
Moxser Mixes                         ?mode=moxser
Hardscore Archive                    ?mode=hardscore
Rave Archive UK                      ?mode=mixcloud_account&key=rave-archive-uk
GetDarker                            ?mode=getdarker
Pirate Radio Archives                ?mode=pirate_menu
Legacy Sites
...
```

`GetDarker` lists the RSS set pages (and a first row to the getdarker
Mixcloud account); every page/detail route ends a directory (`files` for mixed
folder/playable lists) so Kodi never spins.

---

## 11. Menu IA rebuild (3.9.15)

Approved IA in workspace `docs/MENU-IA-REVIEW.md`; owner decisions: keep
GetDarker, Latest merges "on air now", About becomes real credits/sources.

### 11.1 Root — 26 rows → 9 journey rows

Exact ordered labels now pinned by `test_sources.NewSourceRouteTests`:
`Latest`, `Surprise Me`, `Tape Packs`, `Mixes & Shows`, `Live Radio`,
`Curated Gems`, `Favourites`, `Search the Archive`, `About & Sources`.

### 11.2 Three hubs — every old destination reachable, same mode/key

- **Tape Packs** (`?mode=packs_menu`, 10 destinations + Back): Rave Tape Packs
  (`archive_list key=rave`), Jungle / Drum & Bass (`jungle`), Hardcore
  (`hardcore`), House (`house`), UK Garage (`garage`), **Pirate Stations**
  (`pirate` — renamed from "Pirate Radio"), All Tape Packs (`tapepacks`), **By
  Year** (`years`), **Classic Pack Series** (`filters_menu`), **By Rave &
  Venue** (`rave_nights`).
- **Mixes & Shows** (`?mode=shows_menu`, 5 + Back): Podcasts & Mixes
  (`media_menu`), DNB Radio (`dnb_list`), Moxser Mixes (`moxser`),
  **Hardscore.com** (`hardscore`), **GetDarker (dubstep/grime)** (`getdarker`;
  hidden without the Mixcloud add-on, §12).
- **Curated Gems** (`?mode=curated_menu`, 3 + Back): Pirate Radio Archives
  (`pirate_menu`), Rave Archive UK (`mixcloud_account key=rave-archive-uk`;
  hidden without the Mixcloud add-on, §12), **Legacy Archives (2014)**
  (`legacy_menu`).

No route was deleted; `HANDLERS` still has every old mode, so saved favourites
(including `filter_list key=kool/rinse`), deep links and the existing dist
build keep working. The only new routes are the three hub handlers.

### 11.3 Live Radio and Latest

- `radio_menu` now promotes Kool FM and Rinse FM above the seven genre rows:
  Kool FM · Rinse FM · Oldskool & Rave · Jungle · Drum & Bass · Hardcore ·
  House · UK Garage · Breakbeat (+ Back). The Kool/Rinse rows keep the
  existing `filter_list` mode/key (live stream + archive sets).
- `latest_view` prepends `● On air now · Kool FM` and `● On air now · Rinse FM`
  as direct `mode=play` track rows (from `radio.curated`, omitted when a
  stream is unavailable), so row 1 is genuinely play-something. The rows are
  safe under the existing public-host/redirect guard; the directory still ends
  as `files` with the visible End of list marker.

### 11.4 About & Sources

`?mode=about` is now a credits/sources screen (version + GPL-3.0 + GitHub,
archive.org, Mixcloud, SoundCloud, radio-browser.info, Moxser, Hardscore,
GetDarker, Kool/Rinse). Source rows are `mode=open_url` links, validated by the
public-URL guard; no content is hosted by the add-on.

### 11.5 Tests / docs

`test_sources.NewSourceRouteTests` now pins the exact root labels and covers
Tape Packs (all 10 labels/keys), Mixes & Shows (5), Curated Gems (3), Live
Radio order and About sources; `test_routes.LatestCascadeTests` adds
`test_latest_prepends_live_on_air_rows` and keeps the no-item/no-live case.
328 → **334 tests**. README menu section, CODE-REVIEW 3.9.15, changelog and
addon version updated.

---

## 12. Kodi-only hand-off policy (3.9.16)

> This section supersedes the browser/link-out behaviour described for 3.9.14
> (§10.3) and 3.9.15 (§11.4): those rows now hand off to official Kodi add-ons
> or are hidden; no browser/OS intent is used anywhere in the runtime.

Owner decision: **no Kodi row may open a browser or leave Kodi.** Any source
without a direct in-add-on stream must hand off to an official Kodi add-on and
be hidden if that add-on is absent.

Final owner decisions for this integrated 3.9.16:
- **`Curated Gems` keeps that exact label**; the Pirate & Rave Archives rename
  is rejected.
- **SoundCloud is removed from the Kodi build entirely** — no content row, no
  hand-off row, no SoundCloud hand-off from Hardscore/GetDarker links (those
  links do not render). It survives only as a plain About text credit marked
  “web version only”.
- **Mixcloud and YouTube are optional hand-offs** exactly as below: rows only
  when the official add-on is installed, hidden otherwise.
- The nine-row root is unchanged; theme/3.9.16 art/icons/fanarts are retained.

### 12.1 Detection

New `resources/lib/handoff.py`:
- `plugin.audio.mixcloud`, `plugin.video.youtube`. SoundCloud is deliberately
  not detected or handed off; it is web-version-only.
- `available(kind)` checks `xbmcaddon.Addon(id).getAddonInfo("id")` and falls
  back to `xbmc.getCondVisibility("System.HasAddon(<id>)")` (AddonManager).
  A missing/foreign add-on is treated as unavailable (no row).

### 12.2 Hand-off URLs (rows are `plugin://` paths)

| Source | Present add-on → path |
|---|---|
| Mixcloud cloudcast | `plugin://plugin.audio.mixcloud/?mode=40&key=<urlencoded /user/slug>` |
| Mixcloud search | `plugin://plugin.audio.mixcloud/?mode=30&key=cloudcast&offset=0&query=<q>` |
| YouTube video | `plugin://plugin.video.youtube/play/?video_id=<id>` |
| YouTube search | `plugin://plugin.video.youtube/search/?q=<q>` |

The row URL is the hand-off path itself, so selecting it enters the official
add-on's search/cloudcast directory inside Kodi; no `open_url`/OS intent/dialog.

### 12.3 What is hidden without each add-on

| Missing add-on | Hidden |
|---|---|
| `plugin.audio.mixcloud` | GetDarker row in Mixes & Shows; Rave Archive UK row in Curated Gems; Mixcloud links on Hardscore/GetDarker pages; direct `mode=getdarker`/`mode=mixcloud_account` produce no rows (notify only). |
| `plugin.video.youtube` | YouTube links on Hardscore/GetDarker pages. |

Also hidden rather than offered as dead rows: Moxser mix pages without a direct
MP3; Hardscore/GetDarker posts with no direct media and no supported hand-off;
Pirate Radio Archives metadata-only entries (Risk FM/Flava FM stay in the JSON
with notes, but the menu only lists direct-file stations such as Weekend Rush).
Direct-file sources are untouched: Moxser MP3s, Hardscore MP3s, archive.org,
tape packs, Kool/Rinse live streams.

### 12.4 Removed browser paths

`routes.open_url`, `_open_source_item`, the `open_url` handler and
`kodi.open_external` are gone. About & Sources is a read-only `ui.info_item`
credits list (no URLs). `HANDLERS` has no `open_url`; there are no
`open_external`/browser/OS-intent calls in `resources/lib`.

### 12.5 Tests

- `test_handoff.py`: availability via xbmcaddon/condvisibility; exact Mixcloud
  cloudcast/search and YouTube play/search URLs; SoundCloud is rejected;
  foreign hosts rejected.
- `test_sources.py`: missing mixcloud → GetDarker/Rave Archive rows absent and
  direct routes produce no rows; present mixcloud → cloudcast rows are
  `plugin://plugin.audio.mixcloud`; Hardscore/GetDarker links become
  Mixcloud/YouTube plugin rows when present and disappear when
  absent; About rows have empty URLs; no `open_url` handler/browser helper.
- 334 → **360 tests**; docs/changelog/addon version updated.

---

## 13. Theme + hand-off integration (3.9.16 final)

`theme/3.9.16` and `hardening/3.9.16` were merged into one 3.9.16 (the theme
worktree/art is retained; the hand-off logic is applied on top):

- Root labels and order stay exactly the nine IA rows (`Curated Gems` not
  renamed). Every theme icon/fanart wiring is kept: root `root_rows` with
  `fanart-*.jpg`, hub `fanart-hub-*.jpg`, per-source GetDarker/Hardscore/Moxser/
  Pirate Archive art and the re-cut 256×256 stickers (`pirate-archive.png`
  replaces the missing `pirate_source.png`).
- Hand-off logic is preserved on top: Mixcloud/YouTube rows are still
  conditional on their add-on; SoundCloud links are ignored and no SoundCloud
  content/hand-off row exists.
- `docs/THEME-2026.md` + `docs/theme-2026/` are kept; `test/test_theme_art.py`
  runs with `handoff.available` mocked for the optional GetDarker/Rave Archive
  rows.
- `dist/` and `repo/` are rebuilt **after** the merge (not hand-edited) so the
  published 3.9.16 zip contains the theme, hand-off policy and SoundCloud
  removal; tests: **360**.

---

## 14. Raw-platform URL leak fix (3.9.17)

Shield report: Mixcloud links opened Android's Downloader although
`plugin.audio.mixcloud` was not installed. Root cause/affected paths:

- The pre-hand-off Android VIEW intent (`kodi.open_external`) was the original
  browser/Downloader trigger; 3.9.16 removed that call.
- Residual raw-URL paths in the integrated tree could still produce
  `https://…mixcloud.com/…` as an item or resolved play URL: saved favourites
  (`kind=stream`), Latest/podcast episode URLs, hardscore/getdarker/legacy/radio
  direct media, and the generic `play` route accepted any public http(s).
- Fix: `handoff.platform_kind` is now the **single classifier** for
  Mixcloud/SoundCloud/YouTube page URLs; `handoff.target` is the **single
  availability gate** (absent add-on → `''`). `play`/`_playable_url` reject raw
  platform URLs, every route that can receive one filters/hides or converts it
  to a plugin hand-off, and `ui.add_item` has a final choke point that drops
  any raw platform URL (log + no listitem).
- Test: `test_ui.RawPlatformUrlTests`, `test_handoff.platform_kind/target`,
  and `test_sources` favourites/latest/feed/play leak regressions; absent
  add-on asserts no `mixcloud.com`/`soundcloud.com`/`youtube.com`/`youtu.be`
  item URL and no `plugin://` path is emitted.
- 360 → **369 tests**. Mixcloud/YouTube hand-offs unchanged when present;
  SoundCloud remains web-version-only.

---

## 15. Downloads / offline phase 1 (3.9.18)

Explicit user downloads only — no automatic download anywhere. Shared
eligibility with web 1.6.16 (motion-1x1): the same four sources, extensions,
source-host allow-list, public-host predicate and filename scheme.

### 15.1 Eligibility (single predicate)

`downloads.eligible(url, source, check_host=False)` is the single direct-file
predicate. Eligible only when all hold:
- source is exactly one of `Archive.org`, `Moxser.com`, `Hardscore.com`,
  `Pirate Radio Archives`;
- public `http`/`https`, no URL credentials, path ends `.mp3`/`.m4a`;
- host matches that source's allow-list (`*.archive.org`,
  `moxser.com`/`enceladus.feralhosting.com`, `hardscore.com`);
- not a platform page; the start route re-checks the resolved public host.
Excluded: podcast/RSS, Legacy, GetDarker, Mixcloud/SoundCloud/YouTube pages,
live/HLS, and all auto-download. Context menus use the cheap check; the
`download_start` route always re-runs the full public-host `plan`.

### 15.2 Files, names, guards

- Directory: `special://userdata/downloads/raveplayer/` via `xbmcvfs`.
- Filename: `<sanitized-title>-<8hex sha1(url)>.mp3/.m4a`; separators/control/
  reserved names removed, length capped.
- `http.probe_media` HEAD validates `Content-Type` (`audio/*` or
  `application/octet-stream`) and known `Content-Length`; 500 MiB per-file,
  2 GiB total saved, and a 256 MiB free-space reserve. The confirmation dialog
  reports size + free space before any transfer.
- Atomic write: `.part` via `xbmcvfs.File`, close, rename to final; metadata
  index `downloads.json` written after success. Cancel/failure deletes `.part`
  and never leaves a final file/index row. Overwrite asks first and replaces.

### 15.3 View / delete / playback

- **Favourites → Downloads** (`?mode=downloads_menu`): local files with
  size/date; selecting plays the local path (offline, no network); delete
  context removes file + metadata. Missing files show “missing” and can be
  deleted. Back returns to Favourites.
- No network is used by the view. No auto-download.

### 15.4 Context paths and tests

Context action URL (only on eligible rows):
`RunPlugin(plugin://plugin.audio.raveplayer/?mode=download_start&url=<encoded>&title=<encoded>&source=<source>)`
with source one of the four approved labels. Delete:
`RunPlugin(…?mode=download_delete&key=<key>)`.

Tests: `test/test_downloads.py` (predicate, sanitisation, plan/caps/free
space, success/cancel/failure cleanup, overwrite, delete, missing/partial,
atomic files), `test/test_download_routes.py` (context menus on the four
sources, no Download on platform/podcast/legacy rows, Favourites Downloads
entry, view local/missing rows, confirmation size/free text, start/delete
routes). 369 → **394 tests**.

---

## 16. Spinning-head download overlay prototype (3.9.19)

Opt-in cosmetic prototype for the 3.9.18 download flow; default off, so the
plain `DialogProgress` remains the default. Full spec/preview:
`docs/SPINNER-3.9.19.md`.

- **Window:** custom `xbmcgui.WindowXML` (`resources/skins/Default/720p/raveplayer-spinner.xml`, dialog 14000) with image 100, filename 101, percent 102, size 103, remaining 104, cancel hint 105, progress 106.
- **Frames:** 10 pre-rendered PNGs at 256px (and 128px) in
  `resources/art/spinner/`; circular alpha mask, 36° steps, 10 fps; frame index
  `int(elapsed*10)%10`; no GIF dependency. Regenerate with
  `python3 scripts/make-spinner.py` (Pillow dev-only).
- **Lifecycle:** `download_start` opens the overlay only when the
  `spinner_overlay` setting is on; progress callback updates it from the
  download loop; `finally` closes it on success/cancel/failure; if
  `WindowXML` construction/`show()` fails, the route uses the existing
  `DialogProgress`; update failures close the overlay and do not stop the
  download. Back/Stop sets the cancel flag, which the download loop polls.
- **Cost/risks:** ~512 KB frames + 4 KB XML, no runtime dependency. Non-modal
  `WindowXML.show()` is assumed (Kodi standard); a modal future/skin would
  need the setting off. Animation depends on progress updates rather than a
  separate UI thread (thread-safety). Skin layout authored for Estuary 720p;
  fallback covers failure. No Shield capture was available; preview is a mock
  rendered from the real overlay spec.
- **Tests:** `test/test_spinner.py` (frames/XML, index, formatting, lifecycle,
  open failure, cancel), `test/test_download_routes.py` (overlay selected and
  closed; automatic dialog fallback when window open fails). 394 → **403**.
- **Recommendation:** keep opt-in for the Shield trial; promote to default only
  after device validation. Replacing the notification outright now would couple
  a cosmetic prototype to the download path.

---

## 17. Performance pass (3.9.20)

Measured before/after in `docs/PERF-3.9.20.md`; reproducible
`scripts/benchmark.py`. No URL, label, route, setting or test-count changes
(**403 tests unchanged**).

- **Latest:** `latest.merge()` fetches feeds, Archive packs and DNB directory in
  a bounded 3-worker pool (results retrieved in source order; serial fallback).
  `dnbradio.stream_url()` caches listen-page resolutions for 6 h. Warm Latest
  no longer re-resolves every DNB row.
- **Import-time:** provider modules are lazy proxies in `routes`; `http` builds
  urllib/http.client/socket/gzip/zlib/opener/cache lazily; routes defer
  datetime/re/html/traceback; `ui.plain()` compiles regex lazily and skips it
  when no `[` is present. Warm root import+dispatch: **0.777 → 0.080 s**. Full
  CLI process wall ~0.64 → ~0.18 s (Python/OS startup; caveat documented).
- **Hot paths/cleanup:** spinner frame paths `lru_cache`d; dead `http.probe_size`
  and `moxser.stream_urls` removed.
- **Results:** root route ~0.0001 s; hubs ~0.0001 s; Latest cold **6.0/6.1 s**
  (target ≤10), warm **0.04 s** (target ≤2); cached pack open **~0.003 s**
  (target ≤3); Downloads view ~0.000 s.
- **Risks:** lazy imports shift first-use cost to first network route (included
  in measured cold Latest); DNB direct URLs may be up to 6 h stale by design;
  lazy opener/socket proxies preserve the tested patch points.

---

## 18. Docs/UX refresh (3.9.21)

No player, route, URL or label behaviour changed.

- README menu section renamed to 3.9.21 and documents the nine root rows, four
  hubs, Favourites → Downloads and the opt-in spinner; current renders added
  for root, hubs, Downloads and spinner under `docs/theme-2026/` and
  `docs/spinner-preview.png`.
- About & Sources now credits every source actually used (DNB Radio, podcast/
  RSS feeds, Pirate Radio Archives, RaveTapePacks, JungleTapes, Toronto Rave
  Mixtape Archive) and clarifies SoundCloud as **web version only** with no
  Kodi row/hand-off. README gains a linked **Sources & credits** table; all
  links checked live on 2026-11-01.
- `docs/QA-KODI.md`: repeatable Shield checklist covering install/update,
  root/hubs, Kool/Rinse live, pack playback, download + Downloads view, spinner
  toggle, hand-off absence (no browser/Downloader) and About credits. 403 tests
  remain unchanged.

---

## 19. Playback audit (3.9.22)

No autonomous playback path exists. Only `play`/`dnb_play` (explicit list
item) and `play_all` (explicit context action) can start audio; directory
routes, Latest on-air rows, favourites streams, Downloads, About and the
spinner only build ListItems. The Shield incident evidence is external ADB
input injection (logcat 20:27–29), not add-on code. `_fail_playback` no longer
calls `Player.stop()` on a failed resolve, so a bad/programmatic play URL cannot
interrupt unrelated playback. Regression tests: `test/test_playback_audit.py`;
see `docs/PLAYBACK-AUDIT.md`. Suite 403 → 409.
