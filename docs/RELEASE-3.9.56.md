# Release 3.9.56 — remaining Kodi P2s (device QA + advisor)

**Status:** release **prepared, not released**. Branch `fix/3.9.56` is local
only; `main`, the tags and the GitHub release are untouched. Nothing was
pushed, deployed or run on a device in this pass.

**Prepared:** 9 November 2026 · **Branch:** `fix/3.9.56`
**Base:** `main` @ `d06adad` (`3.9.55: advisor review and 3.9.54 device QA
evidence`, tag `v3.9.55`).
**Scope:** the four device-QA P2s from
`docs/RELEASE-3.9.54-DEVICE-QA.md` and the seven cheap advisor P2s selected
from `docs/ADVISOR-REVIEW-3.9.54.md`, plus version/changelog/docs/repo
artifacts. No other advisor P2 was attempted.

---

## 1. Versions

| Artifact | Version | Requires / notes |
|---|---|---|
| `plugin.audio.raveplayer` (`addon.xml`) | **3.9.56** | `xbmc.python` 3.0.1, `script.module.raveresolver` 1.1.0 |
| `script.raveplayer.ui` (`script.raveplayer.ui/addon.xml`) | **3.9.56** | `xbmc.python` 3.0.0, `plugin.audio.raveplayer` **3.9.56** |
| `script.module.raveresolver` | **1.1.0** | unchanged code and contract; rebuilt only because `repo/` is regenerated |
| `repository.raveplayer` | 1.0.0 | unchanged |
| `repo/addons.xml` | 3.9.56 / 3.9.56 / 1.1.0 / 1.0.0 | 4 entries; md5 `f49d755120937bace46200817886ef3b` |

The screen's `<import version>` is Kodi's minimum, not an exact pin; the
repository still installs the pair together.

---

## 1a. Commits

| Commit | Contents |
|---|---|
| `dee9150` | Source, tests and version/changelog/README/PUBLISHING updates for all A/B fixes |
| `2f2691f` | `docs/RELEASE-3.9.56.md` and the regenerated `repo/` artifacts |

---

## 2. Device-QA P2s

### QA P2-1 — Downloads room showed the FAVOURITES hero

Downloads rows (active queue rows, completed rows and missing-file rows) used
`fanart-favourites.jpg`, whose poster carries the FAVOURITES wordmark. They now
use the unlabelled screen bed (`screen-bed-1920x1080.jpg`, with the 1280×720
bed and `fanart-screen.jpg` as fallbacks). Favourites and About keep their own
posters. Regression: `DownloadsTests.test_downloads_hero_is_the_neutral_bed_not_favourites_art`,
plus the Favourites/About hero assertions in `test_screens_library.py`.

### QA P2-2 — stale "now playing" after an external stop

The 1 Hz footer tick now observes the shared Kodi player. When an app-owned
status line was set and the player disappears (JSON-RPC `Player.Stop`, another
add-on, end of queue), the controller clears `CONTROL_STATUS` and the
`rp_now`/now-playing property and paints the idle footer. A 2.5 s grace plus
`playback.is_playing()` prevents a just-started asynchronous `Player.play`
from being mistaken for a stop. In-app Stop keeps its "Stopped." feedback.
Regression: `ExternalStopStatusTests` (active player, external stop, pending
start, in-app stop).

### QA P2-3 — cancel semantics and plugin-path cancel/Back

* `DownloadQueue.cancel(key)` now marks **every active duplicate row for the
  same URL** as `cancelling` and writes the cancel sidecar for each.
* It deletes a completed index entry/file for the same key/URL, removing the
  completed duplicate that survived the 3.9.54 cancel.
* If a cancel lands in the same instant the transfer finishes, the worker
  removes the just-written completed copy and records the job as `cancelled`
  instead of leaving a completed row.
* When one download completes, other queued rows for the same URL are marked
  `cancelled` so a second row cannot stay queued/cancelling after the file
  completed.
* The plugin download overlay (`resources/skins/Default/720p/raveplayer-spinner.xml`)
  now has a real focusable **CANCEL** button (id 107, default control).
  `onControl` marks cancel; `onAction` treats Back, Stop, Previous-menu and
  Parent-dir as cancel. The download loop already polls `iscanceled()` before
  every chunk, and `download_start()` closes the overlay on cancel.

Regressions: the four new `DownloadQueueTests` cancel tests,
`DownloadRouteTests.test_download_start_cancels_when_the_overlay_reports_cancel`,
and the spinner action/XML tests.

### QA P2-4 — 10-minute instance lock after an unclean exit

Scripts run in Kodi's own process, so a marker containing Kodi's live PID could
not be distinguished from a live screen. The screen now keeps an exclusive
`flock` on `screen-instance.lock` for its whole life. The kernel releases that
lock when the owning interpreter dies, so a stale same-PID marker is healed
immediately. A live second interpreter (same or another PID) still fails to
acquire. Platforms without `fcntl` keep the O_EXCL marker and now use a
same-PID heartbeat (`INSTANCE_HEARTBEAT_TTL`) rather than the 10-minute TTL.
Regression: `SingleInstanceTests` same-PID stale, live same-process lock,
dead-PID and no-`fcntl` fallback tests.

---

## 3. Advisor P2s

### Paint cache age, byte cap and fail-soft encode/decode (P2-16/P2-17)

* `PaintCache.load()` rejects and removes an entry older than
  `MAX_AGE_SECONDS` at read time, with no write/prune needed.
* `prune()` enforces a 64 MiB total-byte cap (oldest first) as well as the
  240-entry and 30-day limits.
* `_store_page`/`_store_screen` wrap encode and store; `_cached_page`/
  `_cached_screen` wrap decode; base signatures are guarded. A malformed
  `Page(total="oops")` or a malformed cache value is a miss, never a room
  abort.

Regressions: `PaintCacheDiskTests` age/byte tests and
`StaleWhileRevalidateTests` malformed encode/decode tests.

### Page-2 focus clamp and clamped-page refresh matcher (P2-4/P2-5)

* A changed page now restores the absolute content offset
  (`_content_offset()`/`_restore_offset()`) instead of clamping the
  nav-inclusive on-screen index. Page 2 focus lands on the last content row,
  never on `PREVIOUS PAGE`.
* The refresh matcher and apply check use the page actually painted, not the
  requested integer, so a source clamping page 3 to page 1 no longer drops the
  valid refresh result.
* Cache stores now use the actual painted page and delete the requested-page
  key when they differ.
* Cache keys gained a navigation token (`home`, `room`, `entry:<kind>:<source>`,
  `list`, `search`, `library`, `live`, plus the page number) so a folder page
  and a list page cannot collide.

Regressions: `PaginatedRefreshTests` (shell and library page-2 focus, clamped
page refresh) and `PaintCacheDiskTests.test_nav_token_separates_a_folder_page_2_from_a_list_page_2`.

### Destructive actions invalidate the cached screen (P2-3)

`_invalidate_library_cache()` runs before `_reload_library()`/
`_reload_current()` after a successful remove favourite, remove queue row,
cancel download, or delete download. The removed row cannot flash back from
the paint cache during the background refresh.
Regression: `StaleWhileRevalidateTests.test_destructive_remove_invalidates_the_cached_screen_first`.

### Prefetch cancels on D-pad focus (P2-19)

`on_focus()` and `on_stop()` now set `_user_active` and set the prefetch
cancellation event, in addition to click/context/Back/horizontal input.
Regression: `PrefetchCancelTests`.

---

## 4. Verification

All commands were run from `raveplayer-worktrees/kodi-p2-3.9.56` on the dev
machine (Python 3.9.6). No device, network, ADB or Shield access was used.

| Check | Result |
|---|---|
| Full suite (run 1) | **1166 tests, OK** in 21.8 s |
| Full suite (run 2) | **1166 tests, OK** in 21.8 s |
| `./scripts/build-repo.sh` | plugin 3.9.56, screen 3.9.56, resolver 1.1.0, repository 1.0.0 |
| `./scripts/check-repo-artifacts.sh` | pass after committing the regenerated `repo/` |
| Plugin zip | `dist/plugin.audio.raveplayer-3.9.56.zip`, 9,097,250 B, SHA-256 `2e93b7be3ef1fa0b771a06e4a367cc2a41dbebfff7dad139610d262b7c095c39` |
| Screen zip | `dist/script.raveplayer.ui-3.9.56.zip`, 5,432,878 B, SHA-256 `fbcf10d7e985dc89a59e6bee03721bb133dbae8f2ae28214ebf5c41d0e140782` |
| Resolver zip | 1.1.0, 310,713 B (regenerated timestamp only) |
| Repository zip | 1.0.0, 853,389 B (regenerated timestamp only) |
| `repo/addons.xml` md5 | `f49d755120937bace46200817886ef3b` matches `repo/addons.xml.md5` |

`dist/` and `repo/` plugin/screen zips are byte-identical for this build.

---

## 5. P2 status

| Item | Status in 3.9.56 |
|---|---|
| QA P2-1 Downloads hero | **Closed** |
| QA P2-2 external-stop status | **Closed** |
| QA P2-3 cancel/duplicate/plugin-path | **Closed** for screen queue + plugin overlay cancel/Back; device re-test still required |
| QA P2-4 instance lock TTL | **Closed** (flock healing; fallback heartbeat) |
| Advisor P2-3 destructive flashback | **Closed** |
| Advisor P2-4 page-2 focus clamp | **Closed** |
| Advisor P2-5 clamped-page refresh matcher | **Closed** |
| Advisor P2-9 cache key nav semantics | **Closed** (navigation token + actual-page stores) |
| Advisor P2-16 cache age/byte cap | **Closed** |
| Advisor P2-17 cache encode guard | **Closed** |
| Advisor P2-19 prefetch focus cancellation | **Closed** |

### Left out of scope (documented, not attempted)

* **Plugin-fallback SWR** — the Classic lists are still not row-cached and
  still pay Kodi's Python process start and source fetch.
* **Resident UI** — deliberately deferred; first paint remains a normal script
  launch.
* **Live Radio 6.3 s first open** — still a synchronous `load_stations` on the
  GUI thread; only subsequent opens are cached.
* Advisor P2-10 (HEAD→Range download fallback), P2-11 (screen resolver
  downloads), P2-12 (invalid service URL), P2-13 (no shipped provider source),
  P2-14 (perf-table claims), P2-18 (`ROUND_FACE`/`notify` context), P2-20
  (service metadata/loopback base) and P2-21 (resolver cache pruning) are
  **not** part of this patch. Advisor P2-1/P2-2 and P2-6/P2-7/P2-8/P2-15 were
  closed in 3.9.55.

---

## 6. Device verification still needed

The code paths above are unit-tested offline only. Before shipping, a device
pass should re-check:

1. Downloads (fresh and cached) shows its own neutral hero.
2. JSON-RPC `Player.Stop` clears the status line within ~3 s while the footer
   goes idle; in-app Stop still says "Stopped.".
3. Cancel on an active duplicate removes the completed copy; a plugin-path
   download shows the CANCEL button and Back stops it; no second completed row
   appears.
4. Kill/close the screen uncleanly, then relaunch immediately: no "a screen is
   already open" refusal and no 10-minute wait.
5. Page 2 refresh after a shrink keeps focus on content; page-2 cache hit
   after a source clamps still refreshes.

No data migration and no settings schema change. Rollback is the 3.9.55
plugin + screen pair from `dist/`/`repo/`; the resolver module can stay
installed at 1.1.0.

---

## 7. Rollback

Install `plugin.audio.raveplayer-3.9.55.zip` + `script.raveplayer.ui-3.9.55.zip`
(repository history or the `v3.9.55` tag) and restart Kodi. Paint-cache entries
are version-keyed, so 3.9.55 simply misses 3.9.56 entries and rebuilds its own.
`screen-instance.lock` may be left behind by an unclean exit; 3.9.55 still
honours its old PID/TTL logic, and deleting the one marker file is safe when no
screen is open.
