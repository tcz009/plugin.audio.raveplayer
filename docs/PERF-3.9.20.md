# Performance pass — 3.9.20 (Kodi)

Environment: macOS, Python 3.9.6, repo stubs, live network for Latest/pack
open; route times are in-process `routes.dispatch()` medians (5 runs unless
noted). Root process import/dispatch is measured in a fresh `python3 -c`
child (excludes the interpreter's own startup). `scripts/benchmark.py`
reproduces the route table.

| Metric | Before (3.9.19) | After (3.9.20) | Target | |
|---|---|---|---|---|
| Root, warm route | 0.0003 s | **0.0001 s** | ≤0.15 s | ✅ |
| Root, warm import+dispatch | 0.777 s | **0.080 s** | ≤0.15 s | ✅ |
| `packs_menu` warm | ~0.0001 s | **0.0001 s** | — | — |
| `shows_menu` warm | ~0.0001 s | **0.0001 s** | — | — |
| `radio_menu` warm | ~0.0001 s | **0.0001 s** | — | — |
| `downloads_menu` warm | ~0.0000 s | **0.0000 s** | — | — |
| Latest, cold | 10.6 / 20.1 s (2 runs) | **6.0 / 6.1 s** | ≤10 s | ✅ |
| Latest, warm | 1.57 / 1.74 s | **0.04 s** | ≤2 s | ✅ |
| Pack open, cached | 0.005 s | **0.003 s** | ≤3 s | ✅ |
| Pack open, cold | 1.45 s | 1.3–1.6 s | — | — |

Caveats:
- Full CLI process wall (`/usr/bin/time python3 test/run.py root`) is noisy on
  this Mac: baseline median **0.635 s**, after **0.18 s**. The 0.15 s target is
  met by the route and by import+dispatch (0.08 s); the full process wall adds
  Python/OS startup and file-cache variance and can sit above 0.15 s. The Kodi
  plugin thread is what the target protects, so this is called out rather than
  hidden.
- Latest cold is network-bound and varied by several seconds during the pass;
  both post-change runs stayed below 10 s. The route's 20 s wall budget and
  per-fetch clamps are unchanged, so the worst case is still bounded even if a
  source is down.
- `pack open, cached` got a few milliseconds “slower” (0.005 → 0.003–0.007 s,
  noise) and remains far under 3 s.

## What changed

1. **Parallel Latest.** `latest.merge()` now fetches the three independent
   sources (podcast feeds, Archive packs, DNB directory) in a bounded
   3-worker pool, retrieves results in source order (pre-sort order preserved),
   and falls back to serial on executor failure. The shared HTTP budget/cache
   are already thread-safe.
2. **DNB stream cache.** `dnbradio.stream_url()` caches listen-page resolutions
   for 6 h (`STREAM_TTL`), so warm Latest no longer re-resolves every DNB row.
3. **Import-time work.** `routes` no longer imports the provider modules at
   startup; they are lazy proxies loaded on first use (patch-preserving).
   `http` builds urllib/http.client/socket/gzip/zlib/opener and the cache
   module lazily; `socket` remains a lazy proxy for tests. `routes` defers
   `datetime`, `re`, `html`, `traceback`; `ui.plain()` compiles its regex
   lazily and skips it entirely when the label has no `[`.
4. **Hot paths / cleanup.** Spinner frame paths are `lru_cache`d; dead
   `http.probe_size` and `moxser.stream_urls` removed.
5. No URLs, labels, routes, settings or test count changed: **403 tests OK**.

## Residual risks

- Lazy imports move first-use cost to the first network route. Measured cold
  Latest includes it and stays under target; root warm avoids it.
- The lazy `http._OPENER`/`socket` proxies preserve the tested patch points,
  but the opener is constructed on the first real request.
- DNB stream pages now keep a 6 h cached resolution; if DNB changes a listen
  page, the old direct URL can be used for up to 6 h (it was re-resolved every
  warm call before). This is a deliberate warm-performance trade-off.
