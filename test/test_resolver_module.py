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
        self.assertEqual(root.get("version"), "1.1.1")
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
                    "resolver_service_cookie", "resolver_enable_mega",
                    "resolver_http_timeout",
                    "resolver_service_timeout", "resolver_cache_dir",
                    "resolver_cache_ttl"):
            self.assertIn(key, rows)
        self.assertEqual(rows["resolver_enable_mega"].get("default"), "false")
        self.assertEqual(rows["resolver_service_token"].get("option"), "hidden")
        self.assertEqual(rows["resolver_service_cookie"].get("option"), "hidden")
        self.assertEqual(rows["resolver_service_cookie"].get("default"), "")
        self.assertEqual(rows["resolver_http_timeout"].get("default"), "20")
        self.assertEqual(rows["resolver_cache_ttl"].get("default"), "7200")

    def test_package_version_and_exports(self):
        self.assertEqual(resolver.__version__, "1.1.1")
        for name in ("Resolver", "ResolveError", "Resolution", "InvalidURL",
                     "BlockedURL", "AdapterNotReady", "ServiceError"):
            self.assertTrue(hasattr(resolver, name), name)


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        settings = Settings(addon=FakeAddon())
        self.assertEqual(settings.service_url, "")
        self.assertEqual(settings.service_cookie, "")
        self.assertEqual(settings.service_auth_mode, "none")
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
            "resolver_service_cookie": "session-secret",
            "resolver_enable_mega": "true",
            "resolver_http_timeout": "1",
            "resolver_service_timeout": "999",
            "resolver_cache_dir": tempfile.gettempdir(),
            "resolver_cache_ttl": "0",
        }))
        self.assertTrue(settings.service_configured)
        self.assertEqual(settings.service_auth_mode, "bearer")
        self.assertTrue(settings.enable_mega)
        self.assertEqual(settings.http_timeout, 3)
        self.assertEqual(settings.service_timeout, 120)
        self.assertEqual(settings.cache_ttl, 0)
        self.assertEqual(settings.cache_dir, tempfile.gettempdir())

    def test_token_and_cookie_never_appear_in_public_view_or_repr(self):
        settings = Settings(addon=FakeAddon({
            "resolver_service_token": "top-secret",
            "resolver_service_cookie": "session-secret"}))
        public = settings.as_public_dict()
        self.assertTrue(public["token_configured"])
        self.assertTrue(public["cookie_configured"])
        self.assertNotIn("top-secret", repr(public))
        self.assertNotIn("session-secret", repr(public))
        self.assertNotIn("top-secret", repr(settings))
        self.assertNotIn("session-secret", repr(settings))


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

    def test_memory_is_bounded(self):
        cache = Cache(tempfile.mkdtemp(), ttl=60)
        for index in range(600):
            cache.put(cache.key("k", index), index, ttl=60)
        self.assertLessEqual(len(cache._memory), 512)
        self.assertIs(cache.get(cache.key("k", 0)), MISSING)
        self.assertEqual(cache.get(cache.key("k", 599)), 599)

    def test_clear_only_removes_own_entries(self):
        directory = tempfile.mkdtemp()
        cache = Cache(directory, ttl=60)
        cache.put(cache.key("x"), "value", ttl=60)
        unrelated = os.path.join(directory, "unrelated.json")
        with open(unrelated, "w", encoding="utf-8") as handle:
            handle.write("{}")
        cache.clear()
        self.assertTrue(os.path.exists(unrelated))
        self.assertEqual(os.listdir(directory), ["unrelated.json"])

    def test_entry_file_is_private(self):
        directory = tempfile.mkdtemp()
        cache = Cache(directory, ttl=60)
        key = cache.key("x")
        self.assertTrue(cache.put(key, {"url": "https://example.test/x.mp3"}))
        mode = os.stat(cache.path_for(key)).st_mode & 0o777
        self.assertEqual(mode, 0o600)

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

    def test_media_ports_are_limited_to_80_and_443(self):
        for value in ("https://archive.org:22/a.mp3",
                      "http://mediafire.com:8080/file/abc/set.mp3",
                      "https://mega.nz:8443/file/abc#key"):
            with self.subTest(value=value):
                with self.assertRaises(InvalidURL):
                    policy.check_url(value)
        self.assertEqual(
            policy.check_url("http://archive.org:80/a.mp3"),
            "http://archive.org:80/a.mp3")
        self.assertEqual(
            policy.check_url("https://archive.org:443/a.mp3"),
            "https://archive.org:443/a.mp3")
        # The operator service base is the one opt-out, handled by
        # resolver.service.endpoint(); policy still rejects it by default.
        self.assertIsNone(policy.split_url("http://nas:8080"))

    def test_local_hostname_rejects_single_label_and_localdomain(self):
        for value in ("http://nas/a.mp3", "http://printer.localdomain/a.mp3",
                      "http://metadata.google.internal/x"):
            with self.subTest(value=value):
                with self.assertRaises(BlockedURL):
                    policy.check_url(value)

    def test_service_base_link_local_and_metadata_are_blocked(self):
        for host in ("169.254.169.254", "0.0.0.0", "fe80::1",
                     "fd00:ec2::254", "metadata.google.internal"):
            with self.subTest(host=host):
                self.assertTrue(policy.service_host_blocked(host))
        for host in ("nas", "192.168.1.179", "127.0.0.1",
                     "rave-nas.tail1234.ts.net", "rave.example"):
            with self.subTest(host=host):
                self.assertFalse(policy.service_host_blocked(host))

    def test_headers_are_sanitised_like_the_web_resolver(self):
        headers = policy.sanitize_headers({
            "Referer": "https://www.mediafire.com/",
            "Authorization": "Bearer secret",
            "Cookie": "session=secret",
            "Content-Type": "text/html",
            "Host": "evil.example",
            "X-Ok": "value",
            "X-Number": 7,
            "X-Crlf": "a\r\nInjected: yes",
            "X-Blob": "x" * 9000,
        })
        self.assertEqual(headers.get("Referer"), "https://www.mediafire.com/")
        self.assertEqual(headers.get("X-Ok"), "value")
        self.assertEqual(headers.get("X-Number"), "7")
        for dropped in ("Authorization", "Cookie", "Content-Type", "Host",
                        "X-Crlf", "X-Blob"):
            self.assertNotIn(dropped, headers)

    def test_header_count_and_bytes_are_bounded(self):
        many = {"X-%d" % index: "v" for index in range(40)}
        self.assertLessEqual(len(policy.sanitize_headers(many)), 24)
        big = {"X-A": "v" * 4000, "X-B": "v" * 4000, "X-C": "v" * 200}
        cleaned = policy.sanitize_headers(big)
        self.assertEqual(sorted(cleaned), ["X-A", "X-B"])

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
    def test_redirect_to_private_is_blocked_when_following(self):
        error = urllib.error.HTTPError(
            "https://archive.org/a.mp3", 302, "Found",
            {"Location": "http://127.0.0.1/a.mp3"}, io.BytesIO(b""))
        client = HttpClient(dns_resolver=fake_dns, opener=_Opener([error]))
        with self.assertRaises(BlockedURL):
            client.fetch("https://archive.org/a.mp3", allow_redirects=True)

    def test_redirects_are_not_followed_by_default(self):
        error = urllib.error.HTTPError(
            "https://archive.org/a.mp3", 302, "Found",
            {"Location": "https://archive.org/b.mp3"}, io.BytesIO(b""))
        opener = _Opener([error])
        client = HttpClient(dns_resolver=fake_dns, opener=opener)
        response = client.fetch("https://archive.org/a.mp3")
        self.assertEqual(response.status, 302)
        self.assertEqual(len(opener.calls), 1)

    def test_public_redirect_is_followed_when_explicit(self):
        error = urllib.error.HTTPError(
            "https://archive.org/a.mp3", 302, "Found",
            {"Location": "https://archive.org/b.mp3"}, io.BytesIO(b""))
        opener = _Opener([error, _OpenerResponse(
            b"ok", url="https://archive.org/b.mp3")])
        client = HttpClient(dns_resolver=fake_dns, opener=opener)
        response = client.fetch("https://archive.org/a.mp3",
                                allow_redirects=True)
        self.assertEqual(response.body, b"ok")
        self.assertEqual(response.final_url, "https://archive.org/b.mp3")
        self.assertEqual(len(opener.calls), 2)

    def test_redirect_to_an_off_allowlist_host_is_refused(self):
        error = urllib.error.HTTPError(
            "https://archive.org/a.mp3", 302, "Found",
            {"Location": "https://other.org/b.mp3"}, io.BytesIO(b""))
        client = HttpClient(dns_resolver=fake_dns, opener=_Opener([error]))
        with self.assertRaises(HostNotAllowed):
            client.fetch("https://archive.org/a.mp3", allow_redirects=True,
                         allowed_hosts=("archive.org",))

    def test_redirect_chain_is_capped_at_three(self):
        def hop(url):
            return urllib.error.HTTPError(
                url, 302, "Found",
                {"Location": "https://archive.org/next"},
                io.BytesIO(b""))
        opener = _Opener([hop("https://archive.org/a"),
                          hop("https://archive.org/next"),
                          hop("https://archive.org/next"),
                          hop("https://archive.org/next")])
        client = HttpClient(dns_resolver=fake_dns, opener=opener)
        response = client.fetch("https://archive.org/a",
                                allow_redirects=True)
        # Three hops followed; the fourth 302 is returned to the caller
        # rather than followed.
        self.assertEqual(response.status, 302)
        self.assertEqual(len(opener.calls), 4)

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
