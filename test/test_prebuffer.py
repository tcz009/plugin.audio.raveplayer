# -*- coding: utf-8 -*-
"""Bounded pre-buffer for slow direct sources (Toronto MP3s)."""

import contextlib
import os
import socket
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import routes  # noqa: E402

PUBLIC_INFOS = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
TORONTO = "https://www.torontoravemixtapearchive.com/files/mixtape/a.mp3"
FAST = "https://example.test/a.mp3"


class FakeResponse(object):
    def __init__(self, chunk=b"x" * 100):
        self.chunk = chunk
        self.read_size = None

    def read(self, size):
        self.read_size = size
        return self.chunk


class PrebufferTests(unittest.TestCase):
    def _open(self, response):
        @contextlib.contextmanager
        def opener(url, timeout=None):
            yield response
        return opener

    def test_reads_first_chunk_with_64k_ceiling(self):
        response = FakeResponse(b"abc")
        with mock.patch.object(routes.http, "open_media", self._open(response)):
            self.assertTrue(routes._prebuffer_stream(TORONTO))
        self.assertEqual(response.read_size, routes.PREBUFFER_BYTES)

    def test_empty_or_timeout_is_advisory(self):
        with mock.patch.object(routes.http, "open_media", self._open(FakeResponse(b""))):
            self.assertFalse(routes._prebuffer_stream(TORONTO))

        @contextlib.contextmanager
        def broken(url, timeout=None):
            raise TimeoutError("slow")
            yield  # pragma: no cover
        with mock.patch.object(routes.http, "open_media", broken):
            self.assertFalse(routes._prebuffer_stream(TORONTO))

    def test_host_gate_leaves_fast_sources_alone(self):
        self.assertTrue(routes._should_prebuffer(TORONTO))
        self.assertFalse(routes._should_prebuffer(FAST))


class PrebufferRouteTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.RESOLVED[:]
        self.dns = mock.patch.object(routes.http.socket, "getaddrinfo",
                                     return_value=PUBLIC_INFOS)
        self.dns.start()
        self.addCleanup(self.dns.stop)
        self.setting = mock.patch.object(routes.kodi, "setting_bool", return_value=True)
        self.setting.start()
        self.addCleanup(self.setting.stop)

    def test_prebuffer_runs_and_spinner_closes_before_resolve(self):
        events = []
        class FakeTuning(object):
            expired = False
            def __init__(self, label): pass
            def start(self): pass
            def close(self): events.append("close")
            def cancelled(self): return False
        def resolve(handle, ok, item):
            events.append(("resolve", ok))
        with mock.patch.object(routes.spinner, "TuningSpinner", FakeTuning), \
                mock.patch.object(routes, "_prebuffer_stream", return_value=True) as pre, \
                mock.patch.object(routes.xbmcplugin, "setResolvedUrl", side_effect=resolve):
            routes.play(1, {"url": TORONTO, "label": "Toronto"})
        pre.assert_called_once()
        self.assertLess(events.index("close"), [i for i, e in enumerate(events) if isinstance(e, tuple) and e[0] == "resolve"][0])

    def test_timeout_shows_notice_but_still_resolves(self):
        events = []
        class FakeTuning(object):
            expired = False
            def __init__(self, label): pass
            def start(self): pass
            def close(self): events.append("close")
            def cancelled(self): return False
        with mock.patch.object(routes.spinner, "TuningSpinner", FakeTuning), \
                mock.patch.object(routes, "_prebuffer_stream", return_value=False), \
                mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.xbmcplugin, "setResolvedUrl") as resolve:
            routes.play(1, {"url": TORONTO, "label": "Toronto"})
        notify.assert_called()
        self.assertTrue(resolve.called)
        self.assertEqual(resolve.call_args[0][1], True)

    def test_fast_source_never_prebuffers(self):
        with mock.patch.object(routes, "_prebuffer_stream",
                               side_effect=AssertionError("must not prebuffer")), \
                mock.patch.object(routes.xbmcplugin, "setResolvedUrl") as resolve:
            routes.play(1, {"url": FAST, "label": "Fast"})
        self.assertTrue(resolve.called)


if __name__ == "__main__":
    unittest.main()
