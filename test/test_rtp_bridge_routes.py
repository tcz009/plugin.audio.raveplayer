# -*- coding: utf-8 -*-
"""Playback route uses the loopback bridge only for RTP and fails quietly."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import routes  # noqa: E402

TARGET = "https://www.ravetapepacks.com/music/Pack/Tape_1.mp3"


class FakeBridge(object):
    events = []
    start_ok = True

    def __init__(self):
        self.token = "t"
    def start(self):
        FakeBridge.events.append("start")
        return self.start_ok
    def url_for(self, target):
        return "http://127.0.0.1:9999/t/token"
    def wait_for_playback(self):
        FakeBridge.events.append("wait")
    def close(self):
        FakeBridge.events.append("close")


class BridgeRouteTests(unittest.TestCase):
    def setUp(self):
        FakeBridge.events = []
        FakeBridge.start_ok = True
        self.bridge = mock.patch.object(routes.rtp_bridge, "RTPBridge", FakeBridge)
        self.bridge.start()
        self.addCleanup(self.bridge.stop)
        self.egress = mock.patch.object(routes.http, "is_egress_host", return_value=True)
        self.egress.start()
        self.addCleanup(self.egress.stop)
        self.playable = mock.patch.object(routes, "_playable_url", return_value=TARGET)
        self.playable.start()
        self.addCleanup(self.playable.stop)
        self.resolved = mock.patch.object(routes.xbmcplugin, "setResolvedUrl").start()
        self.addCleanup(mock.patch.stopall)

    def test_rtp_play_uses_bridge_and_waits_before_close(self):
        routes.play(1, {"url": TARGET, "label": "Tape"})
        item = self.resolved.call_args[0][2]
        self.assertEqual(item.path, "http://127.0.0.1:9999/t/token")
        self.assertEqual(FakeBridge.events, ["start", "wait", "close"])

    def test_bridge_failure_falls_back_to_direct_quietly(self):
        FakeBridge.start_ok = False
        with mock.patch.object(routes.kodi, "notify") as notify:
            routes.play(1, {"url": TARGET, "label": "Tape"})
        item = self.resolved.call_args[0][2]
        self.assertEqual(item.path, TARGET)
        notify.assert_not_called()

    def test_rtp_browse_failures_are_quiet(self):
        with mock.patch.object(routes.legacy, "packs", return_value=[]), \
                mock.patch.object(routes.legacy, "pack", return_value=None), \
                mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.kodi, "end_directory") as end:
            routes.legacy_packs(1, {})
            routes.legacy_index(1, {"kind": "dj"})
            routes.legacy_pack(1, {"pack": "missing"})
        notify.assert_not_called()
        self.assertEqual(end.call_count, 3)

    def test_unplayable_rtp_resolve_is_quiet(self):
        self.playable = mock.patch.object(routes, "_playable_url", return_value="")
        self.playable.start()
        with mock.patch.object(routes.kodi, "notify") as notify:
            routes.play(1, {"url": TARGET, "label": "Tape"})
        notify.assert_not_called()
        self.assertFalse(self.resolved.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
