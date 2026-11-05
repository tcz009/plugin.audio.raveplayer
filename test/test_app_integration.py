# -*- coding: utf-8 -*-
"""Integration tests for the full-screen app shell.

These tests drive the real screen modules through the real controller:

* Search/Favourites/Downloads/About route to ``raveui.screens.library``;
* Live Radio routes to ``raveui.screens.live``;
* library Rows and live dicts are adopted by one normalisation;
* the footer is ``raveui.nowplaying.Footer`` for idle/playing/paused/live;
* Spinning Surprise uses one ``raveui.surprise_pick`` policy and one play gate;
* Back pops the shell's own stack after content changes.

No Kodi, no network, no renderer.
"""

import os
import sys
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCREEN = os.path.join(ROOT, "script.raveplayer.ui")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)
sys.path.insert(0, SCREEN)

from raveui import nowplaying  # noqa: E402
from raveui.controller import RaveScreenController  # noqa: E402
from raveui.data import Entry, Page, Track  # noqa: E402
from raveui.screens.library import (LibraryScreens, Row as LibraryRow)  # noqa: E402
from raveui.screens.live import LiveRadio, Row as LiveRow  # noqa: E402
from raveui.surprise_pick import PackCache, PickedTrack, SurprisePicker  # noqa: E402
from raveui.tasks import DirectTaskRunner  # noqa: E402


# --------------------------------------------------------------------- fakes
class FakeView(object):
    def __init__(self):
        self.rows = []
        self.index = 0
        self.title = ""
        self.subtitle = ""
        self.hero = None
        self.status = ""
        self.now_playing = ""
        self.footer = None
        self.footers = []
        self.page_info = ""
        self.key_hints = ("", "")
        self.live = False
        self.plate = None
        self.spinner_visible = False
        self.spinner_images = []
        self.spinner_label = ""
        self.closed = False
        self.closed_calls = 0

    def set_title(self, text):
        self.title = text

    def set_subtitle(self, text):
        self.subtitle = text

    def set_rows(self, rows, selected=0):
        self.rows = list(rows)
        self.index = int(selected or 0)

    def set_room_count(self, count, unit="ROOMS"):
        self.room_count = (count, unit)

    def set_hero(self, entry):
        self.hero = entry

    def set_status(self, text):
        self.status = text

    def set_now_playing(self, text):
        self.now_playing = text

    def set_footer(self, footer):
        self.footer = footer
        self.footers.append(footer)

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
        pass

    def selected_index(self):
        return self.index

    def set_spinner_visible(self, visible):
        self.spinner_visible = bool(visible)

    def set_spinner_image(self, path):
        self.spinner_images.append(path)

    def set_spinner_label(self, text):
        self.spinner_label = text

    def close(self):
        self.closed = True
        self.closed_calls += 1


class IntegrationData(object):
    """Shell-owned rooms only: home, Latest, a pack and the pirate door."""

    def __init__(self):
        self.loaded = []
        self.pack_rows = [Entry(
            "tape-1", "Tape 1", "Dreamscape 19", "", "track", "latest",
            "https://example.test/one.mp3",
            Track("Tape 1", "Dreamscape 19", "https://example.test/one.mp3"),
            downloadable=True)]
        self.modules = types.SimpleNamespace(
            latest=types.SimpleNamespace(
                RAVE_COLLECTION="collection:ravetapes AND mediatype:audio",
                random_pack=mock.Mock(return_value={
                    "identifier": "pack-1", "title": "Dreamscape 19"}),
                recent_packs=mock.Mock(return_value=[
                    {"identifier": "pack-1", "title": "Dreamscape 19"}])),
            archive=types.SimpleNamespace(
                audio_files=mock.Mock(return_value=[
                    {"title": "Tape 1 - Brockie",
                     "url": "https://archive.test/one.mp3"}]),
                thumb=mock.Mock(return_value="")),
            http=types.SimpleNamespace(
                safe_stream_url=mock.Mock(side_effect=lambda url: url)),
            radio=types.SimpleNamespace(
                curated=mock.Mock(side_effect=lambda token: [
                    {"name": {"kool": "Kool FM", "rinse": "Rinse FM",
                              "centreforce": "Centreforce 883"}[token],
                     "url_resolved": "https://live.test/%s" % token}]),
                stream_url=mock.Mock(
                    side_effect=lambda station: station.get("url_resolved", ""))),
            handoff=types.SimpleNamespace(
                target=mock.Mock(return_value="plugin://plugin.audio.mixcloud/?x=1")),
            root=ROOT,
        )
        self.frames = ["frame-0.png", "frame-1.png"]

    def home_rows(self):
        return [
            Entry("latest", "Latest", "newest", "", "section", target="latest"),
            Entry("live", "Live Radio", "live", "", "section", target="live"),
            Entry("search", "Search", "find", "", "search", target="search"),
            Entry("favourites", "Favourites", "saved", "", "section",
                  target="favourites"),
            Entry("downloads", "Downloads", "offline", "", "section",
                  target="downloads"),
            Entry("about", "About", "credits", "", "section", target="about"),
            Entry("surprise", "Spinning Surprise", "random", "", "surprise"),
        ]

    def load(self, target, page=1, rows=50):
        if target is None:
            home = self.home_rows()
            return Page(home, len(home), 1, 1, rows)
        if isinstance(target, str):
            self.loaded.append(("room", target))
            return Page(list(self.pack_rows), 1, 1, 1, rows)
        self.loaded.append(("children", target.key))
        return Page(list(self.pack_rows), 1, 1, 1, rows)

    def spinner_frames(self):
        return list(self.frames)


class FakePlayback(object):
    def __init__(self):
        self.calls = []
        self.collections = []
        self.stop_calls = 0
        self.playing = False
        self.result = types.SimpleNamespace(text="Now playing: Tape 1")

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


class FakeBackend(object):
    """Library backend double: every room is one small ready list."""

    def __init__(self):
        self.searches = []

    def scope(self):
        return "collection:ravetapes AND mediatype:audio"

    def page_size(self):
        return 50

    def search(self, query, page, rows):
        self.searches.append(query)
        if "nothing" in query.lower():
            return [], 0
        return ([{"identifier": "found-1", "title": "Found Pack"},
                 {"identifier": "found-2", "title": "Other Pack"}], 2)

    def archive_thumb(self, identifier):
        return ""

    def art(self, name):
        return ""

    def favourites(self):
        return [{"kind": "pack", "target": "pack-1",
                 "title": "Saved Pack", "source": "Archive.org"}]

    def favourite_key(self, entry):
        return "%s:%s" % (entry.get("kind"), entry.get("target"))

    def favourite_has(self, entry):
        return False

    def favourite_add(self, entry):
        return True

    def favourite_remove(self, key):
        return True

    def downloads(self):
        return [{"key": "dl-1", "title": "Saved File", "source": "Archive.org",
                 "path": "/tmp/saved.mp3", "exists": True, "size": 1024,
                 "added": "2026-11-05T10:00:00Z"}]

    def download_plan(self, url, title, source):
        return {"allowed": False, "reason": "not in this test"}

    def download(self, plan, progress=None, cancelled=None):
        return {"ok": False, "reason": "not in this test"}

    def download_delete(self, key):
        return True

    def playable_url(self, url):
        return url

    def platform_kind(self, url):
        return ""

    def about(self):
        return {"name": "Rave Player", "version": "3.9.51",
                "screen_version": "3.9.50", "kodi_version": "22.0",
                "licence": "GPL-3.0-or-later",
                "links": (), "sources": ()}


# --------------------------------------------------------------------- setup
def build(library=True, live=True, surprise_picker=None, data=None,
          player_snapshot=None, **extra):
    view = FakeView()
    data = data or IntegrationData()
    playback = FakePlayback()
    kwargs = dict(task_runner=DirectTaskRunner(), logger=lambda message: None,
                  surprise_sleep=lambda seconds: None,
                  player_snapshot=player_snapshot)
    if library:
        kwargs["library"] = LibraryScreens(backend=FakeBackend(), playback=None)
    if live:
        kwargs["live"] = LiveRadio(modules=data.modules, playback=None,
                                   stopper=lambda: playback.stop(), art_root=ROOT)
    if surprise_picker is not None:
        kwargs["surprise_picker"] = surprise_picker
    kwargs.update(extra)
    controller = RaveScreenController(view, data, playback, **kwargs)
    return controller, view, data, playback


def row_index(view, label):
    for index, row in enumerate(view.rows):
        if row.label == label:
            return index
    raise AssertionError("row %r not in %r" % (label, [r.label for r in view.rows]))


# --------------------------------------------------------------------- tests
class RoutingTests(unittest.TestCase):
    def test_favourites_downloads_and_about_route_through_library(self):
        ctl, view, _, _ = build()
        ctl.start()

        view.index = row_index(view, "Favourites")
        self.assertTrue(ctl.on_click())
        self.assertEqual(view.title, "FAVOURITES")
        self.assertEqual(view.rows[0].label, "Saved Pack")
        self.assertEqual(view.rows[0].kind, "library_room")
        self.assertEqual(view.rows[0].payload["mode"], "archive_item")

        self.assertFalse(ctl.on_back())
        self.assertEqual(view.rows[0].label, "Latest")

        view.index = row_index(view, "Downloads")
        self.assertTrue(ctl.on_click())
        self.assertEqual(view.title, "DOWNLOADS")
        self.assertEqual(view.rows[0].label, "Saved File")
        self.assertEqual(view.rows[0].kind, "library_track")
        self.assertTrue(view.rows[0].payload["local"])

        self.assertFalse(ctl.on_back())
        view.index = row_index(view, "About")
        self.assertTrue(ctl.on_click())
        self.assertEqual(view.title, "ABOUT")
        self.assertIn("Rave Player", [row.label for row in view.rows])

    def test_search_uses_the_library_scope_and_normalises_results(self):
        ctl, view, _, _ = build()
        ctl.start()
        view.index = row_index(view, "Search")
        self.assertTrue(ctl.on_click())
        self.assertEqual(ctl.view_kind, "keyboard")
        ctl._keyboard["query"] = "dreamscape"
        view.index = 7                    # SEARCH NOW
        self.assertTrue(ctl.on_click())
        self.assertEqual(view.title, "SEARCH")
        self.assertEqual(view.rows[0].label, "Found Pack")
        self.assertEqual(view.rows[0].kind, "library_room")
        self.assertEqual(view.rows[0].payload["identifier"], "found-1")
        self.assertIn("collection:ravetapes", ctl._library_ui.backend.searches[0])
        # Results -> keyboard (query kept) -> home.
        self.assertFalse(ctl.on_back())
        self.assertEqual(ctl.view_kind, "keyboard")
        self.assertEqual(ctl.search_query, "dreamscape")
        self.assertFalse(ctl.on_back())
        self.assertEqual(view.rows[0].label, "Latest")

    def test_search_empty_keeps_the_retry_row_from_the_module(self):
        ctl, view, _, _ = build()
        ctl.start()
        view.index = row_index(view, "Search")
        ctl.on_click()
        ctl._keyboard["query"] = "nothing"
        view.index = 7
        self.assertFalse(ctl.on_click())
        self.assertEqual(view.rows[0].kind, "library_action")
        self.assertEqual(view.rows[0].action, "retry")
        self.assertEqual(view.rows[0].payload["route"], "search")
        self.assertIn("No matching packs", view.status)

    def test_library_room_payload_opens_the_shell_pack_route(self):
        ctl, view, data, _ = build()
        ctl.start()
        view.index = row_index(view, "Favourites")
        ctl.on_click()
        view.index = 0                       # Saved Pack (legacy room)
        self.assertTrue(ctl.on_click())
        self.assertEqual(data.loaded[-1], ("children", "pack-1"))
        self.assertEqual(view.rows[0].label, "Tape 1")


class LiveRoutingTests(unittest.TestCase):
    def test_live_uses_module_rows_and_paints_the_on_air_footer(self):
        ctl, view, _, playback = build()
        ctl.start()
        view.index = row_index(view, "Live Radio")
        self.assertTrue(ctl.on_click())
        self.assertEqual(view.title, "LIVE RADIO")
        self.assertEqual([row.label for row in view.rows],
                         ["Kool FM", "Rinse FM", "Centreforce 883",
                          "Pirate Radio"])
        self.assertTrue(all(row.kind in ("station", "section")
                            for row in view.rows))
        self.assertTrue(all(isinstance(row.action, dict) for row in view.rows))

        view.index = 0
        self.assertTrue(ctl.on_click())
        self.assertEqual(len(playback.calls), 1)
        self.assertTrue(playback.calls[0].live)
        self.assertTrue(view.footer.live)
        self.assertTrue(view.footer.on_air)
        self.assertFalse(view.footer.show_duration)
        self.assertFalse(view.footer.show_progress)
        self.assertEqual(view.rows[0].fact, "ON AIR")

        # OK on the same station stops it; one stop, no second play.
        view.index = 0
        self.assertTrue(ctl.on_click())
        self.assertEqual(playback.stop_calls, 1)
        self.assertEqual(len(playback.calls), 1)
        self.assertFalse(view.footer.on_air)
        self.assertEqual(view.rows[0].fact, "LIVE")

    def test_live_pause_hides_on_air_but_keeps_the_title(self):
        snapshot = {"title": "Kool FM", "playing": True, "paused": True}
        ctl, view, _, playback = build(player_snapshot=lambda: snapshot)
        ctl.start()
        view.index = row_index(view, "Live Radio")
        ctl.on_click()
        view.index = 0
        ctl.on_click()
        ctl._footer_at = None
        ctl.tick()
        self.assertEqual(view.footer.mode, "paused")
        self.assertFalse(view.footer.on_air)
        self.assertIn("Kool FM", view.footer.title)
        self.assertEqual(view.rows[0].fact, "PAUSED")

    def test_live_pirate_door_opens_the_shell_pirate_room(self):
        ctl, view, data, _ = build()
        ctl.start()
        view.index = row_index(view, "Live Radio")
        ctl.on_click()
        view.index = row_index(view, "Pirate Radio")
        self.assertTrue(ctl.on_click())
        self.assertEqual(data.loaded[-1], ("children", "pirate_source"))


class NormalisationTests(unittest.TestCase):
    def test_one_normalisation_adopts_library_rows_and_live_dicts(self):
        ctl, view, _, _ = build()
        library_row = LibraryRow(
            label="Saved Set", kind="track", fact="Archive.org",
            icon="icon.png", fanart="hero.jpg", code="RP-34",
            payload={"action": "play", "url": "https://example.test/a.mp3",
                     "title": "Saved Set", "favourite_key": "k1"},
            subtitle="Saved stream", plot="Saved")
        adopted = ctl._adopt_row(library_row)
        self.assertEqual(adopted.kind, "library_track")
        self.assertEqual(adopted.label, "Saved Set")
        self.assertEqual(adopted.art, "icon.png")
        self.assertEqual(adopted.hero, "hero.jpg")
        self.assertEqual(adopted.action, "play")
        self.assertEqual(adopted.payload["favourite_key"], "k1")

        live_row = LiveRow(title="Kool FM", fact="ON AIR", art="kool.png",
                           code="RP-32", kind="station",
                           action={"type": "stop", "station": "kool"})
        adopted = ctl._adopt_row(live_row)
        self.assertEqual(adopted.kind, "station")
        self.assertEqual(adopted.label, "Kool FM")
        self.assertEqual(adopted.action, {"type": "stop", "station": "kool"})
        self.assertEqual(adopted.target, "kool")
        self.assertEqual(adopted.subtitle, "Live radio · no duration")

        entry = Entry("shell", "Shell Row", "sub", "", "section", target="latest")
        self.assertIs(ctl._adopt_row(entry), entry)


class FooterTests(unittest.TestCase):
    def test_idle_footer_follows_the_focused_room(self):
        ctl, view, _, _ = build()
        ctl.start()
        self.assertEqual(view.footer.mode, "idle")
        self.assertEqual(view.footer.room, "Latest")
        view.index = row_index(view, "Favourites")
        ctl.on_focus()
        self.assertEqual(view.footer.room, "Favourites")

    def test_playing_and_paused_footer_come_from_the_model(self):
        snapshot = {"title": "Tape 1", "artist": "Brockie",
                    "album": "Dreamscape 19", "elapsed": 120,
                    "duration": 240, "playing": True, "paused": False}
        ctl, view, _, playback = build(player_snapshot=lambda: snapshot)
        ctl.start()
        view.index = row_index(view, "Latest")
        ctl.on_click()                 # Latest room
        view.index = 0
        ctl.on_click()                 # pack -> track list
        view.index = 0
        self.assertTrue(ctl.on_click())  # play
        ctl._footer_at = None
        ctl.tick()
        self.assertEqual(view.footer.mode, "playing")
        self.assertTrue(view.footer.on_air)
        self.assertTrue(view.footer.show_duration)

        self.assertEqual(view.footer.elapsed, "2:00")
        self.assertEqual(view.footer.duration, "4:00")
        self.assertEqual(view.footer.progress, 0.5)

        snapshot["paused"] = True
        ctl._footer_at = None
        ctl.tick()
        self.assertEqual(view.footer.mode, "paused")
        self.assertFalse(view.footer.on_air)
        self.assertEqual(view.footer.title, "Tape 1")

    def test_live_footer_hides_duration_even_if_kodi_reports_it(self):
        ctl, view, _, _ = build()
        ctl.start()
        view.index = row_index(view, "Live Radio")
        ctl.on_click()
        view.index = 0
        ctl.on_click()
        footer = view.footer
        self.assertEqual(footer.kicker, "ON AIR")
        self.assertEqual(footer.elapsed, "")
        self.assertEqual(footer.duration, "")
        self.assertIsNone(footer.progress)
        self.assertFalse(footer.show_duration)
        self.assertFalse(footer.show_progress)


class SurpriseTests(unittest.TestCase):
    def test_controller_shares_the_latest_seeded_cache(self):
        ctl, _, data, _ = build()
        self.assertIs(ctl._surprise_cache, data.surprise_cache)

    def test_one_pick_policy_retries_three_times_then_plays_once(self):
        data = IntegrationData()
        data.modules.latest.random_pack = mock.Mock(
            side_effect=[None, None, {"identifier": "pack-1",
                                      "title": "Dreamscape 19"}])
        animator = RecordingAnimator()
        ctl, view, _, playback = build(
            data=data, animator_factory=lambda **kwargs: animator)
        ctl.start()
        self.assertTrue(ctl.surprise(True))
        self.assertEqual(data.modules.latest.random_pack.call_count, 3)
        self.assertEqual(animator.ran, 1)
        self.assertEqual(len(playback.calls), 1)
        self.assertTrue(ctl._surprise_picker.guard.fired)

        # Same gesture: the one-shot guard refuses a second playback.
        self.assertFalse(ctl.surprise(True))
        self.assertEqual(len(playback.calls), 1)

        # A new gesture resets the guard.
        with mock.patch("raveui.controller.threading.Thread") as thread:
            self.assertTrue(ctl._start_surprise())
            self.assertTrue(thread.called)
        self.assertFalse(ctl._surprise_picker.guard.fired)

    def test_surprise_failure_after_exhaustion_shows_one_clear_plate(self):
        picker = SurprisePicker(pick=lambda: None, sleep=lambda seconds: None)
        ctl, view, _, playback = build(surprise_picker=picker)
        ctl.start()
        self.assertFalse(ctl.surprise(True))
        self.assertEqual(picker.attempts, 3)
        self.assertEqual(picker.last_result.attempts, 3)
        self.assertEqual(playback.calls, [])
        self.assertEqual(ctl.plate, "error")
        self.assertEqual(view.plate[1], "NO PACK FOUND")
        self.assertIn("No random pack found", view.plate[2])

    def test_cancelled_pick_does_not_paint_a_failure(self):
        picker = SurprisePicker(
            pick=lambda: {"identifier": "pack-1", "title": "Pack"},
            resolve=lambda identifier: PickedTrack(
                "Tape", "https://example.test/a.mp3", identifier, "Pack"),
            sleep=lambda seconds: None,
            should_stop=lambda: True)
        ctl, view, _, playback = build(surprise_picker=picker)
        ctl.start()
        self.assertFalse(ctl.surprise(True))
        self.assertIsNone(view.plate)
        self.assertEqual(playback.calls, [])


class ContextTests(unittest.TestCase):
    def test_context_on_a_library_track_offers_play_and_remove(self):
        ctl, view, _, playback = build()
        ctl.start()
        view.index = row_index(view, "Downloads")
        ctl.on_click()
        view.index = 0                        # Saved File (library track)
        self.assertTrue(ctl.on_context())
        labels = [row.label for row in view.rows]
        self.assertIn("Play", labels)
        self.assertIn("Remove", labels)
        self.assertIn("Play all", labels)
        view.index = labels.index("Play")
        self.assertTrue(ctl.on_click())
        self.assertEqual(len(playback.calls), 1)

    def test_context_on_a_live_station_uses_the_module_action(self):
        ctl, view, _, playback = build()
        ctl.start()
        view.index = row_index(view, "Live Radio")
        ctl.on_click()
        view.index = 0
        self.assertTrue(ctl.on_context())
        self.assertIn("Play / stop", [row.label for row in view.rows])
        view.index = 0
        self.assertTrue(ctl.on_click())
        self.assertEqual(len(playback.calls), 1)
        self.assertTrue(view.footer.live)


class BackStackTests(unittest.TestCase):
    def test_back_pops_library_and_live_rooms_without_losing_focus(self):
        ctl, view, _, _ = build()
        ctl.start()
        view.index = row_index(view, "Favourites")
        ctl.on_click()
        self.assertFalse(ctl.on_back())
        self.assertEqual(view.rows[view.index].label, "Favourites")
        self.assertEqual(view.rows[0].label, "Latest")

        view.index = row_index(view, "Live Radio")
        ctl.on_click()
        self.assertEqual(view.rows[0].label, "Kool FM")
        self.assertFalse(ctl.on_back())
        self.assertEqual(view.rows[view.index].label, "Live Radio")
        self.assertFalse(view.closed)

    def test_back_from_home_still_closes_once(self):
        ctl, view, _, _ = build()
        ctl.start()
        self.assertTrue(ctl.on_back())
        self.assertTrue(view.closed)
        self.assertEqual(view.closed_calls, 1)


if __name__ == "__main__":
    unittest.main()
