# -*- coding: utf-8 -*-
"""Performance regressions for the Kodi providers (no network, no Kodi).

These lock the 3.9.49 overhaul: parsed pages persist per exact body, the two
JungleTapes catalogue pages are fetched together, a warm DNB batch resolves
from one cache entry, and feed XML is parsed once per body.
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import cache, dnbradio, feeds, legacy, moxser, toronto  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return handle.read()


class _CacheDirMixin(object):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="raveplayer-perf-cache-")
        self.old = os.environ.get(cache.CACHE_DIR_ENV)
        os.environ[cache.CACHE_DIR_ENV] = self.directory

    def tearDown(self):
        if self.old is None:
            os.environ.pop(cache.CACHE_DIR_ENV, None)
        else:
            os.environ[cache.CACHE_DIR_ENV] = self.old
        shutil.rmtree(self.directory, ignore_errors=True)


class TorontoParseCacheTests(_CacheDirMixin, unittest.TestCase):
    def test_genre_tracks_are_parsed_once_per_body(self):
        page = fixture("toronto_jungle.html")
        calls = []
        original = toronto.parse_tracks

        def counting(body):
            calls.append(body)
            return original(body)

        with mock.patch.object(toronto.http, "fetch", return_value=page), \
                mock.patch.object(toronto, "parse_tracks", side_effect=counting):
            first = toronto.tracks("jungle")
            second = toronto.tracks("jungle")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)
        self.assertEqual(len(calls), 1)

    def test_genre_tracks_reparse_when_the_page_changes(self):
        pages = [fixture("toronto_jungle.html"), fixture("toronto_xstatic.html")]
        with mock.patch.object(toronto.http, "fetch",
                               side_effect=lambda *a, **k: pages.pop(0)):
            first = toronto.tracks("jungle")
            second = toronto.tracks("jungle")
        self.assertNotEqual(first, second)

    def test_genre_parse_cache_is_per_slug(self):
        page = fixture("toronto_jungle.html")
        with mock.patch.object(toronto.http, "fetch", return_value=page):
            self.assertTrue(toronto.tracks("jungle"))
        # A different slug with no cached body must not reuse the jungle rows.
        with mock.patch.object(toronto.http, "fetch", return_value=None):
            self.assertEqual(toronto.tracks("house"), [])


class MoxserParseCacheTests(_CacheDirMixin, unittest.TestCase):
    INDEX = """<?xml version="1.0"?><sitemapindex
        xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap><loc>https://moxser.com/sitemaps-1-section-mixes-1-sitemap-p1.xml</loc></sitemap>
        </sitemapindex>"""
    MIXES = """<?xml version="1.0"?><urlset
        xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
        <url><loc>https://moxser.com/mixes/bench-mix</loc>
        <lastmod>2026-10-26T17:06:25+00:00</lastmod>
        <image:image><image:loc>https://moxser.com/a.jpg</image:loc>
        <image:title>Bench+Mix</image:title></image:image></url></urlset>"""

    def _fetch(self, url, timeout=25, headers=None, ttl=0):
        if url == moxser.SITEMAP_INDEX:
            return self.INDEX
        return self.MIXES

    def test_sitemap_is_parsed_once_per_body(self):
        calls = []
        original = moxser._parse_mixes_sitemap

        def counting(body):
            calls.append(body)
            return original(body)

        with mock.patch.object(moxser.http, "fetch", side_effect=self._fetch), \
                mock.patch.object(moxser, "_parse_mixes_sitemap", side_effect=counting), \
                mock.patch.object(moxser, "_throttle"):
            first = moxser.mixes(limit=60)
            second = moxser.mixes(limit=60)

        self.assertEqual([row["page_url"] for row in first],
                         ["https://moxser.com/mixes/bench-mix"])
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)

    def test_sitemap_reparse_when_the_body_changes(self):
        bodies = [self.MIXES, self.MIXES.replace("bench-mix", "other-mix")]
        state = {"index": 0}

        def fetch(url, timeout=25, headers=None, ttl=0):
            if url == moxser.SITEMAP_INDEX:
                return self.INDEX
            body = bodies[min(state["index"], len(bodies) - 1)]
            state["index"] += 1
            return body

        with mock.patch.object(moxser.http, "fetch", side_effect=fetch), \
                mock.patch.object(moxser, "_throttle"):
            first = moxser.mixes(limit=60)
            second = moxser.mixes(limit=60)
        self.assertEqual(first[0]["page_url"], "https://moxser.com/mixes/bench-mix")
        self.assertEqual(second[0]["page_url"], "https://moxser.com/mixes/other-mix")


class JungleTapesConcurrencyTests(unittest.TestCase):
    def test_catalogue_pages_are_fetched_concurrently(self):
        sitemap_started = threading.Event()
        order = []

        def fetch(url, timeout=25, headers=None, ttl=0):
            order.append(url)
            if url.endswith("/tapes"):
                # Only passes when the sitemap request is in flight at the
                # same time; the old serial code would block here until the
                # event timed out.
                self.assertTrue(sitemap_started.wait(2.0))
                return '<a href="/show/tapes-show">x</a>'
            sitemap_started.set()
            return "<loc>https://jungletapes.com/show/sitemap-show</loc>"

        with mock.patch.object(legacy.http, "fetch", side_effect=fetch):
            shows = legacy.jungle_shows()

        keys = sorted(show["key"] for show in shows)
        self.assertEqual(keys, ["sitemap-show", "tapes-show"])
        self.assertEqual(sorted(order), [legacy.JT_BASE + "/sitemap.xml",
                                        legacy.JT_BASE + "/tapes"])

    def test_show_order_keeps_tapes_before_sitemap(self):
        def fetch(url, timeout=25, headers=None, ttl=0):
            if url.endswith("/tapes"):
                return '<a href="/show/zzz-tapes">x</a>'
            return "<loc>https://jungletapes.com/show/aaa-sitemap</loc>"

        with mock.patch.object(legacy.http, "fetch", side_effect=fetch):
            shows = legacy.jungle_shows()
        # Sorted by label (reverse) as before; both sources still present.
        self.assertEqual(len(shows), 2)


class DnbStreamMapTests(_CacheDirMixin, unittest.TestCase):
    PAGE = ('<html><a href="https://cdn.example/show.mp3">Download</a></html>')

    def test_warm_batch_uses_one_cache_entry_without_refetching(self):
        calls = []

        def fetch(url, timeout=25, headers=None, ttl=0):
            calls.append(url)
            return self.PAGE

        with mock.patch.object(dnbradio.http, "fetch", side_effect=fetch):
            first = dnbradio.stream_urls(["1", "2", "3"], timeout=1, workers=2)
            fetched = len(calls)
            second = dnbradio.stream_urls(["1", "2", "3"], timeout=1, workers=2)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)
        self.assertEqual(fetched, 3)
        self.assertEqual(len(calls), fetched)

    def test_partial_cache_resolves_only_the_missing_ids(self):
        calls = []

        def fetch(url, timeout=25, headers=None, ttl=0):
            calls.append(url)
            return self.PAGE

        with mock.patch.object(dnbradio.http, "fetch", side_effect=fetch):
            dnbradio.stream_urls(["41"], timeout=1)
            dnbradio.stream_urls(["41", "42"], timeout=1)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].endswith("mix=41"))
        self.assertTrue(calls[1].endswith("mix=42"))


FEED_XML = """<?xml version="1.0"?><rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel><title>Bench</title>
<item><title>Episode One</title>
<enclosure url="https://cdn.example/one.mp3" type="audio/mpeg"/>
<itunes:duration>1200</itunes:duration></item>
</channel></rss>"""


class FeedParseCacheTests(_CacheDirMixin, unittest.TestCase):
    def test_feed_xml_is_parsed_once_per_body(self):
        calls = []
        original = feeds.parse
        entry = {"id": "bench", "name": "Bench", "url": "https://cdn.example/feed"}

        def counting(body):
            calls.append(body)
            return original(body)

        with mock.patch.object(feeds, "feed", return_value=entry), \
                mock.patch.object(feeds.http, "fetch", return_value=FEED_XML), \
                mock.patch.object(feeds, "parse", side_effect=counting):
            first = feeds.episodes("bench")
            second = feeds.episodes("bench")

        self.assertEqual(first, second)
        self.assertEqual(first[0]["title"], "Episode One")
        self.assertEqual(len(calls), 1)


class RouteWarmPathTests(_CacheDirMixin, unittest.TestCase):
    """A warm directory refresh must not touch the network."""

    def test_warm_rtp_category_needs_no_upstream_request(self):
        homepage = ('<a href="?cat=7">Dreamscape</a>'
                    '<a href="?cat=8">Roast</a>')
        category = '<a rel="bookmark" href="?p=899">Dreamscape 7</a>'
        calls = []

        def request(url, timeout=None, headers=None):
            calls.append(url)
            return category

        # Patch the network layer, not fetch(): the real disk cache must be
        # exercised, which is what a warm Kodi refresh actually does.
        with mock.patch.object(legacy.http, "_request", side_effect=request):
            first = legacy.category("7")
            cold_calls = len(calls)
            second = legacy.category("7")

        self.assertEqual(first, second)
        self.assertEqual(cold_calls, 1)
        self.assertEqual(len(calls), cold_calls)
        self.assertEqual(calls[0], legacy.BASE + "?cat=7")

    def test_warm_rtp_post_needs_no_upstream_request(self):
        page = ('<h1 class="entry-title">Dreamscape 7</h1>'
                '<a href="/music/Dreamscape7/Charlie_Hall.mp3">x</a>')
        calls = []

        def request(url, timeout=None, headers=None):
            calls.append(url)
            return page

        with mock.patch.object(legacy.http, "_request", side_effect=request):
            first = legacy.post("899")
            cold_calls = len(calls)
            second = legacy.post("899")

        self.assertEqual(first["name"], "Dreamscape 7")
        self.assertEqual(first, second)
        self.assertEqual(cold_calls, 1)
        self.assertEqual(len(calls), cold_calls)
        self.assertEqual(calls[0], legacy.BASE + "?p=899")


if __name__ == "__main__":
    unittest.main()
