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


class FeedTests(unittest.TestCase):
    RSS = """<?xml version="1.0"?>
    <rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.0">
      <channel>
        <item>
          <title>Jungle Lab 003</title>
          <enclosure url="https://media.rss.com/a/b/003.mp3" type="audio/mpeg" length="1"/>
          <pubDate>Mon, 19 Jan 2026 11:51:21 +0000</pubDate>
          <itunes:duration>1:02:03</itunes:duration>
          <description>Deep jungle selection.</description>
        </item>
        <item>
          <title>No audio here</title>
          <description>blog post</description>
        </item>
      </channel>
    </rss>"""

    def test_parse_extracts_enclosure_episodes(self):
        import sys, os
        sys.path.insert(0, os.path.join(HERE, 'stubs'))
        from resources.lib import feeds
        episodes = feeds.parse(self.RSS)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]['title'], 'Jungle Lab 003')
        self.assertTrue(episodes[0]['url'].endswith('003.mp3'))
        self.assertEqual(episodes[0]['duration'], 3723)

    def test_parse_survives_broken_xml(self):
        import sys, os
        sys.path.insert(0, os.path.join(HERE, 'stubs'))
        from resources.lib import feeds
        self.assertEqual(feeds.parse('<rss><channel><item>'), [])

    def test_registry_entries_are_well_formed(self):
        import sys, os
        sys.path.insert(0, os.path.join(HERE, 'stubs'))
        from resources.lib import feeds
        entries = feeds.registry()
        self.assertGreaterEqual(len(entries), 3)
        for entry in entries:
            self.assertTrue(entry.get('id'))
            self.assertTrue(entry.get('name'))
            self.assertTrue(entry.get('url', '').startswith('https://'))


class DnbRadioTests(unittest.TestCase):
    RECORDINGS = '''
      <a href="/listen?mix=58125" title="2026-10-29 : DJ 4G4T - Energy Boost on DNBRADIO">
      <a href="/listen?mix=58124" title="2026-10-28 : Valis - Kief Science Session on DNBRADIO">
      <a href="/listen?mix=58125" title="2026-10-29 : DJ 4G4T - Energy Boost on DNBRADIO">
    '''

    LISTEN = '<a href="https://archive-proxy.dnbradio.com/podcasts-new/x/y.mp3?download=1&amp;z=2">'

    def test_parse_recordings_dedupes_and_splits_dates(self):
        import sys, os
        sys.path.insert(0, os.path.join(HERE, 'stubs'))
        from resources.lib import dnbradio
        shows = dnbradio.parse_recordings(self.RECORDINGS)
        self.assertEqual(len(shows), 2)
        self.assertEqual(shows[0]['id'], '58125')
        self.assertEqual(shows[0]['date'], '2026-10-29')
        self.assertEqual(shows[0]['title'], 'DJ 4G4T - Energy Boost')

    def test_parse_listen_unescapes_mp3_url(self):
        import sys, os
        sys.path.insert(0, os.path.join(HERE, 'stubs'))
        from resources.lib import dnbradio
        url = dnbradio.parse_listen(self.LISTEN)
        self.assertTrue(url.startswith('https://archive-proxy.dnbradio.com/'))
        self.assertIn('&z=2', url)

    def test_parse_listen_handles_missing_mp3(self):
        import sys, os
        sys.path.insert(0, os.path.join(HERE, 'stubs'))
        from resources.lib import dnbradio
        self.assertEqual(dnbradio.parse_listen('<html>nothing</html>'), '')
