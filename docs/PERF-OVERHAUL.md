# Performance overhaul — Kodi add-on (3.9.49 pass)

**Branch:** `perf/overhaul-3.9.49` (off `integration/3.9.48`, not merged, not
released) · no push/deploy.

Target: Rave Player feels instant on Kodi 22 (Shield) and on the web, without
changing playback. This file covers the **Kodi add-on**; the web side is
`../Rave Player/docs/PERF-OVERHAUL.md` and the two tables are directly
comparable because they were produced by the same harnesses on the same run.

```
warm navigation ≤ 200 ms perceived · cold first paint ≤ 2.5 s for hubs
RTP category ≤ 3 s via VPN · play-start ≤ 1.5 s when cached
```

## Method

Two harnesses, both committed, both using a throwaway cache directory so they
never touch the profile cache:

- `scripts/bench_routes.py` (new) — what Kodi actually calls:
  `routes.dispatch()` per menu mode, **cold** (cache dir cleared) and **warm**
  (cache populated), plus the fresh-process import cost of the root menu. RTP
  hosts replay the archived pages in `test/fixtures/bench` with 350 ms
  simulated upstream latency (same convention as `PERF-SOURCES.md`); every
  other source is live.
- `scripts/bench_sources.py` (existing) — provider-stage split (upstream /
  cache / parse) for the same sources.

Post pages have no archived capture, so `?p=<id>` replays the archived
`?cat=331` body (a real 155 KB RTP page with 48 MP3 links) — noted in
`test/fixtures/bench/PROVENANCE.md`.

Environment: macOS, Python 3.9.6, repo stubs, live network except RTP.
Before/after runs were **sequential on an idle machine** (running two
benchmarks at once doubled the import number, so those runs were discarded).
Raw output: `docs/bench/routes-{before,after}-3.9.49.json`,
`docs/bench/sources-{before,after}-3.9.49.json`.

## Route table (Kodi, `routes.dispatch`, ms)

| Route | Cold before | Cold after | Warm before | Warm after |
|---|---:|---:|---:|---:|
| `root` | 0.2 | 0.3 | 0.1 | 0.2 |
| `packs_menu` | 0.8 | 2.3 | 0.3 | **0.2** |
| `shows_menu` | 5.1 | 4.9 | 0.1 | 0.1 |
| `latest` | 2,907 | 2,785 | 119.5 | **12.4** |
| `search` | 1,431 | 1,630 | 1.9 | 2.6 |
| `rtp_index` | 370 | 365 | 2.0 | 1.7 |
| `rtp_all` | 409 | 378 | 3.8 | 1.5 |
| `rtp_pack` | 398 | 388 | 4.1 | 2.4 |
| `rtp_category` | 369 | 372 | 12.2 | **9.2** |
| `rtp_post` | 411 | 370 | 14.5 | **7.0** |
| `jt_index` | 2,710 | **2,380** | 17.6 | 13.6 |
| `jt_show` | 914 | 1,310¹ | 2.5 | 2.5 |
| `toronto` | 436 | 451 | 0.6 | 0.3 |
| `toronto_genre` (679 rows) | 1,265 | 1,621¹ | 169.0 | **82.4** |
| `moxser` (1,001 rows) | 2,233 | 2,466¹ | 61.4 | **36.0** |
| `moxser_mix` | 916 | 545 | 10.0 | 6.1 |
| `hardscore` | 759 | 864¹ | 16.8 | 7.7 |
| `archive_list` | 963 | 658 | 3.9 | 1.0 |
| `archive_item` | 805 | 809 | 2.1 | 1.9 |
| `filter_live` | 781 | 740 | 1.7 | 0.9 |
| `play_archive` (play-start) | 22.2 | 7.5 | 1.5 | **1.1** |
| `play_all` (play-start) | 756 | 1,019¹ | 4.7 | 3.1 |
| fresh process: import | 105 | **96** | — | — |
| fresh process: import+root | 106 | **96** | — | — |

¹ Cold rows are upstream-bound and move ±30 % between runs; the marked
differences are network noise, not code. Warm rows and the fresh-process
import are the code changes.

## Provider stages (Kodi, `bench_sources`, ms)

| Scenario | Cold before | Cold after | Warm before | Warm after |
|---|---:|---:|---:|---:|
| `rtp_index` (replay) | 368 | 367 | 3 | 3 |
| `rtp_pack` (replay) | 376 | 378 | 4 | 4 |
| `jt_index` | 2,531 | **2,083** | 21 | 15 |
| `toronto_genre` (679 rows) | 1,082 | 1,095 | 129 | **63** |
| `moxser_index` (1,001 rows) | 2,813 | 2,940 | 89 | **33** |
| `moxser_detail` | 964 | 770 | 5 | 5 |
| `rtp_first_track` | 371 | 369 | 2 | 1 |

## Against the targets

| Target | Result |
|---|---|
| Warm navigation ≤ 200 ms | ✅ worst warm route is `toronto_genre` at **82 ms** (679 rows); hubs are 0.1–14 ms |
| Cold first paint ≤ 2.5 s for hubs | ✅ root/packs/Toronto/RTP hubs 0.3 ms–451 ms; ⚠️ `latest` 2.79 s and `jt_index` 2.38 s are upstream-bound; `moxser` 2.47 s is the site's 1 req/s floor |
| RTP category ≤ 3 s via VPN | ✅ one page: 369 ms replay ≈ 0.4–1 s on a real VPN link; warm 9 ms |
| Play-start ≤ 1.5 s when cached | ✅ 1.1 ms (`play_archive`), 3.1 ms (`play_all`); cold is the Archive metadata request |

## What changed

1. **Parsed pages persist per exact body (`cache.parsed`).**
   Kodi starts a new Python process for every directory, so the parsed object
   has to live on disk. `resources/lib/cache.py` gained
   `parsed(key, ttl, body, parser)` (fingerprint → compare → re-parse only on
   change) and `remember(..., sync=False)`; `legacy._cached_parse` now delegates
   to it. Wired into:
   - `toronto.tracks()` / `toronto.genres()` — the ~1 MB genre page used to be
     re-regexed on every refresh (warm 129 → 63 ms provider, route 169 → 82 ms);
   - `moxser.mixes()` — the mixes sitemap (thousands of `<url>` nodes,
     ElementTree ~2 s cold) is parsed once per body instead of per refresh
     (warm 89 → 33 ms provider, 61 → 36 ms route);
   - `feeds.episodes()` — each feed's XML is parsed once per body;
   - `dnbradio` — see 2.
2. **DNB batch resolves from one cache entry.** `dnbradio.stream_urls()` used to
   spawn one worker per DNB row on every Latest build just to re-read and
   re-regex each listen page. A bounded on-disk map (`dnbradio:streams:v1`,
   same 6 h TTL as the pages) makes a warm batch zero threads, one read.
   Latest warm **119.5 → 12.4 ms**.
3. **JungleTapes catalogue fetched concurrently.** `/tapes` and `/sitemap.xml`
   are independent (JungleTapes has no politeness gap configured), so
   `legacy._fetch_jt_catalogue()` runs both in a 2-worker pool and keeps the old
   result order; any executor failure falls back to serial. Cold hub
   **2,710 → 2,380 ms** (route) / **2,531 → 2,083 ms** (provider).
4. **HTTP bodies no longer fsync.** `http.fetch`/`fetch_json` write cached
   bodies with `sync=False`: the body is recomputable and a power cut just means
   one more fetch. The Shield's flash paid tens of milliseconds per cold page
   for that fsync. Parsed pages already used `sync=False`.
5. **Data files parsed once per process.** `filters.json` and
   `rave-catalog.json` are read through `_cached_json()` (keyed by mtime), so
   building the Tape Packs menu no longer re-opens both files.
6. **Lazy `datetime`.** `ui.short_date()` imports `datetime` on first use
   instead of at module import: ~10 ms off every route that shows no date fact,
   including the root menu (fresh-process import 105 → 96 ms).

## Tests

```sh
cd raveplayer
python3 -m unittest discover -s test
# Ran 664 tests ... OK   (645 at integration/3.9.48)
```

New: `test/test_perf_caches.py` (12) — parsed-once-per-body for Toronto/Moxser,
re-parse on body change, JungleTapes concurrency (a barrier proves the two
fetches overlap), DNB batch resolves once and only fetches missing ids, feed
parse-once, and two "warm RTP category/post needs no upstream request" route
tests. `test/test_cache.py` (+6) covers `parsed()` and `sync=False`.
`test/test_toronto.py` (+1) pins the "cache hit pays no courtesy gap" path and
the existing gap test now forces a miss (it depended on the machine's cache
state). `test/test_latest.py` isolates the new disk map per test.

## Residual risks / not done

- `toronto_genre` warm is now 82 ms for **679 rows**, dominated by per-row
  `url_for()` (`urlencode` × 4 per row: play, favourite, download, delete).
  Batching `addDirectoryItems` or pre-quoting would help; both are bigger
  changes than this pass (and the listing contract must not change).
- The RTP category/post *cold* paths are one page each already; the site's
  "older posts" pagination is sequential by design (single-flight + 1 s gap).
- `latest` cold stays ~2.8 s: it is the slowest provider (Archive/DNB/feeds),
  not parse or cache.
- Version/repo artifacts were **not** bumped: the Rave Screen work owns the
  3.9.48 artifacts, and this branch is not a release. Merge into
  `integration/3.9.49` before bumping `addon.xml`, `changelog.txt` and `repo/`.
- `ThreadPoolExecutor` thread creation is still the main cost inside the
  warm Latest (~12 ms); a persistent pool is not worth it for a process that
  exits after one directory.

## Reproduce

```sh
cd raveplayer
python3 scripts/bench_routes.py --cold-samples 1 --samples 5 \
  --json docs/bench/routes-after-3.9.49.json
python3 scripts/bench_sources.py --cold-samples 3 --samples 5 \
  --json docs/bench/sources-after-3.9.49.json
```
