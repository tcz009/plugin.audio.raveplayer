# -*- coding: utf-8 -*-
"""Round-face fallback for playable tracks without genuine cover art."""

import os
import socket
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import routes, ui  # noqa: E402

PUBLIC_INFOS = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class RoundFaceTests(unittest.TestCase):
    def test_track_item_keeps_real_art_and_falls_back_to_logo(self):
        with mock.patch.object(ui.kodi, "ROUND_FACE", "/tmp/round-face.png"):
            real = ui.track_item(1, "plugin://x", "Track", thumb="https://img.example/a.jpg")
            fallback = ui.track_item(1, "plugin://x", "Track")
        self.assertEqual(real.art["thumb"], "https://img.example/a.jpg")
        self.assertEqual(fallback.art["thumb"], "/tmp/round-face.png")
        self.assertEqual(fallback.art["icon"], "/tmp/round-face.png")

    def test_play_resolution_uses_logo_when_thumb_missing(self):
        with mock.patch.object(routes.http.socket, "getaddrinfo", return_value=PUBLIC_INFOS):
            routes.play(1, {"url": "https://example.test/a.mp3", "label": "Track"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertEqual(resolved["art"]["thumb"], routes.kodi.ROUND_FACE)
        self.assertEqual(resolved["art"]["icon"], routes.kodi.ROUND_FACE)

    def test_play_resolution_keeps_public_cover(self):
        with mock.patch.object(routes.http.socket, "getaddrinfo", return_value=PUBLIC_INFOS):
            routes.play(1, {"url": "https://example.test/a.mp3", "label": "Track",
                            "thumb": "https://img.example/a.jpg"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertEqual(resolved["art"]["thumb"], "https://img.example/a.jpg")


if __name__ == "__main__":
    unittest.main()
