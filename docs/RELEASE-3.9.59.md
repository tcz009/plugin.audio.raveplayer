# Rave Player 3.9.59 — conservative cancel safety

Patch over **3.9.58** (`bb5086f`) for the 3.9.57 cancel reviews. Branch
`fix/3.9.59`; plugin and Rave Screen both **3.9.59**; resolver stays **1.1.0**.

This is a code-only patch: no device run, no ADB, no Shield change, no push and
no tag. Verification is the offline suite and a repo-artifact check.

## Behaviour change: cancel never deletes a completed download

3.9.57/3.9.58 tried to make "cancel removes its completed copy" safe by
distinguishing active from completed rows. The reviews showed that every
variant still had a cross-process deletion or resurrection path. 3.9.59 takes
the conservative rule instead:

- `DownloadQueue.cancel()` only marks **active** rows (`queued`, `checking`,
  `downloading`, `cancelling`) for cancellation and writes their sidecars.
- `_finish(cancelled)` and the late-cancel branch no longer call
  `_delete_completed()`; the helper is removed entirely. A cancel never calls
  `downloads.delete()`.
- Cancelling a completed row does not delete that row or any same-URL copy.
- A same-URL completed copy that already exists stays in Downloads. **Cancel
  removing a completed duplicate is deferred**; this is a known limitation, not
  a release claim. The Downloads room's explicit delete
  (`downloads.delete`) is unchanged and remains the way to remove a finished
  download.

## Durability: sidecar cleared only after a real save

- `_write_store()` returns `_write_json_atomic()`'s boolean (and `True` when
  no store path is configured). `_save_now()` returns it; `_save_throttled()`
  returns it too.
- `_finish()` persists the terminal row and only calls `_clear_cancel()` when
  that write returned `True`. On a failed write the sidecar stays, so the next
  owner reloads the row as cancelled instead of restarting it.
- Owner `_load_store(restart=True)` applies the same gate before dropping stale
  terminal sidecars. The window (`restart=False`) still leaves the sidecar to
  the owner.

## Cross-process store merge

The window and the headless owner write the same `download-queue.json`. A bare
last-writer-wins snapshot let a stale window overwrite newer progress or
re-create a row the owner had completed/removed.

- 3.9.59 writes `{"rows": [...], "removed": {key: updated}}`. Older bare-list
  stores are still read; they are upgraded on the next save.
- `_write_store()` reads the on-disk store under the existing writer lock and
  merges per row by `updated`: a disk row newer than the local copy wins, so a
  stale window cannot rewind progress.
- A completed or dismissed row is remembered as a short-lived removal
  tombstone. A tombstone newer than a local/disk row drops it, so a stale
  snapshot cannot resurrect a removed row. Local cancel/status changes stamp a
  fresh `updated` and therefore win over older disk state.
- `refresh()` also applies tombstones, so a window's next `rows()` drops a ghost
  row instead of painting it indefinitely.
- Window `start()` and `cancel()` refresh the store *before* their active/ghost
  check: a stale window cannot clear an in-flight cancel or act on a row the
  owner already completed.
- Owner drain (`_terminalize_orphan_cancels`) and queued-cancel retry are
  retained. Owner terminal loads now stamp a fresh `updated`, so a window sees
  the drained `cancelled` row and may retry.

## Versions and artifacts

- plugin `3.9.59`; Rave Screen `3.9.59`, requiring plugin `3.9.59`; resolver
  `1.1.0`; repository `1.0.0`.
- `changelog.txt` and `script.raveplayer.ui/changelog.txt` carry the 3.9.59
  entry; README and PUBLISHING point at 3.9.59 and the new release notes.
- `scripts/build.sh`, `scripts/build-repo.sh` and
  `scripts/check-repo-artifacts.sh` are the release path; `dist/` and the
  versioned `repo/` zips are rebuilt from this tree.

## Tests

`test/test_cancel_integrity_adversarial.py` (20 deterministic tests) pins:

- active cancel, completed-row cancel, `_finish(cancelled)` and the late-cancel
  branch never delete a completed index/file;
- a failed real store write keeps the sidecar on both `_finish` and owner load,
  and the next owner terminalizes instead of requeueing;
- a stale window write cannot overwrite a newer owner row, resurrect a removed
  row, or lose a newer local cancel;
- a stale window cancel/start cannot act on an owner-completed ghost row;
- owner drain and a cross-process queued-cancel retry that actually downloads.

The `DownloadQueueTests` in `test/test_rave_screen.py` were updated for the
conservative rule (no delete) and for the new store package format. Two
pre-existing timing flakes were made deterministic: the interrupted-row test
now waits for the durable store before loading the next owner, and the worker
tests wait for the worker thread to finish before the temp directory is
removed. The full suite (`python3 -m unittest discover -s test`) ran twice on
this tree: **1186 tests, OK** in both runs.

## Known limits

- **Cancel does not remove a completed duplicate.** If a same-URL file has
  already completed, cancelling the row leaves it in Downloads. Explicit delete
  from the Downloads room still works. This is deferred work, not claimed as
  fixed.
- Removal tombstones are pruned after **7 days**. A window left open longer
  than that could theoretically resurrect a removed row; normal Kodi sessions
  and the window's `rows()` refresh make this a low-risk residual.
- The store writer lock is best-effort; if it cannot be acquired within its
  timeout the merge still writes a valid snapshot, but two simultaneous
  read-merge-write cycles could lose an update. The unique temp + atomic rename
  still prevents torn JSON.
- The plugin's `downloads.json` index has no cross-process lock. 3.9.59 removes
  the cancel path's reads/writes of that index; the Downloads room's explicit
  delete still uses it.
- `_finish(cancelled)` still calls `_cancel_duplicates()`, so a late drain can
  cancel a same-URL retry that started after the original cancel. Carried from
  3.9.57; not addressed by this minimal patch.
- No device/ADB run, no push and no tag. Kodi device behaviour is not verified
  by this patch.
