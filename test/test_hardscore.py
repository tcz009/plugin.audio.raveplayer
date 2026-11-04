# -*- coding: utf-8 -*-
"""Offline tests for the Hardscore RSS/page adapter."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import hardscore  # noqa: E402

RSS = """<?xml version="1.0"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
 <channel>
  <item>
   <title>Force of One Crew &#8211; Weekend Rush 92.3 FM [June 1993]</title>
   <link>https://www.hardscore.com/?p=11680</link>
   <pubDate>Wed, 22 Nov 2023 20:00:00 +0000</pubDate>
   <description><![CDATA[<a href="https://hardscore.com/mixes/Radio/WeekendRush/1993-06.mp3">Download</a>]]></description>
   <enclosure url="https://hardscore.com/mixes/Radio/WeekendRush/1993-06.mp3" type="audio/mpeg"/>
  </item>
  <item>
   <title>Event post without audio</title>
   <link>https://www.hardscore.com/?p=999</link>
   <pubDate>Mon, 01 Jan 2024 10:00:00 +0000</pubDate>
   <description><![CDATA[Tracklist only]]></description>
  </item>
 </channel>
</rss>"""

PAGE = """<html><head><title>Force of One Crew</title></head><body>
<h1>Force of One Crew – Weekend Rush</h1>
<a href="https://hardscore.com/mixes/Radio/WeekendRush/1993-06.mp3">Download</a>
<a href="https://www.mixcloud.com/Hardscore/force-of-one/">Mixcloud</a>
</body></html>"""


class HardscoreTests(unittest.TestCase):
    def setUp(self):
        self.safe = mock.patch.object(hardscore.http, "safe_stream_url",
                                      side_effect=lambda url: url)
        self.safe.start()
        self.addCleanup(self.safe.stop)

    def test_parse_feed_keeps_enclosures_and_post_links(self):
        rows = hardscore.parse_feed(RSS)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["date"], "2023-11-22")
        self.assertEqual(rows[0]["page_url"], "https://www.hardscore.com/?p=11680")
        self.assertTrue(rows[0]["media_urls"][0].endswith(".mp3"))
        self.assertEqual(rows[1]["media_urls"], [])
        self.assertEqual(rows[1]["page_url"], "https://www.hardscore.com/?p=999")

    def test_items_are_fail_soft(self):
        with mock.patch.object(hardscore.http, "fetch", return_value=None):
            self.assertEqual(hardscore.items(), [])

    def test_items_fetch_uses_cache_and_browser_ua(self):
        with mock.patch.object(hardscore.http, "fetch", return_value=RSS) as download:
            rows = hardscore.items(limit=5)
        self.assertEqual(len(rows), 2)
        self.assertEqual(download.call_args[1]["ttl"], hardscore.FEED_TTL)
        self.assertEqual(download.call_args[1]["headers"]["User-Agent"],
                         hardscore.BROWSER_UA)

    def test_page_extracts_media_and_external_links(self):
        details = hardscore.parse_page(PAGE, "https://www.hardscore.com/?p=1")
        self.assertEqual(details["title"], "Force of One Crew – Weekend Rush")
        self.assertTrue(details["media_urls"][0].endswith(".mp3"))
        self.assertIn("https://www.mixcloud.com/Hardscore/force-of-one/",
                      details["links"])

    def test_media_url_with_literal_entity_is_decoded_once(self):
        # The filename on the server is literally "A_&amp;_B.mp3", so the RSS
        # carries "&amp;amp;". The URL must keep the literal "&amp;".
        rows = hardscore.parse_feed(RSS.replace(
            "1993-06.mp3", "A_&amp;amp;_B.mp3"))
        self.assertEqual(rows[0]["media_urls"],
                         ["https://hardscore.com/mixes/Radio/WeekendRush/A_&amp;_B.mp3"])

    def test_media_urls_drop_non_http_and_dedupe(self):
        rows = hardscore.parse_feed(RSS.replace(
            "1993-06.mp3", "A.mp3"))
        self.assertEqual(len(rows[0]["media_urls"]), 1)
        self.assertEqual(hardscore._media_urls(
            "file:///tmp/x.mp3 javascript:x https://hardscore.com/a.mp3 "
            "https://hardscore.com/a.mp3 https://hardscore.com/b.mp3"),
            ["https://hardscore.com/a.mp3", "https://hardscore.com/b.mp3"])

    def test_page_rejects_non_hardscore_hosts(self):
        with mock.patch.object(hardscore.http, "fetch") as download:
            self.assertEqual(hardscore.page("https://evil.example/x"), {})
        self.assertFalse(download.called)

    def test_page_failure_is_soft(self):
        with mock.patch.object(hardscore.http, "fetch", return_value=None):
            self.assertEqual(hardscore.page("https://www.hardscore.com/?p=1"), {})


if __name__ == "__main__":
    unittest.main()
