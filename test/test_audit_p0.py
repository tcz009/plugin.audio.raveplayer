# -*- coding: utf-8 -*-
"""P0 audit fixes: Live Radio DNS and Archive pack pagination (3.9.49).

Offline only (Kodi stubs, no network).  See docs/OVERHAUL-AUDIT-2026.md P0-2
and P0-4, and docs/INTEGRATION-3.9.49.md for the device evidence.
"""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import routes  # noqa: E402


def _items():
    return list(xbmcplugin.ITEMS)


def _reset():
    del xbmcplugin.ITEMS[:]
    del xbmcplugin.CONTENT[:]


def _station(index):
    return {
        "name": "Station %d" % index,
        "url": "https://stream-%d.example.test/live" % index,
        "favicon": "https://favicon-%d.example.test/icon.png" % index,
    }


def _track(index):
    return {
        "title": "Tape %d - DJ" % index,
        "url": "https://archive.org/download/p/%d.mp3" % index,
        "duration": 60 + index,
    }


class LiveRadioNoDnsTests(unittest.TestCase):
    """P0-2: a 100-station door must not resolve one host per row."""

    def setUp(self):
        _reset()

    def test_hundred_stations_do_zero_dns_lookups(self):
        stations = [_station(index) for index in range(100)]
        resolver = mock.Mock(side_effect=AssertionError("DNS must not run"))
        with mock.patch.object(routes.radio, "display",
                               side_effect=lambda station: (station["name"], "")), \
                mock.patch.object(routes.radio, "stream_url",
                                  side_effect=lambda station: station["url"]), \
                mock.patch.object(routes.http.socket, "getaddrinfo", resolver):
            routes._station_items(1, stations, "Live radio")
        self.assertEqual(len(_items()), 100)
        self.assertEqual(resolver.call_count, 0)
        # The favicon is kept when it is a syntactically public URL, and the
        # bundled radio sticker stays the row icon.
        art = _items()[0]["art"]
        self.assertEqual(art["thumb"], stations[0]["favicon"])
        self.assertTrue(art["icon"].endswith("radio.png"))

    def test_literal_private_stream_is_not_listed_but_private_art_falls_back(self):
        stations = [
            {"name": "LAN art", "url": "https://stream.example.test/a",
             "favicon": "http://192.168.1.5/icon.png"},
            {"name": "LAN stream", "url": "http://10.0.0.4/live",
             "favicon": "https://favicon.example.test/icon.png"},
            {"name": "Good", "url": "https://stream.example.test/b",
             "favicon": "https://favicon.example.test/icon.png"},
        ]
        with mock.patch.object(routes.radio, "display",
                               side_effect=lambda station: (station["name"], "")), \
                mock.patch.object(routes.radio, "stream_url",
                                  side_effect=lambda station: station["url"]):
            routes._station_items(1, stations, "Live radio")
        labels = [item["label"] for item in _items()]
        self.assertEqual(labels, ["LAN art", "Good"])
        # The station is still usable; its LAN favicon is replaced by the
        # bundled radio sticker instead of reaching Kodi's image loader.
        self.assertTrue(_items()[0]["art"]["thumb"].endswith("radio.png"))
        self.assertTrue(_items()[1]["art"]["thumb"].endswith("icon.png"))

    def test_play_still_applies_the_strict_resolution_guard(self):
        # Listing is cheap; starting media is not.  A hostname that resolves
        # private is refused at play time with the normal warning.
        del xbmcplugin.RESOLVED[:]
        infos = [(2, 1, 6, "", ("192.168.1.20", 443))]
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=infos), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.play(1, {"url": "https://stream.example.test/a"})
        self.assertFalse(xbmcplugin.RESOLVED[-1]["ok"])
        self.assertTrue(notify.called)


class ArchivePackPaginationTests(unittest.TestCase):
    """P0-4: one pack must never build a directory larger than 200 rows."""

    def setUp(self):
        _reset()
        self.tracks = [_track(index) for index in range(450)]
        self.audio = mock.patch.object(routes.archive, "audio_files",
                                       return_value=self.tracks)
        self.audio.start()
        self.addCleanup(self.audio.stop)
        rows = mock.patch.object(routes, "_rows_per_page", return_value=200)
        rows.start()
        self.addCleanup(rows.stop)
        for name, value in (("item_title", "Helter Skelter"),
                            ("thumb", "https://archive.example/cover.jpg")):
            patcher = mock.patch.object(routes.archive, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _page(self, page):
        del xbmcplugin.ITEMS[:]
        routes.archive_item(1, {"id": "helter-skelter-tape-packs",
                                "page": str(page)})
        return _items()

    def test_page_one_is_capped_and_states_the_total(self):
        items = self._page(1)
        tracks = [item for item in items
                  if item["properties"].get("IsPlayable") == "true"]
        self.assertEqual(len(tracks), 200)
        self.assertIn("Page 1 of 3 · 450 tracks", items[0]["label"])
        self.assertEqual(items[-1]["label"], "Next page  ›")
        self.assertIn("page=2", items[-1]["url"])
        # Track numbers stay absolute across pages.
        self.assertEqual(tracks[0]["info"]["music"]["tracknumber"], 1)
        self.assertEqual(tracks[-1]["info"]["music"]["tracknumber"], 200)

    def test_last_page_has_the_remainder_and_no_next_row(self):
        items = self._page(3)
        tracks = [item for item in items
                  if item["properties"].get("IsPlayable") == "true"]
        self.assertEqual(len(tracks), 50)
        self.assertIn("Page 3 of 3 · 450 tracks", items[0]["label"])
        self.assertEqual(tracks[0]["info"]["music"]["tracknumber"], 401)
        self.assertFalse(any("Next page" in item["label"] for item in items))

    def test_play_all_from_page_two_starts_at_the_absolute_track(self):
        items = self._page(2)
        tracks = [item for item in items
                  if item["properties"].get("IsPlayable") == "true"]
        context = tracks[0]["context"]
        play_all = next(entry[1] for entry in context if "play_all" in entry[1])
        self.assertIn("start=200", play_all)

    def test_single_page_pack_has_no_header_or_next_row(self):
        self.audio.stop()
        self.tracks = [_track(index) for index in range(7)]
        self.audio = mock.patch.object(routes.archive, "audio_files",
                                       return_value=self.tracks)
        self.audio.start()
        items = self._page(1)
        self.assertEqual(len(items), 7)
        self.assertFalse(any("Page 1 of 1" in item["label"] for item in items))
        self.assertFalse(any("Next page" in item["label"] for item in items))


class SearchScopeTests(unittest.TestCase):
    """P0-1 guard: the device search door stays inside the rave collection."""

    def setUp(self):
        _reset()

    def test_search_query_carries_the_collection_clause(self):
        docs = [{"identifier": "pack-%d" % index, "title": "Pack %d" % index}
                for index in range(12)]
        with mock.patch.object(routes.archive, "search",
                               return_value=(docs, 12)) as search:
            routes.search(1, {"q": "randall"})
        query = search.call_args[0][0]
        self.assertIn("randall", query)
        self.assertIn("collection:ravetapes", query)
        self.assertIn("mediatype:audio", query)


if __name__ == "__main__":
    unittest.main()
