# Rave Player 3.9.74 — playback guard, favourites and resolver pacing

Offline, code/docs only. No device, ADB, push, tag or deploy. Worktree
`raveplayer-worktrees/kodi-phase2`, branch `feat/3.9.74`, base `7833574`
(v3.9.73).

Versions: **plugin 3.9.74**, **screen 3.9.74**, **resolver module 1.1.2**
(`plugin.audio.raveplayer` requires `script.module.raveresolver 1.1.2`).

## What changed

### R4 — absolute `Track.path` no longer bypasses the play-time DNS guard

3.9.73 wrapped every **fresh** web row in `mode=web_play`, but the full-screen
app still trusted any non-empty `Track.path`: a stale paint-cache entry (from
the 3.9.67–3.9.71 builds) could carry the raw absolute stream and hand it
straight to Kodi.  `PlaybackService` now classifies the path before it reaches
the player:

- local downloads (`local=True` / `file://`) stay local;
- `plugin://` hand-off and existing `mode=web_play` paths pass through
  unchanged, so a row is never double-wrapped;
- a relative `/api/ezgarage|ukraves/.../stream` path goes through
  `mode=web_play` and is signed at play time;
- an absolute http(s) path gets an app-side `is_public_http_url_dns()` check
  (injectable for tests).  Private/unresolvable hosts raise a clean
  `ValueError`; public hosts are routed through `mode=web_play`, which repeats
  the guard and exempts the operator's own web base.

`play_collection` applies the same policy per track and skips a stale private
entry instead of poisoning the whole Play all queue.  Favourites use the same
`PlayItem` path, so a saved stream keeps working.

Tests: `test/test_rave_screen.py` (`PlaybackServiceTests` /
`PlaybackPolicyTests`) cover public wrapping, private refusal, relative signed
paths, no double-wrap and Play all.

### R5 — stale `/file` favourite is a clean remove row

The app's Favourites screen still treated `/api/ezgarage/.../file` and
`/api/ukraves/.../file` as session streams and wrapped them in `web_play`, even
though the web service only accepts `/stream`.  The branch now matches
`/stream` only; a `/file` row is a non-playable `ACTION_REMOVE` row with no
plugin wrapper, so the user can remove it or save the working row again.
Tests: `test/test_screens_library.py`.

### Resolver — per-domain pacing (1.1.2)

New `resolver/ratelimit.py` mirrors the web resolver's bucket:

- one token bucket per **registrable domain** (`n1.mediafire.com` and
  `download1.mediafire.com` share `mediafire.com`; Google hosts share
  `google.com`), 60/min with a burst of 10;
- LRU-bounded to 256 domains, injectable monotonic clock;
- a provider 429 records the bounded `Retry-After` and blocks both the next
  adapter attempt **and** the NAS service fallback for that domain.  The
  manager sets `fallback=False` on the surfaced `RateLimited`, so one
  transport cannot retry around another's back-off;
- direct audio (no provider page and no network fetch) is not gated, keeping a
  large play-all fast.

### Resolver — `/api/resolve` result cache + single-flight

`ServiceResultCache` caches successful `Resolution` objects keyed by the
requested URL.  The TTL is 300 s, clamped to the result's own
`expires`; expired results are dropped on read, and errors (including 429) are
never cached.  The cache is LRU-bounded to 256 entries.  Concurrent identical
resolves share one in-flight service request; different URLs are not
coalesced.  The manager wires one cache into `ServiceClient`.

### R3 — Drive/MEGA 429 typed

Drive's 429 (on either the initial probe or the confirm-form probe) and a MEGA
native adapter's HTTP-429 exception now map to `RateLimited` with a bounded
`Retry-After` (numeric or HTTP-date, maximum 120 s).  The service client
already mapped 429; the manager records that back-off in the shared limiter.

## Tests

```sh
python3 -m unittest discover -s test        # full suite, twice
python3 -m unittest test.test_resolver_module test.test_resolver_service \
  test.test_resolver_adapters test.test_resolver_mega \
  test.test_resolver_ratelimit test.test_resolver_servicecache \
  test.test_rave_screen test.test_screens_library
```

All tests are offline (Kodi stubs, fake DNS, fake HTTP, injectable clocks).
New coverage: registrable-domain grouping, burst/refill, 429 blocking,
LRU bounds, service cache TTL/expiry clamp/LRU/single-flight/error handling,
Drive and MEGA 429 typing, app public/private/relative/no-double-wrap playback,
and the stale `/file` favourite row.

## Build

```sh
./scripts/build.sh
./scripts/build-repo.sh
./scripts/check-repo-artifacts.sh
```

`repo/` is regenerated with plugin 3.9.74, screen 3.9.74 and resolver 1.1.2.

## Residual (not in this phase)

- No device/ADB validation; playback, Shield and Piers checks are a separate
  release step.
- The service cache is in-memory and per process (Kodi restarts clear it); the
  adapter cache remains the on-disk signed-URL store.
- The rate limiter gates resolution attempts, not each adapter HTTP request
  (e.g. a Drive confirm form is two requests under one token).  It is a
  provider-protection bucket, not a byte/request quota.
- Classic `fav_list` still rebuilds every saved stream as `mode=play`; only
  the app's `/file` branch changed.  A follow-up can give Classic the same
  same-origin `web_play` routing.
