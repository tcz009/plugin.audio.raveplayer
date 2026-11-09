# -*- coding: utf-8 -*-
"""Offline tests for the 3.9.47 Rave Screen script add-on.

No Kodi device, no network and no renderer: the controller is driven through a
fake view, data source and playback service; the WindowXML adapter is driven
through the stub base class.
"""

import ast
import itertools
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCREEN = os.path.join(ROOT, "script.raveplayer.ui")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)
sys.path.insert(0, SCREEN)

import xbmc  # noqa: E402
import xbmcaddon  # noqa: E402
import xbmcgui  # noqa: E402
import xbmcplugin  # noqa: E402

from raveui import pluginbridge  # noqa: E402
from raveui.animation import SpinnerAnimator, frame_index  # noqa: E402
from raveui.controller import (PAINT_CURRENT, PAINT_EMPTY,  # noqa: E402
                               PAINT_OFFLINE, PAINT_UPDATING,
                               RaveScreenController)
from raveui.data import (Entry, Page, RaveData, SearchTarget, Track,  # noqa: E402
                         ROOM_ORDER)
from raveui.downloadqueue import DownloadQueue  # noqa: E402
from raveui.playback import PlaybackService  # noqa: E402
from raveui.screens.library import (ActionResult, PlayItem,
                                    Row as LibraryRow,
                                    Screen as LibraryScreen)
from raveui.screens.live import LiveTrack, Row as LiveRow  # noqa: E402
from raveui.surprise_pick import PickedTrack, SurprisePicker  # noqa: E402
from raveui.tasks import (DirectTaskRunner, TaskCancelled, TaskFailed, TaskTimeout,
                          ThreadTaskRunner)  # noqa: E402
from raveui import window as ravewindow  # noqa: E402


# --------------------------------------------------------------------- fakes
class FakeView(object):
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.index = 0
        self.title = ""
        self.subtitle = ""
        self.hero = None
        self.status = ""
        self.now_playing = ""
        self.spinner_visible = False
        self.spinner_images = []
        self.spinner_label = ""
        self.notes = []
        self.closed = False
        self.statuses = []
        self.visible_log = []
        self.page_info = ""
        self.key_hints = ("", "")
        self.live = False
        self.plate = None
        self.plate_heads = []
        self.footers = []
        self.footer = None

    def set_title(self, text):
        self.title = text

    def set_subtitle(self, text):
        self.subtitle = text

    def set_rows(self, rows, selected=0):
        self.rows = list(rows)
        self.index = int(selected or 0)

    def set_room_count(self, count):
        self.room_count = count

    def set_hero(self, entry):
        self.hero = entry

    def set_status(self, text):
        self.status = text
        self.statuses.append(text)

    def set_now_playing(self, text):
        self.now_playing = text

    def set_page_info(self, text):
        self.page_info = text

    def set_key_hints(self, ok_text, back_text):
        self.key_hints = (ok_text, back_text)

    def set_live(self, live):
        self.live = bool(live)

    def set_plate(self, kind, title, detail="", hint=""):
        self.plate = (kind, title, detail, hint)

    def clear_plate(self):
        self.plate = None

    def set_plate_head(self, path):
        self.plate_heads = getattr(self, "plate_heads", [])
        self.plate_heads.append(path)

    def set_footer(self, footer):
        self.footer = footer
        self.footers.append(footer)

    def selected_index(self):
        return self.index

    def set_spinner_visible(self, visible):
        self.spinner_visible = bool(visible)
        self.visible_log.append(bool(visible))

    def set_spinner_image(self, path):
        self.spinner_images.append(path)

    def set_spinner_label(self, text):
        self.spinner_label = text

    def notify(self, text):
        self.notes.append(text)

    def close(self):
        self.closed = True


class FakeData(object):
    def __init__(self):
        self.home = [
            Entry("latest", "Latest", "newest", "", "section"),
            Entry("toronto", "Toronto Rave Mixtape Archive", "tapes", "", "section"),
            Entry("surprise", "Spinning Surprise", "random", "", "surprise"),
        ]
        self.loaded = []
        self.section_rows = [Entry("pack-1", "Dreamscape 19", "Rave Tape Packs",
                                   "", "pack", "latest", "pack-1")]
        self.child_rows = [Entry("child-1", "Tape 1 - Brockie", "Dreamscape 19",
                                 "", "track", "latest", "https://example.test/1.mp3",
                                 Track("Tape 1 - Brockie", "Dreamscape 19",
                                       "https://example.test/1.mp3"))]
        self.frames = ["frame-0.png", "frame-1.png", "frame-2.png"]

    def home_rows(self):
        return list(self.home)

    def section_entries(self, key):
        self.loaded.append(("section", key))
        return list(self.section_rows)

    def entries_for(self, entry):
        self.loaded.append(("children", entry.key))
        return list(self.child_rows)

    def spinner_frames(self):
        return list(self.frames)

    def collection(self, entry):
        self.collection_calls = getattr(self, "collection_calls", [])
        self.collection_calls.append(entry.key)
        return [Track("One", entry.label, "https://example.test/a.mp3"),
                Track("Two", entry.label, "https://example.test/b.mp3")]

    def start_download(self, entry):
        self.downloads = getattr(self, "downloads", [])
        self.downloads.append(entry.key)
        return True, "Download started — progress is in Downloads."

    def add_favourite(self, entry):
        self.favourites = getattr(self, "favourites", [])
        self.favourites.append(entry.key)
        return True, "Added to favourites"

    def remove_favourite(self, key):
        return True

    def favourite_payload(self, entry):
        return {"kind": "stream", "target": entry.target or entry.key,
                "title": entry.label}


class FakeLibrary(object):
    """Scripted LibraryScreens double using the real Row/Screen protocol."""

    def __init__(self):
        self.calls = []
        self.play_calls = []
        self.removed = []

    def _room(self, route, title, rows=(), subtitle="", page=1, pages=1,
              total=None, query=""):
        return LibraryScreen(
            route=route, title=title, subtitle=subtitle, rows=tuple(rows),
            state="ready" if rows else "empty", page=page, pages=pages,
            total=len(rows) if total is None else total, page_size=50,
            query=query, noun="items")

    def search(self, query, page=1):
        self.calls.append(("search", query, page))
        if query == "nothing":
            return self._room("search", "SEARCH", (), "No matching packs",
                              query=query)
        rows = [
            LibraryRow(
                label="Found Pack", kind="room", fact="1995",
                icon="found.png", fanart="found-hero.jpg", code="RP-33",
                payload={"room": "pack", "mode": "archive_item",
                         "identifier": "found-1", "source": "Archive.org",
                         "target": "found-1", "title": "Found Pack"},
                subtitle="Internet Archive", plot="A tape pack"),
            LibraryRow(
                label="Other Pack", kind="room", fact="1994",
                icon="other.png", fanart="other-hero.jpg", code="RP-33",
                payload={"room": "pack", "mode": "archive_item",
                         "identifier": "found-2", "source": "Archive.org",
                         "target": "found-2", "title": "Other Pack"},
                subtitle="Internet Archive", plot="A tape pack"),
        ]
        return self._room("search", "SEARCH", rows, "“%s” · 2 packs" % query,
                          total=2, query=query)

    def favourites(self, page=1):
        self.calls.append(("favourites", page))
        row = LibraryRow(
            label="Saved Set", kind="track", fact="Archive.org",
            icon="fav.png", fanart="fav-hero.jpg", code="RP-34",
            payload={"action": "play", "url": "https://example.test/saved.mp3",
                     "title": "Saved Set", "source": "Archive.org",
                     "favourite_key": "stream:https://example.test/saved.mp3",
                     "target": "https://example.test/saved.mp3"},
            subtitle="Archive.org", plot="A saved set")
        return self._room("favourites", "FAVOURITES", [row], "1 saved")

    def downloads(self, page=1):
        self.calls.append(("downloads", page))
        row = LibraryRow(
            label="Saved File", kind="track", fact="1 MB",
            icon="dl.png", fanart="dl-hero.jpg", code="RP-35",
            payload={"action": "play", "url": "/tmp/saved.mp3",
                     "title": "Saved File", "local": True,
                     "download_key": "dl-1", "target": "/tmp/saved.mp3"},
            subtitle="Offline copy", plot="A download")
        return self._room("downloads", "DOWNLOADS", [row], "1 files")

    def about(self):
        self.calls.append(("about",))
        row = LibraryRow(
            label="Rave Player", kind="action", fact="3.9.51",
            icon="about.png", fanart="about-hero.jpg", code="RP-36",
            payload={"action": "open", "url": "https://example.test"},
            subtitle="About & Sources", plot="Version")
        return self._room("about", "ABOUT", [row], "Rave Player 3.9.51")

    def play(self, row):
        self.play_calls.append(row)
        payload = dict(getattr(row, "payload", None) or {})
        title = str(payload.get("title") or "Untitled")
        return ActionResult(True, "play", "Playing %s" % title,
                            track=PlayItem(title, str(payload.get("url") or ""),
                                           album=str(payload.get("source") or ""),
                                           local=bool(payload.get("local"))))

    def play_all(self, screen, shuffle=False):
        tracks = [PlayItem(row.label, str((row.payload or {}).get("url") or ""))
                  for row in screen.rows
                  if getattr(row, "kind", "") == "track"]
        return ActionResult(True, "shuffle" if shuffle else "play_all",
                            "Queued %d tracks" % len(tracks),
                            tracks=tuple(tracks))

    def shuffle(self, screen):
        return self.play_all(screen, shuffle=True)

    def remove(self, row):
        self.removed.append(row)
        return ActionResult(True, "remove", "Removed", refresh="favourites")

    def retry(self, target):
        return self.favourites()


class FakePlayback(object):
    def __init__(self):
        self.calls = []
        self.collections = []
        self.stop_calls = 0
        self.playing = False
        self.result = types.SimpleNamespace(text="Now playing: Track — Pack")

    def play(self, track):
        self.calls.append(track)
        self.playing = True
        return self.result

    def play_collection(self, tracks, shuffle=False):
        self.collections.append((list(tracks), bool(shuffle)))
        self.playing = True
        return types.SimpleNamespace(text="Queued %d tracks" % len(tracks))

    def stop(self):
        self.stop_calls += 1
        self.playing = False
        return True

    def is_playing(self):
        return self.playing


class RecordingAnimator(object):
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.ran = 0

    def run(self):
        self.ran += 1
        return True


class FakeClock(object):
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, milliseconds):
        self.now += float(milliseconds) / 1000.0


def controller(view=None, data=None, playback=None, library=None, **kwargs):
    view = view or FakeView()
    data = data or FakeData()
    playback = playback or FakePlayback()
    kwargs.setdefault("task_runner", DirectTaskRunner())
    kwargs.setdefault("library", library or FakeLibrary())
    kwargs.setdefault("surprise_picker", SurprisePicker(
        pick=lambda: {"identifier": "pack-1", "title": "Dreamscape 19"},
        resolve=lambda identifier: PickedTrack(
            title="Tape 1 - Brockie", url="https://example.test/1.mp3",
            identifier=identifier, pack="Dreamscape 19"),
        sleep=lambda seconds: None))
    ctl = RaveScreenController(view, data, playback, **kwargs)
    return ctl, view, data, playback


# ------------------------------------------------------------------ animation
class AnimationTests(unittest.TestCase):
    def test_frame_index_wraps_and_clamps(self):
        self.assertEqual(frame_index(0), 0)
        self.assertEqual(frame_index(0.1), 1)
        self.assertEqual(frame_index(1.0), 0)
        self.assertEqual(frame_index(-2), 0)

    def test_spins_for_at_least_1_2_seconds_on_the_calling_thread(self):
        clock = FakeClock()
        images = []
        animator = SpinnerAnimator(
            ["a.png", "b.png", "c.png", "d.png"], images.append,
            duration=1.2, fps=10, sleep=clock.sleep, clock=clock)
        self.assertTrue(animator.run())
        self.assertGreaterEqual(clock.now, 1.2)
        self.assertGreaterEqual(len(images), 13)
        self.assertEqual(set(images), {"a.png", "b.png", "c.png", "d.png"})

    def test_cancelled_reveal_stops_without_playback(self):
        calls = []
        animator = SpinnerAnimator(
            ["a.png"], calls.append, duration=1.2, fps=10,
            sleep=lambda ms: None, clock=lambda: 0.0, cancelled=lambda: True)
        self.assertFalse(animator.run())
        self.assertEqual(calls, [])

    def test_dead_image_control_is_fail_soft(self):
        def broken(path):
            raise RuntimeError("no control")

        animator = SpinnerAnimator(["a.png"], broken, sleep=lambda ms: None)
        self.assertFalse(animator.run())


# ------------------------------------------------------------------ controller
class AppData(FakeData):
    """Fake data with all the app entry points used by the controller tests."""

    def __init__(self):
        super().__init__()
        self.home = [
            Entry("latest", "Latest", "newest", "", "section"),
            Entry("search", "Search", "find", "", "search"),
            Entry("surprise", "Spinning Surprise", "random", "", "surprise"),
        ]
        self.search_rows = [
            Entry("found-1", "Found Pack", "search result", "", "pack",
                  "latest", "found-1"),
            Entry("found-2", "Other Pack", "search result", "", "pack",
                  "latest", "found-2"),
        ]
        self.search_calls = []
        self.child_rows = [Entry(
            "child-1", "Tape 1 - Brockie", "Dreamscape 19", "", "track",
            "latest", "https://example.test/1.mp3",
            Track("Tape 1 - Brockie", "Dreamscape 19",
                  "https://example.test/1.mp3"),
            downloadable=True)]

    def load(self, target, page=1, rows=25):
        if isinstance(target, SearchTarget):
            self.search_calls.append(target)
            return Page(list(self.search_rows), len(self.search_rows), 1, 1, rows)
        if target is None:
            return Page(list(self.home), len(self.home), 1, 1, rows)
        if isinstance(target, str):
            self.loaded.append(("section", target))
            return Page(list(self.section_rows), len(self.section_rows), 1, 1, rows)
        self.loaded.append(("children", target.key))
        return Page(list(self.child_rows), len(self.child_rows), 1, 1, rows)


class PagedFakeData(AppData):
    count = 60

    def load(self, target, page=1, rows=25):
        self.pages_called = getattr(self, "pages_called", [])
        self.pages_called.append((target, page, rows))
        count = self.count
        start = (page - 1) * rows
        entries = [Entry("p-%d" % index, "Pack %02d" % index, "paged", "",
                         "pack", "latest", "p-%d" % index)
                   for index in range(start, min(start + rows, count))]
        pages = max(1, (count + rows - 1) // rows)
        return Page(entries, count, min(page, pages), pages, rows,
                    has_next=page < pages)


class WidePagedFakeData(PagedFakeData):
    """Enough rows to exercise a page-size change across a page boundary."""

    count = 200


class ControllerTests(unittest.TestCase):
    def test_start_populates_home_and_selects_first_hero(self):
        ctl, view, data, _ = controller()
        rows = ctl.start()
        self.assertEqual(len(rows), 3)
        self.assertEqual(view.rows[0].label, "Latest")
        self.assertEqual(view.hero, view.rows[0])
        self.assertEqual(view.title, "RAVE PLAYER")
        self.assertIn("OK opens", view.subtitle)
        self.assertEqual(view.key_hints, ("OPEN", "BACK"))

    def test_focus_updates_hero(self):
        ctl, view, _, _ = controller()
        ctl.start()
        view.index = 2
        ctl.on_focus()
        self.assertEqual(view.hero.label, "Spinning Surprise")

    def test_section_load_then_back_returns_home_then_closes(self):
        ctl, view, data, _ = controller()
        ctl.start()
        view.index = 0
        self.assertTrue(ctl.on_click())
        self.assertEqual(data.loaded, [("section", "latest")])
        self.assertEqual(view.rows[0].label, "Dreamscape 19")
        self.assertEqual(ctl.stack_depth, 1)

        self.assertFalse(ctl.on_back())
        self.assertEqual(view.rows[0].label, "Latest")
        self.assertEqual(ctl.stack_depth, 0)

        self.assertTrue(ctl.on_back())
        self.assertTrue(view.closed)
        self.assertTrue(ctl.closed)

    def test_successful_section_paint_clears_the_loading_status(self):
        ctl, view, _, _ = controller()
        ctl.start()
        ctl.on_click()
        self.assertEqual(view.status, "")
        self.assertEqual(view.room_count, 1)
        self.assertEqual(ctl.page, 1)

    def test_back_restores_the_opened_row_not_row_one(self):
        ctl, view, data, _ = controller()
        data.section_rows = [
            Entry("pack-%d" % index, "Pack %d" % index, "Rave Tape Packs",
                  "", "pack", "latest", "pack-%d" % index)
            for index in range(3)]
        ctl.start()
        view.index = 0
        ctl.on_click()
        self.assertEqual(ctl.stack_depth, 1)
        view.index = 2
        ctl.on_focus()
        self.assertTrue(ctl.on_click())
        self.assertEqual(ctl.stack_depth, 2)

        self.assertFalse(ctl.on_back())
        self.assertEqual(view.index, 2)
        self.assertEqual(view.hero.label, "Pack 2")

        self.assertFalse(ctl.on_back())
        self.assertEqual(view.index, 0)
        self.assertEqual(view.hero.label, "Latest")

    def test_back_while_loading_closes_once(self):
        ctl, view, _, _ = controller()
        ctl.start()
        ctl._busy = True
        self.assertTrue(ctl.on_back())
        self.assertTrue(ctl.closed)
        self.assertTrue(view.closed)
        self.assertTrue(ctl.on_back())

    def test_load_failure_paints_an_error_plate_and_retry_recovers(self):
        ctl, view, data, _ = controller(data=AppData())
        ctl.start()
        original = data.load
        data.load = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("offline"))
        self.assertFalse(ctl.on_click())
        self.assertEqual(ctl.plate, "error")
        self.assertEqual(view.plate[0], "error")
        self.assertIn("SOURCE ERROR", view.plate[1])
        self.assertEqual(view.rows[0].label, "Latest")
        self.assertFalse(ctl._busy)

        data.load = original
        data.section_rows = [Entry("ok", "Recovered", "ok", "", "pack",
                                   "latest", "ok")]
        self.assertTrue(ctl.on_click())      # OK on the plate retries
        self.assertEqual(ctl.plate, "")
        self.assertEqual(view.rows[0].label, "Recovered")

    def test_empty_load_paints_the_standby_plate(self):
        ctl, view, data, _ = controller()
        data.section_rows = []
        ctl.start()
        self.assertFalse(ctl.on_click())
        self.assertEqual(ctl.plate, "empty")
        self.assertEqual(view.plate[0], "empty")
        self.assertEqual(view.plate[1], "STANDBY")
        self.assertIn("Nothing in", view.plate[2])
        self.assertFalse(ctl.on_back())
        self.assertEqual(ctl.plate, "")

    def test_load_timeout_paints_an_error_plate(self):
        class TimeoutRunner(object):
            def run(self, function):
                raise TaskTimeout("too slow")

        ctl, view, _, _ = controller(task_runner=TimeoutRunner())
        ctl.start()
        self.assertFalse(ctl.on_click())
        self.assertEqual(ctl.plate, "error")
        self.assertEqual(view.plate[1], "SOURCE TIMEOUT")

    def test_page_navigation_queues_the_next_page_and_back_restores_focus(self):
        ctl, view, data, _ = controller(data=PagedFakeData())
        ctl.start()
        view.index = 0
        ctl.on_click()
        self.assertEqual(ctl.page, 1)
        self.assertEqual(view.rows[0].label, "Pack 00")
        self.assertEqual(view.rows[-1].kind, "page_next")
        self.assertEqual(view.page_info, "P1/2")
        view.index = len(view.rows) - 1
        ctl.on_click()
        self.assertEqual(ctl.page, 2)
        self.assertEqual(view.rows[1].label, "Pack 50")
        self.assertEqual(view.rows[0].kind, "page_prev")
        ctl.on_back()          # back to page 1
        self.assertEqual(ctl.page, 1)
        self.assertEqual(view.rows[0].label, "Pack 00")

    def test_in_window_keyboard_types_searches_and_back_restores_query(self):
        library = FakeLibrary()
        ctl, view, data, _ = controller(data=AppData(), library=library)
        ctl.start()
        view.index = 1            # Search row
        self.assertTrue(ctl.on_click())
        self.assertEqual(ctl.view_kind, "keyboard")
        self.assertEqual(view.title, "SEARCH")
        self.assertIn("\u00abA\u00bb", view.rows[0].label)
        ctl.on_click()            # A
        self.assertEqual(ctl.search_query, "A")
        ctl.on_horizontal(1)
        ctl.on_click()            # B
        self.assertEqual(ctl.search_query, "AB")
        self.assertIn("\u00abB\u00bb", view.rows[0].label)
        view.index = 7            # SEARCH NOW (SCOPE is gone: one scope)
        self.assertTrue(ctl.on_click())
        self.assertEqual(ctl.view_kind, "list")
        self.assertEqual(library.calls[0], ("search", "AB", 1))
        self.assertEqual(view.rows[0].label, "Found Pack")
        self.assertEqual(view.rows[0].kind, "library_room")
        self.assertEqual(view.rows[0].payload["mode"], "archive_item")

        self.assertFalse(ctl.on_back())   # results -> keyboard
        self.assertEqual(ctl.view_kind, "keyboard")
        self.assertEqual(ctl.search_query, "AB")
        self.assertIn("\u00abB\u00bb", view.rows[0].label)
        self.assertFalse(ctl.on_back())   # keyboard -> home
        self.assertEqual(view.rows[0].label, "Latest")

    def test_context_play_all_and_shuffle_queue_the_collection(self):
        ctl, view, data, playback = controller(data=AppData())
        ctl.start()
        view.index = 0
        ctl.on_click()                    # section
        view.index = 0
        ctl.on_click()                    # pack -> track list
        view.index = 0
        self.assertTrue(ctl.on_context())
        labels = [row.label for row in view.rows]
        self.assertIn("Play all", labels)
        self.assertIn("Shuffle all", labels)
        view.index = labels.index("Play all")
        self.assertTrue(ctl.on_click())
        self.assertEqual(len(playback.collections), 1)
        self.assertEqual(len(playback.collections[0][0]), 2)
        self.assertFalse(playback.collections[0][1])

        view.index = 0
        self.assertTrue(ctl.on_context())
        labels = [row.label for row in view.rows]
        view.index = labels.index("Shuffle all")
        self.assertTrue(ctl.on_click())
        self.assertEqual(len(playback.collections), 2)
        self.assertTrue(playback.collections[1][1])

    def test_context_download_and_favourite_call_the_backend(self):
        ctl, view, data, _ = controller(data=AppData())
        ctl.start()
        view.index = 0
        ctl.on_click()
        view.index = 0
        ctl.on_click()                    # track list
        view.index = 0
        self.assertTrue(ctl.on_context())
        labels = [row.label for row in view.rows]
        self.assertIn("Download", labels)
        self.assertIn("Add to favourites", labels)
        view.index = labels.index("Download")
        self.assertTrue(ctl.on_click())
        self.assertEqual(data.downloads, ["child-1"])
        view.index = 0
        self.assertTrue(ctl.on_context())
        labels = [row.label for row in view.rows]
        view.index = labels.index("Add to favourites")
        self.assertTrue(ctl.on_click())
        self.assertEqual(data.favourites, ["child-1"])

    def test_live_genre_door_opens_the_genre_room(self):
        ctl, view, data, _ = controller(data=AppData())
        ctl.start()
        row = LiveRow(
            title="Jungle", fact="GENRE", art="", code="RP-37",
            kind="section",
            action={"type": "open", "source": "live_tag", "tag": "jungle",
                    "target": "jungle", "title": "Jungle"})
        self.assertTrue(ctl._run_live_action(row, row.action))
        self.assertEqual(data.loaded, [("children", "live-tag-jungle")])
        self.assertEqual(view.rows[0].label, "Tape 1 - Brockie")
        self.assertEqual(view.title, "Jungle")

    def test_about_classic_lists_action_opens_the_plugin_directory(self):
        ctl, view, _, _ = controller(data=AppData())
        ctl.start()
        entry = types.SimpleNamespace(
            kind="library_action", action="classic",
            payload={"action": "classic",
                     "url": "plugin://plugin.audio.raveplayer/?mode=classic_root"})
        with mock.patch.object(xbmc, "executebuiltin") as execute:
            self.assertTrue(ctl._run_library_action(entry))
        execute.assert_called_once_with(
            "ActivateWindow(Programs,plugin://plugin.audio.raveplayer/"
            "?mode=classic_root,return)")
        self.assertIn("Classic lists", view.status)

    def test_rows_per_page_cycles_and_reloads(self):
        ctl, view, data, _ = controller(data=PagedFakeData())
        ctl.start()
        view.index = 0
        ctl.on_click()
        self.assertEqual(ctl.rows_per_page, 50)
        view.index = 0
        ctl.on_context()
        labels = [row.label for row in view.rows]
        idx = next(i for i, label in enumerate(labels) if label.startswith("Rows per page"))
        view.index = idx
        ctl.on_click()
        self.assertEqual(ctl.rows_per_page, 100)
        self.assertTrue(data.pages_called)
        self.assertEqual(data.pages_called[-1][2], 100)
        ctl.on_context()
        labels = [row.label for row in view.rows]
        idx = next(i for i, label in enumerate(labels) if label.startswith("Rows per page"))
        view.index = idx
        ctl.on_click()
        self.assertEqual(ctl.rows_per_page, 25)

    def test_refresh_keeps_the_focused_row_and_its_hero(self):
        ctl, view, _, _ = controller(data=WidePagedFakeData())
        ctl.start()
        view.index = 0
        ctl.on_click()                        # Latest room
        view.index = 10
        ctl.on_focus()
        self.assertEqual(view.hero.label, "Pack 10")

        self.assertTrue(ctl.on_context())
        labels = [row.label for row in view.rows]
        view.index = labels.index("Refresh")
        self.assertTrue(ctl.on_click())
        self.assertEqual(view.index, 10)
        self.assertEqual(view.hero.label, "Pack 10")
        self.assertEqual(view.rows[10].label, "Pack 10")

    def test_rows_per_page_change_keeps_the_absolute_offset_and_hero(self):
        ctl, view, _, _ = controller(data=WidePagedFakeData())
        ctl.start()
        view.index = 0
        ctl.on_click()                        # Latest room at 50 rows
        self.assertTrue(ctl._goto_page(2))
        self.assertEqual(ctl.page, 2)
        view.index = 12                       # Pack 50 is row 1; Pack 61 here
        ctl.on_focus()
        self.assertEqual(view.hero.label, "Pack 61")

        self.assertTrue(ctl._cycle_rows_per_page())
        self.assertEqual(ctl.rows_per_page, 100)
        self.assertEqual(ctl.page, 1)
        self.assertEqual(view.rows[view.index].label, "Pack 61")
        self.assertEqual(view.hero.label, "Pack 61")

    def test_surprise_picks_once_animates_once_and_plays_once(self):
        animator = RecordingAnimator()
        ctl, view, data, playback = controller(
            animator_factory=lambda **kwargs: animator)
        ctl.start()
        view.set_spinner_visible(True)
        view.set_spinner_image(ctl._frames[0])
        playback.result = types.SimpleNamespace(
            text="Now playing: Tape 1 - Brockie — Dreamscape 19")
        self.assertTrue(ctl.surprise(True))
        self.assertEqual(animator.ran, 1)
        self.assertEqual(len(playback.calls), 1)
        self.assertEqual(view.now_playing,
                         "Now playing: Tape 1 - Brockie — Dreamscape 19")
        self.assertFalse(view.spinner_visible)
        self.assertIn(True, view.visible_log)
        self.assertIn(False, view.visible_log)
        self.assertEqual(view.spinner_images[0], "frame-0.png")

    def test_surprise_start_paints_splash_and_is_cancellable(self):
        ctl, view, _, _ = controller()
        ctl.start()
        with mock.patch("raveui.controller.threading.Thread") as thread:
            self.assertTrue(ctl._start_surprise())
            self.assertTrue(view.spinner_visible)
            self.assertTrue(thread.called)
        self.assertTrue(ctl._surprising)
        self.assertFalse(ctl.on_back())
        self.assertFalse(view.spinner_visible)
        self.assertFalse(ctl._surprising)
        self.assertFalse(view.closed)

    def test_surprise_no_pick_never_animates_or_plays(self):
        animator = RecordingAnimator()
        picker = SurprisePicker(pick=lambda: None, sleep=lambda seconds: None)
        ctl, view, data, playback = controller(
            animator_factory=lambda **kwargs: animator,
            surprise_picker=picker)
        ctl.start()
        self.assertFalse(ctl.surprise(True))
        self.assertEqual(picker.attempts, 3)
        self.assertEqual(animator.ran, 0)
        self.assertEqual(playback.calls, [])
        self.assertFalse(view.spinner_visible)
        self.assertFalse(ctl._busy)
        self.assertEqual(ctl.plate, "error")
        self.assertEqual(view.plate[1], "NO PACK FOUND")

    def test_surprise_pick_exception_never_plays_and_resets_busy(self):
        picker = SurprisePicker(
            pick=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
            sleep=lambda seconds: None)
        ctl, view, data, playback = controller(surprise_picker=picker)
        ctl.start()
        self.assertFalse(ctl.surprise(True))
        self.assertEqual(playback.calls, [])
        self.assertFalse(view.spinner_visible)
        self.assertFalse(ctl._busy)
        self.assertEqual(ctl.plate, "error")

    def test_surprise_animation_failure_never_plays(self):
        class BrokenAnimator(object):
            def __init__(self, **kwargs):
                pass

            def run(self):
                return False

        ctl, view, data, playback = controller(
            animator_factory=lambda **kwargs: BrokenAnimator(**kwargs))
        ctl.start()
        self.assertFalse(ctl.surprise(True))
        self.assertEqual(playback.calls, [])
        self.assertFalse(view.spinner_visible)
        self.assertEqual(view.plate[1], "REVEAL FAILED")

    def test_surprise_playback_failure_does_not_mark_handoff(self):
        class BrokenPlayback(FakePlayback):
            def play(self, track):
                raise RuntimeError("Kodi refused")

        ctl, view, data, _ = controller(playback=BrokenPlayback())
        ctl.start()
        self.assertFalse(ctl.surprise(True))
        self.assertFalse(ctl.handed_off)
        self.assertIn("Could not start", view.status)

    def test_playback_failure_does_not_mark_handoff(self):
        class BrokenPlayback(object):
            def play(self, track):
                raise RuntimeError("Kodi refused")

        ctl, view, data, _ = controller(playback=BrokenPlayback())
        ctl.start()
        view.index = 0
        ctl.on_click()          # section
        view.index = 0
        ctl.on_click()          # pack -> track list
        view.index = 0
        self.assertFalse(ctl.on_click())  # track -> playback fails
        self.assertFalse(ctl.handed_off)
        self.assertIn("Could not start", view.status)

    def test_track_handoff_is_single_and_back_keeps_audio_and_window(self):
        ctl, view, data, playback = controller()
        ctl.start()
        view.index = 0
        ctl.on_click()
        view.index = 0
        ctl.on_click()
        view.index = 0
        self.assertTrue(ctl.on_click())
        self.assertEqual(len(playback.calls), 1)
        self.assertFalse(ctl.on_back())    # back to the pack list
        self.assertFalse(view.closed)
        self.assertFalse(ctl.closed)
        self.assertIn("audio playing", view.status)
        # Back to Home, then Back stops the audio instead of leaving it
        # running; the next Back closes the window.
        ctl.on_back()
        self.assertFalse(view.closed)
        ctl.on_back()
        self.assertFalse(view.closed)
        self.assertEqual(playback.stop_calls, 1)
        ctl.on_back()
        self.assertTrue(view.closed)

    def test_live_handoff_sets_the_live_footer_policy(self):
        ctl, view, data, _ = controller(data=AppData())
        data.section_rows = [Entry(
            "kool", "Kool FM", "live", "", "station", "live",
            track=Track("Kool FM", "Live radio", "https://live.test/kool",
                        live=True))]
        ctl.start()
        view.index = 0
        ctl.on_click()
        view.index = 0
        self.assertTrue(ctl.on_click())
        self.assertTrue(view.live)
        self.assertTrue(ctl._playing_live)

    def test_stop_action_stops_audio_without_closing(self):
        ctl, view, _, playback = controller()
        ctl.start()
        self.assertTrue(ctl.on_stop())
        self.assertEqual(playback.stop_calls, 1)
        self.assertFalse(view.closed)
        self.assertEqual(view.status, "Stopped.")


# --------------------------------------------------------------------- window
class StubController(object):
    def __init__(self):
        self.clicks = 0
        self.back = 0
        self.focus = 0
        self.should_close = True

    def on_click(self):
        self.clicks += 1
        return True

    def on_focus(self):
        self.focus += 1

    def on_back(self):
        self.back += 1
        return self.should_close

    def shutdown(self):
        self.closed = True


class FakeAction(object):
    def __init__(self, action_id):
        self.action_id = action_id

    def getId(self):
        return self.action_id


class WindowAdapterTests(unittest.TestCase):
    def test_window_class_is_a_windowxml_with_our_skin(self):
        window = ravewindow.RaveScreenWindow(
            ravewindow.XML_FILE, ravewindow.ADDON_PATH)
        self.assertIsInstance(window, xbmcgui.WindowXML)
        self.assertEqual(window.xml_filename, ravewindow.XML_FILE)
        self.assertFalse(window.closed)

    def test_close_marks_controller_closed(self):
        window = ravewindow.RaveScreenWindow("x.xml", "/tmp")
        ctl, _, _, _ = controller()
        window._controller = ctl
        window.close()
        self.assertTrue(window.closed)
        self.assertTrue(ctl.closed)
        window.close()

    def test_close_hands_active_downloads_to_the_headless_owner(self):
        window = ravewindow.RaveScreenWindow("x.xml", "/tmp")
        queue = mock.Mock()
        window._queue = queue
        window.close()
        queue.spawn_worker.assert_called_once()

    def test_click_delegates_to_controller(self):
        window = ravewindow.RaveScreenWindow("x.xml", "/tmp")
        stub = StubController()
        window._controller = stub
        window.onClick(ravewindow.CONTROL_LIST)
        self.assertEqual(stub.clicks, 1)

    def test_back_closes_exactly_once(self):
        window = ravewindow.RaveScreenWindow("x.xml", "/tmp")
        stub = StubController()
        window._controller = stub
        window.onAction(FakeAction(xbmcgui.ACTION_NAV_BACK))
        self.assertEqual(stub.back, 1)
        self.assertTrue(window.closed)
        window.onAction(FakeAction(xbmcgui.ACTION_NAV_BACK))
        self.assertTrue(window.closed)

    def test_dpad_moves_forward_to_base_and_refreshes_hero(self):
        window = ravewindow.RaveScreenWindow("x.xml", "/tmp")
        stub = StubController()
        window._controller = stub
        window.onAction(FakeAction(xbmcgui.ACTION_MOVE_DOWN))
        self.assertEqual(stub.focus, 1)
        self.assertEqual(len(window.actions), 1)

    def test_parent_dir_action_also_closes(self):
        window = ravewindow.RaveScreenWindow("x.xml", "/tmp")
        stub = StubController()
        window._controller = stub
        window.onAction(FakeAction(9))
        self.assertEqual(stub.back, 1)
        self.assertTrue(window.closed)

    def test_set_rows_binds_the_whole_list_in_one_message(self):
        class FakeList(object):
            def __init__(self):
                self.batches = []
                self.singles = 0
                self.selected = None

            def reset(self):
                pass

            def addItems(self, items):
                self.batches.append(list(items))

            def addItem(self, item):
                self.singles += 1

            def selectItem(self, index):
                self.selected = index

        class FakeWindow(object):
            def __init__(self, control):
                self.control = control

            def getControl(self, control_id):
                if control_id == ravewindow.CONTROL_LIST:
                    return self.control
                raise KeyError(control_id)

        control = FakeList()
        view = ravewindow.KodiView(FakeWindow(control))
        view.set_rows([Entry("a", "One", "fact one"),
                       Entry("b", "Two", "fact two")])
        self.assertEqual(len(control.batches), 1)
        self.assertEqual([item.label for item in control.batches[0]], ["One", "Two"])
        self.assertEqual(control.singles, 0)
        self.assertEqual(control.selected, 0)

    def test_open_screen_shows_and_returns_a_closed_window(self):
        class FakeWindow(object):
            def __init__(self):
                self.closed = False
                self.shown = False

            def show(self):
                self.shown = True
                self.closed = True

            def close(self):
                self.closed = True

        fake = FakeWindow()
        result = ravewindow.open_screen(
            window_factory=lambda *a, **k: fake,
            monitor_factory=lambda: types.SimpleNamespace(abortRequested=lambda: False))
        self.assertIs(result, fake)
        self.assertTrue(fake.shown)
        self.assertTrue(fake.closed)

    def test_open_screen_closes_when_kodi_aborts(self):
        class FakeWindow(object):
            def __init__(self):
                self.closed = False
                self.shown = False

            def show(self):
                self.shown = True

            def close(self):
                self.closed = True

        fake = FakeWindow()
        fake.closed = False
        result = ravewindow.open_screen(
            window_factory=lambda *a, **k: fake,
            monitor_factory=lambda: types.SimpleNamespace(abortRequested=lambda: True))
        self.assertIs(result, fake)
        self.assertTrue(fake.closed)

    def test_open_screen_waits_for_a_modal_dialog_before_showing(self):
        class FakeWindow(object):
            def __init__(self):
                self.closed = False
                self.initialized = False
                self.shown = 0

            def show(self):
                # Real Kodi sends GUI_MSG_WINDOW_INIT and invokes onInit, which
                # sets this flag; a modal-refused show() never does.
                self.shown += 1
                self.initialized = True

            def close(self):
                self.closed = True

        fake = FakeWindow()
        modal = [True, True, False]
        with mock.patch.object(ravewindow, "_modal_dialog_active",
                               side_effect=lambda: modal.pop(0) if modal else False):
            result = ravewindow.open_screen(
                window_factory=lambda *a, **k: fake,
                monitor_factory=lambda: types.SimpleNamespace(
                    abortRequested=lambda: fake.shown > 0))
        self.assertIs(result, fake)
        self.assertEqual(fake.shown, 1)
        self.assertTrue(fake.closed)

    def test_open_screen_fails_fast_when_activation_is_refused(self):
        class FakeWindow(object):
            def __init__(self):
                self.closed = False
                self.initialized = False
                self.shown = 0

            def show(self):
                self.shown += 1
                # Refused activation: no onInit, so initialized stays False.

            def close(self):
                self.closed = True

        fake = FakeWindow()
        ticks = itertools.count(0.0, 1.0)
        with mock.patch.object(ravewindow, "_modal_dialog_active", return_value=False), \
                mock.patch.object(ravewindow, "_notify") as notify, \
                mock.patch.object(ravewindow.time, "monotonic",
                                  side_effect=lambda: next(ticks)):
            result = ravewindow.open_screen(
                window_factory=lambda *a, **k: fake,
                monitor_factory=lambda: types.SimpleNamespace(abortRequested=lambda: False))
        self.assertIs(result, fake)
        self.assertGreaterEqual(fake.shown, 1)
        notify.assert_called_once()
        # No headless keepalive. Do not close() an uninitialised window:
        # Window.close() would send TMSG_GUI_PREVIOUS_WINDOW and pop the root
        # list the user is standing on.
        self.assertFalse(fake.closed)


class SingleInstanceTests(unittest.TestCase):
    """P1-6: a second launch reuses/refuses, it never stacks a second window."""

    def test_second_open_screen_reuses_the_live_window(self):
        factories = []
        nested = {}

        class FakeWindow(object):
            def __init__(self):
                self.closed = False
                self.initialized = False
                self.shown = 0

            def show(self):
                self.shown += 1
                self.initialized = True
                if self.shown == 1:
                    nested["result"] = ravewindow.open_screen(
                        window_factory=lambda *a, **k: factories.append("second"),
                        monitor_factory=lambda: types.SimpleNamespace(
                            abortRequested=lambda: True))

            def close(self):
                self.closed = True

        fake = FakeWindow()

        def factory(*args, **kwargs):
            factories.append("first")
            return fake

        result = ravewindow.open_screen(
            window_factory=factory,
            monitor_factory=lambda: types.SimpleNamespace(
                abortRequested=lambda: True))
        self.assertIs(result, fake)
        self.assertIs(nested["result"], fake)
        self.assertEqual(factories, ["first"])

    def test_instance_lock_refuses_while_another_pid_is_alive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "screen-instance.lock")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("424242")
            with mock.patch.object(ravewindow, "_pid_alive", return_value=True):
                self.assertFalse(ravewindow._acquire_instance(path))
            self.assertTrue(os.path.exists(path))
            with mock.patch.object(ravewindow, "_pid_alive", return_value=False):
                self.assertTrue(ravewindow._acquire_instance(path))
            self.assertEqual(ravewindow._read_pid(path), os.getpid())
            ravewindow._release_instance(path)
            self.assertFalse(os.path.exists(path))

    def test_same_pid_stale_lock_self_heals_immediately(self):
        # Scripts run in Kodi's own process, so an unclean exit leaves Kodi's
        # live PID in the marker.  The OS lock, not the PID, decides liveness.
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "screen-instance.lock")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            old = time.time() - ravewindow.INSTANCE_LOCK_TTL
            os.utime(path, (old, old))
            self.assertTrue(ravewindow._acquire_instance(path))
            self.assertEqual(ravewindow._read_pid(path), os.getpid())
            ravewindow._release_instance(path)
            self.assertFalse(os.path.exists(path))

    def test_a_live_same_process_lock_still_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "screen-instance.lock")
            self.assertTrue(ravewindow._acquire_instance(path))
            try:
                self.assertFalse(ravewindow._acquire_instance(path))
                self.assertEqual(ravewindow._read_pid(path), os.getpid())
            finally:
                ravewindow._release_instance(path)
            self.assertFalse(os.path.exists(path))

    def test_no_fcntl_fallback_heals_a_stale_same_pid_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "screen-instance.lock")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            old = time.time() - ravewindow.INSTANCE_HEARTBEAT_TTL - 1
            os.utime(path, (old, old))
            with mock.patch.object(ravewindow, "fcntl", None):
                self.assertTrue(ravewindow._acquire_instance(path))
            self.assertEqual(ravewindow._read_pid(path), os.getpid())
            ravewindow._release_instance(path)
            self.assertFalse(os.path.exists(path))


# ----------------------------------------------------------------------- data
class FakeRandom(object):
    def __init__(self):
        self.calls = 0

    def choice(self, values):
        self.calls += 1
        return values[0]


def fake_modules():
    archive = types.SimpleNamespace(
        audio_files=mock.Mock(return_value=[
            {"title": "Tape 1 - Brockie", "url": "https://archive.test/1.mp3",
             "duration": 2637, "genre": "Jungle", "year": "1994"},
            {"title": "Tape 2 - Randall", "url": "https://archive.test/2.mp3"},
        ]),
        thumb=mock.Mock(return_value="https://archive.test/cover.jpg"),
        search=mock.Mock(return_value=([
            {"identifier": "found-1", "title": "Found Pack",
             "date": "1995-01-01"},
        ], 120)),
    )
    latest = types.SimpleNamespace(
        RAVE_COLLECTION="collection:ravetapes AND mediatype:audio",
        recent_packs=mock.Mock(return_value=[
            {"identifier": "pack-1", "title": "Dreamscape 19"}]),
        random_pack=mock.Mock(return_value={
            "identifier": "pack-1", "title": "Dreamscape 19"}),
        year_query=mock.Mock(side_effect=lambda year: (
            'title:("%s") AND mediatype:audio' % year)),
    )
    toronto = types.SimpleNamespace(
        genres=mock.Mock(return_value=[{"genre": "jungle", "label": "Jungle"}]),
        tracks=mock.Mock(return_value=[
            {"name": "Toronto Tape", "url": "https://toronto.test/a.mp3",
             "metadata": "40:39 • 96 kbps • 27.91 MB"}]),
    )
    legacy = types.SimpleNamespace(
        jungle_shows=mock.Mock(return_value=[
            {"key": "show-%d" % i, "name": "Show %02d" % i}
            for i in range(60)]),
        jungle_tracks=mock.Mock(return_value=[
            {"name": "Rinse 1997", "url": "https://jungle.test/a.mp3"}]),
        packs=mock.Mock(return_value=[
            {"key": "Dreamscape 19", "name": "Dreamscape 19",
             "tracks": [{"name": "Tape 1", "url": "https://rtp.test/a.mp3"}]}]),
        pack=mock.Mock(return_value={
            "key": "Dreamscape 19", "name": "Dreamscape 19",
            "tracks": [{"name": "Tape 1", "url": "https://rtp.test/a.mp3"}]}),
        playable=mock.Mock(side_effect=lambda url: url + "|Referer=https://ravetapepacks.com/"),
        categories=mock.Mock(return_value={
            "events": [{"id": "33", "name": "Vision"}],
            "djs": [{"id": "106", "name": "Brockie"}],
            "mcs": [{"id": "7", "name": "Det"}],
            "years": [{"id": "1994", "name": "1994"}],
        }),
        category_page=mock.Mock(return_value=(
            [{"id": "899", "name": "Dreamscape 7"}], "next")),
        all_packs=mock.Mock(return_value=(
            [{"id": "899", "name": "Dreamscape 7"}], "next")),
        post=mock.Mock(return_value={
            "key": "899", "name": "Dreamscape 7",
            "tracks": [{"name": "Charlie Hall",
                        "url": "https://rtp.test/Charlie_Hall.mp3"}]}),
    )
    _radio_names = {"kool": "Kool FM", "rinse": "Rinse FM",
                    "centreforce": "Centreforce 883"}
    radio = types.SimpleNamespace(
        curated=mock.Mock(side_effect=lambda token: [
            {"name": _radio_names.get(token, token.upper()),
             "url_resolved": "https://live.test/%s" % token}]),
        stations=mock.Mock(return_value=[]),
        stream_url=mock.Mock(side_effect=lambda station: station.get("url_resolved", "")),
        display=mock.Mock(side_effect=lambda station: (
            str(station.get("name") or "Live radio"),
            "GB · AAC · 128 kbps")),
    )
    http = types.SimpleNamespace(safe_stream_url=mock.Mock(side_effect=lambda url: url))
    favourites = types.SimpleNamespace(
        load=mock.Mock(return_value=[
            {"kind": "pack", "target": "pack-1", "title": "Dreamscape 19",
             "source": "Archive.org"},
            {"kind": "legacy_jt", "target": "show-1", "title": "Show One",
             "source": "JungleTapes.com"},
            {"kind": "stream", "target": "https://live.test/kool",
             "title": "Kool FM", "source": "Live radio"},
        ]),
        key=mock.Mock(side_effect=lambda row: "%s:%s" % (row["kind"], row["target"])),
        has=mock.Mock(return_value=False),
        add=mock.Mock(return_value=True),
        remove=mock.Mock(return_value=True),
    )
    downloads = types.SimpleNamespace(
        eligible=mock.Mock(side_effect=lambda url, source: bool(
            url and source and "archive.test" in url)),
        list_downloads=mock.Mock(return_value=[
            {"key": "dl-1", "title": "Saved Set", "source": "Archive.org",
             "path": "/tmp/saved.mp3", "exists": True, "size": 1024,
             "added": "2026-11-05T10:00:00Z", "url": "https://archive.test/1.mp3"},
        ]),
        format_size=mock.Mock(side_effect=lambda size: "%d B" % int(size or 0)),
        total_saved_bytes=mock.Mock(return_value=1024),
        delete=mock.Mock(return_value=True),
    )
    feeds = types.SimpleNamespace(
        registry=mock.Mock(return_value=[
            {"id": "feed-1", "name": "Jungle Lab", "plot": "Jungle podcast"}]),
        episodes=mock.Mock(return_value=[
            {"title": "Episode 1", "url": "https://feeds.test/1.mp3",
             "published": "2026-01-02", "duration": 1800}]),
    )
    dnbradio = types.SimpleNamespace(
        mixes=mock.Mock(return_value=[
            {"id": "42", "title": "DNB Show", "date": "2026-01-01"}]),
        stream_url=mock.Mock(return_value="https://dnb.test/42.mp3"),
    )
    moxser = types.SimpleNamespace(
        mixes=mock.Mock(return_value=[
            {"page_url": "https://moxser.test/mix", "title": "Moxser Mix",
             "date": "2026-01-01", "flyer": ""}]),
        mix=mock.Mock(return_value={
            "page_url": "https://moxser.test/mix", "title": "Moxser Mix",
            "mp3_url": "https://moxser.test/mix.mp3", "date": "2026-01-01"}),
    )
    hardscore = types.SimpleNamespace(
        items=mock.Mock(return_value=[
            {"page_url": "https://hardscore.test/post", "title": "Hardscore Set",
             "date": "2026-01-01"}]),
        page=mock.Mock(return_value={
            "url": "https://hardscore.test/post", "title": "Hardscore Set",
            "media_urls": ["https://hardscore.test/set.mp3"], "links": []}),
    )
    getdarker = types.SimpleNamespace(
        items=mock.Mock(return_value=[
            {"page_url": "https://getdarker.test/post", "title": "GetDarker Set",
             "media_urls": []}]))
    pirate = types.SimpleNamespace(
        entries=mock.Mock(return_value=[
            {"station": "Risk FM", "title": "Risk FM 1993", "year": "1993",
             "stream_url": "https://pirate.test/a.mp3"}]))
    handoff = types.SimpleNamespace(
        platform_kind=mock.Mock(return_value="mixcloud"),
        target=mock.Mock(return_value="plugin://plugin.audio.mixcloud/?mode=40&key=x"),
    )
    live = types.SimpleNamespace(is_live_stream=mock.Mock(return_value=False))
    nowplaying = types.SimpleNamespace(
        parse=mock.Mock(return_value={"venue": "Sanctuary"}))
    routes = types.SimpleNamespace(
        classic_filters=mock.Mock(return_value=[
            {"id": "dreamscape", "name": "Dreamscape",
             "query": 'title:(dreamscape) AND mediatype:audio',
             "plot": "Dreamscape packs", "art": "dreamscape.png",
             "fanart": "fanart-hub-packs.jpg"},
            {"id": "kool", "name": "Kool FM",
             "query": "collection:ravetapes AND Kool",
             "live_name": "Kool", "plot": "Kool FM sets",
             "art": "kool.png", "fanart": "fanart-hub-packs.jpg"},
        ]),
        classic_raves=mock.Mock(return_value=[
            {"name": "Sanctuary", "slug": "sanctuary",
             "query": 'title:(sanctuary) AND mediatype:audio',
             "archive_query": 'title:(sanctuary) AND mediatype:audio',
             "mixcloud_query": "sanctuary", "count": 12,
             "mixcloud_count": 2}]),
        classic_radio_sections=mock.Mock(return_value=[
            {"key": "jungle", "label": "Jungle", "tag": "jungle",
             "art": "radio-jungle.png", "plot": "Live jungle stations"}]),
        classic_archive_sections=mock.Mock(return_value=[
            {"key": "tapepacks", "label": "Every Pack",
             "query": '"tape pack" AND mediatype:audio',
             "art": "tapepacks-all.png", "plot": "Every pack"}]),
        classic_years=mock.Mock(return_value=[2026, 2025]),
        web_source_page=mock.Mock(side_effect=lambda source, page=1: {
            "source": source,
            "title": {"dejavu": "DejaVu FM",
                      "20bensons": "20bensons.com",
                      "ukraves": "UK Raves Downloads",
                      "ezgarage": "EZ Garage Sets"}.get(source, source),
            "sub": "Web source page",
            "label": source,
            "noun": "sets",
            "code": "RP-46",
            "download": source == "dejavu",
            "rows": [{
                "label": "Web Set %s" % source,
                "sub": "A web set",
                "url": "https://web.test/%s/%d.mp3" % (source, page),
                "path": "https://web.test/%s/%d.mp3" % (source, page),
                "art": "",
                "plot": "A web set",
                "label2": "2026",
                "fact": "2026",
                "fav": {"kind": "stream"},
                "download": ({"source": "podomatic"}
                             if source == "dejavu" else None),
            }],
            "page": page,
            "pages": 2,
            "total": 80,
            "per_page": 40,
            "has_next": page < 2,
            "next_page": page + 1,
        }),
        web_live_stations=mock.Mock(return_value=[
            {"token": "dejavu", "name": "DejaVu FM",
             "url": "https://live.test/dejavu", "art": "dejavu.png",
             "meta": "London rave radio"},
            {"token": "osa", "name": "OSA Radio",
             "url": "https://live.test/osa", "art": "osa.png",
             "meta": "Old-skool anthems"},
        ]),
    )
    legacyblog = types.SimpleNamespace(
        MAX_POSTS=500,
        source=mock.Mock(side_effect=lambda key: {
            "id": key, "name": "Mikus Musik" if key == "mikus"
            else "Demodulated Mixtapes"}),
        posts=mock.Mock(return_value=[
            {"title": "Blog Set", "page_url": "https://blog.test/post",
             "date": "2026-01-01", "summary": "A set",
             "media_urls": ["https://blog.test/preview.mp3"],
             "mixcloud_urls": ["https://www.mixcloud.com/mikus/set/"]}]),
        post=mock.Mock(return_value={
            "title": "Blog Set", "page_url": "https://blog.test/post",
            "date": "2026-01-01", "summary": "A set",
            "media_urls": ["https://blog.test/preview.mp3"],
            "mixcloud_urls": ["https://www.mixcloud.com/mikus/set/"]}),
    )
    addon = types.SimpleNamespace(getAddonInfo=mock.Mock(return_value="3.9.51"))
    return types.SimpleNamespace(
        root=ROOT, archive=archive, latest=latest, toronto=toronto, legacy=legacy,
        radio=radio, http=http, favourites=favourites, downloads=downloads,
        feeds=feeds, dnbradio=dnbradio, moxser=moxser, hardscore=hardscore,
        getdarker=getdarker, pirate=pirate, handoff=handoff, live=live,
        nowplaying=nowplaying, routes=routes, legacyblog=legacyblog,
        addon=addon, kodi=types.SimpleNamespace(), ui=types.SimpleNamespace())


class DataTests(unittest.TestCase):
    def data(self, **kwargs):
        return RaveData(modules=fake_modules(), root=ROOT, script_root=SCREEN,
                        **kwargs)

    def test_home_rows_are_the_ten_rooms(self):
        data = self.data()
        labels = [row.label for row in data.home_rows()]
        self.assertEqual(labels, [
            "Latest", "Tape Packs", "Pirate Radio", "Mixes & Shows",
            "Live Radio", "Favourites", "Downloads", "Search",
            "Spinning Surprise", "About",
        ])
        self.assertEqual(len(labels), 10)
        self.assertTrue(all(row.art for row in data.home_rows()))
        self.assertTrue(data.home_rows()[0].hero.endswith("fanart-latest.jpg"))
        surprise = [row for row in data.home_rows() if row.key == "surprise"][0]
        self.assertTrue(surprise.hero.endswith("fanart-surprise.jpg"))
        self.assertEqual([row.key for row in data.home_rows()],
                         list(ROOM_ORDER))

    def test_home_rows_carry_short_facts_codes_and_plots(self):
        data = self.data()
        rows = data.home_rows()
        self.assertEqual([row.code for row in rows], [
            "RP-01", "RP-37", "RP-38", "RP-32", "RP-31", "RP-34",
            "RP-35", "RP-33", "RP-07", "RP-36",
        ])
        for row in rows:
            with self.subTest(row=row.label):
                self.assertLessEqual(len(row.fact), 16)
                self.assertTrue(row.plot)
                self.assertTrue(row.hero)

    def test_section_rows_carry_facts_art_and_meta(self):
        data = self.data()
        self.assertEqual(data.section_entries("latest")[0].fact, "pack")
        self.assertEqual(data.section_entries("toronto")[0].fact, "genre")
        self.assertEqual(data.section_entries("jungletapes")[0].fact, "show")
        self.assertTrue(all(row.kind == "rtp_index"
                            for row in data.section_entries("ravetapepacks")))
        for key in ("latest", "toronto", "jungletapes", "ravetapepacks",
                    "mixes"):
            page = data.room(key, 1, 50)
            self.assertTrue(page.rows, key)
            for row in page.rows:
                self.assertLessEqual(len(row.fact), 16, (key, row.fact))
                self.assertTrue(row.plot, (key, row.label))
                self.assertTrue(row.meta, (key, row.label))

    def test_track_rows_carry_duration_year_genre_and_playability(self):
        data = self.data()
        parent = data.section_entries("latest")[0]
        rows = data.entries_for(parent)
        self.assertEqual(rows[0].fact, "43:57")
        self.assertEqual(rows[0].year, "1994")
        self.assertEqual(rows[0].genre, "Jungle")
        self.assertIn("1994", rows[0].meta)
        self.assertIn("Jungle", rows[0].meta)
        self.assertEqual(rows[0].code, "RP-01")
        self.assertEqual(rows[0].plot, parent.plot)
        self.assertTrue(rows[0].track.url.startswith("https://archive.test/"))

    def test_latest_section_builds_pack_rows_without_track_fetch(self):
        data = self.data()
        rows = data.section_entries("latest")
        self.assertEqual(rows[0].kind, "pack")
        self.assertEqual(rows[0].target, "pack-1")
        data.modules.archive.audio_files.assert_not_called()

    def test_toronto_genre_children_are_track_rows_with_duration(self):
        data = self.data()
        parent = data.section_entries("toronto")[0]
        rows = data.entries_for(parent)
        self.assertEqual(rows[0].kind, "track")
        self.assertEqual(rows[0].track.title, "Toronto Tape")
        self.assertEqual(rows[0].fact, "40:39")

    def test_ravetapepacks_track_keeps_the_referer_suffix(self):
        data = self.data()
        parent = next(row for row in data.section_entries("ravetapepacks")
                      if row.target == "events")
        category = data.entries_for(parent)[0]
        post = data.entries_for(category)[0]
        rows = data.entries_for(post)
        self.assertIn("Referer=", rows[0].track.url)

    def test_ravetapepacks_room_exposes_the_real_indexes(self):
        data = self.data()
        rows = data.section_entries("ravetapepacks")
        self.assertEqual([row.target for row in rows],
                         ["events", "djs", "mcs", "years", "all"])
        self.assertEqual(rows[0].label, "By Event (1)")
        self.assertEqual(rows[4].label, "All Packs")
        events = data.entries_for(rows[0])
        self.assertEqual(events[0].kind, "rtp_category")
        self.assertEqual(events[0].label, "Vision")
        self.assertEqual(events[0].target, "events:33")

    def test_rtp_category_and_post_navigation_reaches_tracks(self):
        data = self.data()
        door = next(row for row in data.section_entries("ravetapepacks")
                    if row.target == "events")
        category = data.entries_for(door)[0]
        page = data.children(category, 1, 25)
        self.assertEqual(page.rows[0].kind, "rtp_post")
        self.assertEqual(page.rows[0].label, "Dreamscape 7")
        self.assertTrue(page.has_next)
        tracks = data.entries_for(page.rows[0])
        self.assertEqual(tracks[0].kind, "track")
        self.assertIn("Referer=", tracks[0].track.url)

    def test_rtp_all_packs_is_cursor_paged(self):
        data = self.data()
        door = next(row for row in data.section_entries("ravetapepacks")
                    if row.target == "all")
        page = data.children(door, 1, 25)
        self.assertEqual(page.rows[0].kind, "rtp_post")
        self.assertTrue(page.has_next)
        self.assertTrue(page.cursor)

    def test_jungletapes_room_pages_60_shows(self):
        data = self.data()
        page = data.room("jungletapes", 2, 25)
        self.assertEqual(page.total, 60)
        self.assertEqual(page.pages, 3)
        self.assertEqual(page.page, 2)
        self.assertEqual(len(page.rows), 25)
        self.assertTrue(page.has_next)

    def test_module_owned_rooms_are_not_in_ravedata(self):
        """One implementation per concern: the shell data layer owns no library/live room."""
        data = self.data()
        for key in ("live", "favourites", "downloads", "about", "search"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    data.room(key, 1, 25)
        for name in ("random_pick", "search", "about_rows",
                     "_favourite_rows", "_download_rows", "_live_entries"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(data, name))

    def test_latest_seeds_the_one_surprise_cache(self):
        from raveui.surprise_pick import PackCache

        data = self.data()
        data.surprise_cache = PackCache()
        data.section_entries("latest")
        self.assertIn("pack-1", data.surprise_cache)
        self.assertEqual(data.surprise_cache.choose().get("identifier"), "pack-1")

    def test_mixes_room_covers_every_source(self):
        data = self.data()
        labels = [row.label for row in data.section_entries("mixes")]
        self.assertEqual(labels, [
            "DNBRADIO Shows", "Podcasts & Mixes", "DejaVu FM Archive",
            "Moxser", "Hardscore", "GetDarker", "Pirate Radio Archives",
            "Mikus Musik", "Demodulated Mixtapes"])
        dnb = data.entries_for(data.section_entries("mixes")[0])
        self.assertEqual(dnb[0].kind, "dnb_show")

    def test_packs_room_reaches_every_classic_tape_destination(self):
        data = self.data()
        rows = data.section_entries("packs")
        self.assertEqual([row.label for row in rows], [
            "Toronto Rave Mixtape Archive", "JungleTapes.com",
            "RaveTapePacks.com", "20bensons.com", "UK Raves Downloads",
            "EZ Garage Sets", "Classic Pack Series",
            "By Rave, Venue & Promoter", "By Year", "Every Pack"])
        self.assertEqual([row.target for row in rows], [
            "toronto", "jungletapes", "ravetapepacks", "20bensons",
            "ukraves", "ezgarage", "filters", "raves",
            "packs_years", "tapepacks"])
        self.assertEqual([row.kind for row in rows], [
            "section", "section", "section", "web_list", "web_list",
            "web_list", "filter_index", "rave_index",
            "year_index", "archive_search"])

    def test_web_doors_reach_paged_web_rows(self):
        data = self.data()
        rows = data.section_entries("packs")
        for target in ("20bensons", "ukraves", "ezgarage"):
            door = next(row for row in rows if row.target == target)
            page = data.children(door, 2, 50)
            self.assertEqual(page.rows_per_page, 40)
            self.assertEqual(page.pages, 2)
            self.assertEqual(page.page, 2)
            self.assertFalse(page.has_next)
            self.assertEqual(len(page.rows), 1)
            row = page.rows[0]
            self.assertEqual(row.kind, "track")
            self.assertEqual(row.track.path, row.track.url)
            self.assertTrue(row.track.url.startswith("https://web.test/%s/" % target))

    def test_dejavu_archive_is_a_paged_downloadable_web_room(self):
        data = self.data()
        mixes = data.section_entries("mixes")
        door = next(row for row in mixes if row.label == "DejaVu FM Archive")
        data.modules.downloads.eligible = mock.Mock(return_value=True)
        page = data.children(door, 1, 50)
        self.assertEqual(page.rows_per_page, 40)
        self.assertEqual(page.page, 1)
        self.assertTrue(page.has_next)
        row = page.rows[0]
        self.assertEqual(row.kind, "track")
        self.assertEqual(row.track.path, row.track.url)
        self.assertTrue(row.downloadable)
        self.assertEqual(row.download_source, "Rave Resolver")
        self.assertEqual(data.favourite_payload(row)["title"], row.label)

    def test_live_rows_include_the_web_stations(self):
        from raveui.screens.live import LiveRadio

        rows = LiveRadio(modules=self.data().modules).rows()
        self.assertEqual([row.title for row in rows[:5]],
                         ["Kool FM", "Rinse FM", "Centreforce 883",
                          "DejaVu FM", "OSA Radio"])
        self.assertEqual([row.action["url"] for row in rows[:5]],
                         ["https://live.test/kool", "https://live.test/rinse",
                          "https://live.test/centreforce",
                          "https://live.test/dejavu",
                          "https://live.test/osa"])

    def test_pirate_room_reaches_hardscore_archives_and_kool(self):
        data = self.data()
        rows = data.section_entries("pirate")
        self.assertEqual([row.label for row in rows],
                         ["Hardscore", "Pirate Radio Archives", "Kool FM Sets"])
        self.assertEqual([row.target for row in rows],
                         ["hardscore_source", "pirate_source", "kool"])
        hardscore = data.entries_for(rows[0])
        self.assertEqual(hardscore[0].kind, "hardscore_post")
        archives = data.entries_for(rows[1])
        self.assertEqual(archives[0].kind, "track")
        kool = data.entries_for(rows[2])
        pack = next(row for row in kool if row.kind == "pack")
        self.assertEqual(pack.target, "found-1")

    def test_classic_pack_series_and_rave_and_year_children(self):
        data = self.data()
        series = data.children(data.section_entries("packs")[6], 1, 50)
        self.assertEqual(series.rows[0].label, "Dreamscape")
        self.assertEqual(series.rows[0].kind, "filter")
        dreamscape = data.children(series.rows[0], 1, 50)
        self.assertEqual(dreamscape.rows[0].kind, "pack")
        self.assertEqual(dreamscape.rows[0].target, "found-1")
        kool = data.children(series.rows[1], 1, 50)
        self.assertEqual(kool.rows[0].kind, "filter_live")
        live = data.children(kool.rows[0], 1, 50)
        self.assertEqual(live.rows[0].kind, "track")
        self.assertTrue(live.rows[0].track.live)
        raves = data.children(data.section_entries("packs")[7], 1, 50)
        self.assertEqual(raves.rows[0].label, "Sanctuary")
        rave = data.children(raves.rows[0], 1, 50)
        self.assertEqual(rave.rows[0].kind, "pack")
        years = data.children(data.section_entries("packs")[8], 1, 50)
        self.assertEqual([row.label for row in years.rows], ["2026", "2025"])
        year = data.children(years.rows[0], 1, 50)
        self.assertEqual(year.rows[0].kind, "pack")
        every = data.children(data.section_entries("packs")[9], 1, 50)
        self.assertEqual(every.rows[0].kind, "pack")

    def test_live_genre_children_are_playable_live_rows(self):
        data = self.data()
        data.modules.radio.stations = mock.Mock(return_value=[
            {"name": "Jungle Station", "url_resolved": "https://live.test/jungle",
             "favicon": ""}])
        tags = data.room("live_tags", 1, 25)
        self.assertEqual(tags.rows[0].label, "Jungle")
        page = data.children(tags.rows[0], 1, 50)
        self.assertEqual(page.rows[0].label, "Jungle Station")
        self.assertTrue(page.rows[0].track.live)
        self.assertEqual(page.rows[0].track.station, "Jungle Station")

    def test_blog_sources_list_posts_and_media(self):
        data = self.data()
        mixes = data.section_entries("mixes")
        mikus = next(row for row in mixes if row.label == "Mikus Musik")
        posts = data.children(mikus, 1, 50)
        self.assertEqual(posts.rows[0].kind, "blog_post")
        self.assertEqual(posts.rows[0].label, "Blog Set")
        media = data.children(posts.rows[0], 1, 50)
        self.assertEqual(media.rows[0].kind, "track")
        self.assertEqual(media.rows[1].kind, "external")

    def test_spinner_frames_are_bundled_with_the_script(self):
        data = RaveData(modules=fake_modules(), root="/nonexistent",
                        script_root=SCREEN)
        frames = data.spinner_frames()
        self.assertEqual(len(frames), 10)
        self.assertTrue(all(os.path.isfile(path) for path in frames))
        import struct
        with open(frames[0], "rb") as handle:
            self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")
            handle.read(4)
            self.assertEqual(handle.read(4), b"IHDR")
            width, height = struct.unpack(">II", handle.read(8))
        self.assertEqual((width, height), (512, 512))


# --------------------------------------------------------------------- bridge
class PluginBridgeTests(unittest.TestCase):
    def tearDown(self):
        pluginbridge.reset_cache()

    def test_plugin_path_and_imports_are_read_only(self):
        path = pluginbridge.plugin_path()
        self.assertEqual(os.path.abspath(path), ROOT)
        modules = pluginbridge.load_plugin()
        self.assertEqual(os.path.abspath(modules.root), ROOT)
        self.assertTrue(hasattr(modules.latest, "random_pack"))
        self.assertTrue(hasattr(modules.legacy, "jungle_shows"))
        self.assertTrue(hasattr(modules.radio, "curated"))
        # The plugin's settings/profile context must not be the script add-on.
        self.assertEqual(os.path.abspath(modules.kodi.ADDON_PATH), ROOT)
        self.assertEqual(modules.kodi.ADDON_ID, "plugin.audio.raveplayer")

    def test_plugin_context_is_bound_before_data_modules_import(self):
        class FakeAddon(object):
            def __init__(self, addon_id=""):
                self.addon_id = addon_id or "script.raveplayer.ui"

            def getAddonInfo(self, key):
                plugin = self.addon_id == "plugin.audio.raveplayer"
                root = ROOT if plugin else SCREEN
                return {
                    "id": self.addon_id,
                    "name": "Rave",
                    "version": "3.9.47",
                    "path": root,
                    "profile": os.path.join(tempfile.gettempdir(), "rave-profile"),
                    "icon": os.path.join(root, "icon.png"),
                    "fanart": os.path.join(root, "fanart.jpg"),
                }.get(key, "")

        def factory(addon_id=""):
            return FakeAddon(addon_id)

        with mock.patch.object(xbmcaddon, "Addon", side_effect=factory):
            modules = pluginbridge.load_plugin()
        self.assertEqual(os.path.abspath(modules.kodi.ADDON_PATH), ROOT)
        # ``ui.DEFAULT_FANART`` is a module-level copy taken while ``ui``
        # imports; it must already be the plugin's fanart, not the script's.
        self.assertEqual(os.path.abspath(modules.ui.DEFAULT_FANART),
                         os.path.join(ROOT, "fanart.jpg"))

    def test_missing_plugin_raises_a_single_stable_error(self):
        class Missing(object):
            def __init__(self, addon_id):
                pass

            def getAddonInfo(self, key):
                return ""

        with self.assertRaises(pluginbridge.PluginUnavailable):
            pluginbridge.load_plugin(addon_factory=Missing)


# ------------------------------------------------------------------ packaging
XML_PATH = os.path.join(SCREEN, "resources", "skins", "Default", "720p",
                        ravewindow.XML_FILE)
ART_ROOT = os.path.join(SCREEN, "resources", "art", "rave-screen")
TEXTURE_ROOT = "special://home/addons/script.raveplayer.ui/"
ALLOWED_FONTS = frozenset(("font13", "font12", "font10"))


def xml_root():
    return ET.parse(XML_PATH).getroot()


def top_controls(root):
    return root.findall("./controls/control")


def by_id(root, control_id):
    for control in root.iter("control"):
        if control.get("id") == str(control_id):
            return control
    return None


def box(control):
    return tuple(int(control.findtext(tag)) for tag in
                 ("posx", "posy", "width", "height"))


def texture_values(root):
    tags = ("texture", "texturebg", "texturemid", "texturefocus",
            "texturenofocus", "textureleft", "textureright")
    values = []
    for element in root.iter():
        if element.tag in tags and element.text:
            values.append(element.text.strip())
    return values


class ManifestAndSkinTests(unittest.TestCase):
    def test_script_manifest_is_kodi_19_22_and_depends_on_the_plugin(self):
        root = ET.parse(os.path.join(SCREEN, "addon.xml")).getroot()
        self.assertEqual(root.get("id"), "script.raveplayer.ui")
        self.assertEqual(root.get("version"), "3.9.70")
        imports = {item.get("addon"): item.get("version")
                   for item in root.findall("./requires/import")}
        self.assertEqual(imports.get("xbmc.python"), "3.0.0")
        self.assertEqual(imports.get("plugin.audio.raveplayer"), "3.9.70")
        extension = root.find("./extension[@point='xbmc.python.script']")
        self.assertIsNotNone(extension)
        self.assertEqual(extension.get("library"), "default.py")

    def test_skin_media_files_exist(self):
        import xml.etree.ElementTree as ET

        path = os.path.join(SCREEN, "resources", "skins", "Default", "720p",
                            ravewindow.XML_FILE)
        root = ET.parse(path).getroot()
        media = os.path.join(SCREEN, "resources", "skins", "Default", "media")
        art = os.path.join(SCREEN, "resources", "art", "rave-screen")
        textures = {node.text for node in root.iter("texture") if node.text}
        self.assertTrue(textures)
        prefix = "special://home/addons/script.raveplayer.ui/"
        for texture in textures:
            if texture.startswith("$INFO["):
                continue
            if texture.startswith(prefix):
                path = os.path.join(SCREEN, texture[len(prefix):])
            else:
                path = os.path.join(media, texture)
            self.assertTrue(os.path.isfile(path), texture)

    def test_skin_fonts_exist_in_estuary(self):
        import xml.etree.ElementTree as ET

        # Estuary (Kodi 19-22) defines exactly these among the plain names used
        # here. Any other name silently falls back to font13: font16, font20
        # and font30 do not exist and previously collapsed the type hierarchy.
        allowed = {"font10", "font12", "font13", "font14", "font27", "font32",
                   "font37", "font45"}
        path = os.path.join(SCREEN, "resources", "skins", "Default", "720p",
                            ravewindow.XML_FILE)
        root = ET.parse(path).getroot()
        fonts = {node.text for node in root.iter("font") if node.text}
        self.assertTrue(fonts)
        self.assertEqual(fonts - allowed, set())

    def test_every_control_constant_exists_in_the_skin_xml(self):
        import xml.etree.ElementTree as ET

        path = os.path.join(SCREEN, "resources", "skins", "Default", "720p",
                            ravewindow.XML_FILE)
        root = ET.parse(path).getroot()
        controls = root.find("controls")
        ids = [control.get("id") for control in controls
               if control.tag == "control" and control.get("id")]
        for name in dir(ravewindow):
            if not name.startswith("CONTROL_"):
                continue
            self.assertIn(str(getattr(ravewindow, name)), ids, name)
        self.assertEqual(root.findtext("defaultcontrol"),
                         str(ravewindow.CONTROL_LIST))

    def test_spinner_controls_are_property_bound_not_constant_false(self):
        import xml.etree.ElementTree as ET

        path = os.path.join(SCREEN, "resources", "skins", "Default", "720p",
                            ravewindow.XML_FILE)
        root = ET.parse(path).getroot()
        by_id = {control.get("id"): control for control in root.iter("control")}
        expected = "String.IsEqual(Window.Property(%s),1)" % (
            ravewindow.SPLASH_PROPERTY,)
        for control_id in ravewindow.SPINNER_CONTROLS:
            control = by_id[str(control_id)]
            # A literal "false" is re-evaluated every frame by Kodi and wins
            # over Control.setVisible(True): the splash never paints.
            self.assertEqual(control.findtext("visible"), expected, control_id)
            self.assertNotEqual(control.findtext("visible"), "false", control_id)

    def test_script_sources_are_python39_compatible(self):
        paths = [os.path.join(SCREEN, "default.py")]
        for name in sorted(os.listdir(os.path.join(SCREEN, "raveui"))):
            if name.endswith(".py"):
                paths.append(os.path.join(SCREEN, "raveui", name))
        for path in paths:
            with self.subTest(path=os.path.basename(path)):
                with open(path, encoding="utf-8") as handle:
                    ast.parse(handle.read(), filename=path,
                              feature_version=(3, 9))


class RaveScreenXMLTests(unittest.TestCase):
    """The XML is the design contract: parse it, do not grep a few strings."""

    def setUp(self):
        self.root = xml_root()
        with open(XML_PATH, encoding="utf-8") as handle:
            self.markup = handle.read()

    def test_window_is_the_add_on_window_at_720p(self):
        self.assertEqual(self.root.tag, "window")
        self.assertEqual(self.root.get("type"), "window")
        self.assertEqual(self.root.get("id"), "15047")
        coordinates = self.root.find("./coordinates")
        self.assertEqual(coordinates.findtext("system"), "1")
        self.assertEqual(coordinates.findtext("posx"), "0")
        self.assertEqual(coordinates.findtext("posy"), "0")

    def test_defaultcontrol_is_50_and_no_setfocusid(self):
        self.assertEqual(self.root.findtext("./defaultcontrol"), "50")
        self.assertNotIn("setFocusId", self.markup)
        self.assertNotIn("setfocusid", self.markup.lower())

    def test_the_adapter_focuses_the_list_only_after_rows_exist(self):
        with open(os.path.join(SCREEN, "raveui", "window.py"),
                  encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("self._controller.start()", source)
        self.assertIn("self.setFocusId(CONTROL_LIST)", source)
        self.assertGreater(source.index("self.setFocusId(CONTROL_LIST)"),
                           source.index("self._controller.start()"))

    def test_bed_and_noise_are_full_bleed(self):
        for control_id in (100, 101):
            control = by_id(self.root, control_id)
            self.assertIsNotNone(control)
            self.assertEqual(box(control), (0, 0, 1280, 720))
        self.assertIn("screen-bed-1280x720.jpg",
                      by_id(self.root, 100).findtext("texture"))
        self.assertIn("noise-overlay-1280x720.png",
                      by_id(self.root, 101).findtext("texture"))

    def test_row_list_is_control_50_not_500(self):
        control = by_id(self.root, 50)
        self.assertIsNotNone(control)
        self.assertEqual(control.get("type"), "list")
        self.assertEqual(box(control), (64, 148, 480, 432))
        self.assertEqual(control.findtext("onup"), "50")
        self.assertEqual(control.findtext("ondown"), "50")
        self.assertEqual(control.findtext("onleft"), "50")
        self.assertEqual(control.findtext("onright"), "50")
        for layout, expected in (("itemlayout", (480, 48)),
                                 ("focusedlayout", (480, 48))):
            node = control.find(layout)
            self.assertIsNotNone(node, layout)
            self.assertEqual((int(node.get("width")), int(node.get("height"))),
                             expected)
        self.assertEqual(control.findtext("scrolltime"), "180")
        self.assertNotIn('id="500"', self.markup)
        self.assertNotIn("Container(500)", self.markup)

    def test_every_referenced_texture_exists(self):
        values = texture_values(self.root)
        self.assertGreaterEqual(len(values), 25)
        for value in values:
            if value.startswith("$INFO["):
                continue
            with self.subTest(texture=value):
                self.assertTrue(value.startswith(TEXTURE_ROOT), value)
                relative = value[len(TEXTURE_ROOT):]
                self.assertTrue(os.path.isfile(os.path.join(SCREEN, relative)),
                                value)

    def test_no_relative_texture_paths(self):
        for value in texture_values(self.root):
            if value.startswith("$INFO["):
                continue
            with self.subTest(texture=value):
                self.assertTrue(value.startswith("special://"), value)

    def test_all_59_design_assets_are_bundled(self):
        pngs = [name for name in os.listdir(ART_ROOT)
                if name.lower().endswith((".png", ".jpg", ".jpeg"))]
        self.assertGreaterEqual(len(pngs), 60)  # 59 + the untouched mark
        for name in ("screen-bed-1280x720.jpg", "noise-overlay-1280x720.png",
                     "hero-frame-640x360.png", "hero-scrim-640x360.png",
                     "hero-shadow-640x360.png", "hero-fallback-640x360.jpg",
                     "focus-plate-474x40.png", "focus-plate-shadow-474x40.png",
                     "focus-bar-6x34.png", "footer-plate-1152x64.png",
                     "np-wave-340x28.png", "progress-track-340x3.png",
                     "progress-fill-2x3.png", "sticker-rp.png",
                     "sticker-focus.png", "sticker-on-air.png",
                     "label-on-the-screen.png", "label-now-playing.png",
                     "label-surprise-me.png", "label-spinning-the-rack.png",
                     "label-the-rave-screen.png", "keycap-b.png",
                     "keycap-ok.png", "surprise-ring-640x640.png",
                     "surprise-caption-plate-640x168.png",
                     "button-focus-220x38.png", "button-nofocus-220x38.png",
                     "mark.png"):
            with self.subTest(asset=name):
                self.assertTrue(os.path.isfile(os.path.join(ART_ROOT, name)), name)

    def test_only_font13_font12_and_font10_are_used(self):
        fonts = {node.text.strip() for node in self.root.iter("font")
                 if node.text and node.text.strip()}
        self.assertTrue(fonts)
        self.assertEqual(fonts - ALLOWED_FONTS, set())

    def test_live_type_sits_inside_the_64_36_safe_frame(self):
        for control in top_controls(self.root):
            if control.get("type") != "label":
                continue
            x, y, width, height = box(control)
            control_id = control.get("id")
            with self.subTest(control=control_id):
                self.assertGreaterEqual(x, 64)
                self.assertGreaterEqual(y, 36)
                self.assertLessEqual(x + width, 1216)
                self.assertLessEqual(y + height, 684)

    def test_720p_bands_match_the_design(self):
        header_rule = by_id(self.root, 117)
        self.assertEqual(box(header_rule), (64, 112, 1152, 2))
        hero = by_id(self.root, 201)
        self.assertEqual(box(hero), (576, 148, 640, 360))
        self.assertEqual(640 / 360, 16 / 9)
        self.assertEqual(148 + 360, 508)          # hero ends above the caption
        self.assertEqual(box(by_id(self.root, 210))[1], 512)
        self.assertEqual(box(by_id(self.root, 212))[1] + 36, 608)
        footer = by_id(self.root, 600)
        self.assertEqual(box(footer), (64, 620, 1152, 64))
        self.assertEqual(64 + 1152, 1216)         # safe right
        self.assertEqual(620 + 64, 684)           # safe bottom
        self.assertEqual(148 + 9 * 48, 580)       # nine rows, no scroll

    def test_hero_and_focus_bindings(self):
        self.assertEqual(by_id(self.root, 201).findtext("texture"),
                         "$INFO[Container(50).ListItem.Art(fanart)]")
        self.assertEqual(by_id(self.root, 204).findtext("texture"),
                         "$INFO[Container(50).ListItem.Icon]")
        self.assertEqual(
            by_id(self.root, 207).findtext("label"),
            "$INFO[Container(50).ListItem.Property(rp_code)]")
        self.assertIn("Container(50).ListItem.Label",
                      by_id(self.root, 210).findtext("label"))
        self.assertIn("UPPERCASE", by_id(self.root, 210).findtext("label"))
        self.assertEqual(
            by_id(self.root, 211).findtext("label"),
            "$INFO[Container(50).ListItem.Property(rp_meta)]")
        self.assertEqual(by_id(self.root, 212).findtext("label"),
                         "$INFO[Container(50).ListItem.Plot]")
        for control_id in (115, 116):
            self.assertIn("Container(50).NumItems",
                          by_id(self.root, control_id).findtext("label"))

        list_control = by_id(self.root, 50)
        item = list_control.find("itemlayout")
        labels = [node.findtext("label") for node in item.findall("control")
                  if node.get("type") == "label"]
        self.assertIn("$INFO[ListItem.Label]", labels)
        self.assertIn("$INFO[ListItem.Label2]", labels)
        self.assertIn("$INFO[ListItem.Property(rp_index)]", labels)
        focused = list_control.find("focusedlayout")
        labels = [node.findtext("label") for node in focused.findall("control")
                  if node.get("type") == "label"]
        self.assertIn("[B]$INFO[ListItem.Label][/B]", labels)
        self.assertIn("$INFO[ListItem.Label2]", labels)
        self.assertIn("$INFO[ListItem.Property(rp_index)]", labels)
        effects = {(node.get("effect"), node.get("time"))
                   for node in focused.findall(".//animation")}
        self.assertIn(("slide", "160"), effects)
        self.assertIn(("fade", "120"), effects)
        self.assertIn(("slide", "150"), effects)

    def test_footer_uses_the_nowplaying_model_and_the_waveform(self):
        self.assertEqual(by_id(self.root, 603).findtext("label"),
                         "$INFO[Window.Property(rp_now_title)]")
        self.assertEqual(by_id(self.root, 605).findtext("label"),
                         "$INFO[Window.Property(rp_now_elapsed)]")
        self.assertEqual(by_id(self.root, 606).findtext("label"),
                         "$INFO[Window.Property(rp_now_duration)]")
        kicker = by_id(self.root, 602)
        self.assertEqual(kicker.get("type"), "label")
        self.assertEqual(kicker.findtext("label"),
                         "$INFO[Window.Property(rp_now_kicker)]")
        self.assertIn("rp_now_on_air", by_id(self.root, 601).findtext("visible"))
        progress = by_id(self.root, 608)
        self.assertEqual(progress.get("type"), "progress")
        self.assertEqual(progress.findtext("info"), "progress")
        self.assertIn("progress-bg-1x1.png", progress.findtext("texturebg"))
        self.assertIn("progress-mid-8x28.png", progress.findtext("texturemid"))
        self.assertIn("sticker-on-air.png",
                      by_id(self.root, 601).findtext("texture"))
        self.assertIn("np-wave-340x28.png",
                      by_id(self.root, 607).findtext("texture"))
        self.assertIn("keycap-ok.png",
                      by_id(self.root, 612).findtext("texture"))
        self.assertIn("keycap-b.png",
                      by_id(self.root, 614).findtext("texture"))
        # Idle footer follows the same Footer model (room + fact).
        self.assertIn("rp_now_room", by_id(self.root, 611).findtext("label"))
        self.assertIn("rp_now_fact", by_id(self.root, 616).findtext("label"))

    def test_surprise_state_matches_the_control_map(self):
        self.assertEqual(box(by_id(self.root, 700)), (0, 0, 1280, 720))
        self.assertEqual(box(by_id(self.root, 702)), (384, 36, 512, 512))
        self.assertEqual(box(by_id(self.root, 707)), (560, 648, 220, 38))
        self.assertEqual(by_id(self.root, 707).get("type"), "button")
        self.assertIn("button-focus-220x38.png",
                      by_id(self.root, 707).findtext("texturefocus"))
        self.assertIn("button-nofocus-220x38.png",
                      by_id(self.root, 707).findtext("texturenofocus"))
        self.assertIsNone(by_id(self.root, 707).findtext("onclick"))
        # The CANCEL button is Python-handled in onClick(707); a builtin
        # Action(Back) would be a second, hidden input path.
        self.assertEqual(by_id(self.root, 709).findtext("label"), "CANCEL")
        self.assertIn("surprise-burst-1280x720.jpg",
                      by_id(self.root, 700).findtext("texture"))
        self.assertIn("label-surprise-me.png",
                      by_id(self.root, 704).findtext("texture"))
        self.assertIn("label-spinning-the-rack.png",
                      by_id(self.root, 705).findtext("texture"))
        expected_visibility = "String.IsEqual(Window.Property(%s),1)" % (
            ravewindow.SPLASH_PROPERTY,)
        for control_id in range(700, 714):
            control = by_id(self.root, control_id)
            self.assertIsNotNone(control, control_id)
            self.assertEqual(control.findtext("visible"), expected_visibility,
                             control_id)


class _FakeControl(object):
    def __init__(self):
        self.items = []
        self.selected = None
        self.image = None
        self.label = None
        self.visible = None

    def reset(self):
        self.items = []

    def addItem(self, item):
        self.items.append(item)

    def selectItem(self, index):
        self.selected = index

    def setImage(self, path):
        self.image = path

    def setLabel(self, text):
        self.label = text

    def setVisible(self, visible):
        self.visible = bool(visible)


class _FakeWindow(object):
    def __init__(self):
        self.controls = {}
        self.props = {}

    def getControl(self, control_id):
        return self.controls.setdefault(control_id, _FakeControl())

    def setProperty(self, key, value):
        self.props[key] = value


class RowViewTests(unittest.TestCase):
    """KodiView is what actually builds the ListItems the hero binds to."""

    def setUp(self):
        self.window = _FakeWindow()
        self.view = ravewindow.KodiView(self.window)

    def test_rows_carry_label2_fact_art_properties_and_plot(self):
        rows = [
            Entry("latest", "LATEST", "long description",
                  os.path.join(ROOT, "resources", "art", "rave.png"),
                  "section", source="latest",
                  hero=os.path.join(ROOT, "resources", "art", "fanart-latest.jpg"),
                  fact="newest", code="RP-01", plot="Newest packs"),
            Entry("live", "LIVE RADIO", "long description", "",
                  "section", fact="live", code="RP-31"),
        ]
        self.view.set_rows(rows)
        control = self.window.getControl(50)
        self.assertEqual(len(control.items), 2)
        self.assertEqual(control.selected, 0)
        first, second = control.items
        self.assertEqual(first.label2, "newest")
        self.assertEqual(first.properties["rp_index"], "01")
        self.assertEqual(first.properties["rp_code"], "RP-01")
        self.assertEqual(first.properties["rp_meta"], "newest  ·  RP-01")
        self.assertTrue(first.art["fanart"].endswith("fanart-latest.jpg"))
        self.assertTrue(first.art["icon"].endswith("rave.png"))
        self.assertEqual(first.info["video"]["plot"], "Newest packs")
        self.assertEqual(second.properties["rp_index"], "02")
        self.assertEqual(second.properties["rp_meta"], "live  ·  RP-31")
        self.assertTrue(second.art["fanart"].endswith("hero-fallback-640x360.jpg"))

    def test_set_hero_uses_fanart_and_falls_back_to_the_print_plate(self):
        entry = Entry("latest", "LATEST", "desc", "",
                      "section", hero=os.path.join(
                          ROOT, "resources", "art", "fanart-latest.jpg"))
        self.view.set_hero(entry)
        self.assertTrue(self.window.getControl(201).image.endswith(
            "fanart-latest.jpg"))
        self.view.set_hero(None)
        self.assertEqual(self.window.getControl(201).image,
                         ravewindow.HERO_FALLBACK)

    def test_title_subtitle_status_and_now_playing(self):
        self.view.set_title("LATEST")
        self.view.set_subtitle("Newest packs")
        self.view.set_status("Loading…")
        self.view.set_now_playing("Now playing: Tape — Pack")
        self.assertEqual(self.window.getControl(119).label, "LATEST")
        self.assertEqual(self.window.getControl(120).label, "Newest packs")
        self.assertTrue(self.window.getControl(119).visible)
        self.assertTrue(self.window.getControl(120).visible)
        self.assertEqual(self.window.getControl(30).label, "Loading…")
        self.assertEqual(self.window.props["rp_now"],
                         "Now playing: Tape — Pack")

    def test_home_hides_the_view_crumb(self):
        self.view.set_title("RAVE PLAYER")
        self.view.set_subtitle("OK opens a source")
        self.assertFalse(self.window.getControl(119).visible)
        self.assertFalse(self.window.getControl(120).visible)
        self.view.set_title("LATEST")
        self.view.set_subtitle("Newest packs")
        self.assertTrue(self.window.getControl(119).visible)
        self.assertTrue(self.window.getControl(120).visible)

    def test_long_titles_are_ellipsised_inside_the_header(self):
        # P2-1: an over-long right-aligned label used to draw left over the
        # RAVE PLAYER wordmark.  The label is clipped before Kodi sees it.
        long_title = ("DAMON WILD - SONIC UNDERGROUND 05 - THE SYNEWAVE "
                      "SELECTION 1994")
        self.view.set_title(long_title)
        label = self.window.getControl(119).label
        self.assertLessEqual(len(label), ravewindow.MAX_VIEW_TITLE)
        self.assertTrue(label.endswith("…"))

    def test_room_count_is_pluralised(self):
        # P2-1: the XML literal rendered "1 ROOMS · STANDBY".
        self.view.set_room_count(1)
        self.assertEqual(self.window.getControl(115).label,
                         "[B]1[/B] ROOM · STANDBY")
        self.assertEqual(self.window.getControl(116).label,
                         "[B]1[/B] ROOM · ON AIR")
        self.view.set_room_count(6)
        self.assertEqual(self.window.getControl(115).label,
                         "[B]6[/B] ROOMS · STANDBY")

    def test_spinner_visibility_covers_the_whole_surprise_state(self):
        self.view.set_spinner_visible(True)
        for control_id in ravewindow.SPINNER_CONTROLS:
            self.assertTrue(self.window.getControl(control_id).visible,
                            control_id)
        # The XML condition reads this property, so it must agree with the
        # controls; otherwise Kodi re-hides them on the next frame.
        self.assertEqual(self.window.props[ravewindow.SPLASH_PROPERTY], "1")
        self.view.set_spinner_visible(False)
        for control_id in ravewindow.SPINNER_CONTROLS:
            self.assertFalse(self.window.getControl(control_id).visible,
                             control_id)
        self.assertEqual(self.window.props[ravewindow.SPLASH_PROPERTY], "0")
        self.assertEqual(len(ravewindow.SPINNER_CONTROLS), 14)


class PluginIntegrationTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]

    def test_root_has_rave_screen_as_a_non_folder_program_row(self):
        from resources.lib import routes

        routes.root(1, {})
        self.assertEqual(xbmcplugin.ITEMS[0]["label"], "Rave Player")
        self.assertIn("mode=screen", xbmcplugin.ITEMS[0]["url"])
        self.assertTrue(xbmcplugin.ITEMS[0]["art"]["icon"].endswith("screen.png"))
        self.assertTrue(xbmcplugin.ITEMS[0]["art"]["fanart"].endswith("fanart-screen.jpg"))
        # Kodi runs a non-folder plugin item via RunScriptWithParams: no
        # directory window, no DialogBusy, and Back stays on the root list.
        self.assertFalse(xbmcplugin.ITEMS[0]["isFolder"])
        self.assertTrue(all(item["isFolder"] for item in xbmcplugin.ITEMS[1:]))

    def test_screen_route_launches_the_script_without_a_directory(self):
        from resources.lib import routes

        with mock.patch.object(routes.xbmc, "getCondVisibility",
                               return_value=True), \
                mock.patch.object(routes.xbmc, "executebuiltin") as execute, \
                mock.patch.object(routes.kodi, "end_directory") as end:
            routes.rave_screen(-1, {})
        execute.assert_called_once_with("RunScript(script.raveplayer.ui)")
        end.assert_not_called()

    def test_screen_route_ends_a_legacy_folder_handle(self):
        from resources.lib import routes

        with mock.patch.object(routes.xbmc, "getCondVisibility",
                               return_value=True), \
                mock.patch.object(routes.xbmc, "executebuiltin"), \
                mock.patch.object(routes.kodi, "end_directory") as end:
            routes.rave_screen(7, {})
        end.assert_called_once()

    def test_screen_route_tells_the_user_when_script_missing(self):
        from resources.lib import routes

        with mock.patch.object(routes.xbmc, "getCondVisibility", return_value=False), \
                mock.patch.object(routes.xbmc, "executebuiltin") as execute, \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.rave_screen(-1, {})
        execute.assert_not_called()
        notify.assert_called_once()
        self.assertIn("not installed", notify.call_args[0][0])
        self.assertEqual(xbmcplugin.ITEMS, [])

    def test_screen_route_tells_the_user_when_script_disabled(self):
        from resources.lib import routes

        def visibility(condition):
            return condition.startswith("System.HasAddon")

        with mock.patch.object(routes.xbmc, "getCondVisibility",
                               side_effect=visibility), \
                mock.patch.object(routes.xbmc, "executebuiltin") as execute, \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.rave_screen(-1, {})
        execute.assert_not_called()
        notify.assert_called_once()
        self.assertIn("disabled", notify.call_args[0][0])


class RepoArtifactTests(unittest.TestCase):
    def test_committed_repo_lists_the_screen_and_contains_its_zip(self):
        import zipfile

        catalogue = os.path.join(ROOT, "repo", "addons.xml")
        with open(catalogue, encoding="utf-8") as handle:
            markup = handle.read()
        self.assertIn('id="script.raveplayer.ui"', markup)
        import xml.etree.ElementTree as ET
        manifest = ET.parse(os.path.join(SCREEN, "addon.xml")).getroot()
        screen_version = manifest.get("version")
        plugin_version = manifest.find(
            "./requires/import[@addon='plugin.audio.raveplayer']").get("version")
        self.assertIn('import addon="plugin.audio.raveplayer" version="%s"'
                      % plugin_version, markup)
        self.assertIn('id="script.raveplayer.ui" name="Rave Player App" version="%s"'
                      % screen_version, markup)
        repo_zip = os.path.join(ROOT, "repo", "script.raveplayer.ui",
                                "script.raveplayer.ui-%s.zip" % screen_version)
        self.assertTrue(os.path.isfile(repo_zip), repo_zip)
        with zipfile.ZipFile(repo_zip) as archive:
            names = set(archive.namelist())
        for name in ("script.raveplayer.ui/default.py",
                     "script.raveplayer.ui/raveui/window.py",
                     "script.raveplayer.ui/raveui/controller.py",
                     "script.raveplayer.ui/resources/skins/Default/720p/"
                     "script-raveplayer-ui.xml",
                     "script.raveplayer.ui/resources/skins/Default/media/"
                     "screen-bg.jpg",
                     "script.raveplayer.ui/resources/art/surprise-burst.jpg",
                     "script.raveplayer.ui/resources/art/spinner/head-512-00.png",
                     "script.raveplayer.ui/resources/art/rave-screen/"
                     "screen-bed-1280x720.jpg",
                     "script.raveplayer.ui/resources/art/rave-screen/"
                     "hero-frame-640x360.png",
                     "script.raveplayer.ui/resources/art/rave-screen/"
                     "mark.png"):
            self.assertIn(name, names)


class PlaybackServiceTests(unittest.TestCase):
    def setUp(self):
        del xbmc.PLAYED[:]

    def test_play_builds_one_music_playlist_and_calls_kodi_player(self):
        service = PlaybackService()
        track = Track("Tape 1 - Brockie", "Dreamscape 19",
                      "https://example.test/1.mp3", live=False)
        result = service.play(track)
        self.assertEqual(result.text,
                         "Now playing: Tape 1 - Brockie — Dreamscape 19")
        self.assertEqual(service.calls, 1)
        self.assertEqual(len(xbmc.PLAYED), 1)
        self.assertEqual(service.last_url, "https://example.test/1.mp3")

    def test_empty_url_is_rejected_without_playback(self):
        service = PlaybackService()
        with self.assertRaises(ValueError):
            service.play(Track("No URL", "Pack", ""))
        self.assertEqual(xbmc.PLAYED, [])

    def test_live_station_marks_the_item_live(self):
        service = PlaybackService()
        track = Track("Kool FM", "Live radio", "https://live.test/kool", live=True)
        service.play(track)
        self.assertEqual(len(xbmc.PLAYED), 1)

    def test_live_reconnect_uses_the_station_token(self):
        service = PlaybackService()
        track = LiveTrack(title="Kool FM", pack="Live radio",
                          url="https://live.test/kool", live=True,
                          station="kool")
        service.play(track)
        path = xbmc.PLAYED[0].items[0][0]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        self.assertEqual(query["station"], ["kool"])
        self.assertEqual(query["live"], ["1"])
        self.assertNotIn("Live radio", query["station"])


class DownloadQueueTests(unittest.TestCase):
    def modules(self, plan=None, result=None):
        plan = plan or {"allowed": True, "size": 100, "filename": "x.mp3",
                        "path": "/tmp/x.mp3", "key": "k", "url": "https://x/1.mp3"}
        result = result or {"ok": True, "reason": ""}
        downloads = types.SimpleNamespace(
            eligible=mock.Mock(return_value=True),
            plan=mock.Mock(return_value=plan),
            download=mock.Mock(side_effect=lambda planned, progress=None,
                               cancelled=None: self._finish(progress, result)),
            list_downloads=mock.Mock(return_value=[]),
            delete=mock.Mock(return_value=True),
        )
        return types.SimpleNamespace(downloads=downloads)

    @staticmethod
    def _finish(progress, result):
        if progress is not None:
            progress(50, 100)
            progress(100, 100)
        return result

    def wait(self, queue, predicate, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate(queue.rows()):
                return True
            time.sleep(0.01)
        return False

    def wait_store(self, path, predicate, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with open(path, encoding="utf-8") as handle:
                    value = json.load(handle)
            except (OSError, ValueError):
                time.sleep(0.01)
                continue
            rows = value.get("rows") if isinstance(value, dict) else value
            if predicate(rows or []):
                return True
            time.sleep(0.01)
        return False

    def wait_idle(self, queue, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with queue._lock:
                if not queue._running:
                    return True
            time.sleep(0.01)
        return False

    def test_download_progress_row_then_completion(self):
        modules = self.modules()
        queue = DownloadQueue(modules=modules)
        ok, message = queue.start("https://x/1.mp3", "Set", "Archive.org", key="k")
        self.assertTrue(ok)
        self.assertIn("started", message)
        self.assertTrue(self.wait(queue, lambda rows: not rows))
        self.assertEqual(modules.downloads.download.call_count, 1)
        self.assertEqual(queue.rows(), [])

    def test_download_plan_refusal_is_a_failed_row(self):
        modules = self.modules(plan={"allowed": False, "reason": "Not allowed"})
        queue = DownloadQueue(modules=modules)
        queue.start("https://x/1.mp3", "Set", "Archive.org", key="k")
        self.assertTrue(self.wait(queue, lambda rows: rows and
                                  rows[0]["status"] == "failed"))
        row = queue.rows()[0]
        self.assertIn("Not allowed", row["detail"])
        modules.downloads.download.assert_not_called()

    def test_download_failure_is_a_row_not_an_exception(self):
        modules = self.modules(result={"ok": False, "reason": "network down"})
        queue = DownloadQueue(modules=modules)
        queue.start("https://x/1.mp3", "Set", "Archive.org", key="k")
        self.assertTrue(self.wait(queue, lambda rows: rows and
                                  rows[0]["status"] == "failed"))
        self.assertIn("network down", queue.rows()[0]["detail"])

    def test_ineligible_source_is_refused_before_the_worker(self):
        modules = self.modules()
        modules.downloads.eligible.return_value = False
        queue = DownloadQueue(modules=modules)
        ok, message = queue.start("https://x/1.mp3", "Set", "Unknown")
        self.assertFalse(ok)
        self.assertIn("not downloadable", message)
        modules.downloads.plan.assert_not_called()


    def test_queue_persists_an_interrupted_row_for_the_next_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "download-queue.json")
            release = threading.Event()

            def blocked(planned, progress=None, cancelled=None):
                progress(42, 100)
                release.wait(2.0)
                return {"ok": False, "reason": "network down"}

            modules = self.modules()
            modules.downloads.download = mock.Mock(side_effect=blocked)
            queue = DownloadQueue(modules=modules, store_path=path)
            queue.start("https://x/1.mp3", "Set", "Archive.org", key="k")
            self.assertTrue(self.wait(
                queue, lambda rows: rows and rows[0]["percent"] == 42))
            # progress() updates memory before the worker persists it; wait
            # for the durable row so the next owner cannot read 0.
            self.assertTrue(self.wait_store(
                path, lambda rows: rows and rows[0]["percent"] == 42))
            next_owner = DownloadQueue(store_path=path)
            rows = next_owner.rows()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["key"], "k")
            self.assertEqual(rows[0]["percent"], 42)
            # An interrupted transfer is queued for the next owner, never
            # left claiming to be live in this dead interpreter.
            self.assertEqual(rows[0]["status"], "queued")
            release.set()
            self.assertTrue(self.wait(
                queue, lambda rows: rows and rows[0]["status"] == "failed"))
            self.assertTrue(self.wait_idle(queue))

    def test_window_queue_defers_transfer_to_the_headless_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "download-queue.json")
            modules = self.modules()
            queue = DownloadQueue(modules=modules, store_path=path,
                                  local_workers=False)
            queue.start("https://x/1.mp3", "Set", "Archive.org", key="k")
            time.sleep(0.1)
            self.assertEqual(modules.downloads.download.call_count, 0)
            self.assertEqual(queue.rows()[0]["status"], "queued")
            builtins = [line for _level, line in xbmc._lines]
            self.assertTrue(any("RunScript(script.raveplayer.ui,downloads)" in line
                                for line in builtins))
            self.assertTrue(queue.cancel("k"))
            self.assertEqual(queue.rows()[0]["status"], "cancelling")

    def test_cancel_leaves_a_completed_copy_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "download-queue.json")
            modules = self.modules()
            modules.downloads.list_downloads.return_value = [
                {"key": "k", "url": "https://x/1.mp3", "title": "Old copy"}]
            queue = DownloadQueue(modules=modules, store_path=path,
                                  local_workers=False)
            queue.start("https://x/1.mp3", "Set", "Archive.org", key="k")
            self.assertTrue(queue.cancel("k"))
            modules.downloads.delete.assert_not_called()
            self.assertEqual(queue.rows()[0]["status"], "cancelling")

    def test_cancel_marks_every_duplicate_row_for_the_same_url(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "download-queue.json")
            modules = self.modules()
            queue = DownloadQueue(modules=modules, store_path=path,
                                  local_workers=False)
            queue.start("https://x/1.mp3", "One", "Archive.org", key="a")
            queue.start("https://x/1.mp3", "Two", "Archive.org", key="b")
            self.assertTrue(queue.cancel("a"))
            rows = {row["key"]: row for row in queue.rows()}
            self.assertEqual(rows["a"]["status"], "cancelling")
            self.assertEqual(rows["b"]["status"], "cancelling")
            self.assertTrue(rows["a"]["cancel"])
            self.assertTrue(rows["b"]["cancel"])

    def test_a_cancel_that_lands_as_the_file_finishes_keeps_the_completed_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "download-queue.json")
            modules = self.modules()
            started = threading.Event()
            release = threading.Event()

            def slow_finish(planned, progress=None, cancelled=None):
                started.set()
                release.wait(2.0)
                return {"ok": True, "reason": ""}

            modules.downloads.download = mock.Mock(side_effect=slow_finish)
            modules.downloads.list_downloads.return_value = [
                {"key": "k", "url": "https://x/1.mp3"}]
            queue = DownloadQueue(modules=modules, store_path=path)
            queue.start("https://x/1.mp3", "Set", "Archive.org", key="k")
            self.assertTrue(started.wait(2.0))
            self.assertTrue(queue.cancel("k"))
            release.set()
            self.assertTrue(self.wait(
                queue, lambda rows: rows and
                rows[0]["status"] == "cancelled"))
            modules.downloads.delete.assert_not_called()
            self.assertNotEqual(queue.rows()[0]["status"], "downloading")

    def test_window_queue_shows_the_owners_downloading_status(self):
        import json as json_module

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "download-queue.json")
            with open(path, "w", encoding="utf-8") as handle:
                json_module.dump([{
                    "key": "k", "title": "Set", "source": "Archive.org",
                    "url": "https://x/1.mp3", "status": "downloading",
                    "percent": 42, "done": 42, "total": 100,
                    "updated": time.time() + 10,
                }], handle)
            queue = DownloadQueue(store_path=path, local_workers=False)
            row = queue.rows()[0]
            self.assertEqual(row["status"], "downloading")
            self.assertEqual(row["percent"], 42)

    def test_cancel_from_the_window_reaches_the_headless_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "download-queue.json")

            def slow(planned, progress=None, cancelled=None):
                for index in range(200):
                    if cancelled():
                        return {"ok": False, "reason": "cancelled by user"}
                    progress(index, 200)
                    time.sleep(0.01)
                return {"ok": False, "reason": "timed out"}

            modules = self.modules()
            modules.downloads.download = mock.Mock(side_effect=slow)
            window_queue = DownloadQueue(modules=modules, store_path=path,
                                         local_workers=False)
            window_queue.start("https://x/1.mp3", "Set", "Archive.org",
                               key="k")
            owner = DownloadQueue(modules=modules, store_path=path)
            owner.resume()
            self.assertTrue(self.wait(
                owner, lambda rows: rows and
                rows[0]["status"] == "downloading"))
            self.assertTrue(window_queue.cancel("k"))
            self.assertTrue(self.wait(
                owner, lambda rows: rows and
                rows[0]["status"] == "cancelled"))
            time.sleep(0.2)   # let the worker's final store write finish

    def test_spawn_worker_only_when_a_transfer_is_active(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "download-queue.json")
            release = threading.Event()

            def blocked(planned, progress=None, cancelled=None):
                release.wait(2.0)
                return {"ok": True, "reason": ""}

            modules = self.modules()
            modules.downloads.download = mock.Mock(side_effect=blocked)
            queue = DownloadQueue(modules=modules, store_path=path)
            self.assertFalse(queue.spawn_worker())
            queue.start("https://x/1.mp3", "Set", "Archive.org", key="k")
            self.assertTrue(queue.spawn_worker())
            builtins = [line for _level, line in xbmc._lines]
            self.assertTrue(any("RunScript(script.raveplayer.ui,downloads)" in line
                                for line in builtins))
            release.set()
            self.assertTrue(self.wait(queue, lambda rows: not rows))
            self.assertTrue(self.wait_idle(queue))

    def test_two_writers_keep_every_store_snapshot_valid(self):
        """The window and headless owner write the same file concurrently."""
        import json as json_module

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "download-queue.json")
            modules = self.modules()
            first = DownloadQueue(modules=modules, store_path=path,
                                  local_workers=False)
            second = DownloadQueue(modules=modules, store_path=path,
                                   local_workers=False)
            errors = []
            snapshots = []

            def write(queue, prefix, count):
                for index in range(count):
                    try:
                        queue.start("https://x/%s-%d.mp3" % (prefix, index),
                                    "Set %s %d" % (prefix, index),
                                    "Archive.org",
                                    key="%s-%d" % (prefix, index))
                    except Exception as exc:  # noqa: BLE001 - reported below
                        errors.append(exc)

            def observe():
                for _ in range(500):
                    try:
                        with open(path, encoding="utf-8") as handle:
                            value = json_module.load(handle)
                    except FileNotFoundError:
                        continue
                    except (OSError, ValueError) as exc:
                        errors.append(exc)
                        continue
                    if isinstance(value, dict):
                        rows = value.get("rows")
                    else:
                        rows = value
                    if not isinstance(rows, list):
                        errors.append(AssertionError(
                            "not a row list: %r" % (value,)))
                        continue
                    for row in rows:
                        if not isinstance(row, dict) or not row.get("key"):
                            errors.append(AssertionError(
                                "partial row snapshot: %r" % (row,)))
                    snapshots.append(len(rows))
                    time.sleep(0.0005)

            writer_a = threading.Thread(target=write, args=(first, "a", 80))
            writer_b = threading.Thread(target=write, args=(second, "b", 80))
            observer = threading.Thread(target=observe)
            writer_a.start()
            writer_b.start()
            observer.start()
            writer_a.join(10.0)
            writer_b.join(10.0)
            observer.join(10.0)

            self.assertEqual(errors, [])
            self.assertTrue(snapshots)
            with open(path, encoding="utf-8") as handle:
                final = json_module.load(handle)
            final_rows = final.get("rows") if isinstance(final, dict) else final
            self.assertIsInstance(final_rows, list)
            self.assertTrue(all(isinstance(row, dict) and row.get("key")
                                for row in final_rows))


class PlaybackPolicyTests(unittest.TestCase):
    def setUp(self):
        del xbmc.PLAYED[:]

    def test_play_collection_queues_every_track_in_one_playlist(self):
        service = PlaybackService()
        tracks = [Track("One", "Pack", "https://x/1.mp3"),
                  Track("Two", "Pack", "https://x/2.mp3")]
        result = service.play_collection(tracks)
        self.assertEqual(result.count, 2)
        self.assertEqual(len(xbmc.PLAYED), 1)
        self.assertEqual(len(xbmc.PLAYED[0]), 2)
        self.assertTrue(all(path.startswith("plugin://plugin.audio.raveplayer/")
                            for path, _item in xbmc.PLAYED[0].items))

    def test_play_collection_shuffles_and_keeps_every_track(self):
        service = PlaybackService()
        tracks = [Track(str(index), "Pack", "https://x/%d.mp3" % index)
                  for index in range(6)]
        service.play_collection(tracks, shuffle=True)
        self.assertEqual(len(xbmc.PLAYED[0]), 6)

    def test_downloaded_file_plays_from_disk_not_a_plugin_route(self):
        service = PlaybackService()
        service.play(Track("Saved", "Downloads", "/tmp/saved.mp3", local=True))
        path, _item = xbmc.PLAYED[0].items[0]
        self.assertEqual(path, "/tmp/saved.mp3")

    def test_external_handoff_uses_its_plugin_path(self):
        service = PlaybackService()
        service.play(Track("Mix", "GetDarker", "https://mixcloud.test/x",
                           path="plugin://plugin.audio.mixcloud/?mode=40&key=x"))
        path, _item = xbmc.PLAYED[0].items[0]
        self.assertTrue(path.startswith("plugin://plugin.audio.mixcloud/"))

    def test_stop_calls_the_player(self):
        service = PlaybackService()
        self.assertTrue(service.stop())
        self.assertEqual(service.stops, 1)

    def test_live_item_is_marked_live_and_uses_the_plugin_route(self):
        service = PlaybackService()
        service.play(Track("Kool FM", "Kool FM", "https://live.test/kool",
                           live=True))
        path, item = xbmc.PLAYED[0].items[0]
        self.assertIn("live=1", path)
        self.assertIn("station=Kool", path)


class ScreenStateXMLTests(unittest.TestCase):
    def setUp(self):
        self.root = xml_root()
        with open(XML_PATH, encoding="utf-8") as handle:
            self.markup = handle.read()

    def test_plate_controls_are_present_property_bound_and_textured(self):
        for control_id in (720, 721, 722, 723, 724, 725, 726, 727):
            control = by_id(self.root, control_id)
            self.assertIsNotNone(control, control_id)
        self.assertIn("String.IsEqual(Window.Property(rp_plate),1)", self.markup)
        self.assertIn("rp_plate_head", self.markup)
        self.assertIn("plate-scrim-1280x720.png", self.markup)
        for node in self.root.iter("visible"):
            self.assertNotEqual((node.text or "").strip(), "false")

    def test_page_indicator_control_exists(self):
        control = by_id(self.root, 617)
        self.assertIsNotNone(control)
        self.assertEqual(control.get("type"), "label")

    def test_live_hides_duration_and_progress(self):
        for control_id, prop in ((605, "rp_now_show_duration"),
                                 (606, "rp_now_show_duration"),
                                 (608, "rp_now_show_progress")):
            control = by_id(self.root, control_id)
            visible = control.findtext("visible") or ""
            self.assertIn(prop, visible, control_id)
            # The model hides both for live; the skin never guesses from
            # Player.Duration (which grows on a live stream).
            self.assertIn("String.IsEqual", visible, control_id)
            self.assertNotIn("Player.Duration", visible, control_id)

    def test_plate_scrim_is_bundled_and_full_bleed(self):
        control = by_id(self.root, 720)
        self.assertEqual(box(control), (0, 0, 1280, 720))
        self.assertTrue(os.path.isfile(os.path.join(
            ART_ROOT, "plate-scrim-1280x720.png")))


class TaskRunnerTests(unittest.TestCase):
    def test_thread_runner_returns_the_value(self):
        runner = ThreadTaskRunner(sleep=lambda ms: None, clock=lambda: 0.0,
                                  monitor=types.SimpleNamespace(abortRequested=lambda: False),
                                  timeout=1.0)
        self.assertEqual(runner.run(lambda: 42), 42)

    def test_thread_runner_stops_when_the_window_closed(self):
        called = []
        runner = ThreadTaskRunner(sleep=lambda ms: None, clock=lambda: 0.0,
                                  monitor=types.SimpleNamespace(abortRequested=lambda: False),
                                  timeout=1.0, cancelled=lambda: True)
        with self.assertRaises(TaskCancelled):
            runner.run(lambda: called.append(1))
        self.assertEqual(called, [])

    def test_thread_runner_wraps_errors(self):
        runner = ThreadTaskRunner(sleep=lambda ms: None, clock=lambda: 0.0,
                                  monitor=types.SimpleNamespace(abortRequested=lambda: False),
                                  timeout=1.0)
        with self.assertRaises(TaskFailed):
            runner.run(lambda: (_ for _ in ()).throw(RuntimeError("boom")))


class _ControllableTask(object):
    """BackgroundTask double: stays running until the test releases it."""

    def __init__(self, function):
        self.function = function
        self.done = False
        self.value = None
        self.error = None

    def start(self):
        return self

    def finish(self):
        if self.done:
            return
        try:
            self.value = self.function()
        except Exception as exc:  # noqa: BLE001 - surfaced by poll
            self.error = exc
        self.done = True

    def poll(self):
        if not self.done:
            return ("running", None)
        if self.error is not None:
            return ("error", self.error)
        return ("done", self.value)


class StaleWhileRevalidateTests(unittest.TestCase):
    """3.9.52: paint the saved page, refresh off-thread, repaint on change."""

    def setUp(self):
        from raveui.paintcache import PaintCache

        self.tmp = tempfile.mkdtemp(prefix="rave-paint-test-")
        self.cache = PaintCache(directory=self.tmp, versions="test/3.9.52")
        self.view = FakeView()
        self.library = FakeLibrary()
        self.ctl, _, self.data, _ = controller(
            view=self.view, library=self.library, paint_cache=self.cache,
            background_task_factory=_ControllableTask)
        self.ctl.start()
        # The idle prefetch must never race these deterministic tests.
        self.ctl._prefetch_cancel.set()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed(self, rows, page=1):
        from raveui.paintcache import encode_page
        from raveui.data import Page

        page_obj = Page(rows=list(rows), total=len(rows), page=page, pages=1,
                        rows_per_page=50)
        self.assertTrue(self.cache.store(
            "page", "latest", page, 50, encode_page(page_obj),
            nav="list:p%d" % page))

    def test_cache_hit_paints_before_any_source_call(self):
        saved = Entry("saved-1", "Saved pack", "Internet Archive", "",
                      "pack", "latest", "saved-1")
        self._seed([saved])
        before = len(self.data.loaded)
        self.assertTrue(self.ctl._load_target("latest", 1))
        self.assertEqual(len(self.data.loaded), before)  # nothing blocked
        self.assertEqual(self.view.rows[0].label, "Saved pack")
        self.assertEqual(self.view.status, PAINT_UPDATING)
        self.assertIsNotNone(self.ctl._refresh)

    def test_refresh_repaints_only_when_the_rows_changed(self):
        saved = Entry("saved-1", "Saved pack", "Internet Archive", "",
                      "pack", "latest", "saved-1")
        self._seed([saved])
        self.ctl._load_target("latest", 1)
        task = self.ctl._refresh["task"]
        task.finish()
        self.ctl.tick()
        self.assertEqual(self.view.rows[0].label, "Dreamscape 19")
        self.assertIn("refresh repaint", " ".join(
            str(line) for line in xbmc._lines))

    def test_unchanged_refresh_does_not_repaint(self):
        rows = list(self.data.section_rows)
        self._seed(rows)
        self.ctl._load_target("latest", 1)
        self.ctl._refresh["task"].finish()
        self.ctl.tick()
        self.assertEqual(self.view.status, PAINT_CURRENT)

    def test_malformed_page_encode_never_breaks_a_room_load(self):
        from raveui.data import Page

        bad = Page(rows=[Entry("a", "A", "", "", "pack", "latest", "a")],
                   total="oops", page=1, pages=1, rows_per_page=50)
        self.ctl._store_page("latest", 1, bad)       # must not raise
        self.assertIsNone(self.ctl._cached_page("latest", 1))
        self.assertTrue(self.ctl._load_target("latest", 1))
        self.assertEqual(self.view.rows[0].label, "Dreamscape 19")

    def test_malformed_cache_value_is_a_miss_not_a_room_abort(self):
        import json
        import time

        path = self.cache._path(self.cache.key("page", "latest", 1, 50))
        payload = {"v": 1, "ts": time.time(),
                   "value": {"rows": [{"key": "a", "label": "A"}],
                             "total": "oops"}}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        self.assertIsNone(self.ctl._cached_page("latest", 1))
        self.assertTrue(self.ctl._load_target("latest", 1))
        self.assertEqual(self.view.rows[0].label, "Dreamscape 19")

    def test_refresh_failure_keeps_the_saved_page(self):
        saved = Entry("saved-1", "Saved pack", "Internet Archive", "",
                      "pack", "latest", "saved-1")
        self._seed([saved])
        self.ctl._load_target("latest", 1)
        task = self.ctl._refresh["task"]
        task.error = RuntimeError("offline")
        task.done = True
        self.ctl.tick()
        self.assertEqual(self.view.rows[0].label, "Saved pack")
        self.assertEqual(self.view.status, PAINT_OFFLINE)

    def test_back_during_refresh_never_waits_or_repaints(self):
        saved = Entry("saved-1", "Saved pack", "Internet Archive", "",
                      "pack", "latest", "saved-1")
        self._seed([saved])
        self.ctl._load_target("latest", 1)
        task = self.ctl._refresh["task"]
        self.assertFalse(self.ctl.on_back())
        self.assertIsNone(self.ctl._refresh)
        task.finish()
        self.ctl.tick()
        self.assertNotEqual(self.view.rows[0].label, "Dreamscape 19")

    def _seed_screen(self, screen):
        from raveui.paintcache import encode_library_screen

        self.assertTrue(self.cache.store(
            "library", "%s|" % screen.route, 1, 50,
            encode_library_screen(screen),
            nav="library:%s::p1" % screen.route))

    def _refreshed_library(self, screen):
        self._seed_screen(self.library.favourites())  # ready saved screen
        self.library.favourites = lambda page=1: screen
        self.assertTrue(self.ctl._load_target("favourites", 1))
        self.assertEqual(self.view.status, PAINT_UPDATING)
        self.ctl._refresh["task"].finish()
        self.ctl.tick()

    def test_destructive_remove_invalidates_the_cached_screen_first(self):
        # 3.9.56 advisor P2-3: a removed favourite must not reappear from the
        # paint cache while the background refresh runs.
        self._seed_screen(self.library.favourites())
        self.assertTrue(self.ctl._load_target("favourites", 1))
        self.assertEqual(self.view.rows[0].label, "Saved Set")
        empty = LibraryScreen(
            route="favourites", title="FAVOURITES", subtitle="0 saved",
            rows=(), state="empty", page=1, pages=1, total=0)
        self.library.remove = lambda row: ActionResult(
            True, "remove", "Removed")
        self.library.favourites = lambda page=1: empty
        subject = self.view.rows[0]
        self.ctl._library_context("library_remove", subject)
        self.assertIsNone(self.cache.load(
            "library", "favourites|", 1, 50,
            nav="library:favourites::p1"))
        self.assertNotIn("Saved Set", [row.label for row in self.view.rows])
        self.assertEqual(self.view.status, "Removed")

    def test_empty_library_refresh_shows_a_terminal_status(self):
        # Without the 3.9.55 fix the stale rows stayed correct but the status
        # stayed "UPDATING" forever, because an empty Screen is not an error.
        empty = LibraryScreen(
            route="favourites", title="FAVOURITES", subtitle="0 saved",
            rows=(), state="empty", page=1, pages=1, total=0)
        self._refreshed_library(empty)
        self.assertEqual(self.view.status, PAINT_EMPTY)
        self.assertEqual(self.view.rows[0].label, "Saved Set")  # SWR keeps it

    def test_error_library_refresh_shows_a_terminal_status(self):
        failed = LibraryScreen(
            route="favourites", title="FAVOURITES", rows=(), state="error",
            error="Could not load Favourites.", page=1, pages=1, total=0)
        self._refreshed_library(failed)
        self.assertEqual(self.view.status, PAINT_OFFLINE)
        self.assertEqual(self.view.rows[0].label, "Saved Set")


class ExternalStopStatusTests(unittest.TestCase):
    """3.9.54 device QA P2-2: an external Player.Stop must clear the status."""

    def setUp(self):
        self.state = {"snapshot": None}
        self.ctl, self.view, _, self.playback = controller(
            player_snapshot=lambda: self.state["snapshot"])
        self.ctl.start()
        self.ctl._prefetch_cancel.set()
        self.ctl._handoff(Track("Andy C", "RTP", "https://example.test/a.mp3"))

    def _tick(self, snapshot, age=0.0):
        self.state["snapshot"] = snapshot
        if age:
            self.ctl._player_active_at -= age
        self.ctl._footer_at = None
        self.ctl.tick()

    def test_active_player_keeps_the_status_line(self):
        self._tick({"playing": True, "title": "Andy C", "elapsed": 1,
                    "duration": 10, "paused": False})
        self.assertIn("Now playing", self.view.status)
        self.assertTrue(self.view.now_playing)

    def test_external_stop_clears_the_now_playing_status(self):
        self._tick({"playing": True, "title": "Andy C", "elapsed": 1,
                    "duration": 10, "paused": False})
        self.playback.playing = False       # JSON-RPC / external stop
        self._tick(None, age=5.0)
        self.assertEqual(self.view.status, "")
        self.assertEqual(self.view.now_playing, "")
        self.assertFalse(self.ctl._playback_status_active)
        self.assertTrue(self.view.footer.idle)

    def test_a_pending_start_is_not_mistaken_for_a_stop(self):
        self._tick(None)                    # Player.play has not started yet
        self.assertIn("Back leaves audio playing", self.view.status)
        self.assertTrue(self.view.now_playing)

    def test_in_app_stop_keeps_its_feedback(self):
        self.playback.playing = False
        self.ctl.on_stop()
        self.assertEqual(self.view.status, "Stopped.")
        self.assertEqual(self.view.now_playing, "")


class PaginatedRefreshTests(unittest.TestCase):
    """3.9.56: page-2 nav rows and clamped pages keep focus and refresh."""

    class PagingData(FakeData):
        def __init__(self, rows_by_page):
            FakeData.__init__(self)
            self.rows_by_page = rows_by_page
            self.calls = []

        def load(self, target, page, rows):
            self.calls.append((target, page, rows))
            wanted = min(max(1, int(page)), len(self.rows_by_page))
            entries = self.rows_by_page[wanted - 1]
            return Page(rows=list(entries), total=sum(
                len(item) for item in self.rows_by_page),
                page=wanted, pages=len(self.rows_by_page),
                rows_per_page=rows,
                has_next=wanted < len(self.rows_by_page))

    def setUp(self):
        from raveui.paintcache import PaintCache

        self.tmp = tempfile.mkdtemp(prefix="rave-page-refresh-")
        self.cache = PaintCache(directory=self.tmp, versions="test/3.9.56")
        self.view = FakeView()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _entries(prefix, count):
        return [Entry("%s-%d" % (prefix, index), "%s %d" % (prefix, index),
                      "", "", "pack", "latest", "%s-%d" % (prefix, index))
                for index in range(count)]

    def test_page_2_refresh_keeps_focus_on_content_not_the_nav_row(self):
        first = self._entries("first", 50)
        second = self._entries("second", 50)
        data = self.PagingData([first, second])
        ctl, view, _, _ = controller(
            view=self.view, data=data, paint_cache=self.cache,
            background_task_factory=_ControllableTask)
        ctl.start()
        ctl._prefetch_cancel.set()
        # A full page-2 cache, then focus content row 20 (on-screen index 21
        # because PREVIOUS PAGE occupies 0).
        ctl._store_page("latest", 2, Page(
            rows=list(second), total=100, page=2, pages=2, rows_per_page=50,
            has_next=False))
        self.assertTrue(ctl._load_target("latest", 2))
        ctl._select_index(21)
        self.assertEqual(ctl._current_index(), 21)
        # The source shrank to 10 rows on the same page.
        data.rows_by_page = [first, self._entries("short", 10)]
        ctl._refresh["task"].finish()
        ctl.tick()
        rows = view.rows
        self.assertEqual(len(rows), 11)       # PREVIOUS PAGE + 10 content
        self.assertEqual(view.index, 10)      # last content row, not nav
        self.assertEqual(rows[view.index].key, "short-9")

    def test_library_page_2_refresh_keeps_focus_on_content(self):
        class PagingLibrary(FakeLibrary):
            def __init__(self):
                FakeLibrary.__init__(self)
                self.pages = {
                    2: [self._library_row("long-%d" % index)
                        for index in range(50)]}

            @staticmethod
            def _library_row(label):
                return LibraryRow(
                    label=label, kind="track", fact="x",
                    icon="x.png", fanart="x.jpg", code="RP-34",
                    payload={"action": "play", "url": "/x.mp3",
                             "title": label})

            def favourites(self, page=1):
                rows = self.pages.get(page, [])
                return LibraryScreen(
                    route="favourites", title="FAVOURITES",
                    subtitle="100 saved", rows=tuple(rows), state="ready",
                    page=page, pages=2, total=100, page_size=50,
                    code="RP-34")

        library = PagingLibrary()
        ctl, view, _, _ = controller(
            view=self.view, library=library, paint_cache=self.cache,
            background_task_factory=_ControllableTask)
        ctl.start()
        ctl._prefetch_cancel.set()
        ctl._store_screen("favourites", "", 2, library.favourites(2))
        self.assertTrue(ctl._load_target("favourites", 2))
        ctl._select_index(21)
        self.assertEqual(ctl._current_index(), 21)
        library.pages[2] = [library._library_row("short-%d" % index)
                            for index in range(10)]
        ctl._refresh["task"].finish()
        ctl.tick()
        self.assertEqual(len(view.rows), 11)
        self.assertEqual(view.index, 10)
        self.assertEqual(view.rows[view.index].label, "short-9")

    def test_refresh_is_not_dropped_when_requested_page_was_clamped(self):
        from raveui.paintcache import encode_page

        saved = Page(rows=self._entries("saved", 3), total=3, page=1,
                     pages=1, rows_per_page=50, has_next=False)
        # Simulate a 3.9.55 entry stored under the requested page 3 while the
        # value actually painted page 1.
        self.assertTrue(self.cache.store(
            "page", "latest", 3, 50, encode_page(saved),
            nav="list:p3"))
        refreshed = self._entries("fresh", 3)
        data = self.PagingData([refreshed])
        ctl, view, _, _ = controller(
            view=self.view, data=data, paint_cache=self.cache,
            background_task_factory=_ControllableTask)
        ctl.start()
        ctl._prefetch_cancel.set()
        self.assertTrue(ctl._load_target("latest", 3))
        self.assertEqual(ctl._page, 1)        # clamped by the painted page
        ctl._refresh["task"].finish()
        ctl.tick()
        # The matcher follows the painted page, so the valid result applies.
        self.assertEqual([row.label for row in view.rows],
                         ["fresh 0", "fresh 1", "fresh 2"])
        self.assertEqual(ctl._page, 1)


class PrefetchCancelTests(unittest.TestCase):
    """3.9.56: D-pad focus movement stops the idle prefetch."""

    def test_focus_cancels_the_prefetch_event(self):
        ctl, view, data, _ = controller()
        ctl.start()
        try:
            self.assertFalse(ctl._prefetch_cancel.is_set())
            ctl.on_focus()
            self.assertTrue(ctl._user_active)
            self.assertTrue(ctl._prefetch_cancel.is_set())
        finally:
            ctl.shutdown()

    def test_focus_prevents_any_speculative_page_load(self):
        ctl, view, data, _ = controller()
        calls = []
        ctl._load_page = lambda target, page: calls.append((target, page))
        ctl.start()
        try:
            ctl.on_focus()
            thread = ctl._prefetch_thread
            if thread is not None:
                thread.join(1.0)
            self.assertEqual(calls, [])
        finally:
            ctl.shutdown()


class PaintCacheDiskTests(unittest.TestCase):
    def setUp(self):
        from raveui.paintcache import PaintCache

        self.tmp = tempfile.mkdtemp(prefix="rave-paint-disk-")
        self.cache = PaintCache(directory=self.tmp, versions="screen/3.9.52 plugin/3.9.51")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_page_round_trip_keeps_rows_and_tracks(self):
        from raveui.paintcache import decode_page, encode_page
        from raveui.data import Page

        page = Page(rows=[Entry("a", "A", "sub", "", "track", "latest",
                                "https://example.test/a.mp3",
                                Track("A", "Pack", "https://example.test/a.mp3",
                                      art="/tmp/a.jpg"))],
                    total=1, page=2, pages=3, rows_per_page=50, has_next=True)
        self.assertTrue(self.cache.store("page", "latest", 2, 50,
                                         encode_page(page)))
        loaded = decode_page(self.cache.load("page", "latest", 2, 50))
        self.assertEqual(loaded.page, 2)
        self.assertEqual(loaded.rows[0].label, "A")
        self.assertEqual(loaded.rows[0].track.url, "https://example.test/a.mp3")
        self.assertTrue(loaded.has_next)

    def test_nav_token_separates_a_folder_page_2_from_a_list_page_2(self):
        from raveui.data import Entry

        folder = Entry("latest", "Latest", "", "", "folder", "latest",
                       "latest")
        folder_key = self.cache.key("page", folder, 2, 50,
                                   nav="entry:folder:latest:p2")
        list_key = self.cache.key("page", "latest", 2, 50,
                                 nav="list:p2")
        self.assertNotEqual(folder_key, list_key)
        other_page = self.cache.key("page", "latest", 2, 50,
                                   nav="list:p3")
        self.assertNotEqual(list_key, other_page)

    def test_a_version_bump_invalidates_old_paint_pages(self):
        from raveui.paintcache import PaintCache, encode_page
        from raveui.data import Page

        page = Page(rows=[Entry("a", "A", "", "", "pack", "latest", "a")],
                    total=1, page=1, pages=1, rows_per_page=50)
        self.cache.store("page", "latest", 1, 50, encode_page(page))
        newer = PaintCache(directory=self.tmp,
                           versions="screen/3.9.53 plugin/3.9.51")
        self.assertIsNone(newer.load("page", "latest", 1, 50))

    def test_corrupt_entry_is_a_miss_not_a_crash(self):
        from raveui.paintcache import encode_page
        from raveui.data import Page

        page = Page(rows=[Entry("a", "A", "", "", "pack", "latest", "a")],
                    total=1, page=1, pages=1, rows_per_page=50)
        self.cache.store("page", "latest", 1, 50, encode_page(page))
        path = self.cache._path(self.cache.key("page", "latest", 1, 50))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{broken")
        self.assertIsNone(self.cache.load("page", "latest", 1, 50))

    def test_an_old_entry_is_a_miss_even_without_a_prune_write(self):
        import json
        import time

        from raveui.paintcache import MAX_AGE_SECONDS, encode_page
        from raveui.data import Page

        page = Page(rows=[Entry("a", "A", "", "", "pack", "latest", "a")],
                    total=1, page=1, pages=1, rows_per_page=50)
        self.cache.store("page", "latest", 1, 50, encode_page(page))
        path = self.cache._path(self.cache.key("page", "latest", 1, 50))
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        payload["ts"] = time.time() - MAX_AGE_SECONDS - 1
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        self.assertIsNone(self.cache.load("page", "latest", 1, 50))
        self.assertFalse(os.path.exists(path))

    def test_prune_enforces_a_total_byte_cap_oldest_first(self):
        import time

        for index in range(6):
            self.cache.store("page", "target-%d" % index, 1, 50,
                             {"blob": "x" * 2000})
            path = self.cache._path(
                self.cache.key("page", "target-%d" % index, 1, 50))
            stamp = time.time() - (100 - index)
            os.utime(path, (stamp, stamp))
        self.cache.prune(max_entries=100, max_bytes=5000)
        names = [name for name in os.listdir(self.tmp)
                 if name.startswith("screen-paint-")]
        total = sum(os.path.getsize(os.path.join(self.tmp, name))
                    for name in names)
        self.assertLessEqual(total, 5000)
        self.assertTrue(names)
        # The oldest entries went first.
        self.assertIsNone(self.cache.load("page", "target-0", 1, 50))
        self.assertIsNotNone(self.cache.load("page", "target-5", 1, 50))


class LiveSignatureTests(unittest.TestCase):
    """3.9.55: equal live rows must hash equal across refreshes."""

    def _row(self, **overrides):
        from raveui.controller import _EntryLike

        values = dict(
            key="live-kool", label="Kool FM",
            subtitle="Live radio · no duration", art="kool.png",
            kind="station", source="live", target="kool", hero="kool.png",
            fact="LIVE", code="RP-32", plot="Live radio · no duration",
            meta="LIVE · RP-32",
            action={"type": "play", "station": "kool", "live": True,
                    "url": "https://live.test/kool", "title": "Kool FM"})
        values.update(overrides)
        return _EntryLike(**values)

    def test_equal_entry_like_rows_sign_stably(self):
        from raveui.controller import _live_signature

        first = self._row()
        second = self._row()
        # The old fallback hashed str(row), i.e. the object address.
        self.assertNotEqual(str(first), str(second))
        self.assertEqual(_live_signature([first]), _live_signature([second]))
        self.assertNotEqual(_live_signature([first]),
                            _live_signature([self._row(fact="ON AIR")]))
        self.assertNotEqual(_live_signature([first]),
                            _live_signature([self._row(label="Rinse FM")]))

    def test_equal_plain_dict_rows_sign_stably(self):
        from raveui.controller import _live_signature

        row = {"title": "Kool FM", "fact": "LIVE", "art": "kool.png",
               "code": "RP-32", "kind": "station",
               "action": {"type": "play", "station": "kool"}}
        self.assertEqual(_live_signature([dict(row)]),
                         _live_signature([dict(row)]))


class LiveRefreshTests(unittest.TestCase):
    """3.9.55: an unchanged cached live refresh ends in SAVED LIST."""

    def setUp(self):
        from raveui.paintcache import PaintCache
        from raveui.screens.live import load_stations

        self.tmp = tempfile.mkdtemp(prefix="rave-live-paint-")
        self.cache = PaintCache(directory=self.tmp, versions="test/3.9.55")
        self.view = FakeView()
        self.data = FakeData()
        self.data.modules = None
        self.ctl, _, _, _ = controller(
            view=self.view, data=self.data, paint_cache=self.cache,
            background_task_factory=_ControllableTask)
        self.ctl.start()
        self.ctl._prefetch_cancel.set()
        self.ctl._store_live(load_stations(None))

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unchanged_live_refresh_shows_up_to_date(self):
        self.assertTrue(self.ctl._load_target("live", 1))
        self.assertEqual(self.view.status, PAINT_UPDATING)
        self.ctl._refresh["task"].finish()
        self.ctl.tick()
        self.assertEqual(self.view.status, PAINT_CURRENT)
        self.assertEqual(self.view.rows[0].label, "Kool FM")


class LazyPluginImportTests(unittest.TestCase):
    def setUp(self):
        pluginbridge.reset_cache()

    def tearDown(self):
        pluginbridge.reset_cache()

    def test_data_modules_are_not_imported_until_first_use(self):
        pluginbridge.reset_cache()
        modules = pluginbridge.load_plugin()
        self.assertNotIn("raveplayer_plugin.resources.lib.latest", sys.modules)
        self.assertNotIn("raveplayer_plugin.resources.lib.legacy", sys.modules)
        self.assertTrue(hasattr(modules.latest, "recent_packs"))
        self.assertIn("raveplayer_plugin.resources.lib.latest", sys.modules)
        self.assertNotIn("raveplayer_plugin.resources.lib.legacy", sys.modules)

    def test_concurrent_load_plugin_calls_install_one_alias(self):
        started = threading.Event()
        release = threading.Event()
        installs = []
        original = pluginbridge._install_alias

        def slow_install(alias, root):
            installs.append(alias)
            started.set()
            release.wait(2.0)
            return original(alias, root)

        results = []

        def load():
            results.append(pluginbridge.load_plugin())

        with mock.patch.object(pluginbridge, "_install_alias",
                               side_effect=slow_install):
            first = threading.Thread(target=load)
            first.start()
            self.assertTrue(started.wait(2.0))
            second = threading.Thread(target=load)
            second.start()
            # The first thread is still inside _install_alias/load_plugin, so
            # an unlocked second caller would install the alias again now.
            time.sleep(0.1)
            self.assertEqual(len(installs), 1)
            release.set()
            first.join(3.0)
            second.join(3.0)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(len(results), 2)
        self.assertIs(results[0], results[1])


class InstantBackTests(unittest.TestCase):
    def test_close_fires_home_once_when_kodi_switches(self):
        window = ravewindow.RaveScreenWindow("x.xml", "/tmp")
        calls = []
        with mock.patch.object(ravewindow.xbmc, "executebuiltin",
                               side_effect=lambda cmd: calls.append(cmd)), \
             mock.patch.object(ravewindow.xbmcgui, "getCurrentWindowId",
                               return_value=ravewindow.HOME_WINDOW_ID):
            window.close()
        self.assertEqual(calls.count("ActivateWindow(Home)"), 1)
        self.assertTrue(window.closed)

    def test_close_retries_twice_with_bounded_waits_when_home_is_refused(self):
        window = ravewindow.RaveScreenWindow("x.xml", "/tmp")
        calls = []
        waits = []
        with mock.patch.object(ravewindow.xbmc, "executebuiltin",
                               side_effect=lambda cmd: calls.append(cmd)), \
             mock.patch.object(ravewindow.xbmcgui, "getCurrentWindowId",
                               return_value=13000), \
             mock.patch.object(
                 ravewindow, "_wait_for_home",
                 side_effect=lambda initial, ms: waits.append(ms) or False):
            window.close()
        self.assertEqual(calls.count("ActivateWindow(Home)"), 3)
        self.assertEqual(waits, [ravewindow.HOME_WAIT_MS,
                                 ravewindow.HOME_FALLBACK_MS,
                                 ravewindow.HOME_RETRY_MS])
        self.assertTrue(window.closed)

    def test_close_stops_after_the_second_attempt_when_home_appears(self):
        window = ravewindow.RaveScreenWindow("x.xml", "/tmp")
        calls = []
        outcomes = iter([False, True])
        with mock.patch.object(ravewindow.xbmc, "executebuiltin",
                               side_effect=lambda cmd: calls.append(cmd)), \
             mock.patch.object(ravewindow.xbmcgui, "getCurrentWindowId",
                               return_value=13000), \
             mock.patch.object(ravewindow, "_wait_for_home",
                               side_effect=lambda initial, ms: next(outcomes)):
            window.close()
        self.assertEqual(calls.count("ActivateWindow(Home)"), 2)
        self.assertTrue(window.closed)


if __name__ == "__main__":
    unittest.main()
