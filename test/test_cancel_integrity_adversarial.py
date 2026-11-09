# -*- coding: utf-8 -*-
"""Adversarial cancel/data-integrity tests for the screen download queue."""

import json
import os
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "script.raveplayer.ui"))

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


def seed(queue, key, url, status="queued", **extra):
    row = {"key": key, "title": key, "source": "mediafire", "url": url,
           "status": status, "percent": 0, "done": 0, "total": 0,
           "detail": "", "started": 0.0, "cancel": False, "updated": 0.0}
    row.update(extra)
    queue._items[key] = row
    if key not in queue._order:
        queue._order.append(key)
    return row


class CancelIntegrityTests(unittest.TestCase):
    def test_cancelled_duplicate_never_deletes_a_completed_same_url(self):
        url = "https://download.example.net/x.mp3"
        modules, downloads = fake_modules([{"key": "A", "url": url}])
        queue = DownloadQueue(modules=modules, local_workers=False,
                              store_path=os.path.join(tempfile.mkdtemp(), "q.json"))
        seed(queue, "A", url, status="done")
        seed(queue, "B", url, status="cancelling", cancel=True)
        queue._finish("B", "cancelled", "cancelled by user")
        self.assertNotIn("A", downloads.deleted)
        self.assertEqual([row["key"] for row in downloads.rows], ["A"])

    def test_user_cancel_deletes_only_its_own_completed_key(self):
        url = "https://download.example.net/y.mp3"
        modules, downloads = fake_modules([
            {"key": "A", "url": url}, {"key": "B", "url": url}])
        queue = DownloadQueue(modules=modules, local_workers=False,
                              store_path=os.path.join(tempfile.mkdtemp(), "q.json"))
        seed(queue, "B", url, status="cancelling", cancel=True)
        queue._finish("B", "cancelled", "user")
        self.assertEqual(downloads.deleted, ["B"])
        self.assertEqual([row["key"] for row in downloads.rows], ["A"])

    def test_queued_cancel_sidecar_does_not_poison_a_retry(self):
        url = "https://download.example.net/z.mp3"
        modules, downloads = fake_modules([])
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        queue = DownloadQueue(modules=modules, local_workers=True, store_path=path)
        queue._request_cancel("retry-key")
        self.assertTrue(queue._cancel_requested("retry-key"))
        ok, _ = queue.start(url, "Retry", "mediafire", key="retry-key")
        self.assertTrue(ok)
        self.assertFalse(queue._cancel_requested("retry-key"))

    def test_terminal_row_drops_its_persisted_cancel_on_load(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        row = {"key": "done-key", "title": "t", "source": "mediafire",
               "url": "https://download.example.net/a.mp3", "status": "cancelled",
               "percent": 0, "done": 0, "total": 0, "detail": "", "started": 0,
               "cancel": True, "updated": 0}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([row], handle)
        with open(path + ".cancel", "w", encoding="utf-8") as handle:
            json.dump(["done-key"], handle)
        queue = DownloadQueue(modules=fake_modules()[0], local_workers=True,
                              store_path=path)
        self.assertFalse(queue._cancel_requested("done-key"))

    def test_screen_queue_deletes_its_own_completed_row(self):
        url = "https://download.example.net/s.mp3"
        modules, downloads = fake_modules([{"key": "S", "url": url}])
        queue = DownloadQueue(modules=None, local_workers=False,
                              store_path=os.path.join(tempfile.mkdtemp(), "q.json"))
        queue._modules = modules  # screen-style lazy modules hook
        queue._delete_completed("S", url)
        self.assertEqual(downloads.deleted, ["S"])


    def test_window_keeps_the_sidecar_for_the_owner(self):
        path = os.path.join(tempfile.mkdtemp(), "q.json")
        row = {"key": "done-key", "title": "t", "source": "mediafire",
               "url": "https://download.example.net/a.mp3", "status": "downloading",
               "percent": 0, "done": 0, "total": 0, "detail": "", "started": 0,
               "cancel": True, "updated": 0}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([row], handle)
        with open(path + ".cancel", "w", encoding="utf-8") as handle:
            json.dump(["done-key"], handle)
        queue = DownloadQueue(modules=fake_modules()[0], local_workers=False,
                              store_path=path)
        self.assertTrue(queue._cancel_requested("done-key"))
        self.assertEqual(queue._row("done-key")["status"], "cancelled")

    def test_owner_terminalizes_a_queued_cancel_without_a_worker(self):
        modules, downloads = fake_modules([])
        queue = DownloadQueue(modules=modules, local_workers=True,
                              store_path=os.path.join(tempfile.mkdtemp(), "q.json"))
        seed(queue, "queued", "https://download.example.net/q.mp3",
             status="queued")
        queue.cancel("queued")
        assert queue._row("queued")["status"] in ("cancelled", "cancelling")
        queue._pump()
        self.assertEqual(queue._row("queued")["status"], "cancelled")
        self.assertFalse(queue.active())
        self.assertFalse(queue._cancel_requested("queued"))

    def test_cancelling_an_active_duplicate_does_not_delete_a_completion(self):
        url = "https://download.example.net/dup.mp3"
        modules, downloads = fake_modules([{"key": "sha1", "url": url}])
        queue = DownloadQueue(modules=modules, local_workers=False,
                              store_path=os.path.join(tempfile.mkdtemp(), "q.json"))
        seed(queue, "A", url, status="done")
        seed(queue, "B", url, status="queued")
        queue.cancel("B")
        self.assertEqual(downloads.deleted, [])

    def test_cancelling_a_completed_row_may_delete_by_url(self):
        url = "https://download.example.net/done.mp3"
        modules, downloads = fake_modules([{"key": "sha1", "url": url}])
        queue = DownloadQueue(modules=modules, local_workers=False,
                              store_path=os.path.join(tempfile.mkdtemp(), "q.json"))
        seed(queue, "screen-key", url, status="done")
        queue.cancel("screen-key")
        self.assertEqual(downloads.deleted, ["sha1"])

    def test_late_finish_of_a_duplicate_never_touches_the_completion(self):
        url = "https://download.example.net/late.mp3"
        modules, downloads = fake_modules([{"key": "A", "url": url}])
        queue = DownloadQueue(modules=modules, local_workers=False,
                              store_path=os.path.join(tempfile.mkdtemp(), "q.json"))
        seed(queue, "A", url, status="done")
        seed(queue, "B", url, status="downloading", cancel=True)
        queue._finish("B", "cancelled", "late cancel")
        self.assertEqual(downloads.deleted, [])
        self.assertEqual([row["key"] for row in downloads.rows], ["A"])


if __name__ == "__main__":
    unittest.main()
