# -*- coding: utf-8 -*-
"""Delayed tuning spinner is wired before playback, never over the player."""

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

from resources.lib import routes  # noqa: E402

PUBLIC_INFOS = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
KOOL = "https://admin.stream.rinse.fm/proxy/kool/stream"


class FakeTuning(object):
    events = []
    expired = False
    cancelled_flag = False

    def __init__(self, label):
        self.label = label
        FakeTuning.events.append(("start", label))

    def start(self):
        return True

    def close(self):
        FakeTuning.events.append(("close",))

    def cancelled(self):
        return FakeTuning.cancelled_flag

    def __getattr__(self, name):
        if name == "expired":
            return FakeTuning.expired
        raise AttributeError(name)


class TuningRouteTests(unittest.TestCase):
    def setUp(self):
        FakeTuning.events = []
        FakeTuning.expired = False
        FakeTuning.cancelled_flag = False
        del xbmcplugin.RESOLVED[:]
        del xbmc.PLAYED[:]
        self.spinner = mock.patch.object(routes.spinner, "TuningSpinner", FakeTuning)
        self.spinner.start()
        self.addCleanup(self.spinner.stop)
        self.setting = mock.patch.object(routes.kodi, "setting_bool", return_value=True)
        self.setting.start()
        self.addCleanup(self.setting.stop)
        self.dns = mock.patch.object(routes.http.socket, "getaddrinfo",
                                     return_value=PUBLIC_INFOS)
        self.dns.start()
        self.addCleanup(self.dns.stop)

    def test_close_is_before_direct_resolve(self):
        def resolve(handle, ok, item):
            FakeTuning.events.append(("resolve", ok))
        with mock.patch.object(routes.xbmcplugin, "setResolvedUrl", side_effect=resolve):
            routes.play(1, {"url": "https://example.test/a.mp3", "label": "Track"})
        closes = [i for i, event in enumerate(FakeTuning.events) if event[0] == "close"]
        resolves = [i for i, event in enumerate(FakeTuning.events) if event[0] == "resolve"]
        self.assertTrue(closes and resolves)
        self.assertLess(closes[0], resolves[0])

    def test_close_is_before_live_playlist_play(self):
        urls = [KOOL] * 6
        def play(playlist):
            FakeTuning.events.append(("player",))
        with mock.patch.object(routes.live, "reconnect_urls", return_value=urls), \
                mock.patch.object(routes.xbmc, "PlayList"), \
                mock.patch.object(routes.xbmc.Player, "play", side_effect=play):
            routes.play(1, {"url": KOOL, "label": "Kool FM", "live": "1"})
        closes = [i for i, event in enumerate(FakeTuning.events) if event[0] == "close"]
        plays = [i for i, event in enumerate(FakeTuning.events) if event[0] == "player"]
        self.assertTrue(closes and plays)
        self.assertLess(closes[0], plays[0])

    def test_timeout_fails_and_closes(self):
        FakeTuning.expired = True
        with mock.patch.object(routes.kodi, "notify") as notify:
            routes.play(1, {"url": "https://example.test/a.mp3", "label": "Track"})
        self.assertTrue(any(event[0] == "close" for event in FakeTuning.events))
        self.assertTrue(xbmcplugin.RESOLVED)
        self.assertFalse(xbmcplugin.RESOLVED[-1]["ok"])
        self.assertTrue(any("taking too long" in str(call) for call in notify.call_args_list))

    def test_dnb_closes_before_play(self):
        def play(handle, params):
            FakeTuning.events.append(("play", params.get("label")))
        with mock.patch.object(routes.dnbradio, "stream_url",
                               return_value="https://example.test/dnb.mp3"), \
                mock.patch.object(routes, "play", side_effect=play):
            routes.dnb_play(1, {"id": "123", "label": "DNB Show"})
        closes = [i for i, event in enumerate(FakeTuning.events) if event[0] == "close"]
        plays = [i for i, event in enumerate(FakeTuning.events) if event[0] == "play"]
        self.assertTrue(closes and plays)
        self.assertLess(closes[0], plays[0])

    def test_setting_off_does_not_construct_spinner(self):
        with mock.patch.object(routes.kodi, "setting_bool", return_value=False), \
                mock.patch.object(routes.spinner, "TuningSpinner",
                                  side_effect=AssertionError("must not construct")):
            routes.play(1, {"url": "https://example.test/a.mp3", "label": "Track"})
        self.assertEqual(FakeTuning.events, [])
        self.assertTrue(xbmcplugin.RESOLVED[-1]["ok"])


if __name__ == "__main__":
    unittest.main()
