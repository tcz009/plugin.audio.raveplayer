# -*- coding: utf-8 -*-
"""Offline tests for the /api/resolve result cache and single-flight."""

import os
import sys
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODULE = os.path.join(ROOT, "script.module.raveresolver")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(MODULE, "resources", "lib"))
sys.path.insert(0, HERE)

from resolver.base import Resolution  # noqa: E402
from resolver.http import HttpResponse  # noqa: E402
from resolver.service import ServiceClient, ServiceResultCache  # noqa: E402

URL = "https://www.podomatic.com/podcasts/show/episodes/1"
PAYLOAD = {
    "url": "https://cdn.example.com/episode.mp3",
    "provider": "podomatic",
    "expires_in": 1000,
}
SERVICE = "http://nas:8080/api/resolve"


class _CountingHTTP(object):
    """Return one queued response per request and count calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.lock = threading.Lock()

    def request(self, *_args, **_kwargs):
        with self.lock:
            self.calls += 1
            response = self.responses.pop(0)
        return response


class _BlockingHTTP(object):
    """First request blocks until ``release``; later calls also block."""

    def __init__(self, response):
        self.response = response
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self.lock = threading.Lock()

    def request(self, *_args, **_kwargs):
        with self.lock:
            self.calls += 1
        self.started.set()
        self.release.wait(5.0)
        return self.response


def response(payload, status=200, headers=None):
    import json

    return HttpResponse(status, headers or {},
                        json.dumps(payload).encode("utf-8"), SERVICE)


class ServiceResultCacheTests(unittest.TestCase):
    def test_ttl_is_clamped_to_expires(self):
        now = [1000.0]
        cache = ServiceResultCache(ttl=300, clock=lambda: now[0])
        result = Resolution("https://cdn.example.com/a.mp3",
                            expires_at=now[0] + 30)
        self.assertTrue(cache.put(URL, None, result))
        self.assertIsNotNone(cache.get(URL))
        now[0] += 29
        self.assertIsNotNone(cache.get(URL))
        now[0] += 2
        self.assertIsNone(cache.get(URL))
        self.assertEqual(len(cache), 0)

    def test_default_ttl_bounds_a_long_lived_result(self):
        now = [1000.0]
        cache = ServiceResultCache(ttl=300, clock=lambda: now[0])
        result = Resolution("https://cdn.example.com/a.mp3",
                            expires_at=now[0] + 10000)
        cache.put(URL, None, result)
        now[0] += 299
        self.assertIsNotNone(cache.get(URL))
        now[0] += 2
        self.assertIsNone(cache.get(URL))

    def test_already_expired_result_is_not_cached(self):
        now = [1000.0]
        cache = ServiceResultCache(ttl=300, clock=lambda: now[0])
        result = Resolution("https://cdn.example.com/a.mp3",
                            expires_at=now[0] - 1)
        self.assertFalse(cache.put(URL, None, result))
        self.assertIsNone(cache.get(URL))

    def test_cache_is_lru_bounded(self):
        now = [1000.0]
        cache = ServiceResultCache(ttl=300, max_entries=2,
                                   clock=lambda: now[0])
        for index in range(3):
            cache.put("https://example.com/%d" % index, None,
                      Resolution("https://cdn.example.com/%d.mp3" % index))
        self.assertEqual(len(cache), 2)
        self.assertIsNone(cache.get("https://example.com/0"))
        self.assertIsNotNone(cache.get("https://example.com/1"))
        self.assertIsNotNone(cache.get("https://example.com/2"))

    def test_the_requested_url_is_the_key(self):
        now = [1000.0]
        cache = ServiceResultCache(ttl=300, clock=lambda: now[0])
        cache.put(URL, "podomatic", Resolution("https://cdn/a.mp3"))
        # The provider hint is derived from the URL, so it must not split the
        # cache for the same page.
        self.assertIsNotNone(cache.get(URL, "mega"))
        self.assertIsNotNone(cache.get(URL, "podomatic"))

    def test_single_flight_identical_resolves(self):
        now = [1000.0]
        cache = ServiceResultCache(ttl=300, clock=lambda: now[0])
        started = threading.Event()
        release = threading.Event()
        calls = []

        def factory():
            calls.append(1)
            started.set()
            release.wait(5.0)
            return Resolution("https://cdn.example.com/a.mp3")

        results = []
        threads = [threading.Thread(target=lambda: results.append(
            cache.run(URL, None, factory))) for _index in range(2)]
        threads[0].start()
        self.assertTrue(started.wait(2.0))
        threads[1].start()
        release.set()
        for thread in threads:
            thread.join(5.0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(cache.get(URL).url, "https://cdn.example.com/a.mp3")

    def test_errors_are_not_cached(self):
        now = [1000.0]
        cache = ServiceResultCache(ttl=300, clock=lambda: now[0])
        calls = []

        def factory():
            calls.append(1)
            if len(calls) == 1:
                raise ValueError("transient")
            return Resolution("https://cdn.example.com/a.mp3")

        with self.assertRaises(ValueError):
            cache.run(URL, None, factory)
        self.assertIsNone(cache.get(URL))
        self.assertEqual(cache.run(URL, None, factory).url,
                         "https://cdn.example.com/a.mp3")
        self.assertEqual(len(calls), 2)


class ServiceClientCacheTests(unittest.TestCase):
    def client(self, http, cache):
        return ServiceClient("http://nas:8080", token="token", timeout=7,
                             http=http, dns_resolver=lambda _h, _p: [
                                 "93.184.216.34"],
                             result_cache=cache)

    def test_second_identical_call_uses_the_cache(self):
        now = [1000.0]
        cache = ServiceResultCache(ttl=300, clock=lambda: now[0])
        http = _CountingHTTP([response(PAYLOAD)])
        client = self.client(http, cache)
        first = client.resolve(URL, provider="podomatic")
        second = client.resolve(URL, provider="podomatic")
        self.assertEqual(first.url, second.url)
        self.assertEqual(http.calls, 1)
        now[0] += 301
        http.responses.append(response(PAYLOAD))
        client.resolve(URL, provider="podomatic")
        self.assertEqual(http.calls, 2)

    def test_concurrent_identical_calls_share_one_request(self):
        now = [1000.0]
        cache = ServiceResultCache(ttl=300, clock=lambda: now[0],
                                   wait_timeout=5.0)
        http = _BlockingHTTP(response(PAYLOAD))
        client = self.client(http, cache)
        results = []
        errors = []

        def run():
            try:
                results.append(client.resolve(URL, provider="podomatic"))
            except Exception as exc:  # noqa: BLE001 - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=run) for _index in range(2)]
        threads[0].start()
        self.assertTrue(http.started.wait(2.0))
        threads[1].start()
        http.release.set()
        for thread in threads:
            thread.join(5.0)
        self.assertEqual(errors, [])
        self.assertEqual(http.calls, 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].url, results[1].url)

    def test_different_urls_are_not_coalesced(self):
        now = [1000.0]
        cache = ServiceResultCache(ttl=300, clock=lambda: now[0])
        http = _CountingHTTP([response(PAYLOAD), response(PAYLOAD)])
        client = self.client(http, cache)
        client.resolve(URL)
        client.resolve(URL + "/2")
        self.assertEqual(http.calls, 2)


if __name__ == "__main__":
    unittest.main()
