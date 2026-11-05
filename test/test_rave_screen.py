# -*- coding: utf-8 -*-
"""Offline tests for the 3.9.47 Rave Screen script add-on.

No Kodi device, no network and no renderer: the controller is driven through a
fake view, data source and playback service; the WindowXML adapter is driven
through the stub base class.
"""

import ast
import itertools
import os
import sys
import tempfile
import types
import unittest
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
from raveui.controller import RaveScreenController  # noqa: E402
from raveui.data import Entry, RaveData, Track  # noqa: E402
from raveui.playback import PlaybackService  # noqa: E402
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

    def set_title(self, text):
        self.title = text

    def set_subtitle(self, text):
        self.subtitle = text

    def set_rows(self, rows):
        self.rows = list(rows)
        self.index = 0

    def set_hero(self, entry):
        self.hero = entry

    def set_status(self, text):
        self.status = text
        self.statuses.append(text)

    def set_now_playing(self, text):
        self.now_playing = text

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
            Entry("latest", "LATEST", "newest", "", "section"),
            Entry("toronto", "TORONTO", "tapes", "", "section"),
            Entry("surprise", "SPINNING SURPRISE", "random", "", "surprise"),
        ]
        self.loaded = []
        self.picks = 0
        self.pick = Track("Tape 1 - Brockie", "Dreamscape 19", "https://example.test/1.mp3")
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

    def random_pick(self):
        self.picks += 1
        return self.pick


class FakePlayback(object):
    def __init__(self):
        self.calls = []
        self.result = types.SimpleNamespace(text="Now playing: Track — Pack")

    def play(self, track):
        self.calls.append(track)
        return self.result


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


def controller(view=None, data=None, playback=None, **kwargs):
    view = view or FakeView()
    data = data or FakeData()
    playback = playback or FakePlayback()
    kwargs.setdefault("task_runner", DirectTaskRunner())
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
class ControllerTests(unittest.TestCase):
    def test_start_populates_home_and_selects_first_hero(self):
        ctl, view, data, _ = controller()
        rows = ctl.start()
        self.assertEqual(len(rows), 3)
        self.assertEqual(view.rows[0].label, "LATEST")
        self.assertEqual(view.hero, view.rows[0])
        self.assertEqual(view.title, "RAVE SCREEN")
        self.assertIn("OK opens", view.subtitle)

    def test_focus_updates_hero(self):
        ctl, view, _, _ = controller()
        ctl.start()
        view.index = 2
        ctl.on_focus()
        self.assertEqual(view.hero.label, "SPINNING SURPRISE")

    def test_section_load_then_back_returns_home_then_closes(self):
        ctl, view, data, _ = controller()
        ctl.start()
        view.index = 0
        self.assertTrue(ctl.on_click())
        self.assertEqual(data.loaded, [("section", "latest")])
        self.assertEqual(view.rows[0].label, "Dreamscape 19")
        self.assertEqual(ctl.stack_depth, 1)

        self.assertFalse(ctl.on_back())
        self.assertEqual(view.rows[0].label, "LATEST")
        self.assertEqual(ctl.stack_depth, 0)

        self.assertTrue(ctl.on_back())
        self.assertTrue(view.closed)
        self.assertTrue(ctl.closed)

    def test_back_while_loading_closes_once(self):
        ctl, view, _, _ = controller()
        ctl.start()
        ctl._busy = True
        self.assertTrue(ctl.on_back())
        self.assertTrue(ctl.closed)
        self.assertTrue(view.closed)
        self.assertTrue(ctl.on_back())

    def test_load_failure_keeps_the_current_view_and_reports(self):
        ctl, view, data, _ = controller()
        ctl.start()
        view.index = 0
        data.section_entries = lambda key: (_ for _ in ()).throw(RuntimeError("offline"))
        self.assertFalse(ctl.on_click())
        self.assertEqual(view.rows[0].label, "LATEST")
        self.assertIn("Could not load", view.status)
        self.assertFalse(ctl._busy)

    def test_load_timeout_is_a_status_not_a_traceback(self):
        class TimeoutRunner(object):
            def run(self, function):
                raise TaskTimeout("too slow")

        ctl, view, _, _ = controller(task_runner=TimeoutRunner())
        ctl.start()
        view.index = 0
        self.assertFalse(ctl.on_click())
        self.assertIn("Timed out", view.status)

    def test_surprise_picks_once_animates_once_and_plays_once(self):
        animator = RecordingAnimator()
        ctl, view, data, playback = controller(
            animator_factory=lambda **kwargs: animator)
        ctl.start()
        view.index = 2
        playback.result = types.SimpleNamespace(
            text="Now playing: Tape 1 - Brockie — Dreamscape 19")
        self.assertTrue(ctl.on_click())
        self.assertEqual(data.picks, 1)
        self.assertEqual(animator.ran, 1)
        self.assertEqual(len(playback.calls), 1)
        self.assertEqual(view.now_playing,
                         "Now playing: Tape 1 - Brockie — Dreamscape 19")
        self.assertFalse(view.spinner_visible)
        self.assertIn(True, view.visible_log)
        self.assertIn(False, view.visible_log)
        self.assertEqual(view.spinner_images[0], "frame-0.png")

    def test_surprise_never_repeats_on_a_second_ok(self):
        animator = RecordingAnimator()
        ctl, view, data, playback = controller(
            animator_factory=lambda **kwargs: animator)
        ctl.start()
        view.index = 2
        ctl.on_click()
        ctl.on_click()
        ctl.on_click()
        self.assertEqual(data.picks, 1)
        self.assertEqual(animator.ran, 1)
        self.assertEqual(len(playback.calls), 1)
        self.assertIn("Already playing", view.status)

    def test_surprise_no_pick_never_animates_or_plays(self):
        animator = RecordingAnimator()
        ctl, view, data, playback = controller(
            animator_factory=lambda **kwargs: animator)
        data.pick = None
        ctl.start()
        view.index = 2
        self.assertFalse(ctl.surprise())
        self.assertEqual(data.picks, 1)
        self.assertEqual(animator.ran, 0)
        self.assertEqual(playback.calls, [])
        self.assertFalse(view.spinner_visible)
        self.assertFalse(ctl._busy)

    def test_surprise_pick_exception_never_plays_and_resets_busy(self):
        ctl, view, data, playback = controller()
        data.random_pick = lambda: (_ for _ in ()).throw(RuntimeError("offline"))
        ctl.start()
        view.index = 2
        self.assertFalse(ctl.surprise())
        self.assertEqual(playback.calls, [])
        self.assertFalse(view.spinner_visible)
        self.assertFalse(ctl._busy)

    def test_surprise_animation_failure_never_plays(self):
        class BrokenAnimator(object):
            def __init__(self, **kwargs):
                pass

            def run(self):
                return False

        ctl, view, data, playback = controller(
            animator_factory=lambda **kwargs: BrokenAnimator(**kwargs))
        ctl.start()
        view.index = 2
        self.assertFalse(ctl.surprise())
        self.assertEqual(playback.calls, [])
        self.assertFalse(view.spinner_visible)

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

    def test_track_handoff_is_single_and_back_closes(self):
        ctl, view, data, playback = controller()
        ctl.start()
        view.index = 0
        ctl.on_click()
        view.index = 0
        ctl.on_click()
        view.index = 0
        self.assertTrue(ctl.on_click())
        self.assertEqual(len(playback.calls), 1)
        ctl.on_click()
        self.assertEqual(len(playback.calls), 1)
        self.assertTrue(ctl.on_back())    # playing -> Back exits directly
        self.assertTrue(view.closed)


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
            {"title": "Tape 1 - Brockie", "url": "https://archive.test/1.mp3"},
            {"title": "Tape 2 - Randall", "url": "https://archive.test/2.mp3"},
        ]),
        thumb=mock.Mock(return_value="https://archive.test/cover.jpg"),
    )
    latest = types.SimpleNamespace(
        recent_packs=mock.Mock(return_value=[
            {"identifier": "pack-1", "title": "Dreamscape 19"}]),
        random_pack=mock.Mock(return_value={
            "identifier": "pack-1", "title": "Dreamscape 19"}),
    )
    toronto = types.SimpleNamespace(
        genres=mock.Mock(return_value=[{"genre": "jungle", "label": "Jungle"}]),
        tracks=mock.Mock(return_value=[
            {"name": "Toronto Tape", "url": "https://toronto.test/a.mp3"}]),
    )
    legacy = types.SimpleNamespace(
        jungle_shows=mock.Mock(return_value=[{"key": "show-1", "name": "Show One"}]),
        jungle_tracks=mock.Mock(return_value=[
            {"name": "Rinse 1997", "url": "https://jungle.test/a.mp3"}]),
        packs=mock.Mock(return_value=[
            {"key": "Dreamscape 19", "name": "Dreamscape 19",
             "tracks": [{"name": "Tape 1", "url": "https://rtp.test/a.mp3"}]}]),
        pack=mock.Mock(return_value={
            "key": "Dreamscape 19", "name": "Dreamscape 19",
            "tracks": [{"name": "Tape 1", "url": "https://rtp.test/a.mp3"}]}),
        playable=mock.Mock(side_effect=lambda url: url + "|Referer=https://ravetapepacks.com/"),
    )
    radio = types.SimpleNamespace(
        curated=mock.Mock(side_effect=lambda token: [
            {"name": token.upper(), "url_resolved": "https://live.test/%s" % token}]),
        stations=mock.Mock(return_value=[]),
        stream_url=mock.Mock(side_effect=lambda station: station.get("url_resolved", "")),
    )
    http = types.SimpleNamespace(safe_stream_url=mock.Mock(side_effect=lambda url: url))
    return types.SimpleNamespace(
        root=ROOT, archive=archive, latest=latest, toronto=toronto, legacy=legacy,
        radio=radio, http=http, kodi=types.SimpleNamespace(), ui=types.SimpleNamespace())


class DataTests(unittest.TestCase):
    def test_home_rows_are_the_five_sources_plus_surprise(self):
        data = RaveData(modules=fake_modules(), root=ROOT, script_root=SCREEN)
        labels = [row.label for row in data.home_rows()]
        self.assertEqual(labels, [
            "LATEST", "TORONTO RAVE MIXTAPE ARCHIVE", "JUNGLETAPES.COM",
            "RAVETAPEPACKS.COM", "LIVE RADIO", "SPINNING SURPRISE",
        ])
        rows = data.home_rows()
        self.assertTrue(all(row.art for row in rows))
        self.assertTrue(rows[0].hero.endswith("fanart-latest.jpg"))
        self.assertTrue(rows[-1].hero.endswith("fanart-surprise.jpg"))

    def test_home_rows_carry_short_facts_codes_and_plots(self):
        data = RaveData(modules=fake_modules(), root=ROOT, script_root=SCREEN)
        rows = data.home_rows()
        self.assertEqual([row.fact for row in rows],
                         ["newest", "1990–2014", "cassette", "1992–2004",
                          "live", "random"])
        self.assertEqual([row.code for row in rows],
                         ["RP-01", "RP-19", "RP-27", "RP-03", "RP-31", "RP-02"])
        for row in rows:
            with self.subTest(row=row.label):
                self.assertLessEqual(len(row.fact), 16)
                self.assertTrue(row.plot)
                self.assertTrue(row.hero)

    def test_section_rows_carry_duration_count_or_source_facts(self):
        data = RaveData(modules=fake_modules(), root=ROOT, script_root=SCREEN)
        self.assertEqual(data.section_entries("latest")[0].fact, "pack")
        self.assertEqual(data.section_entries("toronto")[0].fact, "genre")
        self.assertEqual(data.section_entries("jungletapes")[0].fact, "show")
        self.assertEqual(data.section_entries("ravetapepacks")[0].fact, "1 tape")
        self.assertEqual(data.section_entries("live")[0].fact, "live")
        for key in ("latest", "toronto", "jungletapes", "ravetapepacks", "live"):
            for row in data.section_entries(key):
                self.assertLessEqual(len(row.fact), 16, (key, row.fact))
                self.assertTrue(row.plot, (key, row.label))

    def test_track_fact_prefers_the_duration_then_falls_back_to_the_source(self):
        modules = fake_modules()
        modules.archive.audio_files.return_value = [
            {"title": "Tape 1", "url": "https://archive.test/1.mp3",
             "duration": 2637}]
        data = RaveData(modules=modules, root=ROOT, script_root=SCREEN)
        parent = data.section_entries("latest")[0]
        rows = data.entries_for(parent)
        self.assertEqual(rows[0].fact, "43:57")
        self.assertEqual(rows[0].code, "RP-01")
        self.assertEqual(rows[0].plot, parent.plot)

    def test_latest_section_builds_pack_rows(self):
        data = RaveData(modules=fake_modules(), root=ROOT, script_root=SCREEN)
        rows = data.section_entries("latest")
        self.assertEqual(rows[0].kind, "pack")
        self.assertEqual(rows[0].target, "pack-1")
        data.modules.archive.audio_files.assert_not_called()

    def test_toronto_genre_children_are_track_rows(self):
        data = RaveData(modules=fake_modules(), root=ROOT, script_root=SCREEN)
        parent = data.section_entries("toronto")[0]
        rows = data.entries_for(parent)
        self.assertEqual(rows[0].kind, "track")
        self.assertEqual(rows[0].track.title, "Toronto Tape")

    def test_ravetapepacks_track_keeps_the_referer_suffix(self):
        data = RaveData(modules=fake_modules(), root=ROOT, script_root=SCREEN)
        parent = data.section_entries("ravetapepacks")[0]
        rows = data.entries_for(parent)
        self.assertIn("Referer=", rows[0].track.url)

    def test_live_rows_are_direct_playable_stations(self):
        data = RaveData(modules=fake_modules(), root=ROOT, script_root=SCREEN)
        rows = data.section_entries("live")
        self.assertTrue(rows)
        self.assertEqual(rows[0].kind, "station")
        self.assertTrue(rows[0].track.live)

    def test_random_pick_calls_each_source_once(self):
        modules = fake_modules()
        random_module = FakeRandom()
        data = RaveData(modules=modules, root=ROOT, script_root=SCREEN,
                        random_module=random_module)
        pick = data.random_pick()
        self.assertEqual(pick.pack, "Dreamscape 19")
        self.assertEqual(pick.title, "Tape 1 - Brockie")
        self.assertEqual(modules.latest.random_pack.call_count, 1)
        self.assertEqual(modules.archive.audio_files.call_count, 1)
        self.assertEqual(modules.archive.audio_files.call_args[0], ("pack-1",))
        self.assertEqual(random_module.calls, 1)

    def test_random_pick_without_pack_does_not_fetch_tracks(self):
        modules = fake_modules()
        modules.latest.random_pack.return_value = None
        data = RaveData(modules=modules, root=ROOT, script_root=SCREEN)
        self.assertIsNone(data.random_pick())
        modules.archive.audio_files.assert_not_called()

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
        self.assertEqual(root.get("version"), "3.9.48")
        imports = {item.get("addon"): item.get("version")
                   for item in root.findall("./requires/import")}
        self.assertEqual(imports.get("xbmc.python"), "3.0.0")
        self.assertEqual(imports.get("plugin.audio.raveplayer"), "3.9.48")
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

    def test_spinner_controls_start_hidden_in_the_xml(self):
        import xml.etree.ElementTree as ET

        path = os.path.join(SCREEN, "resources", "skins", "Default", "720p",
                            ravewindow.XML_FILE)
        root = ET.parse(path).getroot()
        by_id = {control.get("id"): control for control in root.iter("control")}
        for control_id in (ravewindow.CONTROL_SPINNER_BG,
                           ravewindow.CONTROL_SPINNER_HEAD,
                           ravewindow.CONTROL_SPINNER_RING,
                           ravewindow.CONTROL_SPINNER_LABEL,
                           ravewindow.CONTROL_SPINNER_HINT):
            visible = by_id[str(control_id)].findtext("visible")
            self.assertEqual(visible, "false", control_id)

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

    def test_the_adapter_does_not_override_focus(self):
        with open(os.path.join(SCREEN, "raveui", "window.py"),
                  encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("setFocusId", source)

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

    def test_footer_uses_player_bindings_and_the_waveform(self):
        self.assertEqual(by_id(self.root, 603).findtext("label"),
                         "$INFO[Player.Title]")
        self.assertEqual(by_id(self.root, 605).findtext("label"),
                         "$INFO[Player.Time]")
        self.assertEqual(by_id(self.root, 606).findtext("label"),
                         "$INFO[Player.Duration]")
        progress = by_id(self.root, 608)
        self.assertEqual(progress.get("type"), "progress")
        self.assertEqual(progress.findtext("info"), "progress")
        self.assertIn("progress-track-340x3.png", progress.findtext("texturebg"))
        self.assertIn("progress-fill-2x3.png", progress.findtext("texturemid"))
        self.assertIn("sticker-on-air.png",
                      by_id(self.root, 601).findtext("texture"))
        self.assertIn("np-wave-340x28.png",
                      by_id(self.root, 607).findtext("texture"))
        self.assertIn("keycap-ok.png",
                      by_id(self.root, 612).findtext("texture"))
        self.assertIn("keycap-b.png",
                      by_id(self.root, 614).findtext("texture"))
        # Idle footer follows the focused row; playing footer follows Player.*.
        self.assertIn("Container(50).ListItem.Label",
                      by_id(self.root, 611).findtext("label"))
        self.assertIn("Container(50).ListItem.Property(rp_meta)",
                      by_id(self.root, 616).findtext("label"))

    def test_surprise_state_matches_the_control_map(self):
        self.assertEqual(box(by_id(self.root, 700)), (0, 0, 1280, 720))
        self.assertEqual(box(by_id(self.root, 702)), (384, 36, 512, 512))
        self.assertEqual(box(by_id(self.root, 707)), (560, 648, 220, 38))
        self.assertEqual(by_id(self.root, 707).get("type"), "button")
        self.assertIn("button-focus-220x38.png",
                      by_id(self.root, 707).findtext("texturefocus"))
        self.assertIn("button-nofocus-220x38.png",
                      by_id(self.root, 707).findtext("texturenofocus"))
        self.assertEqual(by_id(self.root, 707).findtext("onclick"),
                         "Action(Back)")
        self.assertEqual(by_id(self.root, 709).findtext("label"), "CANCEL")
        self.assertIn("surprise-burst-1280x720.jpg",
                      by_id(self.root, 700).findtext("texture"))
        self.assertIn("label-surprise-me.png",
                      by_id(self.root, 704).findtext("texture"))
        self.assertIn("label-spinning-the-rack.png",
                      by_id(self.root, 705).findtext("texture"))
        for control_id in range(700, 714):
            control = by_id(self.root, control_id)
            self.assertIsNotNone(control, control_id)
            self.assertEqual(control.findtext("visible"), "false", control_id)


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
        self.view.set_title("RAVE SCREEN")
        self.view.set_subtitle("OK opens a source")
        self.assertFalse(self.window.getControl(119).visible)
        self.assertFalse(self.window.getControl(120).visible)
        self.view.set_title("LATEST")
        self.view.set_subtitle("Newest packs")
        self.assertTrue(self.window.getControl(119).visible)
        self.assertTrue(self.window.getControl(120).visible)

    def test_spinner_visibility_covers_the_whole_surprise_state(self):
        self.view.set_spinner_visible(True)
        for control_id in ravewindow.SPINNER_CONTROLS:
            self.assertTrue(self.window.getControl(control_id).visible,
                            control_id)
        self.view.set_spinner_visible(False)
        for control_id in ravewindow.SPINNER_CONTROLS:
            self.assertFalse(self.window.getControl(control_id).visible,
                             control_id)
        self.assertEqual(len(ravewindow.SPINNER_CONTROLS), 14)


class PluginIntegrationTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]

    def test_root_has_rave_screen_as_a_non_folder_program_row(self):
        from resources.lib import routes

        routes.root(1, {})
        self.assertEqual(xbmcplugin.ITEMS[0]["label"], "Rave Screen")
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
        self.assertIn('import addon="plugin.audio.raveplayer" version="3.9.48"', markup)
        self.assertIn('id="script.raveplayer.ui" name="Rave Screen" version="3.9.48"',
                      markup)
        repo_zip = os.path.join(ROOT, "repo", "script.raveplayer.ui",
                                "script.raveplayer.ui-3.9.48.zip")
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


if __name__ == "__main__":
    unittest.main()
