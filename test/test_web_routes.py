# -*- coding: utf-8 -*-
"""Offline route tests for the web-only sources (no network, fake client)."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)

import xbmcplugin  # noqa: E402

from resources.lib import routes, webapi  # noqa: E402

BASE = "http://192.168.1.179:8097"


class FakeClient(object):
    def __init__(self, pages=None):
        self.base = BASE
        self.pages = list(pages or [])

    def page(self, path, page=1):
        if self.pages:
            value = self.pages.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        return webapi.WebPage((), page=page)


def rows_payload():
    return [
        {"label": "UK Rave Mix", "sub": "1994 · Sanctuary", "fact": "1994",
         "url": "https://web.test/static/art/ukraves.png",
         "art": "https://web.test/static/art/ukraves.png",
         "download": None},
        {"label": "EZ Set", "sub": "DJ EZ", "fact": "set",
         "url": BASE + "/api/ezgarage/abc/stream", "art": "",
         "download": None},
    ]


def web_page(page=1, pages=2, total=80, has_next=True):
    return webapi.WebPage(
        tuple(webapi.WebRow(
            label=row["label"], sub=row["sub"], play=row["url"],
            art=row["art"], fact=row["fact"], download=row["download"])
              for row in rows_payload()),
        page=page, pages=pages, total=total, per_page=40,
        has_next=has_next, next_page=page + 1 if has_next else None)


class WebRouteTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]
        del xbmcplugin.RESOLVED[:]
        del xbmcplugin.CONTENT[:]
        webapi.clear_cache()

    def _params(self, url):
        return routes.params_from_argv(
            ["plugin://plugin.audio.raveplayer/", "1", url.split("?", 1)[1]])

    def test_web_list_renders_playable_rows_and_page_nav(self):
        with mock.patch.object(routes, "_web_client",
                               return_value=FakeClient([web_page()])):
            routes.web_list(1, {"source": "ukraves"})
        labels = [item["label"] for item in xbmcplugin.ITEMS]
        self.assertIn("UK Rave Mix", labels)
        self.assertIn("EZ Set", labels)
        self.assertIn("Next page  ›", labels)
        item = next(row for row in xbmcplugin.ITEMS
                    if row["label"] == "UK Rave Mix")
        self.assertFalse(item["isFolder"])
        params = self._params(item["url"])
        self.assertEqual(params["mode"], "web_play")
        self.assertEqual(params["url"], rows_payload()[0]["url"])
        self.assertEqual(item["label2"], "1994")
        self.assertIn("Sanctuary", item["info"]["video"]["plot"])
        next_row = next(row for row in xbmcplugin.ITEMS
                        if row["label"] == "Next page  ›")
        self.assertIn("source=ukraves", next_row["url"])
        self.assertIn("page=2", next_row["url"])

    def test_web_list_unconfigured_or_failed_renders_a_retry_plate(self):
        with mock.patch.object(routes, "_web_client", return_value=None), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.web_list(1, {"source": "20bensons"})
        self.assertTrue(notify.called)
        labels = [item["label"] for item in xbmcplugin.ITEMS]
        self.assertTrue(any("Nothing from 20bensons.com" in label
                            for label in labels))
        retry = next(item for item in xbmcplugin.ITEMS
                     if "Nothing from" in item["label"])
        self.assertIn("mode=web_list", retry["url"])
        self.assertIn("source=20bensons", retry["url"])

    def test_web_list_unknown_source_is_a_quiet_notice(self):
        with mock.patch.object(routes.kodi, "notify") as notify:
            routes.web_list(1, {"source": "nope"})
        self.assertTrue(notify.called)
        self.assertEqual(xbmcplugin.ITEMS, [])

    def test_web_play_relative_uses_the_service_origin(self):
        settings = {"resolver_service_url": BASE,
                    "resolver_service_token": "token"}
        client = mock.Mock()
        client.signed_play.return_value = ""
        with mock.patch.object(routes.kodi, "setting",
                               side_effect=lambda name, default="": settings.get(
                                   name, default)), \
                mock.patch.object(routes, "_web_client", return_value=client):
            routes.web_play(1, {"url": "/api/ezgarage/abc/stream",
                                "label": "EZ Set"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["path"], BASE + "/api/ezgarage/abc/stream")
        self.assertEqual(resolved["properties"]["IsPlayable"], "true")
        # The same-origin row never runs a public-DNS check on the LAN base.
        self.assertTrue(client.signed_play.called)

    def test_web_play_absolute_public_stream_is_direct(self):
        public = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with mock.patch.object(routes.kodi, "setting", return_value=""), \
                mock.patch.object(routes.http.socket, "getaddrinfo",
                                  return_value=public):
            routes.web_play(1, {"url": "https://20bensons.com/mp3/a.mp3",
                                "label": "20bensons set"})
        self.assertEqual(xbmcplugin.RESOLVED[-1]["path"],
                         "https://20bensons.com/mp3/a.mp3")

    def test_web_play_absolute_row_is_refused_when_dns_is_private(self):
        private = [(2, 1, 6, "", ("10.0.0.5", 443))]
        with mock.patch.object(routes.kodi, "setting", return_value=""), \
                mock.patch.object(routes.http.socket, "getaddrinfo",
                                  return_value=private):
            routes.web_play(1, {"url": "https://evil.example/mp3/a.mp3",
                                "label": "bad"})
        self.assertFalse(xbmcplugin.RESOLVED[-1]["ok"])

    def test_web_play_refuses_foreign_private_and_platform_urls(self):
        for value in ("http://192.168.1.50/secret.mp3",
                      "https://youtu.be/abc", "file:///etc/passwd"):
            del xbmcplugin.RESOLVED[:]
            with self.subTest(url=value), \
                    mock.patch.object(routes.kodi, "setting", return_value=""):
                routes.web_play(1, {"url": value, "label": "bad"})
            self.assertEqual(len(xbmcplugin.RESOLVED), 1)
            self.assertFalse(xbmcplugin.RESOLVED[-1]["ok"])

    def test_web_live_renders_one_playable_station_row(self):
        with mock.patch.object(routes, "web_live_stations",
                               return_value=[{
                                   "token": "dejavu", "name": "DejaVu FM",
                                   "url": "https://dejavufm.radioca.st/stream",
                                   "meta": "London rave radio"}]):
            routes.web_live(1, {"token": "dejavu"})
        item = xbmcplugin.ITEMS[0]
        self.assertFalse(item["isFolder"])
        params = self._params(item["url"])
        self.assertEqual(params["mode"], "web_play")
        self.assertEqual(params["live"], "1")
        self.assertIn("mode=web_play", item["url"])

    def test_web_live_stations_prefers_the_api_and_falls_back(self):
        client = FakeClient([webapi.WebPage((
            webapi.WebRow(label="DejaVu FM", play="https://api.test/dejavu"),
            webapi.WebRow(label="OSA Radio", play="https://api.test/osa"),
        ))])
        with mock.patch.object(routes, "_web_client", return_value=client):
            rows = routes.web_live_stations()
        self.assertEqual([row["url"] for row in rows],
                         ["https://api.test/dejavu", "https://api.test/osa"])
        with mock.patch.object(routes, "_web_client", return_value=None):
            fallback = routes.web_live_stations()
        self.assertEqual([row["name"] for row in fallback],
                         ["DejaVu FM", "OSA Radio"])
        self.assertTrue(all(row["url"].startswith("https://")
                            for row in fallback))

    def test_web_source_page_returns_plain_kodi_rows(self):
        with mock.patch.object(routes, "_web_client",
                               return_value=FakeClient([web_page()])):
            doc = routes.web_source_page("ukraves", 1)
        self.assertEqual(doc["page"], 1)
        self.assertEqual(doc["pages"], 2)
        self.assertEqual(doc["per_page"], 40)
        self.assertEqual(doc["rows"][0]["url"], rows_payload()[0]["url"])
        self.assertEqual(doc["rows"][0]["path"], rows_payload()[0]["url"])
        with mock.patch.object(routes, "_web_client", return_value=None):
            self.assertIsNone(routes.web_source_page("ukraves", 1))


if __name__ == "__main__":
    unittest.main()
