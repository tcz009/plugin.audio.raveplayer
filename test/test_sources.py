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

    def test_root_is_the_ten_row_journey(self):
        routes.root(1, {})
        self.assertEqual(self._labels(), [
            "Rave Screen", "Latest", "Tape Packs", "Pirate Radio",
            "Mixes & Shows", "Live Radio", "Favourites", "Search the Archive",
            "Surprise Me", "About & Sources",
        ])
        urls = dict(zip(self._labels(), self._urls()))
        self.assertIn("mode=screen", urls["Rave Screen"])
        self.assertIn("mode=packs_menu", urls["Tape Packs"])
        self.assertIn("mode=pirate_radio", urls["Pirate Radio"])
        self.assertIn("mode=shows_menu", urls["Mixes & Shows"])
        self.assertIn("mode=radio_menu", urls["Live Radio"])

    def test_shows_hub_is_the_four_living_feeds(self):
        routes.shows_menu(1, {})
        self.assertEqual(self._labels(), [
            "Podcasts & Mixes", "DNBRADIO", "GetDarker", "Moxser", "Back",
        ])
        urls = dict(zip(self._labels(), self._urls()))
        self.assertIn("mode=media_menu", urls["Podcasts & Mixes"])
        self.assertIn("mode=dnb_list", urls["DNBRADIO"])
        self.assertIn("mode=getdarker", urls["GetDarker"])
        self.assertIn("mode=moxser", urls["Moxser"])

    def test_tape_packs_hub_is_the_2026_order(self):
        routes.packs_menu(1, {})
        self.assertEqual(self._labels(), [
            "Toronto Rave Mixtape Archive", "JungleTapes.com",
            "RaveTapePacks.com", "Classic Pack Series",
            "By Rave, Venue & Promoter", "By Year", "Every Pack", "Back",
        ])
        urls = dict(zip(self._labels(), self._urls()))
        self.assertIn("mode=toronto", urls["Toronto Rave Mixtape Archive"])
        self.assertIn("mode=legacy_jt", urls["JungleTapes.com"])
        self.assertIn("mode=legacy_menu", urls["RaveTapePacks.com"])
        self.assertIn("mode=filters_menu", urls["Classic Pack Series"])
        self.assertIn("mode=rave_nights", urls["By Rave, Venue & Promoter"])
        self.assertIn("mode=years", urls["By Year"])
        self.assertIn("key=tapepacks", urls["Every Pack"])

    def test_pirate_radio_hub_has_three_children(self):
        routes.pirate_radio(1, {})
        self.assertEqual(self._labels(), [
            "Hardscore", "Pirate Radio Archives", "Kool FM Sets", "Back",
        ])
        urls = dict(zip(self._labels(), self._urls()))
        self.assertIn("mode=hardscore", urls["Hardscore"])
        self.assertIn("mode=pirate_menu", urls["Pirate Radio Archives"])
        self.assertIn("mode=filter_list", urls["Kool FM Sets"])
        self.assertIn("key=kool", urls["Kool FM Sets"])

    def test_live_radio_names_stations_then_genres(self):
        routes.radio_menu(1, {})
        self.assertEqual(self._labels(), [
            "Kool FM", "Rinse FM", "Centreforce 883",
            "Hardcore", "Jungle", "Drum & Bass", "House", "UK Garage",
            "Dubstep & Grime", "Back",
        ])
        urls = dict(zip(self._labels(), self._urls()))
        self.assertIn("mode=filter_list", urls["Kool FM"])
        self.assertIn("key=kool", urls["Kool FM"])
        self.assertIn("mode=station_live", urls["Centreforce 883"])
        self.assertIn("token=centreforce", urls["Centreforce 883"])

    def test_ravetapepacks_submenu_exposes_its_native_index(self):
        routes.legacy_menu(1, {})
        self.assertEqual(self._labels(), [
            "By Event", "By DJ", "By MC", "By Year", "All Packs", "Back",
        ])
        urls = dict(zip(self._labels(), self._urls()))
        for label, kind in (("By Event", "event"), ("By DJ", "dj"),
                            ("By MC", "mc"), ("By Year", "year")):
            self.assertIn("mode=legacy_index", urls[label])
            self.assertIn("kind=" + kind, urls[label])
        self.assertIn("mode=legacy_packs", urls["All Packs"])

    def test_ravetapepacks_index_opens_each_kind_s_category_route(self):
        categories = {
            "events": [{"id": "5", "name": "Dreamscape"}],
            "djs": [{"id": "106", "name": "Brockie"}],
            "mcs": [{"id": "203", "name": "Bassman"}],
            "years": [{"id": "56", "name": "1992"}],
        }
        for kind in ("event", "dj", "mc", "year"):
            del xbmcplugin.ITEMS[:]
            with mock.patch.object(routes.legacy, "categories",
                                   return_value=categories):
                routes.legacy_index(1, {"kind": kind})
            url = xbmcplugin.ITEMS[0]["url"]
            self.assertIn("mode=legacy_category", url)
            self.assertIn("kind=" + kind, url)
            self.assertIn("cat=" + categories[routes.RTP_INDEX_KINDS[kind]][0]["id"],
                          url)

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
        soundcloud = next(item for item in xbmcplugin.ITEMS
                          if item["label"] == "Source: SoundCloud")
        self.assertIn("Web version only", soundcloud["info"]["music"]["plot"])

    def test_pirate_menu_only_shows_direct_file_stations(self):
        routes.pirate_menu(1, {})
        self.assertEqual(self._labels(), [
            "Risk FM 107.1  [COLOR gray](1 recording)[/COLOR]",
            "Weekend Rush 92.3  [COLOR gray](2 recordings)[/COLOR]", "Back",
        ])
        del xbmcplugin.ITEMS[:]
        routes.pirate_station(1, {"station": "Weekend Rush 92.3"})
        urls = self._urls()
        self.assertEqual(len(urls), 3)  # two recordings + Back
        self.assertTrue(any("mode=play" in url and "hardscore.com" in url for url in urls))
        del xbmcplugin.ITEMS[:]
        routes.pirate_station(1, {"station": "Risk FM 107.1"})
        self.assertTrue(any("mode=play" in url and "risk_fm_107_1.mp3" in url
                            for url in self._urls()))

    def test_metadata_only_pirate_station_is_hidden(self):
        with mock.patch.object(routes.kodi, "notify") as notify:
            routes.pirate_station(1, {"station": "Flava FM"})
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
        self.assertFalse(any("plugin.audio.soundcloud" in url for url in urls))
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

    def test_getdarker_page_handoffs_youtube_only(self):
        details = {"title": "Set", "media_urls": [],
                   "links": ["https://www.youtube.com/watch?v=abc123",
                             "https://soundcloud.com/artist/track"]}
        with mock.patch.object(routes.getdarker_source, "page", return_value=details), \
                mock.patch.object(routes.handoff, "available", return_value=True):
            routes.getdarker_page(1, {"page": "https://getdarker.com/audio/sets/x/"})
        urls = self._urls()
        self.assertTrue(any("plugin.video.youtube" in url for url in urls))
        self.assertFalse(any("plugin.audio.soundcloud" in url for url in urls))
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

    def _assert_no_raw_platform_url(self, items, allow_plugin=()):
        forbidden = ("mixcloud.com", "soundcloud.com", "youtube.com", "youtu.be")
        for item in items:
            url = item["url"]
            for token in forbidden:
                self.assertNotIn(token, url, item["label"])
            self.assertTrue(url.startswith("plugin://") or "mode=" in url, url)
        if not allow_plugin:
            for item in items:
                self.assertNotIn("plugin://plugin.audio.mixcloud", item["url"])
                self.assertNotIn("plugin://plugin.video.youtube", item["url"])

    def test_saved_mixcloud_favourite_is_hidden_without_addon(self):
        entries = [{"kind": "stream", "target": "https://www.mixcloud.com/getdarker/x/",
                    "title": "Saved Mixcloud", "source": "Mixcloud"}]
        with mock.patch.object(routes.favourites, "load", return_value=entries), \
                mock.patch.object(routes.handoff, "available", return_value=False):
            routes.fav_list(1, {})
        self.assertEqual([item["label"] for item in xbmcplugin.ITEMS],
                         ["Downloads  [COLOR gray](0)[/COLOR]"])
        self.assertFalse(any("mixcloud.com" in item["url"] for item in xbmcplugin.ITEMS))

    def test_saved_mixcloud_favourite_hands_off_with_addon(self):
        entries = [{"kind": "stream", "target": "https://www.mixcloud.com/getdarker/x/",
                    "title": "Saved Mixcloud", "source": "Mixcloud"}]
        with mock.patch.object(routes.favourites, "load", return_value=entries), \
                mock.patch.object(routes.handoff, "available", return_value=True):
            routes.fav_list(1, {})
        self.assertEqual(len(xbmcplugin.ITEMS), 2)
        self.assertIn("mode=downloads_menu", xbmcplugin.ITEMS[0]["url"])
        self.assertIn("plugin://plugin.audio.mixcloud", xbmcplugin.ITEMS[1]["url"])
        self.assertNotIn("mixcloud.com", xbmcplugin.ITEMS[1]["url"])

    def test_latest_mixcloud_episode_is_hidden_without_addon(self):
        items = [{"kind": "episode", "title": "Episode",
                  "url": "https://www.mixcloud.com/getdarker/x/", "source": "Mixcloud",
                  "when": None, "duration": None}]
        with mock.patch.object(routes.latest, "merge", return_value=items), \
                mock.patch.object(routes.radio, "curated", return_value=[]), \
                mock.patch.object(routes.handoff, "available", return_value=False):
            routes.latest_view(1, {})
        self.assertFalse(any("mixcloud.com" in item["url"] for item in xbmcplugin.ITEMS))
        self.assertFalse(any("plugin.audio.mixcloud" in item["url"]
                             for item in xbmcplugin.ITEMS))

    def test_latest_mixcloud_episode_hands_off_with_addon(self):
        items = [{"kind": "episode", "title": "Episode",
                  "url": "https://www.mixcloud.com/getdarker/x/", "source": "Mixcloud",
                  "when": None, "duration": None}]
        with mock.patch.object(routes.latest, "merge", return_value=items), \
                mock.patch.object(routes.radio, "curated", return_value=[]), \
                mock.patch.object(routes.handoff, "available", return_value=True):
            routes.latest_view(1, {})
        self.assertEqual(len(xbmcplugin.ITEMS), 2)  # hand-off + End of list
        url = xbmcplugin.ITEMS[0]["url"]
        self.assertIn("plugin://plugin.audio.mixcloud", url)
        self.assertNotIn("mixcloud.com", url)

    def test_feed_mixcloud_episode_hands_off_with_addon(self):
        entry = {"id": "f", "name": "Feed", "url": "https://x/feed", "plot": ""}
        episodes = [{"title": "Episode", "url": "https://www.mixcloud.com/getdarker/x/",
                     "published": "", "description": "", "duration": None}]
        with mock.patch.object(routes.feeds, "feed", return_value=entry), \
                mock.patch.object(routes.feeds, "episodes", return_value=episodes), \
                mock.patch.object(routes.handoff, "available", return_value=True):
            routes.feed(1, {"key": "f"})
        self.assertEqual(len(xbmcplugin.ITEMS), 1)
        self.assertIn("plugin://plugin.audio.mixcloud", xbmcplugin.ITEMS[0]["url"])
        self.assertNotIn("mixcloud.com", xbmcplugin.ITEMS[0]["url"])

    def test_feed_mixcloud_episode_is_hidden_without_addon(self):
        entry = {"id": "f", "name": "Feed", "url": "https://x/feed", "plot": ""}
        episodes = [{"title": "Episode", "url": "https://www.mixcloud.com/getdarker/x/",
                     "published": "", "description": "", "duration": None}]
        with mock.patch.object(routes.feeds, "feed", return_value=entry), \
                mock.patch.object(routes.feeds, "episodes", return_value=episodes), \
                mock.patch.object(routes.handoff, "available", return_value=False):
            routes.feed(1, {"key": "f"})
        self.assertEqual(xbmcplugin.ITEMS, [])

    def test_play_route_rejects_raw_platform_urls(self):
        for url in ("https://www.mixcloud.com/getdarker/x/",
                    "https://www.youtube.com/watch?v=abc",
                    "https://soundcloud.com/a/b"):
            with mock.patch.object(routes.kodi, "notify") as notify:
                routes.play(1, {"url": url})
            self.assertTrue(notify.called)
            self.assertFalse(xbmcplugin.RESOLVED[-1]["ok"])
            self.assertNotIn("mixcloud.com", xbmcplugin.RESOLVED[-1]["path"])
            self.assertNotIn("youtube.com", xbmcplugin.RESOLVED[-1]["path"])
            self.assertNotIn("soundcloud.com", xbmcplugin.RESOLVED[-1]["path"])

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
