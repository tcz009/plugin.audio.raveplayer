# -*- coding: utf-8 -*-
"""Adversarial cancel/data-integrity tests for the screen download queue.

3.9.59 conservative rule: a cancel never deletes a completed download.  These
tests pin that rule, the save-then-clear durability gate, and the cross-process
store merge (stale window vs live owner).
"""

import json
import os
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "script.raveplayer.ui"))

from raveui import downloadqueue as dqmod  # noqa: E402
from raveui.downloadqueue import DownloadQueue  # noqa: E402


class FakeDownloads(object):
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.deleted = []
        self.download_calls = 0

    def eligible(self, url, source, check_host=True):
        return True

    def list_downloads(self):
        return [dict(row) for row in self.rows]

    def delete(self, key):
        self.deleted.append(key)
        before = len(self.rows)
        self.rows = [row for row in self.rows if str(row.get("key")) != str(key)]
        return len(self.rows) < before

    def plan(self, url, title="", source="", **kwargs):
        return {"allowed": True, "size": 1024, "url": url}

    def download(self, plan, progress=None, cancelled=None):
        self.download_calls += 1
        return {"ok": True, "path": "/tmp/x.mp3"}


def fake_modules(rows=None):
    downloads = FakeDownloads(rows)
    return types.SimpleNamespace(downloads=downloads), downloads


def make_row(key, url, status="queued", updated=0.0, **extra):
    row = {"key": key, "title": key, "source": "mediafire", "url": url,
           "status": status, "percent": 0, "done": 0, "total": 0,
           "detail": "", "started": 0.0, "cancel": False,
           "updated": updated}
    row.update(extra)
    return row


def seed(queue, key, url, status="queued", updated=0.0, **extra):
    row = make_row(key, url, status, updated, **extra)
    queue._items[key] = row
    if key not in queue._order:
        queue._order.append(key)
    return row


def write_store(path, rows, removed=None):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"rows": list(rows), "removed": dict(removed or {})}, handle)


def read_store(path):
    with open(path, "r", encoding="utf-8") as handle:
        package = json.load(handle)
    if isinstance(package, dict):
        return package.get("rows") or [], package.get("removed") or {}
    return package or [], {}


class CancelIntegrityTests(unittest.TestCase):
    def queue(self, modules=None, local_workers=False, path=None):
        modules = modules or fake_modules()[0]
        if path is None:
            path = os.path.join(tempfile.mkdtemp(), "q.json")
        return DownloadQueue(modules=modules, local_workers=local_workers,
                             store_path=path)

    def wait_until(self, predicate, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    # ---------------------------------------------------------- no deletion
    def test_cancelled_duplicate_never_deletes_a_completed_same_url(self):
        url = "https://download.example.net/x.mp3"
        modules, downloads = fake_modules([{"key": "A", "url": url}])
        queue = self.queue(modules)
        seed(queue, "A", url, status="done")
        seed(queue, "B", url, status="cancelling", cancel=True)
        queue._finish("B", "cancelled", "cancelled by user")
        self.assertEqual(downloads.deleted, [])
        self.assertEqual([row["key"] for row in downloads.rows], ["A"])

    def test_active_cancel_never_deletes_a_completed_copy(self):
        url = "https://download.example.net/active.mp3"
        modules, downloads = fake_modules([{"key": "sha1", "url": url}])
        queue = self.queue(modules)
        seed(queue, "B", url, status="queued", updated=100)
        self.assertTrue(queue.cancel("B"))
        self.assertEqual(queue._row("B")["status"], "cancelling")
        self.assertEqual(downloads.deleted, [])
        self.assertEqual([row["key"] for row in downloads.rows], ["sha1"])

    def test_completed_row_cancel_does_not_delete_either(self):
        url = "https://download.example.net/done.mp3"
        modules, downloads = fake_modules([{"key": "sha1", "url": url}])
        queue = self.queue(modules)
        seed(queue, "screen-key", url, status="done", updated=100)
        self.assertFalse(queue.cancel("screen-key"))
        self.assertEqual(downloads.deleted, [])
        self.assertEqual([row["key"] for row in downloads.rows], ["sha1"])

    def test_late_finish_of_a_duplicate_never_touches_the_completion(self):
        url = "https://download.example.net/late.mp3"
        modules, downloads = fake_modules([{"key": "A", "url": url}])
        queue = self.queue(modules)
        seed(queue, "A", url, status="done")
        seed(queue, "B", url, status="downloading", cancel=True)
        queue._finish("B", "cancelled", "late cancel")
        self.assertEqual(downloads.deleted, [])
        self.assertEqual([row["key"] for row in downloads.rows], ["A"])

    def test_late_cancel_after_success_leaves_the_completed_copy(self):
        url = "https://download.example.net/late-ok.mp3"
        modules, downloads = fake_modules([{"key": "sha1", "url": url}])
        queue = self.queue(modules, local_workers=True)
        seed(queue, "K", url, status="downloading", cancel=True, updated=100)
        queue._run_one("K")
        self.assertEqual(downloads.deleted, [])
        self.assertEqual(queue._row("K")["status"], "cancelled")
        self.assertEqual([row["key"] for row in downloads.rows], ["sha1"])

    # ---------------------------------------------------------- lifecycle
    def test_queued_cancel_sidecar_does_not_poison_a_retry(self):
        url = "https://download.example.net/z.mp3"
        modules, downloads = fake_modules([])
        queue = self.queue(modules, local_workers=True)
        queue._request_cancel("retry-key")
        self.assertTrue(queue._cancel_requested("retry-key"))
        ok, _ = queue.start(url, "Retry", "mediafire", key="retry-key")
        self.assertTrue(ok)
        self.assertFalse(queue._cancel_requested("retry-key"))

    def test_terminal_row_drops_its_persisted_cancel_on_load(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        row = make_row("done-key", "https://download.example.net/a.mp3",
                       status="cancelled", updated=10, cancel=True)
        write_store(path, [row])
        with open(path + ".cancel", "w", encoding="utf-8") as handle:
            json.dump(["done-key"], handle)
        queue = self.queue(local_workers=True, path=path)
        self.assertFalse(queue._cancel_requested("done-key"))

    def test_window_keeps_the_sidecar_for_the_owner(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        row = make_row("done-key", "https://download.example.net/a.mp3",
                       status="downloading", updated=10, cancel=True)
        write_store(path, [row])
        with open(path + ".cancel", "w", encoding="utf-8") as handle:
            json.dump(["done-key"], handle)
        queue = self.queue(local_workers=False, path=path)
        self.assertTrue(queue._cancel_requested("done-key"))
        self.assertEqual(queue._row("done-key")["status"], "cancelled")

    def test_owner_terminalizes_a_queued_cancel_without_a_worker(self):
        modules, downloads = fake_modules([])
        queue = self.queue(modules, local_workers=True)
        seed(queue, "queued", "https://download.example.net/q.mp3",
             status="queued", updated=100)
        queue.cancel("queued")
        self.assertIn(queue._row("queued")["status"], ("cancelled", "cancelling"))
        queue._pump()
        self.assertEqual(queue._row("queued")["status"], "cancelled")
        self.assertFalse(queue.active())
        self.assertFalse(queue._cancel_requested("queued"))

    def test_owner_drain_then_cross_process_retry_downloads(self):
        url = "https://download.example.net/retry.mp3"
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        modules, downloads = fake_modules([])
        window = self.queue(modules, local_workers=False, path=path)
        self.assertTrue(window.start(url, "Set", "mediafire", key="K")[0])
        self.assertTrue(window.cancel("K"))
        self.assertTrue(window._cancel_requested("K"))

        owner = self.queue(modules, local_workers=True, path=path)
        owner.resume()
        self.assertFalse(owner.active())
        self.assertFalse(owner._cancel_requested("K"))
        self.assertEqual(owner._row("K")["status"], "cancelled")

        # The window sees the owner's newer terminal row and may retry.
        window.refresh()
        self.assertEqual(window._row("K")["status"], "cancelled")
        self.assertTrue(window.start(url, "Retry", "mediafire", key="K")[0])
        owner.resume()
        self.assertTrue(self.wait_until(
            lambda: downloads.download_calls >= 1))
        self.assertTrue(self.wait_until(lambda: not owner._running))
        self.assertIsNone(owner._row("K"))
        self.assertEqual(downloads.download_calls, 1)

    # ---------------------------------------------------------- save gate
    def _fail_store_write(self, path):
        original = dqmod._write_json_atomic

        def write(current, value, description, log):
            if current == path:
                return False
            return original(current, value, description, log)

        return mock.patch.object(dqmod, "_write_json_atomic", write)

    def test_failed_store_write_keeps_the_sidecar_on_finish(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        url = "https://download.example.net/fail.mp3"
        write_store(path, [make_row("K", url, status="downloading",
                                   updated=10)])
        modules, downloads = fake_modules([])
        queue = self.queue(modules, local_workers=False, path=path)
        queue._request_cancel("K")
        with self._fail_store_write(path):
            queue._finish("K", "cancelled", "cancelled by user")
        self.assertTrue(queue._cancel_requested("K"))
        rows, _removed = read_store(path)
        self.assertEqual(rows[0]["status"], "downloading")
        # A later owner with a working store must terminalize, not requeue.
        owner = self.queue(modules, local_workers=True, path=path)
        self.assertEqual(owner._row("K")["status"], "cancelled")
        self.assertFalse(owner._cancel_requested("K"))
        self.assertFalse(owner.active())

    def test_failed_store_write_keeps_the_sidecar_on_owner_load(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        url = "https://download.example.net/load.mp3"
        write_store(path, [make_row("K", url, status="downloading",
                                   updated=10)])
        with open(path + ".cancel", "w", encoding="utf-8") as handle:
            json.dump(["K"], handle)
        modules, downloads = fake_modules([])
        with self._fail_store_write(path):
            owner = self.queue(modules, local_workers=True, path=path)
        self.assertTrue(owner._cancel_requested("K"))
        rows, _removed = read_store(path)
        self.assertEqual(rows[0]["status"], "downloading")
        # Re-load with a working store: the durable sidecar still terminalizes.
        recovery = self.queue(modules, local_workers=True, path=path)
        self.assertEqual(recovery._row("K")["status"], "cancelled")
        self.assertFalse(recovery._cancel_requested("K"))

    # ------------------------------------------------ cross-process merge
    def test_stale_window_write_cannot_overwrite_newer_owner_row(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        url = "https://download.example.net/progress.mp3"
        write_store(path, [make_row(
            "K", url, status="downloading", updated=200,
            percent=42, done=42, total=100)])
        window = self.queue(local_workers=False, path=path)
        with window._lock:
            window._items["K"]["updated"] = 100
            window._items["K"]["percent"] = 5
            window._items["K"]["status"] = "queued"
        self.assertTrue(window._save_now())
        rows, _removed = read_store(path)
        self.assertEqual(rows[0]["updated"], 200)
        self.assertEqual(rows[0]["percent"], 42)
        self.assertEqual(rows[0]["status"], "downloading")

    def test_local_cancel_with_newer_updated_wins_the_merge(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        url = "https://download.example.net/cancel-win.mp3"
        write_store(path, [make_row("K", url, status="downloading",
                                   updated=100)])
        window = self.queue(local_workers=False, path=path)
        with window._lock:
            window._items["K"]["updated"] = 200
            window._items["K"]["status"] = "cancelling"
            window._items["K"]["cancel"] = True
        window._save_now()
        rows, _removed = read_store(path)
        self.assertEqual(rows[0]["status"], "cancelling")
        self.assertTrue(rows[0]["cancel"])
        self.assertEqual(rows[0]["updated"], 200)

    def test_stale_window_write_cannot_resurrect_a_removed_row(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        url = "https://download.example.net/removed.mp3"
        now = time.time()
        write_store(path, [], {"K": now})
        window = self.queue(local_workers=False, path=path)
        seed(window, "K", url, status="downloading", updated=now - 100)
        window._save_now()
        rows, removed = read_store(path)
        self.assertEqual(rows, [])
        self.assertEqual(removed, {"K": now})

    def test_refresh_drops_a_ghost_row_the_owner_completed(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        url = "https://download.example.net/ghost.mp3"
        write_store(path, [], {"K": 300})
        window = self.queue(local_workers=False, path=path)
        seed(window, "K", url, status="downloading", updated=100)
        window.refresh()
        self.assertIsNone(window._row("K"))
        self.assertEqual(window.rows(), [])

    def test_stale_window_cancel_cannot_resurrect_a_completed_row(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        url = "https://download.example.net/stale-cancel.mp3"
        now = time.time()
        write_store(path, [make_row("K", url, status="downloading",
                                   updated=now)])
        window = self.queue(local_workers=False, path=path)
        owner_modules, downloads = fake_modules([])
        owner = self.queue(owner_modules, local_workers=True, path=path)
        owner._run_one("K")
        self.assertIsNone(owner._row("K"))

        self.assertFalse(window.cancel("K"))
        rows, removed = read_store(path)
        self.assertEqual(rows, [])
        self.assertIn("K", removed)
        self.assertIsNone(window._row("K"))

    def test_window_start_after_owner_completion_keeps_only_the_new_row(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        done_url = "https://download.example.net/completed.mp3"
        write_store(path, [make_row("K", done_url, status="downloading",
                                   updated=100)])
        window = self.queue(local_workers=False, path=path)

        owner_modules, downloads = fake_modules([])
        owner = self.queue(owner_modules, local_workers=True, path=path)
        owner._run_one("K")
        self.assertIsNone(owner._row("K"))
        rows, removed = read_store(path)
        self.assertEqual(rows, [])
        self.assertIn("K", removed)

        new_url = "https://download.example.net/new.mp3"
        self.assertTrue(window.start(new_url, "New", "mediafire", key="B")[0])
        rows, removed = read_store(path)
        self.assertEqual([row["key"] for row in rows], ["B"])
        self.assertIn("K", removed)


if __name__ == "__main__":
    unittest.main()
