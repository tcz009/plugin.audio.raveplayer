# -*- coding: utf-8 -*-
"""Loopback RTP playback bridge: token, range/headers, redirects, close."""

import base64
import contextlib
import os
import sys
import unittest
import urllib.error
import urllib.request
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import rtp_bridge  # noqa: E402

TARGET = "https://www.ravetapepacks.com/music/Pack/Tape_1.mp3|Referer=https://www.ravetapepacks.com/"


class FakeResponse(object):
    def __init__(self, body=b"bridge-body", status=206, final=TARGET):
        self.body = body
        self.status = status
        self.final = final
        self.headers = {
            "Content-Type": "audio/mpeg",
            "Content-Length": str(len(body)),
            "Content-Range": "bytes 0-10/100",
            "Accept-Ranges": "bytes",
        }
        self.reads = 0

    def geturl(self):
        return self.final

    def read(self, size):
        if self.reads:
            return b""
        self.reads += 1
        return self.body


class RTPBridgeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.response = FakeResponse()
        @contextlib.contextmanager
        def fake_open(url, timeout=None, headers=None, method=None):
            self.calls.append({"url": url, "headers": headers or {}, "method": method})
            yield self.response
        self.open_media = mock.patch.object(rtp_bridge.http, "open_media", fake_open)
        self.open_media.start()
        self.is_egress = mock.patch.object(
            rtp_bridge.http, "is_egress_host",
            side_effect=lambda value: "ravetapepacks.com" in str(value))
        self.is_egress.start()
        self.bridge = rtp_bridge.RTPBridge()
        self.assertTrue(self.bridge.start())
        self.addCleanup(self._close)

    def _close(self):
        self.bridge.close()
        self.open_media.stop()
        self.is_egress.stop()

    def test_url_for_only_bridges_rtp_hosts(self):
        self.assertTrue(self.bridge.url_for(TARGET).startswith(
            "http://127.0.0.1:"))
        self.assertEqual(self.bridge.url_for("https://example.com/a.mp3"), "")

    def test_range_and_headers_are_forwarded(self):
        url = self.bridge.url_for(TARGET)
        request = urllib.request.Request(url, headers={
            "Range": "bytes=0-10",
            "Referer": "https://www.ravetapepacks.com/",
            "User-Agent": "Kodi",
        })
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read()
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers.get("Content-Range"),
                             "bytes 0-10/100")
        self.assertEqual(body, b"bridge-body")
        self.assertEqual(self.calls[0]["headers"]["Range"], "bytes=0-10")
        self.assertEqual(self.calls[0]["headers"]["Referer"],
                         "https://www.ravetapepacks.com/")
        self.assertEqual(self.calls[0]["url"], TARGET)

    def test_bad_token_and_non_rtp_targets_are_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as bad:
            urllib.request.urlopen("http://127.0.0.1:%d/wrong/%s"
                                   % (self.bridge.port, "abc"), timeout=5)
        self.assertEqual(bad.exception.code, 403)
        encoded = base64.urlsafe_b64encode(
            b"https://example.com/a.mp3").decode("ascii").rstrip("=")
        with self.assertRaises(urllib.error.HTTPError) as non_rtp:
            urllib.request.urlopen("http://127.0.0.1:%d/%s/%s"
                                   % (self.bridge.port, self.bridge.token, encoded),
                                   timeout=5)
        self.assertEqual(non_rtp.exception.code, 403)
        self.assertEqual(self.calls, [])

    def test_redirect_away_from_rtp_is_refused(self):
        self.response.final = "https://example.com/final"
        url = self.bridge.url_for(TARGET)
        with self.assertRaises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(url, timeout=5)
        self.assertEqual(refused.exception.code, 502)


if __name__ == "__main__":
    unittest.main()
