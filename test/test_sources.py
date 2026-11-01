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

    def test_curated_hub_has_three_doors(self):
        routes.curated_menu(1, {})
        self.assertEqual(self._labels(), [
            "Pirate Radio Archives", "Rave Archive UK",
            "Legacy Archives (2014)", "Back",
        ])
        urls = dict(zip(self._labels(), self._urls()))
        self.assertIn("mode=pirate_menu", urls["Pirate Radio Archives"])
        self.assertIn("mode=mixcloud_account", urls["Rave Archive UK"])
        self.assertIn("key=rave-archive-uk", urls["Rave Archive UK"])
        self.assertIn("mode=legacy_menu", urls["Legacy Archives (2014)"])

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
        first = xbmcplugin.ITEMS[0]
        self.assertIn("mode=open_url", first["url"])
        self.assertIn("github.com", first["url"].replace("%2F", "/").replace("%3A", ":"))

    def test_pirate_menu_and_weekend_rush_playlist(self):
        routes.pirate_menu(1, {})
        labels = self._labels()
        self.assertIn("Risk FM 107.1  [COLOR gray](1 recording)[/COLOR]", labels)
        self.assertIn("Weekend Rush 92.3  [COLOR gray](2 recordings)[/COLOR]", labels)
        del xbmcplugin.ITEMS[:]
        routes.pirate_station(1, {"station": "Weekend Rush 92.3"})
        urls = self._urls()
        self.assertEqual(len(urls), 3)  # two recordings + Back
        self.assertTrue(any("mode=play" in url and "hardscore.com" in url for url in urls))

    def test_metadata_only_pirate_entry_notifies(self):
        routes.pirate_station(1, {"station": "Risk FM 107.1"})
        item = xbmcplugin.ITEMS[0]
        self.assertIn("metadata only", item["label"])
        self.assertIn("mode=pirate_note", item["url"])
        with mock.patch.object(routes.kodi, "notify") as notify:
            routes.pirate_note(1, {"station": "Risk FM 107.1",
                                   "title": item["info"]["music"]["title"]})
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

    def test_moxser_detail_without_mp3_offers_the_page(self):
        details = {"title": "Test Mix", "date": "", "mp3_url": ""}
        with mock.patch.object(routes.moxser_source, "mix", return_value=details):
            routes.moxser_mix(1, {"page": "https://moxser.com/mixes/test-mix"})
        self.assertIn("mode=open_url", xbmcplugin.ITEMS[0]["url"])

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

    def test_hardscore_event_lists_media_and_links(self):
        details = {"title": "Post", "media_urls": ["https://hardscore.com/a.mp3"],
                   "links": ["https://www.mixcloud.com/Hardscore/x/"]}
        with mock.patch.object(routes.hardscore_source, "page", return_value=details):
            routes.hardscore_event(1, {"page": "https://www.hardscore.com/?p=1"})
        urls = self._urls()
        self.assertTrue(any("mode=play" in url for url in urls))
        self.assertTrue(any("mode=open_url" in url for url in urls))

    def test_getdarker_lists_rss_and_mixcloud_link(self):
        rows = [{"title": "Set", "page_url": "https://getdarker.com/audio/sets/x/",
                 "date": "2008-01-01", "media_urls": [], "description": ""}]
        with mock.patch.object(routes.getdarker_source, "items", return_value=rows):
            routes.getdarker(1, {})
        self.assertIn("GetDarker on Mixcloud", self._labels())
        urls = self._urls()
        self.assertTrue(any("mode=mixcloud_account" in url for url in urls))
        self.assertTrue(any("mode=getdarker_page" in url for url in urls))

    def test_mixcloud_account_lists_cloudcast_pages(self):
        rows = [{"title": "Skream", "url": "https://www.mixcloud.com/getdarker/skream/",
                 "created": "2021-03-15T14:45:05Z", "thumb": ""}]
        with mock.patch.object(routes.mixcloud_source, "cloudcasts", return_value=rows):
            routes.mixcloud_account(1, {"key": "getdarker"})
        self.assertIn("mode=open_url", xbmcplugin.ITEMS[0]["url"])
        self.assertIn("mixcloud.com", xbmcplugin.ITEMS[0]["url"].replace("%2F", "/")
                      .replace("%3A", ":").lower())

    def test_open_url_validates_and_opens_external_page(self):
        with mock.patch.object(routes.http, "is_public_http_url", return_value=True), \
                mock.patch.object(routes.kodi, "open_external") as opened:
            routes.open_url(1, {"url": "https://www.mixcloud.com/getdarker/"})
        self.assertTrue(opened.called)
        with mock.patch.object(routes.http, "is_public_http_url", return_value=False), \
                mock.patch.object(routes.kodi, "open_external") as opened, \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.open_url(1, {"url": "file:///etc/passwd"})
        self.assertFalse(opened.called)
        self.assertTrue(notify.called)


if __name__ == "__main__":
    unittest.main()
