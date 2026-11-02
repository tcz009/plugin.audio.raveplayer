# -*- coding: utf-8 -*-
"""Live identity and finite direct-URL reconnect playlist tests (3.9.26)."""

import os
import socket
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmc  # noqa: E402
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


class ReconnectUrlTests(unittest.TestCase):
    def test_builds_a_finite_six_entry_playlist(self):
        urls = live.reconnect_urls(KOOL, "Kool FM")
        self.assertEqual(len(urls), live.LIVE_RECONNECT_ENTRIES)
        self.assertTrue(all(url == KOOL for url in urls))

    def test_resolver_is_called_per_entry_and_refreshes_urls(self):
        seen = []
        def resolver(station):
            seen.append(station)
            return KOOL + "?attempt=%d" % len(seen)
        urls = live.reconnect_urls(KOOL, "Kool FM", resolver=resolver)
        self.assertEqual(len(urls), live.LIVE_RECONNECT_ENTRIES)
        self.assertEqual(len(seen), live.LIVE_RECONNECT_ENTRIES)
        self.assertEqual(urls[0], KOOL + "?attempt=1")
        self.assertEqual(urls[-1], KOOL + "?attempt=6")
        self.assertEqual(len(set(urls)), live.LIVE_RECONNECT_ENTRIES)

    def test_failed_resolver_keeps_last_known_direct_url(self):
        urls = live.reconnect_urls(KOOL, "Kool FM", resolver=lambda _name: "")
        self.assertEqual(urls, [KOOL] * live.LIVE_RECONNECT_ENTRIES)

    def test_cap_is_bounded_and_invalid_cap_falls_back(self):
        self.assertLessEqual(len(live.reconnect_urls(KOOL, "Kool FM", entries=99)),
                             live.MAX_RECONNECT_ENTRIES)
        self.assertEqual(len(live.reconnect_urls(KOOL, "Kool FM", entries="bad")),
                         live.LIVE_RECONNECT_ENTRIES)

    def test_invalid_stream_yields_no_playlist(self):
        self.assertEqual(live.reconnect_urls("file:///etc/passwd", "Kool FM"), [])


class LivePlayRouteTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.RESOLVED[:]
        del xbmc.PLAYED[:]
        dns = mock.patch.object(routes.http.socket, "getaddrinfo",
                                return_value=PUBLIC_INFOS)
        dns.start()
        self.addCleanup(dns.stop)

    def test_live_play_starts_six_direct_urls_not_setResolvedUrl(self):
        routes.play(1, {"url": KOOL, "label": "Kool FM", "live": "1",
                        "station": "Kool FM"})
        self.assertEqual(xbmcplugin.RESOLVED, [])
        playlist = xbmc.PLAYED[-1]
        self.assertEqual(len(playlist.items), live.LIVE_RECONNECT_ENTRIES)
        self.assertTrue(all(url == KOOL for url, _item in playlist.items))
        self.assertTrue(all(".m3u" not in url for url, _item in playlist.items))
        first_item = playlist.items[0][1]
        self.assertEqual(first_item.info["music"]["title"], "Kool FM")
        self.assertEqual(first_item.info["music"]["artist"], "Kool FM")
        self.assertEqual(first_item.info["music"]["album"], "Live radio")
        self.assertNotIn("Now Playing info goes here", str(first_item.info))

    def test_rinse_play_is_also_a_direct_url_playlist(self):
        routes.play(1, {"url": RINSE, "label": "Rinse FM", "live": "1"})
        playlist = xbmc.PLAYED[-1]
        self.assertEqual(len(playlist.items), live.LIVE_RECONNECT_ENTRIES)
        self.assertTrue(all(url == RINSE for url, _item in playlist.items))
        self.assertEqual(playlist.items[0][1].info["music"]["title"], "Rinse FM")

    def test_non_live_play_is_still_direct(self):
        routes.play(1, {"url": "https://example.test/a.mp3", "label": "Track"})
        self.assertEqual(xbmcplugin.RESOLVED[-1]["path"], "https://example.test/a.mp3")

    def test_playlist_start_failure_falls_back_to_direct_stream(self):
        with mock.patch.object(routes.xbmc.Player, "play",
                               side_effect=RuntimeError("no player")):
            routes.play(1, {"url": KOOL, "label": "Kool FM", "live": "1"})
        self.assertEqual(xbmcplugin.RESOLVED[-1]["path"], KOOL)

    def test_user_stop_clears_playlist_without_addon_restart(self):
        routes.play(1, {"url": KOOL, "label": "Kool FM", "live": "1"})
        self.assertEqual(len(xbmc.PLAYED), 1)
        xbmc.Player().stop()
        self.assertEqual(xbmc.PLAYED, [])
        self.assertEqual(xbmcplugin.RESOLVED, [])

    def test_no_playlist_file_or_m3u_is_created(self):
        routes.play(1, {"url": KOOL, "label": "Kool FM", "live": "1"})
        playlist = xbmc.PLAYED[-1]
        self.assertFalse(any(str(url).endswith(".m3u") for url, _item in playlist.items))
        self.assertFalse(any("raveplayer-live" in str(url) for url, _item in playlist.items))


if __name__ == "__main__":
    unittest.main()
