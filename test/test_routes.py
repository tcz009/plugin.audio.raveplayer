# -*- coding: utf-8 -*-
"""Offline tests for route helpers (no plugin directory, no network)."""

import os
import socket
import sys
import time
import unittest
import urllib.parse
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import routes  # noqa: E402

PUBLIC_INFOS = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]


class RouteHelperTests(unittest.TestCase):
    def test_clean_description_unescapes_and_strips_tags(self):
        value = ["<p>Jungle &amp; drum", "&amp; bass</p>"]
        self.assertEqual(routes._clean_description(value), "Jungle & drum & bass")

    def test_clean_description_keeps_comparisons(self):
        self.assertEqual(routes._clean_description("Recorded at 2 < 3 > 1"), "Recorded at 2 < 3 > 1")

    def test_clean_description_truncates(self):
        self.assertEqual(len(routes._clean_description("x" * 900)), 600)

    def test_clean_description_handles_empty_values(self):
        self.assertEqual(routes._clean_description(None), "")
        self.assertEqual(routes._clean_description([]), "")

    def test_year_label_never_renders_none(self):
        self.assertEqual(routes._year_label({}), "")
        self.assertEqual(routes._year_label({"year": None, "date": None}), "")
        self.assertEqual(routes._year_label({"date": "1995-01-01"}), "1995")
        self.assertEqual(routes._year_label({"year": [1997, 1998]}), "1997")

    def test_page_number_clamps_invalid_values(self):
        self.assertEqual(routes._page_number({"page": "3"}), 3)
        self.assertEqual(routes._page_number({"page": "0"}), 1)
        self.assertEqual(routes._page_number({"page": "nope"}), 1)
        self.assertEqual(routes._page_number({}), 1)

    def test_rows_per_page_falls_back_when_setting_is_zero(self):
        with mock.patch.object(routes.kodi, "setting_int", return_value=0):
            self.assertEqual(routes._rows_per_page(), routes.ROWS_PER_PAGE)
        with mock.patch.object(routes.kodi, "setting_int", return_value=-1):
            self.assertEqual(routes._rows_per_page(), routes.ROWS_PER_PAGE)

    def test_rows_per_page_is_capped(self):
        with mock.patch.object(routes.kodi, "setting_int", return_value=100000):
            self.assertEqual(routes._rows_per_page(), routes.MAX_ROWS_PER_PAGE)

    def test_episode_limit_defaults_and_caps(self):
        with mock.patch.object(routes.kodi, "setting_int", return_value=0):
            self.assertEqual(routes._episode_limit(), routes.EPISODES_PER_FEED)
        with mock.patch.object(routes.kodi, "setting_int", return_value=100000):
            self.assertEqual(routes._episode_limit(), routes.MAX_EPISODES_PER_FEED)
        with mock.patch.object(routes.kodi, "setting_int", return_value=25):
            self.assertEqual(routes._episode_limit(), 25)

    def test_start_index_clamps(self):
        self.assertEqual(routes._start_index({}, 5), 0)
        self.assertEqual(routes._start_index({"start": "-4"}, 5), 0)
        self.assertEqual(routes._start_index({"start": "99"}, 5), 4)
        self.assertEqual(routes._start_index({"start": "nope"}, 5), 0)
        self.assertEqual(routes._start_index({}, 0), 0)

    def test_page_plot_counts_items_and_pages(self):
        self.assertEqual(routes._page_plot(724, 2, 50), "Page 2 of 15 · 724 items")

    def test_flag_reads_kodi_style_booleans(self):
        for value in ("1", "true", "YES", "on"):
            self.assertTrue(routes._flag({"shuffle": value}, "shuffle"), value)
        for value in ("0", "false", "", None):
            self.assertFalse(routes._flag({"shuffle": value}, "shuffle"), value)
        self.assertFalse(routes._flag({}, "shuffle"))

    def test_params_from_argv_handles_question_mark_and_blanks(self):
        self.assertEqual(
            routes.params_from_argv(["plugin://x/", "1", "?mode=root&key=rave"]),
            {"mode": "root", "key": "rave"},
        )
        self.assertEqual(routes.params_from_argv(["plugin://x/", "1"]), {})

    def test_archive_items_skips_documents_without_identifier(self):
        docs = [
            {"identifier": "good", "title": ["A", "Title"], "year": "1994"},
            {"title": "no id"},
        ]
        with mock.patch.object(routes.ui, "menu_item") as menu_item:
            routes._archive_items(1, docs)
        self.assertEqual(menu_item.call_count, 1)
        args = menu_item.call_args[0]
        self.assertIn("A Title", args[2])
        self.assertIn("1994", args[2])

    def test_dispatch_without_valid_handle_does_not_raise(self):
        with mock.patch.object(routes.kodi, "log") as log:
            routes.dispatch([])
        self.assertTrue(log.called)

    def test_radio_tag_unknown_section_notifies_and_ends(self):
        with mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.kodi, "end_directory") as end:
            routes.radio_tag(1, {"key": "missing"})
        self.assertTrue(notify.called)
        self.assertTrue(end.called)

    def test_legacy_pack_without_key_does_not_fetch(self):
        with mock.patch.object(routes.legacy, "packs") as packs, \
                mock.patch.object(routes.kodi, "notify"), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.legacy_pack(1, {})
        self.assertFalse(packs.called)

    def test_legacy_show_without_key_does_not_fetch(self):
        with mock.patch.object(routes.legacy, "jungle_tracks") as tracks, \
                mock.patch.object(routes.kodi, "notify"), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.legacy_jt_show(1, {})
        self.assertFalse(tracks.called)

    def test_legacy_pack_emits_the_referer_suffix_to_kodi(self):
        tracks = [{"name": "Tape 1",
                   "url": "https://www.ravetapepacks.com/music/Pack/Tape_1.mp3"}]
        del xbmcplugin.ITEMS[:]
        with mock.patch.object(routes.legacy, "pack", return_value={
                "key": "Pack", "name": "Pack", "tracks": tracks}), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.legacy_pack(1, {"pack": "Pack"})
        item = next(entry for entry in xbmcplugin.ITEMS
                    if entry["label"] == "Tape 1")
        params = routes.params_from_argv(
            ["plugin://plugin.audio.raveplayer/", "1", item["url"].split("?", 1)[1]])
        self.assertEqual(params["mode"], "play")
        self.assertTrue(params["url"].endswith(routes.legacy.REFERER_SUFFIX))

    def test_archive_item_without_id_notifies(self):
        with mock.patch.object(routes.archive, "audio_files") as audio, \
                mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.archive_item(1, {})
        self.assertFalse(audio.called)
        self.assertTrue(notify.called)


class RouteRenderTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]
        del xbmcplugin.CACHE_FLAGS[:]
        del xbmcplugin.RESOLVED[:]

    def _menu_calls(self):
        return [(item["label"], item["url"]) for item in xbmcplugin.ITEMS]

    def test_archive_items_get_play_all_shuffle_and_favourite(self):
        docs = [{"identifier": "pack-1", "title": "Pack One"}]
        routes._archive_items(1, docs)
        context = [label for label, _command in xbmcplugin.ITEMS[0]["context"]]
        self.assertEqual(context, ["Play all", "Shuffle pack", "Add to favourites"])

    def test_archive_item_tracks_offer_play_from_here_and_favourite(self):
        tracks = [{"title": "One", "url": "https://archive.org/download/p/1.mp3", "duration": 61}]
        with mock.patch.object(routes.archive, "audio_files", return_value=tracks), \
                mock.patch.object(routes.archive, "item_title", return_value="Pack One"):
            routes.archive_item(1, {"id": "pack-1"})
        item = xbmcplugin.ITEMS[0]
        context = [label for label, _command in item["context"]]
        self.assertEqual(context, ["Play all from here", "Add to favourites", "Download"])
        self.assertIn("start=0", item["context"][0][1])
        self.assertEqual(item["info"]["music"]["duration"], 61)

    def test_archive_item_passes_pack_cover_and_parsed_plot_to_playback(self):
        tracks = [{"title": "Tape 1 - Carl Cox", "url": "https://archive.org/download/p/1.mp3"}]
        with mock.patch.object(routes.archive, "audio_files", return_value=tracks), \
                mock.patch.object(routes.archive, "item_title",
                                  return_value="Dreamscape 19 - 1995"):
            routes.archive_item(1, {"id": "pack-1"})
        item = xbmcplugin.ITEMS[0]
        thumb = routes.archive.thumb("pack-1")
        self.assertEqual(item["art"]["fanart"], thumb)
        self.assertEqual(item["art"]["thumb"], thumb)
        plot = item["info"]["music"]["plot"]
        self.assertEqual(item["info"]["music"].get("comment"), plot)
        self.assertIn("Carl Cox", plot)
        self.assertIn("Dreamscape", plot)
        self.assertIn("1995", plot)
        self.assertIn("From archive.org item pack-1", plot)
        self.assertIn("mode=play", item["url"])
        self.assertIn("fanart=", item["url"])
        self.assertIn("plot=", item["url"])

    def test_play_resolver_sets_fanart_and_plot_on_the_resolved_item(self):
        with mock.patch.object(routes.http.socket, "getaddrinfo", return_value=PUBLIC_INFOS):
            routes.play(1, {
            "url": "https://archive.org/download/p/1.mp3",
            "label": "[I]Tape 1[/I]",
            "thumb": "https://art.example.test/thumb",
            "fanart": "https://art.example.test/fanart",
                "plot": "Carl Cox · Dreamscape · 1995 — From archive.org item p",
            })
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["path"], "https://archive.org/download/p/1.mp3")
        self.assertEqual(resolved["art"]["thumb"], "https://art.example.test/thumb")
        self.assertEqual(resolved["art"]["fanart"], "https://art.example.test/fanart")
        self.assertEqual(resolved["info"]["music"]["title"], "Tape 1")
        self.assertIn("Carl Cox", resolved["info"]["music"]["plot"])
        self.assertEqual(resolved["info"]["music"].get("comment"),
                         resolved["info"]["music"]["plot"])

    def test_play_resolver_without_fanart_keeps_the_old_art(self):
        with mock.patch.object(routes.http.socket, "getaddrinfo", return_value=PUBLIC_INFOS):
            routes.play(1, {"url": "https://example.test/1.mp3", "thumb": "https://art.example.test/thumb"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertEqual(resolved["art"], {"thumb": "https://art.example.test/thumb", "icon": "https://art.example.test/thumb"})
        self.assertNotIn("plot", resolved["info"]["music"])
        self.assertNotIn("comment", resolved["info"]["music"])

    def test_search_with_query_paginates_without_a_dialog(self):
        docs = [{"identifier": "pack-1", "title": "Pack One"}]
        with mock.patch.object(routes.archive, "search", return_value=(docs, 120)) as search, \
                mock.patch.object(routes.kodi, "setting_int", return_value=50), \
                mock.patch.object(routes.kodi, "dialog") as dialog, \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.search(1, {"q": "jungle"})
        self.assertFalse(dialog.called)
        self.assertEqual(search.call_args[1]["page"], 1)
        labels = [label for label, _url in self._menu_calls()]
        self.assertIn("Next page  ›", labels)
        next_url = [url for label, url in self._menu_calls() if label.startswith("Next page")][0]
        self.assertIn("mode=search", next_url)
        self.assertIn("q=jungle", next_url)
        self.assertIn("page=2", next_url)

    def test_search_without_query_or_dialog_ends_empty(self):
        with mock.patch.object(routes.kodi, "dialog") as dialog, \
                mock.patch.object(routes.kodi, "end_directory") as end, \
                mock.patch.object(routes.archive, "search") as search:
            dialog.return_value.input.return_value = "   "
            routes.search(1, {})
        self.assertFalse(search.called)
        self.assertTrue(end.called)

    def test_empty_page_does_not_offer_another_page(self):
        with mock.patch.object(routes.archive, "search", return_value=([], 120)), \
                mock.patch.object(routes.kodi, "setting_int", return_value=50), \
                mock.patch.object(routes.kodi, "notify"), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.archive_list(1, {"key": "rave"})
        labels = [label for label, _url in self._menu_calls()]
        self.assertFalse(any(label.startswith("Next page") for label in labels))

    def test_year_list_next_page_points_at_page_two(self):
        docs = [{"identifier": "pack-1", "title": "Pack One"}]
        with mock.patch.object(routes.archive, "search", return_value=(docs, 120)), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.year_list(1, {"year": "1994"})
        labels = [label for label, _url in self._menu_calls()]
        self.assertIn("More from 1994", labels)
        next_url = [url for label, url in self._menu_calls() if label == "More from 1994"][0]
        self.assertIn("mode=year_list", next_url)
        self.assertIn("page=2", next_url)
        self.assertIn("year=1994", next_url)

    def test_media_menu_uses_the_episode_limit_and_can_hide_empty_feeds(self):
        registry = [
            {"id": "a", "name": "Feed A", "plot": ""},
            {"id": "b", "name": "Feed B", "plot": ""},
        ]
        episodes = [{"title": "One", "url": "http://x/1.mp3"}, {"title": "Two", "url": "http://x/2.mp3"}]
        with mock.patch.object(routes.feeds, "registry", return_value=registry), \
                mock.patch.object(routes.feeds, "episodes_many",
                                  return_value=[(registry[0], episodes), (registry[1], [])]) as fetch, \
                mock.patch.object(routes, "_episode_limit", return_value=2), \
                mock.patch.object(routes.kodi, "setting_bool", return_value=True), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.media_menu(1, {})
        self.assertEqual(fetch.call_args[1].get("limit"), 2)
        labels = [label for label, _url in self._menu_calls()]
        self.assertEqual(labels, ["Feed A  [COLOR gray](2 episodes)[/COLOR]", "Back"])

    def test_media_menu_without_feeds_notifies(self):
        with mock.patch.object(routes.feeds, "registry", return_value=[]), \
                mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.media_menu(1, {})
        self.assertTrue(notify.called)

    def test_favourite_folders_use_their_own_routes(self):
        entries = [
            {"kind": "legacy_pack", "target": "Dreamscape19", "title": "Dreamscape 19", "source": "RaveTapePacks.com"},
            {"kind": "legacy_jt", "target": "show-1", "title": "Show 1", "source": "JungleTapes.com"},
            {"kind": "dnb", "target": "58125", "title": "DNB Show", "source": "DNB Radio"},
            {"kind": "stream", "target": "https://x/1.mp3", "title": "Episode", "source": "Feed"},
            {"kind": "pack", "target": "pack-1", "title": "Pack", "source": "Archive.org"},
        ]
        with mock.patch.object(routes.favourites, "load", return_value=entries), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.fav_list(1, {})
        urls = [url for _label, url in self._menu_calls()]
        self.assertTrue(any("mode=archive_item" in url for url in urls))
        self.assertTrue(any("mode=legacy_pack" in url for url in urls))
        self.assertTrue(any("mode=legacy_jt_show" in url for url in urls))
        self.assertTrue(any("mode=dnb_play" in url for url in urls))
        self.assertTrue(any("mode=play" in url and "url=https" in url for url in urls))
        self.assertEqual(len(urls), 6)

    def test_fav_add_reports_already_saved_and_refreshes(self):
        with mock.patch.object(routes.favourites, "has", return_value=True), \
                mock.patch.object(routes.favourites, "add", return_value=True), \
                mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.kodi, "refresh") as refresh, \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.fav_add(1, {"kind": "pack", "target": "x", "title": "X"})
        self.assertEqual(notify.call_args[0][0], "Already in favourites")
        self.assertTrue(refresh.called)


class SectionLabelTests(unittest.TestCase):
    def test_house_is_not_double_labelled_garage(self):
        archive = next(section for section in routes.ARCHIVE_SECTIONS if section["key"] == "house")
        self.assertEqual(archive["label"], "House")
        self.assertNotIn("garage", archive["query"].lower())
        radio = next(section for section in routes.RADIO_SECTIONS if section["key"] == "house")
        self.assertEqual(radio["label"], "House")
        self.assertEqual(radio["tag"], "house")
        self.assertFalse(any("House & Garage" in section.get("label", "")
                             for section in routes.RADIO_SECTIONS))

class QuickFilterDataTests(unittest.TestCase):
    def test_filters_are_unique_and_cover_the_web_parity_ids(self):
        entries = routes._filters()
        ids = [entry["id"] for entry in entries]
        self.assertEqual(len(ids), 16)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("dj-ez", ids)
        self.assertIn("garage-nation", ids)
        self.assertIn("rinse", ids)
        for entry in entries:
            self.assertTrue(entry.get("name"), entry)
            self.assertTrue(entry.get("query"), entry)

class LatestCascadeTests(unittest.TestCase):
    """The Latest folder must not become an endless auto-advancing playlist."""

    def setUp(self):
        del xbmcplugin.ITEMS[:]
        del xbmcplugin.RESOLVED[:]
        del xbmcplugin.CONTENT[:]
        del xbmcplugin.CACHE_FLAGS[:]

    @staticmethod
    def _params(item):
        return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(item["url"]).query))

    def test_latest_ends_as_files_drops_dead_dnb_rows_and_marks_the_end(self):
        merged = [
            {"kind": "pack", "identifier": "pack-1", "title": "Pack One",
             "source": "Rave Tape Packs", "when": None},
            {"kind": "dnb", "id": "10", "title": "Reachable DNB",
             "source": "DNB Radio", "when": None},
            {"kind": "dnb", "id": "11", "title": "Unreachable DNB",
             "source": "DNB Radio", "when": None},
        ]

        def fake_fetch(url, timeout=20, headers=None, ttl=0):
            if "mix=10" in url:
                return '<a href="https://proxy.dnbradio.com/10.mp3">'
            return None  # mix=11: host unreachable

        with mock.patch.object(routes.latest, "merge", return_value=merged), \
                mock.patch.object(routes.dnbradio.http, "fetch", side_effect=fake_fetch):
            routes.latest_view(1, {})

        self.assertEqual(xbmcplugin.CONTENT[-1], "files")
        labels = [item["label"] for item in xbmcplugin.ITEMS]
        self.assertTrue(any(label.startswith("Pack One") for label in labels))
        self.assertTrue(any(label.startswith("Reachable DNB") for label in labels))
        self.assertFalse(any("Unreachable DNB" in label for label in labels))
        # A resolved DNB row uses the build-time stream through mode=play, never dnb_play.
        resolved = next(item for item in xbmcplugin.ITEMS
                        if item["label"].startswith("Reachable DNB"))
        params = self._params(resolved)
        self.assertEqual(params["mode"], "play")
        self.assertEqual(params["url"], "https://proxy.dnbradio.com/10.mp3")
        self.assertFalse(any("mode=dnb_play" in item["url"] for item in xbmcplugin.ITEMS))
        # The final row is a visible, deliberately non-playable terminator.
        last = xbmcplugin.ITEMS[-1]
        self.assertEqual(last["label"], "End of list")
        self.assertFalse(last["isFolder"])
        self.assertEqual(last["properties"].get("IsPlayable"), "false")
        self.assertEqual(last["url"], "")

    def test_latest_with_no_items_still_ends_as_files(self):
        with mock.patch.object(routes.latest, "merge", return_value=[]), \
                mock.patch.object(routes.radio, "curated", return_value=[]), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.latest_view(1, {})
        self.assertTrue(notify.called)
        self.assertEqual(xbmcplugin.CONTENT[-1], "files")
        self.assertEqual(xbmcplugin.ITEMS, [])

    def test_latest_prepends_live_on_air_rows(self):
        stations = {"kool": [{"name": "Kool FM",
                              "url_resolved": "https://admin.stream.rinse.fm/proxy/kool/stream"}],
                    "rinse": [{"name": "Rinse FM",
                               "url_resolved": "https://admin.stream.rinse.fm/proxy/rinse_uk/stream"}]}

        def curated(token):
            return stations.get(token, [])

        with mock.patch.object(routes.latest, "merge", return_value=[]), \
                mock.patch.object(routes.radio, "curated", side_effect=curated), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.latest_view(1, {})
        self.assertFalse(notify.called)
        labels = [item["label"] for item in xbmcplugin.ITEMS]
        self.assertEqual(labels[:2], ["● On air now · Kool FM",
                                      "● On air now · Rinse FM"])
        params = self._params(xbmcplugin.ITEMS[0])
        self.assertEqual(params["mode"], "play")
        self.assertIn("admin.stream.rinse.fm/proxy/kool/stream", params["url"])
        self.assertEqual(xbmcplugin.CONTENT[-1], "files")
        self.assertEqual(xbmcplugin.ITEMS[-1]["label"], "End of list")


class PlaybackFailureTests(unittest.TestCase):
    """A failed resolve must notify and stop, not advance down the folder."""

    def setUp(self):
        del xbmcplugin.RESOLVED[:]
        del xbmcplugin.ITEMS[:]

    def test_dnb_play_unresolved_notifies_without_wiping_the_queue(self):
        with mock.patch.object(routes.dnbradio, "stream_url", return_value=""), \
                mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.xbmc, "PlayList") as playlist:
            routes.dnb_play(1, {"id": "10", "label": "Show"})
        self.assertTrue(notify.called)
        self.assertFalse(playlist.called)
        self.assertFalse(xbmcplugin.RESOLVED[-1]["ok"])

    def test_dnb_play_scraper_error_fails_safely(self):
        with mock.patch.object(routes.dnbradio, "stream_url", side_effect=RuntimeError("boom")), \
                mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.xbmc, "PlayList") as playlist:
            routes.dnb_play(1, {"id": "10"})
        self.assertTrue(notify.called)
        self.assertFalse(playlist.called)
        self.assertFalse(xbmcplugin.RESOLVED[-1]["ok"])

    def test_play_rejects_non_http_urls(self):
        for url in ("file:///etc/passwd", "special://home/x",
                    "plugin://plugin.video.x/", "javascript:alert(1)"):
            with mock.patch.object(routes.kodi, "notify") as notify:
                routes.play(1, {"url": url})
            self.assertTrue(notify.called, url)
            self.assertFalse(xbmcplugin.RESOLVED[-1]["ok"], url)

    def test_play_accepts_http_urls_with_a_header_suffix(self):
        with mock.patch.object(routes.http.socket, "getaddrinfo", return_value=PUBLIC_INFOS):
            routes.play(1, {"url": "https://example.test/a.mp3|Referer=https://example.test/"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["path"], "https://example.test/a.mp3|Referer=https://example.test/")

    def test_dnb_play_resolves_and_plays(self):
        with mock.patch.object(routes.dnbradio, "stream_url",
                               return_value="https://proxy.dnbradio.com/10.mp3"), \
                mock.patch.object(routes.http.socket, "getaddrinfo", return_value=PUBLIC_INFOS):
            routes.dnb_play(1, {"id": "10", "label": "Show"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["path"], "https://proxy.dnbradio.com/10.mp3")

    def test_play_without_a_stream_fails_safely(self):
        with mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.xbmc, "PlayList") as playlist:
            routes.play(1, {})
        self.assertTrue(notify.called)
        self.assertFalse(playlist.called)
        self.assertFalse(xbmcplugin.RESOLVED[-1]["ok"])

    def test_play_success_does_not_clear_the_playlist(self):
        with mock.patch.object(routes.xbmc, "PlayList") as playlist, \
                mock.patch.object(routes.http.socket, "getaddrinfo", return_value=PUBLIC_INFOS):
            routes.play(1, {"url": "https://example.test/1.mp3"})
        self.assertTrue(xbmcplugin.RESOLVED[-1]["ok"])
        self.assertFalse(playlist.called)


class DispatchFailureTests(unittest.TestCase):
    """A crashing handler must never traceback to Kodi or leave it spinning."""

    def setUp(self):
        del xbmcplugin.ITEMS[:]
        del xbmcplugin.RESOLVED[:]
        del xbmcplugin.CONTENT[:]
        del xbmcplugin.CACHE_FLAGS[:]
        del xbmcplugin.SUCCEEDED[:]

    def test_folder_handler_crash_notifies_and_ends_with_failure(self):
        handler = mock.Mock(side_effect=RuntimeError("boom"))
        with mock.patch.dict(routes.HANDLERS, {"root": handler}), \
                mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.kodi, "log") as log:
            routes.dispatch(["plugin://x/", "7", "?mode=root"])
        self.assertTrue(notify.called)
        self.assertTrue(log.called)
        self.assertEqual(xbmcplugin.SUCCEEDED, [False])
        self.assertIn("files", xbmcplugin.CONTENT)
        self.assertTrue(routes.kodi.directory_ended(7))
        self.assertIsNone(routes.http.remaining())

    def test_playback_handler_crash_returns_a_failed_resolve(self):
        handler = mock.Mock(side_effect=RuntimeError("boom"))
        with mock.patch.dict(routes.HANDLERS, {"play": handler}), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.dispatch(["plugin://x/", "8", "?mode=play"])
        self.assertTrue(notify.called)
        self.assertFalse(xbmcplugin.RESOLVED[-1]["ok"])
        self.assertEqual(xbmcplugin.CONTENT, [])

    def test_runplugin_handler_crash_only_notifies(self):
        handler = mock.Mock(side_effect=RuntimeError("boom"))
        with mock.patch.dict(routes.HANDLERS, {"fav_add": handler}), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.dispatch(["plugin://x/", "9", "?mode=fav_add&kind=pack&target=x&title=X"])
        self.assertTrue(notify.called)
        self.assertEqual(xbmcplugin.CONTENT, [])
        self.assertEqual(xbmcplugin.RESOLVED, [])

    def test_successful_handler_gets_a_budget_and_it_is_cleared(self):
        probe = {}

        def handler(handle, params):
            probe["remaining"] = routes.http.remaining()
            routes.kodi.end_directory(handle, "files")

        with mock.patch.dict(routes.HANDLERS, {"root": handler}):
            routes.dispatch(["plugin://x/", "10", "?mode=root"])
        self.assertIsNotNone(probe["remaining"])
        self.assertGreater(probe["remaining"], 0)
        self.assertIsNone(routes.http.remaining())


class SlowSourceNoticeTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]
        del xbmcplugin.CONTENT[:]
        del xbmcplugin.CACHE_FLAGS[:]

    def _dispatch_with_budget_flag(self, mode):
        def handler(handle, params):
            routes.kodi.end_directory(handle, "files")
        with mock.patch.dict(routes.HANDLERS, {"root": handler, "play": handler}), \
                mock.patch.object(routes.http, "route_budget_exhausted", return_value=True), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.dispatch(["plugin://x/", "11", "?mode=" + mode])
        return [str(call.args[0]) for call in notify.call_args_list]

    def test_folder_route_notifies_when_the_network_budget_ran_out(self):
        messages = self._dispatch_with_budget_flag("root")
        self.assertTrue(any("slow" in message.lower() for message in messages), messages)

    def test_playback_route_does_not_show_the_partial_results_notice(self):
        messages = self._dispatch_with_budget_flag("play")
        self.assertFalse(any("slow" in message.lower() for message in messages), messages)


class RaveRouteTests(unittest.TestCase):
    """Catalogue names with spaces must round-trip through the plugin URL."""

    def setUp(self):
        del xbmcplugin.ITEMS[:]

    @staticmethod
    def _entry():
        return {"name": "World Dance", "query": "collection:ravetapes", "count": 3}

    def test_rave_nights_key_round_trips_with_spaces(self):
        with mock.patch.object(routes, "_rave_catalog", return_value=[self._entry()]), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.rave_nights(1, {})
        urls = [item["url"] for item in xbmcplugin.ITEMS if "mode=rave_list" in item["url"]]
        self.assertTrue(urls)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(urls[0]).query))
        self.assertEqual(params["key"], "World Dance")

    def test_rave_list_resolves_a_name_with_spaces(self):
        docs = [{"identifier": "pack-1", "title": "Pack One"}]
        with mock.patch.object(routes, "_rave_catalog", return_value=[self._entry()]), \
                mock.patch.object(routes.archive, "search", return_value=(docs, 100)), \
                mock.patch.object(routes, "_rows_per_page", return_value=10), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.rave_list(1, {"key": "World Dance"})
        urls = [item["url"] for item in xbmcplugin.ITEMS
                if "mode=rave_list" in item["url"]]
        self.assertEqual(len(urls), 1)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(urls[0]).query))
        self.assertEqual(params["key"], "World Dance")
        self.assertEqual(params["page"], "2")

    def test_rave_list_with_invalid_page_does_not_raise(self):
        with mock.patch.object(routes, "_rave_catalog", return_value=[self._entry()]), \
                mock.patch.object(routes.archive, "search", return_value=([], 0)), \
                mock.patch.object(routes.kodi, "notify"), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.rave_list(1, {"key": "World Dance", "page": "nope"})


class ThirdPartyLabelTests(unittest.TestCase):
    """K9: third-party text must not inject Kodi label markup."""

    def setUp(self):
        del xbmcplugin.ITEMS[:]

    def test_archive_title_markup_is_stripped_from_the_row(self):
        docs = [{"identifier": "pack-1", "title": "[B]Bold[/B] [CR]Pack"}]
        routes._archive_items(1, docs)
        label = xbmcplugin.ITEMS[0]["label"]
        self.assertNotIn("[B]", label)
        self.assertNotIn("[CR]", label)
        self.assertIn("Bold", label)

    def test_latest_title_and_source_markup_is_stripped(self):
        items = [{"kind": "pack", "identifier": "pack-1",
                  "title": "Bad[/COLOR] [CR]Title", "source": "Feed [B]x[/B]",
                  "when": None}]
        with mock.patch.object(routes.latest, "merge", return_value=items), \
                mock.patch.object(routes.latest, "resolve_dnb_streams", return_value={}), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.latest_view(1, {})
        labels = [item["label"] for item in xbmcplugin.ITEMS]
        self.assertFalse(any("[CR]" in label or "[B]" in label for label in labels), labels)
        self.assertTrue(any("Bad" in label and "Title" in label for label in labels), labels)

    def test_feed_episode_title_markup_is_stripped(self):
        entry = {"id": "feed", "name": "Feed", "url": "https://x/feed", "plot": ""}
        episodes = [{"title": "[B]Episode[/B]", "url": "https://x/a.mp3",
                     "published": "[I]Mon[/I]", "description": "", "duration": None}]
        with mock.patch.object(routes.feeds, "feed", return_value=entry), \
                mock.patch.object(routes.feeds, "episodes", return_value=episodes), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.feed(1, {"key": "feed"})
        label = xbmcplugin.ITEMS[0]["label"]
        self.assertNotIn("[B]", label)
        self.assertNotIn("[I]", label)
        self.assertIn("Episode", label)


class PlaybackHostGuardTests(unittest.TestCase):
    """K6 follow-up: private/loopback/metadata playback hosts are refused."""

    def setUp(self):
        del xbmcplugin.RESOLVED[:]
        del xbmcplugin.ITEMS[:]

    @staticmethod
    def _infos(*addresses):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "",
                 (address, 80)) for address in addresses]

    def _play(self, url, resolver):
        with mock.patch.object(routes.http.socket, "getaddrinfo", side_effect=resolver), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.play(1, {"url": url})
        return xbmcplugin.RESOLVED[-1], notify

    def test_literal_private_and_metadata_addresses_are_rejected(self):
        urls = [
            "http://127.0.0.1/x.mp3",
            "http://127.10.0.5/x.mp3",
            "http://10.0.0.1/x.mp3",
            "http://172.16.4.2/x.mp3",
            "http://172.31.255.254/x.mp3",
            "http://192.168.1.10:8097/stream",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/x.mp3",
            "http://[fc00::1]/x.mp3",
            "http://0.0.0.0/x.mp3",
            "http://[::ffff:127.0.0.1]/x.mp3",
        ]
        for url in urls:
            resolved, notify = self._play(url, lambda *args, **kwargs: self._infos("93.184.216.34"))
            self.assertFalse(resolved["ok"], url)
            self.assertTrue(notify.called, url)

    def test_hostname_resolving_private_is_rejected(self):
        resolved, notify = self._play(
            "https://stream.example.test/a.mp3",
            lambda *args, **kwargs: self._infos("192.168.1.20"))
        self.assertFalse(resolved["ok"])
        self.assertTrue(notify.called)

    def test_mixed_public_and_private_answers_are_rejected(self):
        resolved, notify = self._play(
            "https://stream.example.test/a.mp3",
            lambda *args, **kwargs: self._infos("93.184.216.34", "10.0.0.7"))
        self.assertFalse(resolved["ok"])
        self.assertTrue(notify.called)

    def test_unresolvable_host_is_rejected(self):
        def resolver(*args, **kwargs):
            raise socket.gaierror("name not known")

        resolved, notify = self._play("https://does-not-resolve.example/x.mp3", resolver)
        self.assertFalse(resolved["ok"])
        self.assertTrue(notify.called)

    def test_public_host_is_allowed(self):
        resolved, _notify = self._play(
            "https://stream.example.test/a.mp3",
            lambda *args, **kwargs: self._infos("93.184.216.34", "2606:2800:220:1::1"))
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["path"], "https://stream.example.test/a.mp3")

    def test_header_suffix_is_kept_for_public_hosts(self):
        resolved, _notify = self._play(
            "https://stream.example.test/a.mp3|Referer=https://example.test/&User-Agent=Mozilla/5.0",
            lambda *args, **kwargs: self._infos("93.184.216.34"))
        self.assertTrue(resolved["ok"])
        self.assertTrue(resolved["path"].endswith(
            "|Referer=https://example.test/&User-Agent=Mozilla/5.0"))


class DescriptionBoundTests(unittest.TestCase):
    """A4: hostile descriptions must be stripped in linear time."""

    def test_hostile_description_is_capped_and_fast(self):
        started = time.monotonic()
        text = routes._clean_description("<a" * 131072)
        elapsed = time.monotonic() - started
        self.assertLessEqual(len(text), 600)
        self.assertLess(elapsed, 0.5, elapsed)


class ArtUrlGuardTests(unittest.TestCase):
    """A11: third-party art URLs get the same public-host guard as streams."""

    def setUp(self):
        del xbmcplugin.RESOLVED[:]
        del xbmcplugin.ITEMS[:]

    def test_station_loopback_favicon_is_dropped(self):
        station = {"name": "Station", "url": "https://stream.example.test/a",
                   "favicon": "http://127.0.0.1/icon.png"}
        with mock.patch.object(routes.radio, "display", return_value=("Station", "")), \
                mock.patch.object(routes.radio, "stream_url",
                                  return_value="https://stream.example.test/a"), \
                mock.patch.object(routes.http.socket, "getaddrinfo", return_value=PUBLIC_INFOS):
            routes._station_items(1, [station], "Live")
        self.assertEqual(xbmcplugin.ITEMS[0]["art"].get("thumb"), routes.kodi.ICON)

    def test_play_drops_local_file_thumb_and_keeps_public_stream(self):
        with mock.patch.object(routes.http.socket, "getaddrinfo", return_value=PUBLIC_INFOS):
            routes.play(1, {"url": "https://stream.example.test/a.mp3",
                            "thumb": "file:///etc/passwd"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["art"]["thumb"], routes.kodi.ICON)


if __name__ == "__main__":
    unittest.main()
