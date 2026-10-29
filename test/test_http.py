# -*- coding: utf-8 -*-
"""Offline tests for the HTTP layer and its caching wrapper."""

import gzip
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from email.message import Message
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import cache, http  # noqa: E402


class FakeResponse(object):
    def __init__(self, body, headers=None):
        self.body = body
        self.headers = headers or Message()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class DecodeTests(unittest.TestCase):
    def test_gzip_body_is_decompressed(self):
        headers = Message()
        headers["Content-Encoding"] = "gzip"
        response = FakeResponse(gzip.compress("Café".encode("utf-8")), headers)
        self.assertEqual(http._decode(response), "Café")

    def test_xml_declaration_charset_wins_without_header_charset(self):
        body = '<?xml version="1.0" encoding="ISO-8859-1"?><title>Café</title>'
        response = FakeResponse(body.encode("iso-8859-1"), Message())
        self.assertEqual(http._decode(response), body)

    def test_utf8_bom_is_stripped(self):
        response = FakeResponse("\ufeffhello".encode("utf-8"), Message())
        self.assertEqual(http._decode(response), "hello")

    def test_unknown_charset_falls_back_to_utf8(self):
        headers = Message()
        headers["Content-Type"] = "text/plain; charset=not-a-real-charset"
        response = FakeResponse("Café".encode("utf-8"), headers)
        self.assertEqual(http._decode(response), "Café")

    def test_corrupt_gzip_does_not_escape_the_http_layer(self):
        headers = Message()
        headers["Content-Encoding"] = "gzip"
        response = FakeResponse(b"this is not gzip", headers)
        with mock.patch("urllib.request.urlopen", return_value=response):
            self.assertIsNone(http._request("https://example.test/x", 5, None))

    def test_network_error_returns_none(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            self.assertIsNone(http._request("https://example.test/x", 5, None))


class FetchCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="raveplayer-http-test-")
        self.old = os.environ.get(cache.CACHE_DIR_ENV)
        os.environ[cache.CACHE_DIR_ENV] = self.directory

    def tearDown(self):
        if self.old is None:
            os.environ.pop(cache.CACHE_DIR_ENV, None)
        else:
            os.environ[cache.CACHE_DIR_ENV] = self.old
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_text_response_is_cached(self):
        with mock.patch.object(http, "_request", return_value="body") as request:
            self.assertEqual(http.fetch("https://example.test/a", ttl=60), "body")
            self.assertEqual(http.fetch("https://example.test/a", ttl=60), "body")
        self.assertEqual(request.call_count, 1)

    def test_zero_ttl_always_requests(self):
        with mock.patch.object(http, "_request", return_value="body") as request:
            http.fetch("https://example.test/nocache")
            http.fetch("https://example.test/nocache")
        self.assertEqual(request.call_count, 2)

    def test_empty_response_is_not_cached(self):
        with mock.patch.object(http, "_request", side_effect=["", "body"]) as request:
            self.assertIsNone(http.fetch("https://example.test/empty", ttl=60))
            self.assertEqual(http.fetch("https://example.test/empty", ttl=60), "body")
        self.assertEqual(request.call_count, 2)

    def test_headers_are_part_of_the_cache_key(self):
        with mock.patch.object(http, "_request", return_value="body") as request:
            http.fetch("https://example.test/headers", headers={"Referer": "a"}, ttl=60)
            http.fetch("https://example.test/headers", headers={"Referer": "b"}, ttl=60)
        self.assertEqual(request.call_count, 2)

    def test_json_response_is_cached(self):
        with mock.patch.object(http, "_request", return_value='{"ok": true}') as request:
            self.assertEqual(http.fetch_json("https://example.test/j", ttl=60), {"ok": True})
            self.assertEqual(http.fetch_json("https://example.test/j", ttl=60), {"ok": True})
        self.assertEqual(request.call_count, 1)

    def test_bad_json_is_not_cached(self):
        with mock.patch.object(http, "_request", return_value="<html>oops</html>") as request:
            self.assertIsNone(http.fetch_json("https://example.test/bad", ttl=60))
            self.assertIsNone(http.fetch_json("https://example.test/bad", ttl=60))
        self.assertEqual(request.call_count, 2)

    def test_cache_failure_does_not_break_the_fetch(self):
        blocker = os.path.join(self.directory, "file")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("x")
        os.environ[cache.CACHE_DIR_ENV] = blocker
        with mock.patch.object(http, "_request", return_value="body"):
            self.assertEqual(http.fetch("https://example.test/disk", ttl=60), "body")


if __name__ == "__main__":
    unittest.main()
