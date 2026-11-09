# -*- coding: utf-8 -*-
"""Offline tests for the web-only JSON client (no network, injected opener)."""

import json
import os
import sys
import unittest
import urllib.error
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)

from resources.lib import webapi  # noqa: E402

BASE = "http://192.168.1.179:8097"


class FakeResponse(object):
    def __init__(self, body=b"", status=200, headers=None, url=""):
        self._body = body
        self.status = status
        self.headers = dict(headers or {})
        self._url = url
        self.closed = False

    def read(self, amount=-1):
        if amount is None or amount < 0:
            amount = len(self._body)
        return self._body[:amount]

    def geturl(self):
        return self._url

    def close(self):
        self.closed = True


class FakeOpener(object):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.timeouts = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        response = self.responses.pop(0) if self.responses else FakeResponse(
            body=b"{}")
        if isinstance(response, Exception):
            raise response
        return response


def json_response(payload, status=200):
    body = json.dumps(payload).encode("utf-8")
    return FakeResponse(body=body, status=status,
                        headers={"Content-Type": "application/json",
                                 "Content-Length": str(len(body))})


def payload(**extra):
    doc = {
        "title": "20bensons.com",
        "sub": "Old-skool rave MP3s",
        "items": [
            {"label": "Dreamscape 19", "sub": "1994 · Helter Skelter",
             "play": "https://20bensons.com/mp3/Dreamscape_19.mp3",
             "art": "/static/art/20bensons.png", "fact": "1994",
             "fav": {"kind": "stream"}, "download": {"source": "20bensons"}},
            {"label": "YouTube hand-off", "play": "https://youtube.com/watch?v=1"},
            {"label": "Relative set", "play": "/api/ezgarage/abc/stream",
             "art": "static/art/djez.png", "sub": "DJ EZ"},
            {"label": "Folder row", "open": "/api/20bensons"},
        ],
        "total": 234,
        "pager": {"page": 2, "pages": 6, "total": 234, "per_page": 40,
                  "next": "/api/20bensons?page=3"},
        "next": "/api/20bensons?page=3",
    }
    doc.update(extra)
    return doc


class _CacheMixin(object):
    def setUp(self):
        webapi.clear_cache()


class BaseTests(_CacheMixin, unittest.TestCase):

    def test_normalise_base(self):
        self.assertEqual(webapi.normalise_base("192.168.1.179:8097"),
                         BASE)
        self.assertEqual(webapi.normalise_base(BASE + "/"), BASE)
        self.assertEqual(webapi.normalise_base(" https://example.test/app/ "),
                         "https://example.test/app")
        for bad in ("", "   ", "ftp://example.test", "http://u:p@example.test",
                    "http://example.test?q=1", "http://example.test#frag",
                    "http://example.test:99999", "http://exa\nmple.test"):
            with self.subTest(value=bad):
                self.assertEqual(webapi.normalise_base(bad), "")

    def test_resolve_url(self):
        self.assertEqual(webapi.resolve_url("/api/x", BASE),
                         BASE + "/api/x")
        self.assertEqual(webapi.resolve_url("static/a.png", BASE),
                         BASE + "/static/a.png")
        self.assertEqual(webapi.resolve_url("https://cdn.test/a.mp3", BASE),
                         "https://cdn.test/a.mp3")
        self.assertEqual(webapi.resolve_url("//cdn.test/a.mp3", BASE),
                         "http://cdn.test/a.mp3")
        for bad in ("file:///etc/passwd", "javascript:alert(1)", "", None):
            with self.subTest(value=bad):
                self.assertEqual(webapi.resolve_url(bad, BASE), "")

    def test_playable_url_rejects_external_pages_and_private_absolutes(self):
        self.assertEqual(webapi.playable_url("/api/ukraves/1/stream", BASE),
                         BASE + "/api/ukraves/1/stream")
        self.assertEqual(
            webapi.playable_url("https://20bensons.com/a.mp3", BASE),
            "https://20bensons.com/a.mp3")
        self.assertEqual(
            webapi.playable_url("https://youtu.be/abc", BASE), "")
        self.assertEqual(
            webapi.playable_url("https://www.youtube.com/watch?v=abc", BASE), "")
        self.assertEqual(
            webapi.playable_url("http://192.168.1.50/secret.mp3", BASE), "")

    def test_api_url_stays_on_the_service(self):
        client = webapi.Client(BASE)
        self.assertEqual(client.api_url("/api/live", 1),
                         BASE + "/api/live")
        self.assertEqual(client.api_url("/api/live", 2),
                         BASE + "/api/live?page=2")
        self.assertEqual(client.api_url("/api/live?feed=1", 3),
                         BASE + "/api/live?feed=1&page=3")
        with self.assertRaises(webapi.WebAPIError):
            client.api_url("https://elsewhere.test/api/live", 1)


class FetchTests(_CacheMixin, unittest.TestCase):
    def test_token_header_and_page_query(self):
        opener = FakeOpener([json_response(payload())])
        client = webapi.Client(BASE, "secret-token", opener=opener)
        page = client.page("/api/20bensons", 2)
        self.assertEqual(len(opener.requests), 1)
        request = opener.requests[0]
        self.assertEqual(request.full_url, BASE + "/api/20bensons?page=2")
        self.assertEqual(request.get_header("Authorization"),
                         "Bearer secret-token")
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(opener.timeouts[0], webapi.DEFAULT_TIMEOUT)
        self.assertEqual(page.page, 2)
        self.assertEqual(page.pages, 6)
        self.assertEqual(page.total, 234)
        self.assertEqual(page.per_page, 40)
        self.assertTrue(page.has_next)
        self.assertEqual(page.next_page, 3)

    def test_rows_resolve_relative_play_and_art_and_drop_external(self):
        opener = FakeOpener([json_response(payload())])
        page = webapi.Client(BASE, "t", opener=opener).page("/api/20bensons", 1)
        self.assertEqual([row.label for row in page.rows],
                         ["Dreamscape 19", "Relative set"])
        first, relative = page.rows
        self.assertEqual(first.play,
                         "https://20bensons.com/mp3/Dreamscape_19.mp3")
        self.assertEqual(first.art, BASE + "/static/art/20bensons.png")
        self.assertEqual(first.fact, "1994")
        self.assertEqual(relative.play, BASE + "/api/ezgarage/abc/stream")
        self.assertEqual(relative.art, BASE + "/static/art/djez.png")
        items = webapi.kodi_items(page)
        self.assertEqual(items[0]["url"], first.play)
        self.assertEqual(items[0]["path"], first.play)
        self.assertEqual(items[0]["label"], "Dreamscape 19")

    def test_cursor_pager_and_bare_list_shapes(self):
        page = webapi.parse_page({
            "items": [{"label": "One", "play": "/api/x/1/stream"}],
            "pager": {"page": 1, "pages": None, "total": None,
                      "next": "/api/ukraves?page=2"},
            "next": "/api/ukraves?page=2",
        }, requested_page=1, base=BASE)
        self.assertIsNone(page.pages)
        self.assertIsNone(page.total)
        self.assertTrue(page.has_next)
        self.assertEqual(page.next_page, 2)

        bare = webapi.parse_page(
            [{"label": "One", "play": "/api/x/1/stream"}],
            requested_page=1, base=BASE)
        self.assertEqual(len(bare.rows), 1)
        self.assertFalse(bare.has_next)

    def test_short_cache_avoids_a_second_request(self):
        opener = FakeOpener([json_response(payload())])
        clock = [1000.0]
        client = webapi.Client(BASE, "t", opener=opener, cache_ttl=60,
                               clock=lambda: clock[0])
        first = client.page("/api/20bensons", 1)
        clock[0] += 30
        second = client.page("/api/20bensons", 1)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(first.rows, second.rows)
        clock[0] += 31
        opener.responses.append(json_response(payload()))
        client.page("/api/20bensons", 1)
        self.assertEqual(len(opener.requests), 2)

    def test_response_byte_cap(self):
        opener = FakeOpener([FakeResponse(body=b"{" + b"x" * 200 + b"}")])
        client = webapi.Client(BASE, "t", opener=opener, max_bytes=64)
        with self.assertRaises(webapi.WebAPIError):
            client.page("/api/x", 1)

    def test_declared_content_length_cap(self):
        response = FakeResponse(
            body=b"{}", headers={"Content-Length": "999999"})
        with self.assertRaises(webapi.WebAPIError):
            webapi.Client(BASE, "t", opener=FakeOpener([response]),
                          max_bytes=64).page("/api/x", 1)

    def test_off_host_redirect_is_refused(self):
        error = urllib.error.HTTPError(
            BASE + "/api/x", 302, "Found",
            {"Location": "http://evil.test/api/x"}, None)
        opener = FakeOpener([error])
        with self.assertRaises(webapi.WebAPIError):
            webapi.Client(BASE, "t", opener=opener).page("/api/x", 1)
        self.assertEqual(len(opener.requests), 1)

    def test_same_origin_redirect_is_followed(self):
        error = urllib.error.HTTPError(
            BASE + "/api/x", 302, "Found",
            {"Location": BASE + "/api/y"}, None)
        opener = FakeOpener([error, json_response({"items": []})])
        page = webapi.Client(BASE, "t", opener=opener).page("/api/x", 1)
        self.assertEqual(page.rows, ())
        self.assertEqual([request.full_url for request in opener.requests],
                         [BASE + "/api/x", BASE + "/api/y"])
        self.assertEqual(opener.requests[1].get_header("Authorization"),
                         "Bearer t")

    def test_http_error_and_bad_json_raise_webapierror(self):
        with self.assertRaises(webapi.WebAPIError):
            webapi.Client(BASE, "t", opener=FakeOpener([
                FakeResponse(body=b"{}", status=401)])).page("/api/x", 1)
        with self.assertRaises(webapi.WebAPIError):
            webapi.Client(BASE, "t", opener=FakeOpener([
                FakeResponse(body=b"not json")])).page("/api/x", 1)


if __name__ == "__main__":
    unittest.main()
