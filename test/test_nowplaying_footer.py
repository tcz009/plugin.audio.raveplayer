# -*- coding: utf-8 -*-
"""Offline tests for the footer / now-playing model (Live Radio screen)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCREEN = os.path.join(ROOT, "script.raveplayer.ui")
sys.path.insert(0, SCREEN)

from raveui import nowplaying  # noqa: E402


class StandbyTests(unittest.TestCase):
    def test_idle_is_standby_with_no_media(self):
        footer = nowplaying.standby()
        self.assertTrue(footer.idle)
        self.assertFalse(footer.has_media)
        self.assertFalse(footer.on_air)
        self.assertEqual(footer.kicker, "STANDBY")
        self.assertEqual(footer.title, "NOTHING PLAYING")
        self.assertEqual(footer.meta, "PICK A ROOM · PRESS OK")
        self.assertFalse(footer.show_duration)
        self.assertFalse(footer.show_progress)
        self.assertIsNone(footer.progress)
        self.assertEqual(footer.duration, "")
        self.assertFalse(nowplaying.is_on_air(footer))

    def test_focused_room_replaces_the_hint(self):
        footer = nowplaying.standby(room="Live Radio", fact="live")
        self.assertEqual(footer.meta, "Live Radio · live")
        self.assertEqual(footer.room, "Live Radio")
        self.assertEqual(footer.fact, "live")

    def test_count_is_plural_aware(self):
        self.assertIn("1 ROOM", nowplaying.standby(count=1).meta)
        self.assertIn("4 ROOMS", nowplaying.standby(count=4).meta)


class PlayingTests(unittest.TestCase):
    def test_playing_track_has_total_elapsed_and_progress(self):
        footer = nowplaying.playing(
            "Tape 1 - Brockie", artist="Brockie", album="Dreamscape 19",
            duration=2637, elapsed=1204)
        self.assertEqual(footer.mode, nowplaying.PLAYING)
        self.assertTrue(footer.on_air)
        self.assertEqual(footer.kicker, "NOW PLAYING")
        self.assertEqual(footer.title, "Tape 1 - Brockie")
        self.assertEqual(footer.meta, "Brockie · Dreamscape 19")
        self.assertEqual(footer.elapsed, "20:04")
        self.assertEqual(footer.duration, "43:57")
        self.assertTrue(footer.show_duration)
        self.assertTrue(footer.show_progress)
        self.assertAlmostEqual(footer.progress, 1204 / 2637.0, places=4)

    def test_progress_is_clamped_and_survives_bad_values(self):
        footer = nowplaying.playing("A", duration=100, elapsed=999)
        self.assertEqual(footer.progress, 1.0)
        self.assertEqual(footer.elapsed, "1:40")
        bad = nowplaying.playing("A", duration="oops", elapsed=None)
        self.assertIsNone(bad.progress)
        self.assertFalse(bad.show_progress)
        self.assertFalse(bad.show_duration)

    def test_hours_and_unicode_separators(self):
        self.assertEqual(nowplaying.format_clock(3723), "1:02:03")
        self.assertEqual(nowplaying.split_artist_title("Vinylgroover - Dreamscape XII"),
                         ("Vinylgroover", "Dreamscape XII"))
        self.assertEqual(nowplaying.split_artist_title("LTJ Bukem – Atlantis"),
                         ("LTJ Bukem", "Atlantis"))
        self.assertEqual(nowplaying.split_artist_title("Just A Title"),
                         ("", "Just A Title"))
        self.assertEqual(nowplaying.split_artist_title(""), ("", ""))

    def test_title_and_meta_are_clipped(self):
        footer = nowplaying.playing("x" * 100, artist="a" * 100, album="b" * 100)
        self.assertLessEqual(len(footer.title), 48)
        self.assertLessEqual(len(footer.meta), 64)
        self.assertTrue(footer.title.endswith("…"))


class PausedTests(unittest.TestCase):
    def test_paused_clears_on_air_but_keeps_metadata(self):
        footer = nowplaying.playing("Tape 1", artist="Brockie",
                                    duration=100, elapsed=50, paused=True)
        self.assertEqual(footer.mode, nowplaying.PAUSED)
        self.assertTrue(footer.paused)
        self.assertFalse(footer.on_air)
        self.assertEqual(footer.kicker, "PAUSED")
        self.assertEqual(footer.title, "Tape 1")
        self.assertEqual(footer.duration, "1:40")
        self.assertFalse(nowplaying.is_on_air(footer))

    def test_pause_and_resume_are_pure(self):
        playing = nowplaying.playing("Tape 1", duration=100, elapsed=50)
        paused = nowplaying.pause(playing)
        resumed = nowplaying.resume(paused)
        self.assertFalse(playing.paused)
        self.assertTrue(paused.paused)
        self.assertFalse(resumed.paused)
        self.assertTrue(resumed.on_air)
        self.assertEqual(resumed.mode, nowplaying.PLAYING)
        self.assertFalse(nowplaying.pause(nowplaying.standby()).paused)

    def test_live_paused_resumes_live_not_as_a_track(self):
        footer = nowplaying.playing("Kool FM", live=True, paused=True)
        self.assertTrue(footer.media_live)
        self.assertFalse(footer.on_air)
        resumed = nowplaying.resume(footer)
        self.assertEqual(resumed.mode, nowplaying.LIVE)
        self.assertTrue(resumed.on_air)
        self.assertFalse(resumed.show_duration)


class LiveTests(unittest.TestCase):
    def test_live_hides_duration_elapsed_and_progress(self):
        footer = nowplaying.playing("Kool FM", artist="DJ Hype",
                                    duration=3600, elapsed=1800, live=True)
        self.assertEqual(footer.mode, nowplaying.LIVE)
        self.assertTrue(footer.on_air)
        self.assertTrue(footer.media_live)
        self.assertEqual(footer.kicker, "ON AIR")
        self.assertEqual(footer.duration, "")
        self.assertEqual(footer.elapsed, "")
        self.assertIsNone(footer.progress)
        self.assertFalse(footer.show_duration)
        self.assertFalse(footer.show_progress)
        self.assertEqual(footer.status_line(), "ON AIR · Kool FM")

    def test_live_factory_and_station_footer(self):
        footer = nowplaying.live("Rinse FM", artist="DJ Flight")
        self.assertTrue(footer.live)
        self.assertEqual(footer.meta, "DJ Flight")
        another = nowplaying.for_station(
            "Kool FM", is_playing=True, stream_title="Randall - Dreamscape 1994")
        self.assertEqual(another.title, "Dreamscape 1994")
        self.assertEqual(another.meta, "Randall")
        idle = nowplaying.for_station("Kool FM", is_playing=False)
        self.assertTrue(idle.idle)
        self.assertEqual(idle.meta, "Kool FM · LIVE RADIO")


class FromPlayerTests(unittest.TestCase):
    def test_kodi_time_dicts_and_percentage(self):
        footer = nowplaying.from_player({
            "title": "Tape 1 - Brockie",
            "artist": ["Brockie"],
            "album": "Dreamscape 19",
            "time": {"hours": 0, "minutes": 20, "seconds": 4},
            "totaltime": {"hours": 0, "minutes": 43, "seconds": 57},
            "percentage": 45.7,
            "speed": 1,
            "playing": True,
        })
        self.assertEqual(footer.mode, nowplaying.PLAYING)
        self.assertEqual(footer.elapsed, "20:04")
        self.assertEqual(footer.duration, "43:57")
        self.assertAlmostEqual(footer.progress, 0.457, places=3)

    def test_paused_from_speed(self):
        footer = nowplaying.from_player({
            "title": "Tape 1", "duration": 100, "elapsed": 50, "speed": 0,
        })
        self.assertEqual(footer.mode, nowplaying.PAUSED)
        self.assertFalse(footer.on_air)

    def test_live_hint_wins_even_with_a_duration(self):
        footer = nowplaying.from_player({
            "title": "Kool FM", "duration": 3600, "elapsed": 1800,
            "is_live": True, "speed": 1,
        })
        self.assertEqual(footer.mode, nowplaying.LIVE)
        self.assertFalse(footer.show_duration)
        explicit = nowplaying.from_player({"title": "Kool FM", "duration": 30},
                                          live=True)
        self.assertEqual(explicit.mode, nowplaying.LIVE)

    def test_missing_duration_is_not_guessed_live(self):
        footer = nowplaying.from_player({"title": "Unknown tape", "speed": 1})
        self.assertEqual(footer.mode, nowplaying.PLAYING)
        self.assertFalse(footer.show_duration)
        self.assertFalse(footer.media_live)

    def test_not_playing_is_idle(self):
        footer = nowplaying.from_player({"title": "Tape 1", "playing": False,
                                         "speed": 1})
        self.assertTrue(footer.idle)


class PropertiesTests(unittest.TestCase):
    def test_window_properties_are_string_flags(self):
        props = nowplaying.playing("Tape 1", duration=100,
                                   elapsed=25).properties()
        self.assertEqual(props["rp_now_on_air"], "1")
        self.assertEqual(props["rp_now_show_progress"], "1")
        self.assertEqual(props["rp_now_progress"], "25")
        self.assertEqual(props["rp_now_duration"], "1:40")
        idle = nowplaying.standby().properties()
        self.assertEqual(idle["rp_now_show_progress"], "0")
        self.assertEqual(idle["rp_now_on_air"], "0")
        self.assertEqual(idle["rp_now_progress"], "")

    def test_status_line_for_idle_and_playing(self):
        self.assertEqual(nowplaying.standby().status_line(),
                         "PICK A ROOM · PRESS OK")
        self.assertEqual(
            nowplaying.playing("Tape 1", artist="Brockie").status_line(),
            "NOW PLAYING · Tape 1 · Brockie")


if __name__ == "__main__":
    unittest.main()
