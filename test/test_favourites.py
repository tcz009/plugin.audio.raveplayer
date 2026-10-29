# -*- coding: utf-8 -*-
"""Offline tests for the favourites store."""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import favourites  # noqa: E402


class FavouriteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rave-fav-")
        os.environ[favourites.FAV_DIR_ENV] = self.directory

    def tearDown(self):
        os.environ.pop(favourites.FAV_DIR_ENV, None)
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_starts_empty(self):
        self.assertEqual(favourites.load(), [])

    def test_add_and_load(self):
        self.assertTrue(favourites.add({"kind": "pack", "target": "dreamscape-19", "title": "Dreamscape XIX"}))
        entries = favourites.load()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Dreamscape XIX")

    def test_add_is_deduplicated_and_moves_to_front(self):
        favourites.add({"kind": "pack", "target": "a", "title": "Pack A"})
        favourites.add({"kind": "pack", "target": "b", "title": "Pack B"})
        favourites.add({"kind": "pack", "target": "a", "title": "Pack A again"})
        entries = favourites.load()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["title"], "Pack A again")

    def test_remove(self):
        favourites.add({"kind": "pack", "target": "a", "title": "Pack A"})
        favourites.remove("pack:a")
        self.assertEqual(favourites.load(), [])

    def test_has(self):
        entry = {"kind": "stream", "target": "http://x/1.mp3", "title": "Episode"}
        favourites.add(entry)
        self.assertTrue(favourites.has(entry))
        self.assertFalse(favourites.has({"kind": "stream", "target": "http://x/2.mp3", "title": "Other"}))

    def test_rejects_entries_without_target(self):
        self.assertFalse(favourites.add({"kind": "pack", "target": "", "title": "Broken"}))

    def test_titles_are_truncated(self):
        favourites.add({"kind": "pack", "target": "x", "title": "T" * 500})
        self.assertEqual(len(favourites.load()[0]["title"]), 200)

    def test_corrupt_file_is_ignored(self):
        with open(os.path.join(self.directory, favourites.FILENAME), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertEqual(favourites.load(), [])

    def test_wrong_shape_is_ignored(self):
        with open(os.path.join(self.directory, favourites.FILENAME), "w", encoding="utf-8") as handle:
            json.dump({"nope": True}, handle)
        self.assertEqual(favourites.load(), [])

    def test_max_entries_cap(self):
        for index in range(favourites.MAX_ENTRIES + 20):
            favourites.add({"kind": "pack", "target": str(index), "title": "Pack %d" % index})
        self.assertEqual(len(favourites.load()), favourites.MAX_ENTRIES)

    def test_missing_kind_becomes_stream(self):
        favourites.save([{"target": "https://x/1.mp3", "title": "Episode"}])
        self.assertEqual(favourites.load()[0]["kind"], "stream")

    def test_unknown_kind_is_not_trusted(self):
        favourites.save([{"kind": "made-up", "target": "x", "title": "Thing"}])
        self.assertEqual(favourites.load()[0]["kind"], "stream")

    def test_entries_without_target_are_dropped_on_load(self):
        with open(os.path.join(self.directory, favourites.FILENAME), "w", encoding="utf-8") as handle:
            json.dump([
                {"kind": "pack", "title": "No target"},
                "not a dict",
                {"kind": "pack", "target": "ok", "title": "Good"},
            ], handle)
        self.assertEqual([entry["target"] for entry in favourites.load()], ["ok"])

    def test_legacy_folder_kinds_round_trip(self):
        favourites.add({"kind": "legacy_pack", "target": "Dreamscape19", "title": "Dreamscape 19"})
        favourites.add({"kind": "legacy_jt", "target": "show-1", "title": "Show 1"})
        self.assertEqual([entry["kind"] for entry in favourites.load()], ["legacy_jt", "legacy_pack"])

    def test_save_replaces_the_file_without_leaving_temporary_files(self):
        favourites.add({"kind": "pack", "target": "old", "title": "Old"})
        self.assertTrue(favourites.save([{"kind": "pack", "target": "new", "title": "New"}]))
        self.assertEqual([entry["target"] for entry in favourites.load()], ["new"])
        leftovers = [name for name in os.listdir(self.directory) if name.startswith(".favourites-")]
        self.assertEqual(leftovers, [])

    def test_save_failure_is_reported(self):
        blocker = os.path.join(self.directory, "not-a-directory")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("x")
        os.environ[favourites.FAV_DIR_ENV] = blocker
        self.assertFalse(favourites.save([{"kind": "pack", "target": "x", "title": "X"}]))


if __name__ == "__main__":
    unittest.main()
