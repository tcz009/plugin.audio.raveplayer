# -*- coding: utf-8 -*-
"""Offline tests for the curated Pirate Radio Archives data."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import pirate  # noqa: E402


class PirateDataTests(unittest.TestCase):
    def test_data_file_has_the_required_schema(self):
        allowed = set(pirate.FIELDS) | {"note"}
        rows = pirate.entries()
        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(set(row).issubset(allowed), row)
            for field in pirate.FIELDS:
                self.assertIn(field, row)
            self.assertIsInstance(row["djs"], list)

    def test_station_grouping_preserves_order(self):
        groups = pirate.stations()
        self.assertEqual([group["station"] for group in groups],
                         ["Risk FM 107.1", "Weekend Rush 92.3", "Flava FM"])
        self.assertEqual(len(pirate.station("Weekend Rush 92.3")["entries"]), 2)

    def test_weekend_rush_entries_have_confirmed_streams(self):
        entries = pirate.station("Weekend Rush 92.3")["entries"]
        years = sorted(entry["year"] for entry in entries)
        self.assertEqual(years, [1993, 1995])
        for entry in entries:
            self.assertTrue(entry["source_url"].startswith("https://www.hardscore.com/"))
            self.assertTrue(entry["stream_url"].startswith("https://hardscore.com/"))

    def test_confirmed_and_unconfirmed_pages_are_kept_apart(self):
        risk = pirate.station("Risk FM 107.1")["entries"]
        confirmed = [entry for entry in risk if entry["stream_url"]]
        self.assertEqual(len(confirmed), 1)
        self.assertTrue(confirmed[0]["stream_url"].endswith("risk_fm_107_1.mp3"))
        pending = [entry for entry in risk if not entry["stream_url"]]
        self.assertEqual(len(pending), 1)
        self.assertTrue(pending[0]["source_url"])
        self.assertTrue(pending[0]["note"])
        flava = pirate.station("Flava FM")["entries"][0]
        self.assertEqual(flava["source_url"], "")
        self.assertIsNone(flava["year"])
        self.assertTrue(flava["note"])

    def test_malformed_rows_and_missing_file_are_ignored(self):
        with mock.patch("builtins.open", side_effect=OSError("missing")):
            self.assertEqual(pirate.entries(), [])
            self.assertEqual(pirate.stations(), [])
        with mock.patch("builtins.open", mock.mock_open(read_data='[{"station": 1}]')):
            self.assertEqual(pirate.entries(), [])


if __name__ == "__main__":
    unittest.main()
