# Independent advisor review — Rave Player 3.9.57

**Review type:** independent, read-only. No device, no ADB, no Shield change,
no tracked edit by the reviewer, no push and no tag. The only write by the
reviewer is this untracked report. The reproductions below are temporary
harnesses outside the repo.
**Repo/worktree:** `raveplayer-worktrees/kodi-p2-3.9.57`
**Branch:** `fix/3.9.57` · **Base:** `1c40b8f` (3.9.56) · **HEAD:** `b5fd460`
**Patch:** `git diff 1c40b8f..HEAD` — 16 files, 682 insertions, 15 deletions
(34 changed lines in `downloadqueue.py`, 116 lines of new tests, the rest
manifests, repo artifacts and docs).
**Review basis:** `docs/ADVISOR-REVIEW-3.9.56.md`, `docs/RELEASE-3.9.57.md`, the
3.9.54 device-QA P2-3 section and the current code.

> **Worktree note:** while this review was running, the worktree acquired an
> uncommitted 47/25-line change to
> `script.raveplayer.ui/raveui/downloadqueue.py` that was **not** authored by
> this reviewer. It is not part of `git diff 1c40b8f..HEAD` and is not covered
> by the verdict below. See “Concurrent worktree delta” at the end; the report
> reviews the committed `b5fd460` as requested.


---

## Verdict

**NO SHIP** for `b5fd460`.

The headline **data-loss P1 is fixed**: completed rows are now deleted by key
only, so an auto-cancelled duplicate can no longer remove the file/index entry
of a row that finished successfully. I could not construct a production path
where `_delete_completed` removes another job's completion.

The patch does **not** deliver the rest of what it claims:

1. **The screen queue still cannot delete its completed index row.** Queue keys
   are screen row keys (`toronto:<genre>:<md5-10>`); plugin completion keys are
   `sha1(url)[:16]`. Key-only matching therefore never matches in production.
   The 3.9.56 advisor P2 and the release-note claim ("a screen cancel removes
   its own file/index row") remain false. The new test fakes key equality.
2. **A queued-row cancel with a live headless owner is never terminalized.**
   The row stays `cancelling` forever, `queue.active()` stays true so the owner
   process never exits, and a retry of the same key is refused. This is
   pre-existing, but the 3.9.57 notes claim the queued-cancel lifecycle is
   fixed; it is only fixed when a *new* owner process loads the store.
3. **The sidecar durability claim is not safe.** The window `_load_store`
   clears a sidecar for a row it infers terminal *without* persisting that
   status, and the owner clears the sidecar *before* saving the store. A crash
   or a failed store write can therefore resurrect a cancelled row.
4. **The adversarial tests are weaker than the release note says.** One
   directly exercises a worker that crashes on a missing `plan()` method and
   never downloads; the "lazy modules" test bypasses the lazy hook and passes
   the 3.9.56 code; the persisted-status path and the advisor-required
   late-finish cross-row case are untested.

There is no P0 (crash/security/credential) finding. Normal download, complete,
completed-row delete and retry paths pass the existing suite; the instance
lock/heartbeat and progress code are untouched by this patch.

---

## Ranked findings

### B1 — P1 (release blocker): screen cancel still cannot delete its completed row

**Where:** `script.raveplayer.ui/raveui/downloadqueue.py:312-345` (`_delete_completed`);
`:269-310` (`cancel`); `script.raveplayer.ui/raveui/data.py:207-209,1070-1084`;
`resources/lib/downloads.py:206-207,420-430`.

**What happens**

The queue key and the plugin's completion key are different namespaces:

- `RaveData.start_download()` passes `key=_text(entry.key) or url`
  (`data.py:1082-1083`). Track entries are built with
  `_stable_key(parent_key, url) = "<parent>:<md5(url)[:10]>"`
  (`data.py:207-209,1197`), e.g. `toronto:garage:fb0edf7835`.
- The plugin writes every completed index row with
  `key=_key(plan_row["url"]) = sha1(url)[:16]`
  (`downloads.py:206-207,423`), e.g. `7dc328ee74e99ac1`.

The new `_delete_completed` only matches `candidate_key == key`
(`downloadqueue.py:334-338`). Those two values never meet. Reproduced with the
repo class and a fake index whose completed row uses the real plugin key:

```
plugin completion key: 7dc328ee74e99ac1
screen queue key    : toronto:garage:fb0edf7835
deleted after user cancel: []      completed rows: ['7dc328ee74e99ac1']
```

Under 3.9.56 the URL match removed that completed row (which is exactly what
caused the P1 data loss for auto-cancelled duplicates). 3.9.57 removes the
risk by disabling the deletion entirely. The 3.9.56 advisor's required fix was
to **distinguish the explicit user cancel from the auto/late cancel**: only the
user path may remove a completed copy, and an auto-cancelled duplicate must
never remove the row that caused the cancellation. That distinction is not
implemented; all three callers now use the same key-only comparison.

Consequences:

- `LibraryScreens.cancel()` → `queue.cancel()` (`library.py:1396-1410`) cannot
  remove the completed copy the user was cancelling. The 3.9.54 QA P2-3
  "already-completed duplicate file was not deleted" is still true.
- The release/changelog claim "The screen download queue now uses the lazy
  plugin modules hook for completed-file deletion, so a screen cancel removes
  its own file/index row" is false in production.
- The late-cancel branch (`downloadqueue.py:568-580`) no longer removes the
  file it just finished; the comment "The file is still unwanted: remove it"
  is now dead behaviour. This is safe (retention, not loss) but contradicts
  the 3.9.54 P2-3 intent.

**Why 3.9.56 code passes the new test**

`test_screen_queue_deletes_its_own_completed_row`
(`test/test_cancel_integrity_adversarial.py:105-112`) sets
`queue._modules = modules` and uses `"S"` as **both** the queue key and the
completed row key. The 3.9.56 code checks `self._modules is None`, then deletes
by key-or-URL, so it passes too. The test never exercises
`self.modules`/`pluginbridge.load_plugin`, and it never calls `cancel()`.

**Required fix:** either (a) keep the 3.9.56 URL match for the **explicit
`cancel()` path only** and keep key-only for `_finish(cancelled)` and the
late-cancel branch (the advisor's requested ownership distinction), or
(b) persist the plugin's completion key (`plan["key"]` / a public
`downloads.key(url)` helper) on the queue row at plan time and use that for the
user-cancel deletion, with an ownership flag so a late-finish does not remove a
completion it did not own; or (c) explicitly decide that cancel never deletes
completed rows, then correct the notes/changelog and drop the misleading test.
Add a test with realistic distinct keys (`toronto:...` vs `sha1(url)[:16]`),
not `"S" == "S"`.

### B2 — P1 (release blocker): queued cancel + live owner = permanent `cancelling` row and spinning owner

**Where:** `downloadqueue.py:269-310` (`cancel`), `:478-490` (`_pump`),
`:447-475` (`resume`), `:365-368` (`active`); `downloadworker.py:24-25,36-46`.

**What happens**

`cancel()` marks a queued row `cancelling` and writes the sidecar
(`downloadqueue.py:292-306`), expecting the owner worker to observe it. But:

- `_pump()` only starts rows whose status is exactly `"queued"`
  (`:485-488`); a `cancelling` row is never started.
- `refresh()` uses `_read_store(restart=False)` and never converts a live
  `cancelling` row to `cancelled` (`:695-736`); only a **new** `DownloadQueue`
  with `restart=True` converts it (`:714-721`).
- `active()` counts `cancelling` as active (`:34,365-368`), so the owner's
  `while queue.active()` loop (`downloadworker.py:37-46`) never exits.

Reproduced with `max_workers=1`: A blocks a worker, B is queued; cancel B;
release A; after A finishes B is still `cancelling`, `queue.active()` is
`True`, and `_cancel_requested("B")` is `True`. A *new* owner instance then
loads B as `cancelled` and clears the sidecar — i.e. it only heals on a fresh
process (Kodi restart), not in the live owner. While the live owner is stuck,
`start(B)` clears the sidecar and then returns `False` ("already running"),
so the user cannot retry. The Downloads room shows "Cancelling…" with no
dismiss action.

This is reachable whenever the owner is already running (e.g. a previous
download) and a newly queued row (4th concurrent row, or a row queued behind a
blocked worker) is cancelled before a slot frees. The release note "a later
retry of the same key runs normally instead of being cancelled/deleted" is
therefore false for the common live-owner case.

**Required fix:** in `refresh()`/`resume()`, terminalize `cancelling` rows that
are not in `self._running` (set `cancelled`, clear the sidecar, save), or have
`cancel()` write terminal `cancelled` when it can prove no worker owns the row.
Add a test with a blocked worker + a queued row, cancel the queued row, release
the worker, and assert the row becomes terminal and `active()` becomes false.

### B3 — P2: sidecar clear/save ordering can resurrect a cancelled row

**Where:** `downloadqueue.py:666-693` (`_load_store`), `:640-655` (`_finish`),
`:680-693` in particular.

The new terminal-load clear is unsafe in two independent ways:

1. **The window clears without persisting.** A window queue is constructed with
   `local_workers=False` (`window.py:517-519`). `_load_store` marks any row with
   a sidecar `cancelled` (`:671-673`), computes `stale` from `self._items`
   (`:677-678`), drops those keys from the sidecar unconditionally
   (`:679-685`), and calls `_save_now()` only when `restart` (`:689-693`). So a
   window that loads a row whose durable status is still active (the crash
   window between `_request_cancel()` and `_save_now()` in `cancel()`, or a
   failed store write) clears the sidecar and leaves the store active.
   Reproduced: store row `downloading` + sidecar `["K"]`; window load →
   in-memory `cancelled`, sidecar empty, durable store still `downloading`;
   a following owner (`restart=True`) loads K as `queued` and resumes it.
2. **The owner clears before saving.** Even on the owner path, `_load_store`
   clears the sidecar (`:679-685`) before `_save_now()` (`:689-693`). If the
   store write fails (disk full, read-only profile, VFS glitch), the sidecar is
   gone and the durable row is still active. Reproduced with a subclass whose
   `_save_now` raises: durable `downloading`, sidecar empty, next owner
   `queued`. `_finish()` has the same order: `_clear_cancel(key)` at `:649`
   before `_save_now()` at `:654`.

The comment at `:686-688` says "The owner must persist the terminal status ...
otherwise losing the sidecar would resurrect the cancelled row" — but the
sidecar is already lost before the save. The safe order is **persist first,
then clear**, and the window should not clear a sidecar for a row whose
durable status is still active (leave it for the owner).

**Required fix:** save the terminal status before dropping the sidecar; make
the window clear only when the durable row is already terminal (or not clear at
all); add a test that fails the store write and asserts the cancel still wins
on the next owner load.

### B4 — P2: adversarial tests are false positives / incomplete; notes overstate

**Where:** `test/test_cancel_integrity_adversarial.py`; release notes/changelog.

- `FakeDownloads` has no `plan()` (`:18-38`), but
  `test_queued_cancel_sidecar_does_not_poison_a_retry` builds a queue with
  `local_workers=True` (`:84-87`). The spawned worker therefore fails with
  `Could not check the file: 'FakeDownloads' object has no attribute 'plan'`
  and `download_calls == 0`. The test only asserts the sidecar is false
  (`:89`), so it passes while the retry does not actually download. The
  release note's "a later retry ... runs normally" is not tested.
- `test_terminal_row_drops_its_persisted_cancel_on_load` (`:91-103`) seeds the
  store row already `cancelled`, so it cannot exercise the new `_save_now`
  persistence (the "persisted cancelled status" claim). It also uses a window
  queue (`local_workers=False`), the path that does *not* save.
- No test covers the advisor-required variant (b): A completes, B returns
  `ok` while `late_cancel` is set, and A's file/index must survive. The
  existing same-key test
  (`test_rave_screen.py:2362`) asserts `downloads.delete` is called for the
  just-finished key, which is the opposite of the production key relationship.
- No test covers the `_run_one` success → `_cancel_duplicates` path (A
  actually completes); the new test calls `_finish()` directly.
- No test covers the lazy hook (`pluginbridge.load_plugin`), plugin
  unavailability, the live-owner stuck case, or the save-failure/ordering case.

The release note "Regressions covered by `test/test_cancel_integrity_adversarial.py`
plus the existing queue/screen suites" is not supported by the file as written.

**Required fix:** add the missing cases (especially a realistic-key screen
cancel test and the late-finish cross-row test), give `FakeDownloads` a
`plan()`, and assert the worker actually ran (or the row reached `queued`/
`downloading`) in the retry test.

---

## Area-by-area assessment

### 1. `_delete_completed` key-only identity — data loss fixed; feature broken

**No remaining production path deletes another job's completion.** The delete
is keyed on the queue key, and the plugin index is keyed on the URL hash, so
the two never collide. In particular:

- `_cancel_duplicates` (`:609-638`) marks other active rows for the same URL
  `cancelled` and writes their sidecars; the later `_finish(cancelled)` calls
  `_delete_completed` with each row's own queue key, which cannot match the
  completed row that caused the cancellation.
- The late-finish branch (`:568-580`) deletes with the finishing row's queue
  key; it cannot match another row's completion.
- The only theoretical cross-delete is a completed index row whose key equals
  the queue key of a different job. The plugin never writes screen keys, and
  the screen never passes the plugin hash, so this is not reachable. A
  completed row with the same key but a different artifact is also not
  possible in the index: `_save_index` filters rows by key and URL, and
  `_key` is derived from the URL; the queue never writes the index.

This safety is **accidental**: it depends on the two key namespaces never
meeting. If B1 is fixed by passing the plugin key into the queue, then two
queue rows for the same URL would share a completion key, and an
auto-cancelled duplicate's `_finish(cancelled)` would delete the completion the
winner just wrote. The fix therefore needs the explicit user-cancel vs
auto/late distinction, not just a key change.

### 2. Sidecar lifecycle — partially fixed; B2/B3

What is right:

- `start()` clears the sidecar for the key before writing the fresh row
  (`:245-247`), so a stale queued-cancel no longer poisons a retry.
- A **new** owner process converts `cancelling`/interrupted rows and persists
  the terminal status (`_read_store(restart=True)` `:714-721`, `_load_store`
  `:671-693`). Verified: store `cancelling` + sidecar → owner load `cancelled`,
  durable store `cancelled`, sidecar empty, retry works.
- `_finish()` clears its own sidecar; success pops the row and clears it.
- `_cancel_duplicates` writes sidecars for the duplicates it marks terminal.

What is still wrong: B2 (live owner never terminalizes a queued cancel) and B3
(window clears without saving; owner clears before saving). The release note's
"losing the sidecar cannot resurrect the row" is not guaranteed.

### 3. Screen queue `modules` lazy hook — called, but ineffective; P3 I/O

`_delete_completed` now uses the lazy `self.modules` property inside a
`try/except` (`:320-329`), so the screen queue no longer short-circuits on
`_modules is None`. `pluginbridge.load_plugin()` raises `PluginUnavailable`
when the plugin is missing and is caught; `modules.downloads` import failures
and `list_downloads()` failures are caught; `delete()` failures are caught per
row. No deadlock was found: `pluginbridge._IMPORT_LOCK` is acquired
sequentially by `load_plugin()` and then by the lazy `downloads` attribute
access, and the queue's own lock is released before `_delete_completed`.

But because of B1 it removes nothing in production. The new test bypasses the
hook (sets `_modules`), so the hook is not actually tested. On the GUI thread,
`cancel()` now performs a plugin import plus `list_downloads()` (one
`xbmcvfs.exists`/`size` per completed file) before returning; that is new
blocking I/O on the GUI thread. The 3.9.56 advisor suggested a deferred delete
executed by the owner; that would be safer.

### 4. `_cancel_duplicates` and cancel semantics — data-loss correct; user-cancel feature regressed

`_cancel_duplicates` still marks every other active row for the same URL
`cancelled`, writes its sidecar, and saves. It skips the finishing key (which
was already popped on success). It cannot double-delete: `_delete_completed`
only deletes a row that still matches, and `downloads.delete` returns `False`
once the row is gone.

Semantics:

- **Auto-cancel** (A completes) no longer deletes A's completion — correct and
  the important P1 fix.
- **Late cancel** (B returns `ok` after the cancel) leaves the completed file
  in Downloads, because the queue key cannot match the plugin key. Safe
  (retention) but contradicts the "remove the unwanted file" comment and the
  3.9.54 P2-3 intent.
- **User cancel** of a queued row also leaves the old completed copy — the P2
  this patch claims to close (B1).
- Duplicate completed rows under a different key are intentionally left for
  an explicit Remove; the release-note "Known limits" says this, but it
  understates that in production *all* completed rows are under a different
  key.

### 5. Regression risk — normal paths pass; lock/heartbeat untouched; two new write-order risks

- Normal download/plan/progress/complete/delete/retry: the existing
  `DownloadQueueTests` (13 tests) and the full suite pass. The patch does not
  touch `window.py`, `downloadworker.py`'s loop, the instance lock/heartbeat,
  or the plugin's download writer.
- Instance lock/heartbeat: unchanged by 3.9.57. The 3.9.56 no-fcntl fallback
  risk (a >3 s synchronous block can let a second screen open) is carried; it
  is not newly claimed fixed or narrowed in the 3.9.57 notes.
- Progress/index: `_load_store` now performs an extra `_save_now()` on owner
  start when any terminal row exists. It runs **before**
  `acquire_worker_lock()` (`downloadworker.py:24-25`), so a losing/duplicate
  owner can write a stale snapshot over a live owner's store (valid JSON, but
  a lost update). Before 3.9.57 the owner did not write at construction. Move
  the save after the lock is acquired.
- `start()` clears the sidecar **before** checking whether the row is still
  active (`:247-251`). A double-tap start during an in-flight cancel drops the
  sidecar; the cancel then depends on the local `cancel` flag/store refresh.
  The window's `start` does not refresh first, so a stale window can also
  replace a live owner's row. Clear only after the active check.
- Cross-process `downloads.json`: `downloads.delete()`/`_save_index()` have no
  inter-process lock (`downloads.py:261-282,446-456`). The queue's store lock
  does not protect the plugin index. 3.9.57's window-side `_delete_completed`
  makes this easier to hit *if* B1 is fixed (it is currently masked because
  the key never matches). Use the ownership guard and consider a plugin-side
  index lock before enabling cross-process deletion.

### 6. Release hygiene — versions/artifacts/tests pass; notes not accurate

- Versions are consistent: plugin `3.9.57` (`addon.xml:4`), screen `3.9.57`
  and it requires plugin `3.9.57` (`script.raveplayer.ui/addon.xml:4,8`),
  resolver `1.1.0`, repository `1.0.0`; `repo/addons.xml` matches and
  `repo/addons.xml.md5` is `e6cf5f64624b27bea31c34b09c4362cc`, which matches
  the file.
- `scripts/check-repo-artifacts.sh` passes. The committed repo plugin zip
  (144 payload files) and screen zip (105) are byte-identical to the worktree
  for every common file, including `raveui/downloadqueue.py`; resolver (21)
  and repository (3) zip payloads are identical to 3.9.56 (timestamps only).
  `dist/` and `repo/` plugin/screen zips are identical. No junk
  (`.DS_Store`, `__pycache__`, `.pyc`, `.part`, `.tmp`, tests) in the zips.
- `git diff --check` is clean; no secret/token/debug value observed in the
  reviewed diff.
- Full suite at HEAD: **1171 tests, OK** twice (38.6 s, 41.0 s); the new
  adversarial file passes 5/5 five times (despite the coverage gaps above).
- The release notes/changelog overstate the completed-deletion and retry
  behaviour (B1/B4). The notes also do not record a verification run; add the
  HEAD run and count.

---

## Verification performed

| Check | Result |
|---|---|
| `git diff 1c40b8f..HEAD` review | 16 files, 682 insertions, 15 deletions |
| Full suite at HEAD, run 1 | **1171 tests, OK** in 38.6 s |
| Full suite at HEAD, run 2 | **1171 tests, OK** in 41.0 s |
| New `test_cancel_integrity_adversarial`, 5 runs | 5 tests OK each |
| `git diff --check` | clean |
| `sh scripts/check-repo-artifacts.sh` | pass |
| `repo/addons.xml` md5 | `e6cf5f64624b27bea31c34b09c4362cc` matches |
| Versions | plugin 3.9.57, screen 3.9.57 (requires plugin 3.9.57), resolver 1.1.0, repo 1.0.0 |
| Repo plugin zip vs worktree | 144 payload files; all common files identical |
| Repo screen zip vs worktree | 105 payload files; all identical |
| Resolver/repository zips vs 3.9.56 | payload identical (21/3 files) |
| `dist/` vs `repo/` zips | byte-identical (plugin `fdf7f489…`, screen `17fb289c…`) |
| Zip junk/secret scan | no hits |
| Device / ADB / Shield | not used |

Targeted reproductions (temporary harnesses outside the repo, no tracked
changes):

- user cancel with a real plugin completion key → `deleted == []` (B1);
- window load of a `downloading` row + sidecar → in-memory `cancelled`,
  sidecar empty, durable store still `downloading`; next owner loads `queued`
  (B3);
- owner load with a failing `_save_now` → durable `downloading`, sidecar empty,
  next owner `queued` (B3);
- blocked worker + queued row B, cancel B, release the worker → B stays
  `cancelling`, `active()` true; a new owner converts it to `cancelled` (B2);
- new retry test's worker → `Could not check the file: 'FakeDownloads' object
  has no attribute 'plan'`, `download_calls == 0` (B4).

---

## Required before SHIP

1. Fix B1 with the advisor's explicit-user-cancel vs auto/late-cancel
   distinction (or a persisted completion key plus an ownership flag), and
   correct the release notes to match the actual behaviour. Add a realistic
   distinct-key test that goes through `cancel()` with a window-style queue.
2. Fix B2 so a queued cancel with a live owner becomes terminal and the owner
   can exit; add the blocked-worker test.
3. Fix B3's clear/save ordering (persist first, then clear; the window should
   not clear a sidecar for an active durable row) and add a store-failure test.
4. Fix B4: give `FakeDownloads` a `plan()`, assert the retry actually runs, and
   add the missing late-finish cross-row, `_run_one`/`_cancel_duplicates`,
   lazy-hook/plugin-unavailable and persistence tests.
5. Either harden/narrow the carried no-fcntl heartbeat claim, correct the
   3.9.56 QA P2-3 "Closed" row, and fix the still-wrong malformed-cache test
   key (3.9.56 advisor required items 3-5), or explicitly defer them in the
   3.9.57 notes.

## Residual risk (non-blocking)

- Owner `_load_store` save before the worker lock (lost update with two owners).
- `start()` clears the sidecar before the active check (double-tap can drop an
  in-flight cancel).
- GUI-thread plugin import/index stat in `cancel()`; prefer a deferred owner
  delete.
- Cross-process `downloads.json` writes are unlocked; the current key mismatch
  masks this, but fixing B1 makes it live.
- `_cancel_duplicates` leaves sidecars for queued duplicates until a load/start
  (harmless now, but another durability edge).
- The 3.9.56 no-fcntl heartbeat fallback, `docs/RELEASE-3.9.56.md` P2-3
  status, and the malformed-cache test remain from the prior review.

## Concurrent worktree delta (outside this verdict)

At the time of writing, the worktree contains an uncommitted change to
`script.raveplayer.ui/raveui/downloadqueue.py` (47 insertions / 25 deletions)
that was **not** authored by this reviewer and is not in
`git diff 1c40b8f..HEAD`. It appears to apply the direction of B1-B3:

- `cancel()` now calls `_delete_completed(..., by_url=True)` and
  `_delete_completed` accepts a URL match only when `by_url` is set;
  `_finish(cancelled)` stays key-only. This is the advisor's requested
  user-cancel vs auto/late distinction and, if committed and tested, would
  close B1.
- `cancel()` terminalizes a `queued` row it believes has no worker
  (`candidate not in self._running`) instead of leaving it `cancelling`, and
  clears its sidecar. This targets B2.
- `_finish`/`_load_store` now save before clearing the sidecar, and the
  terminal-load clear is owner-only (`restart=True`). This targets B3.

It has not been reviewed or tested as part of this report. Two points to
check before committing:

1. `_load_store` still calls `_update_cancels(drop)` after a failed
   `_save_now()` (the `try/except` catches and continues). A failed store
   write therefore still clears the sidecar and can resurrect the row; gate the
   clear on a successful save.
2. In the window queue, `self._running` is always empty
   (`local_workers=False`), so the new terminal-queued-cancel branch can mark
   a row `cancelled` and clear its sidecar while the headless owner has already
   started that row. The owner's worker then sees no cancel flag and no
   sidecar and can finish the download while the window shows it cancelled.
   The owner should acknowledge/terminalize (or the window should write the
   sidecar and let the owner's `refresh`/`resume` terminalize rows not in its
   `_running`); add the race test.
3. The tests were not updated for the delta; re-run the full suite and add
   cases for these three changes.

## Bottom line

The data-loss bug that blocked 3.9.56 is closed: key-only matching means an
auto-cancelled duplicate cannot delete the winner's file. But the patch closes
it by making the completed deletion unreachable, so the screen still cannot do
the P2-3 cleanup it advertises, and the new sidecar logic is not durable in the
window/clear-before-save cases. The live-owner queued cancel remains a
user-visible stuck state and a leaked owner process. These are fixable in a
small follow-up; the current notes should not ship as written.
