# -*- coding: utf-8 -*-
"""Offline tests for list-item construction (display markup vs metadata)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import ui  # noqa: E402


class PlainTextTests(unittest.TestCase):
    def test_strips_kodi_markup(self):
        self.assertEqual(
            ui.plain("[COLOR gray](1994)[/COLOR] [I]GB[/I]"),
            "(1994) GB",
        )
        self.assertEqual(ui.plain("[B]Bold[/B]"), "Bold")
        self.assertEqual(ui.plain("No markup"), "No markup")

    def test_keeps_bracketed_words_that_are_not_markup(self):
        self.assertEqual(ui.plain("[Live] Set"), "[Live] Set")
        self.assertEqual(ui.plain("1994 [Part 2]"), "1994 [Part 2]")


class ListItemInfoTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]

    def test_track_metadata_title_has_no_markup(self):
        ui.track_item(1, "plugin://x?mode=play", "Show  [COLOR gray](12 Oct)[/COLOR]",
                      title="Show")
        info = xbmcplugin.ITEMS[0]["info"]["music"]
        self.assertEqual(info["title"], "Show")
        self.assertTrue(xbmcplugin.ITEMS[0]["label"].startswith("Show  [COLOR"))

    def test_track_title_defaults_to_plain_label(self):
        ui.track_item(1, "plugin://x?mode=play", "Show  [COLOR gray](12 Oct)[/COLOR]")
        self.assertEqual(xbmcplugin.ITEMS[0]["info"]["music"]["title"], "Show  (12 Oct)")

    def test_menu_metadata_title_has_no_markup(self):
        ui.menu_item(1, "plugin://x?mode=feed", "Feed  [COLOR gray](4 episodes)[/COLOR]")
        self.assertEqual(xbmcplugin.ITEMS[0]["info"]["music"]["title"], "Feed  (4 episodes)")

    def test_track_duration_and_artist_are_metadata(self):
        ui.track_item(1, "plugin://x?mode=play", "Station [I]GB[/I]", artist="[B]GB[/B]", duration=90)
        info = xbmcplugin.ITEMS[0]["info"]["music"]
        self.assertEqual(info["artist"], "GB")
        self.assertEqual(info["duration"], 90)


if __name__ == "__main__":
    unittest.main()
