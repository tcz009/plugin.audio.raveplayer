# -*- coding: utf-8 -*-
"""Toronto Rave Mixtape Archive scraper/menu tests (fixtures only)."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import downloads, routes, toronto  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return handle.read()


class TorontoParserTests(unittest.TestCase):
    def test_genres_use_canonical_order_plus_nav_extras(self):
        rows = toronto.parse_genres(fixture("toronto_home.html"))
        self.assertEqual([row["genre"] for row in rows],
                         ["jungle", "house", "studio", "xstatic", "breaks"])
        self.assertEqual(rows[0]["label"], "Jungle & Hardcore")
        self.assertEqual(rows[-1]["label"], "Breaks")

    def test_tracks_parse_labels_entities_urls_and_metadata(self):
        rows = toronto.parse_tracks(fixture("toronto_jungle.html"))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["name"], "187- Live at Syrous The Next Level Sept 4 1993")
        self.assertIn("40:39", rows[0]["metadata"])
        self.assertEqual(rows[1]["name"], "Brockie & Dj Rap - Jungle Mania - Side A")
        self.assertEqual(rows[1]["url"],
                         "https://www.torontoravemixtapearchive.com/files/mixtape/"
                         "Brockie%20%26%20Dj%20Rap%20-%20Jungle%20Mania%20-%20Side%20A.mp3")
        self.assertEqual(rows[2]["name"], "ABCDEF12")

    def test_tracks_reject_traversal_and_non_mixtape_files(self):
        rows = toronto.parse_tracks(fixture("toronto_jungle.html"))
        urls = " ".join(row["url"] for row in rows)
        self.assertNotIn("escape", urls)
        self.assertNotIn("/files/other/", urls)

    def test_xstatic_directory_is_supported(self):
        rows = toronto.parse_tracks(fixture("toronto_xstatic.html"))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all("/files/xstatic/" in row["url"] for row in rows))
        self.assertEqual(rows[1]["name"], "Carl Cox & Friends")


class TorontoFetchTests(unittest.TestCase):
    def test_genres_and_tracks_use_ttl_cache_and_request_gap(self):
        calls = []
        def fetch(url, **kwargs):
            calls.append((url, kwargs.get("ttl")))
            return fixture("toronto_home.html") if url.endswith("/") else fixture("toronto_jungle.html")
        with mock.patch.object(toronto.http, "fetch", side_effect=fetch), \
                mock.patch.object(toronto.time, "sleep") as sleep, \
                mock.patch.object(toronto, "_last_fetch_at", 0.0):
            rows = toronto.genres()
            tracks = toronto.tracks("jungle")
        self.assertTrue(rows)
        self.assertTrue(tracks)
        self.assertEqual(calls[0][0], toronto.BASE + "/")
        self.assertEqual(calls[1][0], toronto.BASE + "/jungle.html")
        self.assertEqual(calls[0][1], toronto.INDEX_TTL)
        self.assertEqual(calls[1][1], toronto.PAGE_TTL)
        sleep.assert_called()

    def test_empty_page_is_fail_soft(self):
        with mock.patch.object(toronto.http, "fetch", return_value=""):
            self.assertEqual(toronto.tracks("jungle"), [])
            self.assertTrue(toronto.genres())


class TorontoRouteTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]
        del xbmcplugin.CONTENT[:]

    def test_shows_menu_has_toronto_door(self):
        with mock.patch.object(routes.handoff, "available", return_value=False):
            routes.shows_menu(1, {})
        labels = [item["label"] for item in xbmcplugin.ITEMS]
        self.assertIn("Toronto Rave Mixtape Archive", labels)

    def test_genre_menu_renders_subfolders(self):
        with mock.patch.object(routes.toronto_source, "genres", return_value=[
                {"genre": "jungle", "label": "Jungle & Hardcore"},
                {"genre": "xstatic", "label": "X-Static"}]):
            routes.toronto(1, {})
        self.assertEqual([item["label"] for item in xbmcplugin.ITEMS],
                         ["Jungle & Hardcore", "X-Static", "Back"])
        self.assertIn("mode=toronto_genre", xbmcplugin.ITEMS[0]["url"])

    def test_genre_rows_play_direct_and_offer_download(self):
        tracks = [{"name": "Brockie & Dj Rap - Side A",
                   "url": "https://www.torontoravemixtapearchive.com/files/mixtape/a.mp3",
                   "metadata": "40:00"}]
        with mock.patch.object(routes.toronto_source, "tracks", return_value=tracks), \
                mock.patch.object(routes.http.socket, "getaddrinfo",
                                  return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), \
                mock.patch.object(routes.downloads, "eligible", return_value=True):
            routes.toronto_genre(1, {"genre": "jungle"})
        item = xbmcplugin.ITEMS[0]
        self.assertIn("mode=play", item["url"])
        self.assertIn("files%2Fmixtape%2Fa.mp3", item["url"])
        self.assertTrue(item["art"]["thumb"].endswith("toronto.png"))
        labels = [ctx[0] for ctx in item["context"]]
        self.assertIn("Add to favourites", labels)
        self.assertIn("Download", labels)

    def test_download_source_eligibility_and_host_gate(self):
        url = "https://www.torontoravemixtapearchive.com/files/mixtape/a.mp3"
        with mock.patch.object(downloads.http, "safe_stream_url", side_effect=lambda u: u):
            self.assertTrue(downloads.eligible(url, "Toronto Rave Mixtape Archive"))
            self.assertFalse(downloads.eligible(
                "https://evil.example/files/mixtape/a.mp3", "Toronto Rave Mixtape Archive"))


if __name__ == "__main__":
    unittest.main()
