# -*- coding: utf-8 -*-
"""Offline tests for the resolver SDK package: policy, settings, cache, logs.

No Kodi device and no network: the module is imported from its installable
layout with the shared Kodi stubs, and every DNS/HTTP path is injected.
"""

import os
import sys
import io
import tempfile
import unittest
import urllib.error
from unittest import mock
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODULE = os.path.join(ROOT, "script.module.raveresolver")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(MODULE, "resources", "lib"))
sys.path.insert(0, HERE)

import resolver  # noqa: E402
from resolver import policy  # noqa: E402
from resolver.base import BlockedURL, HostNotAllowed, InvalidURL  # noqa: E402
from resolver.cache import Cache, MISSING  # noqa: E402
from resolver.direct import DirectAdapter  # noqa: E402
from resolver.http import HttpClient  # noqa: E402
from resolver.log import Logger  # noqa: E402
from resolver.settings import Settings  # noqa: E402
from resolver_fakes import (FakeAddon, RecordingLogger, fake_dns,  # noqa: E402
                            make_settings, response)


class ManifestTests(unittest.TestCase):
    def test_module_manifest_is_installable(self):
        root = ET.parse(os.path.join(MODULE, "addon.xml")).getroot()
        self.assertEqual(root.get("id"), "script.module.raveresolver")
        self.assertEqual(root.get("version"), "1.0.0")
        imports = {item.get("addon"): item.get("version")
                   for item in root.findall("./requires/import")}
        self.assertEqual(imports.get("xbmc.python"), "3.0.0")
        module = root.find("./extension[@point='xbmc.python.module']")
        self.assertIsNotNone(module)
        self.assertEqual(module.get("library"), "resources/lib")

    def test_module_files_exist(self):
        for name in ("README.md", "changelog.txt", "LICENSE.txt",
                     "icon.png", "fanart.jpg", "resources/settings.xml"):
            path = os.path.join(MODULE, name)
            self.assertTrue(os.path.isfile(path), path)
        self.assertTrue(os.path.isdir(os.path.join(
            MODULE, "resources", "lib", "resolver")))

    def test_settings_manifest_ids_and_defaults(self):
        root = ET.parse(os.path.join(
            MODULE, "resources", "settings.xml")).getroot()
        rows = {item.get("id"): item for item in root.findall(".//setting")}
        for key in ("resolver_service_url", "resolver_service_token",
                    "resolver_enable_mega", "resolver_http_timeout",
                    "resolver_service_timeout", "resolver_cache_dir",
                    "resolver_cache_ttl"):
            self.assertIn(key, rows)
        self.assertEqual(rows["resolver_enable_mega"].get("default"), "false")
        self.assertEqual(rows["resolver_service_token"].get("option"), "hidden")
        self.assertEqual(rows["resolver_http_timeout"].get("default"), "20")
        self.assertEqual(rows["resolver_cache_ttl"].get("default"), "7200")

    def test_package_version_and_exports(self):
        self.assertEqual(resolver.__version__, "1.0.0")
        for name in ("Resolver", "ResolveError", "Resolution", "InvalidURL",
                     "BlockedURL", "AdapterNotReady", "ServiceError"):
            self.assertTrue(hasattr(resolver, name), name)


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        settings = Settings(addon=FakeAddon())
        self.assertEqual(settings.service_url, "")
        self.assertFalse(settings.service_configured)
        self.assertFalse(settings.enable_mega)
        self.assertEqual(settings.http_timeout, 20)
        self.assertEqual(settings.service_timeout, 25)
        self.assertEqual(settings.cache_ttl, 7200)
        self.assertTrue(settings.cache_dir.endswith("raveresolver"))

    def test_overrides_and_clamping(self):
        settings = Settings(addon=FakeAddon({
            "resolver_service_url": "http://nas:8080",
            "resolver_service_token": "top-secret",
            "resolver_enable_mega": "true",
            "resolver_http_timeout": "1",
            "resolver_service_timeout": "999",
            "resolver_cache_dir": tempfile.gettempdir(),
            "resolver_cache_ttl": "0",
        }))
        self.assertTrue(settings.service_configured)
        self.assertTrue(settings.enable_mega)
        self.assertEqual(settings.http_timeout, 3)
        self.assertEqual(settings.service_timeout, 120)
        self.assertEqual(settings.cache_ttl, 0)
        self.assertEqual(settings.cache_dir, tempfile.gettempdir())

    def test_token_never_appears_in_public_view_or_repr(self):
        settings = Settings(addon=FakeAddon({
            "resolver_service_token": "top-secret"}))
        public = settings.as_public_dict()
        self.assertTrue(public["token_configured"])
        self.assertNotIn("top-secret", repr(public))
        self.assertNotIn("top-secret", repr(settings))


class CacheTests(unittest.TestCase):
    def test_put_get_and_key_hashing(self):
        directory = tempfile.mkdtemp()
        cache = Cache(directory, ttl=60)
        url = "https://download1.mediafire.com/secret-token/file.mp3"
        key = cache.key("mediafire", url)
        self.assertNotIn("mediafire", key)
        self.assertNotIn("secret-token", key)
        self.assertIs(cache.get(key), MISSING)
        self.assertTrue(cache.put(key, {"url": url}, ttl=60))
        self.assertEqual(cache.get(key), {"url": url})

    def test_expiry_uses_injected_clock(self):
        now = [1000.0]
        cache = Cache(tempfile.mkdtemp(), ttl=10, clock=lambda: now[0])
        key = cache.key("x")
        cache.put(key, "value", ttl=10)
        self.assertEqual(cache.get(key), "value")
        now[0] = 1011.0
        self.assertIs(cache.get(key), MISSING)

    def test_corrupt_entry_is_a_miss(self):
        directory = tempfile.mkdtemp()
        cache = Cache(directory, ttl=60)
        key = cache.key("x")
        with open(cache.path_for(key), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertIs(cache.get(key), MISSING)

    def test_disabled_cache_is_a_miss(self):
        cache = Cache(tempfile.mkdtemp(), ttl=0)
        self.assertFalse(cache.enabled)
        cache.put("k", "v")
        self.assertIs(cache.get("k"), MISSING)


class PolicyTests(unittest.TestCase):
    def test_private_and_local_targets_are_blocked(self):
        values = [
            "http://127.0.0.1/a.mp3",
            "http://10.1.2.3/a.mp3",
            "http://192.168.1.2/a.mp3",
            "http://169.254.169.254/latest/meta-data",
            "http://0.0.0.0/a.mp3",
            "http://[::1]/a.mp3",
            "http://localhost/a.mp3",
            "http://nas.local/a.mp3",
            "http://printer.internal/a.mp3",
        ]
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(BlockedURL):
                    policy.check_url(value)

    def test_public_literal_and_dns_policy(self):
        normalised = policy.check_url(
            "https://archive.org/download/x/a.mp3", resolve_dns=True,
            resolver=fake_dns)
        self.assertEqual(normalised, "https://archive.org/download/x/a.mp3")
        self.assertFalse(policy.host_is_blocked("archive.org", 443, fake_dns))
        self.assertTrue(policy.host_is_blocked(
            "archive.org", 443, lambda h, p: ["127.0.0.1"]))
        self.assertTrue(policy.host_is_blocked(
            "archive.org", 443, lambda h, p: ["93.184.216.34", "10.0.0.5"]))
        self.assertTrue(policy.host_is_blocked(
            "archive.org", 443, lambda h, p: []))

    def test_syntax_rejections(self):
        for value in ("", "not a url", "ftp://archive.org/a.mp3",
                      "https://user:pass@archive.org/a.mp3",
                      "https://archive.org:99999/a.mp3",
                      "javascript:alert(1)"):
            with self.subTest(value=value):
                with self.assertRaises(InvalidURL):
                    policy.check_url(value)

    def test_allowlist_rejects_unknown_public_host(self):
        with self.assertRaises(HostNotAllowed):
            policy.check_url("https://unknown.example.com/a.mp3",
                             allowed_hosts=policy.DIRECT_HOSTS,
                             resolve_dns=True, resolver=fake_dns)

    def test_provider_mapping(self):
        cases = {
            "https://www.mediafire.com/file/abc/set.mp3": "mediafire",
            "https://download239.mediafire.com/abc/set.mp3?x=1": "mediafire",
            "https://drive.google.com/file/d/abcdefghij1234567890/view": "drive",
            "https://drive.google.com/open?id=abcdefghij1234567890": "drive",
            "https://www.podomatic.com/podcasts/show/episodes/1": "podomatic",
            "https://mega.nz/file/abc12345#" + "A" * 43: "mega",
            "https://mega.co.nz/#!abc12345!" + "A" * 43: "mega",
            "https://archive.org/download/x/a.mp3": "direct",
            "https://archive.org/download/x/a.zip": "",
            "https://unknown.example.com/a.mp3": "",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(policy.provider_for(value), expected)

    def test_audio_extension_detection(self):
        self.assertTrue(policy.is_audio_url("https://x/a.MP3?token=1"))
        self.assertTrue(policy.is_audio_url("https://x/a.m4a#frag"))
        self.assertFalse(policy.is_audio_url("https://x/a.html"))
        self.assertFalse(policy.is_audio_url("https://x/a.mp3.zip"))

    def test_describe_url_is_log_safe(self):
        self.assertEqual(
            policy.describe_url("https://www.mediafire.com/file/secret?token=x"),
            "https://www.mediafire.com")


class _OpenerResponse(object):
    def __init__(self, body=b"", status=200, headers=None,
                 url="https://archive.org/a.mp3"):
        self.body = body
        self.status = status
        self.headers = headers or {}
        self._url = url
        self._read = False

    def read(self, amount=-1):
        data = self.body if amount is None or amount < 0 else self.body[:amount]
        self.body = b""
        return data

    def geturl(self):
        return self._url

    def close(self):
        pass


class _Opener(object):
    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append((request.full_url, timeout))
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


class HttpClientGuardTests(unittest.TestCase):
    def test_redirect_to_private_is_blocked(self):
        error = urllib.error.HTTPError(
            "https://archive.org/a.mp3", 302, "Found",
            {"Location": "http://127.0.0.1/a.mp3"}, io.BytesIO(b""))
        client = HttpClient(dns_resolver=fake_dns, opener=_Opener([error]))
        with self.assertRaises(BlockedURL):
            client.fetch("https://archive.org/a.mp3")

    def test_public_redirect_is_followed(self):
        error = urllib.error.HTTPError(
            "https://archive.org/a.mp3", 302, "Found",
            {"Location": "https://archive.org/b.mp3"}, io.BytesIO(b""))
        opener = _Opener([error, _OpenerResponse(
            b"ok", url="https://archive.org/b.mp3")])
        client = HttpClient(dns_resolver=fake_dns, opener=opener)
        response = client.fetch("https://archive.org/a.mp3")
        self.assertEqual(response.body, b"ok")
        self.assertEqual(response.final_url, "https://archive.org/b.mp3")
        self.assertEqual(len(opener.calls), 2)

    def test_private_service_host_can_be_explicitly_allowed(self):
        opener = _Opener([_OpenerResponse(b"{}", url="http://nas.local:8080/x")])
        client = HttpClient(dns_resolver=fake_dns, opener=opener)
        response = client.fetch("http://nas.local:8080/x", allow_private=True)
        self.assertEqual(response.status, 200)


class LoggerTests(unittest.TestCase):
    def test_token_and_signed_url_are_redacted(self):
        logger = RecordingLogger(secrets=["top-secret"])
        logger.error("Authorization: Bearer top-secret for "
                     "https://download1.mediafire.com/abc/set.mp3?token=top-secret")
        text = logger.text()
        self.assertNotIn("top-secret", text)
        self.assertIn("https://download1.mediafire.com/***", text)

    def test_plain_message_survives(self):
        logger = RecordingLogger()
        logger.info("mediafire: page parsed")
        self.assertIn("mediafire: page parsed", logger.text())


class NoNetworkTests(unittest.TestCase):
    def test_direct_resolution_does_not_touch_a_socket(self):
        adapter = DirectAdapter(dns_resolver=fake_dns)
        with mock.patch("socket.getaddrinfo",
                        side_effect=AssertionError("network")), \
                mock.patch("urllib.request.urlopen",
                           side_effect=AssertionError("network")):
            result = adapter.resolve("https://archive.org/download/x/a.mp3")
        self.assertEqual(result.url, "https://archive.org/download/x/a.mp3")
        self.assertEqual(result.provider, "direct")

    def test_private_url_never_reaches_a_transport(self):
        from resolver import Resolver
        from resolver_fakes import FakeHTTP
        http = FakeHTTP([])
        resolver = Resolver(settings=make_settings(), http=http,
                            dns_resolver=fake_dns)
        with self.assertRaises(BlockedURL):
            resolver.resolve("http://192.168.1.2/a.mp3")
        self.assertEqual(http.count(), 0)


if __name__ == "__main__":
    unittest.main()
