# -*- coding: utf-8 -*-
"""Live station identity and direct-stream playback tests (3.9.25)."""

import os
import socket
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import live, routes  # noqa: E402

PUBLIC_INFOS = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
KOOL = "https://admin.stream.rinse.fm/proxy/kool/stream"
RINSE = "https://admin.stream.rinse.fm/proxy/rinse_uk/stream"


class LiveIdentityTests(unittest.TestCase):
    def test_live_url_detection_and_station_mapping(self):
        self.assertTrue(live.is_live_stream(KOOL))
        self.assertTrue(live.is_live_stream(RINSE))
        self.assertFalse(live.is_live_stream("https://example.test/radio.mp3"))
        self.assertEqual(live.station_name(KOOL), "Kool FM")
        self.assertEqual(live.station_name(RINSE), "Rinse FM")
        self.assertEqual(live.station_name(KOOL, "Now Playing info goes here"), "Kool FM")
        self.assertEqual(live.station_name("https://example.test/x", "My Station"), "My Station")


class LivePlayRouteTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.RESOLVED[:]
        dns = mock.patch.object(routes.http.socket, "getaddrinfo",
                                return_value=PUBLIC_INFOS)
        dns.start()
        self.addCleanup(dns.stop)

    def test_live_play_resolves_the_direct_stream_again(self):
        routes.play(1, {"url": KOOL, "label": "Kool FM", "live": "1",
                        "station": "Kool FM"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["path"], KOOL)
        self.assertNotIn(".m3u", resolved["path"])
        self.assertEqual(resolved["info"]["music"]["title"], "Kool FM")
        self.assertEqual(resolved["info"]["music"]["artist"], "Kool FM")
        self.assertEqual(resolved["info"]["music"]["album"], "Live radio")
        self.assertNotIn("Now Playing info goes here", str(resolved["info"]))

    def test_rinse_play_also_resolves_direct(self):
        routes.play(1, {"url": RINSE, "label": "Rinse FM", "live": "1"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertEqual(resolved["path"], RINSE)
        self.assertNotIn(".m3u", resolved["path"])
        self.assertEqual(resolved["info"]["music"]["title"], "Rinse FM")

    def test_non_live_play_is_direct(self):
        routes.play(1, {"url": "https://example.test/a.mp3", "label": "Track"})
        self.assertEqual(xbmcplugin.RESOLVED[-1]["path"], "https://example.test/a.mp3")

    def test_no_playback_resolver_uses_m3u(self):
        routes.play(1, {"url": KOOL, "label": "Kool FM", "live": "1"})
        self.assertFalse(any(".m3u" in str(item.get("path", ""))
                             for item in xbmcplugin.RESOLVED))


if __name__ == "__main__":
    unittest.main()
