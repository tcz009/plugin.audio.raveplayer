# Legacy source loading — RaveTapePacks first (Kodi)

**Branch:** `perf/legacy-source-loading` (not merged, not released)
**Code commit:** `2acb41f` · **Report:** this commit (`docs/PERF-SOURCES.md` + `docs/bench/`)
**Priority:** RaveTapePacks.com (RTP); JungleTapes, Toronto, Moxser, Hardscore
and archive.org are measured as baselines.

## Outcome

- A Kodi **directory refresh of the RTP index** no longer re-parses the cached
  homepage: warm **14 ms → 3 ms** (p95 20 → 3). The parsed pack index is now a
  disk-cache entry (Kodi starts a new Python process per directory, so an
  in-process cache would not survive).
- RTP pack detail warm **16 ms → 4 ms**, first-track warm **14 ms → 2 ms**.
- Kodi has no RTP category page (see below); its single homepage fetch was
  already the only page. Cold RTP is therefore unchanged (~1 upstream page,
  ~395 ms in replay) — the win is the refresh path.
- Toronto cache hits no longer pay the 0.5 s courtesy gap:
  **504 ms → 1 ms** (index), **505 ms → 77 ms** (genre page, parse-bound).
- Moxser cache hits no longer pay the 1 s gap:
  **3,013 ms → 41 ms** (index), **1,003 ms → 7 ms** (detail).
- Every route now logs its wall-clock in debug:
  `route <mode> took <N> ms`.
- RTP page requests are single-flight per host with a 1 s gap (cache misses
  only), matching the web build and the site's ban history.

## Blocked: RaveTapePacks IP ban

This network is still blocked by RaveTapePacks. DNS resolves
`www.ravetapepacks.com` to `94.126.20.188`, but TCP 443 and 80 time out; the
committed audit in this repo also reports `ravetapepacks 0/0 pass (0%)`.
Therefore **all RTP numbers are a replay** of archived pages
(`test/fixtures/bench/`, provenance in `PROVENANCE.md`) with **350 ms simulated
upstream latency** per page. Replay reproduces bytes, parse and cache cost, not
TLS/redirects/live content. The baseline sources are live.

When the ban lifts:

```sh
python3 scripts/bench_sources.py --replay none --only rtp_index,rtp_all,rtp_pack
python3 scripts/audit_legacy_links.py --source ravetapepacks --limit 5
```

## Before → after

Wall-clock ms for the real plugin route (`routes.dispatch` with the test XBMC
stubs, real disk cache). `cold` clears the cache; 3 cold samples for RTP, 1 for
live baselines, 5 warm samples. p50/p95. "Parse" is everything that is not a
text fetch (route/UI work plus any JSON-level cache read).

### RTP (replay)

| Scenario | Rows | Cold p50 before | Cold p50 after | Cold p95 before | Cold p95 after | Warm p50 before | Warm p50 after | Warm p95 before | Warm p95 after |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| index (`legacy_index kind=event`) | 18 | 387 | 395 | 390 | 395 | 14 | **3** | 20 | 3 |
| all packs (`legacy_packs`) | 17 | 387 | 395 | 387 | 396 | 14 | **3** | 20 | 3 |
| pack detail (`legacy_pack`) | 1 | 389 | 396 | 397 | 407 | 16 | **4** | 21 | 4 |
| first track (`playable()`) | 1 | 385 | 395 | 386 | 395 | 14 | **2** | 19 | 2 |

The Kodi index route always used one homepage fetch, so cold does not move.
The warm delta is the persisted parsed index: the old code read the 200 KB body
from the cache and re-ran the regex pass on every refresh.

### Baselines (live)

| Scenario | Rows | Cold p50 before | Cold p50 after | Warm p50 before | Warm p50 after | Warm p95 before | Warm p95 after |
|---|---:|---:|---:|---:|---:|---:|---:|
| `jungletapes` index | 311 | 2,625 | 2,888 | 15 | 15 | 22 | 23 |
| `jungletapes` show | 2 | 984 | 955 | 5 | 4 | 5 | 5 |
| Toronto index | 5 | 907 | 517 | 504 | **1** | 505 | 1 |
| Toronto jungle page | 679 | 1,586 | 1,260 | 505 | **76** | 537 | 77 |
| Moxser index | 1,001 | 2,198 | 2,445 | 3,013 | **41** | 3,015 | 47 |
| Moxser detail | 1 | 1,753 | 816 | 1,003 | **7** | 1,005 | 8 |
| Hardscore index | 11 | 703 | 700 | 12 | 11 | 13 | 14 |
| archive.org list | 6 | — | 819 | — | 1 | — | 1 |
| archive.org item | 7 | 817 | 784 | 3 | 4 | 4 | 4 |

The archive-list before row used the wrong section key and produced 0 rows, so
it has no meaningful before value. Cold rows are live-network bound; the warm
Toronto/Moxser rows are the cache-hit fix.

## Kodi-specific findings

- **Re-parse on refresh**: Kodi invokes a new process per directory. The body
  cache already avoided the network, but every refresh re-ran `_music_refs()`
  over the 200 KB page. `_cached_parse()` now persists
  `{fingerprint, parsed}` under `legacy:rtp:packs:v1` for 6 h; the body is still
  read and fingerprinted so a changed page re-parses.
- **Throttle charged on cache hits**: `toronto._fetch()` and `moxser._fetch()`
  slept before checking the cache, so every refresh paid 0.5 s / 1 s. They now
  call `http.is_cached()` first.
- **No category pages**: `legacy_index` labels the four nav types but lists
  `legacy.packs()` for each; the add-on never fetches `?cat=`. Category-page
  caching is therefore a web-only fix (and the web report covers it).
- **Route wall-clock**: `routes.dispatch()` logs `route <mode> took <N> ms` at
  debug level after `end_route()`.

## Bounded concurrency / politeness

RTP page fetches use the same per-host single-flight slot with a 1 s gap as the
web build (`resources/lib/http.py`), entered only on a cache miss. Kodi routes
are single-threaded anyway, so this changes the *pattern* (never two RTP pages
open, polite gap) rather than the route's concurrency. No same-host worker pool
was added; independent sources already use the add-on's existing bounded pools
(`latest.merge`, `feeds.episodes_many`, `dnbradio.stream_urls`).

## Files changed (Kodi)

- `resources/lib/legacy.py` — parsed-page cache, `pack()`, one-decode display
  names, `_packs_from_html()` split out.
- `resources/lib/http.py` — per-host single-flight + 1 s gap for RTP;
  `is_cached()`.
- `resources/lib/cache.py` — `has()` (freshness without returning the value).
- `resources/lib/toronto.py`, `resources/lib/moxser.py` — throttle only on a
  cache miss.
- `resources/lib/routes.py` — `legacy_pack` uses `legacy.pack()`; route timing.
- `scripts/bench_sources.py` (new), `test/fixtures/bench/` (archived replay
  pages + provenance).
- Tests: `test/test_legacy_cache.py` (new, 5), `test/test_routes.py` (updated
  to mock `legacy.pack`), `test/test_cache.py` (+1 `has()`).

## Tests

```sh
cd raveplayer
python3 -m unittest discover -s test -v
```

- **498 tests OK** when the pre-existing untracked `* 2.*` duplicate files are
  excluded (`test_naming` fails on 39 art copies + 1 duplicate scan; those
  files are outside this branch and were not modified).
- The naming failures reproduce without this branch's code changes; they are
  untracked workspace artifacts (for example `test_entity_decode 2.py`,
  `docs/theme-2026/.../years 2.png`).
- The new cache tests use a throwaway `RAVEPLAYER_CACHE_DIR` per test.

## Reproduce

```sh
cd raveplayer

# RTP replay (same bytes, 350 ms simulated upstream)
python3 scripts/bench_sources.py \
  --only rtp_index,rtp_all,rtp_pack,rtp_first_track \
  --cold-samples 3 --samples 5 --json /tmp/rtp-kodi.json

# Everything, RTP replayed + baselines live
python3 scripts/bench_sources.py --cold-samples 1 --samples 5 --json /tmp/all-kodi.json
```

Raw output: `docs/bench/before-kodi.json`, `after-kodi.json`,
`before-rtp-replay.json`, `after-rtp-replay.json`.
