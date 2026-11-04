# -*- coding: utf-8 -*-
"""Resolve the built RaveTapePacks URLs against an HTTP server, offline.

The live site hotlink guard returns 403 to a bare GET and audio/mpeg (or 206
with a Range) once the Referer/UA from ``legacy.playable()`` are present.  This
test reproduces that contract locally so a URL-building regression is caught
without touching ravetapepacks.com.
"""

import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import legacy  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    server_version = "RaveFixture/1.0"

    def log_message(self, *args):  # keep unittest output clean
        pass

    def _send(self, status, body, content_type="audio/mpeg", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        port = self.server.server_address[1]
        root = "http://127.0.0.1:%d/" % port
        if self.path == "/":
            page = (
                '<audio src="/music/Pack One/Tape 1 (Side A) - Swan-E.mp3"></audio>'
                '<audio src="http://127.0.0.1:%d/music/PackTwo/'
                'DJ_SS_&amp;_Twisted_Individual.mp3"></audio>'
                % port
            )
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        if not self.path.startswith("/music/"):
            self._send(404, b"missing", "text/plain")
            return
        # Hotlink guard: the exact Referer + browser UA from the suffix.
        if self.headers.get("Referer") != root or \
                self.headers.get("User-Agent") != "Mozilla/5.0":
            self._send(403, b"Access forbidden!", "text/html; charset=utf-8")
            return
        body = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 32
        if self.headers.get("Range") == "bytes=0-":
            self._send(206, body, extra={
                "Content-Range": "bytes 0-%d/%d" % (len(body) - 1, len(body))})
        else:
            self._send(200, body)

    def do_HEAD(self):
        port = self.server.server_address[1]
        root = "http://127.0.0.1:%d/" % port
        if self.headers.get("Referer") != root or \
                self.headers.get("User-Agent") != "Mozilla/5.0":
            self.send_response(403)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", "40")
        self.end_headers()


class LegacyStreamResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d/" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2)

    def _patched(self):
        return (
            mock.patch.object(legacy, "BASE", self.base),
            mock.patch.object(legacy.http, "host_is_blocked", return_value=False),
            mock.patch.object(legacy.http, "is_public_http_url", return_value=True),
        )

    def test_built_urls_resolve_to_audio_with_the_referer_suffix(self):
        patches = self._patched()
        for patcher in patches:
            patcher.start()
        try:
            packs = legacy.packs()
            tracks = [track for pack in packs for track in pack["tracks"]]
            self.assertEqual(len(tracks), 2)
            for track in tracks:
                playable = legacy.playable(track["url"])
                self.assertIn("|Referer=" + self.base, playable)
                with legacy.http.open_media(playable, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertTrue(
                        response.headers.get("Content-Type", "").startswith("audio/"))
                    self.assertTrue(response.read(4).startswith(b"ID3"))
        finally:
            for patcher in reversed(patches):
                patcher.stop()

    def test_probe_media_sends_the_suffix_referer(self):
        patches = self._patched()
        for patcher in patches:
            patcher.start()
        try:
            url = legacy.playable(
                self.base + "music/PackOne/Tape_1.mp3")
            probe = legacy.http.probe_media(url, timeout=5)
            self.assertEqual(probe.get("content_type"), "audio/mpeg")
            self.assertEqual(probe.get("size"), 40)
        finally:
            for patcher in reversed(patches):
                patcher.stop()


if __name__ == "__main__":
    unittest.main()
