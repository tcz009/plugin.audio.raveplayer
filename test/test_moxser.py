# -*- coding: utf-8 -*-
"""Offline tests for the Moxser sitemap/page adapter."""

import os
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import moxser  # noqa: E402

INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
 <sitemap><loc>https://moxser.com/sitemaps-1-section-mixes-1-sitemap-p1.xml</loc></sitemap>
 <sitemap><loc>https://moxser.com/sitemaps-1-section-cookiePolicy-1-sitemap.xml</loc></sitemap>
</sitemapindex>"""

MIXES = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
 <url>
  <loc>https://moxser.com/mixes/loraine-james-resident-advisor-1062-26-october-2026</loc>
  <lastmod>2026-10-26T17:06:25+00:00</lastmod>
  <image:image>
   <image:loc>https://moxser.com/assets/uploads/primary/Loraine-James-1062.jpg</image:loc>
   <image:title>Loraine+James+Resident+Advisor+1062+26+October+2026</image:title>
  </image:image>
 </url>
</urlset>"""

PAGE = """<html><head>
<meta property="og:title" content="Loraine James Resident Advisor 1062 (26 October 2026)">
<meta property="og:image" content="https://moxser.com/assets/uploads/primary/Loraine-James-1062.jpg">
</head><body><h1>Loraine James Resident Advisor 1062</h1>
<a href="https://enceladus.feralhosting.com/moxser/2026/90195/Loraine%20James%201062.mp3">Download</a>
</body></html>"""


class MoxserTests(unittest.TestCase):
    def setUp(self):
        self.interval = moxser.MIN_INTERVAL
        moxser.MIN_INTERVAL = 0
        moxser._last_request = 0.0

    def tearDown(self):
        moxser.MIN_INTERVAL = self.interval
        moxser._last_request = 0.0

    def test_sitemap_index_selects_only_mixes(self):
        self.assertEqual(moxser._sitemap_urls(INDEX),
                         ["https://moxser.com/sitemaps-1-section-mixes-1-sitemap-p1.xml"])
        self.assertEqual(moxser._sitemap_urls("not xml"), [])

    def test_sitemap_rows_have_title_date_and_flyer(self):
        rows = moxser._parse_mixes_sitemap(MIXES)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["title"],
                         "Loraine James Resident Advisor 1062 26 October 2026")
        self.assertEqual(row["date"], "2026-10-26")
        self.assertTrue(row["flyer"].endswith("Loraine-James-1062.jpg"))

    def test_mixes_fetches_index_and_mixes_sitemap_with_cache_and_ua(self):
        def fetch(url, **kwargs):
            if url == moxser.SITEMAP_INDEX:
                return INDEX
            return MIXES
        with mock.patch.object(moxser.http, "fetch", side_effect=fetch) as download:
            rows = moxser.mixes(limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(download.call_count, 2)
        self.assertEqual(download.call_args_list[0][1]["ttl"], moxser.SITEMAP_TTL)
        self.assertEqual(download.call_args_list[0][1]["headers"]["User-Agent"],
                         moxser.BROWSER_UA)

    def test_mix_extracts_title_date_flyer_and_direct_mp3(self):
        with mock.patch.object(moxser.http, "fetch", return_value=PAGE), \
                mock.patch.object(moxser.http, "safe_stream_url",
                                  side_effect=lambda url: url):
            details = moxser.mix(
                "https://moxser.com/mixes/loraine-james-resident-advisor-1062-26-october-2026")
        self.assertEqual(details["title"],
                         "Loraine James Resident Advisor 1062 (26 October 2026)")
        self.assertEqual(details["date"], "2026-10-26")
        self.assertTrue(details["flyer"].endswith("Loraine-James-1062.jpg"))
        self.assertTrue(details["mp3_url"].endswith(".mp3"))

    def test_unsafe_mp3_candidate_is_dropped(self):
        with mock.patch.object(moxser.http, "fetch", return_value=PAGE), \
                mock.patch.object(moxser.http, "safe_stream_url", return_value=""):
            details = moxser.mix(
                "https://moxser.com/mixes/loraine-james-resident-advisor-1062-26-october-2026")
        self.assertEqual(details["mp3_url"], "")

    def test_foreign_or_malformed_page_url_is_never_fetched(self):
        for url in ("https://evil.example/mixes/x", "http://moxser.com/mixes/x",
                    "https://moxser.com/artists/x", "not a url"):
            with mock.patch.object(moxser.http, "fetch") as download:
                self.assertEqual(moxser.mix(url), {})
            self.assertFalse(download.called)

    def test_failures_are_soft(self):
        with mock.patch.object(moxser.http, "fetch", return_value=None):
            self.assertEqual(moxser.mixes(), [])
            self.assertEqual(moxser.mix("https://moxser.com/mixes/a-b"), {})

    def test_rate_limit_sleeps_between_requests(self):
        moxser.MIN_INTERVAL = 1.0
        moxser._last_request = time.monotonic()
        with mock.patch.object(moxser.time, "sleep") as sleep:
            moxser._throttle()
        self.assertTrue(sleep.called)
        self.assertGreater(sleep.call_args[0][0], 0.0)


if __name__ == "__main__":
    unittest.main()
