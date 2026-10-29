# -*- coding: utf-8 -*-
"""Offline tests for Archive audio-file selection and durations."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import archive  # noqa: E402


class AudioFileTests(unittest.TestCase):
    def _files(self, files):
        with mock.patch.object(archive, "item", return_value={"metadata": {"title": "Pack"}, "files": files}):
            return archive.audio_files("pack")

    def test_derivative_ogg_is_not_a_second_track(self):
        tracks = self._files([
            {"name": "Show A.mp3", "source": "original", "format": "VBR MP3", "length": "100.5"},
            {"name": "Show A.ogg", "source": "derivative", "format": "Ogg Vorbis", "length": "100.4"},
            {"name": "Show B.mp3", "source": "original", "format": "VBR MP3", "length": "200"},
        ])
        self.assertEqual([track["title"] for track in tracks], ["Show A", "Show B"])
        self.assertTrue(all(track["url"].endswith(".mp3") for track in tracks))

    def test_original_wins_over_derivative_with_the_same_stem(self):
        tracks = self._files([
            {"name": "Set.mp3", "source": "derivative", "format": "VBR MP3"},
            {"name": "Set.flac", "source": "original", "format": "FLAC"},
        ])
        self.assertEqual(len(tracks), 1)
        self.assertTrue(tracks[0]["url"].endswith(".flac"))

    def test_same_stem_in_different_folders_is_kept(self):
        tracks = self._files([
            {"name": "Tape 1/01.mp3", "source": "original", "format": "VBR MP3"},
            {"name": "Tape 2/01.mp3", "source": "original", "format": "VBR MP3"},
        ])
        self.assertEqual(len(tracks), 2)
        self.assertIn("Tape%201/01.mp3", tracks[0]["url"])
        self.assertIn("Tape%202/01.mp3", tracks[1]["url"])

    def test_tracks_are_ranked_then_named(self):
        tracks = self._files([
            {"name": "b.mp3", "source": "derivative", "format": "VBR MP3"},
            {"name": "z.flac", "source": "original", "format": "FLAC"},
            {"name": "a.wav", "source": "original", "format": "WAVE"},
        ])
        self.assertEqual([track["name"] for track in tracks], ["a.wav", "z.flac", "b.mp3"])

    def test_duration_is_parsed_from_archive_lengths(self):
        self.assertEqual(archive._duration("1872.46"), 1872)
        self.assertEqual(archive._duration(65), 65)
        self.assertEqual(archive._duration("1:02:03"), 3723)
        self.assertEqual(archive._duration("00:02:30"), 150)
        self.assertIsNone(archive._duration(""))
        self.assertIsNone(archive._duration(None))
        self.assertIsNone(archive._duration("0"))
        self.assertIsNone(archive._duration("soon"))

    def test_track_duration_is_returned(self):
        tracks = self._files([
            {"name": "A.mp3", "source": "original", "format": "VBR MP3", "length": "61.9"},
        ])
        self.assertEqual(tracks[0]["duration"], 61)


class SearchBoundsTests(unittest.TestCase):
    def test_rows_and_page_are_clamped(self):
        seen = {}

        def fetch(url, **kwargs):
            seen["url"] = url
            return {"response": {"docs": [], "numFound": 0}}

        with mock.patch.object(archive.http, "fetch_json", side_effect=fetch):
            archive.search("x", page=0, rows=100000)
        self.assertIn("rows=500", seen["url"])
        self.assertIn("page=1", seen["url"])

    def test_invalid_rows_falls_back(self):
        seen = {}
        with mock.patch.object(archive.http, "fetch_json",
                               side_effect=lambda url, **kw: seen.update(url=url) or {}):
            archive.search("x", rows="nope")
        self.assertIn("rows=50", seen["url"])


if __name__ == "__main__":
    unittest.main()
