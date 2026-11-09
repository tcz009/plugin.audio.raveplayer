# -*- coding: utf-8 -*-
"""Offline tests for the resolver service's MEGA ``stream`` contract.

Covers the web 1.6.64 payload (``source``/``expires``/``stream``), the older
``provider``/``expires_at`` shape, absolute-URL construction for LAN and
Tailscale bases, Bearer vs session-cookie auth, and fail-closed behaviour: a
MEGA resolve never returns the AES-CTR ciphertext ``url``.
"""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODULE = os.path.join(ROOT, "script.module.raveresolver")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(MODULE, "resources", "lib"))
sys.path.insert(0, HERE)

from resolver.base import (ServiceAuthError, ServiceError,  # noqa: E402
                           ServiceProtocolError)
from resolver.service import (DEFAULT_COOKIE_NAME, ServiceClient,  # noqa: E402
                              cookie_header, endpoint, stream_base)
from resolver_fakes import (FakeHTTP, RecordingLogger, fake_dns,  # noqa: E402
                            make_settings, response)

TOKEN = "resolver-service-token"
COOKIE = "raveplayer_session=session-value"
MEGA_INPUT = "https://mega.nz/file/abc12345#" + "A" * 43
CIPHERTEXT = "https://gfs123.userstorage.mega.co.nz/dl/encrypted-blob"
STREAM = ("/api/mega/stream?u=https%3A%2F%2Fmega.nz%2Ffile%2Fabc12345"
          "%23" + "A" * 43 + "&e=1800000000&t=signed-token")


def service_response(body, url="http://nas:8080/api/resolve"):
    return response(body, url=url)


class PayloadTests(unittest.TestCase):
    def client(self, http, **kwargs):
        return ServiceClient("http://nas:8080", timeout=7, http=http,
                             dns_resolver=fake_dns, **kwargs)

    def test_new_payload_source_and_expires(self):
        http = FakeHTTP([service_response({
            "ok": True,
            "url": "https://cdn.example.com/set.mp3",
            "headers": {"Referer": "https://www.podomatic.com/"},
            "expires": 1800000000,
            "source": "podomatic",
            "host": "cdn.example.com",
        })])
        result = self.client(http, token=TOKEN).resolve(
            "https://www.podomatic.com/podcasts/show/episodes/1")
        self.assertEqual(result.url, "https://cdn.example.com/set.mp3")
        self.assertEqual(result.provider, "podomatic")
        self.assertEqual(result.source, "service")
        self.assertEqual(result.expires_at, 1800000000.0)
        self.assertEqual(result.headers,
                         {"Referer": "https://www.podomatic.com/"})

    def test_old_payload_provider_and_expires_at(self):
        http = FakeHTTP([service_response({
            "url": "https://cdn.example.com/set.mp3",
            "provider": "mediafire",
            "expires_at": 1800000001,
        })])
        result = self.client(http, token=TOKEN).resolve(
            "https://www.mediafire.com/file/abc/set.mp3")
        self.assertEqual(result.provider, "mediafire")
        self.assertEqual(result.expires_at, 1800000001.0)

    def test_old_payload_expires_in_is_still_accepted(self):
        http = FakeHTTP([service_response({
            "url": "https://cdn.example.com/set.mp3",
            "provider": "podomatic",
            "expires_in": 300,
        })])
        before = time.time()
        result = self.client(http, token=TOKEN).resolve(
            "https://www.podomatic.com/podcasts/show/episodes/1")
        self.assertGreaterEqual(result.expires_at, before)
        self.assertLess(result.expires_at, before + 600)

    def test_nested_result_wrapper(self):
        http = FakeHTTP([service_response({
            "ok": True,
            "result": {"url": "https://cdn.example.com/set.mp3",
                       "source": "direct"},
        })])
        result = self.client(http, token=TOKEN).resolve(
            "https://archive.org/download/x/a.mp3")
        self.assertEqual(result.provider, "direct")
        self.assertEqual(result.url, "https://cdn.example.com/set.mp3")

    def test_non_mega_stream_field_is_ignored(self):
        http = FakeHTTP([service_response({
            "url": "https://cdn.example.com/set.mp3",
            "source": "podomatic",
            "stream": STREAM,
        })])
        result = self.client(http, token=TOKEN).resolve(
            "https://www.podomatic.com/podcasts/show/episodes/1")
        self.assertEqual(result.url, "https://cdn.example.com/set.mp3")

    def test_non_mega_missing_url_is_protocol_error(self):
        http = FakeHTTP([service_response({"source": "podomatic",
                                           "stream": STREAM})])
        with self.assertRaises(ServiceProtocolError):
            self.client(http, token=TOKEN).resolve(
                "https://www.podomatic.com/podcasts/show/episodes/1")


class MegaStreamTests(unittest.TestCase):
    def client(self, http, base="http://nas:8080", **kwargs):
        return ServiceClient(base, timeout=7, http=http,
                             dns_resolver=fake_dns, **kwargs)

    def resolve_mega(self, http, **kwargs):
        return self.client(http, **kwargs).resolve(MEGA_INPUT,
                                                   provider="mega")

    def test_mega_stream_is_selected_over_ciphertext(self):
        http = FakeHTTP([service_response({
            "ok": True,
            "url": CIPHERTEXT,
            "headers": {"Referer": "https://mega.nz/",
                        "Authorization": "Bearer should-be-dropped"},
            "expires": 1760000000,
            "source": "mega",
            "stream": STREAM,
        })])
        result = self.resolve_mega(http, token=TOKEN)
        self.assertEqual(result.url, "http://nas:8080" + STREAM)
        self.assertNotIn(CIPHERTEXT, result.url)
        self.assertNotIn("userstorage.mega.co.nz", result.url)
        self.assertEqual(result.provider, "mega")
        self.assertEqual(result.source, "service")
        # The signed token's ``e`` is the playable expiry, not the storage
        # URL's ``expires``.
        self.assertEqual(result.expires_at, 1800000000.0)
        # No media-request headers are appended to the self-authenticating URL.
        self.assertEqual(result.headers, {})
        self.assertNotIn("|", result.kodi_url())

    def test_mega_stream_works_without_a_url_field(self):
        http = FakeHTTP([service_response({
            "source": "mega", "stream": STREAM, "expires": 1760000000})])
        result = self.resolve_mega(http, token=TOKEN)
        self.assertEqual(result.url, "http://nas:8080" + STREAM)

    def test_legacy_provider_mega_with_stream_is_accepted(self):
        http = FakeHTTP([service_response({
            "url": CIPHERTEXT, "provider": "mega", "stream": STREAM})])
        result = self.resolve_mega(http, token=TOKEN)
        self.assertEqual(result.url, "http://nas:8080" + STREAM)

    def test_mega_without_stream_never_falls_back_to_ciphertext(self):
        payloads = (
            {"url": CIPHERTEXT, "source": "mega"},
            {"url": CIPHERTEXT, "provider": "mega"},
            {"url": CIPHERTEXT, "source": "mega", "stream": ""},
            {"url": CIPHERTEXT, "source": "mega", "stream": None},
            {"url": CIPHERTEXT},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                http = FakeHTTP([service_response(payload)])
                with self.assertRaises(ServiceProtocolError) as caught:
                    self.resolve_mega(http, token=TOKEN)
                self.assertNotIn(CIPHERTEXT, str(caught.exception))

    def test_absolute_or_protocol_relative_stream_is_rejected(self):
        for stream in ("https://evil.example/api/mega/stream?t=x",
                       "//evil.example/api/mega/stream?t=x",
                       "api/mega/stream?t=x",
                       "/api/mega/stream?t=x\nSet-Cookie: y",
                       "/api/mega/stream?t=x\\y",
                       "/api/mega/stream?t=x#fragment",
                       "/api/mega/stream?t=" + "x" * 9000):
            with self.subTest(stream=stream[:40]):
                http = FakeHTTP([service_response({
                    "source": "mega", "url": CIPHERTEXT, "stream": stream})])
                with self.assertRaises(ServiceProtocolError):
                    self.resolve_mega(http, token=TOKEN)

    def test_mega_stream_keeps_lan_or_tailscale_base(self):
        for base in ("http://192.168.1.179:8097",
                     "http://rave-nas.tail1234.ts.net:8097"):
            with self.subTest(base=base):
                http = FakeHTTP([service_response({
                    "source": "mega", "stream": STREAM})])
                result = self.resolve_mega(http, base=base, token=TOKEN)
                self.assertEqual(result.url, base + STREAM)


class AbsoluteURLTests(unittest.TestCase):
    def absolute(self, base, stream=STREAM):
        client = ServiceClient(base, token=TOKEN, http=FakeHTTP([]),
                               dns_resolver=fake_dns)
        return client.absolute_stream_url(stream)

    def test_lan_base(self):
        self.assertEqual(
            self.absolute("http://192.168.1.179:8097"),
            "http://192.168.1.179:8097" + STREAM)

    def test_tailscale_base(self):
        self.assertEqual(
            self.absolute("http://rave-nas.tail1234.ts.net:8097"),
            "http://rave-nas.tail1234.ts.net:8097" + STREAM)

    def test_trailing_slash_does_not_double(self):
        self.assertEqual(
            self.absolute("http://192.168.1.179:8097/"),
            "http://192.168.1.179:8097" + STREAM)

    def test_base_may_already_be_the_endpoint_or_api(self):
        expected = "http://nas:8080" + STREAM
        self.assertEqual(self.absolute("http://nas:8080/api/resolve"),
                         expected)
        self.assertEqual(self.absolute("http://nas:8080/api"), expected)
        self.assertEqual(self.absolute("http://nas:8080/api/resolve/"),
                         expected)
        self.assertEqual(self.absolute("http://nas:8080/"), expected)

    def test_reverse_proxy_prefix_is_preserved(self):
        self.assertEqual(
            self.absolute("https://rave.example/resolver"),
            "https://rave.example/resolver" + STREAM)
        self.assertEqual(
            self.absolute("https://rave.example/resolver/api/resolve"),
            "https://rave.example/resolver" + STREAM)

    def test_web_path_already_has_the_prefix(self):
        stream = "/resolver" + STREAM
        self.assertEqual(
            self.absolute("https://rave.example/resolver", stream),
            "https://rave.example" + stream)

    def test_query_is_preserved_verbatim(self):
        url = self.absolute("http://nas:8080")
        self.assertEqual(url.split("?", 1)[1], STREAM.split("?", 1)[1])
        self.assertIn("u=https%3A%2F%2Fmega.nz", url)
        self.assertIn("&t=signed-token", url)

    def test_stream_base_forms(self):
        self.assertEqual(stream_base("http://nas:8080"), "http://nas:8080")
        self.assertEqual(stream_base("http://nas:8080/"), "http://nas:8080")
        self.assertEqual(stream_base("http://nas:8080/api"),
                         "http://nas:8080")
        self.assertEqual(stream_base("http://nas:8080/api/resolve"),
                         "http://nas:8080")
        self.assertEqual(stream_base("https://rave.example/resolver"),
                         "https://rave.example/resolver")
        self.assertEqual(endpoint("http://nas:8080/"),
                         "http://nas:8080/api/resolve")


class AuthTests(unittest.TestCase):
    def request_headers(self, **kwargs):
        http = FakeHTTP([service_response({
            "url": "https://cdn.example.com/set.mp3", "source": "direct"})])
        ServiceClient("http://nas:8080", timeout=7, http=http,
                      dns_resolver=fake_dns, **kwargs).resolve(
            "https://archive.org/download/x/a.mp3")
        _kind, _args, call = http.calls[0]
        return call["headers"]

    def test_bearer_auth(self):
        headers = self.request_headers(token=TOKEN)
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
        self.assertNotIn("Cookie", headers)

    def test_cookie_header_normalisation(self):
        self.assertEqual(cookie_header("session-value"),
                         DEFAULT_COOKIE_NAME + "=session-value")
        self.assertEqual(cookie_header(COOKIE), COOKIE)
        self.assertEqual(cookie_header(""), "")

    def test_bare_cookie_value_gets_the_default_name(self):
        headers = self.request_headers(cookie="session-value")
        self.assertEqual(headers["Cookie"],
                         DEFAULT_COOKIE_NAME + "=session-value")
        self.assertNotIn("Authorization", headers)

    def test_cookie_pair_is_sent_as_configured(self):
        headers = self.request_headers(cookie=COOKIE)
        self.assertEqual(headers["Cookie"], COOKIE)
        self.assertNotIn("Authorization", headers)

    def test_bearer_wins_when_both_are_configured(self):
        headers = self.request_headers(token=TOKEN, cookie=COOKIE)
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
        self.assertNotIn("Cookie", headers)

    def test_no_auth_configured_sends_neither(self):
        headers = self.request_headers()
        self.assertNotIn("Authorization", headers)
        self.assertNotIn("Cookie", headers)

    def test_cookie_with_line_break_is_refused(self):
        with self.assertRaises(ServiceError):
            ServiceClient("http://nas:8080", cookie="a=b\r\nX-Evil: 1",
                          http=FakeHTTP([]), dns_resolver=fake_dns)

    def test_cookie_401_is_auth_error(self):
        http = FakeHTTP([response({"error": "auth"}, status=401)])
        client = ServiceClient("http://nas:8080", cookie=COOKIE,
                               http=http, dns_resolver=fake_dns)
        with self.assertRaises(ServiceAuthError):
            client.resolve("https://archive.org/download/x/a.mp3")

    def test_cookie_is_never_returned_in_resolution_headers(self):
        http = FakeHTTP([service_response({
            "url": "https://cdn.example.com/set.mp3", "source": "direct",
            "headers": {"Cookie": COOKIE, "Referer": "https://example.com/"}})])
        client = ServiceClient("http://nas:8080", cookie=COOKIE,
                               http=http, dns_resolver=fake_dns)
        result = client.resolve("https://archive.org/download/x/a.mp3")
        self.assertEqual(result.headers, {"Referer": "https://example.com/"})

    def test_cookie_secret_is_redacted_by_the_logger(self):
        secret = "session-value"
        logger = RecordingLogger(secrets=[secret])
        logger.error("Cookie: " + COOKIE)
        self.assertNotIn(secret, logger.text())

    def test_from_settings_uses_bearer_or_cookie(self):
        bearer = ServiceClient.from_settings(
            make_settings(resolver_service_url="http://nas:8080",
                          resolver_service_token=TOKEN), FakeHTTP([]),
            dns_resolver=fake_dns)
        self.assertEqual(bearer.auth_mode, "bearer")
        cookie = ServiceClient.from_settings(
            make_settings(resolver_service_url="http://nas:8080",
                          resolver_service_cookie=COOKIE), FakeHTTP([]),
            dns_resolver=fake_dns)
        self.assertEqual(cookie.auth_mode, "cookie")


class ManagerFallbackTests(unittest.TestCase):
    def resolver(self, http, **settings):
        from resolver import Resolver
        from resolver.cache import Cache
        import tempfile

        values = {"resolver_service_url": "http://nas:8080",
                  "resolver_enable_mega": "true"}
        values.update(settings)
        return Resolver(settings=make_settings(**values), http=http,
                        cache=Cache(tempfile.mkdtemp(), ttl=0),
                        dns_resolver=fake_dns)

    def test_manager_does_not_resolve_mega_to_ciphertext(self):
        http = FakeHTTP([service_response({
            "url": CIPHERTEXT, "source": "mega"})])
        with self.assertRaises(ServiceProtocolError):
            self.resolver(http).resolve(MEGA_INPUT)
        self.assertEqual(http.count(), 1)

    def test_manager_returns_the_stream_url(self):
        http = FakeHTTP([service_response({
            "url": CIPHERTEXT, "source": "mega", "stream": STREAM})])
        result = self.resolver(http, resolver_service_token=TOKEN).resolve(
            MEGA_INPUT)
        self.assertEqual(result.url, "http://nas:8080" + STREAM)
        self.assertEqual(result.provider, "mega")

    def test_manager_uses_cookie_from_settings(self):
        http = FakeHTTP([service_response({
            "url": "https://cdn.example.com/episode.mp3",
            "source": "podomatic"})])
        result = self.resolver(
            http, resolver_service_cookie=COOKIE).resolve(
            "https://www.podomatic.com/podcasts/show/episodes/1")
        _kind, _args, call = http.calls[0]
        self.assertEqual(call["headers"]["Cookie"], COOKIE)
        self.assertNotIn("Authorization", call["headers"])
        self.assertEqual(result.source, "service")


if __name__ == "__main__":
    unittest.main()
