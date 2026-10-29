# -*- coding: utf-8 -*-
"""Offline tests for route helpers (no plugin directory, no network)."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import routes  # noqa: E402


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

    def _menu_calls(self):
        return [(item["label"], item["url"]) for item in xbmcplugin.ITEMS]

    def test_archive_items_get_play_all_shuffle_and_favourite(self):
        docs = [{"identifier": "pack-1", "title": "Pack One"}]
        routes._archive_items(1, docs)
        context = [label for label, _command in xbmcplugin.ITEMS[0]["context"]]
        self.assertEqual(context, ["Play all", "Shuffle pack", "Add to favourites"])

    def test_archive_item_tracks_offer_play_from_here_and_favourite(self):
        tracks = [{"title": "One", "url": "https://archive.org/download/p/1.mp3", "duration": 61}]
        with mock.patch.object(routes.archive, "audio_files", return_value=tracks):
            routes.archive_item(1, {"id": "pack-1"})
        item = xbmcplugin.ITEMS[0]
        context = [label for label, _command in item["context"]]
        self.assertEqual(context, ["Play all from here", "Add to favourites"])
        self.assertIn("start=0", item["context"][0][1])
        self.assertEqual(item["info"]["music"]["duration"], 61)

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
                mock.patch.object(routes.feeds, "episodes", side_effect=[episodes, []]) as fetch, \
                mock.patch.object(routes, "_episode_limit", return_value=2), \
                mock.patch.object(routes.kodi, "setting_bool", return_value=True), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.media_menu(1, {})
        self.assertEqual(fetch.call_args_list[0][1].get("limit"), 2)
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
        self.assertEqual(len(urls), 5)

    def test_fav_add_reports_already_saved_and_refreshes(self):
        with mock.patch.object(routes.favourites, "has", return_value=True), \
                mock.patch.object(routes.favourites, "add", return_value=True), \
                mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.kodi, "refresh") as refresh, \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.fav_add(1, {"kind": "pack", "target": "x", "title": "X"})
        self.assertEqual(notify.call_args[0][0], "Already in favourites")
        self.assertTrue(refresh.called)

if __name__ == "__main__":
    unittest.main()
