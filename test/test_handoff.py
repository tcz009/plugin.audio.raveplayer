# -*- coding: utf-8 -*-
"""Offline tests for Kodi add-on hand-off URLs and detection."""

import glob
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import handoff  # noqa: E402


class FakeAddon(object):
    def __init__(self, addon_id):
        self.addon_id = addon_id

    def getAddonInfo(self, key):
        return self.addon_id if key == "id" else ""


def _detect(installed):
    def factory(addon_id):
        if addon_id not in installed:
            raise RuntimeError("add-on not installed")
        return FakeAddon(addon_id)
    return factory


class AvailabilityTests(unittest.TestCase):
    def test_missing_addons_are_unavailable(self):
        with mock.patch.object(handoff.xbmcaddon, "Addon", side_effect=_detect(set())), \
                mock.patch.object(handoff.xbmc, "getCondVisibility", return_value=False):
            for kind in ("mixcloud", "soundcloud", "youtube"):
                self.assertFalse(handoff.available(kind), kind)

    def test_installed_addons_are_available(self):
        installed = {handoff.MIXCLOUD_ID, handoff.SOUNDCLOUD_ID, handoff.YOUTUBE_ID}
        with mock.patch.object(handoff.xbmcaddon, "Addon", side_effect=_detect(installed)):
            for kind in ("mixcloud", "soundcloud", "youtube"):
                self.assertTrue(handoff.available(kind), kind)

    def test_condvisibility_fallback(self):
        with mock.patch.object(handoff.xbmcaddon, "Addon", side_effect=RuntimeError("missing")), \
                mock.patch.object(handoff.xbmc, "getCondVisibility", return_value=True):
            self.assertTrue(handoff.available("youtube"))

    def test_unknown_kind_is_unavailable(self):
        self.assertFalse(handoff.available("archive"))

    def test_runtime_has_no_browser_opening_calls(self):
        root = os.path.dirname(HERE)
        paths = glob.glob(os.path.join(root, "resources", "lib", "*.py"))
        paths.append(os.path.join(root, "default.py"))
        forbidden = ("open_url", "open_external", "webbrowser", "StartAndroidActivity")
        for path in paths:
            text = open(path, encoding="utf-8").read()
            for token in forbidden:
                self.assertNotIn(token, text, "%s contains %s" % (path, token))


class UrlBuilderTests(unittest.TestCase):
    def test_mixcloud_search(self):
        self.assertEqual(
            handoff.mixcloud_search("GetDarker"),
            "plugin://plugin.audio.mixcloud/?mode=30&key=cloudcast&offset=0&query=GetDarker",
        )

    def test_mixcloud_cloudcast_path(self):
        self.assertEqual(
            handoff.mixcloud_cloudcast("https://www.mixcloud.com/getdarker/skream-watch-the-ride-2008/"),
            "plugin://plugin.audio.mixcloud/?mode=40&key=%2Fgetdarker%2Fskream-watch-the-ride-2008",
        )
        self.assertEqual(handoff.mixcloud_cloudcast("https://evil.example/x/y"), "")

    def test_soundcloud_play_and_search(self):
        page = "https://soundcloud.com/artist/track"
        self.assertEqual(
            handoff.soundcloud_play(page),
            "plugin://plugin.audio.soundcloud/play/?url=https%3A%2F%2Fsoundcloud.com%2Fartist%2Ftrack",
        )
        self.assertEqual(
            handoff.soundcloud_search("artist track"),
            "plugin://plugin.audio.soundcloud/search/?query=artist%20track",
        )

    def test_youtube_play_and_search(self):
        self.assertEqual(
            handoff.youtube_play("https://www.youtube.com/watch?v=abc123"),
            "plugin://plugin.video.youtube/play/?video_id=abc123",
        )
        self.assertEqual(
            handoff.youtube_play("https://youtu.be/xyz789"),
            "plugin://plugin.video.youtube/play/?video_id=xyz789",
        )
        self.assertEqual(
            handoff.youtube_target("https://www.youtube.com/channel/foo", "GetDarker"),
            "plugin://plugin.video.youtube/search/?q=GetDarker",
        )

    def test_targets_prefer_direct_pages(self):
        self.assertTrue(handoff.soundcloud_target(
            "https://soundcloud.com/artist/track").startswith(
                "plugin://plugin.audio.soundcloud/play/"))
        self.assertTrue(handoff.mixcloud_target(
            "https://www.mixcloud.com/getdarker/x/").startswith(
                "plugin://plugin.audio.mixcloud/?mode=40"))


if __name__ == "__main__":
    unittest.main()
