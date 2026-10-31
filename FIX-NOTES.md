# FIX-NOTES — "Latest" cascade fix (plugin.audio.raveplayer 3.9.8)

Date: 31 Oct 2026 · Version: **3.9.8** (was 3.9.7) · Scope: `resources/lib`, `test/`,
version/changelog, new zip. **Not deployed to any device.**

## Symptom (reported on Shield, Kodi 22.0-BETA1)

`Latest` opened with 56 rows, but every playable DNBRADIO row failed because the
DNB host was unreachable in the current network state. Kodi then treated the
folder as a playlist and auto-advanced down it item after item — the user saw an
endless "going down the page" loop, with the log repeating:

```
CCurlFile::Stat/Open ... Could not connect to server(7)
```

## Root cause

1. `latest_view()` rendered a **mixed folder** (tape packs = folders; podcast
   episodes and DNBRADIO shows = playable items) but finished the directory as
   content **`songs`**. Kodi's music content type is playlist-shaped: when a
   playable item in such a folder fails, Kodi advances to the next item instead
   of stopping — exactly the reported cascade.
2. DNBRADIO stream URLs were resolved **lazily**, only when a row was played
   (`dnb_play`). So every DNBRADIO row in `Latest` looked playable even when the
   host was unreachable; each one failed on play and handed Kodi the next row.
3. The failure path only notified + `setResolvedUrl(False)`, which does not stop
   a folder-built playlist from advancing.

## Changes

| File | Change |
|---|---|
| `resources/lib/dnbradio.py` | `stream_url(mix_id, timeout=25)` now accepts a timeout. New `stream_urls(mix_ids, timeout=RESOLVE_TIMEOUT, workers=RESOLVE_WORKERS)` resolves a batch concurrently via `concurrent.futures`, dedupes ids, drops failures and never raises. `RESOLVE_TIMEOUT = 3.0 s`, `RESOLVE_WORKERS = 8`. |
| `resources/lib/latest.py` | New `resolve_dnb_streams(items, timeout, workers)` — one concurrent batch for every DNB row in the merged list; returns `{mix_id: stream_url}` for the rows that resolved, and returns `{}` (logged) on an unexpected failure instead of breaking the screen. |
| `resources/lib/routes.py` | `latest_view()` resolves DNB URLs **before** rendering and **drops** rows that did not resolve (host unreachable / listen page changed). Resolved DNB rows play the build-time stream via `mode=play`. Directory ends with content **`files`** plus a final `End of list` row. New `_fail_playback()` helper; `play()` and `dnb_play()` now use it: notify, clear the music playlist (so Kodi cannot advance to the next row), `setResolvedUrl(False)`. `dnb_play()` also catches scraper exceptions and fails safely. |
| `resources/lib/ui.py` | New `end_marker()` — a visible terminator row with no URL and `IsPlayable=false`, so selecting it can never play or resolve anything. |
| `test/test_latest.py` | New `DnbStreamBatchTests` (unreachable ids dropped, dedupe, empty input, one bad worker) and `ResolveDnbStreamsTests` (batch wiring, no network for non-DNB lists, failed batch tolerated). |
| `test/test_routes.py` | New `LatestCascadeTests` (content=`files`, unreachable DNB row dropped, resolved row uses `mode=play`, non-playable end row) and `PlaybackFailureTests` (unresolved/raising `dnb_play` notifies, clears the playlist and reports failure; `play()` without a stream fails safely; success does not clear). |
| `test/stubs/xbmcplugin.py` | Records ListItem properties so the tests can assert the end row is not playable. |
| `addon.xml` / `changelog.txt` | Version 3.9.8 + changelog entry. |

## Behaviour after the fix

- `Latest` is a **files** directory: folders open, playable rows play
  individually, and a failed row can no longer make Kodi walk the list.
- DNBRADIO rows only appear if their stream URL resolved while the folder was
  built. When the DNB host is unreachable they are omitted; the rest of
  `Latest` (packs, podcasts) still shows.
- The list always ends with a visible, non-playable `End of list` row.
- Any remaining failed resolve is a dead stop: notification + no cascade. This
  also covers DNBRADIO favourites (`dnb_play` still resolves on demand there)
  and any other playable row.
- No new settings, no change to sources, artwork, labels or other routes.

Cost: opening `Latest` now makes up to 12 extra DNBRADIO listen-page requests,
concurrently (3 s timeout, 8 workers). Typically well under a second; worst case
roughly 6 s only if every request hits the timeout. If the host is down, the DNB
rows are dropped after that timeout instead of offering dead rows.

## Verification

```sh
python3 -m unittest discover -s test          # Ran 207 tests ... OK   (was 193)
python3 -m unittest test.test_latest test.test_routes -v   # Ran 60 tests ... OK
python3 test/run.py latest
# mode=latest  items=56  resolved=0  content=['files']    (dev Mac, 31 Oct 2026,
# network up; DNB listen pages resolved. 3.7 s total.)
```

Artifact build verified: `dist/plugin.audio.raveplayer-3.9.8.zip` contains
`addon.xml` version 3.9.8, the four updated modules, no `test/` and no
`__pycache__`; 40 files.

## Delivered artifact

- `dist/plugin.audio.raveplayer-3.9.8.zip` — 1,153,351 bytes, SHA-256
  `f8cb3ca06723eb78f2f9fa9c7eada8b5bd58b708c784aada4588434a8bc9289c`
- Not installed, pushed or deployed anywhere.

## Install risks / notes for the Lead

1. **`repo/` was not regenerated** (not part of this change set). Consequences:
   `repo/addons.xml(.md5)` still advertise 3.9.7, the tracked repo zip is still
   3.9.7, so repository-based auto-update will not offer 3.9.8, and
   `scripts/check-repo-artifacts.sh` will fail until you run
   `./scripts/build-repo.sh` and commit the regenerated `repo/` (per
   PUBLISHING.md). Manual zip install from `dist/` works now.
2. Same add-on id + higher version, so a manual zip install upgrades 3.9.7 in
   place; settings and favourites live in the add-on profile and are preserved.
   Kodi 22 beta may ask to allow installs from unknown sources / show an
   "unofficial" prompt for a zip — expected, and no different from earlier
   versions.
3. **First `Latest` open is slower when DNB is unreachable**: up to ~6 s worst
   case before the dead rows are dropped (previously the folder opened fast and
   then cascaded). With the host up, the smoke run was ~3.7 s for the whole
   route on a dev machine.
4. Kodi may show `Latest` in a files-ish default view now (content type
   changed from `songs` to `files`); the view is user-selectable and no setting
   was added. This is the intended visible difference.
5. `dnb_play` failure now clears the add-on's music playlist (intended: it
   breaks the cascade). Side effect: a failed resolve clears a user-built
   queue.
6. Requirements unchanged (`xbmc.python 3.0.1`, Kodi 20–22). New code is stdlib
   only (`concurrent.futures`), Python 3.9-compatible.
7. Rollback: reinstall `dist/plugin.audio.raveplayer-3.9.7.zip` (kept locally).

No secrets, addresses or private hostnames were added to any file, and nothing
was committed, tagged, pushed or deployed.
