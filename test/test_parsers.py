# -*- coding: utf-8 -*-
"""Offline unit tests for the pure parsing/formatting helpers.

No network, no Kodi: run with `python3 -m unittest discover -s test -v`.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import archive, cache, dnbradio, feeds, legacy, radio  # noqa: E402


class ArchiveTests(unittest.TestCase):
    def test_pretty_strips_extension_and_underscores(self):
        self.assertEqual(archive._pretty("TAPE_1_-_DAZEE.mp3"), "TAPE 1 - DAZEE")

    def test_pretty_handles_empty(self):
        self.assertEqual(archive._pretty(""), "Untitled")
        self.assertEqual(archive._pretty(None), "Untitled")
        self.assertEqual(archive._pretty("/"), "Untitled")

    def test_pretty_handles_paths_and_non_strings(self):
        self.assertEqual(archive._pretty("pack/disc/01.mp3"), "01")
        self.assertEqual(archive._pretty(123), "123")

    def test_track_title_prefers_descriptive_filename(self):
        entry = {"name": "PACK/TAPE 3 - MASTERVIBE.mp3", "title": "Dreamscape XIX Arena 2"}
        self.assertEqual(archive._track_title(entry, "Dreamscape XIX Arena 2"), "TAPE 3 - MASTERVIBE")

    def test_track_title_falls_back_to_distinct_title(self):
        entry = {"name": "01.mp3", "title": "Ellis Dee - 2.4.94"}
        self.assertEqual(archive._track_title(entry, "World Dance"), "Ellis Dee - 2.4.94")

    def test_track_title_handles_list_titles(self):
        entry = {"name": "01.mp3", "title": ["Ellis Dee", "World Dance"]}
        self.assertEqual(archive._track_title(entry, "World Dance"), "Ellis Dee World Dance")

    def test_is_descriptive_rejects_generic_names(self):
        for generic in ("track01", "01", "part 2", "audio3"):
            self.assertFalse(archive._is_descriptive(generic), generic)
        self.assertTrue(archive._is_descriptive("TAPE 4 (B) - GROOVERIDER"))

    def test_rank_prefers_original_then_mp3(self):
        self.assertLess(archive._rank({"source": "original"}), archive._rank({"format": "VBR MP3"}))
        self.assertLess(archive._rank({"format": "VBR MP3"}), archive._rank({"format": "PNG"}))

    def test_rank_tolerates_missing_or_null_format(self):
        self.assertEqual(archive._rank({}), 2)
        self.assertEqual(archive._rank({"format": None}), 2)

    def test_thumb_quotes_identifier(self):
        self.assertEqual(
            archive.thumb("a b/c"),
            "https://archive.org/services/img/a%20b%2Fc",
        )

    def test_search_returns_empty_on_malformed_payloads(self):
        payloads = [
            None,
            [],
            {"response": None},
            {"response": {"docs": None, "numFound": "not-a-number"}},
            {"response": {"docs": "nope", "numFound": None}},
        ]
        for payload in payloads:
            with mock.patch.object(archive.http, "fetch_json", return_value=payload):
                self.assertEqual(archive.search("x"), ([], 0), payload)

    def test_search_filters_non_dict_docs_and_clamps_total(self):
        payload = {"response": {"docs": [{"identifier": "ok"}, "bad"], "numFound": -4}}
        with mock.patch.object(archive.http, "fetch_json", return_value=payload):
            docs, total = archive.search("x")
        self.assertEqual(docs, [{"identifier": "ok"}])
        self.assertEqual(total, 0)

    def test_audio_files_skips_bad_entries_and_quotes_urls(self):
        payload = {
            "metadata": {"title": "Pack"},
            "files": [
                {"name": "disc/Track One.mp3", "format": None, "source": "original", "size": "10"},
                {"name": None, "format": "MP3"},
                {"format": "MP3"},
                {"name": "disc/Track Two.mp3", "format": "VBR MP3"},
                "not a dict",
            ],
        }
        with mock.patch.object(archive, "item", return_value=payload):
            tracks = archive.audio_files("an id")
        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[0]["url"], "https://archive.org/download/an%20id/disc/Track%20One.mp3")
        self.assertEqual(tracks[0]["title"], "Track One")
        self.assertEqual(tracks[0]["size"], 10)

    def test_audio_files_tolerates_non_list_files(self):
        with mock.patch.object(archive, "item", return_value={"files": None}):
            self.assertEqual(archive.audio_files("x"), [])


class LegacyTests(unittest.TestCase):
    def test_pack_name_splits_camel_case(self):
        self.assertEqual(legacy._pack_name("GarageNation2ndBirthday"), "Garage Nation 2nd Birthday")

    def test_pack_name_spaces_volumes(self):
        self.assertEqual(legacy._pack_name("ExposureVol1"), "Exposure Vol 1")

    def test_pack_name_unquotes_and_unescapes(self):
        self.assertEqual(legacy._pack_name("Swan%20E%20%26%20Friends"), "Swan E & Friends")

    def test_track_pretty(self):
        self.assertEqual(legacy._pretty("Tape_1_(Side_A)_-_Swan-E"), "Tape 1 (Side A) - Swan-E")

    def test_track_pretty_unescapes_html_entities(self):
        self.assertEqual(legacy._pretty("Wolf_%26amp%3B_Tranzit"), "Wolf & Tranzit")

    def test_playable_appends_referer(self):
        url = legacy.playable("https://www.ravetapepacks.com/music/X/Y.mp3")
        self.assertTrue(url.endswith("|Referer=https://www.ravetapepacks.com/&User-Agent=Mozilla/5.0"))
        self.assertIn("|", url)

    def test_jungle_label_cleans_slug(self):
        label = legacy._jt_label("tapes/20030211-rough-tough-side-b__mix")
        self.assertNotIn("/", label)
        self.assertNotIn("_", label)
        self.assertTrue(label.startswith("20030211"))

    def test_packs_groups_and_builds_encoded_urls(self):
        page = (
            '<a href="/music/HelterSkelter/Tape 1 (Side A) - Swan-E.mp3">one</a>'
            '<a href="/music/HelterSkelter/Tape_2.mp3">two</a>'
        )
        with mock.patch.object(legacy.http, "fetch", return_value=page):
            packs = legacy.packs()
        self.assertEqual(len(packs), 1)
        self.assertEqual(packs[0]["key"], "HelterSkelter")
        self.assertEqual(packs[0]["name"], "Helter Skelter")
        self.assertEqual(len(packs[0]["tracks"]), 2)
        self.assertIn("Tape%201%20%28Side%20A%29", packs[0]["tracks"][0]["url"])

    def test_jungle_shows_uses_sitemap_and_dedupes(self):
        sitemap = (
            "<urlset><url><loc>https://jungletapes.com/show/alpha</loc></url>"
            "<url><loc>https://jungletapes.com/show/alpha</loc></url>"
            "<url><loc>https://jungletapes.com/show/beta</loc></url></urlset>"
        )
        with mock.patch.object(legacy.http, "fetch", return_value=sitemap):
            shows = legacy.jungle_shows()
        self.assertEqual([show["key"] for show in shows], ["beta", "alpha"])

    def test_jungle_shows_falls_back_to_front_page(self):
        page = '<a href="/show/gamma" class="x">Gamma</a><a href="/show/delta">Delta</a>'
        with mock.patch.object(legacy.http, "fetch", side_effect=["", page]):
            shows = legacy.jungle_shows()
        self.assertEqual([show["key"] for show in shows], ["gamma", "delta"])

    def test_jungle_tracks_resolves_relative_and_protocol_urls(self):
        page = (
            '<a href="//cdn.example.com/a%20b.mp3">one</a>'
            '<a href="/sites/default/files/c.mp3">two</a>'
        )
        with mock.patch.object(legacy.http, "fetch", return_value=page):
            tracks = legacy.jungle_tracks("show")
        self.assertEqual(tracks[0]["url"], "https://cdn.example.com/a%20b.mp3")
        self.assertEqual(tracks[0]["name"], "a b")
        self.assertEqual(tracks[1]["url"], "https://jungletapes.com/sites/default/files/c.mp3")

    def test_toronto_tracks_unescapes_entities_before_quoting(self):
        page = '<a href="/files/mixtape/Wolf &amp; Tranzit - Live.mp3">x</a>'
        with mock.patch.object(legacy.http, "fetch", return_value=page):
            tracks = legacy.toronto_tracks()
        self.assertEqual(tracks[0]["name"], "Wolf & Tranzit - Live")
        self.assertIn("Wolf%20%26%20Tranzit%20-%20Live.mp3", tracks[0]["url"])
        self.assertNotIn("amp;", tracks[0]["url"])


class RadioTests(unittest.TestCase):
    def test_stream_url_prefers_resolved(self):
        station = {"url": "http://fallback", "url_resolved": "http://resolved"}
        self.assertEqual(radio.stream_url(station), "http://resolved")

    def test_stream_url_falls_back(self):
        self.assertEqual(radio.stream_url({"url": "http://fallback"}), "http://fallback")

    def test_stream_url_rejects_non_dict(self):
        self.assertEqual(radio.stream_url("http://nope"), "")

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

    def test_display_ignores_zero_or_invalid_bitrate(self):
        self.assertEqual(radio.display({"name": "A", "bitrate": "0"})[1], "")
        self.assertEqual(radio.display({"name": "A", "bitrate": "fast"})[1], "")

    def test_stations_filters_bad_entries_and_tries_next_mirror(self):
        first = None
        second = [{"name": "A", "url": "http://a"}, "bad", {"name": "B"}]
        with mock.patch.object(radio.http, "fetch_json", side_effect=[first, second]):
            stations = radio.stations("jungle")
        self.assertEqual([station["name"] for station in stations], ["A"])

    def test_stations_tries_next_mirror_after_empty_list(self):
        with mock.patch.object(radio.http, "fetch_json", side_effect=[[], [{"url": "http://a"}]]) as fetch:
            self.assertEqual(len(radio.stations("jungle")), 1)
        self.assertEqual(fetch.call_count, 2)


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

    ATOM = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Atom Mix</title>
        <link rel="enclosure" type="audio/mpeg" href="https://example.test/a.mp3?x=1&amp;y=2"/>
        <updated>2026-01-19T11:51:21Z</updated>
        <summary>Atom description.</summary>
      </entry>
    </feed>"""

    def test_parse_extracts_enclosure_episodes(self):
        episodes = feeds.parse(self.RSS)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["title"], "Jungle Lab 003")
        self.assertTrue(episodes[0]["url"].endswith("003.mp3"))
        self.assertEqual(episodes[0]["duration"], 3723)

    def test_parse_survives_broken_xml(self):
        self.assertEqual(feeds.parse("<rss><channel><item>"), [])
        self.assertEqual(feeds.parse(None), [])

    def test_parse_supports_atom_entries(self):
        episodes = feeds.parse(self.ATOM)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["title"], "Atom Mix")
        self.assertEqual(episodes[0]["url"], "https://example.test/a.mp3?x=1&y=2")
        self.assertEqual(episodes[0]["published"], "2026-01-19T11:51:21Z")
        self.assertEqual(episodes[0]["description"], "Atom description.")

    def test_parse_decodes_xml_entities_once(self):
        xml = (
            '<rss><channel><item><title>A &amp; B</title>'
            '<enclosure url="https://example.test/a.mp3?x=1&amp;y=2"/>'
            "</item></channel></rss>"
        )
        episodes = feeds.parse(xml)
        self.assertEqual(episodes[0]["title"], "A & B")
        self.assertEqual(episodes[0]["url"], "https://example.test/a.mp3?x=1&y=2")

    def test_duration_handles_fractional_and_invalid_values(self):
        self.assertEqual(feeds._duration(_item_with_duration("1:02:03.500")), 3723)
        self.assertEqual(feeds._duration(_item_with_duration("3723.9")), 3723)
        self.assertIsNone(feeds._duration(_item_with_duration("soon")))
        self.assertIsNone(feeds._duration(_item_with_duration("")))

    def test_text_joins_nested_elements(self):
        import xml.etree.ElementTree as ET
        node = ET.fromstring("<item><title>Hello <b>World</b></title></item>")
        self.assertEqual(feeds._text(node, "title"), "Hello World")

    def test_registry_entries_are_well_formed(self):
        entries = feeds.registry()
        self.assertGreaterEqual(len(entries), 3)
        for entry in entries:
            self.assertTrue(entry.get("id"))
            self.assertTrue(entry.get("name"))
            self.assertTrue(entry.get("url", "").startswith("https://"))

    def test_unknown_feed_is_none(self):
        self.assertIsNone(feeds.feed("does-not-exist"))


class FeedCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="raveplayer-feed-test-")
        self.old = os.environ.get(cache.CACHE_DIR_ENV)
        os.environ[cache.CACHE_DIR_ENV] = self.directory

    def tearDown(self):
        if self.old is None:
            os.environ.pop(cache.CACHE_DIR_ENV, None)
        else:
            os.environ[cache.CACHE_DIR_ENV] = self.old
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_episodes_are_fetched_once(self):
        entry = {"id": "test", "name": "Test", "url": "https://example.test/feed.xml", "plot": ""}
        with mock.patch.object(feeds, "feed", return_value=entry), \
                mock.patch.object(feeds.http, "_request", return_value=FeedTests.RSS) as fetch:
            self.assertEqual(len(feeds.episodes("test")), 1)
            self.assertEqual(len(feeds.episodes("test")), 1)
        self.assertEqual(fetch.call_count, 1)


class DnbRadioTests(unittest.TestCase):
    RECORDINGS = '''
      <a href="/listen?mix=58125" title="2026-10-29 : DJ 4G4T - Energy Boost on DNBRADIO">
      <a href="/listen?mix=58124" title="2026-10-28 : Valis - Kief Science Session on DNBRADIO">
      <a href="/listen?mix=58125" title="2026-10-29 : DJ 4G4T - Energy Boost on DNBRADIO">
    '''

    LISTEN = '<a href="https://archive-proxy.dnbradio.com/podcasts-new/x/y.mp3?download=1&amp;z=2">'

    def test_parse_recordings_dedupes_and_splits_dates(self):
        shows = dnbradio.parse_recordings(self.RECORDINGS)
        self.assertEqual(len(shows), 2)
        self.assertEqual(shows[0]["id"], "58125")
        self.assertEqual(shows[0]["date"], "2026-10-29")
        self.assertEqual(shows[0]["title"], "DJ 4G4T - Energy Boost")

    def test_parse_recordings_unescapes_titles(self):
        shows = dnbradio.parse_recordings(
            '<a href="/listen?mix=1" title="2026-01-01 : A &amp; B on DNBRADIO">'
        )
        self.assertEqual(shows[0]["title"], "A & B")

    def test_parse_listen_unescapes_mp3_url(self):
        url = dnbradio.parse_listen(self.LISTEN)
        self.assertTrue(url.startswith("https://archive-proxy.dnbradio.com/"))
        self.assertIn("&z=2", url)
        self.assertNotIn("amp;", url)

    def test_parse_listen_handles_missing_mp3(self):
        self.assertEqual(dnbradio.parse_listen("<html>nothing</html>"), "")

    def test_link_quotes_mix_ids(self):
        self.assertTrue(dnbradio.link("12 3").endswith("mix=12%203"))


def _item_with_duration(value):
    import xml.etree.ElementTree as ET
    node = ET.fromstring("<item/>")
    duration = ET.SubElement(node, "{http://www.itunes.com/dtds/podcast-1.0.0}duration")
    duration.text = value
    return node


if __name__ == "__main__":
    unittest.main()
