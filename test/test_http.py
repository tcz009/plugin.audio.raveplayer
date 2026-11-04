# -*- coding: utf-8 -*-
"""Offline tests for the HTTP layer and its caching wrapper."""

import gzip
import os
import shutil
import sys
import tempfile
import time
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
        self._offset = 0

    def read(self, size=-1):
        if size is None or size < 0:
            chunk = self.body[self._offset:]
            self._offset = len(self.body)
            return chunk
        chunk = self.body[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk

    def read1(self, size=-1):
        """Like HTTPResponse.read1: one recv's worth of data."""
        return self.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class SlowDripResponse(FakeResponse):
    """A hostile server: one body byte per short sleep, never EOF early."""

    def __init__(self, body, delay=0.02):
        FakeResponse.__init__(self, body)
        self.delay = delay

    def read1(self, size=-1):
        if self._offset >= len(self.body):
            return b""
        time.sleep(self.delay)
        chunk = self.body[self._offset:self._offset + 1]
        self._offset += len(chunk)
        return chunk


def _redirect_error(location, code=302):
    headers = Message()
    headers["Location"] = location
    return urllib.error.HTTPError("https://start.example/x", code, "Found", headers, None)


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
        with mock.patch.object(http._OPENER, "open", return_value=response):
            self.assertIsNone(http._request("https://example.test/x", 5, None))

    def test_network_error_returns_none(self):
        with mock.patch.object(http._OPENER, "open", side_effect=urllib.error.URLError("offline")):
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

    def test_cached_body_is_served_even_after_the_budget_is_gone(self):
        with mock.patch.object(http, "_request", return_value="body"):
            self.assertEqual(http.fetch("https://example.test/cached", ttl=60), "body")
        http.begin_route(0)
        try:
            with mock.patch.object(http, "_request") as request:
                self.assertEqual(http.fetch("https://example.test/cached", ttl=60), "body")
            self.assertFalse(request.called)
        finally:
            http.end_route()

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


class ResponseHardeningTests(unittest.TestCase):
    """Bounded bodies/decompression and the per-invocation network budget."""

    def tearDown(self):
        http.end_route()

    def test_oversized_body_is_rejected(self):
        response = FakeResponse(b"x" * 100, Message())
        with mock.patch.object(http, "MAX_BODY_BYTES", 10):
            self.assertIsNone(http._decode(response, 5))

    def test_gzip_bomb_is_rejected_after_decompression(self):
        headers = Message()
        headers["Content-Encoding"] = "gzip"
        response = FakeResponse(gzip.compress(b"x" * 100), headers)
        with mock.patch.object(http, "MAX_BODY_BYTES", 10):
            self.assertIsNone(http._decode(response, 5))

    def test_body_read_has_a_wall_clock_deadline(self):
        response = FakeResponse(b"x" * (http.READ_CHUNK_BYTES * 3), Message())
        # monotonic(): deadline calc, first loop check, then the deadline has passed
        with mock.patch.object(http.time, "monotonic", side_effect=[0.0, 0.0, 99.0]):
            self.assertIsNone(http._read_limited(response, 1))

    def test_zero_budget_skips_the_request(self):
        http.begin_route(0)
        with mock.patch.object(http, "_request") as request:
            self.assertIsNone(http.fetch("https://example.test/x"))
        self.assertFalse(request.called)
        self.assertTrue(http.route_budget_exhausted())

    def test_budget_clamps_the_request_timeout(self):
        http.begin_route(5)
        captured = {}

        def fake_request(url, timeout, headers):
            captured["timeout"] = timeout
            return "body"

        with mock.patch.object(http, "_request", side_effect=fake_request):
            self.assertEqual(http.fetch("https://example.test/x", timeout=20), "body")
        self.assertGreater(captured["timeout"], 0.0)
        self.assertLessEqual(captured["timeout"], 5.0)

    def test_unbudgeted_fetch_keeps_the_requested_timeout(self):
        captured = {}

        def fake_request(url, timeout, headers):
            captured["timeout"] = timeout
            return "body"

        http.end_route()
        with mock.patch.object(http, "_request", side_effect=fake_request):
            http.fetch("https://example.test/x", timeout=17)
        self.assertEqual(captured["timeout"], 17)

    def test_end_route_clears_the_budget(self):
        http.begin_route(5)
        self.assertIsNotNone(http.remaining())
        http.end_route()
        self.assertIsNone(http.remaining())
        self.assertFalse(http.route_budget_exhausted())

    def test_route_budget_stops_a_sequence_of_fetches(self):
        http.begin_route(0.05)
        calls = []

        def slow_request(url, timeout, headers):
            calls.append(timeout)
            time.sleep(0.01)
            return "body"

        with mock.patch.object(http, "_request", side_effect=slow_request):
            for _ in range(20):
                http.fetch("https://example.test/x", timeout=5)
        self.assertTrue(http.route_budget_exhausted())
        self.assertLess(len(calls), 20)

    def test_non_string_header_values_do_not_raise(self):
        response = FakeResponse(b"ok", Message())
        with mock.patch.object(http._OPENER, "open", return_value=response):
            self.assertEqual(http._request("https://example.test/x", 5, {"X-N": 1}), "ok")

    def test_declared_content_length_over_the_cap_is_rejected(self):
        headers = Message()
        headers["Content-Length"] = "999999999"
        response = FakeResponse(b"x", headers)
        with mock.patch.object(http, "MAX_BODY_BYTES", 10):
            self.assertIsNone(http._read_limited(response, 5))


class ReadBoundTests(unittest.TestCase):
    """A1: a slow-drip body must not outlive its wall-clock deadline."""

    def test_slow_drip_body_is_abandoned_at_the_deadline(self):
        response = SlowDripResponse(b"x" * 200, delay=0.02)
        started = time.monotonic()
        self.assertIsNone(http._read_limited(response, 0.12))
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.8, elapsed)

    def test_fetch_of_slow_drip_body_is_bounded_by_the_budget(self):
        response = SlowDripResponse(b"x" * 200, delay=0.02)
        http.begin_route(0.15)
        try:
            started = time.monotonic()
            with mock.patch.object(http._OPENER, "open", return_value=response):
                self.assertIsNone(http.fetch("https://slow.example/x", timeout=20))
            elapsed = time.monotonic() - started
        finally:
            http.end_route()
        self.assertLess(elapsed, 0.8, elapsed)


class MediaRedirectTests(unittest.TestCase):
    """open_media follows the same validated public redirects as fetch()."""

    infos = [(2, 1, 6, "", ("93.184.216.34", 443))]

    def test_open_media_follows_a_public_redirect(self):
        opener = mock.Mock()
        opener.open.side_effect = [
            _redirect_error("https://next.example/y"),
            FakeResponse(b"ID3", Message()),
        ]
        with mock.patch.object(http, "_OPENER", opener), \
                mock.patch.object(http.socket, "getaddrinfo", return_value=self.infos):
            with http.open_media("https://start.example/a.mp3", timeout=5) as response:
                self.assertEqual(response.read(3), b"ID3")
        self.assertEqual(opener.open.call_count, 2)

    def test_open_media_refuses_a_redirect_to_loopback(self):
        opener = mock.Mock()
        opener.open.side_effect = [_redirect_error("http://127.0.0.1/secret")]
        with mock.patch.object(http, "_OPENER", opener), \
                mock.patch.object(http.socket, "getaddrinfo", return_value=self.infos):
            with self.assertRaises(ValueError):
                with http.open_media("https://start.example/a.mp3", timeout=5):
                    pass
        self.assertEqual(opener.open.call_count, 1)


class RedirectHardeningTests(unittest.TestCase):
    """A2: redirects are public-http(s), validated per hop and budgeted."""

    def setUp(self):
        self.infos = [(2, 1, 6, "", ("93.184.216.34", 443))]

    def _follow(self, responses):
        opener = mock.Mock()
        opener.open.side_effect = responses
        with mock.patch.object(http, "_OPENER", opener), \
                mock.patch.object(http.socket, "getaddrinfo", return_value=self.infos):
            return http._request("https://start.example/x", 5, None), opener

    def test_non_http_initial_url_is_refused(self):
        opener = mock.Mock()
        with mock.patch.object(http, "_OPENER", opener):
            self.assertIsNone(http._request("ftp://example.test/x", 5, None))
        self.assertFalse(opener.open.called)

    def test_automatic_redirect_handler_is_disabled(self):
        self.assertTrue(any(isinstance(handler, http._NoRedirectHandler)
                            for handler in http._OPENER.handlers))

    def test_public_redirect_is_followed(self):
        body, opener = self._follow([
            _redirect_error("https://next.example/y"),
            FakeResponse(b"payload", Message()),
        ])
        self.assertEqual(body, "payload")
        self.assertEqual(opener.open.call_count, 2)

    def test_redirect_to_loopback_is_refused(self):
        body, opener = self._follow([_redirect_error("http://127.0.0.1/secret")])
        self.assertIsNone(body)
        self.assertEqual(opener.open.call_count, 1)

    def test_redirect_to_ftp_is_refused(self):
        body, opener = self._follow([_redirect_error("ftp://example.test/file")])
        self.assertIsNone(body)
        self.assertEqual(opener.open.call_count, 1)

    def test_redirect_to_a_private_hostname_is_refused(self):
        opener = mock.Mock()
        opener.open.side_effect = [_redirect_error("https://lan.example/x")]
        priv = [(2, 1, 6, "", ("192.168.1.20", 443))]
        with mock.patch.object(http, "_OPENER", opener), \
                mock.patch.object(http.socket, "getaddrinfo", return_value=priv):
            self.assertIsNone(http._request("https://start.example/x", 5, None))
        self.assertEqual(opener.open.call_count, 1)

    def test_redirect_chain_is_capped_at_three_hops(self):
        body, opener = self._follow([
            _redirect_error("https://a.example/1"),
            _redirect_error("https://a.example/2"),
            _redirect_error("https://a.example/3"),
            _redirect_error("https://a.example/4"),
        ])
        self.assertIsNone(body)
        self.assertEqual(opener.open.call_count, 4)

    def test_redirects_are_budgeted_between_hops(self):
        def slow_redirect(*args, **kwargs):
            time.sleep(0.12)
            raise _redirect_error("https://next.example/again")

        opener = mock.Mock()
        opener.open.side_effect = slow_redirect
        http.begin_route(0.25)
        try:
            started = time.monotonic()
            with mock.patch.object(http, "_OPENER", opener), \
                    mock.patch.object(http.socket, "getaddrinfo", return_value=self.infos):
                self.assertIsNone(http._request("https://start.example/x", 20, None))
            elapsed = time.monotonic() - started
        finally:
            http.end_route()
        self.assertLess(elapsed, 0.8, elapsed)
        self.assertGreaterEqual(opener.open.call_count, 1)


class CacheKeyTests(unittest.TestCase):
    """A9: the cache key must be injective for hostile header values."""

    def test_awkward_header_values_do_not_collide(self):
        one = http._cache_key("text", "https://x/feed", {"Referer": "a&b=c"})
        two = http._cache_key("text", "https://x/feed", {"Referer": "a", "b": "c"})
        self.assertNotEqual(one, two)

    def test_header_keys_are_case_insensitive(self):
        one = http._cache_key("text", "https://x/feed", {"Referer": "a"})
        two = http._cache_key("text", "https://x/feed", {"referer": "a"})
        self.assertEqual(one, two)


if __name__ == "__main__":
    unittest.main()
