# -*- coding: utf-8 -*-
"""Offline route tests for the 3.9.14 sources and menus."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import routes  # noqa: E402


class NewSourceRouteTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]
        del xbmcplugin.CONTENT[:]

    def _labels(self):
        return [item["label"] for item in xbmcplugin.ITEMS]

    def _urls(self):
        return [item["url"] for item in xbmcplugin.ITEMS]

    def test_root_is_the_nine_row_journey(self):
        routes.root(1, {})
        self.assertEqual(self._labels(), [
            "Latest", "Surprise Me", "Tape Packs", "Mixes & Shows",
            "Live Radio", "Curated Gems", "Favourites",
            "Search the Archive", "About & Sources",
        ])
        urls = dict(zip(self._labels(), self._urls()))
        self.assertIn("mode=packs_menu", urls["Tape Packs"])
        self.assertIn("mode=shows_menu", urls["Mixes & Shows"])
        self.assertIn("mode=radio_menu", urls["Live Radio"])
        self.assertIn("mode=curated_menu", urls["Curated Gems"])

    def test_shows_hub_contains_the_new_sources(self):
        with mock.patch.object(routes.handoff, "available", return_value=False):
            routes.shows_menu(1, {})
        self.assertEqual(self._labels(), [
            "Podcasts & Mixes", "DNB Radio", "Moxser Mixes",
            "Hardscore.com", "Back",
        ])
        del xbmcplugin.ITEMS[:]
        with mock.patch.object(routes.handoff, "available", return_value=True):
            routes.shows_menu(1, {})
        labels = self._labels()
        self.assertEqual(labels, [
            "Podcasts & Mixes", "DNB Radio", "Moxser Mixes",
            "Hardscore.com", "GetDarker (dubstep/grime)", "Back",
        ])
        urls = dict(zip(labels, self._urls()))
        self.assertIn("mode=moxser", urls["Moxser Mixes"])
        self.assertIn("mode=hardscore", urls["Hardscore.com"])
        self.assertIn("mode=getdarker", urls["GetDarker (dubstep/grime)"])

    def test_tape_packs_hub_has_all_ten_existing_destinations(self):
        routes.packs_menu(1, {})
        labels = self._labels()
        self.assertEqual(labels, [
            "Rave Tape Packs", "Jungle / Drum & Bass", "Hardcore", "House",
            "UK Garage", "Pirate Stations", "All Tape Packs", "By Year",
            "Classic Pack Series", "By Rave & Venue", "Back",
        ])
        urls = dict(zip(labels, self._urls()))
        self.assertIn("mode=archive_list", urls["Rave Tape Packs"])
        self.assertIn("key=rave", urls["Rave Tape Packs"])
        self.assertIn("key=garage", urls["UK Garage"])
        self.assertIn("key=pirate", urls["Pirate Stations"])
        self.assertIn("mode=years", urls["By Year"])
        self.assertIn("mode=filters_menu", urls["Classic Pack Series"])
        self.assertIn("mode=rave_nights", urls["By Rave & Venue"])

    def test_curated_hub_hides_rave_archive_without_mixcloud_addon(self):
        with mock.patch.object(routes.handoff, "available", return_value=False):
            routes.curated_menu(1, {})
        self.assertEqual(self._labels(), [
            "Pirate Radio Archives", "Legacy Archives (2014)", "Back",
        ])

    def test_curated_hub_shows_rave_archive_with_mixcloud_addon(self):
        with mock.patch.object(routes.handoff, "available", return_value=True):
            routes.curated_menu(1, {})
        self.assertEqual(self._labels(), [
            "Pirate Radio Archives", "Rave Archive UK",
            "Legacy Archives (2014)", "Back",
        ])
        urls = dict(zip(self._labels(), self._urls()))
        self.assertIn("mode=mixcloud_account", urls["Rave Archive UK"])
        self.assertIn("key=rave-archive-uk", urls["Rave Archive UK"])

    def test_live_radio_hub_promotes_kool_and_rinse(self):
        routes.radio_menu(1, {})
        labels = self._labels()
        self.assertEqual(labels, [
            "Kool FM", "Rinse FM", "Oldskool & Rave", "Jungle",
            "Drum & Bass", "Hardcore", "House", "UK Garage", "Breakbeat", "Back",
        ])
        urls = dict(zip(labels, self._urls()))
        self.assertIn("mode=filter_list", urls["Kool FM"])
        self.assertIn("key=kool", urls["Kool FM"])
        self.assertIn("key=rinse", urls["Rinse FM"])

    def test_about_and_sources_lists_credits_and_every_source(self):
        routes.about(1, {})
        labels = self._labels()
        for expected in ("GPL-3.0", "archive.org", "Mixcloud", "SoundCloud",
                         "radio-browser.info", "Moxser.com", "Hardscore.com",
                         "GetDarker.com", "Kool FM", "Rinse FM"):
            self.assertTrue(any(expected in label for label in labels), expected)
        # Credits stay read-only; no row leaves Kodi or opens a browser.
        for item in xbmcplugin.ITEMS[:-1]:
            self.assertEqual(item["url"], "")
            self.assertEqual(item["properties"].get("IsPlayable"), "false")

    def test_pirate_menu_only_shows_direct_file_stations(self):
        routes.pirate_menu(1, {})
        self.assertEqual(self._labels(), [
            "Weekend Rush 92.3  [COLOR gray](2 recordings)[/COLOR]", "Back",
        ])
        del xbmcplugin.ITEMS[:]
        routes.pirate_station(1, {"station": "Weekend Rush 92.3"})
        urls = self._urls()
        self.assertEqual(len(urls), 3)  # two recordings + Back
        self.assertTrue(any("mode=play" in url and "hardscore.com" in url for url in urls))

    def test_metadata_only_pirate_station_is_hidden(self):
        with mock.patch.object(routes.kodi, "notify") as notify:
            routes.pirate_station(1, {"station": "Risk FM 107.1"})
        self.assertEqual(xbmcplugin.ITEMS, [])
        self.assertTrue(notify.called)

    def test_moxser_list_and_detail(self):
        row = {"page_url": "https://moxser.com/mixes/test-mix",
               "title": "Test Mix", "date": "2026-10-26",
               "flyer": "https://moxser.com/flyer.jpg"}
        with mock.patch.object(routes.moxser_source, "mixes", return_value=[row]):
            routes.moxser(1, {})
        self.assertIn("mode=moxser_mix", xbmcplugin.ITEMS[0]["url"])
        del xbmcplugin.ITEMS[:]
        details = {"title": "Test Mix", "date": "2026-10-26", "mp3_url":
                   "https://enceladus.feralhosting.com/moxser/test.mp3"}
        with mock.patch.object(routes.moxser_source, "mix", return_value=details):
            routes.moxser_mix(1, {"page": row["page_url"]})
        self.assertIn("mode=play", xbmcplugin.ITEMS[0]["url"])
        self.assertIn("test.mp3", xbmcplugin.ITEMS[0]["url"])

    def test_moxser_detail_without_mp3_is_hidden(self):
        details = {"title": "Test Mix", "date": "", "mp3_url": ""}
        with mock.patch.object(routes.moxser_source, "mix", return_value=details), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.moxser_mix(1, {"page": "https://moxser.com/mixes/test-mix"})
        self.assertEqual(xbmcplugin.ITEMS, [])
        self.assertTrue(notify.called)

    def test_hardscore_rows_use_direct_media_and_post_pages(self):
        rows = [
            {"title": "With audio", "page_url": "https://www.hardscore.com/?p=1",
             "date": "2023-11-22", "media_urls": ["https://hardscore.com/a.mp3"],
             "description": "Tracklist"},
            {"title": "Post only", "page_url": "https://www.hardscore.com/?p=2",
             "date": "", "media_urls": [], "description": ""},
        ]
        with mock.patch.object(routes.hardscore_source, "items", return_value=rows):
            routes.hardscore(1, {})
        urls = self._urls()
        self.assertTrue(any("mode=play" in url and "a.mp3" in url for url in urls))
        self.assertTrue(any("mode=hardscore_event" in url for url in urls))

    def test_hardscore_event_handoffs_links_to_kodi_addons_only(self):
        details = {"title": "Post", "media_urls": ["https://hardscore.com/a.mp3"],
                   "links": ["https://www.mixcloud.com/Hardscore/x/",
                             "https://www.youtube.com/watch?v=abc123",
                             "https://soundcloud.com/artist/track"]}
        with mock.patch.object(routes.hardscore_source, "page", return_value=details), \
                mock.patch.object(routes.handoff, "available", return_value=True):
            routes.hardscore_event(1, {"page": "https://www.hardscore.com/?p=1"})
        urls = self._urls()
        self.assertTrue(any("mode=play" in url for url in urls))
        self.assertTrue(any("plugin.audio.mixcloud" in url for url in urls))
        self.assertTrue(any("plugin.video.youtube" in url for url in urls))
        self.assertTrue(any("plugin.audio.soundcloud" in url for url in urls))
        self.assertFalse(any("mode=open_url" in url for url in urls))

    def test_hardscore_event_hides_links_without_addons(self):
        details = {"title": "Post", "media_urls": [],
                   "links": ["https://www.mixcloud.com/Hardscore/x/"]}
        with mock.patch.object(routes.hardscore_source, "page", return_value=details), \
                mock.patch.object(routes.handoff, "available", return_value=False), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.hardscore_event(1, {"page": "https://www.hardscore.com/?p=1"})
        self.assertEqual(xbmcplugin.ITEMS, [])
        self.assertTrue(notify.called)

    def test_getdarker_is_hidden_without_mixcloud_addon(self):
        with mock.patch.object(routes.handoff, "available", return_value=False), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.getdarker(1, {})
        self.assertEqual(xbmcplugin.ITEMS, [])
        self.assertTrue(notify.called)

    def test_getdarker_lists_rss_and_mixcloud_handoff(self):
        rows = [{"title": "Set", "page_url": "https://getdarker.com/audio/sets/x/",
                 "date": "2008-01-01", "media_urls": [], "description": ""}]
        with mock.patch.object(routes.getdarker_source, "items", return_value=rows), \
                mock.patch.object(routes.handoff, "available", return_value=True):
            routes.getdarker(1, {})
        self.assertIn("GetDarker on Mixcloud", self._labels())
        urls = self._urls()
        self.assertTrue(any("plugin.audio.mixcloud" in url for url in urls))
        self.assertTrue(any("mode=getdarker_page" in url for url in urls))
        self.assertFalse(any("mode=open_url" in url for url in urls))

    def test_getdarker_page_handoffs_youtube_and_soundcloud(self):
        details = {"title": "Set", "media_urls": [],
                   "links": ["https://www.youtube.com/watch?v=abc123",
                             "https://soundcloud.com/artist/track"]}
        with mock.patch.object(routes.getdarker_source, "page", return_value=details), \
                mock.patch.object(routes.handoff, "available", return_value=True):
            routes.getdarker_page(1, {"page": "https://getdarker.com/audio/sets/x/"})
        urls = self._urls()
        self.assertTrue(any("plugin.video.youtube" in url for url in urls))
        self.assertTrue(any("plugin.audio.soundcloud" in url for url in urls))
        self.assertFalse(any("mode=open_url" in url for url in urls))

    def test_getdarker_page_hides_links_without_addons(self):
        details = {"title": "Set", "media_urls": [],
                   "links": ["https://www.youtube.com/watch?v=abc123"]}
        with mock.patch.object(routes.getdarker_source, "page", return_value=details), \
                mock.patch.object(routes.handoff, "available", return_value=False), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.getdarker_page(1, {"page": "https://getdarker.com/audio/sets/x/"})
        self.assertEqual(xbmcplugin.ITEMS, [])
        self.assertTrue(notify.called)

    def test_mixcloud_account_is_hidden_without_mixcloud_addon(self):
        with mock.patch.object(routes.handoff, "available", return_value=False), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.mixcloud_account(1, {"key": "getdarker"})
        self.assertEqual(xbmcplugin.ITEMS, [])
        self.assertTrue(notify.called)

    def test_mixcloud_account_hands_off_cloudcasts_to_kodi_addon(self):
        rows = [{"title": "Skream", "url": "https://www.mixcloud.com/getdarker/skream/",
                 "created": "2021-03-15T14:45:05Z", "thumb": ""}]
        with mock.patch.object(routes.mixcloud_source, "cloudcasts", return_value=rows), \
                mock.patch.object(routes.handoff, "available", return_value=True):
            routes.mixcloud_account(1, {"key": "getdarker"})
        self.assertIn("plugin://plugin.audio.mixcloud/", xbmcplugin.ITEMS[0]["url"])
        self.assertIn("mode=40", xbmcplugin.ITEMS[0]["url"])
        self.assertFalse(any("mode=open_url" in url for url in self._urls()))

    def test_no_browser_or_open_url_route_remains(self):
        self.assertNotIn("open_url", routes.HANDLERS)
        self.assertFalse(hasattr(routes.kodi, "open_external"))


if __name__ == "__main__":
    unittest.main()
