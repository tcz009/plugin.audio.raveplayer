# -*- coding: utf-8 -*-
"""Offline tests for the on-disk response cache (no network, no Kodi)."""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import cache  # noqa: E402


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="raveplayer-cache-test-")
        self.old = os.environ.get(cache.CACHE_DIR_ENV)
        os.environ[cache.CACHE_DIR_ENV] = self.directory

    def tearDown(self):
        if self.old is None:
            os.environ.pop(cache.CACHE_DIR_ENV, None)
        else:
            os.environ[cache.CACHE_DIR_ENV] = self.old
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_missing_key_returns_sentinel(self):
        self.assertIs(cache.get("never-written", 60), cache.MISSING)

    def test_round_trip_preserves_unicode(self):
        value = {"title": "Café — jungle", "items": [1, 2, 3]}
        self.assertTrue(cache.put("round-trip", value))
        self.assertEqual(cache.get("round-trip", 60), value)

    def test_path_lives_under_configured_directory(self):
        path = cache.path_for("where")
        self.assertEqual(os.path.dirname(path), self.directory)
        self.assertTrue(path.endswith(".json"))

    def test_expired_entry_is_a_miss(self):
        cache.put("old", "stale")
        self.assertIs(cache.get("old", 60, now=cache.time.time() + 61), cache.MISSING)

    def test_none_ttl_never_expires(self):
        cache.put("forever", "value")
        self.assertEqual(cache.get("forever", None, now=cache.time.time() + 10 ** 6), "value")

    def test_future_timestamp_is_treated_as_stale(self):
        cache.put("clock-skew", "value")
        self.assertIs(cache.get("clock-skew", 60, now=cache.time.time() - 60), cache.MISSING)

    def test_corrupt_json_is_ignored_and_removed(self):
        path = cache.path_for("corrupt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertIs(cache.get("corrupt", 60), cache.MISSING)
        self.assertFalse(os.path.exists(path))

    def test_wrong_version_is_ignored(self):
        path = cache.path_for("version")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"v": 999, "ts": cache.time.time(), "value": "old"}, handle)
        self.assertIs(cache.get("version", 60), cache.MISSING)
        self.assertFalse(os.path.exists(path))

    def test_unserialisable_value_is_not_written(self):
        self.assertFalse(cache.put("object", object()))
        self.assertIs(cache.get("object", 60), cache.MISSING)

    def test_remember_calls_producer_once(self):
        calls = []

        def producer():
            calls.append(1)
            return "produced"

        self.assertEqual(cache.remember("remember", 60, producer), "produced")
        self.assertEqual(cache.remember("remember", 60, producer), "produced")
        self.assertEqual(len(calls), 1)

    def test_remember_does_not_cache_failures(self):
        calls = []

        def producer():
            calls.append(1)
            return None

        self.assertIsNone(cache.remember("failure", 60, producer))
        self.assertIsNone(cache.remember("failure", 60, producer))
        self.assertEqual(len(calls), 2)

    def test_disk_errors_are_best_effort(self):
        # Point the cache at a regular file so both mkdir and open fail.
        blocker = os.path.join(self.directory, "not-a-directory")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("x")
        os.environ[cache.CACHE_DIR_ENV] = blocker
        self.assertFalse(cache.put("disk", "value"))
        self.assertIs(cache.get("disk", 60), cache.MISSING)


if __name__ == "__main__":
    unittest.main()
