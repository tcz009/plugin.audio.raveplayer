# -*- coding: utf-8 -*-
"""Offline NAS resolver-service tests: contract, fallback and redaction."""

import json
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
from resolver.base import (BlockedURL, InvalidURL, NotFound,  # noqa: E402
                           ProviderError, ProviderTimeout, RateLimited,
                           ServiceAuthError, ServiceError,
                           ServiceProtocolError, UnsupportedURL)
from resolver.cache import Cache  # noqa: E402
from resolver.http import HttpTransportError  # noqa: E402
from resolver.service import ServiceClient, endpoint  # noqa: E402
from resolver_fakes import (FakeHTTP, RecordingLogger, fake_dns,  # noqa: E402
                            make_settings, response)

TOKEN = "very-secret-token"


class EndpointTests(unittest.TestCase):
    def test_endpoint_forms(self):
        cases = {
            "http://nas:8080": "http://nas:8080/api/resolve",
            "http://nas:8080/": "http://nas:8080/api/resolve",
            "http://nas:8080/api": "http://nas:8080/api/resolve",
            "http://nas:8080/api/resolve": "http://nas:8080/api/resolve",
            "https://rave.example/resolver": "https://rave.example/resolver/api/resolve",
            "https://rave.example/resolver/api/resolve/": "https://rave.example/resolver/api/resolve",
            # Bare host[:port] is accepted, matching webapi.normalise_base().
            "nas:8080": "http://nas:8080/api/resolve",
            "nas": "http://nas/api/resolve",
            "192.168.1.179:8097": "http://192.168.1.179:8097/api/resolve",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(endpoint(value), expected)

    def test_invalid_service_urls(self):
        for value in ("", "not a url", "ftp://nas/resolve",
                      "http://user:pass@nas:8080", "http://nas:8080/?x=1",
                      "http://169.254.169.254", "169.254.169.254",
                      "http://metadata.google.internal"):
            with self.subTest(value=value):
                with self.assertRaises(ServiceError):
                    endpoint(value)


class ServiceClientTests(unittest.TestCase):
    def client(self, http, token=TOKEN):
        return ServiceClient("http://nas:8080", token=token,
                             timeout=7, http=http, dns_resolver=fake_dns)

    def test_successful_response(self):
        http = FakeHTTP([response({
            "url": "https://cdn.example.com/set.mp3",
            "provider": "podomatic",
            "headers": {"Referer": "https://www.podomatic.com/",
                        "Authorization": "should-be-dropped"},
            "expires_in": 300,
        }, url="http://nas:8080/api/resolve")])
        result = self.client(http).resolve(
            "https://www.podomatic.com/podcasts/show/episodes/1",
            provider="podomatic")
        self.assertEqual(result.url, "https://cdn.example.com/set.mp3")
        self.assertEqual(result.provider, "podomatic")
        self.assertEqual(result.source, "service")
        self.assertEqual(result.headers, {"Referer": "https://www.podomatic.com/"})
        self.assertIsNotNone(result.expires_at)
        kind, args, kwargs = http.calls[0]
        self.assertEqual(kind, "request")
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "http://nas:8080/api/resolve")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(json.loads(kwargs["body"].decode("utf-8")),
                         {"url": "https://www.podomatic.com/podcasts/show/episodes/1",
                          "provider": "podomatic"})

    def test_service_headers_are_sanitised(self):
        http = FakeHTTP([response({
            "url": "https://cdn.example.com/set.mp3",
            "headers": {"Referer": "https://cdn.example.com/",
                        "Content-Type": "text/html",
                        "Authorization": "Bearer leak",
                        "Cookie": "session=leak",
                        "X-Crlf": "a\r\nInjected: 1",
                        "X-Ok": "yes"},
        }, url="http://nas:8080/api/resolve")])
        result = self.client(http).resolve("https://example.com/watch/1")
        self.assertEqual(result.headers,
                         {"Referer": "https://cdn.example.com/", "X-Ok": "yes"})

    def test_nested_result_and_iso_expiry(self):
        http = FakeHTTP([response({
            "result": {
                "url": "https://cdn.example.com/set.mp3",
                "expires_at": "2030-01-01T00:00:00Z",
            }
        }, url="http://nas:8080/api/resolve")])
        result = self.client(http).resolve("https://example.com/watch/1")
        self.assertEqual(result.provider, "service")
        self.assertGreater(result.expires_at, 1800000000)

    def test_auth_failure_is_typed(self):
        http = FakeHTTP([response({"error": "bad token"}, status=401)])
        with self.assertRaises(ServiceAuthError):
            self.client(http).resolve("https://example.com/watch/1")

    def test_server_failure_is_typed(self):
        http = FakeHTTP([response("", status=500)])
        with self.assertRaises(ServiceError):
            self.client(http).resolve("https://example.com/watch/1")

    def test_invalid_json_is_protocol_error(self):
        http = FakeHTTP([response("<html>oops</html>")])
        with self.assertRaises(ServiceProtocolError):
            self.client(http).resolve("https://example.com/watch/1")

    def test_private_result_is_rejected(self):
        http = FakeHTTP([response({"url": "http://192.168.1.5/stream"},
                                  url="http://nas:8080/api/resolve")])
        with self.assertRaises(ServiceProtocolError):
            self.client(http).resolve("https://example.com/watch/1")

    def test_missing_url_is_protocol_error(self):
        http = FakeHTTP([response({"provider": "mega"})])
        with self.assertRaises(ServiceProtocolError):
            self.client(http).resolve("https://example.com/watch/1")

    def test_transport_failure_is_service_error(self):
        http = FakeHTTP([HttpTransportError("timeout", host="nas")])
        with self.assertRaises(ServiceError):
            self.client(http).resolve("https://example.com/watch/1")

    def test_token_is_not_in_an_error_or_log(self):
        logger = RecordingLogger(secrets=[TOKEN])
        client = ServiceClient("http://nas:8080", token=TOKEN,
                               timeout=7,
                               http=FakeHTTP([response("", status=401)]),
                               logger=logger, dns_resolver=fake_dns)
        with self.assertRaises(ServiceAuthError) as caught:
            client.resolve("https://example.com/watch/1")
        self.assertNotIn(TOKEN, str(caught.exception))
        logger.error("Authorization: Bearer " + TOKEN)
        self.assertNotIn(TOKEN, logger.text())


class ServiceErrorMappingTests(unittest.TestCase):
    def client(self, http):
        return ServiceClient("http://nas:8080", token=TOKEN, timeout=7,
                             http=http, dns_resolver=fake_dns)

    def test_rate_limited_honours_retry_after(self):
        http = FakeHTTP([response(
            {"ok": False, "code": "rate_limited", "error": "slow down"},
            status=429, headers={"Retry-After": "37"})])
        with self.assertRaises(RateLimited) as caught:
            self.client(http).resolve("https://example.com/watch/1")
        self.assertEqual(caught.exception.retry_after, 37)

    def test_rate_limited_caps_retry_after(self):
        http = FakeHTTP([response(
            {"ok": False, "code": "rate_limited"}, status=429,
            headers={"Retry-After": "9999"})])
        with self.assertRaises(RateLimited) as caught:
            self.client(http).resolve("https://example.com/watch/1")
        self.assertEqual(caught.exception.retry_after, 120)

    def test_timeout_status_and_code(self):
        for status, body in ((504, {"ok": False, "code": "timeout"}),
                             (502, {"ok": False, "code": "timeout"})):
            with self.subTest(status=status):
                http = FakeHTTP([response(body, status=status)])
                with self.assertRaises(ProviderTimeout):
                    self.client(http).resolve("https://example.com/watch/1")

    def test_blocked_code_maps_even_on_http_400(self):
        http = FakeHTTP([response(
            {"ok": False, "code": "blocked", "error": "refused"},
            status=400)])
        with self.assertRaises(BlockedURL):
            self.client(http).resolve("http://router.lan/a.mp3")

    def test_not_found_code_maps_even_on_http_400(self):
        http = FakeHTTP([response(
            {"ok": False, "code": "not_found"}, status=400)])
        with self.assertRaises(NotFound):
            self.client(http).resolve("https://example.com/watch/1")

    def test_invalid_and_unsupported_are_typed(self):
        cases = (("invalid", InvalidURL), ("unsupported", UnsupportedURL),
                 ("unknown", UnsupportedURL))
        for code, expected in cases:
            with self.subTest(code=code):
                http = FakeHTTP([response(
                    {"ok": False, "code": code}, status=400)])
                with self.assertRaises(expected):
                    self.client(http).resolve("https://example.com/watch/1")

    def test_upstream_code_maps_to_provider_error(self):
        http = FakeHTTP([response(
            {"ok": False, "code": "upstream"}, status=502)])
        with self.assertRaises(ProviderError):
            self.client(http).resolve("https://example.com/watch/1")

    def test_ok_false_on_http_200_is_typed(self):
        http = FakeHTTP([response({"ok": False, "code": "not_found"})])
        with self.assertRaises(NotFound):
            self.client(http).resolve("https://example.com/watch/1")

    def test_service_redirect_is_not_followed(self):
        http = FakeHTTP([response("", status=302,
                                  headers={"Location": "https://evil.example/x"})])
        with self.assertRaises(ServiceProtocolError):
            self.client(http).resolve("https://example.com/watch/1")
        self.assertEqual(http.count("request"), 1)

    def test_dns_private_result_is_rejected(self):
        http = FakeHTTP([response({
            "url": "https://evil.example/secret.mp3"})])
        client = ServiceClient("http://nas:8080", token=TOKEN,
                               timeout=7, http=http,
                               dns_resolver=lambda host, port: ["10.0.0.5"])
        with self.assertRaises(ServiceProtocolError):
            client.resolve("https://example.com/watch/1")

    def test_non_standard_result_port_is_rejected(self):
        http = FakeHTTP([response({
            "url": "https://cdn.example.com:8080/secret.mp3"})])
        with self.assertRaises(ServiceProtocolError):
            self.client(http).resolve("https://example.com/watch/1")

    def test_mapped_error_does_not_echo_the_body(self):
        secret = "https://cdn.example.com/secret?token=abc"
        http = FakeHTTP([response(
            {"ok": False, "code": "upstream", "error": secret}, status=502)])
        with self.assertRaises(ProviderError) as caught:
            self.client(http).resolve("https://example.com/watch/1")
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("token", str(caught.exception))


class ServiceConfigurationTests(unittest.TestCase):
    def test_bare_host_port_keeps_the_resolver_and_adapters(self):
        settings = make_settings(resolver_service_url="nas:8080",
                                 resolver_service_token=TOKEN)
        resolver = Resolver(settings=settings, http=FakeHTTP([]),
                            cache=Cache(tempfile.mkdtemp(), ttl=1),
                            dns_resolver=fake_dns)
        self.assertIsNotNone(resolver.service)
        self.assertEqual(resolver.service.endpoint,
                         "http://nas:8080/api/resolve")
        self.assertEqual([adapter.name for adapter in resolver.adapters],
                         ["mediafire", "drive", "podomatic", "mega", "direct"])

    def test_invalid_or_metadata_service_base_does_not_disable_adapters(self):
        for value in ("169.254.169.254", "http://[fe80::1]/resolver",
                      "http://metadata.google.internal:8080"):
            with self.subTest(value=value):
                settings = make_settings(resolver_service_url=value,
                                         resolver_service_token=TOKEN)
                logger = RecordingLogger(secrets=[TOKEN])
                resolver = Resolver(settings=settings, http=FakeHTTP([]),
                                    cache=Cache(tempfile.mkdtemp(), ttl=1),
                                    logger=logger, dns_resolver=fake_dns)
                self.assertIsNone(resolver.service)
                self.assertEqual(
                    [adapter.name for adapter in resolver.adapters],
                    ["mediafire", "drive", "podomatic", "mega", "direct"])
                self.assertNotIn(TOKEN, logger.text())

    def test_service_base_link_local_typo_still_resolves_mediafire(self):
        page = "https://www.mediafire.com/file/abc123/set.mp3"
        signed = "https://download239.mediafire.com/abc123/set.mp3?token=s"
        settings = make_settings(resolver_service_url="169.254.169.254")
        resolver = Resolver(
            settings=settings,
            http=FakeHTTP([response('<a href="%s">x</a>' % signed)]),
            cache=Cache(tempfile.mkdtemp(), ttl=300), dns_resolver=fake_dns)
        result = resolver.resolve(page)
        self.assertEqual(result.provider, "mediafire")
        self.assertEqual(result.url, signed)


class FallbackTests(unittest.TestCase):
    def resolver(self, http, settings=None, **kwargs):
        return Resolver(
            settings=settings or make_settings(
                resolver_service_url="http://nas:8080",
                resolver_service_token=TOKEN,
                resolver_enable_mega="true"),
            http=http, cache=Cache(tempfile.mkdtemp(), ttl=1),
            dns_resolver=fake_dns, **kwargs)

    def test_podomatic_page_falls_back_to_service(self):
        http = FakeHTTP([response({
            "url": "https://cdn.example.com/episode.mp3",
            "provider": "podomatic",
        }, url="http://nas:8080/api/resolve")])
        result = self.resolver(http).resolve(
            "https://www.podomatic.com/podcasts/show/episodes/1")
        self.assertEqual(result.source, "service")
        self.assertEqual(result.url, "https://cdn.example.com/episode.mp3")

    def test_mega_enabled_falls_back_to_service(self):
        stream = ("/api/mega/stream?u=https%3A%2F%2Fmega.nz%2Ffile%2Fabc12345"
                  "%23" + "A" * 43 + "&e=1800000000&t=signed-token")
        http = FakeHTTP([response({
            "url": "https://gfs123.userstorage.mega.co.nz/abc",
            "source": "mega",
            "stream": stream,
        }, url="http://nas:8080/api/resolve")])
        result = self.resolver(http).resolve(
            "https://mega.nz/file/abc12345#" + "A" * 43)
        self.assertEqual(result.provider, "mega")
        self.assertEqual(result.source, "service")
        self.assertTrue(result.url.startswith(
            "http://nas:8080/api/mega/stream?"))
        self.assertNotIn("userstorage.mega.co.nz", result.url)
        self.assertEqual(result.headers, {})

    def test_no_service_keeps_in_process_error(self):
        resolver = self.resolver(FakeHTTP([]), settings=make_settings(
            resolver_enable_mega="true"))
        from resolver.base import AdapterNotReady
        with self.assertRaises(AdapterNotReady):
            resolver.resolve("https://mega.nz/file/abc12345#" + "A" * 43)

    def test_use_service_false_skips_fallback(self):
        resolver = self.resolver(FakeHTTP([]))
        from resolver.base import AdapterNotReady
        with self.assertRaises(AdapterNotReady):
            resolver.resolve("https://mega.nz/file/abc12345#" + "A" * 43,
                             use_service=False)

    def test_blocked_url_never_calls_service(self):
        http = FakeHTTP([])
        resolver = self.resolver(http)
        with self.assertRaises(BlockedURL):
            resolver.resolve("http://192.168.1.5/a.mp3")
        self.assertEqual(http.count(), 0)

    def test_non_fallback_error_never_calls_service(self):
        http = FakeHTTP([])
        resolver = self.resolver(http)
        from resolver.base import InvalidURL
        # A Mega URL without its decryption key is a local policy failure; it
        # must not become a service request.
        with self.assertRaises(InvalidURL):
            resolver.resolve("https://mega.nz/file/abc12345")
        self.assertEqual(http.count(), 0)

    def test_direct_never_calls_service(self):
        http = FakeHTTP([])
        resolver = self.resolver(http)
        result = resolver.resolve("https://archive.org/download/x/a.mp3")
        self.assertEqual(result.provider, "direct")
        self.assertEqual(http.count(), 0)


if __name__ == "__main__":
    unittest.main()
