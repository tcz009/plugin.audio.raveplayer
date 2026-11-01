# -*- coding: utf-8 -*-
"""Offline tests for curated Mixcloud sources."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import mixcloud  # noqa: E402

PAYLOAD = {
    "data": [
        {
            "name": "Skream – Watch The Ride [2008]",
            "url": "https://www.mixcloud.com/getdarker/skream-watch-the-ride-2008/",
            "created_time": "2021-03-15T14:45:05Z",
            "audio_length": 3600000,
            "user": {"name": "GetDarker"},
            "pictures": {"medium": "https://thumbnailer.mixcloud.com/x.jpg"},
        },
        {"name": "Bad page", "url": "https://evil.example/nope/"},
        "not a dict",
    ]
}


class MixcloudTests(unittest.TestCase):
    def test_registry_has_the_two_curated_sources(self):
        keys = [source["key"] for source in mixcloud.registry()]
        self.assertEqual(keys, ["rave-archive-uk", "getdarker"])
        self.assertEqual(mixcloud.source("getdarker")["account"], "getdarker")
        self.assertIsNone(mixcloud.source("nope"))

    def test_cloudcasts_maps_api_rows_and_filters_bad_urls(self):
        with mock.patch.object(mixcloud.http, "fetch_json", return_value=PAYLOAD) as fetch:
            rows = mixcloud.cloudcasts("getdarker", limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Skream – Watch The Ride [2008]")
        self.assertTrue(rows[0]["url"].startswith("https://www.mixcloud.com/getdarker/"))
        self.assertEqual(rows[0]["user"], "GetDarker")
        self.assertEqual(fetch.call_args[1]["ttl"], mixcloud.ACCOUNT_TTL)

    def test_cloudcasts_are_fail_soft(self):
        for payload in (None, [], {"data": None}, {"data": "nope"}):
            with mock.patch.object(mixcloud.http, "fetch_json", return_value=payload):
                self.assertEqual(mixcloud.cloudcasts("getdarker"), [])

    def test_invalid_account_never_fetches(self):
        for account in ("", "../etc/passwd", "a b", "a/b"):
            with mock.patch.object(mixcloud.http, "fetch_json") as fetch:
                self.assertEqual(mixcloud.cloudcasts(account), [])
            self.assertFalse(fetch.called)


if __name__ == "__main__":
    unittest.main()
