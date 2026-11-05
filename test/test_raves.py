# -*- coding: utf-8 -*-
"""The researched rave catalogue that ships inside the add-on."""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)


class RaveCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(ROOT, "resources", "rave-catalog.json")
        with open(path, encoding="utf-8") as handle:
            cls.data = json.load(handle)

    def test_catalogue_ships_with_the_addon(self):
        self.assertGreaterEqual(len(self.data), 40)
        for entry in self.data:
            self.assertTrue(entry["name"])
            self.assertIsInstance(entry["archive_count"], int)
            if entry["archive_count"] > 0:
                # Anything the Rave Nights menu can show needs an Archive query.
                self.assertTrue(entry.get("archive_query"), entry["name"])
            else:
                # 22 researched rows are Mixcloud-only: archive_query is null
                # and the loader filters them out, so no query is expected.
                self.assertIn(entry.get("archive_query"), (None, ""), entry["name"])

    def test_catalogue_loader_matches_the_web_registry(self):
        from resources.lib import routes
        entries = routes._rave_catalog()
        self.assertTrue(entries, "loader should return catalogue entries")
        # Archive-only rows carry a query; Mixcloud-only rows carry the
        # Mixcloud query.  Nothing without either should be listed.
        for entry in entries:
            self.assertTrue(entry["count"] or entry["mixcloud_count"], entry["name"])
            if entry["count"]:
                self.assertTrue(entry["query"], entry["name"])
            if entry["mixcloud_count"]:
                self.assertTrue(entry["mixcloud_query"], entry["name"])
        self.assertEqual(
            entries, sorted(entries, key=lambda item: item["name"].lower())
        )
        self.assertEqual(len(entries), len(self.data))


if __name__ == "__main__":
    unittest.main()
