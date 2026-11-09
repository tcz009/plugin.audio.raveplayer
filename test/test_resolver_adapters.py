# -*- coding: utf-8 -*-
"""Offline adapter tests: selection, direct, Mediafire, Drive, Podomatic.

Every network call is a queued fake; every hostname is resolved by the injected
public-IP resolver.  The suite asserts the fake was actually used.
"""

import base64
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
from resolver.base import (AdapterNotReady, BlockedURL, HostNotAllowed,  # noqa: E402
                           InvalidURL, NotFound, ProviderError, RateLimited,
                           UnsupportedURL)
from resolver.cache import Cache  # noqa: E402
from resolver.direct import DirectAdapter  # noqa: E402
from resolver.drive import (DriveNotAudio, DriveAdapter, UnknownDriveFile,  # noqa: E402
                            file_id, parse_confirm_form, view_url)
from resolver.mediafire import (MediafireAdapter, clean_page_url,  # noqa: E402
                                signed_url_from_page)
from resolver.podomatic import PodomaticAdapter  # noqa: E402
from resolver_fakes import (FakeHTTP, RecordingLogger, fake_dns,  # noqa: E402
                            make_settings, response)


def build(http=None, settings=None, **kwargs):
    return Resolver(settings=settings or make_settings(), http=http,
                    cache=Cache(tempfile.mkdtemp(), ttl=300),
                    dns_resolver=fake_dns, service=False, **kwargs)


class SelectionTests(unittest.TestCase):
    def test_provider_and_adapter_selection(self):
        resolver = build(FakeHTTP([]))
        cases = {
            "https://www.mediafire.com/file/abc/set.mp3": "mediafire",
            "https://drive.google.com/file/d/abcdefghij1234567890/view": "drive",
            "https://www.podomatic.com/podcasts/show/episodes/1": "podomatic",
            "https://mega.nz/file/abc12345#" + "A" * 43: "mega",
            "https://archive.org/download/x/a.mp3": "direct",
        }
        for url, provider in cases.items():
            with self.subTest(url=url):
                self.assertEqual(resolver.provider_for(url), provider)
                self.assertEqual(resolver.adapter_for(url).name, provider)
                if provider != "direct":
                    self.assertTrue(resolver.needs_resolution(url))
        self.assertFalse(resolver.needs_resolution(
            "https://archive.org/download/x/a.mp3"))

    def test_unknown_url_has_no_adapter(self):
        resolver = build(FakeHTTP([]))
        self.assertIsNone(resolver.adapter_for("https://example.com/watch/1"))
        with self.assertRaises(UnsupportedURL):
            resolver.resolve("https://example.com/watch/1", use_service=False)

    def test_explicit_provider_mismatch_is_invalid(self):
        resolver = build(FakeHTTP([]))
        with self.assertRaises(InvalidURL):
            resolver.resolve("https://archive.org/download/x/a.mp3",
                             provider="mediafire", use_service=False)

    def test_available_providers(self):
        resolver = build(FakeHTTP([]))
        self.assertEqual(resolver.available_providers(),
                         ["mediafire", "drive", "podomatic", "mega", "direct"])


class DirectTests(unittest.TestCase):
    def test_direct_audio_is_returned_without_fetching(self):
        http = FakeHTTP([])
        adapter = DirectAdapter(dns_resolver=fake_dns)
        result = adapter.resolve("https://archive.org/download/x/Set%201.mp3")
        self.assertEqual(result.url, "https://archive.org/download/x/Set%201.mp3")
        self.assertEqual(result.provider, "direct")
        self.assertEqual(result.title, "Set 1.mp3")
        self.assertEqual(http.count(), 0)

    def test_unknown_host_is_fallback_eligible(self):
        adapter = DirectAdapter(dns_resolver=fake_dns)
        with self.assertRaises(HostNotAllowed) as caught:
            adapter.resolve("https://unknown.example.com/a.mp3")
        self.assertTrue(caught.exception.fallback)

    def test_private_host_is_not_fallback_eligible(self):
        adapter = DirectAdapter(dns_resolver=fake_dns)
        with self.assertRaises(BlockedURL) as caught:
            adapter.resolve("http://127.0.0.1/a.mp3")
        self.assertFalse(caught.exception.fallback)

    def test_provider_page_is_never_treated_as_direct(self):
        adapter = DirectAdapter(dns_resolver=fake_dns)
        self.assertFalse(adapter.matches(
            "https://www.mediafire.com/file/abc/set.mp3"))
        with self.assertRaises(InvalidURL):
            adapter.resolve("https://www.mediafire.com/file/abc/set.mp3")

    def test_fragment_is_dropped(self):
        adapter = DirectAdapter(dns_resolver=fake_dns)
        result = adapter.resolve("https://archive.org/download/x/a.mp3#t=10")
        self.assertEqual(result.url, "https://archive.org/download/x/a.mp3")

    def test_resolver_direct_path(self):
        resolver = build(FakeHTTP([]))
        result = resolver.resolve("https://archive.org/download/x/a.mp3")
        self.assertEqual(result.source, "in-process")


class MediafireTests(unittest.TestCase):
    PAGE = "https://www.mediafire.com/file/abc123/set.mp3"
    SIGNED = "https://download239.mediafire.com/abc123/set.mp3?token=signed"

    def adapter(self, http, **kwargs):
        return MediafireAdapter(
            http, Cache(tempfile.mkdtemp(), ttl=300),
            logger=RecordingLogger(), min_gap=0, **kwargs)

    def test_signed_url_from_plain_page(self):
        body = '<a href="%s">Download</a>' % self.SIGNED
        self.assertEqual(signed_url_from_page(body), self.SIGNED)
        self.assertEqual(clean_page_url(self.PAGE), (self.PAGE, ""))
        self.assertEqual(clean_page_url(self.SIGNED), ("", self.SIGNED))

    def test_signed_url_from_scrambled_attribute(self):
        token = base64.b64encode(self.SIGNED.encode()).decode()
        body = '<div data-scrambled-url="%s"></div>' % token
        self.assertEqual(signed_url_from_page(body), self.SIGNED)

    def test_resolve_page_and_cache(self):
        http = FakeHTTP([response(
            '<a href="%s">x</a>' % self.SIGNED,
            headers={"Content-Type": "text/html"}, url=self.PAGE)])
        adapter = self.adapter(http)
        first = adapter.resolve(self.PAGE)
        second = adapter.resolve(self.PAGE)
        self.assertEqual(first.url, self.SIGNED)
        self.assertEqual(first.provider, "mediafire")
        self.assertEqual(second.url, self.SIGNED)
        self.assertEqual(http.count("fetch"), 1)

    def test_direct_signed_url_needs_no_fetch(self):
        http = FakeHTTP([])
        result = self.adapter(http).resolve(self.SIGNED)
        self.assertEqual(result.url, self.SIGNED)
        self.assertEqual(http.count(), 0)

    def test_429_is_typed_and_backs_off(self):
        http = FakeHTTP([
            response("", status=429, headers={"Retry-After": "7"},
                     url=self.PAGE),
        ])
        adapter = self.adapter(http)
        with self.assertRaises(RateLimited) as caught:
            adapter.resolve(self.PAGE)
        self.assertEqual(caught.exception.retry_after, 7)
        with self.assertRaises(RateLimited):
            adapter.resolve(self.PAGE)
        self.assertEqual(http.count("fetch"), 1)

    def test_404_is_not_found(self):
        http = FakeHTTP([response("", status=404, url=self.PAGE)])
        with self.assertRaises(NotFound):
            self.adapter(http).resolve(self.PAGE)

    def test_missing_link_is_provider_error(self):
        http = FakeHTTP([response("<html>no link</html>", url=self.PAGE)])
        with self.assertRaises(ProviderError):
            self.adapter(http).resolve(self.PAGE)

    def test_non_mediafire_url_is_rejected(self):
        with self.assertRaises(InvalidURL):
            clean_page_url("https://example.com/file/abc/x.mp3")


class DriveTests(unittest.TestCase):
    URL = "https://drive.google.com/file/d/abcdefghij1234567890/view"
    DIRECT = ("https://drive.usercontent.google.com/download"
              "?id=abcdefghij1234567890&export=download")

    def adapter(self, http):
        return DriveAdapter(http, Cache(tempfile.mkdtemp(), ttl=300))

    def test_file_id_forms(self):
        for value in (
                self.URL,
                "https://drive.google.com/open?id=abcdefghij1234567890",
                "https://drive.google.com/uc?export=download&id=abcdefghij1234567890",
                "abcdefghij1234567890"):
            with self.subTest(value=value):
                self.assertEqual(file_id(value), "abcdefghij1234567890")
        self.assertEqual(file_id("https://example.com/x"), "")
        self.assertIn("abcdefghij1234567890", view_url(self.URL))

    def test_direct_audio_probe(self):
        http = FakeHTTP([response(
            b"", headers={"Content-Type": "audio/mpeg"},
            url=self.DIRECT)])
        result = self.adapter(http).resolve(self.URL)
        self.assertEqual(result.url, self.DIRECT)
        self.assertEqual(http.count("fetch"), 1)
        self.assertEqual(http.calls[0][2]["headers"]["Range"],
                         "bytes=0-4095")

    def test_confirm_form_is_followed(self):
        form = (
            '<form id="download-form" action="https://drive.usercontent.google.com/download">'
            '<input type="hidden" name="id" value="abcdefghij1234567890">'
            '<input type="hidden" name="export" value="download">'
            '<input type="hidden" name="confirm" value="t">'
            '<input type="submit" value="Download">'
            "</form>")
        http = FakeHTTP([
            response(form, headers={"Content-Type": "text/html"},
                     url="https://drive.google.com/uc?export=download"),
            response(b"", headers={"Content-Type": "audio/mpeg"},
                     url=self.DIRECT),
        ])
        result = self.adapter(http).resolve(self.URL)
        self.assertEqual(result.url, self.DIRECT)
        self.assertEqual(http.count("fetch"), 2)

    def test_result_is_cached(self):
        http = FakeHTTP([response(
            b"", headers={"Content-Type": "audio/mp4"}, url=self.DIRECT)])
        adapter = self.adapter(http)
        adapter.resolve(self.URL)
        adapter.resolve(self.URL)
        self.assertEqual(http.count("fetch"), 1)

    def test_404_and_non_audio(self):
        with self.assertRaises(UnknownDriveFile):
            self.adapter(FakeHTTP([response("", status=404)])).resolve(self.URL)
        with self.assertRaises(DriveNotAudio):
            self.adapter(FakeHTTP([
                response("<html>not a download form</html>",
                         headers={"Content-Type": "text/html"})
            ])).resolve(self.URL)

    def test_confirm_form_rejects_non_google_action(self):
        form = (
            '<form id="download-form" action="https://evil.example/download">'
            '<input type="hidden" name="id" value="1"></form>')
        self.assertEqual(parse_confirm_form(form), "")
        self.assertEqual(parse_confirm_form("<html></html>"), "")


class PodomaticTests(unittest.TestCase):
    def test_direct_cdn_file_resolves_in_process(self):
        adapter = PodomaticAdapter()
        url = "https://cdn.podomatic.com/abc/episode.mp3"
        result = adapter.resolve(url)
        self.assertEqual(result.url, url)
        self.assertEqual(result.provider, "podomatic")

    def test_page_needs_native_or_service(self):
        adapter = PodomaticAdapter()
        with self.assertRaises(AdapterNotReady) as caught:
            adapter.resolve("https://www.podomatic.com/podcasts/show/episodes/1")
        self.assertTrue(caught.exception.fallback)

    def test_native_adapter_is_used(self):
        adapter = PodomaticAdapter(
            native=lambda url: "https://cdn.podomatic.com/abc/episode.mp3")
        result = adapter.resolve(
            "https://www.podomatic.com/podcasts/show/episodes/1")
        self.assertEqual(result.url, "https://cdn.podomatic.com/abc/episode.mp3")

    def test_non_podomatic_host_is_rejected(self):
        adapter = PodomaticAdapter()
        with self.assertRaises(InvalidURL):
            adapter.resolve("https://example.com/episode.mp3")


if __name__ == "__main__":
    unittest.main()
