# -*- coding: utf-8 -*-
"""Offline tests for the Live Radio screen module."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCREEN = os.path.join(ROOT, "script.raveplayer.ui")
sys.path.insert(0, SCREEN)

from raveui import nowplaying  # noqa: E402
from raveui.screens import live  # noqa: E402


KOOL = "https://admin.stream.rinse.fm/proxy/kool/stream"
RINSE = "https://admin.stream.rinse.fm/proxy/rinse_uk/stream"
CENTREFORCE = "https://listen.centreforceradio.com/96"


class FakeHttp(object):
    def safe_stream_url(self, url):
        text = str(url or "").strip()
        return text if text.startswith(("http://", "https://")) else ""


class FakeRadio(object):
    def __init__(self, urls=None, names=None):
        self.urls = dict(urls or {"kool": KOOL, "rinse": RINSE,
                                  "centreforce": CENTREFORCE})
        self.names = dict(names or {})
        self.calls = []

    def curated(self, token):
        self.calls.append(token)
        if token not in self.urls:
            return []
        return [{
            "name": self.names.get(token, {"kool": "Kool FM", "rinse": "Rinse FM",
                                           "centreforce": "Centreforce 883"}[token]),
            "url_resolved": self.urls[token],
            "countrycode": "GB",
            "codec": "MP3",
            "bitrate": 128,
        }]

    def stream_url(self, station):
        return station.get("url_resolved") or station.get("url") or ""


class FakeModules(object):
    def __init__(self, radio=None, root=None):
        self.radio = radio or FakeRadio()
        self.http = FakeHttp()
        self.root = root


class FakePlayback(object):
    def __init__(self, error=None, with_stop=True):
        self.tracks = []
        self.error = error
        self.with_stop = with_stop
        self.stop_calls = 0

    def play(self, track):
        if self.error is not None:
            raise self.error
        self.tracks.append(track)
        return type("Result", (), {"text": "Now playing: %s" % track.title})()

    def stop(self):
        if not self.with_stop:
            raise AssertionError("stop should not be called")
        self.stop_calls += 1


def make_live(**kwargs):
    modules = kwargs.pop("modules", FakeModules())
    playback = kwargs.pop("playback", FakePlayback())
    stopper = kwargs.pop("stopper", playback.stop)
    return live.LiveRadio(modules=modules, playback=playback, stopper=stopper,
                          **kwargs)


class RowProtocolTests(unittest.TestCase):
    def test_rows_have_exactly_the_library_fields(self):
        rows = make_live().rows()
        self.assertEqual(len(rows), 12)
        for row in rows:
            self.assertEqual(set(row.keys()), set(live.ROW_FIELDS))
            self.assertIsInstance(row, dict)
            self.assertEqual(row.title, row["title"])
            self.assertEqual(row.kind, row["kind"])
            self.assertIsInstance(row.action, dict)
        self.assertEqual([row.kind for row in rows],
                         ["station"] * 5 + ["section"] +
                         ["section"] * 6)
        self.assertEqual(rows[0].fact, "LIVE")
        self.assertEqual(rows[5].title, "Pirate Radio")
        self.assertEqual(rows[5].fact, "PIRATE")
        self.assertEqual(rows[5].action,
                         {"type": "open", "source": "pirate", "target": "pirate"})
        self.assertEqual([row.title for row in rows[6:]],
                         ["Hardcore", "Jungle", "Drum & Bass", "House",
                          "UK Garage", "Dubstep & Grime"])
        self.assertTrue(all(row.action["source"] == "live_tag"
                            for row in rows[6:]))

    def test_rows_are_json_serialisable_and_copyable(self):
        row = make_live().rows()[0]
        import json
        self.assertEqual(json.loads(json.dumps(row))["title"], "Kool FM")
        clone = row.copy()
        clone["fact"] = "X"
        self.assertEqual(row.fact, "LIVE")

    def test_station_metadata_and_codes(self):
        rows = make_live().rows()
        self.assertEqual([row.title for row in rows[:5]],
                         ["Kool FM", "Rinse FM", "Centreforce 883",
                          "DejaVu FM", "OSA Radio"])
        self.assertEqual([row.code for row in rows],
                         ["RP-32", "RP-33", "RP-34", "RP-45", "RP-46",
                          "RP-35", "RP-36", "RP-37", "RP-38", "RP-39",
                          "RP-40", "RP-41"])
        self.assertEqual(rows[0].action["url"], KOOL)
        self.assertTrue(rows[0].action["live"])

    def test_default_stations_work_without_a_plugin(self):
        radio = live.LiveRadio()
        rows = radio.rows()
        self.assertEqual([row.title for row in rows[:3]],
                         ["Kool FM", "Rinse FM", "Centreforce 883"])
        self.assertEqual([station.url for station in radio.stations],
                         [KOOL, RINSE, CENTREFORCE,
                          "https://dejavufm.radioca.st/stream",
                          "https://osa.radioca.st/stream"])

    def test_plugin_urls_win_and_unsafe_urls_fall_back(self):
        plugin = FakeRadio(urls={"kool": "https://example.test/kool",
                                 "rinse": "file:///etc/passwd",
                                 "centreforce": CENTREFORCE})
        radio = live.LiveRadio(modules=FakeModules(radio=plugin))
        self.assertEqual(radio.stations[0].url, "https://example.test/kool")
        self.assertEqual(radio.stations[1].url, RINSE)  # unsafe -> canonical
        self.assertEqual(radio.stations[1].token, "rinse")

    def test_plugin_names_update_display(self):
        plugin = FakeRadio(names={"centreforce": "Centreforce 88.3"})
        radio = live.LiveRadio(modules=FakeModules(radio=plugin))
        self.assertEqual(radio.stations[2].name, "Centreforce 88.3")

    def test_art_resolves_under_the_plugin_art_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = os.path.join(tmp, "resources", "art")
            os.makedirs(directory)
            for name in ("kool.png", "rinse.png", "centreforce.png",
                         "dejavu.png", "osa.png", "pirate-radio.png"):
                with open(os.path.join(directory, name), "wb") as handle:
                    handle.write(b"png")
            radio = live.LiveRadio(modules=FakeModules(root=tmp))
            rows = radio.rows()
            self.assertEqual(rows[0].art,
                             os.path.join(directory, "kool.png"))
            self.assertTrue(rows[5].art.endswith("pirate-radio.png"))
            self.assertTrue(rows[-1].art.endswith("radio-dubstep-grime.png"))

    def test_missing_art_keeps_a_portable_filename(self):
        rows = make_live(art_root="/nonexistent").rows()
        self.assertEqual(rows[0].art, "kool.png")


class PlayStopTests(unittest.TestCase):
    def test_play_calls_the_player_once_with_a_live_track(self):
        playback = FakePlayback()
        radio = make_live(playback=playback)
        self.assertTrue(radio.play("kool"))
        self.assertEqual(len(playback.tracks), 1)
        track = playback.tracks[0]
        self.assertEqual(track.title, "Kool FM")
        self.assertEqual(track.url, KOOL)
        self.assertEqual(track.pack, "Live radio")
        self.assertTrue(track.live)
        self.assertEqual(track.station, "kool")
        self.assertEqual(radio.on_air, "kool")
        self.assertIn("ON AIR", radio.status)

    def test_row_flips_to_on_air_and_action_becomes_stop(self):
        radio = make_live()
        radio.play("rinse")
        rows = radio.rows()
        self.assertEqual(rows[1].fact, "ON AIR")
        self.assertEqual(rows[1].action["type"], "stop")
        self.assertEqual(rows[1].action["station"], "rinse")
        self.assertEqual(rows[0].fact, "LIVE")

    def test_playing_the_same_station_never_double_plays(self):
        playback = FakePlayback()
        radio = make_live(playback=playback)
        self.assertTrue(radio.play("kool"))
        self.assertFalse(radio.play("kool"))
        self.assertEqual(len(playback.tracks), 1)
        self.assertIn("Already on air", radio.status)

    def test_switching_stations_makes_one_new_call_and_idles_the_old_row(self):
        playback = FakePlayback()
        radio = make_live(playback=playback)
        radio.play("kool")
        self.assertTrue(radio.play("rinse"))
        self.assertEqual(len(playback.tracks), 2)
        self.assertEqual(playback.stop_calls, 0)
        rows = radio.rows()
        self.assertEqual(rows[0].fact, "LIVE")
        self.assertEqual(rows[1].fact, "ON AIR")
        self.assertEqual(radio.state("kool").mode, "idle")

    def test_stop_calls_the_stopper_once_and_returns_to_standby(self):
        playback = FakePlayback()
        radio = make_live(playback=playback)
        radio.play("kool")
        self.assertTrue(radio.stop())
        self.assertEqual(playback.stop_calls, 1)
        self.assertEqual(radio.on_air, "")
        self.assertEqual(radio.status, "STANDBY")
        self.assertEqual(radio.rows()[0].fact, "LIVE")
        self.assertFalse(radio.stop())  # nothing on air -> no second call
        self.assertEqual(playback.stop_calls, 1)

    def test_stop_without_a_stopper_is_reported_without_lying(self):
        playback = FakePlayback(with_stop=False)
        radio = make_live(playback=playback, stopper=None)
        radio.play("kool")
        self.assertFalse(radio.stop())
        self.assertEqual(radio.on_air, "kool")

    def test_toggle_and_perform(self):
        playback = FakePlayback()
        radio = make_live(playback=playback)
        self.assertTrue(radio.perform(radio.action("kool")))
        self.assertTrue(radio.perform(radio.action("kool")))  # stop
        self.assertEqual(len(playback.tracks), 1)
        self.assertEqual(playback.stop_calls, 1)
        self.assertFalse(radio.perform({"type": "open", "target": "pirate"}))
        self.assertFalse(radio.perform(None))
        self.assertTrue(radio.toggle("kool"))
        self.assertTrue(radio.toggle("kool"))
        self.assertEqual(len(playback.tracks), 2)

    def test_missing_or_failing_playback_never_leaves_on_air(self):
        radio = live.LiveRadio(playback=None)
        self.assertFalse(radio.play("kool"))
        self.assertEqual(radio.on_air, "")
        broken = make_live(playback=FakePlayback(error=RuntimeError("dead stream")))
        self.assertFalse(broken.play("kool"))
        self.assertEqual(broken.on_air, "")
        self.assertIn("Could not start", broken.status)

    def test_unknown_station(self):
        playback = FakePlayback()
        radio = make_live(playback=playback)
        self.assertFalse(radio.play("does-not-exist"))
        self.assertFalse(radio.toggle("does-not-exist"))
        self.assertEqual(playback.tracks, [])

    def test_pause_clears_on_air_without_touching_playback(self):
        playback = FakePlayback()
        radio = make_live(playback=playback)
        radio.play("kool")
        self.assertTrue(radio.set_paused(True))
        self.assertEqual(radio.state("kool").mode, "paused")
        self.assertFalse(radio.state("kool").on_air)
        self.assertEqual(radio.rows()[0].fact, "PAUSED")
        self.assertEqual(radio.action("kool")["type"], "play")  # resume
        footer = radio.footer()
        self.assertTrue(footer.paused)
        self.assertFalse(footer.on_air)
        self.assertTrue(radio.set_paused(False))
        self.assertTrue(radio.footer().on_air)
        self.assertEqual(len(playback.tracks), 1)
        self.assertFalse(live.LiveRadio().set_paused(True))


class NowPlayingTests(unittest.TestCase):
    def test_live_state_never_exposes_duration_or_progress(self):
        radio = make_live()
        radio.play("kool")
        state = radio.state("kool")
        self.assertTrue(state.on_air)
        self.assertTrue(state.is_live)
        self.assertFalse(state.has_duration)
        self.assertFalse(state.has_progress)
        self.assertIsNone(state.duration)
        self.assertIsNone(state.elapsed)
        self.assertIsNone(state.progress)
        self.assertEqual(state.title, "Kool FM")

    def test_icy_metadata_is_split_for_the_footer(self):
        radio = make_live(now_playing=lambda token: "Randall - Dreamscape 1994")
        radio.play("kool")
        metadata = radio.now_playing()
        self.assertEqual(metadata["title"], "Dreamscape 1994")
        self.assertEqual(metadata["artist"], "Randall")
        self.assertEqual(metadata["stream_title"], "Randall - Dreamscape 1994")
        self.assertIsNone(metadata["duration"])
        footer = radio.footer()
        self.assertEqual(footer.title, "Dreamscape 1994")
        self.assertEqual(footer.meta, "Randall")
        self.assertEqual(footer.mode, nowplaying.LIVE)
        self.assertFalse(footer.show_duration)
        self.assertFalse(footer.show_progress)

    def test_metadata_dict_probe(self):
        radio = make_live(now_playing=lambda token: {
            "title": "Atlantis", "artist": "LTJ Bukem", "meta": "Kool FM"})
        radio.play("kool")
        metadata = radio.now_playing()
        self.assertEqual((metadata["artist"], metadata["title"]),
                         ("LTJ Bukem", "Atlantis"))
        self.assertEqual(metadata["meta"], "Kool FM")

    def test_idle_footer_is_standby(self):
        footer = make_live().footer()
        self.assertTrue(footer.idle)
        self.assertEqual(footer.kicker, "STANDBY")
        self.assertEqual(footer.room, "Live Radio")

    def test_probe_failure_does_not_break_the_footer(self):
        def broken(token):
            raise RuntimeError("ICY timeout")
        radio = make_live(now_playing=broken)
        radio.play("kool")
        footer = radio.footer()
        self.assertEqual(footer.title, "Kool FM")
        self.assertTrue(footer.on_air)

    def test_metadata_is_not_invented_for_an_idle_station(self):
        radio = make_live(now_playing=lambda token: "Artist - Title")
        metadata = radio.now_playing("kool")
        self.assertEqual(metadata["title"], "Kool FM")
        self.assertFalse(metadata["on_air"])
        self.assertFalse(metadata["has_duration"])


class HelpersTests(unittest.TestCase):
    def test_playable_rows(self):
        rows = make_live().rows()
        playable = live.playable_rows(rows)
        self.assertEqual(len(playable), 5)
        self.assertEqual(live.playable_rows(None), [])

    def test_station_lookup_by_name_and_token(self):
        radio = make_live()
        self.assertEqual(radio.station("KOOL").token, "kool")  # noqa: N802
        self.assertEqual(radio.station("Rinse FM").token, "rinse")
        self.assertIsNone(radio.station("nope"))


if __name__ == "__main__":
    unittest.main()
