# 3.9.52 performance pass — stale paint, lazy imports, instant Back

Branch `perf/3.9.52` off `main` 1c0b9da. Plugin 3.9.52, screen 3.9.51.
Device: Nvidia Shield, Kodi 22.0 beta (Piers), Estuary. Playback was stopped
and Home was left in the foreground after every measurement run.

The owner's complaint was that the last Kodi build "felt slow". The work was
ordered so the thing the user touches first — opening a room — changed first,
and every step was measured on the Shield through JSON-RPC 8080 and the Kodi
log (`[script.raveplayer.ui]` INFO lines written for this pass).

## What changed

### 1. Stale-while-revalidate paint (`raveui/paintcache.py` + controller)

* The controller stores the **last successful painted page** per target
  (room key, folder `Entry`, search route/query, live stations) in
  `special://profile/addon_data/script.raveplayer.ui/paint-cache/`.
* Keys are versioned by schema, screen version, plugin version and
  rows-per-page, so an upgrade can never paint rows built by old code.
* On open: read one small JSON file, `_apply_page` + `_render_page`, set the
  quiet `UPDATING · showing saved list` status, then start a **daemon
  `BackgroundTask`**. `tick()` polls it; the page is repainted only when the
  row signature changed (`SAVED LIST · up to date` otherwise). Back cancels
  the refresh immediately and never waits.
* Applied to: Latest, Toronto (hub + genre + folder pages), JungleTapes shows
  and show pages, RaveTapePacks hub/index/category/post, Live Radio, Search,
  Favourites, Downloads, About and every paged folder. Root/Classic root are
  static two/ten-row menus and have nothing to revalidate.
* Unknown/non-serialisable row types are never written: a miss just loads the
  old way. Empty/error results are not stored, so a source hiccup cannot
  poison the paint cache.

### 2. Lazy imports + idle prefetch

* `pluginbridge.load_plugin()` used to import all twenty plugin data modules
  during window init. It now imports only `plugin.kodi` (needed to repair the
  plugin add-on context before any module caches `DEFAULT_FANART` etc.) and
  loads the rest on first attribute access, guarded by a lock.
* Local harness (`PYTHONPATH=test/stubs:.`): `load_plugin()` **322 ms → 50 ms**
  and **1 module imported instead of 20**; `latest` costs 56 ms only when
  first used.
* After the first paint, an idle, cancellable prefetch (2 s grace, stops the
  moment the user acts, checks closed/busy/refresh between items) loads Latest
  and the RaveTapePacks "By Event" index and writes both to the paint cache.
  Device log: `prefetch 'latest' rows=50` and `prefetch Entry(...rtp-index-events...) rows=50`.

### 3. Instant Back

`RaveScreenWindow.close()` no longer runs `ActivateWindow(Home)` twelve times
with a 200 ms sleep (worst case 2.4 s). It fires once, waits up to 200 ms for
window id 10000, and retries once (300 ms) only when the switch was refused.
Measured `back-home` line: **28–79 ms**.

### 4. Resident UI — deferred on the timebox

Not attempted. 1–3 are solid and the resident-service variant (a preloaded
window/data service) is the one most likely to be flaky on Kodi 22 beta; a
half-working always-on service would be worse than the 560–630 ms first paint
we now have. It stays a documented follow-up, not a reverted experiment.

### 5. Per-row work

* `RaveData._art()` / `_neutral_hero()` now resolve art once per process;
  fifty rows share a handful of sticker names and each miss was a filesystem
  `stat` on the Shield.
* `handoff.platform_kind()` is `lru_cache`d (the screen is resident, so the
  same stream URLs recur across rooms).
* `routes.art()` is cached per plugin process (fixed art directory).
* ListItem construction/`setInfo` remains the per-row floor; no behaviour was
  dropped to chase it (the video plot tag is still set because Estuary reads
  `ListItem.Plot` from it).

## Device numbers

Method: `Files.GetDirectory` over JSON-RPC for plugin routes (client round trip,
three samples, median); screen rooms via the `[script.raveplayer.ui]` INFO lines
the controller writes (`in N ms` excludes event dispatch; `first paint` is
script-start → rows painted). Paint-cache-cold runs delete only the derived
paint-cache directory, never settings or userdata.

| Path | Before (3.9.51/3.9.50) | After (3.9.52/3.9.51) |
|---|---|---|
| App launch → first paint (script-internal) | not instrumented; external 1.19–1.33 s | **556–629 ms** internal; 0.99–1.57 s external (Kodi window activation dominates) |
| Latest open, paint cache warm | ~0.4–0.6 s typical; up to 1.9 s cold | **91–126 ms** |
| Latest open, no paint cache (first ever / after expiry) | ~0.9–1.9 s (source fetch) | 1904 ms first load; 126 ms on the next open |
| Toronto hub | 467 ms (external baseline) | **51 ms** warm / 166 ms first |
| Toronto genre (678 tracks / 14 pages) | **4.27 s** (baseline log) | **85 ms** warm; 2673 ms first |
| RaveTapePacks hub | 392–428 ms | 188 ms first |
| RTP "By Event" index (50 categories) | 571 ms (plugin route) | 171 ms first |
| RTP category page | 469–2524 ms (plugin route) | 153 ms first |
| Live Radio | not measured before | 52 ms warm; **6.3 s** first (radio-browser resolve) |
| Back app → Kodi Home | 12×200 ms loop, worst 2.4 s | **28–79 ms** |
| Play start (Toronto track) | 742 ms (external baseline) | 62 ms (warm stream) |
| Plugin root route (process floor) | 336–371 ms | 294–304 ms median 304 ms |
| Plugin Latest fallback | 729 ms warm / 2.5–4.6 s first (3.9.51 samples) | median 787 ms (no regression) |
| Plugin search fallback | **>90 s timeout / no rows** | unchanged — still a >1 s path |

Remaining >1 s paths (honest list):

* First-ever Toronto genre page (~2.7 s), first Latest after cache expiry
  (~1.9 s), first Live Radio (~6.3 s): these are source calls; the paint cache
  makes every subsequent open <150 ms.
* Plugin fallback lists still pay Python process start (~300 ms) and, for
  RTP/Archive, the upstream fetch on first use. The app shell is the primary
  surface (3.9.51) and is the one with the row-list paint cache.
* Plugin search fallback times out (>90 s) — pre-existing, unrelated to this
  pass; the screen's Search room is the supported search path.

## Screens

Device captures (Shield 1080p, downscaled to 1280 px) are in
`docs/perf-3.9.52/`:

* `home.png` — Home after the lazy-import change: all eleven rooms painted
  without importing any data module beyond `plugin.kodi`.
* `latest-painted.png` — Latest opened from the prefetched paint cache; the
  quiet `SAVED LIST · up to date` status is visible bottom-left after the
  background refresh completed with unchanged rows.

## Tests

`python3 -m unittest discover -s test` → **970 tests OK**.

New (3.9.52) coverage:

* `StaleWhileRevalidateTests` — cache hit paints before any source call;
  refresh repaints changed rows; unchanged refresh does not repaint; refresh
  failure keeps the saved page; Back during refresh cancels without waiting or
  repainting.
* `PaintCacheDiskTests` — page/track round-trip, version bump invalidates,
  corrupt entry is a miss.
* `LazyPluginImportTests` — `latest`/`legacy` are absent from `sys.modules`
  after `load_plugin()` and appear only on first use.
* `InstantBackTests` — one `ActivateWindow(Home)` when Kodi switches, two when
  it refuses.
* `test_rave_screen` manifest expectation bumped to screen 3.9.51; the
  committed-repo test passes after `scripts/build-repo.sh`.

## Rollback

* Device: reinstall the 3.9.51 plugin + 3.9.50 screen zips and restart Kodi;
  paint cache lives in `addon_data/script.raveplayer.ui/paint-cache` and can be
  deleted (or ignored — new keys are versioned).
* Repo: `git revert` the 3.9.52 commits on `perf/3.9.52`; no data migration and
  no settings were added.
* No web changes; resolver work is untouched.
