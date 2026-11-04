# -*- coding: utf-8 -*-
"""Offline tests for the on-disk response cache (no network, no Kodi)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

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

    def test_has_matches_get_for_fresh_and_stale_entries(self):
        self.assertFalse(cache.has("has-key", 60))
        self.assertTrue(cache.put("has-key", {"value": 1}))
        self.assertTrue(cache.has("has-key", 60))
        self.assertFalse(cache.has("has-key", 1, now=cache.time.time() + 10))


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

    def test_entry_without_a_value_is_a_miss(self):
        path = cache.path_for("no-value")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"v": cache.VERSION, "ts": cache.time.time()}, handle)
        self.assertIs(cache.get("no-value", 60), cache.MISSING)
        self.assertFalse(os.path.exists(path))

    def test_entry_with_a_null_value_is_a_miss(self):
        path = cache.path_for("null-value")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"v": cache.VERSION, "ts": cache.time.time(), "value": None}, handle)
        self.assertIs(cache.get("null-value", 60), cache.MISSING)

    def test_remember_never_returns_the_sentinel(self):
        path = cache.path_for("sentinel")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"v": cache.VERSION, "ts": cache.time.time()}, handle)
        self.assertEqual(cache.remember("sentinel", 60, lambda: "fresh"), "fresh")


class CacheMaintenanceTests(unittest.TestCase):
    """The cache directory is bounded and oversized entries cannot be loaded."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="raveplayer-cache-maint-")
        self.old = os.environ.get(cache.CACHE_DIR_ENV)
        os.environ[cache.CACHE_DIR_ENV] = self.directory

    def tearDown(self):
        if self.old is None:
            os.environ.pop(cache.CACHE_DIR_ENV, None)
        else:
            os.environ[cache.CACHE_DIR_ENV] = self.old
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_maintain_removes_expired_entries(self):
        cache.put("old", "value")
        cache.put("fresh", "value")
        old_path = cache.path_for("old")
        now = cache.time.time()
        os.utime(old_path, (now - 10 ** 6, now - 10 ** 6))
        removed = cache.maintain(now=now, max_age=1000)
        self.assertEqual(removed, 1)
        self.assertIs(cache.get("old", 60), cache.MISSING)
        self.assertEqual(cache.get("fresh", 60), "value")

    def test_maintain_caps_the_number_of_entries(self):
        now = cache.time.time()
        for index in range(5):
            cache.put("entry-%d" % index, index)
            path = cache.path_for("entry-%d" % index)
            os.utime(path, (now - 1000 + index, now - 1000 + index))
        removed = cache.maintain(now=now, max_entries=2, max_age=10 ** 9)
        self.assertEqual(removed, 3)
        remaining = [name for name in os.listdir(self.directory) if name.endswith(".json")]
        self.assertEqual(len(remaining), 2)
        self.assertEqual(cache.get("entry-4", 60), 4)

    def test_maintain_removes_stale_temp_files_only(self):
        now = cache.time.time()
        dead = os.path.join(self.directory, ".tmp-dead.json")
        live = os.path.join(self.directory, ".tmp-live.json")
        for path, age in ((dead, 7200), (live, 0)):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{}")
            os.utime(path, (now - age, now - age))
        removed = cache.maintain(now=now, stale_temp=3600)
        self.assertEqual(removed, 1)
        self.assertFalse(os.path.exists(dead))
        self.assertTrue(os.path.exists(live))

    def test_oversized_entry_is_not_loaded(self):
        path = cache.path_for("oversized")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"v": 1, "ts": 1, "value": "x"}')
        with mock.patch.object(cache, "MAX_ENTRY_BYTES", 10):
            self.assertIs(cache.get("oversized", None), cache.MISSING)
        self.assertFalse(os.path.exists(path))

    def test_failed_replace_leaves_no_temp_file_behind(self):
        with mock.patch.object(cache.os, "replace", side_effect=OSError("disk full")):
            self.assertFalse(cache.put("replace-fail", "value"))
        leftovers = [name for name in os.listdir(self.directory) if name.startswith(".tmp-")]
        self.assertEqual(leftovers, [])

    def test_hostile_key_cannot_escape_the_cache_directory(self):
        path = cache.path_for("../../etc/passwd")
        self.assertEqual(os.path.dirname(path), self.directory)


if __name__ == "__main__":
    unittest.main()
