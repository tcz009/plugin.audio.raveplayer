# -*- coding: utf-8 -*-
"""Uniform pagination (3.9.50): boundaries, page coverage, nav rows, play-all.

Every list that can exceed a screenful goes through ``routes._paged`` and the
same "Page N of M · X items" header / Previous-Next rows.  These tests walk the
real route handlers page by page and assert that the union of the pages is the
whole source list, with no duplicate or missing rows.
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

PAGE = 50


def _reset():
    del xbmcplugin.ITEMS[:]


def _items():
    return list(xbmcplugin.ITEMS)


def _content(items):
    """Rows that are actual list content (not headers, nav or the Back row)."""
    return [
        item for item in items
        if item["label"] != "Back"
        and not item["label"].startswith("Page ")
        and not item["label"].startswith(("Next page", "Previous page"))
    ]


def _walk(route, params):
    """Call ``route`` for every page via its Next link; return content rows."""
    seen = []
    urls = []
    page = 1
    while True:
        _reset()
        route(1, dict(params, page=str(page)))
        rows = _content(_items())
        seen.extend(rows)
        urls.append([item["url"] for item in _items()])
        if not any(item["label"].startswith("Next page") for item in _items()):
            break
        page += 1
        if page > 200:  # pragma: no cover - guards a broken Next link
            raise AssertionError("Next page never terminated")
    return seen, urls


class PagedWindowTests(unittest.TestCase):
    def test_empty_list_is_one_empty_page(self):
        window, page, pages, total, start = routes._paged([], 1, 50)
        self.assertEqual((window, page, pages, total, start), ([], 1, 1, 0, 0))

    def test_exact_multiple_has_no_spare_page(self):
        rows = list(range(100))
        window, page, pages, total, start = routes._paged(rows, 2, 50)
        self.assertEqual(len(window), 50)
        self.assertEqual((page, pages, total, start), (2, 2, 100, 50))

    def test_partial_last_page(self):
        rows = list(range(101))
        window, page, pages, total, start = routes._paged(rows, 3, 50)
        self.assertEqual(window, [100])
        self.assertEqual((page, pages, total, start), (3, 3, 101, 100))

    def test_page_is_clamped_to_the_last_page(self):
        rows = list(range(101))
        _window, page, pages, _total, start = routes._paged(rows, 99, 50)
        self.assertEqual((page, pages, start), (3, 3, 100))

    def test_invalid_page_falls_back_to_one(self):
        for value in (0, -3):
            _window, page, _pages, _total, start = routes._paged(
                list(range(10)), value, 50)
            self.assertEqual((page, start), (1, 0))

    def test_page_label_matches_the_owner_wording(self):
        self.assertEqual(routes._page_label(2, 15, 724, "items"),
                         "Page 2 of 15 · 724 items")
        self.assertEqual(routes._page_label(1, 1, 0, "tracks"),
                         "Page 1 of 1 · 0 tracks")
        # Server-side lists do not know M without walking every WordPress page.
        self.assertEqual(routes._page_label(3, None, 10, "packs"),
                         "Page 3 · 10 packs")

    def test_header_only_exists_on_a_multi_page_list(self):
        _reset()
        self.assertFalse(routes._page_header(1, 1, 1, 10, "items"))
        self.assertEqual(_items(), [])
        self.assertTrue(routes._page_header(1, 2, 3, 120, "items"))
        self.assertEqual(_items()[0]["label"], "Page 2 of 3 · 120 items")

    def test_nav_rows_are_hidden_at_bounds_and_link_neighbours(self):
        _reset()
        routes._page_nav(1, "moxser", {}, 1, 3, 120, 50, "items")
        labels = [item["label"] for item in _items()]
        self.assertEqual(labels, ["Next page  ›"])
        self.assertIn("page=2", _items()[0]["url"])

        _reset()
        routes._page_nav(1, "moxser", {}, 2, 3, 120, 50, "items")
        urls = {item["label"]: item["url"] for item in _items()}
        self.assertIn("page=1", urls["Previous page  ‹"])
        self.assertIn("page=3", urls["Next page  ›"])

        _reset()
        routes._page_nav(1, "moxser", {}, 3, 3, 120, 50, "items")
        self.assertEqual([item["label"] for item in _items()],
                         ["Previous page  ‹"])


class SourcePagingTests(unittest.TestCase):
    def setUp(self):
        _reset()
        pager = mock.patch.object(routes, "_rows_per_page", return_value=PAGE)
        pager.start()
        self.addCleanup(pager.stop)
        url = mock.patch.object(routes, "_playable_url", side_effect=lambda value: value)
        url.start()
        self.addCleanup(url.stop)

    def test_moxser_1001_pages_cover_every_mix(self):
        rows = [{"title": "Mix %04d" % i,
                 "page_url": "https://moxser.com/mixes/%d" % i,
                 "date": "", "flyer": ""} for i in range(1001)]
        with mock.patch.object(routes.moxser_source, "mixes", return_value=rows):
            seen, _urls = _walk(routes.moxser, {})
            self.assertEqual(len(seen), 1001)
            self.assertEqual([item["label"] for item in seen],
                             ["Mix %04d" % i for i in range(1001)])
            _reset()
            routes.moxser(1, {"page": "1"})
            self.assertEqual(_items()[0]["label"],
                             "Page 1 of 21 · 1,001 mixes")
            _reset()
            routes.moxser(1, {"page": "21"})
            self.assertEqual(_content(_items())[0]["label"], "Mix 1000")
            self.assertFalse(any(item["label"].startswith("Next page")
                                 for item in _items()))
            self.assertTrue(any(item["label"].startswith("Previous page")
                                for item in _items()))

    def test_toronto_genre_679_and_2640_are_fully_paged(self):
        for total in (679, 2640):
            tracks = [{"name": "Toronto Mix %04d" % i,
                       "url": "https://toronto.example/files/%d.mp3" % i}
                      for i in range(total)]
            with mock.patch.object(routes.toronto_source, "tracks",
                                   return_value=tracks), \
                    mock.patch.object(routes.kodi, "end_directory"):
                seen, _urls = _walk(routes.toronto_genre, {"genre": "jungle"})
            self.assertEqual(len(seen), total)
            self.assertEqual(len({item["label"] for item in seen}), total)
            self.assertEqual(seen[0]["label"], "Toronto Mix 0000")
            self.assertEqual(seen[-1]["label"], "Toronto Mix %04d" % (total - 1))
            # Track numbers are absolute, not page-relative.
            self.assertEqual(seen[PAGE]["info"]["music"]["tracknumber"], PAGE + 1)

    def test_jungletapes_310_shows_are_fully_paged(self):
        shows = [{"key": "show-%03d" % i, "name": "Show %03d" % i}
                 for i in range(310)]
        with mock.patch.object(routes.legacy, "jungle_shows", return_value=shows), \
                mock.patch.object(routes.kodi, "end_directory"):
            seen, _urls = _walk(routes.legacy_jt, {})
        self.assertEqual(len(seen), 310)
        self.assertEqual([item["label"] for item in seen],
                         ["Show %03d" % i for i in range(310)])

    def test_rave_nights_55_are_fully_paged(self):
        entries = [{"name": "Rave %03d" % i, "slug": "rave-%03d" % i,
                    "count": i, "mixcloud_count": 0}
                   for i in range(55)]
        with mock.patch.object(routes, "_rave_catalog", return_value=entries), \
                mock.patch.object(routes.kodi, "end_directory"):
            seen, _urls = _walk(routes.rave_nights, {})
        self.assertEqual(len(seen), 55)
        self.assertEqual(len({item["label"] for item in seen}), 55)

    def test_downloads_are_paged(self):
        rows = [{"title": "Download %03d" % i, "exists": False,
                 "key": "dl-%03d" % i, "source": "Archive.org",
                 "added": "2026-01-02"} for i in range(120)]
        with mock.patch.object(routes.downloads, "list_downloads",
                               return_value=rows), \
                mock.patch.object(routes.kodi, "end_directory"):
            seen, _urls = _walk(routes.downloads_menu, {})
        self.assertEqual(len(seen), 120)
        self.assertEqual(len({item["label"] for item in seen}), 120)

    def test_live_radio_500_stations_are_fully_paged(self):
        stations = [{"name": "Station %03d" % i,
                     "url": "https://stream-%03d.example.test/live" % i,
                     "favicon": ""} for i in range(500)]

        def display(station):
            return station["name"], "live"

        with mock.patch.object(routes.radio, "stations", return_value=stations), \
                mock.patch.object(routes.radio, "display", side_effect=display), \
                mock.patch.object(routes.radio, "stream_url",
                                  side_effect=lambda station: station["url"]), \
                mock.patch.object(routes.kodi, "end_directory"):
            seen, _urls = _walk(routes.radio_tag, {"key": "jungle"})
        self.assertEqual(len(seen), 500)
        labels = [item["label"] for item in seen]
        self.assertEqual(len(set(labels)), 500)

    def test_search_page_two_has_previous_and_next(self):
        docs = [{"identifier": "pack-%d" % i, "title": "Pack %d" % i}
                for i in range(PAGE)]
        with mock.patch.object(routes.archive, "search",
                               return_value=(docs, 120)), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.search(1, {"q": "randall", "page": "2"})
        labels = [item["label"] for item in _items()]
        self.assertEqual(labels[0], "Page 2 of 3 · 120 items")
        self.assertIn("Previous page  ‹", labels)
        self.assertIn("Next page  ›", labels)

    def test_single_page_source_has_no_header_or_nav(self):
        rows = [{"title": "Mix %02d" % i,
                 "page_url": "https://moxser.com/mixes/%d" % i,
                 "date": "", "flyer": ""} for i in range(10)]
        with mock.patch.object(routes.moxser_source, "mixes", return_value=rows):
            routes.moxser(1, {})
        labels = [item["label"] for item in _items()]
        self.assertEqual(labels, ["Mix %02d" % i for i in range(10)] + ["Back"])


class PackPagingTests(unittest.TestCase):
    def setUp(self):
        _reset()
        pager = mock.patch.object(routes, "_rows_per_page", return_value=PAGE)
        pager.start()
        self.addCleanup(pager.stop)
        self.tracks = [{"title": "Tape %03d - DJ" % i,
                        "url": "https://archive.org/download/p/%d.mp3" % i,
                        "duration": 60 + i}
                       for i in range(451)]
        patch = mock.patch.object(routes.archive, "audio_files",
                                  return_value=self.tracks)
        patch.start()
        self.addCleanup(patch.stop)
        for name, value in (("item_title", "Helter Skelter"),
                            ("thumb", "https://archive.example/cover.jpg")):
            patcher = mock.patch.object(routes.archive, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_last_partial_page_has_offset_track_numbers(self):
        routes.archive_item(1, {"id": "helter", "page": "10"})
        content = _content(_items())
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0]["info"]["music"]["tracknumber"], 451)
        labels = [item["label"] for item in _items()]
        self.assertIn("Page 10 of 10 · 451 tracks", labels)
        self.assertIn("Previous page  ‹", labels)
        self.assertFalse(any(item["label"].startswith("Next page") for item in _items()))

    def test_play_all_from_page_two_still_queues_the_whole_pack(self):
        routes.archive_item(1, {"id": "helter", "page": "2"})
        rows = _content(_items())
        play = [entry[1] for entry in rows[0]["context"]
                if "mode=play_all" in entry[1]]
        self.assertEqual(len(play), 1)
        self.assertIn("start=50", play[0])

        captured = {}

        def fake_play(tracks, identifier=None, start=0, shuffle=False, **extra):
            captured.update(tracks=tracks, start=start, shuffle=shuffle)
            return True

        with mock.patch.object(routes, "_play_tracks", side_effect=fake_play):
            routes.play_all(1, {"id": "helter", "start": "50"})
        self.assertEqual(len(captured["tracks"]), 451)
        self.assertEqual(captured["start"], 50)

    def test_toronto_play_all_collection_uses_the_whole_genre(self):
        tracks = [{"name": "Toronto Mix %04d" % i,
                   "url": "https://toronto.example/files/%d.mp3" % i}
                  for i in range(679)]
        captured = {}

        def fake_play(rows, identifier=None, start=0, shuffle=False, **extra):
            captured.update(rows=rows, start=start, shuffle=shuffle, **extra)
            return True

        with mock.patch.object(routes.toronto_source, "tracks",
                               return_value=tracks), \
                mock.patch.object(routes, "_play_tracks", side_effect=fake_play):
            routes.play_all_collection(1, {"source": "toronto",
                                           "key": "jungle", "start": "250"})
        self.assertEqual(len(captured["rows"]), 679)
        self.assertEqual(captured["start"], 250)
        self.assertEqual(captured["album"], "Jungle & Hardcore")


if __name__ == "__main__":
    unittest.main()

