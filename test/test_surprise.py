# -*- coding: utf-8 -*-
"""Surprise Me reveal route tests (overlay fake; no network/playback)."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import routes, spinner  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeReveal(object):
    events = []
    cancelled = False
    def __init__(self, code="RANDOM PACK"):
        self.code = code
        FakeReveal.events.append(("init", code))
    def show(self):
        FakeReveal.events.append(("show",))
        return True
    def close(self):
        FakeReveal.events.append(("close",))


class SurpriseRouteTests(unittest.TestCase):
    def setUp(self):
        FakeReveal.events = []
        FakeReveal.cancelled = False
        del xbmcplugin.ITEMS[:]
        self.reveal = mock.patch.object(routes.spinner, "SurpriseReveal", FakeReveal)
        self.reveal.start()
        self.addCleanup(self.reveal.stop)

    def test_overlay_xml_uses_existing_frames_and_burst_art(self):
        xml = os.path.join(ROOT, "resources", "skins", "Default", "720p",
                           spinner.SURPRISE_XML)
        with open(xml, encoding="utf-8") as handle:
            markup = handle.read()
        for control_id in ("99", "100", "101", "102", "103", "104"):
            self.assertIn('id="%s"' % control_id, markup)
        self.assertIn("SURPRISE ME", markup)
        self.assertIn("SPINNING THE RACK", markup)
        burst = os.path.join(ROOT, "resources", "art", "surprise-burst.jpg")
        self.assertTrue(os.path.isfile(burst))
        self.assertTrue(os.path.isfile(spinner.frame_paths(spinner.FRAME_SIZE, ROOT)[0]))

    def test_overlay_closes_before_random_pick_result(self):
        pack = {"identifier": "pack-1", "title": "Pack"}
        with mock.patch.object(routes.kodi, "setting_bool", return_value=True), \
                mock.patch.object(routes.latest, "random_pack", return_value=pack), \
                mock.patch.object(routes, "archive_item",
                                  side_effect=lambda h, p: FakeReveal.events.append(("archive",))):
            routes.surprise(1, {})
        self.assertEqual(FakeReveal.events[0][0], "init")
        self.assertEqual(FakeReveal.events[1][0], "show")
        self.assertEqual(FakeReveal.events[2][0], "close")
        self.assertEqual(FakeReveal.events[3][0], "archive")

    def test_setting_off_picks_immediately_without_overlay(self):
        pack = {"identifier": "pack-1", "title": "Pack"}
        with mock.patch.object(routes.kodi, "setting_bool", return_value=False), \
                mock.patch.object(routes.spinner, "SurpriseReveal",
                                  side_effect=AssertionError("must not construct")), \
                mock.patch.object(routes.latest, "random_pack", return_value=pack), \
                mock.patch.object(routes, "archive_item") as archive:
            routes.surprise(1, {})
        archive.assert_called_once()
        self.assertEqual(FakeReveal.events, [])

    def test_back_cancel_skips_random_pick_and_closes(self):
        FakeReveal.cancelled = True
        with mock.patch.object(routes.kodi, "setting_bool", return_value=True), \
                mock.patch.object(routes.latest, "random_pack") as pick, \
                mock.patch.object(routes.kodi, "end_directory") as end:
            routes.surprise(1, {})
        pick.assert_not_called()
        end.assert_called_once()
        self.assertTrue(any(event[0] == "close" for event in FakeReveal.events))

    def test_reveal_failure_still_picks(self):
        pack = {"identifier": "pack-1", "title": "Pack"}
        def fail_show(self):
            FakeReveal.events.append(("show",))
            raise RuntimeError("window broke")
        with mock.patch.object(routes.kodi, "setting_bool", return_value=True), \
                mock.patch.object(FakeReveal, "show", fail_show), \
                mock.patch.object(routes.latest, "random_pack", return_value=pack), \
                mock.patch.object(routes, "archive_item") as archive:
            routes.surprise(1, {})
        archive.assert_called_once()
        self.assertTrue(any(event[0] == "close" for event in FakeReveal.events))


if __name__ == "__main__":
    unittest.main()
