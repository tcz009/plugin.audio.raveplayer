# Independent advisor re-review — Rave Player 3.9.56

**Review type:** independent, read-only. No device, no ADB, no Shield change,
no code edit, no push and no tag.
**Repo/worktree:** `raveplayer-worktrees/kodi-p2-3.9.56`
**Branch:** `fix/3.9.56` · **Base:** `d06adad` (`v3.9.55`) · **HEAD:** `1c40b8f`
**Patch:** `git diff d06adad..HEAD` — 26 files, 1351 insertions, 103 deletions.
**Review basis:** the P2 list in `docs/RELEASE-3.9.54-DEVICE-QA.md`, the 3.9.54
advisor findings in `docs/ADVISOR-REVIEW-3.9.54.md`, and the current code. The
prompt named `docs/QA-P2-REPRO`, but no file with that name exists in this
worktree, in `main`, or in any other worktree; the four device-QA P2s above are
therefore the authoritative reproduction list used here. This is a
documentation/process gap, not a code blocker.

---

## Verdict

**NO SHIP** for `1c40b8f`.

The hero, now-playing and cache/paging work is largely correct and well tested.
The download-cancel work is **not safe to release**: a duplicate/auto-cancelled
row can delete the file and index entry of the transfer that just completed,
and a queued cancel leaves a cancel sidecar that can make a later retry
immediately cancel and delete an already-completed copy. Both are data-loss
regressions in the exact QA P2-3 area this patch is meant to close. The
screen's own `DownloadQueue` also cannot perform the advertised completed-row
deletion because it is constructed without the plugin modules, so the
"completed same-key deletion" claim is only true on the headless owner path and
is still incomplete for queued rows.

There is no P0 (crash/security/credential) finding. The cache, paging and
instance-lock changes are sound on the primary Shield path; the remaining
instance-lock risks are fallback/race edges.

---

## Ranked findings

### P1 — Cancel can delete a successfully completed download (data loss)

**Where:** `script.raveplayer.ui/raveui/downloadqueue.py:561-572` (late-cancel
branch), `:579` (`_cancel_duplicates` on success), `:602-631`
(`_cancel_duplicates`), `:633-645` (`_finish(cancelled)` deletes completed),
`:310-338` (`_delete_completed` matches by key **or URL**).

**What happens**

Two active rows for one URL can exist with different queue keys (the screen
passes `entry.key`; two rooms/duplicate rows can produce different keys). The
normal success path is:

1. Row A finishes and writes its completed index entry/file
   (`downloads.download` does this before returning `ok`).
2. `_run_one` pops A, clears the cancel sidecar and calls
   `_cancel_duplicates(A, url)` (`:574-579`).
3. That marks the other active row B `cancel=True`, status `cancelled`, and
   writes a cancel sidecar for B (`:621-627`).
4. B's worker sees the cancel and returns `{"ok": False, "reason":
   "cancelled"}` (or, if the cancel lands after its last chunk, returns
   `{"ok": True}`).
5. Either `_finish(B, "cancelled", ...)` or the late-cancel branch calls
   `_delete_completed(B, url)` (`:567-572`, `:643-645`).
6. `_delete_completed` matches A's completed row **by URL** (`:330`) even
   though A has a different queue key, and calls `downloads.delete(A_key)`,
   which removes A's final file and index entry.

The user did not cancel A; A completed successfully. The duplicate handling
therefore deletes the only good copy.

**Reproduced** with the repo `DownloadQueue` and a deterministic two-row fake
(or real plugin) download:

```
start A -> ok, completed index key "hash"
start B -> same URL, different key
A returns ok -> _cancel_duplicates(B) -> B returns cancelled
_finish(B, "cancelled") -> downloads.delete("hash")
result: A index/file deleted; queue only shows B cancelled
```

The late-finish variant is the same: when B's `download()` returns `ok`
despite the cancel, `_run_one` sees `late_cancel` and deletes A's completed
entry before finishing B as cancelled.

**Also affected by the URL match:** cancelling a new attempt for a URL that
already has an old completed copy deletes that old copy by URL even though the
queue row key is different. That may be the intended "replace/remove duplicate"
behaviour in some cases, but it is not guarded against the successful-row case
above.

**Required fix (must be before tag):**

- Distinguish a **user cancel** (`DownloadQueue.cancel`) from an **automatic
  duplicate cancel** (`_cancel_duplicates`) and from a late cancel. Only the
  explicit user-cancel path may delete a completed copy; an auto-cancelled
  duplicate must never delete the completed row that caused the cancellation.
- Do not let a completed entry belonging to another queue key be removed by
  the duplicate cancellation. A completion/ownership check (the row that just
  returned `ok`) is needed before `downloads.delete`, not a bare URL match.
- Add regression tests for both variants: (a) B returns cancelled after A
  succeeds; (b) B returns `ok` after A succeeds while `late_cancel` is set.
  Assert A's file/index survive.

### P1/P2 — A queued-cancel sidecar survives and cancels/deletes a later retry

**Where:** `script.raveplayer.ui/raveui/downloadqueue.py:230-258` (`start` does
not clear the sidecar), `:267-307` (`cancel` writes it), `:659-669`
(`_load_store` marks cancelled but does not clear it), `:741-754`
(`_request_cancel`/`_cancel_requested`), `:633-645` (cancelled finish deletes).

**What happens**

Cancel a **queued** row (no worker has started, or the window queue is
`local_workers=False` and the owner has no worker for it):

- `cancel()` writes `key` to `download-queue.json.cancel` and saves the row as
  `cancelling`.
- The owner loads the row, converts `cancelling` to `cancelled`
  (`_read_store`), sees no active row, exits. No `_finish` runs, so the sidecar
  is never cleared.
- Later the user starts the same download key again. `start()` replaces the
  cancelled row but does **not** clear the sidecar. The new worker's
  `cancelled()` is immediately true; `downloads.download` returns
  `"cancelled"`; `_finish(cancelled)` calls `_delete_completed` and removes an
  existing completed copy (and the retry does not download).

**Reproduced** with a queued row, a window queue, then an owner queue and a
same-key retry:

```
window.cancel("k") -> sidecar ["k"], no worker, no completed delete
owner loads row -> status cancelled, owner.active() == False; deleted []
owner.start(same key) -> download called with cancelled() == True
_finish(cancelled) -> downloads.delete("hash") -> deleted ["hash"]
```

**Fix:** clear the sidecar for a row key at the start of a new `start()` (or
before writing the fresh row), and clear it when a queued/cancelled row is
terminal without a worker. `_cancel_duplicates` should not leave a sidecar for
a queued duplicate that will never run. Add a queued-cancel → retry test.

### P2 — Screen cancel cannot delete the completed index entry (no modules)

**Where:** `script.raveplayer.ui/raveui/window.py:517-519` constructs
`DownloadQueue(logger=..., store_path=..., local_workers=False)` with
`modules=None`; `script.raveplayer.ui/raveui/downloadqueue.py:318` checks
`self._modules is None` and returns without loading the lazy `modules`
property.

**What happens**

The primary screen path calls `LibraryScreens.cancel` →
`self.queue.cancel(key)`. The queue belongs to the window, so `_modules` is
`None`; `_delete_completed` is a no-op. This was reproduced directly:

```
window queue modules: None
cancel: True
_delete_completed(...): 0
```

If an owner worker is running for the row, its `_finish(cancelled)` path can
delete the completed entry (and has the P1 problem above). But for a **queued**
row there is no worker: the owner loads it as `cancelled`, exits, and the
completed copy/index remains. The release note's claim that
"`DownloadQueue.cancel(key)` ... deletes a completed index entry/file" is
therefore false for the normal screen queue in that case.

**Fix:** use the lazy `self.modules` property inside a `try` (or pass the
plugin namespace into the window queue / a deferred-delete sidecar the owner
executes). Add a test that constructs the queue exactly as `window.py` does
(no modules), cancels a queued row, and verifies a completed index entry is
removed. Whichever fix is chosen must preserve the P1 guard so it cannot
delete a successful row.

### P2 (fallback-only) — The no-fcntl heartbeat can declare a live screen stale

**Where:** `script.raveplayer.ui/raveui/window.py:47-51`
(`INSTANCE_HEARTBEAT_TTL = 3.0`), `:822-858` (fallback), `:911-917`
(`_touch_instance`), `:978-991` (heartbeat only from the open-screen loop).
`docs/RELEASE-3.9.56.md:194` records that the Live Radio first open is still a
synchronous `load_stations` on the GUI thread (6.3 s class).

On a platform where `fcntl` is unavailable (the fallback is explicitly for
Windows; it can also be reached if `flock` returns a non-EAGAIN error), the
only heartbeat is the `_touch_instance` call in the open-screen loop
(`:978-991`). If a synchronous action runs on that same add-on execution path
and blocks for more than 3 s, a second launch in that window sees
`pid == os.getpid()` and `age > INSTANCE_HEARTBEAT_TTL`, removes the live
marker and opens a second window. The documented 6.3 s Live Radio first open
is exactly that class of synchronous block. Whether Kodi delivers the action
on the same path as the loop is platform/Kodi-specific, so this is a
fallback-path risk rather than a demonstrated Shield bug; the OS flock path is
correct on the Shield. It nevertheless contradicts the general "no
double-instance window" claim on fallback platforms.

**Fix:** drive the fallback heartbeat from a separate timer/thread (or update
it from a GUI-idle callback) and/or raise the TTL past the worst-case
synchronous block; add a test that simulates an old marker held by a live
same-PID screen during a blocking call.

### P3 — Residual risks and hygiene

1. **Instance release race.** `_release_instance` removes the marker **before**
   closing the flock (`window.py:920-931`). A launch that opened the old inode
   and blocked on the lock can acquire the now-unlinked inode and run while a
   later launch creates a new marker and also acquires a lock. Leave the marker
   in place and close the descriptor (the next owner rewrites the PID), or
   revalidate the path after acquiring. Low probability, but the change is in
   the single-instance area and should be hardened.
2. **Live cache decode is not guarded.** `_cached_live`
   (`controller.py:1300-1327`) checks the payload is a dict but iterates
   `payload.get("stations")` without a try. A malformed value such as
   `{"stations": 5}` raises `TypeError` from `_open_live_room` and aborts the
   room; the page/library guards added by this patch do not cover it. The
   atomic store makes this unlikely, but the module's own "cache is never
   load-bearing" rule should include the live entry.
3. **Destructive invalidation covers one page only.** `_invalidate_library_cache`
   (`controller.py:1727-1747`) deletes the current page's cache entry. Removing
   a favourite or download can shift later pages; those pages still paint the
   old row from cache until their background refresh. Honest release wording
   would say "the current page", not the whole room.
4. **Status observation detects disappearance, not replacement.** The tick
   clears only when the player is gone (`controller.py:2133-2146`). If another
   add-on replaces the media while the app's status line is still latched, the
   app-owned "Now playing" text stays until navigation. This is narrower than
   QA P2-2, but the shared-player promise is not complete.
5. **2.5 s status grace vs 3.0 s live start grace.** Live start can take up to
   3 s in `_reconcile_live`, while `_clear_playback_status` clears at 2.5 s.
   A slow live start can lose the status line even though the live latch is
   still within its own grace. Align the two constants or re-mark on start.
6. **`docs/RELEASE-3.9.56.md` verification record.** The table lists two full
   runs (lines 158-159) and does not list the final `1c40b8f` doc commit. The
   `0b59f17` flock-hardening code landed after the earlier recorded run
   (commits are at 14:19-14:20 on 9 Nov), and the final table was edited in
   `1c40b8f`. I independently ran the suite **three times at HEAD** (1166 tests
   OK each: 21.5 s, 22.0 s, 21.4 s), so the code is green, but the release
   record should name the post-`0b59f17` run and preferably the third run.
7. **One new test is a false positive.**
   `test_malformed_cache_value_is_a_miss_not_a_room_abort`
   (`test/test_rave_screen.py:2733-2745`) writes the bad payload under
   `cache.key("page", "latest", 1, 50)` with the default empty `nav`, while
   `_cached_page` looks up `nav="list:p1"`. The lookup misses regardless of
   the decode guard, so the test does not exercise the guard. Write the bad
   value under the same `nav` key (and ideally use a value that makes
   `decode_page` raise, e.g. `{"rows": 5}`) and add a library equivalent.
8. **Prefetch is cancelled by initial focus.** `on_focus` now sets the
   cancellation event (`controller.py:342-347`). `window.onFocus` calls it when
   the list first receives focus, so the 2 s prefetch likely never runs on a
   normal launch. This is a performance regression relative to the original
   prefetch intent, not a functional failure; decide whether initial focus
   should count as user activity.
9. **`_downloads_hero` repeats three file stats per row**
   (`screens/library.py:1589-1601`). Fifty download rows mean ~150 `isfile`
   calls per paint. The existing `_neutral_hero` cache pattern could be reused.
10. **Missing QA repro doc.** Add `docs/QA-P2-REPRO` (or name the device-QA
    section explicitly in the release notes) so the next reviewer can match
    code to the exact device steps.

---

## Area-by-area assessment

### 1. Downloads hero — PASS

`_downloads_hero()` (`screens/library.py:1589-1601`) resolves
`screen-bed-1920x1080.jpg`, then the 1280×720 bed, then `fanart-screen.jpg`.
Both beds exist under `script.raveplayer.ui/resources/art/rave-screen/`, and
`fanart-screen.jpg` exists in the plugin art tree. It is used for active queue
rows (`_queue_row`), failed/cancelled queue rows, completed rows and
missing-file rows, so the FAVOURITES poster can no longer leak into Downloads.
Favourites (`:1331`) and About keep their own fanart; the existing
`FavouritesTests`/`AboutTests` assertions and the new Downloads hero test cover
the split. I found no other Downloads row construction path that needs the bed.

### 2. Now-playing / status clearing — PASS with residual risks

All app-owned playback entry points mark the status as owned:
`_handoff` (`controller.py:1041-1048`), `_play_collection` (`:1112-1118`),
`_play_tracks` (`:2890-2896`) and `_run_live_action` (`:1995-2000`). The 1 Hz
tick observes the player, records an active snapshot, and after a 2.5 s gap
with `playback.is_playing()` false clears `now_playing`, `CONTROL_STATUS`,
`_last_play_key`, `_handed_off` and the `rp_now` property
(`controller.py:989-1013`, `:2133-2146`). `on_stop` keeps its "Stopped."
feedback and resets the flags so the tick cannot overwrite it
(`:543-570`). All mutations are on the GUI/tick thread; no new timer or
worker was introduced, and the prefetch/refresh shutdown paths are unchanged.

The residual risks are the live-start grace mismatch, the fact that a
replacement player (another add-on starts new media without a gap) does not
clear the old status, and the fact that clearing is skipped while the 0.9 s
footer throttle is active. None loses data.

### 3. Cancel semantics — FAIL (see P1/P1/P2 above)

What is right:

- `cancel` marks every active duplicate for the same URL (`:290-303`), writes
  the sidecar, and preserves the original return contract (`active`).
- A late-finishing transfer is checked after `download()` returns and is
  converted to a cancelled row (`:561-573`).
- `_cancel_duplicates` stops a second worker after one row completes
  (`:602-631`).
- The plugin overlay has a real `CANCEL` button id 107 with
  `<defaultcontrol>107</defaultcontrol>` and `<onclick>SetProperty(rave_cancel,1)</onclick>`
  (`resources/skins/Default/720p/raveplayer-spinner.xml:76-85`), and
  `SpinnerWindow.iscanceled` checks both `_rave_cancelled` and the window
  property (`resources/lib/spinner.py:205-217`). `onAction` handles Back,
  Stop, Previous-menu and Parent-dir (`:469-476`). The download loop polls
  `cancelled()` before every chunk and the overlay closes in `finally`
  (`routes.py:2521-2552`).
- Unrelated URLs are not matched by `_delete_completed`; only the same key or
  URL is touched.

What is wrong:

- The URL match plus auto-cancel creates the P1 data-loss paths.
- The window queue has no modules, so its completed-row deletion is a no-op
  (P2).
- Queued cancels leave a sidecar that can cancel/delete a later retry (P1/P2).
- `_delete_completed` runs on the GUI thread in the window (when modules are
  supplied, e.g. tests) and on the owner worker; `downloads.json` has no
  inter-process lock around `_load_index`/`_save_index`/`delete`, so a
  concurrent delete and completion can still lose an update. The queue's
  store lock does not protect the plugin's downloads index. This is a
  pre-existing race that the new cross-process deletion makes easier to hit;
  it should be covered by the same ownership guard as the P1 fix.

### 4. Instance lock — PASS on the Shield path; fallback risk

- The marker is opened `O_CREAT|O_RDWR`, locked with
  `flock(LOCK_EX|LOCK_NB)` and the descriptor is held for the window's life
  (`window.py:861-907`). A second interpreter in the same Kodi process gets
  `EAGAIN` and is refused; the same-PID test passes.
- A stale marker left by a dead interpreter is healed immediately: the kernel
  released the lock, the new open acquires it, and `pid == os.getpid()` is
  treated as self (not a live owner) and overwritten (`:891-906`). The
  `INSTANCE_LOCK_FD` is closed/released on all `open_screen` exits
  (`:920-931`, `:995-999`).
- A live **different** PID from a pre-flock build is honoured while its marker
  is younger than the 10-minute TTL (`:896-900`), preserving compatibility.
- Non-EAGAIN `flock` errors fall back to the O_EXCL marker plus the same-PID
  heartbeat (`:882-890`, `:822-858`); the stale-fallback test passes.

Residual: the fallback heartbeat and the release race above. The fcntl path
itself is correct for the Shield/Android target, and I found no way for a
normal second launch to slip past a live flock.

### 5. Cache lifecycle / paging — PASS with low-severity gaps

- `PaintCache.load` now enforces `MAX_AGE_SECONDS` at read time and removes the
  expired file (`paintcache.py:399-409`); no write/prune is needed.
- `prune` enforces the 64 MiB total-byte budget oldest-first in addition to the
  240-entry and 30-day limits (`:472-525`). The tests cover the byte cap and
  oldest-first order.
- `_store_page`/`_store_screen` wrap encoding and storage (`controller.py:
  1241-1261`, `:1279-1298`); `_cached_page`/`_cached_screen` wrap decoding
  (`:1226-1239`, `:1263-1277`). A malformed `Page(total="oops")` is a miss and
  does not abort the room (the malformed-value test is weak; see P3).
- Page-2 focus uses `_content_offset()`/`_restore_offset()` rather than the
  nav-inclusive index (`:1427-1434`, `:1467-1469`); the page-2 shell and
  library tests pass, including a shrink to 10 rows where focus stays on
  content.
- The refresh matcher follows the painted page (`:1514-1524`,
  `:1636-1646`), and cache stores use the actual painted page, deleting the
  requested key when it differs (`:1250-1259`, `:1290-1296`). The clamped
  page-3 → page-1 test passes.
- Cache keys carry a nav token (`home`/`list`/`entry:<kind>:<source>`/
  `library:<route>:<query>`/`live`) plus the page and rows-per-page
  (`paintcache.py:92-104`, `controller.py:1211-1224`); the folder-vs-list test
  passes. Old 3.9.55 keys miss by version.
- Destructive remove/cancel/delete invalidates the current cached screen before
  the reload (`controller.py:1727-1747`, call sites `:1773-1791`, `:2838-2842`,
  `:2981-3000`), so the removed row does not flash back on the current page.

Low-severity gaps: only the current page is invalidated; `_cached_live` is not
guarded; the malformed cache test uses the wrong key; the 64 MiB cap is only
enforced every 16 writes (bounded overshoot, acceptable). No corruption or
unbounded growth was found.

### 6. Release hygiene — PASS on versions/artifacts; report needs correction

- Versions are consistent: plugin `3.9.56` (`addon.xml:4`), screen `3.9.56`
  and it requires plugin `3.9.56` (`script.raveplayer.ui/addon.xml:4,8`),
  resolver `1.1.0`, repository `1.0.0`; `repo/addons.xml` has the same four
  versions and `repo/addons.xml.md5` is
  `f49d755120937bace46200817886ef3b`, matching the file. Grep found no stale
  3.9.55 version references in active manifests/tests (only historical docs
  and comments).
- `sh scripts/check-repo-artifacts.sh` passes for all three add-ons.
- I compared every payload file in the committed repo plugin zip (144 files)
  and screen zip (105 files) against the worktree: all byte-identical. The
  repo resolver/repository zips are payload-identical to `v3.9.55` (timestamp
  only, as claimed). `dist` and `repo` plugin/screen hashes match the release
  notes:
  - plugin `4f174e4e2b6dc27b6521cea35b31a5e56353b3cfa06e143aa7c0ccdafc6dd7d2`
  - screen `0021366ffdabd07f209c33c478709ebdf1ac39173076fef53461e6a3f4c4086a`
- `git diff --check` is clean. No `.DS_Store`, `.pyc`, `__pycache__`,
  `.part`, `.tmp`, logs or test/docs trees are in the zips; no secret/token/
  debug value appears in the diff. The package payloads are current.
- `docs/RELEASE-3.9.56.md` is honest about scope and lists the deferred items
  (plugin-fallback SWR, resident UI, Live 6.3 s, advisor P2-10/11/12/13/14/18/
  20/21). Two wording/record issues remain: the QA P2-3 "Closed" row
  (`:178`) overstates what the code does (P1/P2 above), and the verification
  table (`:158-159`) records two runs and not the final commit; see P3.6.

---

## Verification performed

| Check | Result |
|---|---|
| `git diff d06adad..HEAD` review | 26 files, 1351 insertions, 103 deletions |
| Full suite at HEAD, run 1 | **1166 tests, OK** in 21.5 s |
| Full suite at HEAD, run 2 | **1166 tests, OK** in 22.0 s |
| Full suite at HEAD, run 3 | **1166 tests, OK** in 21.4 s |
| `git diff --check` | clean |
| `sh scripts/check-repo-artifacts.sh` | pass |
| Repo/plugin zip vs worktree | 144/144 payload files identical |
| Repo/screen zip vs worktree | 105/105 payload files identical |
| Resolver/repository zip vs `v3.9.55` | payload identical (timestamp rebuild only) |
| Version/manifest/md5 checks | pass |
| Zip junk/secret scan | no hits |
| Device/ADB/Shield | not used |

I also ran targeted reproductions outside the repo (temporary harnesses, no
repo changes):

- two active duplicate rows, A completes, B auto-cancels → `downloads.delete`
  was called for A's completed key;
- queued cancel in a window-style queue (no modules) → `_delete_completed`
  returned 0 and the owner loaded the row as cancelled with no delete;
- the same queued cancel followed by a same-key retry → the retry's
  `cancelled()` was true and `downloads.delete` removed the completed key.

These are the P1/P2 findings above, not hypothetical paths.

---

## Required before SHIP

1. Fix the P1 cancel ownership/auto-cancel problem; add the two duplicate
   completion tests.
2. Fix the queued-cancel sidecar lifecycle (clear on `start`/terminal load) and
   the window queue's missing modules so completed-row deletion actually works
   from the screen; add a screen-style queue test.
3. Either harden the no-fcntl heartbeat against a >3 s synchronous block or
   narrow the release claim for fallback platforms.
4. Update the QA P2-3 status in `docs/RELEASE-3.9.56.md` from "Closed" to
   partial until 1-2 are fixed, and record a post-`0b59f17`/third test run.
5. Correct the malformed-cache test key so the decode guard is actually
   exercised.

## Recommended but not blocking

- Harden `_release_instance` against the remove-before-close race.
- Guard `_cached_live` decode.
- Decide whether initial focus should cancel prefetch; if not, distinguish
  user D-pad movement from the first focus event.
- Cache the Downloads hero path per screen instead of statting three files per
  row.
- Align the 2.5 s status grace with the 3.0 s live start grace, and consider
  comparing player identity/content so an external replacement cannot leave a
  stale "Now playing" line.
- Invalidate all cached pages for a room on a destructive action, or
  explicitly document that only the current page is invalidated.

---

## Bottom line

The patch is close: hero, status clearing, cache lifecycle, pagination and the
flock path are implemented carefully and the full suite is green three times
at HEAD. It cannot ship while cancelling a duplicate can delete the file that
just downloaded successfully, and while the screen's cancel path cannot
perform the completed-row deletion it advertises. Fix the cancel ownership
model and the queue/sidecar lifecycle, rerun the suite, update the release
record, then this should be a straightforward **SHIP**.
