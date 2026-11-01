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

    def test_item_title_normalises_lists_and_missing_metadata(self):
        with mock.patch.object(archive, "item", return_value={"metadata": {"title": ["World", "Dance"]}}):
            self.assertEqual(archive.item_title("pack"), "World Dance")
        with mock.patch.object(archive, "item", return_value={}):
            self.assertEqual(archive.item_title("pack"), "")


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


class ArchiveUrlSafetyTests(unittest.TestCase):
    """Archive metadata is third-party input: never let it escape the item path."""

    def test_traversing_filenames_are_dropped(self):
        files = [
            {"name": "../../evil.mp3", "source": "original", "format": "VBR MP3"},
            {"name": "/abs/evil.mp3", "source": "original", "format": "VBR MP3"},
            {"name": "a/../b.mp3", "source": "original", "format": "VBR MP3"},
            {"name": "a\\b.mp3", "source": "original", "format": "VBR MP3"},
            {"name": "a//b.mp3", "source": "original", "format": "VBR MP3"},
            {"name": "disc/../evil.mp3", "source": "original", "format": "VBR MP3"},
            {"name": "disc/Track One.mp3", "source": "original", "format": "VBR MP3"},
        ]
        with mock.patch.object(archive, "item", return_value={"files": files}):
            tracks = archive.audio_files("pack")
        self.assertEqual([track["name"] for track in tracks], ["disc/Track One.mp3"])
        self.assertEqual(tracks[0]["url"],
                         "https://archive.org/download/pack/disc/Track%20One.mp3")

    def test_control_characters_in_filenames_are_dropped(self):
        files = [{"name": "bad\x01.mp3", "source": "original"}, {"name": "ok.mp3"}]
        with mock.patch.object(archive, "item", return_value={"files": files}):
            tracks = archive.audio_files("pack")
        self.assertEqual([track["name"] for track in tracks], ["ok.mp3"])

    def test_valid_direct_storage_base_is_used(self):
        base = archive._direct_base({"dir": "/27/items/pack", "d1": "ia801234.us.archive.org"})
        self.assertEqual(base, "https://ia801234.us.archive.org/27/items/pack/")
        spaced = archive._direct_base({"dir": "/dir with space", "server": "ia1.us.archive.org"})
        self.assertEqual(spaced, "https://ia1.us.archive.org/dir%20with%20space/")

    def test_hostile_storage_nodes_and_dirs_are_rejected(self):
        for payload in (
            {"dir": "/27/items/../../evil", "d1": "ia1.us.archive.org"},
            {"dir": "/27/items", "d1": "evil.example.com:8080"},
            {"dir": "/27/items", "d1": "evil.example.com/x"},
            {"dir": "/27/items?x=1", "d1": "ia1.us.archive.org"},
            {"dir": "/27/items#frag", "d1": "ia1.us.archive.org"},
            {"dir": "/27/it\x01ems", "d1": "ia1.us.archive.org"},
            {"dir": "/27/items", "d1": "bad host"},
            {"dir": "", "d1": "ia1.us.archive.org"},
        ):
            self.assertEqual(archive._direct_base(payload), "", payload)

    def test_invalid_storage_node_falls_back_to_download_url(self):
        payload = {
            "metadata": {"title": "Pack"},
            "dir": "/27/items/pack",
            "d1": "evil.example.com:8080",
            "files": [{"name": "Track One.mp3", "source": "original"}],
        }
        with mock.patch.object(archive, "item", return_value=payload):
            tracks = archive.audio_files("pack")
        self.assertTrue(tracks[0]["url"].startswith("https://archive.org/download/pack/"))

    def test_infinite_durations_and_sizes_do_not_raise(self):
        for value in (float("inf"), float("-inf"), "Infinity", "inf", "1e400", "1e999"):
            self.assertIsNone(archive._duration(value), value)
        self.assertEqual(archive._as_int(float("inf")), 0)
        # Very long digit strings must not escape as a traceback either.
        archive._duration("1:" + "9" * 6000)


if __name__ == "__main__":
    unittest.main()
