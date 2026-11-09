# -*- coding: utf-8 -*-
"""Offline tests for the library screens (Search / Favourites / Downloads / About).

No Kodi device, renderer or network: the protocol is driven through a fake
backend, and the plugin adapter is driven through a fake module namespace.
"""

import ast
import os
import random
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCREEN = os.path.join(ROOT, "script.raveplayer.ui")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)
sys.path.insert(0, SCREEN)

from raveui import pluginbridge  # noqa: E402
from raveui.screens import library as library_mod  # noqa: E402
from raveui.screens.library import (  # noqa: E402
    ACTION_DOWNLOAD,
    ACTION_FAVOURITE,
    ACTION_OPEN,
    ACTION_PLAY,
    ACTION_PLAY_ALL,
    ACTION_REMOVE,
    ACTION_RETRY,
    ACTION_SHUFFLE,
    AboutInfo,
    ActionResult,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SCOPE,
    KIND_ACTION,
    KIND_ROOM,
    KIND_TRACK,
    LibraryScreens,
    Link,
    PAGE_SIZES,
    PluginBackend,
    PlayItem,
    PROJECT_URL,
    ROUTE_ABOUT,
    ROUTE_DOWNLOADS,
    ROUTE_FAVOURITES,
    ROUTE_SEARCH,
    Row,
    Screen,
    STATE_EMPTY,
    STATE_ERROR,
    STATE_LOADING,
    STATE_READY,
    _fact,
    _size_fact,
    normalise_page_size,
)


# --------------------------------------------------------------------- fakes
class FakePlayback(object):
    def __init__(self, text="Now playing"):
        self.calls = []
        self.text = text
        self.error = None

    def play(self, item):
        if self.error is not None:
            raise self.error
        self.calls.append(item)
        return types.SimpleNamespace(text=self.text)


class QueuePlayback(FakePlayback):
    def __init__(self):
        FakePlayback.__init__(self)
        self.queues = []
        self.error_all = None

    def play_all(self, items, shuffle=False):
        if self.error_all is not None:
            raise self.error_all
        self.queues.append((list(items), shuffle))
        return types.SimpleNamespace(text="Queued %d" % len(items))


class FakeBackend(object):
    def __init__(self):
        self.scope_value = "collection:ravetapes AND mediatype:audio"
        self.page_size_value = DEFAULT_PAGE_SIZE
        self.docs = []
        self.search_total_value = None
        self.search_error = None
        self.searches = []
        self.favourite_rows = []
        self.favourites_error = None
        self.favourite_store = []
        self.has_favourite = False
        self.favourite_add_result = True
        self.favourite_remove_result = True
        self.favourite_error = None
        self.removed_favourites = []
        self.download_rows = []
        self.downloads_error = None
        self.plan_result = {"allowed": True, "size": 1000,
                            "path": "/dl/x.mp3", "key": "new-key"}
        self.plan_error = None
        self.plan_calls = []
        self.download_calls = []
        self.download_impl = None
        self.deleted_downloads = []
        self.download_delete_result = True
        self.download_error = None
        self.playable_blocked = set()
        self.playable_calls = []
        self.playable_error = None
        self.platform_map = {}
        self.art_prefix = "/art/"
        self.thumb_prefix = "https://archive.org/services/img/"
        self.about_value = AboutInfo(
            name="Rave Player",
            version="3.9.51",
            screen_version="3.9.50",
            kodi_version="21.0",
            links=(Link("Project page", PROJECT_URL, "github"),),
            sources=(Link("Internet Archive", "https://archive.org",
                          "archive.org"),),
        )
        self.about_error = None

    # -------------------------------------------------------------- reads
    def scope(self):
        if self.scope_value is None:
            raise RuntimeError("no scope")
        return self.scope_value

    def page_size(self):
        return self.page_size_value

    def search(self, query, page, rows):
        self.searches.append((query, page, rows))
        if self.search_error is not None:
            raise self.search_error
        total = (len(self.docs) if self.search_total_value is None
                 else self.search_total_value)
        start = (page - 1) * rows
        return list(self.docs[start:start + rows]), total

    def archive_thumb(self, identifier):
        if identifier.startswith("broken"):
            return ""
        return self.thumb_prefix + identifier

    def art(self, name):
        if not self.art_prefix:
            return ""
        return self.art_prefix + name

    def favourites(self):
        if self.favourites_error is not None:
            raise self.favourites_error
        return list(self.favourite_rows)

    def favourite_key(self, entry):
        return "%s:%s" % (entry.get("kind"), entry.get("target"))

    def favourite_has(self, entry):
        return self.has_favourite

    def favourite_add(self, entry):
        if self.favourite_error is not None:
            raise self.favourite_error
        if not self.favourite_add_result:
            return False
        self.favourite_store.append(dict(entry))
        return True

    def favourite_remove(self, key):
        if self.favourite_error is not None:
            raise self.favourite_error
        self.removed_favourites.append(key)
        return self.favourite_remove_result

    def downloads(self):
        if self.downloads_error is not None:
            raise self.downloads_error
        return list(self.download_rows)

    def download_plan(self, url, title, source):
        self.plan_calls.append((url, title, source))
        if self.plan_error is not None:
            raise self.plan_error
        return dict(self.plan_result)

    def download(self, plan, progress=None, cancelled=None):
        self.download_calls.append((dict(plan), progress, cancelled))
        if self.download_error is not None:
            raise self.download_error
        if self.download_impl is not None:
            return self.download_impl(plan, progress, cancelled)
        if progress is not None:
            progress(plan.get("size", 0), plan.get("size", 0))
        return {"ok": True, "reason": ""}

    def download_delete(self, key):
        self.deleted_downloads.append(key)
        return self.download_delete_result

    def playable_url(self, url):
        self.playable_calls.append(url)
        if self.playable_error is not None:
            raise self.playable_error
        if url in self.playable_blocked:
            return ""
        if not url.startswith(("http://", "https://")):
            return ""
        return url

    def platform_kind(self, url):
        return self.platform_map.get(url, "")

    def about(self):
        if self.about_error is not None:
            raise self.about_error
        return self.about_value


def make_docs(count, start=0):
    return [
        {"identifier": "pack-%d" % index,
         "title": "Pack %d" % index,
         "year": str(1990 + index % 10)}
        for index in range(start, start + count)
    ]


def make_track(url="https://stream.test/1.mp3", title="Tune", **extra):
    payload = {"action": ACTION_PLAY, "url": url, "title": title,
               "album": "Pack", "source": "Archive.org",
               "favourite_kind": "stream"}
    payload.update(extra)
    return Row(label=title, kind=KIND_TRACK, fact="track", payload=payload)


class FakeQueue(object):
    """Minimal DownloadQueue double for the Downloads room."""

    def __init__(self):
        self.rows_value = []
        self.cancelled = []
        self.dismissed = []

    def rows(self):
        return [dict(row) for row in self.rows_value]

    def cancel(self, key):
        self.cancelled.append(key)
        return True

    def dismiss(self, key):
        self.dismissed.append(key)
        return True


class LibraryTestCase(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.screens = LibraryScreens(self.backend)


# ------------------------------------------------------------------ page size
class PageSizeTests(LibraryTestCase):
    def test_values_snap_to_the_allowed_set(self):
        self.assertEqual(normalise_page_size(0), DEFAULT_PAGE_SIZE)
        self.assertEqual(normalise_page_size(None), DEFAULT_PAGE_SIZE)
        self.assertEqual(normalise_page_size(10), 25)
        self.assertEqual(normalise_page_size(30), 25)
        self.assertEqual(normalise_page_size(40), 50)
        self.assertEqual(normalise_page_size(60), 50)
        self.assertEqual(normalise_page_size(90), 100)
        self.assertEqual(normalise_page_size(99), 100)
        self.assertEqual(normalise_page_size(400), 100)
        for size in PAGE_SIZES:
            self.assertEqual(normalise_page_size(size), size)

    def test_search_uses_each_allowed_backend_size(self):
        for size in PAGE_SIZES:
            backend = FakeBackend()
            backend.page_size_value = size
            backend.docs = make_docs(size + 5)
            screens = LibraryScreens(backend)
            screen = screens.search("dreamscape", 1)
            self.assertEqual(screen.page_size, size)
            self.assertEqual(len(screen.rows), size)
            self.assertEqual(backend.searches[0][2], size)

    def test_invalid_backend_setting_falls_back_to_100(self):
        self.backend.page_size_value = 999
        self.backend.docs = make_docs(5)
        screen = self.screens.search("x", 1)
        self.assertEqual(screen.page_size, 100)

    def test_constructor_override_wins(self):
        self.backend.page_size_value = 100
        self.backend.docs = make_docs(60)
        screens = LibraryScreens(self.backend, page_size=25)
        screen = screens.search("x", 1)
        self.assertEqual(screen.page_size, 25)
        self.assertEqual(len(screen.rows), 25)

    def test_broken_backend_setting_never_blocks_a_list(self):
        self.backend.page_size = lambda: (_ for _ in ()).throw(RuntimeError("x"))
        self.backend.docs = make_docs(5)
        self.assertEqual(self.screens.search("x", 1).page_size,
                         DEFAULT_PAGE_SIZE)

    def test_loading_and_back_do_not_force_a_plugin_load(self):
        self.backend.page_size_value = 25
        self.backend.docs = make_docs(1)
        results = self.screens.search("x", 1)
        self.backend.page_size = lambda: (_ for _ in ()).throw(RuntimeError("x"))
        loading = self.screens.loading(ROUTE_SEARCH, query="x")
        self.assertEqual(loading.page_size, 25)
        idle = self.screens.back(results)
        self.assertEqual(idle.page_size, 25)


# --------------------------------------------------------------------- search
class SearchTests(LibraryTestCase):
    def test_query_is_scoped_and_rows_are_mapped(self):
        self.backend.docs = make_docs(3)
        screen = self.screens.search("dreamscape", 1)
        self.assertEqual(screen.route, ROUTE_SEARCH)
        self.assertEqual(screen.title, "SEARCH")
        self.assertEqual(screen.code, "RP-33")
        self.assertEqual(screen.state, STATE_READY)
        query, page, rows = self.backend.searches[0]
        self.assertEqual(
            query, "dreamscape AND collection:ravetapes AND mediatype:audio")
        self.assertEqual((page, rows), (1, DEFAULT_PAGE_SIZE))
        row = screen.rows[0]
        self.assertEqual(row.label, "Pack 0")
        self.assertEqual(row.kind, KIND_ROOM)
        self.assertEqual(row.fact, "1990")
        self.assertEqual(row.code, "RP-33")
        self.assertEqual(row.icon, "https://archive.org/services/img/pack-0")
        self.assertEqual(row.fanart, "/art/fanart-search.jpg")
        self.assertEqual(row.payload["mode"], "archive_item")
        self.assertEqual(row.payload["identifier"], "pack-0")
        self.assertEqual(row.payload["favourite_kind"], "pack")
        self.assertEqual(row.payload["source"], "Archive.org")
        self.assertEqual(row.art, row.icon)
        self.assertEqual(row.hero, row.fanart)

    def test_results_are_paged(self):
        self.backend.docs = make_docs(60)
        first = self.screens.search("dreamscape", 1)
        self.assertEqual((first.page, first.pages, first.total), (1, 2, 60))
        self.assertEqual(len(first.rows), 50)
        self.assertEqual(first.page_label, "Page 1 of 2 · 60 packs")
        second = self.screens.search("dreamscape", 2)
        self.assertEqual((second.page, second.pages), (2, 2))
        self.assertEqual(len(second.rows), 10)
        self.assertEqual(second.rows[0].label, "Pack 50")

    def test_out_of_range_page_clamps_to_the_last_page(self):
        self.backend.docs = make_docs(60)
        screen = self.screens.search("dreamscape", 99)
        self.assertEqual((screen.page, screen.pages), (2, 2))
        self.assertEqual(len(screen.rows), 10)
        self.assertEqual([call[1] for call in self.backend.searches], [99, 2])

    def test_blank_query_never_touches_the_backend(self):
        for value in ("", "   ", "\x00\n"):
            screen = self.screens.search(value)
            self.assertEqual(screen.state, STATE_EMPTY)
            self.assertEqual(screen.rows, ())
            self.assertEqual(screen.query, "")
            self.assertIsNone(screen.retry_row)
        self.assertEqual(self.backend.searches, [])

    def test_empty_results_offer_a_retry_row(self):
        self.backend.docs = []
        screen = self.screens.search("rare", 1)
        self.assertEqual(screen.state, STATE_EMPTY)
        self.assertEqual(screen.subtitle, "No matching packs")
        row = screen.retry_row
        self.assertIsNotNone(row)
        self.assertEqual(row.label, "Search again")
        self.assertEqual(row.payload, {"action": ACTION_RETRY,
                                       "route": ROUTE_SEARCH,
                                       "query": "rare", "page": 1})
        again = self.screens.retry(row)
        self.assertEqual(again.state, STATE_EMPTY)
        self.assertEqual(len(self.backend.searches), 2)

    def test_error_state_offers_retry_and_recovers(self):
        self.backend.search_error = RuntimeError("archive down")
        screen = self.screens.search("dreamscape", 1)
        self.assertEqual(screen.state, STATE_ERROR)
        self.assertIn("archive down", screen.error)
        self.assertEqual(screen.retry_row.label, "Retry")
        self.backend.search_error = None
        self.backend.docs = make_docs(2)
        recovered = self.screens.retry(screen)
        self.assertEqual(recovered.state, STATE_READY)
        self.assertEqual(len(recovered.rows), 2)

    def test_docs_without_an_identifier_are_skipped(self):
        self.backend.docs = [{"title": "No id"}, make_docs(1)[0]]
        screen = self.screens.search("x", 1)
        self.assertEqual(len(screen.rows), 1)
        self.assertEqual(screen.rows[0].payload["identifier"], "pack-0")

    def test_control_characters_are_collapsed_in_the_query(self):
        self.backend.docs = make_docs(1)
        self.screens.search("dream\x00scape", 1)
        self.assertTrue(self.backend.searches[0][0].startswith(
            "dream scape AND collection:ravetapes"))

    def test_scope_falls_back_when_the_backend_cannot_supply_one(self):
        self.backend.scope_value = None
        self.backend.docs = make_docs(1)
        self.screens.search("dreamscape", 1)
        self.assertIn(DEFAULT_SCOPE, self.backend.searches[0][0])


# ----------------------------------------------------------------- favourites
def make_favourite_entries():
    return [
        {"kind": "pack", "target": "pack-1", "title": "Dreamscape 19",
         "source": "Archive.org"},
        {"kind": "legacy_pack", "target": "legacy-1", "title": "Fantazia",
         "source": "RaveTapePacks"},
        {"kind": "legacy_jt", "target": "show-1", "title": "Jungle show",
         "source": "JungleTapes"},
        {"kind": "dnb", "target": "dnb-1", "title": "DNB show",
         "source": "DNB Radio"},
        {"kind": "stream", "target": "https://stream.test/1.mp3",
         "title": "Kool FM", "source": "Live radio"},
        {"kind": "stream", "target": "https://www.mixcloud.com/x/",
         "title": "Cloud set", "source": "Mixcloud"},
        {"kind": "stream", "target": "https://dead.test/2.mp3",
         "title": "Gone", "source": "Archive.org"},
    ]


class FavouritesTests(LibraryTestCase):
    def setUp(self):
        LibraryTestCase.setUp(self)
        self.backend.favourite_rows = make_favourite_entries()
        self.backend.platform_map["https://www.mixcloud.com/x/"] = "mixcloud"
        self.backend.playable_blocked.add("https://dead.test/2.mp3")

    def test_rows_carry_the_right_room_and_action_payloads(self):
        screen = self.screens.favourites(1)
        self.assertEqual(screen.route, ROUTE_FAVOURITES)
        self.assertEqual(screen.title, "FAVOURITES")
        self.assertEqual(screen.code, "RP-34")
        self.assertEqual(screen.total, len(self.backend.favourite_rows))
        labels = [row.label for row in screen.rows]
        self.assertEqual(labels, ["Dreamscape 19", "Fantazia", "Jungle show",
                                  "DNB show", "Kool FM", "Cloud set", "Gone"])
        pack = screen.rows[0]
        self.assertEqual(pack.kind, KIND_ROOM)
        self.assertEqual(pack.payload["mode"], "archive_item")
        self.assertEqual(pack.payload["identifier"], "pack-1")
        self.assertEqual(pack.payload["favourite_key"], "pack:pack-1")
        self.assertEqual(screen.rows[1].payload["mode"], "legacy_pack")
        self.assertEqual(screen.rows[2].payload["mode"], "legacy_jt_show")
        self.assertEqual(screen.rows[3].payload["mode"], "dnb_play")
        live = screen.rows[4]
        self.assertEqual(live.kind, KIND_TRACK)
        self.assertEqual(live.payload["action"], ACTION_PLAY)
        self.assertEqual(live.payload["url"], "https://stream.test/1.mp3")
        self.assertTrue(live.payload["live"])
        platform = screen.rows[5]
        self.assertEqual(platform.kind, KIND_ROOM)
        self.assertEqual(platform.payload["room"], "platform")
        self.assertEqual(platform.payload["platform"], "mixcloud")
        stale = screen.rows[6]
        self.assertEqual(stale.kind, KIND_ACTION)
        self.assertEqual(stale.payload["action"], ACTION_REMOVE)
        self.assertEqual(stale.payload["favourite_key"],
                         "stream:https://dead.test/2.mp3")
        self.assertEqual(stale.fact, "stale")
        for row in screen.rows:
            self.assertEqual(row.code, "RP-34")
            self.assertEqual(row.fanart, "/art/fanart-favourites.jpg")
            self.assertNotIn("screen-bed", row.fanart)

    def test_pagination_covers_every_entry_once(self):
        self.backend.favourite_rows = [
            {"kind": "stream", "target": "https://x.test/%d.mp3" % index,
             "title": "Favourite %d" % index, "source": "Archive.org"}
            for index in range(120)
        ]
        first = self.screens.favourites(1)
        second = self.screens.favourites(2)
        third = self.screens.favourites(3)
        self.assertEqual((first.page, first.pages, first.total), (1, 3, 120))
        self.assertEqual((len(first.rows), len(second.rows),
                          len(third.rows)), (50, 50, 20))
        labels = ([row.label for row in first.rows]
                  + [row.label for row in second.rows]
                  + [row.label for row in third.rows])
        self.assertEqual(len(set(labels)), 120)
        self.assertEqual(first.page_label, "Page 1 of 3 · 120 favourites")

    def test_play_a_saved_stream_hands_the_validated_url_to_playback(self):
        playback = FakePlayback()
        screens = LibraryScreens(self.backend, playback=playback)
        screen = screens.favourites(1)
        result = screens.play(screen.rows[4])
        self.assertTrue(result.ok)
        self.assertEqual(len(playback.calls), 1)
        self.assertEqual(playback.calls[0].url, "https://stream.test/1.mp3")
        self.assertTrue(playback.calls[0].live)

    def test_favourite_adds_the_source_entry(self):
        screen = self.screens.favourites(1)
        result = self.screens.favourite(screen.rows[0])
        self.assertTrue(result.ok)
        self.assertEqual(result.action, ACTION_FAVOURITE)
        self.assertEqual(result.refresh, ROUTE_FAVOURITES)
        self.assertEqual(result.payload["kind"], "pack")
        self.assertEqual(result.payload["target"], "pack-1")
        self.assertEqual(self.backend.favourite_store[0]["title"],
                         "Dreamscape 19")

    def test_already_saved_is_reported_without_a_duplicate_row(self):
        self.backend.has_favourite = True
        screen = self.screens.favourites(1)
        result = self.screens.favourite(screen.rows[0])
        self.assertTrue(result.ok)
        self.assertEqual(result.message, "Already in favourites")

    def test_favourite_failure_is_a_failed_action(self):
        self.backend.favourite_add_result = False
        screen = self.screens.favourites(1)
        result = self.screens.favourite(screen.rows[0])
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Could not save that favourite.")

    def test_remove_a_stale_favourite(self):
        screen = self.screens.favourites(1)
        result = self.screens.remove(screen.rows[6])
        self.assertTrue(result.ok)
        self.assertEqual(result.action, ACTION_REMOVE)
        self.assertEqual(result.refresh, ROUTE_FAVOURITES)
        self.assertEqual(self.backend.removed_favourites,
                         ["stream:https://dead.test/2.mp3"])

    def test_empty_favourites_offer_refresh(self):
        self.backend.favourite_rows = []
        screen = self.screens.favourites(1)
        self.assertEqual(screen.state, STATE_EMPTY)
        self.assertEqual(screen.subtitle, "No favourites yet")
        self.assertEqual(screen.retry_row.payload["route"], ROUTE_FAVOURITES)
        self.assertEqual(screen.retry_row.label, "Refresh favourites")

    def test_backend_error_becomes_a_retryable_screen(self):
        self.backend.favourites_error = RuntimeError("profile unreadable")
        screen = self.screens.favourites(1)
        self.assertEqual(screen.state, STATE_ERROR)
        self.assertIn("profile unreadable", screen.error)
        self.assertEqual(screen.retry_row.payload["action"], ACTION_RETRY)

    def test_entries_without_a_target_are_skipped(self):
        self.backend.favourite_rows = [
            {"kind": "pack", "target": "", "title": "Broken"},
            {"kind": "pack", "target": "ok", "title": "Fine"},
        ]
        screen = self.screens.favourites(1)
        self.assertEqual([row.label for row in screen.rows], ["Fine"])


# ------------------------------------------------------------------ downloads
def make_download_entries():
    return [
        {"key": "k1", "title": "One", "path": "/downloads/one.mp3",
         "exists": True, "size": 12 * 1024 * 1024, "source": "Archive.org",
         "added": "2026-01-01 10:00:00"},
        {"key": "k2", "title": "Two", "path": "/downloads/two.mp3",
         "exists": False, "size": 0, "source": "Archive.org",
         "added": "2026-01-02 10:00:00"},
    ]


class DownloadsTests(LibraryTestCase):
    def setUp(self):
        LibraryTestCase.setUp(self)
        self.backend.download_rows = make_download_entries()

    def test_downloads_hero_is_the_neutral_bed_not_favourites_art(self):
        # 3.9.54 device QA P2-1: Downloads painted the FAVOURITES hero.
        screen = self.screens.downloads(1)
        expected = "/art/screen-bed-1920x1080.jpg"
        for row in screen.rows:
            self.assertEqual(row.fanart, expected)
            self.assertEqual(row.hero, expected)
            self.assertNotIn("favourites", row.fanart)
        queue = FakeQueue()
        screens = LibraryScreens(self.backend, queue=queue)
        queue.rows_value = [{
            "key": "q1", "title": "Active", "status": "downloading",
            "percent": 10, "source": "Archive.org"}]
        active = screens.downloads(1).rows[0]
        self.assertEqual(active.fanart, expected)

    def test_existing_and_missing_files_map_to_track_and_action_rows(self):
        screen = self.screens.downloads(1)
        self.assertEqual(screen.route, ROUTE_DOWNLOADS)
        self.assertEqual(screen.title, "DOWNLOADS")
        self.assertEqual(screen.code, "RP-35")
        self.assertEqual(screen.total, 2)
        saved, missing = screen.rows
        self.assertEqual(saved.kind, KIND_TRACK)
        self.assertEqual(saved.fact, "12.0 MB")
        self.assertEqual(saved.payload["action"], ACTION_PLAY)
        self.assertEqual(saved.payload["url"], "/downloads/one.mp3")
        self.assertTrue(saved.payload["local"])
        self.assertEqual(saved.payload["download_key"], "k1")
        self.assertEqual(missing.kind, KIND_ACTION)
        self.assertEqual(missing.fact, "missing")
        self.assertEqual(missing.payload["action"], ACTION_REMOVE)
        self.assertEqual(missing.payload["download_key"], "k2")

    def test_local_download_playback_bypasses_the_stream_guard(self):
        playback = FakePlayback()
        screens = LibraryScreens(self.backend, playback=playback)
        screen = screens.downloads(1)
        result = screens.play(screen.rows[0])
        self.assertTrue(result.ok)
        self.assertEqual(playback.calls[0].url, "/downloads/one.mp3")
        self.assertTrue(playback.calls[0].local)
        self.assertEqual(self.backend.playable_calls, [])

    def test_a_downloaded_file_is_not_favourited_as_a_stream(self):
        screen = self.screens.downloads(1)
        result = self.screens.favourite(screen.rows[0])
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "That file is already downloaded.")
        self.assertEqual(self.backend.favourite_store, [])

    def test_remove_a_missing_download(self):
        screen = self.screens.downloads(1)
        result = self.screens.remove(screen.rows[1])
        self.assertTrue(result.ok)
        self.assertEqual(result.refresh, ROUTE_DOWNLOADS)
        self.assertEqual(self.backend.deleted_downloads, ["k2"])

    def test_download_reports_progress_and_refreshes_the_list(self):
        def impl(plan, progress, cancelled):
            progress(500, 1000)
            progress(1000, 1000)
            return {"ok": True, "reason": ""}

        self.backend.download_impl = impl
        calls = []
        row = make_track()
        result = self.screens.download(row, progress=lambda d, t: calls.append((d, t)))
        self.assertTrue(result.ok)
        self.assertEqual(result.action, ACTION_DOWNLOAD)
        self.assertEqual(result.refresh, ROUTE_DOWNLOADS)
        self.assertEqual(result.message, "Downloaded Tune")
        self.assertEqual(calls, [(500, 1000), (1000, 1000)])
        self.assertEqual(result.payload["download_key"], "new-key")
        self.assertEqual(self.backend.plan_calls,
                         [("https://stream.test/1.mp3", "Tune", "Archive.org")])
        progress = self.screens.progress("https://stream.test/1.mp3")
        self.assertFalse(progress["active"])
        self.assertEqual(progress["percent"], 100)
        self.assertEqual(progress["error"], "")

    def test_disallowed_plan_never_starts_a_download(self):
        self.backend.plan_result = {"allowed": False,
                                    "reason": "Not enough free space."}
        result = self.screens.download(make_track())
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Not enough free space.")
        self.assertEqual(self.backend.download_calls, [])

    def test_plan_error_is_reported(self):
        self.backend.plan_error = RuntimeError("probe failed")
        result = self.screens.download(make_track())
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Could not prepare the download.")

    def test_failed_download_keeps_the_reason_in_progress(self):
        self.backend.download_impl = lambda plan, progress, cancelled: {
            "ok": False, "reason": "upstream reset"}
        result = self.screens.download(make_track())
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "upstream reset")
        progress = self.screens.progress("https://stream.test/1.mp3")
        self.assertFalse(progress["active"])
        self.assertEqual(progress["error"], "upstream reset")

    def test_download_exception_is_a_failed_action(self):
        self.backend.download_error = RuntimeError("disk gone")
        result = self.screens.download(make_track())
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Download failed.")
        self.assertFalse(self.screens.progress(
            "https://stream.test/1.mp3")["active"])

    def test_already_downloaded_rows_are_refused(self):
        result = self.screens.download(Row(
            label="Local", kind=KIND_TRACK, payload={"local": True,
                                                     "url": "/x.mp3"}))
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "That track is already downloaded.")

    def test_missing_url_is_refused(self):
        result = self.screens.download(Row(label="No URL", kind=KIND_TRACK))
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "That row has no download URL.")

    def test_a_broken_progress_callback_does_not_break_the_download(self):
        def explode(done, total):
            raise RuntimeError("UI gone")

        result = self.screens.download(make_track(), progress=explode)
        self.assertTrue(result.ok)

    def test_progress_returns_copies(self):
        self.screens.download(make_track())
        item = self.screens.progress("https://stream.test/1.mp3")
        item["percent"] = 1
        self.assertEqual(
            self.screens.progress("https://stream.test/1.mp3")["percent"], 100)
        self.assertEqual(len(self.screens.progress()), 1)

    def test_empty_downloads_offer_refresh(self):
        self.backend.download_rows = []
        screen = self.screens.downloads(1)
        self.assertEqual(screen.state, STATE_EMPTY)
        self.assertEqual(screen.subtitle, "No downloads yet")
        self.assertEqual(screen.retry_row.payload["route"], ROUTE_DOWNLOADS)

    def test_backend_error_becomes_a_retryable_screen(self):
        self.backend.downloads_error = RuntimeError("vfs gone")
        screen = self.screens.downloads(1)
        self.assertEqual(screen.state, STATE_ERROR)
        self.assertIn("vfs gone", screen.error)


# ---------------------------------------------------------------------- about
class AboutTests(LibraryTestCase):
    def test_versions_licence_links_and_sources_are_rows(self):
        screen = self.screens.about()
        self.assertEqual(screen.route, ROUTE_ABOUT)
        self.assertEqual(screen.title, "ABOUT")
        self.assertEqual(screen.code, "RP-36")
        self.assertEqual(screen.state, STATE_READY)
        labels = [row.label for row in screen.rows]
        self.assertEqual(labels, ["Rave Player", "Rave Player", "Kodi",
                                  "Licence", "Classic lists",
                                  "Project page", "Internet Archive"])
        facts = [row.fact for row in screen.rows]
        self.assertEqual(facts, ["3.9.51", "3.9.50", "21.0",
                                 "GPL-3.0-or-later", "fallback", "github",
                                 "archive.org"])
        for row in screen.rows:
            self.assertEqual(row.kind, KIND_ACTION)
            self.assertEqual(row.code, "RP-36")
            self.assertEqual(row.fanart, "/art/fanart-about.jpg")
        for row in screen.rows[:4] + screen.rows[5:]:
            self.assertEqual(row.payload["action"], ACTION_OPEN)
        self.assertEqual(screen.rows[4].payload["action"], "classic")
        self.assertEqual(screen.rows[4].payload["url"],
                         "plugin://plugin.audio.raveplayer/?mode=classic_root")
        self.assertEqual(screen.rows[0].payload["url"], PROJECT_URL)
        self.assertEqual(screen.rows[-1].payload["url"], "https://archive.org")
        self.assertIn("3.9.51", screen.subtitle)

    def test_a_dict_about_payload_is_accepted(self):
        self.backend.about_value = {
            "name": "Rave Player",
            "version": "9.9.9",
            "screen_version": "1.2.3",
            "kodi_version": "22.0",
            "licence": "GPL-3.0-or-later",
            "links": [{"label": "Project page", "url": PROJECT_URL,
                       "fact": "github"}],
            "sources": [],
        }
        screen = self.screens.about()
        self.assertEqual(screen.rows[0].fact, "9.9.9")
        self.assertEqual(screen.rows[1].fact, "1.2.3")
        self.assertEqual(screen.rows[2].fact, "22.0")

    def test_about_error_is_retryable(self):
        self.backend.about_error = RuntimeError("metadata broken")
        screen = self.screens.about()
        self.assertEqual(screen.state, STATE_ERROR)
        self.assertIn("metadata broken", screen.error)
        self.assertEqual(screen.retry_row.label, "Retry")


# -------------------------------------------------------------------- actions
class ActionTests(LibraryTestCase):
    def test_play_refuses_a_url_the_guard_rejects(self):
        playback = FakePlayback()
        screens = LibraryScreens(self.backend, playback=playback)
        result = screens.play(make_track("javascript:alert(1)"))
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "That stream is not playable.")
        self.assertEqual(playback.calls, [])

    def test_play_refuses_an_empty_url(self):
        self.assertFalse(self.screens.play(
            Row(label="Empty", kind=KIND_TRACK, payload={})).ok)

    def test_play_returns_the_playback_text(self):
        playback = FakePlayback(text="Now playing: Tune — Pack")
        screens = LibraryScreens(self.backend, playback=playback)
        result = screens.play(make_track())
        self.assertTrue(result.ok)
        self.assertEqual(result.message, "Now playing: Tune — Pack")
        self.assertIsInstance(result.track, PlayItem)
        self.assertEqual(result.track.pack, "Pack")

    def test_play_handles_a_player_exception(self):
        playback = FakePlayback()
        playback.error = RuntimeError("kodi player busy")
        screens = LibraryScreens(self.backend, playback=playback)
        result = screens.play(make_track())
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Could not start playback.")

    def test_play_without_a_player_returns_an_intent(self):
        result = self.screens.play(make_track())
        self.assertTrue(result.ok)
        self.assertEqual(result.payload["url"], "https://stream.test/1.mp3")
        self.assertEqual(result.track.title, "Tune")

    def test_play_all_collects_playable_tracks_in_order(self):
        screen = Screen(route=ROUTE_FAVOURITES, title="FAVOURITES", rows=(
            make_track("https://stream.test/1.mp3", "One"),
            Row(label="Pack", kind=KIND_ROOM, payload={"room": "pack"}),
            make_track("https://stream.test/2.mp3", "Two"),
            make_track("https://dead.test/3.mp3", "Dead"),
        ))
        self.backend.playable_blocked.add("https://dead.test/3.mp3")
        result = self.screens.play_all(screen)
        self.assertTrue(result.ok)
        self.assertEqual(result.action, ACTION_PLAY_ALL)
        self.assertEqual([track.url for track in result.tracks],
                         ["https://stream.test/1.mp3",
                          "https://stream.test/2.mp3"])
        self.assertEqual([item["title"] for item in result.payload["tracks"]],
                         ["One", "Two"])
        self.assertFalse(result.payload["shuffle"])

    def test_play_all_with_nothing_playable_fails(self):
        screen = Screen(route=ROUTE_FAVOURITES, title="FAVOURITES", rows=(
            Row(label="Pack", kind=KIND_ROOM, payload={"room": "pack"}),
        ))
        result = self.screens.play_all(screen)
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Nothing to play on this page.")

    def test_shuffle_uses_the_injected_random_source(self):
        rows = tuple(make_track("https://stream.test/%d.mp3" % index,
                                "Track %d" % index) for index in range(5))
        screen = Screen(route=ROUTE_DOWNLOADS, title="DOWNLOADS", rows=rows)
        screens = LibraryScreens(self.backend,
                                 random_module=random.Random(7))
        expected = [row.payload["url"] for row in rows]
        random.Random(7).shuffle(expected)
        result = screens.shuffle(screen)
        self.assertTrue(result.ok)
        self.assertEqual(result.action, ACTION_SHUFFLE)
        self.assertTrue(result.payload["shuffle"])
        self.assertEqual([track.url for track in result.tracks], expected)
        self.assertEqual(sorted(track.url for track in result.tracks),
                         sorted(row.payload["url"] for row in rows))

    def test_play_all_uses_a_player_that_can_queue(self):
        playback = QueuePlayback()
        screens = LibraryScreens(self.backend, playback=playback)
        screen = Screen(route=ROUTE_DOWNLOADS, title="DOWNLOADS",
                        rows=(make_track(),))
        result = screens.shuffle(screen)
        self.assertTrue(result.ok)
        self.assertEqual(len(playback.queues), 1)
        self.assertTrue(playback.queues[0][1])
        self.assertEqual(result.message, "Queued 1")

    def test_play_all_player_failure_is_reported(self):
        playback = QueuePlayback()
        playback.error_all = RuntimeError("no playlist")
        screens = LibraryScreens(self.backend, playback=playback)
        result = screens.play_all(Screen(route=ROUTE_DOWNLOADS,
                                         title="DOWNLOADS",
                                         rows=(make_track(),)))
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Could not start playback.")

    def test_retry_replays_each_room(self):
        self.backend.docs = make_docs(1)
        search_screen = self.screens.search("x", 1)
        self.assertEqual(self.screens.retry(search_screen).route, ROUTE_SEARCH)
        self.backend.favourite_rows = make_favourite_entries()
        favourites_screen = self.screens.favourites(1)
        self.assertEqual(self.screens.retry(favourites_screen).route,
                         ROUTE_FAVOURITES)
        self.backend.download_rows = make_download_entries()
        downloads_screen = self.screens.downloads(1)
        self.assertEqual(self.screens.retry(downloads_screen).route,
                         ROUTE_DOWNLOADS)
        self.assertEqual(self.screens.retry(ROUTE_ABOUT).route, ROUTE_ABOUT)

    def test_retry_with_an_unknown_route_is_an_error_screen(self):
        screen = self.screens.retry("made-up")
        self.assertEqual(screen.state, STATE_ERROR)
        self.assertEqual(screen.error, "Nothing to retry")

    def test_back_from_search_results_returns_to_idle_search(self):
        self.backend.docs = make_docs(2)
        results = self.screens.search("dreamscape", 1)
        idle = self.screens.back(results)
        self.assertEqual(idle.route, ROUTE_SEARCH)
        self.assertEqual(idle.query, "")
        self.assertEqual(idle.rows, ())
        self.assertEqual(idle.state, STATE_EMPTY)
        self.assertEqual(len(self.backend.searches), 1)  # no extra request
        self.assertIsNone(self.screens.back(idle))

    def test_back_from_every_other_room_leaves_the_library(self):
        self.backend.favourite_rows = make_favourite_entries()
        self.backend.download_rows = make_download_entries()
        for screen in (self.screens.favourites(1), self.screens.downloads(1),
                       self.screens.about()):
            self.assertIsNone(self.screens.back(screen))
        self.assertIsNone(self.screens.back(None))

    def test_loading_screen_is_plain_and_room_aware(self):
        screen = self.screens.loading(ROUTE_SEARCH, query="dreamscape", page=2)
        self.assertEqual(screen.state, STATE_LOADING)
        self.assertEqual(screen.title, "SEARCH")
        self.assertEqual(screen.subtitle, "Loading…")
        self.assertEqual(screen.query, "dreamscape")
        self.assertEqual(screen.page, 2)
        self.assertEqual(screen.rows, ())


# --------------------------------------------------------------- protocol API
class ProtocolTests(unittest.TestCase):
    def test_row_aliases_match_the_window_adapter(self):
        row = Row(label="Pack", kind=KIND_ROOM, icon="/a.png",
                  fanart="/b.jpg", payload={"action": ACTION_PLAY})
        self.assertEqual(row.art, "/a.png")
        self.assertEqual(row.hero, "/b.jpg")
        self.assertEqual(row.title, "Pack")
        self.assertEqual(row.action, ACTION_PLAY)
        hero_fallback = Row(label="Pack", icon="/a.png")
        self.assertEqual(hero_fallback.hero, "/a.png")

    def test_screen_normalises_rows_and_reports_pages(self):
        screen = Screen(route=ROUTE_SEARCH, title="SEARCH",
                        rows=[Row(label="One")], page=2, pages=3, total=120,
                        noun="packs")
        self.assertIsInstance(screen.rows, tuple)
        self.assertEqual(screen.rows_per_page, DEFAULT_PAGE_SIZE)
        self.assertEqual(screen.page_label, "Page 2 of 3 · 120 packs")
        self.assertTrue(screen.has_previous)
        self.assertTrue(screen.has_next)
        single = Screen(route=ROUTE_SEARCH, title="SEARCH")
        self.assertEqual(single.page_label, "")
        self.assertFalse(single.has_previous)
        self.assertFalse(single.has_next)

    def test_action_result_normalises_tracks(self):
        result = ActionResult(True, ACTION_PLAY_ALL, tracks=[PlayItem("A", "u")])
        self.assertIsInstance(result.tracks, tuple)

    def test_fact_is_capped_and_size_facts_are_compact(self):
        self.assertLessEqual(len(_fact("a" * 40)), 16)
        self.assertTrue(_fact("a" * 40).endswith("…"))
        self.assertEqual(_size_fact(12 * 1024 * 1024), "12.0 MB")
        self.assertEqual(_size_fact(1024), "1 KB")
        self.assertEqual(_size_fact(0), "")

    def test_the_module_has_no_kodi_or_network_import_at_top_level(self):
        path = os.path.join(SCREEN, "raveui", "screens", "library.py")
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        imported = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        for forbidden in ("xbmc", "xbmcgui", "xbmcaddon", "xbmcvfs",
                          "xbmcplugin", "urllib", "requests", "socket"):
            self.assertNotIn(forbidden, imported)


# ---------------------------------------------------------------- plugin wire
class WindowAdapterContractTests(unittest.TestCase):
    """Rows render through the existing adapter without a window.py edit."""

    def test_a_library_row_renders_through_the_existing_kodi_view(self):
        from raveui import window as ravewindow

        class FakeList(object):
            def __init__(self):
                self.batches = []
                self.selected = None

            def reset(self):
                pass

            def addItems(self, items):
                self.batches.append(list(items))

            def selectItem(self, index):
                self.selected = index

        class FakeWindow(object):
            def __init__(self, control):
                self.control = control

            def getControl(self, control_id):
                if control_id == ravewindow.CONTROL_LIST:
                    return self.control
                raise KeyError(control_id)

        icon = os.path.join(ROOT, "resources", "art", "favourites.png")
        fanart = os.path.join(ROOT, "resources", "art",
                              "fanart-favourites.jpg")
        row = Row(label="Dreamscape 19", kind=KIND_ROOM, fact="1994",
                  icon=icon, fanart=fanart, code="RP-33",
                  payload={"action": ACTION_OPEN}, plot="A tape pack")
        control = FakeList()
        view = ravewindow.KodiView(FakeWindow(control))
        view.set_rows([row])
        self.assertEqual(control.selected, 0)
        item = control.batches[0][0]
        self.assertEqual(item.label, "Dreamscape 19")
        self.assertEqual(item.label2, "1994")
        self.assertEqual(item.art["icon"], icon)
        self.assertEqual(item.art["fanart"], fanart)
        self.assertEqual(item.properties["rp_code"], "RP-33")
        self.assertEqual(item.info["video"]["plot"], "A tape pack")


class PluginBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rave-library-")
        art_dir = os.path.join(self.temp.name, "resources", "art")
        os.makedirs(art_dir)
        with open(os.path.join(art_dir, "favourites.png"), "wb") as handle:
            handle.write(b"png")
        self.calls = {}
        self.extra = types.SimpleNamespace(
            platform_kind=lambda url: "mixcloud")

        def search(query, page, rows):
            self.calls["search"] = (query, page, rows)
            return [{"identifier": "x", "title": "X"}], 1

        modules = types.SimpleNamespace(
            root=self.temp.name,
            latest=types.SimpleNamespace(
                RAVE_COLLECTION="collection:ravetapes AND mediatype:audio"),
            kodi=types.SimpleNamespace(
                setting_int=lambda name, default: 25),
            archive=types.SimpleNamespace(
                search=search, thumb=lambda identifier: "/thumb/" + identifier),
            http=types.SimpleNamespace(
                safe_stream_url=lambda url: "safe:" + url),
            favourites=types.SimpleNamespace(
                load=lambda: [{"kind": "pack", "target": "p", "title": "P"}],
                key=lambda entry: "k:" + entry["target"],
                has=lambda entry: True,
                add=lambda entry: True,
                remove=lambda key: True),
            downloads=types.SimpleNamespace(
                list_downloads=lambda: [{"key": "k"}],
                plan=lambda url, title, source: {"allowed": True},
                download=lambda plan, progress=None, cancelled=None: {
                    "ok": True},
                delete=lambda key: True),
            handoff=self.extra,
            addon=types.SimpleNamespace(
                getAddonInfo=lambda key: {"version": "3.9.51"}.get(key, "")),
        )
        self.backend = PluginBackend(modules=modules)

    def tearDown(self):
        self.temp.cleanup()

    def test_reads_scope_page_size_art_and_search(self):
        self.assertEqual(self.backend.scope(),
                         "collection:ravetapes AND mediatype:audio")
        self.assertEqual(self.backend.page_size(), 25)
        self.assertEqual(self.backend.archive_thumb("x"), "/thumb/x")
        self.assertEqual(self.backend.art("favourites.png"),
                         os.path.join(self.temp.name, "resources", "art",
                                      "favourites.png"))
        self.assertEqual(self.backend.art("missing.png"), "")
        docs, total = self.backend.search("q", 2, 25)
        self.assertEqual(docs[0]["identifier"], "x")
        self.assertEqual(total, 1)
        self.assertEqual(self.calls["search"], ("q", 2, 25))

    def test_favourites_and_downloads_are_delegated(self):
        self.assertEqual(self.backend.favourites()[0]["target"], "p")
        self.assertEqual(self.backend.favourite_key({"target": "p"}), "k:p")
        self.assertTrue(self.backend.favourite_has({}))
        self.assertTrue(self.backend.favourite_add({}))
        self.assertTrue(self.backend.favourite_remove("k:p"))
        self.assertEqual(self.backend.downloads(), [{"key": "k"}])
        self.assertTrue(self.backend.download_plan("u", "t", "s")["allowed"])
        self.assertTrue(self.backend.download({"allowed": True})["ok"])
        self.assertTrue(self.backend.download_delete("k"))

    def test_playable_and_platform_urls_are_delegated(self):
        self.assertEqual(self.backend.playable_url("https://x/1.mp3"),
                         "safe:https://x/1.mp3")
        self.assertEqual(self.backend.platform_kind("https://mixcloud.com"),
                         "mixcloud")

    def test_about_reads_both_addon_versions(self):
        info = self.backend.about()
        self.assertEqual(info.name, "Rave Player")
        self.assertEqual(info.version, "3.9.51")
        self.assertEqual(info.kodi_version, "21.0")
        self.assertTrue(info.links)
        self.assertTrue(info.sources)

    def test_missing_plugin_metadata_still_renders_about(self):
        modules = types.SimpleNamespace()
        backend = PluginBackend(modules=modules)
        info = backend.about()
        self.assertEqual(info.version, "")
        self.assertTrue(info.links)

    def test_extra_modules_are_imported_through_the_private_alias(self):
        extra = types.SimpleNamespace(platform_kind=lambda url: "youtube")
        modules = types.SimpleNamespace()
        backend = PluginBackend(modules=modules)
        with mock.patch.object(library_mod.importlib, "import_module",
                               return_value=extra) as importer:
            self.assertIs(backend._module("handoff"), extra)
        importer.assert_called_once_with(
            "raveplayer_plugin.resources.lib.handoff")
        self.assertIs(modules.handoff, extra)

    def test_broken_search_raises_for_the_screen_to_catch(self):
        modules = types.SimpleNamespace(
            latest=types.SimpleNamespace(RAVE_COLLECTION="scope"),
            kodi=types.SimpleNamespace(setting_int=lambda name, default: 50),
            archive=types.SimpleNamespace(
                search=lambda *args, **kwargs: (_ for _ in ()).throw(
                    RuntimeError("down"))),
        )
        backend = PluginBackend(modules=modules)
        with self.assertRaises(RuntimeError):
            backend.search("q", 1, 50)


class RealPluginBackendTests(unittest.TestCase):
    """The default backend against the repo's real plugin modules (no network)."""

    def setUp(self):
        pluginbridge.reset_cache()
        self.fav_dir = tempfile.mkdtemp(prefix="rave-library-fav-")
        self.dl_dir = tempfile.mkdtemp(prefix="rave-library-dl-")
        os.environ["RAVEPLAYER_FAV_DIR"] = self.fav_dir
        os.environ["RAVE_DOWNLOAD_DIR"] = self.dl_dir
        self.backend = PluginBackend()

    def tearDown(self):
        os.environ.pop("RAVEPLAYER_FAV_DIR", None)
        os.environ.pop("RAVE_DOWNLOAD_DIR", None)
        shutil.rmtree(self.fav_dir, ignore_errors=True)
        shutil.rmtree(self.dl_dir, ignore_errors=True)
        pluginbridge.reset_cache()

    def test_scope_page_size_and_art_come_from_the_plugin(self):
        self.assertEqual(self.backend.scope(),
                         "collection:ravetapes AND mediatype:audio")
        # The shared xbmcaddon stub advertises results_per_page=5.
        self.assertEqual(self.backend.page_size(), 25)
        path = self.backend.art("favourites.png")
        self.assertTrue(os.path.isfile(path), path)
        self.assertEqual(os.path.basename(path), "favourites.png")

    def test_favourites_round_trip_through_the_real_store(self):
        entry = {"kind": "pack", "target": "pack-1", "title": "Pack One",
                 "source": "Archive.org"}
        self.assertTrue(self.backend.favourite_add(entry))
        self.assertTrue(self.backend.favourite_has(entry))
        self.assertEqual(self.backend.favourites()[0]["title"], "Pack One")
        self.assertEqual(self.backend.favourite_key(entry), "pack:pack-1")
        self.assertTrue(self.backend.favourite_remove("pack:pack-1"))
        self.assertEqual(self.backend.favourites(), [])

    def test_downloads_read_the_real_index_without_network(self):
        self.assertEqual(self.backend.downloads(), [])

    def test_about_uses_the_plugin_and_script_versions(self):
        info = self.backend.about()
        self.assertEqual(info.version, "3.0.0")
        self.assertEqual(info.screen_version, "3.0.0")
        self.assertEqual(info.kodi_version, "21.0")
        self.assertEqual(info.licence, "GPL-3.0-or-later")
        self.assertTrue(info.links)
        self.assertTrue(info.sources)


if __name__ == "__main__":
    unittest.main()
