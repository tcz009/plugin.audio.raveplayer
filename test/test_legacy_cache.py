# -*- coding: utf-8 -*-
"""RaveTapePacks parsed-page cache (Kodi, no network, no Kodi)."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import cache, legacy  # noqa: E402


def _page(pack, track="Tape_1"):
    return '<a href="/music/%s/%s.mp3">%s</a>' % (pack, track, track)


class LegacyCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="raveplayer-legacy-cache-")
        self.old = os.environ.get(cache.CACHE_DIR_ENV)
        os.environ[cache.CACHE_DIR_ENV] = self.directory

    def tearDown(self):
        if self.old is None:
            os.environ.pop(cache.CACHE_DIR_ENV, None)
        else:
            os.environ[cache.CACHE_DIR_ENV] = self.old
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_packs_parse_once_for_the_same_body(self):
        page = _page("KodiParseOncePack")
        calls = []
        original = legacy._packs_from_html

        def counting(body):
            calls.append(body)
            return original(body)

        with mock.patch.object(legacy.http, "fetch", return_value=page), \
                mock.patch.object(legacy, "_packs_from_html", side_effect=counting):
            first = legacy.packs()
            second = legacy.packs()

        self.assertEqual([pack["key"] for pack in first], ["KodiParseOncePack"])
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)

    def test_packs_reparse_when_the_body_changes(self):
        pages = [_page("KodiBodyOne", "One"), _page("KodiBodyTwo", "Two")]
        with mock.patch.object(legacy.http, "fetch", side_effect=lambda *a, **k: pages.pop(0)):
            self.assertEqual([pack["key"] for pack in legacy.packs()], ["KodiBodyOne"])
            self.assertEqual([pack["key"] for pack in legacy.packs()], ["KodiBodyTwo"])

    def test_packs_fetch_uses_the_browser_headers(self):
        seen = []

        def fake_fetch(url, timeout=None, headers=None, ttl=0):
            seen.append((url, dict(headers or {}), ttl))
            return _page("KodiHeaderPack")

        with mock.patch.object(legacy.http, "fetch", side_effect=fake_fetch):
            legacy.packs()

        self.assertEqual(seen[0][0], legacy.BASE)
        self.assertEqual(seen[0][1].get("User-Agent"), legacy.BROWSER_UA)
        self.assertEqual(seen[0][2], legacy.PACKS_TTL)

    def test_pack_resolves_from_the_cached_index(self):
        entry = {"key": "KodiPack", "name": "Kodi Pack", "tracks": []}
        with mock.patch.object(legacy, "packs", return_value=[entry]) as packs:
            self.assertIs(legacy.pack("KodiPack"), entry)
            self.assertIsNone(legacy.pack("missing"))
            self.assertIsNone(legacy.pack(""))
        self.assertEqual(packs.call_count, 2)  # the empty key never reads the index

    def test_literal_entity_in_a_filename_is_not_decoded_twice(self):
        page = ('<a href="/music/KodiEntity/Literal_%26amp%3B_Name.mp3">x</a>'
                '<a href="/music/Kodi%20Entity/Percent_%2520_Literal.mp3">y</a>')
        with mock.patch.object(legacy.http, "fetch", return_value=page):
            packs = {pack["key"]: pack for pack in legacy.packs()}

        self.assertEqual(packs["KodiEntity"]["tracks"][0]["name"],
                         "Literal &amp; Name")
        self.assertEqual(packs["Kodi Entity"]["tracks"][0]["name"],
                         "Percent %20 Literal")


if __name__ == "__main__":
    unittest.main()
