# Pagination and test determinism — 3.9.50 (integration pending)

Branch `feat/pagination-3.9.50` (worktree `raveplayer-worktrees/pagination-3.9.50`),
based on `integration/3.9.49` @ `49d3e3c`.  No version bump: the integration
release was pending when this branch was cut.

## What changed

- One pager for every list that can exceed a page. `routes._paged()` slices a
  known collection, `_page_header()` draws the first-row
  `Page N of M · X items`, and `_page_nav()` draws `Previous page` / `Next page`
  rows (hidden at their bounds). The `results_per_page` setting is now a
  25/50/100 choice, default 50.
- Covered lists: Toronto genres (679/2,640), Moxser (1,001), JungleTapes shows
  (310), Rave Nights (55), downloads, live radio, podcast feeds, RaveTapePacks
  indexes/categories/all-packs/posts/packs, Archive sections/search/year/
  filters/packs, Latest and favourites. JungleTapes no longer hard-codes 50.
- Track numbers are absolute (`archive_item` page 2 starts at 51; Toronto,
  RTP and JungleTapes detail rows do the same).
- Play all / Shuffle stay whole-collection. `play_all` still feeds
  `archive.audio_files()` in full; `play_all_collection` resolves the complete
  Toronto/RTP/JungleTapes list and starts at the absolute `start` index.
- Listing cost is O(page), not O(collection): the visible window is sliced
  before row dictionaries are built.

## Test matrix (this host, macOS, Python 3.9.6)

Kodi (`python3 -m unittest discover -s test`, 715 tests):

| Run | Before this branch | After |
|---|---|---|
| Plain ×3 | 696/696 ×3 (green) | 715/715 ×3 (green) |
| Temp `RAVEPLAYER_CACHE_DIR` ×3 | 696/696 ×3 (green) | 715/715 ×3 (green) |
| Shuffled module order ×3 | **failed 1/3** (EntryPointGuardTests) | 715/715 ×3 (green) |

Web (`pytest test` offline, `pytest test_e2e` serial) lives in the sibling
`rave-player-worktrees/pagination-1.6.53` worktree; see its
`docs/PAGINATION-AND-FLAKES.md`.

## Flake found and fixed

`test_compat.EntryPointGuardTests` did `import default`. `test_rave_screen`
inserts `script.raveplayer.ui/` at the front of `sys.path`, so when that file
ran first `import default` resolved to the *screen* add-on's `default.py`
(no `routes` attribute) and the test failed. The suite only failed under a
shuffled order: seeds 1 and 3 passed, seed 2 failed. The test now loads the
plugin entry point by path with `importlib.util.spec_from_file_location`, so
module discovery order cannot change what it tests.

The suite also had a shared global cache: `cache._directory()` fell back to
`/tmp/raveplayer-test-profile/cache` for every run, so a warm cache from an
earlier run could satisfy a later test. `test/stubs/xbmcaddon.py` now creates a
unique `RAVEPLAYER_CACHE_DIR` per test process and removes it at exit (an
explicit harness value still wins, which is what the temp-cache matrix uses).

## Commands

```sh
cd raveplayer-worktrees/pagination-3.9.50
python3 -m unittest discover -s test                 # plain
d=$(mktemp -d); RAVEPLAYER_CACHE_DIR="$d" python3 -m unittest discover -s test
python3 scripts/bench_pagination.py --samples 5 --json /tmp/kodi-page.json
```

Shuffled order (used to find the entry-point flake):

```sh
python3 - <<'PY'
import os, random, sys, unittest
root = os.getcwd()
sys.path[:0] = [os.path.join(root, "test", "stubs"), root, os.path.join(root, "test")]
mods = sorted(f[:-3] for f in os.listdir("test") if f.startswith("test_"))
random.Random(11).shuffle(mods)
suite = unittest.TestSuite()
loader = unittest.TestLoader()
for name in mods:
    suite.addTests(loader.loadTestsFromName(name))
raise SystemExit(0 if unittest.TextTestRunner().run(suite).wasSuccessful() else 1)
PY
```

## Timings (hermetic host render, not a device)

`scripts/bench_pagination.py` replaces every source with a deterministic list,
so these numbers measure paging/row building, not network. Each page also has
the header/nav/Back rows, hence `rows` > 50.

| List | Page | Rows | Cold ms | Warm p50 ms | Warm p95 ms |
|---|---|---|---|---|---|
| Toronto 2,640 | 1 | 53 | 38.5 | 4.1 | 5.3 |
| Toronto 2,640 | 53 | 43 | 4.1 | 3.4 | 3.5 |
| Moxser 1,001 | 1 | 53 | 33.0 | 1.3 | 1.4 |
| Moxser 1,001 | 21 | 4 | 0.4 | 0.4 | 0.4 |
| JungleTapes 310 | 1 | 53 | 1.3 | 1.3 | 1.3 |
| JungleTapes 310 | 7 | 13 | 0.4 | 0.3 | 0.3 |
| Rave Nights 55 | 1 | 53 | 0.9 | 0.7 | 0.7 |
| Rave Nights 55 | 2 | 8 | 0.1 | 0.1 | 0.1 |
| Downloads 120 | 1 | 53 | 0.9 | 0.9 | 0.9 |
| Downloads 120 | 3 | 23 | 0.9 | 0.4 | 0.4 |
| Live radio 500 | 1 | 52 | 16.2 | 9.5 | 9.6 |
| Live radio 500 | 10 | 52 | 10.6 | 9.2 | 9.3 |
| Pack 1,645 | 1 | 52 | 20.0 | 14.9 | 14.9 |
| Pack 1,645 | 33 | 47 | 13.5 | 13.1 | 13.1 |
| Search 2,400 | 1 | 52 | 16.0 | 7.7 | 7.8 |
| Search 2,400 | 48 | 53 | 7.6 | 6.9 | 7.5 |

`Cold` is the first call for that route in the process (lazy imports included);
`warm` is the next five calls. There is
no Kodi device in this environment, so device cold/warm network timings are not
claimed here; run `python3 test/run.py <mode>` on the Shield to capture those.

## Repeatability

Full suite was run 9 times after the fix (3 plain, 3 temp-cache, 3 shuffled)
with 715/715 every time. No deploy, push, or version bump was performed.
