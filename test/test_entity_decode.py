# -*- coding: utf-8 -*-
"""Scraped titles must render as text, never as HTML entities.

Feeds and scrapers regularly double-encode an entity: a title that should read
``A & B – C`` arrives as ``A &amp;amp; B &amp;#x2013; C``.  These fixtures pin
the decoded output for Toronto, Moxser, Hardscore and the RSS/Atom parser.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import feeds, hardscore, moxser, toronto  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures", "entities")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return handle.read()


def assert_plain(test, value):
    test.assertIn("&", value)
    test.assertIn("\u2013", value)
    for entity in ("&amp;", "&#x2013;", "&quot;", "&#8211;"):
        test.assertNotIn(entity, value)


class EntityDecodeTests(unittest.TestCase):
    def test_toronto_title(self):
        rows = toronto.parse_tracks(fixture("toronto.html"))
        self.assertEqual(len(rows), 1)
        assert_plain(self, rows[0]["name"])
        self.assertEqual(rows[0]["name"], "Brockie & DJ Rap \u2013 Jungle Mania")

    def test_moxser_title(self):
        rows = moxser._parse_mixes_sitemap(fixture("moxser_sitemap.xml"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Alpha Show & Guest \u2013 26 October 2026")
        assert_plain(self, rows[0]["title"])

    def test_hardscore_title(self):
        rows = hardscore.parse_feed(fixture("hardscore.xml"))
        self.assertEqual(len(rows), 1)
        assert_plain(self, rows[0]["title"])
        self.assertEqual(rows[0]["title"],
                         "Force of One Crew & MC \u2013 Weekend Rush [June 1993]")

    def test_feed_title_and_description(self):
        episodes = feeds.parse(fixture("feed.xml"))
        self.assertEqual(len(episodes), 1)
        title = episodes[0]["title"]
        assert_plain(self, title)
        self.assertEqual(title, 'Skream & Benga \u2013 FWD "Rinse" 20.11.2009')
        self.assertIn("Live & direct \u2013 two hours",
                      episodes[0]["description"])


if __name__ == "__main__":
    unittest.main()
