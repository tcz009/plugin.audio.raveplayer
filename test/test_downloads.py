# -*- coding: utf-8 -*-
"""Offline tests for explicit downloads (xbmcvfs mocked by the stub)."""

import contextlib
import os
import shutil
import sys
import tempfile
import unittest
from email.message import Message
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import downloads  # noqa: E402

URL = "https://archive.org/download/pack/1.mp3"


class FakeResponse(object):
    def __init__(self, body, content_type="audio/mpeg", length=None, fail=False):
        self.body = body
        self.offset = 0
        self.fail = fail
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(body) if length is None else length)

    def read(self, size=-1):
        if self.fail:
            raise OSError("connection lost")
        if size is None or size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


@contextlib.contextmanager
def stream(response):
    yield response


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rave-dl-")
        os.environ[downloads.DIR_ENV] = self.directory

    def tearDown(self):
        os.environ.pop(downloads.DIR_ENV, None)
        shutil.rmtree(self.directory, ignore_errors=True)

    def _plan(self, body=b"x" * 2048, **overrides):
        filename = "test-abcdef12.mp3"
        plan = {
            "allowed": True, "reason": "", "url": URL, "title": "Test Set",
            "source": "Archive.org", "size": len(body), "free": 10 * 1024 * 1024,
            "filename": filename, "path": os.path.join(self.directory, filename),
            "existing": False, "key": downloads._key(URL), "content_type": "audio/mpeg",
        }
        plan.update(overrides)
        return plan

    # -------------------------------------------------------------- predicate
    def test_eligible_sources_and_extensions(self):
        with mock.patch.object(downloads.http, "safe_stream_url", side_effect=lambda u: u):
            self.assertTrue(downloads.eligible(URL, "Archive.org"))
            self.assertTrue(downloads.eligible(
                "https://hardscore.com/mixes/a.m4a", "Hardscore.com"))
            self.assertTrue(downloads.eligible(
                "https://enceladus.feralhosting.com/moxser/a.mp3", "Moxser.com"))
            self.assertTrue(downloads.eligible(
                "https://hardscore.com/mixes/Radio/WeekendRush/a.mp3",
                "Pirate Radio Archives"))
            self.assertFalse(downloads.eligible(URL, "Podcasts"))
            self.assertFalse(downloads.eligible("https://archive.org/a.wav", "Archive.org"))
            self.assertFalse(downloads.eligible(
                "https://www.mixcloud.com/getdarker/a.mp3", "Archive.org"))
            self.assertFalse(downloads.eligible(
                "https://evil.example/a.mp3", "Archive.org"))
            self.assertFalse(downloads.eligible(
                "https://user:pass@archive.org/a.mp3", "Archive.org"))

    def test_platform_urls_are_never_eligible(self):
        for url in ("https://www.mixcloud.com/a/b.mp3",
                    "https://soundcloud.com/a/b.mp3",
                    "https://youtu.be/abc.mp3"):
            self.assertFalse(downloads.eligible(url, "Archive.org"))

    # --------------------------------------------------------------- filename
    def test_filename_is_sanitised_and_hashed(self):
        name = downloads.sanitize_filename("../../EVIL: TAPE? *|<>", URL)
        self.assertNotIn("/", name)
        self.assertNotIn("\\", name)
        self.assertNotIn(":", name)
        self.assertTrue(name.endswith(".mp3"))
        self.assertRegex(name, r"^[a-z0-9-]+-[0-9a-f]{8}\.mp3$")
        self.assertLessEqual(len(name), 100)
        self.assertTrue(downloads.sanitize_filename("Café Mix", URL, ".m4a").endswith(".m4a"))
        self.assertTrue(downloads.sanitize_filename("", URL).startswith("rave-player-"))

    # ------------------------------------------------------------------- plan
    def _plan_patches(self, size=1024, content_type="audio/mpeg", free=1024 * 1024 * 1024):
        return [
            mock.patch.object(downloads, "eligible", return_value=True),
            mock.patch.object(downloads.http, "probe_media",
                              return_value={"size": size, "content_type": content_type,
                                            "final_url": URL}),
            mock.patch.object(downloads, "free_bytes", return_value=free),
            mock.patch.object(downloads, "total_saved_bytes", return_value=0),
        ]

    def test_plan_accepts_a_valid_file(self):
        patches = self._plan_patches()
        with patches[0], patches[1], patches[2], patches[3]:
            plan = downloads.plan(URL, "Test Set", "Archive.org")
        self.assertTrue(plan["allowed"], plan)
        self.assertEqual(plan["size"], 1024)
        self.assertRegex(downloads.sanitize_filename("Test Set", URL),
                         r"^test-set-[0-9a-f]{8}\.mp3$")

    def test_plan_refuses_low_space(self):
        patches = self._plan_patches(size=1024, free=downloads.MIN_FREE_BYTES)
        with patches[0], patches[1], patches[2], patches[3]:
            plan = downloads.plan(URL, "Test Set", "Archive.org")
        self.assertFalse(plan["allowed"])
        self.assertIn("space", plan["reason"].lower())

    def test_plan_refuses_bad_type_size_and_caps(self):
        cases = [
            dict(content_type="text/html"),
            dict(size=0),
            dict(size=downloads.MAX_FILE_BYTES + 1),
        ]
        for case in cases:
            patches = self._plan_patches(**case)
            with patches[0], patches[1], patches[2], patches[3]:
                self.assertFalse(downloads.plan(URL, "Set", "Archive.org")["allowed"], case)
        patches = self._plan_patches()
        with patches[0], patches[1], patches[2], \
                mock.patch.object(downloads, "total_saved_bytes",
                                  return_value=downloads.MAX_TOTAL_BYTES):
            self.assertFalse(downloads.plan(URL, "Set", "Archive.org")["allowed"])

    def test_plan_refuses_unverifiable_probe(self):
        with mock.patch.object(downloads, "eligible", return_value=True), \
                mock.patch.object(downloads.http, "probe_media", return_value={}):
            plan = downloads.plan(URL, "Set", "Archive.org")
        self.assertFalse(plan["allowed"])

    # --------------------------------------------------------------- download
    def test_success_is_atomic_and_indexed(self):
        body = b"x" * 5000
        plan = self._plan(body)
        progress = []
        with mock.patch.object(downloads.http, "open_media",
                               return_value=stream(FakeResponse(body))):
            result = downloads.download(plan, progress=lambda d, t: progress.append(d))
        self.assertTrue(result["ok"], result)
        self.assertTrue(os.path.exists(plan["path"]))
        self.assertFalse(os.path.exists(plan["path"] + ".part"))
        self.assertEqual(open(plan["path"], "rb").read(), body)
        rows = downloads.list_downloads()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Test Set")
        self.assertEqual(rows[0]["size"], len(body))
        self.assertTrue(progress)

    def test_cancel_leaves_no_file_or_metadata(self):
        plan = self._plan()
        result = downloads.download(plan, cancelled=lambda: True)
        self.assertFalse(result["ok"])
        self.assertIn("cancel", result["reason"].lower())
        self.assertFalse(os.path.exists(plan["path"]))
        self.assertFalse(os.path.exists(plan["path"] + ".part"))
        self.assertEqual(downloads.list_downloads(), [])

    def test_failure_cleans_partial_file(self):
        plan = self._plan()
        with mock.patch.object(downloads.http, "open_media",
                               return_value=stream(FakeResponse(b"x" * 10, fail=True))):
            result = downloads.download(plan)
        self.assertFalse(result["ok"])
        self.assertFalse(os.path.exists(plan["path"]))
        self.assertFalse(os.path.exists(plan["path"] + ".part"))
        self.assertEqual(downloads.list_downloads(), [])

    def test_bad_content_type_cleans_up(self):
        plan = self._plan()
        with mock.patch.object(downloads.http, "open_media",
                               return_value=stream(FakeResponse(b"x", content_type="text/html"))):
            self.assertFalse(downloads.download(plan)["ok"])
        self.assertFalse(os.path.exists(plan["path"]))
        self.assertEqual(downloads.list_downloads(), [])

    def test_overwrite_replaces_existing_file(self):
        plan = self._plan(b"new" * 1000)
        os.makedirs(self.directory, exist_ok=True)
        with open(plan["path"], "wb") as handle:
            handle.write(b"old")
        with mock.patch.object(downloads.http, "open_media",
                               return_value=stream(FakeResponse(b"new" * 1000))):
            self.assertTrue(downloads.download(plan)["ok"])
        self.assertEqual(open(plan["path"], "rb").read(), b"new" * 1000)
        self.assertEqual(len(downloads.list_downloads()), 1)

    # ----------------------------------------------------------- list/delete
    def test_delete_removes_file_and_metadata(self):
        plan = self._plan()
        with mock.patch.object(downloads.http, "open_media",
                               return_value=stream(FakeResponse(b"x" * 100))):
            self.assertTrue(downloads.download(plan)["ok"])
        self.assertTrue(downloads.delete(plan["key"]))
        self.assertFalse(os.path.exists(plan["path"]))
        self.assertEqual(downloads.list_downloads(), [])

    def test_missing_file_is_listed_and_delete_cleans_metadata(self):
        downloads._save_index([{
            "key": "gone", "filename": "gone-12345678.mp3", "title": "Gone",
            "source": "Archive.org", "url": URL, "size": 10, "added": "2026-01-01T00:00:00Z",
        }])
        rows = downloads.list_downloads()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["missing"])
        self.assertTrue(downloads.delete("gone"))
        self.assertEqual(downloads.list_downloads(), [])

    def test_stale_part_is_removed_on_download(self):
        plan = self._plan()
        with open(plan["path"] + ".part", "wb") as handle:
            handle.write(b"stale")
        with mock.patch.object(downloads.http, "open_media",
                               return_value=stream(FakeResponse(b"x" * 100))):
            self.assertTrue(downloads.download(plan)["ok"])
        self.assertFalse(os.path.exists(plan["path"] + ".part"))

    def test_total_saved_bytes_and_format(self):
        self.assertEqual(downloads.format_size(0), "0 B")
        self.assertTrue(downloads.format_size(1024 * 1024).endswith("MB"))


if __name__ == "__main__":
    unittest.main()
