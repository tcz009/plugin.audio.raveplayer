# -*- coding: utf-8 -*-
"""Offline tests for the 2014 blog archives restored in 3.9.61."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)

from resources.lib import legacyblog  # noqa: E402


MIKUS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Mikus Musik</title>
<item>
  <title>House &amp; Garage Classics</title>
  <link>http://mikusmusik.blogspot.com/2026/07/house.html</link>
  <pubDate>Thu, 16 Jul 2026 08:38:20 +0000</pubDate>
  <description>&lt;p&gt;A set&lt;/p&gt;</description>
  <content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/">&lt;iframe src="https://www.mixcloud.com/widget/iframe/?hide_cover=1&amp;amp;feed=%2Fmikus%2Fhouse-garage%2F"&gt;&lt;/iframe&gt;</content:encoded>
</item></channel></rss>"""

DEMODULATED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Demodulated Mixtapes</title>
<item>
  <title>Gulembo &#8211; The Best of The Cave</title>
  <link>http://mixtapes.demodulated.com/gulembo/</link>
  <pubDate>Tue, 31 May 2011 22:42:44 +0000</pubDate>
  <description>&lt;p&gt;Download Full CD&lt;/p&gt;[audio:http://www.demodulated.com/music/mixsets/preview.mp3]</description>
</item></channel></rss>"""


class ParseTests(unittest.TestCase):
    def test_mikus_post_keeps_title_date_and_mixcloud_handoff(self):
        rows = legacyblog.parse_feed(MIKUS, "mikus")
        self.assertEqual(len(rows), 1)
        post = rows[0]
        self.assertEqual(post["title"], "House & Garage Classics")
        self.assertEqual(post["date"], "2026-07-16")
        self.assertEqual(post["page_url"],
                         "http://mikusmusik.blogspot.com/2026/07/house.html")
        self.assertEqual(post["media_urls"], [])
        self.assertEqual(post["mixcloud_urls"],
                         ["https://www.mixcloud.com/mikus/house-garage/"])

    def test_demodulated_post_extracts_the_direct_preview(self):
        rows = legacyblog.parse_feed(DEMODULATED, "demodulated")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"],
                         "Gulembo – The Best of The Cave")
        self.assertEqual(rows[0]["media_urls"],
                         ["http://www.demodulated.com/music/mixsets/preview.mp3"])
        self.assertEqual(rows[0]["mixcloud_urls"], [])

    def test_unsafe_schemes_and_entities_are_ignored(self):
        unsafe = DEMODULATED.replace(
            "http://www.demodulated.com/music/mixsets/preview.mp3",
            "file:///etc/passwd")
        self.assertEqual(legacyblog.parse_feed(unsafe, "demodulated")[0]
                         ["media_urls"], [])
        self.assertEqual(legacyblog.parse_feed(
            '<!DOCTYPE x [<!ENTITY a "b">]>' + DEMODULATED, "demodulated"), [])

    def test_bytes_and_malformed_xml_return_empty(self):
        self.assertEqual(legacyblog.parse_feed(MIKUS.encode("utf-8"), "mikus"), [])
        self.assertEqual(legacyblog.parse_feed("<rss", "mikus"), [])

    def test_sources_are_the_two_2014_blogs(self):
        self.assertEqual([row["id"] for row in legacyblog.sources()],
                         ["mikus", "demodulated"])
        self.assertEqual(legacyblog.source("MIKUS")["name"], "Mikus Musik")
        self.assertIsNone(legacyblog.source("missing"))


if __name__ == "__main__":
    unittest.main()
