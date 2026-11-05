# -*- coding: utf-8 -*-
"""RaveTapePacks event/DJ/MC/year navigation and post pages (offline).

The live homepage is replayed from the 2024 source fixture; category and post
pages are real Wayback excerpts.  No test here reaches ravetapepacks.com.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import cache, legacy, routes  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")


def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return handle.read()


class _CacheIsolation(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="raveplayer-rtp-nav-")
        self.old = os.environ.get(cache.CACHE_DIR_ENV)
        os.environ[cache.CACHE_DIR_ENV] = self.directory

    def tearDown(self):
        if self.old is None:
            os.environ.pop(cache.CACHE_DIR_ENV, None)
        else:
            os.environ[cache.CACHE_DIR_ENV] = self.old
        shutil.rmtree(self.directory, ignore_errors=True)


class CategoryParseTests(_CacheIsolation):
    def test_homepage_grouping_counts_and_boundaries(self):
        categories = legacy.parse_categories(_fixture("ravetapepacks-nav.html"))

        self.assertEqual(len(categories["events"]), 50)
        self.assertEqual(len(categories["djs"]), 209)
        self.assertEqual(len(categories["mcs"]), 90)
        self.assertEqual(len(categories["years"]), 13)
        self.assertEqual(categories["events"][0]["name"], "Accelerated Culture")
        self.assertEqual(categories["djs"][0]["name"], "Adam F")
        self.assertEqual(categories["mcs"][0]["name"], "5ive-O")
        self.assertEqual(categories["mcs"][-1]["name"], "Yankee")
        self.assertEqual(categories["years"][0], {"id": "56", "name": "1992"})
        self.assertEqual(categories["years"][-1], {"id": "332", "name": "2004"})

    def test_one_id_used_by_an_event_and_an_mc_is_kept_in_both(self):
        categories = legacy.parse_categories(_fixture("ravetapepacks-nav.html"))

        # The site reuses cat=33 ("Vision") in both menus; a global de-dupe
        # would drop the MC and turn the published 90 into 89.
        self.assertIn({"id": "33", "name": "Vision"}, categories["events"])
        self.assertIn({"id": "33", "name": "Vision"}, categories["mcs"])
        for kind in legacy.CATEGORY_KINDS:
            ids = [entry["id"] for entry in categories[kind]]
            self.assertEqual(len(ids), len(set(ids)), kind)

    def test_full_homepage_ignores_genre_and_other_categories(self):
        categories = legacy.parse_categories(_fixture("bench/rtp-home.html"))
        included = set()
        for kind in legacy.CATEGORY_KINDS:
            included.update(entry["id"] for entry in categories[kind])

        self.assertEqual(
            {kind: len(categories[kind]) for kind in legacy.CATEGORY_KINDS},
            {"events": 50, "djs": 209, "mcs": 90, "years": 13})
        # "The Edge" (13) and the sidebar-only rows are after the year block.
        self.assertNotIn("13", included)

    def test_falls_back_to_the_heading_nesting_without_markers(self):
        page = (
            '<li><a href="#">PACKS BY EVENT</a><ul>'
            '<li><a href="?cat=10">Amazon</a></li></ul></li>'
            '<li><a href="#">PACKS BY DJ</a><ul>'
            '<li><a href="?cat=106">Brockie</a></li></ul></li>'
            '<li><a href="#">PACKS BY MC</a><ul>'
            '<li><a href="?cat=203">Bassman</a></li></ul></li>'
            '<li><a href="#">PACKS BY YEAR</a><ul>'
            '<li><a href="?cat=56">1992</a></li></ul></li>'
        )
        categories = legacy.parse_categories(page)
        self.assertEqual([item["name"] for item in categories["events"]], ["Amazon"])
        self.assertEqual([item["name"] for item in categories["djs"]], ["Brockie"])
        self.assertEqual([item["name"] for item in categories["mcs"]], ["Bassman"])
        self.assertEqual([item["name"] for item in categories["years"]], ["1992"])

    def test_categories_fetch_the_homepage_with_browser_headers(self):
        page = _fixture("ravetapepacks-nav.html")
        seen = []

        def fake_fetch(url, timeout=None, headers=None, ttl=0):
            seen.append((url, dict(headers or {}), ttl))
            return page

        with mock.patch.object(legacy.http, "fetch", side_effect=fake_fetch):
            first = legacy.categories()
            second = legacy.categories()

        self.assertEqual(len(seen), 2)  # one body read per call, one parse
        self.assertEqual(seen[0][0], legacy.BASE)
        self.assertEqual(seen[0][1].get("User-Agent"), legacy.BROWSER_UA)
        self.assertEqual(first, second)
        self.assertEqual(len(first["djs"]), 209)


class CategoryPageTests(_CacheIsolation):
    def _two_page_fetch(self):
        pages = {
            legacy.BASE + "?cat=5": _fixture("ravetapepacks-category-paged.html"),
            legacy.BASE + "?cat=5&paged=2": _fixture(
                "ravetapepacks-category-paged-2.html"),
        }
        calls = []

        def fake_fetch(url, timeout=None, headers=None, ttl=0):
            calls.append(url)
            return pages.get(url)

        return fake_fetch, calls

    def test_category_follows_older_posts_and_returns_every_pack(self):
        fake_fetch, calls = self._two_page_fetch()
        with mock.patch.object(legacy.http, "fetch", side_effect=fake_fetch):
            posts = legacy.category("5")

        self.assertEqual(calls, [legacy.BASE + "?cat=5",
                                 legacy.BASE + "?cat=5&paged=2"])
        self.assertEqual(len(posts), 10)
        self.assertEqual(posts[0], {"id": "899", "name": "Dreamscape 7"})
        self.assertEqual(posts[7], {"id": "206", "name": "Dreamscape 4"})
        self.assertEqual(posts[-1], {"id": "37", "name": "Dreamscape 2"})

    def test_category_does_not_walk_backwards_from_the_last_page(self):
        page = _fixture("ravetapepacks-category-paged-2.html")
        calls = []

        def fake_fetch(url, timeout=None, headers=None, ttl=0):
            calls.append(url)
            return page

        with mock.patch.object(legacy.http, "fetch", side_effect=fake_fetch):
            posts = legacy.category("5")

        self.assertEqual(len(posts), 2)
        self.assertEqual(len(calls), 1)  # the "Newer posts" link is ignored

    def test_category_rejects_bad_ids_without_fetching(self):
        calls = []
        with mock.patch.object(legacy.http, "fetch",
                               side_effect=lambda *a, **k: calls.append(a) or ""):
            self.assertEqual(legacy.category("../../etc/passwd"), [])
            self.assertEqual(legacy.category(""), [])
            self.assertEqual(legacy.category("x5"), [])
        self.assertEqual(calls, [])

    def test_category_pagination_is_bounded(self):
        calls = []

        def fake_fetch(url, timeout=None, headers=None, ttl=0):
            calls.append(url)
            page = int(url.rsplit("paged=", 1)[-1]) if "paged=" in url else 1
            return ('<a href="?p=%d" rel="bookmark">Pack %d</a>'
                    '<div class="nav-previous"><a href="?cat=5&amp;paged=%d">'
                    'Older posts</a></div>' % (page, page, page + 1))

        with mock.patch.object(legacy.http, "fetch", side_effect=fake_fetch), \
                mock.patch.object(legacy, "MAX_CATEGORY_PAGES", 3):
            posts = legacy.category("5")

        self.assertEqual(len(calls), 3)
        self.assertEqual([entry["id"] for entry in posts], ["1", "2", "3"])

    def test_category_reuses_the_parse_for_the_same_pages(self):
        fake_fetch, _calls = self._two_page_fetch()
        parses = []
        original = legacy._posts_from_html

        def counting(page):
            parses.append(page)
            return original(page)

        with mock.patch.object(legacy.http, "fetch", side_effect=fake_fetch), \
                mock.patch.object(legacy, "_posts_from_html", side_effect=counting):
            first = legacy.category("5")
            second = legacy.category("5")

        self.assertEqual(first, second)
        self.assertEqual(len(parses), 2)  # one parse per distinct page body


class PostPageTests(_CacheIsolation):
    def test_post_parses_the_pack_mp3s_in_document_order(self):
        page = _fixture("ravetapepacks-post.html")
        seen = []

        def fake_fetch(url, timeout=None, headers=None, ttl=0):
            seen.append((url, dict(headers or {}), ttl))
            return page

        with mock.patch.object(legacy.http, "fetch", side_effect=fake_fetch):
            entry = legacy.post("899")

        self.assertEqual(seen[0][0], legacy.BASE + "?p=899")
        self.assertEqual(seen[0][1].get("User-Agent"), legacy.BROWSER_UA)
        self.assertEqual(seen[0][2], legacy.POST_TTL)
        self.assertEqual(entry["key"], "899")
        self.assertEqual(entry["name"], "Dreamscape 7")
        self.assertEqual(len(entry["tracks"]), 15)
        self.assertEqual(entry["tracks"][0], {
            "name": "Charlie Hall",
            "url": "https://www.ravetapepacks.com/music/Dreamscape7/Charlie_Hall.mp3",
        })
        self.assertEqual(entry["tracks"][-1]["name"], "Vibes")

    def test_post_rejects_bad_ids_without_fetching(self):
        calls = []
        with mock.patch.object(legacy.http, "fetch",
                               side_effect=lambda *a, **k: calls.append(a) or ""):
            self.assertIsNone(legacy.post("../899"))
            self.assertIsNone(legacy.post(""))
            self.assertIsNone(legacy.post("abc"))
        self.assertEqual(calls, [])

    def test_post_returns_none_when_the_page_cannot_be_fetched(self):
        with mock.patch.object(legacy.http, "fetch", return_value=None):
            self.assertIsNone(legacy.post("899"))


class LegacyNavigationRouteTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]
        del xbmcplugin.CONTENT[:]

    def _urls(self):
        return [item["url"] for item in xbmcplugin.ITEMS]

    def test_index_lists_categories_for_each_kind(self):
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
            self.assertEqual([item["label"] for item in xbmcplugin.ITEMS],
                             [categories[routes.RTP_INDEX_KINDS[kind]][0]["name"],
                              "Back"])
            params = routes.params_from_argv(
                ["plugin://plugin.audio.raveplayer/", "1",
                 xbmcplugin.ITEMS[0]["url"].split("?", 1)[1]])
            self.assertEqual(params["mode"], "legacy_category")
            self.assertEqual(params["kind"], kind)
            self.assertEqual(params["cat"],
                             categories[routes.RTP_INDEX_KINDS[kind]][0]["id"])

    def test_index_rejects_an_unknown_kind(self):
        with mock.patch.object(routes.legacy, "categories") as categories, \
                mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.legacy_index(1, {"kind": "genre"})
        self.assertFalse(categories.called)
        self.assertTrue(notify.called)

    def test_category_lists_packs_with_post_links(self):
        posts = [{"id": "899", "name": "Dreamscape 7"},
                 {"id": "879", "name": "Dreamscape 6"}]
        with mock.patch.object(routes.legacy, "category_page",
                               return_value=(posts, "")):
            routes.legacy_category(1, {"kind": "dj", "cat": "106", "label": "Brockie"})
        self.assertEqual([item["label"] for item in xbmcplugin.ITEMS],
                         ["Dreamscape 7", "Dreamscape 6", "Back"])
        params = routes.params_from_argv(
            ["plugin://plugin.audio.raveplayer/", "1",
             xbmcplugin.ITEMS[0]["url"].split("?", 1)[1]])
        self.assertEqual(params["mode"], "legacy_post")
        self.assertEqual(params["post"], "899")
        self.assertEqual(params["kind"], "dj")
        self.assertEqual(params["cat"], "106")
        back = routes.params_from_argv(
            ["plugin://plugin.audio.raveplayer/", "1",
             xbmcplugin.ITEMS[-1]["url"].split("?", 1)[1]])
        self.assertEqual(back["mode"], "legacy_index")
        self.assertEqual(back["kind"], "dj")

    def test_category_rejects_bad_ids_without_fetching(self):
        with mock.patch.object(routes.legacy, "category_page") as category, \
                mock.patch.object(routes.kodi, "end_directory") as end:
            routes.legacy_category(1, {"kind": "nope", "cat": "5"})
            routes.legacy_category(1, {"kind": "dj", "cat": "../../x"})
        self.assertFalse(category.called)
        self.assertEqual(end.call_count, 2)

    def test_post_lists_tracks_with_play_and_download_context(self):
        entry = {"key": "899", "name": "Dreamscape 7", "tracks": [
            {"name": "Charlie Hall",
             "url": "https://www.ravetapepacks.com/music/Dreamscape7/Charlie_Hall.mp3"},
        ]}
        with mock.patch.object(routes.legacy, "post", return_value=entry):
            routes.legacy_post(1, {"post": "899"})

        item = xbmcplugin.ITEMS[0]
        self.assertEqual(item["label"], "Charlie Hall")
        params = routes.params_from_argv(
            ["plugin://plugin.audio.raveplayer/", "1", item["url"].split("?", 1)[1]])
        self.assertEqual(params["mode"], "play")
        self.assertTrue(params["url"].endswith(routes.legacy.REFERER_SUFFIX))
        self.assertIn("Add to favourites", [label for label, _ in item["context"]])
        self.assertIn("Download", [label for label, _ in item["context"]])

    def test_post_without_an_id_does_not_fetch(self):
        with mock.patch.object(routes.legacy, "post") as post, \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.legacy_post(1, {})
        self.assertFalse(post.called)

    def test_post_unknown_reports_instead_of_a_silent_empty_folder(self):
        with mock.patch.object(routes.legacy, "post", return_value=None), \
                mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.legacy_post(1, {"post": "404"})
        self.assertTrue(notify.called)


if __name__ == "__main__":
    unittest.main()


class NewPaginationTests(_CacheIsolation):
    def test_all_packs_reads_the_paginated_blog_archive(self):
        page = _fixture("ravetapepacks-all-packs.html")
        with mock.patch.object(legacy.http, "fetch", return_value=page):
            posts, nxt = legacy.all_packs(1)

        self.assertEqual([post["id"] for post in posts],
                         ["2687", "2669", "2666"])
        self.assertEqual(posts[0]["name"], "The Best Of British – The Jubilee Jam")
        self.assertEqual(nxt, legacy.BASE + "?cat=0&paged=2")

    def test_category_page_returns_one_page_and_its_next_link(self):
        pages = {
            legacy.BASE + "?cat=5": _fixture("ravetapepacks-category-paged.html"),
            legacy.BASE + "?cat=5&paged=2": _fixture(
                "ravetapepacks-category-paged-2.html"),
        }

        def fake_fetch(url, timeout=None, headers=None, ttl=0):
            return pages.get(url)

        with mock.patch.object(legacy.http, "fetch", side_effect=fake_fetch):
            first, nxt = legacy.category_page("5", 1)
            second, last = legacy.category_page("5", 2)

        self.assertEqual(len(first), 8)
        self.assertTrue(nxt.endswith("?cat=5&paged=2"))
        self.assertEqual(len(second), 2)
        self.assertEqual(last, "")

    def test_show_page_uses_the_stream_field_once_per_side(self):
        page = _fixture("jungletapes-show.html")
        with mock.patch.object(legacy.http, "fetch", return_value=page):
            tracks = legacy.jungle_tracks(
                "assignment-earth_chry_1055_2000-10-23-000000")

        self.assertEqual(len(tracks), 2)
        self.assertTrue(all("jungle_tapes_uploaded_audio_files" in track["url"]
                            for track in tracks))
        self.assertNotIn("Tapes/2000.10.23", " ".join(t["url"] for t in tracks))

    def test_jt_show_list_is_paginated(self):
        shows = [{"key": "show-%03d" % index, "name": "Show %03d" % index}
                 for index in range(120)]
        with mock.patch.object(routes.legacy, "jungle_shows", return_value=shows), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.legacy_jt(1, {})
        urls = [item["url"] for item in xbmcplugin.ITEMS]
        self.assertEqual(len([url for url in urls if "mode=legacy_jt_show" in url]), 50)
        self.assertTrue(any("mode=legacy_jt&page=2" in url for url in urls))

    def test_category_route_offers_the_next_page(self):
        posts = [{"id": "899", "name": "Dreamscape 7"}]
        with mock.patch.object(routes.legacy, "category_page",
                               return_value=(posts, "more")), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.legacy_category(1, {"kind": "dj", "cat": "106",
                                       "label": "Brockie"})
        urls = [item["url"] for item in xbmcplugin.ITEMS]
        self.assertTrue(any("mode=legacy_category" in url and "page=2" in url
                            for url in urls))

    def test_search_widens_with_a_title_and_scene_scope(self):
        calls = []

        def fake_search(query, page=1, rows=50, sort="downloads desc"):
            calls.append(query)
            if query.startswith("title:(dreamscape)"):
                return [{"identifier": "wide", "title": "Dreamscape 19"}], 20
            return [{"identifier": "one", "title": "Dreamscape 3"}], 2

        with mock.patch.object(routes.archive, "search", side_effect=fake_search), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.search(1, {"q": "dreamscape"})

        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].startswith("dreamscape AND collection:ravetapes"))
        self.assertTrue(calls[1].startswith("title:(dreamscape) AND mediatype:audio"))
        self.assertIn("subject:(rave OR jungle OR hardcore", calls[1])
