# -*- coding: utf-8 -*-
"""Live reconnect playlist and fixed station metadata tests."""

import os
import socket
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import kodi, live, routes  # noqa: E402

PUBLIC_INFOS = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
KOOL = "https://admin.stream.rinse.fm/proxy/kool/stream"
RINSE = "https://admin.stream.rinse.fm/proxy/rinse_uk/stream"


class LivePlaylistTests(unittest.TestCase):
    def test_live_url_detection_and_station_mapping(self):
        self.assertTrue(live.is_live_stream(KOOL))
        self.assertTrue(live.is_live_stream(RINSE))
        self.assertFalse(live.is_live_stream("https://example.test/radio.mp3"))
        self.assertEqual(live.station_name(KOOL), "Kool FM")
        self.assertEqual(live.station_name(RINSE), "Rinse FM")
        self.assertEqual(live.station_name(KOOL, "Now Playing info goes here"), "Kool FM")
        self.assertEqual(live.station_name("https://example.test/x", "My Station"), "My Station")

    def test_m3u_is_finite_and_uses_fixed_station_name(self):
        body = live.playlist_text(KOOL, live.station_name(KOOL))
        self.assertTrue(body.startswith("#EXTM3U\n"))
        self.assertEqual(body.count("#EXTINF:-1,Kool FM"), live.LIVE_RECONNECT_ENTRIES)
        self.assertEqual(body.count(KOOL), live.LIVE_RECONNECT_ENTRIES)
        self.assertNotIn("Now Playing info goes here", body)
        self.assertLessEqual(live.LIVE_RECONNECT_ENTRIES, 12)
        self.assertEqual(live.playlist_text("file:///nope", "Kool FM"), "")

    def test_write_playlist_uses_xbmcvfs_and_returns_absolute_existing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "live.m3u")

            class FakeFile:
                def __init__(self, path, mode):
                    self.data = ""
                def write(self, data):
                    self.data += data
                def flush(self):
                    pass
                def close(self):
                    with open(target, "w", encoding="utf-8") as handle:
                        handle.write(self.data)

            class FakeVfs:
                @staticmethod
                def mkdirs(path):
                    return True
                @staticmethod
                def File(path, mode):
                    return FakeFile(path, mode)
                @staticmethod
                def exists(path):
                    return os.path.isfile(target)
                @staticmethod
                def translatePath(path):
                    return target

            with mock.patch.object(live, "xbmcvfs", FakeVfs):
                path = live.write_playlist(KOOL, "Kool FM")
            self.assertEqual(path, target)
            self.assertTrue(os.path.isabs(path))
            self.assertTrue(os.path.isfile(path))
            with open(target, encoding="utf-8") as handle:
                body = handle.read()
            self.assertEqual(body.count(KOOL), live.LIVE_RECONNECT_ENTRIES)


class LivePlayRouteTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.RESOLVED[:]
        dns = mock.patch.object(routes.http.socket, "getaddrinfo",
                                return_value=PUBLIC_INFOS)
        dns.start()
        self.addCleanup(dns.stop)

    def test_live_play_resolves_bounded_m3u_with_fixed_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "kool-live.m3u")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(live.playlist_text(KOOL, "Kool FM"))
            with mock.patch.object(routes.live, "write_playlist",
                                   return_value=target) as writer:
                routes.play(1, {"url": KOOL, "label": "Kool FM", "live": "1",
                                "station": "Kool FM"})
            resolved = xbmcplugin.RESOLVED[-1]
            self.assertTrue(resolved["ok"])
            self.assertTrue(os.path.isabs(resolved["path"]))
            self.assertTrue(os.path.isfile(resolved["path"]))
        self.assertEqual(resolved["path"], target)
        self.assertEqual(resolved["info"]["music"]["title"], "Kool FM")
        self.assertEqual(resolved["info"]["music"]["artist"], "Kool FM")
        self.assertEqual(resolved["info"]["music"]["album"], "Live radio")
        self.assertNotIn("Now Playing info goes here", str(resolved["info"]))
        writer.assert_called_once()

    def test_live_play_falls_back_if_m3u_path_is_not_absolute(self):
        with mock.patch.object(routes.live, "write_playlist",
                               return_value="special://temp/kool.m3u"):
            routes.play(1, {"url": KOOL, "label": "Kool FM", "live": "1"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertEqual(resolved["path"], KOOL)

    def test_playlist_path_has_m3u_extension(self):
        self.assertTrue(live.playlist_path(KOOL).endswith(".m3u"))

    def test_live_play_falls_back_to_direct_stream_if_m3u_write_fails(self):
        with mock.patch.object(routes.live, "write_playlist", return_value=""):
            routes.play(1, {"url": KOOL, "label": "Kool FM", "live": "1"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["path"], KOOL)

    def test_write_failure_falls_back_with_empty_path(self):
        class BrokenVfs:
            @staticmethod
            def mkdirs(path):
                raise OSError("no temp")
        with mock.patch.object(live, "xbmcvfs", BrokenVfs):
            self.assertEqual(live.write_playlist(KOOL, "Kool FM"), "")

    def test_non_live_play_is_still_direct(self):
        routes.play(1, {"url": "https://example.test/a.mp3", "label": "Track"})
        self.assertEqual(xbmcplugin.RESOLVED[-1]["path"], "https://example.test/a.mp3")


if __name__ == "__main__":
    unittest.main()
