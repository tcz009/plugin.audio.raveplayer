# -*- coding: utf-8 -*-
"""Look-and-feel 3.9.44: Label2 facts, visible plots and track InfoTags.

Offline only (Kodi stubs, no network).  The audit is
``docs/LOOK-AND-FEEL-2026.md``; the shipped changes are recorded in
``docs/LOOK-AND-FEEL-3.9.44.md``.
"""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmc  # noqa: E402
import xbmcplugin  # noqa: E402

from resources.lib import archive, kodi, nowplaying, routes, ui  # noqa: E402


class FactFormattingTests(unittest.TestCase):
    def test_fact_is_plain_and_capped(self):
        self.assertEqual(ui.fact("  48.0 MB  ·  31 Oct "), "48.0 MB · 31 Oct")
        self.assertEqual(len(ui.fact("x" * 60)), ui.MAX_LABEL2_CHARS)
        self.assertTrue(ui.fact("x" * 60).endswith("…"))
        self.assertEqual(ui.fact("[COLOR gray]1994[/COLOR]"), "1994")
        self.assertEqual(ui.fact(None), "")

    def test_duration_fact_uses_the_shortest_clock(self):
        self.assertEqual(ui.duration_fact(2637), "43:57")
        self.assertEqual(ui.duration_fact(3723), "1:02:03")
        self.assertEqual(ui.duration_fact("61"), "1:01")
        self.assertEqual(ui.duration_fact("1:02:03"), "1:02:03")
        for value in (None, "", 0, "soon", -5):
            with self.subTest(value=value):
                self.assertEqual(ui.duration_fact(value), "")

    def test_count_fact_groups_digits(self):
        self.assertEqual(ui.count_fact(1204), "1,204")
        self.assertEqual(ui.count_fact("7"), "7")
        self.assertEqual(ui.count_fact(None), "")
        self.assertEqual(ui.count_fact("nope"), "")

    def test_short_date_is_iso_only(self):
        self.assertEqual(ui.short_date("2026-10-31T12:00:00Z"), "31 Oct")
        self.assertEqual(ui.short_date("2026-10-31"), "31 Oct")
        for value in ("", None, "31/10/2026", "2026-13-01"):
            with self.subTest(value=value):
                self.assertEqual(ui.short_date(value), "")

    def test_size_date_fact_fits_the_budget(self):
        self.assertEqual(ui.size_date_fact("48.0 MB", "2026-10-31T00:00:00Z"),
                         "48.0 MB · 31 Oct")
        self.assertEqual(len(ui.size_date_fact("48.0 MB", "2026-10-31T00:00:00Z")),
                         ui.MAX_LABEL2_CHARS)
        self.assertEqual(ui.size_date_fact("1023.9 GB", "2026-10-31T00:00:00Z"),
                         "1023.9 GB")


class VisiblePlotTests(unittest.TestCase):
    """Estuary reads ListItem.Plot from the video InfoTag, on every Kodi."""

    def setUp(self):
        del xbmcplugin.ITEMS[:]

    def test_kodi_22_plot_is_only_on_the_video_tag(self):
        with mock.patch.object(kodi, "KODI_MAJOR", 22):
            ui.menu_item(1, "plugin://x?mode=packs_menu", "Tape Packs",
                         plot="Cassette packs and rave tapes.")
        info = xbmcplugin.ITEMS[0]["info"]
        self.assertEqual(info["video"]["plot"], "Cassette packs and rave tapes.")
        self.assertNotIn("plot", info["music"])
        self.assertEqual(info["music"]["comment"], "Cassette packs and rave tapes.")

    def test_legacy_kodi_plot_is_on_both_tags(self):
        with mock.patch.object(kodi, "KODI_MAJOR", 21):
            ui.menu_item(1, "plugin://x?mode=packs_menu", "Tape Packs",
                         plot="Cassette packs and rave tapes.")
        info = xbmcplugin.ITEMS[0]["info"]
        self.assertEqual(info["video"]["plot"], "Cassette packs and rave tapes.")
        self.assertEqual(info["music"]["plot"], "Cassette packs and rave tapes.")

    def test_info_rows_and_track_rows_get_a_video_plot(self):
        with mock.patch.object(kodi, "KODI_MAJOR", 22):
            ui.info_item(1, "Source: SoundCloud", plot="Web version only.")
            ui.track_item(1, "plugin://x?mode=play", "Track",
                          plot="Vinylgroover · Dreamscape · 1994")
        self.assertEqual(xbmcplugin.ITEMS[0]["info"]["video"]["plot"],
                         "Web version only.")
        self.assertEqual(xbmcplugin.ITEMS[1]["info"]["video"]["plot"],
                         "Vinylgroover · Dreamscape · 1994")

    def test_no_plot_means_no_video_tag(self):
        ui.menu_item(1, "plugin://x?mode=year_list", "1994", label2="1994")
        self.assertNotIn("video", xbmcplugin.ITEMS[0]["info"])

    def test_video_plot_is_plain_text(self):
        ui.menu_item(1, "plugin://x?mode=root", "Row",
                     plot="[COLOR gray]Grey copy[/COLOR]")
        self.assertEqual(xbmcplugin.ITEMS[0]["info"]["video"]["plot"], "Grey copy")


class RouteLabel2Tests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]

    def _assert_budget(self, item):
        self.assertLessEqual(len(item["label2"]), ui.MAX_LABEL2_CHARS, item["label"])
        self.assertNotIn("[", item["label2"], item["label"])

    def test_root_rows_carry_a_short_fact(self):
        routes.root(1, {})
        self.assertEqual(len(xbmcplugin.ITEMS), 10)
        for item in xbmcplugin.ITEMS:
            with self.subTest(label=item["label"]):
                self.assertTrue(item["label2"], item["label"])
                self._assert_budget(item)
        facts = dict((item["label"], item["label2"]) for item in xbmcplugin.ITEMS)
        self.assertEqual(facts["Rave Screen"], "full screen")
        self.assertEqual(facts["Tape Packs"], "1990–2004")
        self.assertEqual(facts["Search the Archive"], "archive.org")

    def test_pack_hub_rows_carry_a_fact(self):
        routes.packs_menu(1, {})
        rows = [item for item in xbmcplugin.ITEMS if item["label"] != "Back"]
        self.assertEqual(len(rows), 7)
        for item in rows:
            with self.subTest(label=item["label"]):
                self.assertTrue(item["label2"], item["label"])
                self._assert_budget(item)
        facts = dict((item["label"], item["label2"]) for item in rows)
        self.assertEqual(facts["JungleTapes.com"], "300+ shows")
        self.assertEqual(facts["RaveTapePacks.com"], "1992–2004")

    def test_track_rows_carry_duration_and_downloads_carry_size_date(self):
        tracks = [{"title": "Tape 1 - Carl Cox",
                   "url": "https://archive.org/download/p/1.mp3",
                   "duration": 2637, "genre": "Jungle"}]
        with mock.patch.object(routes.archive, "audio_files", return_value=tracks), \
                mock.patch.object(routes.archive, "item_title", return_value="Dreamscape 19"):
            routes.archive_item(1, {"id": "pack-1"})
        self.assertEqual(xbmcplugin.ITEMS[0]["label2"], "43:57")

        del xbmcplugin.ITEMS[:]
        rows = [{"key": "k", "title": "Dreamscape 19", "path": "/tmp/x.mp3",
                 "exists": True, "size": 48 * 1024 * 1024, "source": "Archive.org",
                 "added": "2026-10-31T12:00:00Z", "filename": "x.mp3"}]
        with mock.patch.object(routes.downloads, "list_downloads", return_value=rows), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.downloads_menu(1, {})
        self.assertEqual(xbmcplugin.ITEMS[0]["label2"], "48.0 MB · 31 Oct")

    def test_archive_rows_use_the_parsed_venue(self):
        docs = [{"identifier": "pack-1", "title": "Dreamscape 12 August 1994"}]
        routes._archive_items(1, docs)
        self.assertEqual(xbmcplugin.ITEMS[0]["label2"], "Dreamscape")


class TrackInfoTagTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]
        del xbmc.PLAYED[:]

    def test_archive_tracks_expose_artist_album_year_genre_and_tracknumber(self):
        tracks = [
            {"title": "Tape 1 - Carl Cox",
             "url": "https://archive.org/download/p/1.mp3",
             "duration": 2637, "genre": "Jungle"},
            {"title": "Tape 2 - Ellis Dee",
             "url": "https://archive.org/download/p/2.mp3",
             "duration": None, "genre": "Jungle"},
        ]
        pack = "Dreamscape XII — The August Bank Holiday Showcase 26 Aug 1994"
        with mock.patch.object(routes.archive, "audio_files", return_value=tracks), \
                mock.patch.object(routes.archive, "item_title", return_value=pack):
            routes.archive_item(1, {"id": "pack-1"})
        first = xbmcplugin.ITEMS[0]["info"]["music"]
        self.assertEqual(first["artist"], "Carl Cox")
        self.assertEqual(first["album"], pack)
        self.assertEqual(first["year"], 1994)
        self.assertEqual(first["genre"], "Jungle")
        self.assertEqual(first["tracknumber"], 1)
        second = xbmcplugin.ITEMS[1]["info"]["music"]
        self.assertEqual(second["artist"], "Ellis Dee")
        self.assertEqual(second["tracknumber"], 2)
        # No length on this one, so the known year is the Label2 fallback.
        self.assertEqual(xbmcplugin.ITEMS[1]["label2"], "1994")

    def test_play_all_carries_the_same_tags_with_original_tracknumbers(self):
        tracks = [
            {"title": "Tape 1 - Carl Cox",
             "url": "https://archive.org/download/p/1.mp3",
             "duration": 61, "genre": "Jungle"},
            {"title": "Tape 2 - Ellis Dee",
             "url": "https://archive.org/download/p/2.mp3",
             "duration": 90, "genre": "Jungle"},
        ]
        pack = "Dreamscape 19 - 1995"
        with mock.patch.object(routes.archive, "audio_files", return_value=tracks), \
                mock.patch.object(routes.archive, "item_title", return_value=pack), \
                mock.patch.object(routes.http.socket, "getaddrinfo",
                                  return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            routes.play_all(1, {"id": "p"})
        _url, listitem = xbmc.PLAYED[-1].items[0]
        info = listitem.info["music"]
        self.assertEqual(info["album"], pack)
        self.assertEqual(info["artist"], "Carl Cox")
        self.assertEqual(info["year"], 1995)
        self.assertEqual(info["genre"], "Jungle")
        self.assertEqual(info["tracknumber"], 1)


class SceneGenreTests(unittest.TestCase):
    def _tracks(self, metadata):
        files = [{"name": "A.mp3", "source": "original", "format": "VBR MP3"}]
        with mock.patch.object(archive, "item",
                               return_value={"metadata": metadata, "files": files}):
            return archive.audio_files("pack")

    def test_archive_subject_tags_become_a_display_genre(self):
        self.assertEqual(self._tracks({"title": "Pack",
                                       "subject": ["Jungle", "Drum & Bass"]})[0]["genre"],
                         "Drum & Bass")
        self.assertEqual(self._tracks({"title": "Pack", "subject": "UK Garage"})[0]["genre"],
                         "UK Garage")
        self.assertEqual(self._tracks({"title": "Pack", "subject": "Hardcore"})[0]["genre"],
                         "Hardcore")

    def test_unknown_subject_leaves_genre_blank(self):
        self.assertEqual(self._tracks({"title": "Pack"})[0]["genre"], "")
        self.assertEqual(self._tracks({"title": "Pack", "subject": "Field recording"})[0]["genre"],
                         "")

    def test_an_explicit_genre_word_in_the_title_is_a_fallback(self):
        self.assertEqual(self._tracks({"title": "Jungle Fever Vol 2"})[0]["genre"], "Jungle")
        self.assertEqual(self._tracks({"title": "Rave Nation 1994"})[0]["genre"], "Rave")
        self.assertEqual(self._tracks({"title": "Pack", "subject": "Jungle",
                                       "creator": "x"})[0]["genre"], "Jungle")


class YearFromDetailsTests(unittest.TestCase):
    def test_year_reads_parsed_dates(self):
        self.assertEqual(nowplaying.year({"date": "26 Aug 1994"}), 1994)
        self.assertEqual(nowplaying.year({"date": "1994"}), 1994)
        self.assertEqual(nowplaying.year({"date": "10 Mar 1992"}), 1992)
        self.assertEqual(nowplaying.year({}), 0)
        self.assertEqual(nowplaying.year({"date": "unknown"}), 0)
        self.assertEqual(nowplaying.year(None), 0)


class AboutPlotTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]

    def test_about_descriptions_are_visible_on_kodi_22(self):
        with mock.patch.object(kodi, "KODI_MAJOR", 22):
            routes.about(1, {})
        soundcloud = next(item for item in xbmcplugin.ITEMS
                          if item["label"] == "Source: SoundCloud")
        self.assertIn("Web version only", soundcloud["info"]["video"]["plot"])
        self.assertIn("Web version only", soundcloud["info"]["music"]["comment"])


if __name__ == "__main__":
    unittest.main()
