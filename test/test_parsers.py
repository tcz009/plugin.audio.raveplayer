# -*- coding: utf-8 -*-
"""Offline unit tests for the pure parsing/formatting helpers.

No network, no Kodi: run with `python3 -m unittest discover -s test -v`.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import archive, legacy, radio  # noqa: E402


class ArchiveTests(unittest.TestCase):
    def test_pretty_strips_extension_and_underscores(self):
        self.assertEqual(archive._pretty("TAPE_1_-_DAZEE.mp3"), "TAPE 1 - DAZEE")

    def test_pretty_handles_empty(self):
        self.assertEqual(archive._pretty(""), "Untitled")

    def test_track_title_prefers_descriptive_filename(self):
        entry = {"name": "PACK/TAPE 3 - MASTERVIBE.mp3", "title": "Dreamscape XIX Arena 2"}
        self.assertEqual(archive._track_title(entry, "Dreamscape XIX Arena 2"), "TAPE 3 - MASTERVIBE")

    def test_track_title_falls_back_to_distinct_title(self):
        entry = {"name": "01.mp3", "title": "Ellis Dee - 2.4.94"}
        self.assertEqual(archive._track_title(entry, "World Dance"), "Ellis Dee - 2.4.94")

    def test_is_descriptive_rejects_generic_names(self):
        for generic in ("track01", "01", "part 2", "audio3"):
            self.assertFalse(archive._is_descriptive(generic), generic)
        self.assertTrue(archive._is_descriptive("TAPE 4 (B) - GROOVERIDER"))

    def test_rank_prefers_original_then_mp3(self):
        self.assertLess(archive._rank({"source": "original"}), archive._rank({"format": "VBR MP3"}))
        self.assertLess(archive._rank({"format": "VBR MP3"}), archive._rank({"format": "PNG"}))


class LegacyTests(unittest.TestCase):
    def test_pack_name_splits_camel_case(self):
        self.assertEqual(legacy._pack_name("GarageNation2ndBirthday"), "Garage Nation 2nd Birthday")

    def test_pack_name_spaces_volumes(self):
        self.assertEqual(legacy._pack_name("ExposureVol1"), "Exposure Vol 1")

    def test_track_pretty(self):
        self.assertEqual(legacy._pretty("Tape_1_(Side_A)_-_Swan-E"), "Tape 1 (Side A) - Swan-E")

    def test_playable_appends_referer(self):
        url = legacy.playable("https://www.ravetapepacks.com/music/X/Y.mp3")
        self.assertTrue(url.endswith("|Referer=https://www.ravetapepacks.com/&User-Agent=Mozilla/5.0"))
        self.assertIn("|", url)

    def test_jungle_label_cleans_slug(self):
        label = legacy._jt_label("tapes/20030211-rough-tough-side-b__mix")
        self.assertNotIn("/", label)
        self.assertNotIn("_", label)
        self.assertTrue(label.startswith("20030211"))


class RadioTests(unittest.TestCase):
    def test_stream_url_prefers_resolved(self):
        station = {"url": "http://fallback", "url_resolved": "http://resolved"}
        self.assertEqual(radio.stream_url(station), "http://resolved")

    def test_stream_url_falls_back(self):
        self.assertEqual(radio.stream_url({"url": "http://fallback"}), "http://fallback")

    def test_display_builds_meta(self):
        name, meta = radio.display({
            "name": " Kool FM ", "countrycode": "GB", "codec": "MP3", "bitrate": 128,
        })
        self.assertEqual(name, "Kool FM")
        self.assertEqual(meta, "GB · MP3 · 128 kbps")

    def test_display_without_meta(self):
        name, meta = radio.display({"name": "Station"})
        self.assertEqual(name, "Station")
        self.assertEqual(meta, "")


if __name__ == "__main__":
    unittest.main()
