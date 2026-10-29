# -*- coding: utf-8 -*-
"""Offline tests for "Play all" / "Shuffle pack" playlist building."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmc  # noqa: E402
import xbmcplugin  # noqa: E402

from resources.lib import routes  # noqa: E402

TRACKS = [
    {"title": "One", "url": "https://archive.org/download/p/1.mp3", "duration": 61},
    {"title": "Two", "url": "https://archive.org/download/p/2.mp3", "duration": None},
    {"title": "Three", "url": "https://archive.org/download/p/3.mp3", "duration": 90},
]


class PlayAllTests(unittest.TestCase):
    def setUp(self):
        del xbmc.PLAYED[:]
        del xbmcplugin.ITEMS[:]
        del xbmcplugin.CACHE_FLAGS[:]

    def _played_urls(self):
        playlist = xbmc.PLAYED[-1]
        return [url for url, _item in playlist.items]

    def test_play_all_starts_every_track(self):
        with mock.patch.object(routes.archive, "audio_files", return_value=TRACKS):
            routes.play_all(1, {"id": "p"})
        self.assertEqual(self._played_urls(), [track["url"] for track in TRACKS])

    def test_play_all_from_here_starts_at_the_selected_track(self):
        with mock.patch.object(routes.archive, "audio_files", return_value=TRACKS):
            routes.play_all(1, {"id": "p", "start": "1"})
        self.assertEqual(self._played_urls(), [TRACKS[1]["url"], TRACKS[2]["url"]])

    def test_play_all_clamps_an_out_of_range_start(self):
        with mock.patch.object(routes.archive, "audio_files", return_value=TRACKS):
            routes.play_all(1, {"id": "p", "start": "99"})
        self.assertEqual(self._played_urls(), [TRACKS[-1]["url"]])

    def test_shuffle_uses_every_track(self):
        with mock.patch.object(routes.archive, "audio_files", return_value=TRACKS), \
                mock.patch.object(routes.random, "shuffle", side_effect=lambda items: items.reverse()):
            routes.play_all(1, {"id": "p", "shuffle": "1", "start": "2"})
        self.assertEqual(self._played_urls(), [TRACKS[2]["url"], TRACKS[1]["url"], TRACKS[0]["url"]])

    def test_shuffle_zero_keeps_the_track_order(self):
        with mock.patch.object(routes.archive, "audio_files", return_value=TRACKS), \
                mock.patch.object(routes.random, "shuffle") as shuffle:
            routes.play_all(1, {"id": "p", "shuffle": "0"})
        self.assertFalse(shuffle.called)
        self.assertEqual(self._played_urls(), [track["url"] for track in TRACKS])

    def test_track_metadata_includes_duration(self):
        with mock.patch.object(routes.archive, "audio_files", return_value=TRACKS):
            routes.play_all(1, {"id": "p"})
        _url, listitem = xbmc.PLAYED[-1].items[0]
        self.assertEqual(listitem.info["music"]["title"], "One")
        self.assertEqual(listitem.info["music"]["duration"], 61)

    def test_no_tracks_notifies_and_does_not_start_playback(self):
        with mock.patch.object(routes.archive, "audio_files", return_value=[]), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.play_all(1, {"id": "p"})
        self.assertTrue(notify.called)
        self.assertEqual(xbmc.PLAYED, [])

    def test_missing_id_does_not_fetch(self):
        with mock.patch.object(routes.archive, "audio_files") as audio, \
                mock.patch.object(routes.kodi, "notify"):
            routes.play_all(1, {})
        self.assertFalse(audio.called)


if __name__ == "__main__":
    unittest.main()
