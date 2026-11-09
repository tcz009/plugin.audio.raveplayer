# -*- coding: utf-8 -*-
"""Offline tests for the per-domain resolver rate limiter.

The limiter mirrors the web resolver's bucket: one state per registrable
domain, LRU-bounded, with a 429 back-off that adapter and service fallback
share.  No network is used.
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODULE = os.path.join(ROOT, "script.module.raveresolver")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(MODULE, "resources", "lib"))
sys.path.insert(0, HERE)

from resolver import Resolver  # noqa: E402
from resolver.base import (AdapterNotReady, RateLimited,  # noqa: E402
                           Resolution)
from resolver.cache import Cache  # noqa: E402
from resolver.ratelimit import (DomainRateLimiter, MAX_KEYS,  # noqa: E402
                                domain_for, registrable_domain)
from resolver_fakes import FakeHTTP, fake_dns, make_settings, response  # noqa: E402

MEDIAFIRE_PAGE = "https://www.mediafire.com/file/abc123/set.mp3"
SIGNED = "https://download239.mediafire.com/abc123/set.mp3?token=s"


class RegistrableDomainTests(unittest.TestCase):
    def test_subdomains_share_the_registrable_domain(self):
        self.assertEqual(registrable_domain("mediafire.com"), "mediafire.com")
        self.assertEqual(registrable_domain("www.mediafire.com"),
                         "mediafire.com")
        self.assertEqual(registrable_domain("download239.mediafire.com"),
                         "mediafire.com")
        self.assertEqual(registrable_domain("drive.google.com"), "google.com")
        self.assertEqual(registrable_domain("docs.google.com"), "google.com")

    def test_multi_label_suffix_and_ip(self):
        self.assertEqual(registrable_domain("n1.example.co.uk"),
                         "example.co.uk")
        self.assertEqual(registrable_domain("gfs1.userstorage.mega.co.nz"),
                         "mega.co.nz")
        self.assertEqual(registrable_domain("10.0.0.5"), "10.0.0.5")
        self.assertEqual(registrable_domain("localhost"), "localhost")
        self.assertEqual(registrable_domain(""), "")

    def test_domain_for_url(self):
        self.assertEqual(domain_for(MEDIAFIRE_PAGE), "mediafire.com")
        self.assertEqual(domain_for("not a url"), "")


class LimiterTests(unittest.TestCase):
    def limiter(self, now, **kwargs):
        return DomainRateLimiter(
            rate_per_minute=60, burst=3, clock=lambda: now[0], **kwargs)

    def test_burst_then_refill(self):
        now = [1000.0]
        limiter = self.limiter(now)
        for _index in range(3):
            self.assertEqual(limiter.take(MEDIAFIRE_PAGE), 0)
        self.assertGreaterEqual(limiter.take(MEDIAFIRE_PAGE), 1)
        now[0] += 1.0
        self.assertEqual(limiter.take(MEDIAFIRE_PAGE), 0)

    def test_shared_subdomains_share_one_bucket(self):
        now = [1000.0]
        limiter = self.limiter(now)
        for _index in range(3):
            limiter.take("https://n1.mediafire.com/file/a.mp3")
        # A different subdomain must not get a fresh burst.
        self.assertGreaterEqual(
            limiter.take("https://download9.mediafire.com/file/a.mp3"), 1)
        # But another provider is unaffected.
        self.assertEqual(
            limiter.take("https://drive.google.com/file/d/x/view"), 0)

    def test_block_honours_retry_after_and_does_not_shorten(self):
        now = [1000.0]
        limiter = self.limiter(now)
        self.assertEqual(limiter.block(MEDIAFIRE_PAGE, 7), 7)
        self.assertEqual(limiter.take(MEDIAFIRE_PAGE), 7)
        # A second, shorter 429 must not shorten the existing back-off.
        limiter.block(MEDIAFIRE_PAGE, 2)
        self.assertEqual(limiter.take(MEDIAFIRE_PAGE), 7)
        now[0] += 8.0
        self.assertEqual(limiter.take(MEDIAFIRE_PAGE), 0)

    def test_block_is_capped(self):
        now = [1000.0]
        limiter = self.limiter(now)
        self.assertEqual(limiter.block(MEDIAFIRE_PAGE, 9999), 120)
        self.assertEqual(limiter.block(MEDIAFIRE_PAGE, 0), 1)

    def test_state_is_lru_bounded(self):
        now = [1000.0]
        limiter = self.limiter(now, max_keys=3)
        for index in range(5):
            limiter.take("https://host%d.example/%d" % (index, index))
        self.assertEqual(len(limiter), 3)
        self.assertLessEqual(len(limiter), MAX_KEYS)
        # The oldest key was evicted, so it gets a fresh burst.
        self.assertEqual(limiter.take("https://host0.example/again"), 0)
        self.assertEqual(len(limiter), 3)

    def test_disabled_rate_never_blocks(self):
        now = [1000.0]
        limiter = DomainRateLimiter(rate_per_minute=0, burst=1,
                                    clock=lambda: now[0])
        for _index in range(50):
            self.assertEqual(limiter.take(MEDIAFIRE_PAGE), 0)


class _FailingAdapter(object):
    name = "mediafire"

    def __init__(self, error):
        self.error = error
        self.calls = 0

    def matches(self, _url):
        return True

    def resolve(self, _url):
        self.calls += 1
        raise self.error


class _ReadyAdapter(object):
    name = "mediafire"

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def matches(self, _url):
        return True

    def resolve(self, _url):
        self.calls += 1
        return self.result


class ManagerLimiterTests(unittest.TestCase):
    def resolver(self, adapter, http=None, limiter=None, service=None):
        return Resolver(
            settings=make_settings(), http=http or FakeHTTP([]),
            cache=Cache(tempfile.mkdtemp(), ttl=1),
            dns_resolver=fake_dns, adapters=[adapter],
            service=service, limiter=limiter)

    def test_adapter_429_blocks_the_next_attempt_without_a_call(self):
        now = [1000.0]
        limiter = DomainRateLimiter(rate_per_minute=60, burst=5,
                                    clock=lambda: now[0])
        adapter = _FailingAdapter(RateLimited("slow", retry_after=9))
        resolver = self.resolver(adapter, limiter=limiter)
        with self.assertRaises(RateLimited) as caught:
            resolver.resolve(MEDIAFIRE_PAGE)
        self.assertEqual(caught.exception.retry_after, 9)
        self.assertFalse(caught.exception.fallback)
        with self.assertRaises(RateLimited):
            resolver.resolve(MEDIAFIRE_PAGE)
        self.assertEqual(adapter.calls, 1)
        now[0] += 10.0
        resolved = Resolution(SIGNED)
        resolver = self.resolver(_ReadyAdapter(resolved), limiter=limiter)
        self.assertEqual(resolver.resolve(MEDIAFIRE_PAGE).url, SIGNED)

    def test_adapter_429_does_not_fall_back_to_service(self):
        http = FakeHTTP([])
        adapter = _FailingAdapter(RateLimited("slow", retry_after=30))
        resolver = Resolver(
            settings=make_settings(
                resolver_service_url="http://nas:8080",
                resolver_service_token="token"),
            http=http, cache=Cache(tempfile.mkdtemp(), ttl=1),
            dns_resolver=fake_dns, adapters=[adapter])
        with self.assertRaises(RateLimited):
            resolver.resolve(MEDIAFIRE_PAGE)
        self.assertEqual(http.count(), 0)

    def test_service_429_blocks_the_domain_for_both_paths(self):
        http = FakeHTTP([response(
            {"ok": False, "code": "rate_limited"},
            status=429, headers={"Retry-After": "11"},
            url="http://nas:8080/api/resolve")])
        resolver = Resolver(
            settings=make_settings(
                resolver_service_url="http://nas:8080",
                resolver_service_token="token"),
            http=http, cache=Cache(tempfile.mkdtemp(), ttl=1),
            dns_resolver=fake_dns,
            adapters=[_FailingAdapter(AdapterNotReady("native missing"))])
        with self.assertRaises(RateLimited) as caught:
            resolver.resolve(MEDIAFIRE_PAGE)
        self.assertEqual(caught.exception.retry_after, 11)
        self.assertEqual(http.count(), 1)
        # The provider's domain is blocked, so a second attempt is refused
        # before either the adapter or the service is called.
        with self.assertRaises(RateLimited):
            resolver.resolve(MEDIAFIRE_PAGE)
        self.assertEqual(http.count(), 1)

    def test_direct_audio_is_not_gated(self):
        now = [1000.0]
        limiter = DomainRateLimiter(rate_per_minute=1, burst=1,
                                    clock=lambda: now[0])
        resolver = Resolver(
            settings=make_settings(), http=FakeHTTP([]),
            cache=Cache(tempfile.mkdtemp(), ttl=1), dns_resolver=fake_dns,
            service=False, limiter=limiter)
        for _index in range(20):
            result = resolver.resolve(
                "https://archive.org/download/x/%d.mp3" % _index)
            self.assertEqual(result.provider, "direct")


if __name__ == "__main__":
    unittest.main()
