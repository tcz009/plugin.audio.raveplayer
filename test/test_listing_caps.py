# -*- coding: utf-8 -*-
"""Regression guard: listing sources must not silently truncate their results."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import feeds, hardscore, moxser, routes, toronto  # noqa: E402


def moxser_index(sitemaps=5):
    rows = "".join(
        "<sitemap><loc>https://moxser.com/sitemaps-1-section-mixes-1-sitemap-p%d.xml</loc></sitemap>" % index
        for index in range(1, sitemaps + 1)
    )
    return '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</sitemapindex>' % rows


def moxser_sitemap(count):
    rows = []
    for index in range(count):
        rows.append(
            "<url><loc>https://moxser.com/mixes/mix-%d</loc>"
            "<lastmod>2026-10-26T17:06:25+00:00</lastmod>"
            "<image:image xmlns:image=\"http://www.google.com/schemas/sitemap-image/1.1\">"
            "<image:loc>https://moxser.com/a.jpg</image:loc>"
            "<image:title>Mix %d</image:title></image:image></url>" % (index, index)
        )
    return ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(rows) + "</urlset>")


def hardscore_rss(count):
    items = []
    for index in range(count):
        items.append(
            "<item><title>Post %d</title><link>https://www.hardscore.com/?p=%d</link>"
            "<description><![CDATA[<a href=\"https://hardscore.com/mixes/p%d.mp3\">Download</a>]]></description>"
            "<pubDate>Mon, 02 Nov 2026 12:00:00 +0000</pubDate></item>" % (index, index, index)
        )
    return "<rss><channel>%s</channel></rss>" % "".join(items)


def toronto_page(count):
    rows = []
    for index in range(count):
        rows.append(
            '<a download="Toronto Mix %d" href="/files/mixtape/Toronto Mix %d.mp3">'
            '<div class="header">Toronto Mix %d</div></a>' % (index, index, index)
        )
    return "<html><body>%s</body></html>" % "".join(rows)


def feed_xml(count):
    items = []
    for index in range(count):
        items.append(
            "<item><title>Episode %d</title><enclosure url=\"https://example.test/e%d.mp3\" "
            "type=\"audio/mpeg\"/></item>" % (index, index)
        )
    return "<rss><channel>%s</channel></rss>" % "".join(items)


class ListingCapTests(unittest.TestCase):
    def test_moxser_returns_all_150_across_five_sitemaps(self):
        old = moxser.MIN_INTERVAL
        moxser.MIN_INTERVAL = 0
        try:
            counter = {"n": 0}
            def fetch(url, **kwargs):
                if url == moxser.SITEMAP_INDEX:
                    return moxser_index()
                counter["n"] += 1
                return moxser_sitemap(30).replace("mix-", "mix-%d-" % counter["n"])
            with mock.patch.object(moxser.http, "fetch", side_effect=fetch):
                rows = moxser.mixes(limit=moxser.MAX_MIXES)
        finally:
            moxser.MIN_INTERVAL = old
        self.assertEqual(len(rows), 150)

    def test_hardscore_returns_all_150_feed_items(self):
        with mock.patch.object(hardscore.http, "safe_stream_url", side_effect=lambda url: url):
            rows = hardscore.parse_feed(hardscore_rss(150), limit=hardscore.MAX_ITEMS)
        self.assertEqual(len(rows), 150)

    def test_toronto_page_678_is_not_truncated(self):
        rows = toronto.parse_tracks(toronto_page(678))
        self.assertEqual(len(rows), 678)
        self.assertEqual(rows[-1]["name"], "Toronto Mix 677")

    def test_feed_parser_returns_all_120_episodes(self):
        rows = feeds.parse(feed_xml(120))
        self.assertEqual(len(rows), 120)

    def _render_all_pages(self, route, params):
        """Walk Next page links and return every content row exactly once."""
        seen = []
        page = 1
        while True:
            del xbmcplugin.ITEMS[:]
            route(1, dict(params, page=str(page)))
            rows = [item for item in xbmcplugin.ITEMS
                    if item["label"] not in ("Back",)
                    and not item["label"].startswith("Page ")
                    and not item["label"].startswith(("Next page", "Previous page"))]
            seen.extend(rows)
            next_links = [item["url"] for item in xbmcplugin.ITEMS
                          if item["label"].startswith("Next page")]
            self.assertLessEqual(len(rows), 50, "page %d exceeded the page size" % page)
            if not next_links:
                break
            page += 1
        return seen

    def test_routes_page_through_the_full_source_lists(self):
        with mock.patch.object(routes, "_rows_per_page", return_value=50):
            rows = [{"title": "Mix %d" % i, "page_url": "https://moxser.com/mixes/%d" % i,
                     "date": "", "flyer": ""} for i in range(150)]
            with mock.patch.object(routes.moxser_source, "mixes", return_value=rows):
                seen = self._render_all_pages(routes.moxser, {})
            self.assertEqual([item["label"] for item in seen],
                             ["Mix %d" % i for i in range(150)])

            hsrows = [{"title": "Post %d" % i, "page_url": "https://www.hardscore.com/?p=%d" % i,
                       "date": "", "media_urls": [], "description": ""} for i in range(150)]
            with mock.patch.object(routes.hardscore_source, "items", return_value=hsrows):
                seen = self._render_all_pages(routes.hardscore, {})
            self.assertEqual([item["label"] for item in seen],
                             ["Post %d  [COLOR gray](post)[/COLOR]" % i
                              for i in range(150)])

            trows = [{"name": "Toronto Mix %d" % i,
                      "url": "https://www.torontoravemixtapearchive.com/files/mixtape/%d.mp3" % i}
                     for i in range(678)]
            with mock.patch.object(routes.toronto_source, "tracks", return_value=trows), \
                    mock.patch.object(routes, "_playable_url", side_effect=lambda url: url), \
                    mock.patch.object(routes.kodi, "end_directory"):
                seen = self._render_all_pages(routes.toronto_genre, {"genre": "jungle"})
            self.assertEqual(len(seen), 678)
            self.assertEqual(seen[0]["label"], "Toronto Mix 0")
            self.assertEqual(seen[-1]["label"], "Toronto Mix 677")

    def test_old_cap_constants_are_raised(self):
        self.assertGreaterEqual(moxser.MAX_MIXES, 1000)
        self.assertGreaterEqual(hardscore.MAX_ITEMS, 1000)
        self.assertGreaterEqual(toronto.MAX_TRACKS, 1000)
        self.assertGreaterEqual(routes.MAX_EPISODES_PER_FEED, 1000)


if __name__ == "__main__":
    unittest.main()
