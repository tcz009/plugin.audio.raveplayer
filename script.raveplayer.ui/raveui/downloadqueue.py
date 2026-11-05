# -*- coding: utf-8 -*-
"""In-window download queue.

Downloads are the one place where the screen writes through the plugin: it
calls the plugin's own ``downloads.plan``/``download`` helpers, so eligibility,
size limits, atomic renames and ``downloads.json`` stay owned by one add-on.

The network work runs on a daemon worker.  A download is a *row* in the
Downloads room, not a modal dialog: the GUI keeps painting and Back still
closes the window.  Progress is read from the row snapshot whenever the room is
rendered, and the optional ``on_update`` callback is only a hint (the worker
never touches Kodi controls).
"""

import threading
import time

from . import pluginbridge

ACTIVE = ("queued", "checking", "downloading", "cancelling")


class DownloadQueue(object):
    def __init__(self, modules=None, logger=None, on_update=None):
        self._modules = modules
        self._logger = logger
        self._on_update = on_update
        self._lock = threading.Lock()
        self._items = {}
        self._order = []

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
            if not self.modules.downloads.eligible(url, source):
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
            }
            if row_key not in self._order:
                self._order.append(row_key)
        worker = threading.Thread(target=self._run, args=(row_key,),
                                  name="rave-download", daemon=True)
        worker.start()
        return True, "Download started — progress is in Downloads."

    def cancel(self, key):
        with self._lock:
            row = self._items.get(str(key or ""))
            if row is None or row.get("status") not in ACTIVE:
                return False
            row["cancel"] = True
            row["status"] = "cancelling"
        self._safe_update()
        return True

    def dismiss(self, key):
        key = str(key or "")
        with self._lock:
            row = self._items.pop(key, None)
            if row is not None and key in self._order:
                self._order.remove(key)
        return row is not None

    def rows(self):
        with self._lock:
            return [dict(self._items[key]) for key in self._order
                    if key in self._items]

    # -------------------------------------------------------------- worker
    def _run(self, key):
        with self._lock:
            row = self._items.get(key)
        if row is None:
            return
        try:
            self._set(key, status="checking", detail="Checking size")
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
        self._safe_update()

        def progress(done, total):
            percent = int((done * 100) / total) if total else 0
            with self._lock:
                current = self._items.get(key)
                if current is not None:
                    current["done"] = int(done or 0)
                    current["total"] = int(total or current.get("total") or 0)
                    current["percent"] = max(0, min(percent, 100))
                    current["status"] = "downloading"
            self._safe_update()

        def cancelled():
            with self._lock:
                current = self._items.get(key)
                return bool(current is None or current.get("cancel"))

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
            self._safe_update()
            return
        reason = str(result.get("reason") or "Download failed.")
        status = "cancelled" if "cancel" in reason.lower() else "failed"
        self._finish(key, status, reason)

    def _set(self, key, **fields):
        with self._lock:
            row = self._items.get(key)
            if row is None:
                return
            row.update(fields)
        self._safe_update()

    def _finish(self, key, status, detail):
        with self._lock:
            row = self._items.get(key)
            if row is None:
                return
            row["status"] = status
            row["detail"] = str(detail or status)[:160]
        self._log("download %s: %s (%s)" % (key, status, detail))
        self._safe_update()

    def _safe_update(self):
        if self._on_update is None:
            return
        try:
            self._on_update()
        except Exception:  # noqa: BLE001 - a hint must never break a worker
            pass

    def _log(self, message):
        if self._logger is None:
            return
        try:
            self._logger(message)
        except Exception:
            pass
