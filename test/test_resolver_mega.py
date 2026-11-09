# -*- coding: utf-8 -*-
"""Offline Mega URL parsing and adapter-seam tests (no Mega network client)."""

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
from resolver.base import (AdapterNotReady, InvalidURL,  # noqa: E402
                           UnsupportedURL)
from resolver.cache import Cache  # noqa: E402
from resolver.mega import MegaAdapter, MegaLink, parse_url  # noqa: E402
from resolver_fakes import FakeHTTP, fake_dns, make_settings  # noqa: E402

KEY = "A" * 43


class MegaParseTests(unittest.TestCase):
    def test_current_file_form(self):
        link = parse_url("https://mega.nz/file/abc12345#%s" % KEY)
        self.assertEqual(link.kind, "file")
        self.assertEqual(link.handle, "abc12345")
        self.assertEqual(link.key, KEY)
        self.assertEqual(link.url, "https://mega.nz/file/abc12345#%s" % KEY)

    def test_current_folder_form(self):
        link = parse_url("https://mega.nz/folder/folder12#%s" % ("B" * 22))
        self.assertEqual(link.kind, "folder")
        self.assertEqual(link.handle, "folder12")

    def test_legacy_forms_and_host_normalisation(self):
        file_link = parse_url("https://mega.co.nz/#!abc12345!%s" % KEY)
        self.assertEqual(file_link.kind, "file")
        self.assertEqual(file_link.url, "https://mega.nz/file/abc12345#%s" % KEY)
        folder = parse_url("https://mega.nz/#F!folder12!%s" % ("C" * 22))
        self.assertEqual(folder.kind, "folder")
        self.assertEqual(folder.handle, "folder12")

    def test_trailing_segments_are_ignored(self):
        link = parse_url("https://mega.nz/file/abc12345/Name.mp3#%s" % KEY)
        self.assertEqual(link.handle, "abc12345")

    def test_missing_key_is_rejected(self):
        with self.assertRaises(InvalidURL):
            parse_url("https://mega.nz/file/abc12345")
        with self.assertRaises(InvalidURL):
            parse_url("https://mega.nz/file/abc12345#")

    def test_bad_handle_or_host_is_rejected(self):
        with self.assertRaises(InvalidURL):
            parse_url("https://mega.nz/file/@@@#" + KEY)
        with self.assertRaises(InvalidURL):
            parse_url("https://example.com/file/abc12345#" + KEY)

    def test_unknown_shape_is_unsupported(self):
        with self.assertRaises(UnsupportedURL):
            parse_url("https://mega.nz/contact")

    def test_repr_does_not_leak_key(self):
        link = MegaLink("file", "abc12345", KEY, "https://mega.nz/file/x")
        self.assertNotIn(KEY, repr(link))
        self.assertIn("key=set", repr(link))


class MegaAdapterTests(unittest.TestCase):
    URL = "https://mega.nz/file/abc12345#%s" % KEY

    def test_folder_is_not_one_stream(self):
        adapter = MegaAdapter(enabled=True)
        with self.assertRaises(UnsupportedURL) as caught:
            adapter.resolve("https://mega.nz/folder/folder12#%s" % ("B" * 22))
        self.assertFalse(caught.exception.fallback)

    def test_disabled_mega_is_rejected_without_fallback(self):
        adapter = MegaAdapter(enabled=False)
        with self.assertRaises(UnsupportedURL) as caught:
            adapter.resolve(self.URL)
        self.assertFalse(caught.exception.fallback)

    def test_enabled_without_native_is_adapter_not_ready(self):
        adapter = MegaAdapter(enabled=True)
        with self.assertRaises(AdapterNotReady) as caught:
            adapter.resolve(self.URL)
        self.assertTrue(caught.exception.fallback)

    def test_native_string_result(self):
        adapter = MegaAdapter(
            enabled=True,
            native=lambda link: "https://gfs123.userstorage.mega.co.nz/abc")
        result = adapter.resolve(self.URL)
        self.assertEqual(result.provider, "mega")
        self.assertEqual(result.url,
                         "https://gfs123.userstorage.mega.co.nz/abc")

    def test_native_dict_result_keeps_headers(self):
        adapter = MegaAdapter(
            enabled=True,
            native=lambda link: {
                "url": "https://gfs123.userstorage.mega.co.nz/abc",
                "headers": {"Referer": "https://mega.nz/"},
                "expires_at": 1234567890,
            })
        result = adapter.resolve(self.URL)
        self.assertEqual(result.headers, {"Referer": "https://mega.nz/"})
        self.assertEqual(result.expires_at, 1234567890)

    def test_native_failure_is_typed(self):
        def boom(_link):
            raise RuntimeError("bad key")

        adapter = MegaAdapter(enabled=True, native=boom)
        with self.assertRaises(Exception) as caught:
            adapter.resolve(self.URL)
        self.assertIn("Mega resolve failed", str(caught.exception))

    def test_manager_respects_disabled_mega_and_never_calls_service(self):
        http = FakeHTTP([])
        settings = make_settings(resolver_enable_mega="false",
                                 resolver_service_url="http://nas:8080",
                                 resolver_service_token="token")
        resolver = Resolver(settings=settings, http=http,
                            cache=Cache(tempfile.mkdtemp(), ttl=1),
                            dns_resolver=fake_dns)
        with self.assertRaises(UnsupportedURL):
            resolver.resolve(self.URL)
        self.assertEqual(http.count(), 0)

    def test_manager_uses_native_adapter(self):
        resolved = "https://gfs123.userstorage.mega.co.nz/abc"
        resolver = Resolver(
            settings=make_settings(resolver_enable_mega="true"),
            http=FakeHTTP([]),
            cache=Cache(tempfile.mkdtemp(), ttl=1),
            dns_resolver=fake_dns, service=False,
            native_mega=lambda link: resolved)
        self.assertEqual(resolver.resolve(self.URL).url, resolved)


if __name__ == "__main__":
    unittest.main()
