# -*- coding: utf-8 -*-
"""Download queue: persistent rows + bounded workers.

Downloads are the one place where the screen writes through the plugin: it
calls the plugin's own ``downloads.plan``/``download`` helpers, so eligibility,
size limits, atomic renames and ``downloads.json`` stay owned by one add-on.

The network work runs on a daemon worker.  A download is a *row* in the
Downloads room, not a modal dialog: the GUI keeps painting and Back still
closes the window.  Progress is read from the row snapshot whenever the room is
rendered, and the optional ``on_update`` callback is only a hint (the worker
never touches Kodi controls).

Leaving the window must not kill a transfer.  When a store path is configured
(the real window always configures one), every row is persisted, and
:meth:`DownloadQueue.spawn_worker` starts a headless ``script.raveplayer.ui
downloads`` process before the window's interpreter exits.  That worker reloads
the store, restarts interrupted rows and keeps the queue alive until it drains.
"""

import json
import os
import threading
import time

from . import pluginbridge

ACTIVE = ("queued", "checking", "downloading", "cancelling")
FINISHED = ("failed", "cancelled")
DEFAULT_MAX_WORKERS = 3
WORKER_LOCK_TTL = 45.0
_PROGRESS_SAVE_INTERVAL = 1.0


def default_store_path():
    """Profile path for the persistent queue (empty when outside Kodi)."""
    try:
        import xbmcaddon

        profile = (xbmcaddon.Addon("script.raveplayer.ui")
                   .getAddonInfo("profile") or "")
    except Exception:  # noqa: BLE001 - tests/CLI have no profile
        try:
            import xbmcaddon

            profile = xbmcaddon.Addon().getAddonInfo("profile") or ""
        except Exception:  # noqa: BLE001 - no add-on context
            profile = ""
    if not profile:
        return ""
    try:
        import xbmcvfs

        # Kodi returns "special://profile/..." here; os.open/makedirs need the
        # translated filesystem path or every write fails with ENOENT.
        profile = xbmcvfs.translatePath(profile) or profile
    except Exception:  # noqa: BLE001 - tests / CLI have no VFS
        pass
    try:
        os.makedirs(profile, exist_ok=True)
    except OSError:
        pass
    return os.path.join(profile, "download-queue.json")


class DownloadQueue(object):
    def __init__(self, modules=None, logger=None, on_update=None,
                 store_path=None, max_workers=DEFAULT_MAX_WORKERS,
                 local_workers=True):
        self._modules = modules
        self._logger = logger
        self._on_update = on_update
        self._lock = threading.Lock()
        self._items = {}
        self._order = []
        self._store_path = store_path
        # The window defers transfer ownership to the headless script process
        # (local_workers=False) so closing the window can never kill a transfer;
        # the headless owner and the offline tests run workers in-process.
        self._local_workers = bool(local_workers)
        self._max_workers = max(1, int(max_workers or DEFAULT_MAX_WORKERS))
        self._running = {}
        self._last_save = 0.0
        self._worker_lock_path = ""
        if store_path:
            # Only the process that will run the transfer may convert an
            # interrupted "downloading" row back to "queued"; a read-only
            # window follows the owner's live status instead.
            self._load_store(restart=self._local_workers)

    @property
    def modules(self):
        if self._modules is None:
            self._modules = pluginbridge.load_plugin()
        return self._modules

    # ------------------------------------------------------------------ API
    def start(self, url, title, source, key=""):
        url = str(url or "")
        title = str(title or "Rave Player download")
        source = str(source or "")
        if not url or not source:
            return False, "That row has no downloadable file."
        try:
            # Cheap eligibility only: scheme/host/extension.  DNS and the size
            # probe run in the worker, so starting a download never stalls the
            # GUI thread (P2-8).
            if not self.modules.downloads.eligible(url, source,
                                                   check_host=False):
                return False, "That source is not downloadable."
        except Exception as exc:  # noqa: BLE001 - optional module
            return False, "Downloads are unavailable (%s)." % exc
        row_key = str(key or url)
        with self._lock:
            existing = self._items.get(row_key)
            if existing is not None and existing.get("status") in ACTIVE:
                return False, "That download is already running."
            self._items[row_key] = {
                "key": row_key, "title": title, "source": source, "url": url,
                "status": "queued", "percent": 0, "done": 0, "total": 0,
                "detail": "", "started": time.time(), "cancel": False,
                "updated": time.time(),
            }
            if row_key not in self._order:
                self._order.append(row_key)
        self._save_now()
        if self._local_workers:
            self._pump()
        else:
            # The window only owns the row and the store; a separate script
            # process performs the transfer and survives this window.
            self.spawn_worker()
        return True, "Download started — progress is in Downloads."

    def cancel(self, key):
        key = str(key or "")
        with self._lock:
            row = self._items.get(key)
            if row is None or row.get("status") not in ACTIVE:
                return False
            row["cancel"] = True
            row["status"] = "cancelling"
            row["updated"] = time.time()
        # A progress write from the transfer worker can land after this row is
        # saved; the sidecar is the durable cancel barrier the worker polls
        # before every chunk (P1-5).
        self._request_cancel(key)
        self._save_now()
        self._safe_update()
        return True

    def dismiss(self, key):
        key = str(key or "")
        with self._lock:
            row = self._items.pop(key, None)
            if row is not None and key in self._order:
                self._order.remove(key)
        if row is not None:
            self._clear_cancel(key)
            self._save_now()
        return row is not None

    def rows(self):
        if not self._local_workers and self._store_path:
            self.refresh()
        with self._lock:
            return [dict(self._items[key]) for key in self._order
                    if key in self._items]

    def active(self):
        with self._lock:
            return any(row.get("status") in ACTIVE
                       for row in self._items.values())

    # ------------------------------------------------------------ ownership
    def worker_active(self):
        """True while a headless owner from another interpreter is alive."""
        path = self._store_path + ".worker" if self._store_path else ""
        if not path:
            return False
        try:
            age = time.time() - os.path.getmtime(path)
        except OSError:
            return False
        return age <= WORKER_LOCK_TTL

    def spawn_worker(self):
        """Start a headless download worker if anything is still active.

        The window's interpreter exits when the window closes; the separate
        script process is what keeps the transfer alive.
        """
        if not self._store_path or not self.active():
            return False
        if self.worker_active():
            return False
        try:
            import xbmc

            xbmc.executebuiltin("RunScript(script.raveplayer.ui,downloads)")
            return True
        except Exception as exc:  # noqa: BLE001 - queue dies with the window
            self._log("could not spawn the download worker: %s" % exc)
            return False

    def acquire_worker_lock(self):
        path = self._store_path + ".worker" if self._store_path else ""
        if not path:
            return False
        for _ in range(2):
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(descriptor, str(os.getpid()).encode("utf-8"))
                finally:
                    os.close(descriptor)
                self._worker_lock_path = path
                return True
            except FileExistsError:
                try:
                    age = time.time() - os.path.getmtime(path)
                except OSError:
                    age = 0
                if age > WORKER_LOCK_TTL:
                    try:
                        os.remove(path)
                    except OSError:
                        return False
                    continue
                return False
            except OSError:
                return False
        return False

    def heartbeat(self):
        if not self._worker_lock_path:
            return
        try:
            os.utime(self._worker_lock_path, None)
        except OSError:
            pass

    def release_worker_lock(self):
        if not self._worker_lock_path:
            return
        try:
            os.remove(self._worker_lock_path)
        except OSError:
            pass
        self._worker_lock_path = ""

    def refresh(self):
        """Merge rows written by another process without clobbering progress."""
        if not self._store_path:
            return
        rows = self._read_store()
        with self._lock:
            for row in rows:
                key = str(row.get("key") or "")
                if not key:
                    continue
                current = self._items.get(key)
                if current is not None:
                    # Only a newer disk snapshot may replace local state, so a
                    # slightly older read cannot rewind a live progress row.
                    if float(row.get("updated") or 0) <= float(
                            current.get("updated") or 0):
                        continue
                elif key not in self._order:
                    self._order.append(key)
                self._items[key] = row

    def resume(self):
        """Restart queued/interrupted rows (used by the headless worker)."""
        if not self._local_workers:
            self.spawn_worker()
            return
        self._pump()
        self.refresh()
        self._pump()

    # -------------------------------------------------------------- worker
    def _pump(self):
        """Start workers for queued rows, up to the configured cap."""
        if not self._local_workers:
            return
        with self._lock:
            slots = self._max_workers - len(
                [thread for thread in self._running.values() if thread.is_alive()])
            pending = [key for key in self._order
                       if key in self._items
                       and self._items[key].get("status") == "queued"
                       and key not in self._running]
        for key in pending[:max(0, slots)]:
            self._spawn(key)

    def _spawn(self, key):
        worker = threading.Thread(target=self._run, args=(key,),
                                  name="rave-download", daemon=True)
        with self._lock:
            self._running[key] = worker
        worker.start()

    def _run(self, key):
        with self._lock:
            row = self._items.get(key)
        if row is None:
            with self._lock:
                self._running.pop(key, None)
            return
        try:
            self._run_one(key)
        finally:
            with self._lock:
                self._running.pop(key, None)
            self._pump()

    def _run_one(self, key):
        try:
            self._set(key, status="checking", detail="Checking size")
            row = self._row(key)
            if row is None:
                return
            plan = self.modules.downloads.plan(row["url"], row["title"],
                                               row["source"])
        except Exception as exc:  # noqa: BLE001 - never raise into Kodi
            self._finish(key, "failed", "Could not check the file: %s" % exc)
            return
        if not plan.get("allowed"):
            self._finish(key, "failed", plan.get("reason") or "Download not allowed.")
            return
        with self._lock:
            current = self._items.get(key)
            if current is not None:
                current["total"] = int(plan.get("size") or 0)
                current["status"] = "downloading"
                current["detail"] = "Downloading"
                current["updated"] = time.time()
        self._save_now()

        def progress(done, total):
            percent = int((done * 100) / total) if total else 0
            first = False
            with self._lock:
                current = self._items.get(key)
                if current is not None:
                    first = not current.get("percent")
                    current["done"] = int(done or 0)
                    current["total"] = int(total or current.get("total") or 0)
                    current["percent"] = max(0, min(percent, 100))
                    current["status"] = "downloading"
                    current["updated"] = time.time()
            # Persist the first measurable progress at once: a daemon owner
            # that dies one tick later must leave a resumable percentage.
            if first:
                self._save_now()
            else:
                self._save_throttled()
            self._safe_update()

        def cancelled():
            with self._lock:
                current = self._items.get(key)
                local = bool(current is None or current.get("cancel"))
            return bool(local or self._cancel_requested(key))

        try:
            result = self.modules.downloads.download(
                plan, progress=progress, cancelled=cancelled)
        except Exception as exc:  # noqa: BLE001 - fail as a row, not a traceback
            self._finish(key, "failed", "Download failed: %s" % exc)
            return
        if result.get("ok"):
            with self._lock:
                self._items.pop(key, None)
                if key in self._order:
                    self._order.remove(key)
            self._clear_cancel(key)
            self._save_now()
            self._safe_update()
            return
        reason = str(result.get("reason") or "Download failed.")
        status = "cancelled" if "cancel" in reason.lower() else "failed"
        self._finish(key, status, reason)

    def _row(self, key):
        with self._lock:
            row = self._items.get(key)
            return dict(row) if row is not None else None

    def _set(self, key, **fields):
        with self._lock:
            row = self._items.get(key)
            if row is None:
                return
            fields["updated"] = time.time()
            row.update(fields)
        self._save_now()
        self._safe_update()

    def _finish(self, key, status, detail):
        with self._lock:
            row = self._items.get(key)
            if row is None:
                return
            row["status"] = status
            row["detail"] = str(detail or status)[:160]
            row["updated"] = time.time()
        self._clear_cancel(key)
        self._log("download %s: %s (%s)" % (key, status, detail))
        self._save_now()
        self._safe_update()

    def _safe_update(self):
        if self._on_update is None:
            return
        try:
            self._on_update()
        except Exception:  # noqa: BLE001 - a hint must never break a worker
            pass

    # ------------------------------------------------------------ persistence
    def _load_store(self, restart=True):
        for row in self._read_store(restart=restart):
            key = str(row.get("key") or "")
            if not key or key in self._items:
                continue
            if self._cancel_requested(key):
                row["status"] = "cancelled"
                row["cancel"] = True
            if key not in self._order:
                self._order.append(key)
            self._items[key] = row

    def _read_store(self, restart=False):
        path = self._store_path
        if not path:
            return []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                package = json.load(handle)
        except (OSError, ValueError, TypeError):
            return []
        rows = []
        for raw in package if isinstance(package, list) else []:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("key") or "")
            url = str(raw.get("url") or "")
            source = str(raw.get("source") or "")
            if not key or not url or not source:
                continue
            status = str(raw.get("status") or "queued")
            if restart:
                # Only the owner's initial load treats an in-flight row as
                # interrupted.  A live refresh must keep the current status so
                # the Downloads room can show percent and cancel.
                if status in ("checking", "downloading"):
                    status = "queued"
                elif status == "cancelling":
                    status = "cancelled"
            rows.append({
                "key": key,
                "title": str(raw.get("title") or "Download"),
                "source": source,
                "url": url,
                "status": status if status in ACTIVE + FINISHED else "queued",
                "percent": max(0, min(100, int(raw.get("percent") or 0))),
                "done": max(0, int(raw.get("done") or 0)),
                "total": max(0, int(raw.get("total") or 0)),
                "detail": str(raw.get("detail") or "")[:160],
                "started": float(raw.get("started") or time.time()),
                "cancel": bool(raw.get("cancel")),
                "updated": float(raw.get("updated") or 0),
            })
        return rows

    def _cancel_store_path(self):
        return self._store_path + ".cancel" if self._store_path else ""

    def _read_cancels(self):
        path = self._cancel_store_path()
        if not path:
            return set()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, ValueError, TypeError):
            return set()
        if not isinstance(value, list):
            return set()
        return {str(key) for key in value if key}

    def _write_cancels(self, keys):
        path = self._cancel_store_path()
        if not path:
            return
        temporary = path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(sorted(keys), handle)
            os.replace(temporary, path)
        except OSError as exc:
            try:
                os.remove(temporary)
            except OSError:
                pass
            self._log("cancel flag save failed: %s" % exc)

    def _request_cancel(self, key):
        keys = self._read_cancels()
        keys.add(str(key))
        self._write_cancels(keys)

    def _clear_cancel(self, key):
        keys = self._read_cancels()
        if str(key) in keys:
            keys.discard(str(key))
            self._write_cancels(keys)

    def _cancel_requested(self, key):
        return str(key) in self._read_cancels()

    def _save_now(self):
        self._last_save = time.monotonic()
        self._write_store()

    def _save_throttled(self):
        now = time.monotonic()
        if now - self._last_save < _PROGRESS_SAVE_INTERVAL:
            return
        self._last_save = now
        self._write_store()

    def _write_store(self):
        path = self._store_path
        if not path:
            return
        with self._lock:
            rows = [dict(self._items[key]) for key in self._order
                    if key in self._items]
        temporary = path + ".tmp"
        try:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(rows, handle, ensure_ascii=False, indent=0)
            os.replace(temporary, path)
        except OSError as exc:
            try:
                os.remove(temporary)
            except OSError:
                pass
            self._log("download queue save failed: %s" % exc)

    def _log(self, message):
        if self._logger is None:
            return
        try:
            self._logger(message)
        except Exception:
            pass
