# -*- coding: utf-8 -*-
"""Offline tests for the 3.9.53 resolver wiring.

Covers provider selection, header construction, the Mega signed-stream URL,
play-all's lazy per-track wrapping, downloads and quiet failures.  No test
opens a network connection: DNS, HTTP and the resolver itself are injected.
"""

import os
import sys
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODULE = os.path.join(ROOT, "script.module.raveresolver")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(MODULE, "resources", "lib"))
sys.path.insert(0, HERE)

import xbmc  # noqa: E402
import xbmcplugin  # noqa: E402

from resolver import policy  # noqa: E402
from resolver.base import ProviderError, Resolution  # noqa: E402

from resources.lib import downloads, http as plugin_http, routes  # noqa: E402

PUBLIC_INFOS = [
    (2, 1, 6, "", ("93.184.216.34", 443)),
]

MEDIAFIRE_PAGE = "https://www.mediafire.com/file/abc123/set"
DRIVE_PAGE = "https://drive.google.com/file/d/abc123/view"
PODOMATIC_PAGE = "https://www.podomatic.com/podcasts/show/episodes/1"
MEGA_PAGE = "https://mega.nz/file/abc12345#" + "A" * 43

MEDIAFIRE_FILE = "https://download239.mediafire.com/file/set.mp3"
DRIVE_FILE = ("https://drive.usercontent.google.com/download"
              "?id=abc123&export=download&confirm=t")
PODOMATIC_FILE = "https://cdn.podomatic.com/audio/set.mp3"
SIGNED_STREAM = ("http://nas:8080/api/mega/stream"
                 "?u=https%3A%2F%2Fmega.nz%2Ffile%2Fabc12345&e=1800000000&t=tok")


class FakeService(object):
    def __init__(self, base="http://nas:8080"):
        self.stream_base = base


class FakeResolver(object):
    """Small stand-in with the SDK's public selection/resolve surface."""

    def __init__(self, results=None, service_base="http://nas:8080"):
        self.results = dict(results or {})
        self.calls = []
        self.service = FakeService(service_base)

    def provider_for(self, url):
        return policy.provider_for(url)

    def needs_resolution(self, url):
        return self.provider_for(url) not in ("", "direct")

    def resolve(self, url):
        self.calls.append(url)
        value = self.results.get(url)
        if isinstance(value, BaseException):
            raise value
        if value is None:
            raise ProviderError("no fixture for that provider")
        return value


class WiringBase(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.RESOLVED[:]
        del xbmcplugin.ITEMS[:]
        del xbmc.PLAYED[:]
        self.resolver = FakeResolver()
        mock.patch.object(routes, "_resolver",
                          return_value=self.resolver).start()
        mock.patch.object(routes, "_base_url",
                          return_value="plugin://plugin.audio.raveplayer/").start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(xbmcplugin.RESOLVED.clear)
        self.addCleanup(xbmcplugin.ITEMS.clear)
        self.addCleanup(xbmc.PLAYED.clear)

    def add(self, page, resolution):
        self.resolver.results[page] = resolution
        return resolution


class SelectionAndHeaderTests(WiringBase):
    def test_direct_audio_passes_through_without_a_resolver_call(self):
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            self.assertEqual(
                routes._resolve_stream("https://archive.org/download/p/1.mp3"),
                "https://archive.org/download/p/1.mp3")
        self.assertEqual(self.resolver.calls, [])

    def test_unknown_host_is_not_routed_through_the_resolver(self):
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            self.assertEqual(
                routes._resolve_stream("https://live.example.test/stream"),
                "https://live.example.test/stream")
        self.assertEqual(self.resolver.calls, [])

    def test_mediafire_page_resolves_once_and_keeps_headers(self):
        self.add(MEDIAFIRE_PAGE, Resolution(
            MEDIAFIRE_FILE, provider="mediafire",
            headers={"Referer": "https://www.mediafire.com/"}))
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            stream = routes._resolve_stream(MEDIAFIRE_PAGE)
        self.assertTrue(stream.startswith(MEDIAFIRE_FILE + "|Referer="), stream)
        self.assertNotIn(MEDIAFIRE_PAGE, stream)
        self.assertEqual(self.resolver.calls, [MEDIAFIRE_PAGE])

    def test_drive_page_resolves_to_a_direct_url(self):
        self.add(DRIVE_PAGE, Resolution(DRIVE_FILE, provider="drive"))
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            self.assertEqual(routes._resolve_stream(DRIVE_PAGE), DRIVE_FILE)

    def test_podomatic_page_resolves_to_a_direct_url(self):
        self.add(PODOMATIC_PAGE, Resolution(PODOMATIC_FILE,
                                            provider="podomatic"))
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            self.assertEqual(routes._resolve_stream(PODOMATIC_PAGE),
                             PODOMATIC_FILE)

    def test_page_provider_selection_is_local_and_cheap(self):
        self.assertEqual(routes._provider_for(MEDIAFIRE_PAGE), "mediafire")
        self.assertEqual(routes._provider_for(DRIVE_PAGE), "drive")
        self.assertEqual(routes._provider_for(PODOMATIC_PAGE), "podomatic")
        self.assertEqual(routes._provider_for(MEGA_PAGE), "mega")
        # Direct/unknown hosts are not resolver pages: no module import and no
        # resolution, so playing Archive audio keeps the old fast path.
        self.assertEqual(routes._provider_for("https://archive.org/a.mp3"), "")
        self.assertEqual(routes._provider_for("https://example.test/a"), "")


class MegaStreamTests(WiringBase):
    def test_signed_stream_is_absolute_and_headerless(self):
        self.add(MEGA_PAGE, Resolution(SIGNED_STREAM, provider="mega",
                                       source="service", headers={}))
        stream = routes._resolve_stream(MEGA_PAGE)
        self.assertEqual(stream, SIGNED_STREAM)
        self.assertNotIn("|", stream)

    def test_reverse_proxy_prefix_is_preserved(self):
        self.resolver.service = FakeService("https://rave.example/resolver")
        signed = ("https://rave.example/resolver/api/mega/stream"
                  "?u=x&e=1800000000&t=tok")
        self.add(MEGA_PAGE, Resolution(signed, provider="mega",
                                       source="service"))
        self.assertEqual(routes._resolve_stream(MEGA_PAGE), signed)

    def test_ciphertext_url_is_never_returned(self):
        ciphertext = "https://gfs123.userstorage.mega.co.nz/dl/encrypted-blob"
        self.add(MEGA_PAGE, Resolution(ciphertext, provider="mega",
                                       source="service", headers={}))
        self.assertEqual(routes._resolve_stream(MEGA_PAGE), "")

    def test_stream_on_a_foreign_host_is_refused(self):
        foreign = "http://192.168.1.50:8080/api/mega/stream?u=x&e=1&t=tok"
        self.add(MEGA_PAGE, Resolution(foreign, provider="mega",
                                       source="service"))
        self.assertEqual(routes._resolve_stream(MEGA_PAGE), "")

    def test_stream_outside_the_mega_path_is_refused(self):
        wrong = "http://nas:8080/api/resolve?u=x&e=1&t=tok"
        self.add(MEGA_PAGE, Resolution(wrong, provider="mega",
                                       source="service"))
        self.assertEqual(routes._resolve_stream(MEGA_PAGE), "")

    def test_native_mega_result_still_uses_the_public_guard(self):
        native = Resolution("https://gfs123.userstorage.mega.co.nz/dl/signed",
                            provider="mega", source="in-process")
        self.add(MEGA_PAGE, native)
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            self.assertEqual(routes._resolve_stream(MEGA_PAGE), native.url)


class ProtocolOptionTests(WiringBase):
    """3.9.55: Kodi ``|Header=``/protocol options never ride a resolution."""

    def test_provider_page_with_options_is_refused_before_resolve(self):
        pages = (
            MEDIAFIRE_PAGE + "|Header=Referer=https://www.mediafire.com/",
            MEDIAFIRE_PAGE + "|Referer=https://www.mediafire.com/",
            MEDIAFIRE_PAGE + "|Cookie=session",
        )
        for page in pages:
            with self.subTest(page=page):
                self.assertEqual(routes._resolve_stream(page), "")
        self.assertEqual(self.resolver.calls, [])

    def test_resolved_non_mega_url_with_pipe_is_refused(self):
        self.add(MEDIAFIRE_PAGE, Resolution(
            MEDIAFIRE_FILE + "|Cookie=session", provider="mediafire",
            headers={"Referer": "https://www.mediafire.com/"}))
        with mock.patch.object(routes.kodi, "log"):
            self.assertEqual(routes._resolve_stream(MEDIAFIRE_PAGE), "")

    def test_resolved_non_mega_url_with_control_character_is_refused(self):
        self.add(MEDIAFIRE_PAGE, Resolution(
            MEDIAFIRE_FILE + "\nHeader=x", provider="mediafire"))
        self.assertEqual(routes._resolve_stream(MEDIAFIRE_PAGE), "")

    def test_exact_signed_mega_url_is_still_returned(self):
        # The one exception: the service's exact signed stream URL is not a
        # resolved non-Mega URL, even when the input was a provider page.
        self.add(MEDIAFIRE_PAGE, Resolution(
            SIGNED_STREAM, provider="service", source="service"))
        self.assertEqual(routes._resolve_stream(MEDIAFIRE_PAGE), SIGNED_STREAM)


class QuietFailureTests(WiringBase):
    def test_resolve_failure_logs_only_the_error_class(self):
        self.add(MEDIAFIRE_PAGE, ProviderError(
            "failed for " + MEDIAFIRE_PAGE))
        with mock.patch.object(routes.kodi, "log") as log, \
                mock.patch.object(routes.kodi, "notify") as notify:
            self.assertEqual(routes._resolve_stream(MEDIAFIRE_PAGE), "")
        self.assertTrue(log.called)
        self.assertFalse(notify.called)
        joined = " ".join(str(call) for call in log.call_args_list)
        self.assertNotIn(MEDIAFIRE_PAGE, joined)
        self.assertIn("ProviderError", joined)

    def test_play_provider_failure_returns_a_failed_resolve(self):
        self.add(MEDIAFIRE_PAGE, ProviderError("boom"))
        with mock.patch.object(routes.kodi, "notify") as notify:
            routes.play(1, {"url": MEDIAFIRE_PAGE, "label": "Set"})
        self.assertTrue(notify.called)
        self.assertFalse(xbmcplugin.RESOLVED[-1]["ok"])


class PlayRouteTests(WiringBase):
    def test_play_uses_the_resolved_url_and_header_suffix(self):
        self.add(MEDIAFIRE_PAGE, Resolution(
            MEDIAFIRE_FILE, provider="mediafire",
            headers={"Referer": "https://www.mediafire.com/"}))
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            routes.play(1, {"url": MEDIAFIRE_PAGE, "label": "Set"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertTrue(resolved["ok"])
        self.assertTrue(resolved["path"].startswith(MEDIAFIRE_FILE + "|Referer="))
        self.assertNotIn(MEDIAFIRE_PAGE, resolved["path"])
        self.assertEqual(self.resolver.calls, [MEDIAFIRE_PAGE])

    def test_play_mega_hands_the_player_the_signed_url(self):
        self.add(MEGA_PAGE, Resolution(SIGNED_STREAM, provider="mega",
                                       source="service"))
        routes.play(1, {"url": MEGA_PAGE, "label": "Mega set"})
        resolved = xbmcplugin.RESOLVED[-1]
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["path"], SIGNED_STREAM)
        self.assertNotIn("|", resolved["path"])


class PlayAllTests(WiringBase):
    def _playlist(self):
        self.assertTrue(xbmc.PLAYED)
        return xbmc.PLAYED[-1]

    def test_provider_page_is_queued_as_a_plugin_play_url(self):
        tracks = [{"title": "Mediafire set", "url": MEDIAFIRE_PAGE}]
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            self.assertTrue(routes._play_tracks(tracks, album="Pack"))
        playlist = self._playlist()
        path, item = playlist.items[0]
        self.assertTrue(path.startswith("plugin://"), path)
        self.assertIn("mode=play", path)
        self.assertNotEqual(path, MEDIAFIRE_PAGE)
        self.assertEqual(self.resolver.calls, [])
        params = dict(urllib.parse.parse_qsl(
            urllib.parse.urlsplit(path).query))
        self.assertEqual(params["url"], MEDIAFIRE_PAGE)

    def test_mega_page_is_not_queued_as_ciphertext_or_page(self):
        tracks = [{"title": "Mega set", "url": MEGA_PAGE}]
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            self.assertTrue(routes._play_tracks(tracks, album="Pack"))
        path, _item = self._playlist().items[0]
        self.assertNotIn(MEGA_PAGE, path)
        self.assertIn("mode=play", path)

    def test_play_all_keeps_offsets_and_direct_tracks(self):
        tracks = [
            {"title": "Zero", "url": "https://archive.org/download/p/0.mp3"},
            {"title": "One", "url": MEDIAFIRE_PAGE},
            {"title": "Two", "url": "https://archive.org/download/p/2.mp3"},
        ]
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            self.assertTrue(routes._play_tracks(tracks, album="Pack", start=1))
        items = self._playlist().items
        self.assertEqual(len(items), 2)
        first_path, first_item = items[0]
        second_path, second_item = items[1]
        self.assertTrue(first_path.startswith("plugin://"))
        self.assertEqual(second_path, "https://archive.org/download/p/2.mp3")
        # The absolute index is preserved for the OSD track number.
        self.assertEqual(first_item.info["music"]["tracknumber"], 2)
        self.assertEqual(second_item.info["music"]["tracknumber"], 3)

    def test_bridge_host_is_still_wrapped(self):
        tracks = [{"title": "JT", "url":
                   "https://www.jungletapes.com/shows/a.mp3"}]
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            self.assertTrue(routes._play_tracks(tracks, album="Pack"))
        path, _item = self._playlist().items[0]
        self.assertTrue(path.startswith("plugin://"))
        self.assertIn("mode=play", path)


class DownloadPredicateTests(unittest.TestCase):
    def test_resolver_sources_are_allowed(self):
        with mock.patch.object(downloads.http, "safe_stream_url",
                               side_effect=lambda url: url):
            self.assertTrue(downloads.eligible(MEDIAFIRE_FILE, "Rave Resolver"))
            self.assertTrue(downloads.eligible(PODOMATIC_FILE, "Rave Resolver"))
        # Drive's download URL and the signed Mega endpoint have no extension.
        self.assertTrue(downloads.eligible(DRIVE_FILE, "Rave Resolver",
                                           resolved=True))
        self.assertFalse(downloads.eligible(DRIVE_FILE, "Rave Resolver"))

    def test_signed_mega_stream_needs_the_exact_extra_host(self):
        signed = "http://192.168.1.179:8097/api/mega/stream?u=x&e=1&t=tok"
        self.assertTrue(downloads.eligible(
            signed, "Rave Resolver", resolved=True,
            extra_hosts=("192.168.1.179",)))
        self.assertFalse(downloads.eligible(
            signed, "Rave Resolver", resolved=True))
        self.assertFalse(downloads.eligible(
            signed, "Rave Resolver", resolved=True,
            extra_hosts=("other.host",)))

    def test_existing_sources_are_unchanged(self):
        with mock.patch.object(downloads.http, "safe_stream_url",
                               side_effect=lambda url: url):
            self.assertTrue(downloads.eligible(
                "https://archive.org/download/p/1.mp3", "Archive.org"))
            self.assertFalse(downloads.eligible(
                "https://archive.org/download/p/1.mp3", "Rave Resolver"))


class DownloadPlanTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.directory = tempfile.mkdtemp(prefix="rave-resolver-dl-")
        self.addCleanup(self._cleanup)
        mock.patch.dict(os.environ, {downloads.DIR_ENV: self.directory}).start()
        mock.patch.object(downloads.http.socket, "getaddrinfo",
                          return_value=PUBLIC_INFOS).start()
        self.addCleanup(mock.patch.stopall)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.directory, ignore_errors=True)

    def test_resolved_drive_plan_uses_probe_type_for_the_extension(self):
        with mock.patch.object(downloads.http, "probe_media",
                               return_value={"size": 1024,
                                             "content_type": "audio/mp4"}) as probe, \
                mock.patch.object(downloads, "free_bytes",
                                  return_value=1024 * 1024 * 1024), \
                mock.patch.object(downloads, "total_saved_bytes", return_value=0):
            plan = downloads.plan(DRIVE_FILE, "Drive set", "Rave Resolver",
                                  resolved=True)
        self.assertTrue(plan["allowed"], plan)
        self.assertTrue(plan["filename"].endswith(".m4a"), plan["filename"])
        probe.assert_called_once_with(DRIVE_FILE, timeout=20,
                                      allow_private=False)

    def test_mega_plan_probes_the_service_with_allow_private(self):
        signed = "http://192.168.1.179:8097/api/mega/stream?u=x&e=1&t=tok"
        with mock.patch.object(downloads.http, "probe_media",
                               return_value={"size": 2048,
                                             "content_type": "audio/mpeg"}) as probe, \
                mock.patch.object(downloads, "free_bytes",
                                  return_value=1024 * 1024 * 1024), \
                mock.patch.object(downloads, "total_saved_bytes", return_value=0):
            plan = downloads.plan(signed, "Mega set", "Rave Resolver",
                                  resolved=True, extra_hosts=("192.168.1.179",),
                                  allow_private=True)
        self.assertTrue(plan["allowed"], plan)
        self.assertTrue(plan["allow_private"])
        probe.assert_called_once_with(signed, timeout=20, allow_private=True)

    def test_download_forwards_allow_private_to_open_media(self):
        import contextlib

        class Response(object):
            headers = {"Content-Type": "audio/mpeg", "Content-Length": "4"}

            def __init__(self):
                self.sent = False

            def read(self, size=-1):
                if self.sent:
                    return b""
                self.sent = True
                return b"data"

        calls = []

        @contextlib.contextmanager
        def open_media(url, timeout=30, allow_private=False):
            calls.append((url, timeout, allow_private))
            yield Response()

        filename = "mega-12345678.mp3"
        plan = {
            "allowed": True, "reason": "", "source": "Rave Resolver",
            "url": "http://nas:8080/api/mega/stream?u=x&e=1&t=tok",
            "title": "Mega set", "size": 4, "filename": filename,
            "path": os.path.join(self.directory, filename), "key": "k",
            "allow_private": True,
        }
        with mock.patch.object(downloads.http, "open_media", open_media):
            result = downloads.download(plan)
        self.assertTrue(result["ok"], result)
        self.assertEqual(calls, [(plan["url"], 30, True)])

    def test_resolved_plan_still_enforces_audio_content_type(self):
        with mock.patch.object(downloads.http, "probe_media",
                               return_value={"size": 1024,
                                             "content_type": "text/html"}), \
                mock.patch.object(downloads, "free_bytes",
                                  return_value=1024 * 1024 * 1024), \
                mock.patch.object(downloads, "total_saved_bytes", return_value=0):
            plan = downloads.plan(DRIVE_FILE, "Not audio", "Rave Resolver",
                                  resolved=True)
        self.assertFalse(plan["allowed"])
        self.assertIn("audio", plan["reason"].lower())


class DownloadRouteTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]
        self.resolver = FakeResolver()
        mock.patch.object(routes, "_resolver",
                          return_value=self.resolver).start()
        mock.patch.object(routes.kodi, "notify").start()
        self.plan = mock.patch.object(routes.downloads, "plan",
                                      return_value={"allowed": False,
                                                    "reason": "stop"}).start()
        self.addCleanup(mock.patch.stopall)

    def test_mediafire_download_resolves_before_planning(self):
        self.resolver.results[MEDIAFIRE_PAGE] = Resolution(
            MEDIAFIRE_FILE, provider="mediafire",
            headers={"Referer": "https://www.mediafire.com/"})
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            routes.download_start(1, {"url": MEDIAFIRE_PAGE,
                                      "title": "Set", "source": "Archive.org"})
        args, kwargs = self.plan.call_args
        self.assertTrue(args[0].startswith(MEDIAFIRE_FILE + "|Referer="))
        self.assertEqual(args[2], "Rave Resolver")
        self.assertTrue(kwargs["resolved"])
        self.assertFalse(kwargs["allow_private"])
        self.assertEqual(self.resolver.calls, [MEDIAFIRE_PAGE])

    def test_download_page_with_options_is_refused_before_resolve(self):
        with mock.patch.object(routes.kodi, "notify") as notify:
            routes.download_start(1, {
                "url": MEDIAFIRE_PAGE + "|Header=Referer=x", "title": "Set"})
        self.assertFalse(self.plan.called)
        self.assertEqual(self.resolver.calls, [])
        self.assertTrue(notify.called)

    def test_download_resolved_url_with_pipe_is_refused(self):
        self.resolver.results[MEDIAFIRE_PAGE] = Resolution(
            MEDIAFIRE_FILE + "|Cookie=session", provider="mediafire")
        with mock.patch.object(routes.kodi, "notify") as notify:
            routes.download_start(1, {"url": MEDIAFIRE_PAGE, "title": "Set"})
        self.assertFalse(self.plan.called)
        self.assertTrue(notify.called)

    def test_mega_download_uses_the_signed_stream_endpoint(self):
        self.resolver.results[MEGA_PAGE] = Resolution(
            SIGNED_STREAM, provider="mega", source="service")
        routes.download_start(1, {"url": MEGA_PAGE,
                                  "title": "Mega set",
                                  "source": "Archive.org"})
        args, kwargs = self.plan.call_args
        self.assertEqual(args[0], SIGNED_STREAM)
        self.assertEqual(args[2], "Rave Resolver")
        self.assertTrue(kwargs["allow_private"])
        self.assertEqual(kwargs["extra_hosts"], ("nas",))

    def test_resolver_failure_stops_before_planning(self):
        self.resolver.results[MEDIAFIRE_PAGE] = ProviderError("boom")
        with mock.patch.object(routes.kodi, "notify") as notify:
            routes.download_start(1, {"url": MEDIAFIRE_PAGE, "title": "Set"})
        self.assertFalse(self.plan.called)
        self.assertTrue(notify.called)

    def test_direct_source_does_not_call_the_resolver(self):
        with mock.patch.object(routes.http.socket, "getaddrinfo",
                               return_value=PUBLIC_INFOS):
            routes.download_start(1, {
                "url": "https://archive.org/download/p/1.mp3",
                "title": "Archive set", "source": "Archive.org"})
        self.assertEqual(self.resolver.calls, [])
        _args, kwargs = self.plan.call_args
        self.assertFalse(kwargs["resolved"])


class PrivateMediaGuardTests(unittest.TestCase):
    def test_service_media_url_allows_lan_but_rejects_credentials(self):
        ok = "http://192.168.1.179:8097/api/mega/stream?u=x&e=1&t=t"
        self.assertEqual(plugin_http._service_media_url(ok), ok)
        for bad in ("http://user:pass@192.168.1.179/x",
                    "file:///etc/passwd",
                    "http://nas:8080/x\r\nX-Injected: y",
                    "https:///no-host"):
            self.assertEqual(plugin_http._service_media_url(bad), "", bad)

    def test_redirects_in_private_mode_must_stay_on_the_origin(self):
        base = "http://nas:8080/api/mega/stream?u=x"
        self.assertTrue(plugin_http._same_origin(
            "http://nas:8080/api/mega/stream?u=x&hop=1", base))
        self.assertFalse(plugin_http._same_origin(
            "http://192.168.1.50:8080/api/mega/stream?u=x", base))
        self.assertFalse(plugin_http._same_origin(
            "https://nas:8080/api/mega/stream?u=x", base))


class SettingsAndManifestTests(unittest.TestCase):
    def test_plugin_manifest_depends_on_the_module_version(self):
        plugin = ET.parse(os.path.join(ROOT, "addon.xml")).getroot()
        module = ET.parse(os.path.join(MODULE, "addon.xml")).getroot()
        imports = {item.get("addon"): item.get("version")
                   for item in plugin.findall("./requires/import")}
        self.assertEqual(imports.get("script.module.raveresolver"),
                         module.get("version"))
        self.assertEqual(plugin.get("version"), "3.9.71")

    def test_resolver_settings_are_in_the_plugin_ui(self):
        root = ET.parse(os.path.join(ROOT, "resources", "settings.xml")).getroot()
        rows = {item.get("id"): item for item in root.findall(".//setting")}
        for key in ("resolver_service_url", "resolver_service_token",
                    "resolver_service_cookie", "resolver_enable_mega"):
            self.assertIn(key, rows)
        self.assertEqual(rows["resolver_service_url"].get("default"), "")
        self.assertEqual(rows["resolver_service_token"].get("default"), "")
        self.assertEqual(rows["resolver_service_token"].get("option"), "hidden")
        self.assertEqual(rows["resolver_service_cookie"].get("default"), "")
        self.assertEqual(rows["resolver_service_cookie"].get("option"), "hidden")
        self.assertEqual(rows["resolver_enable_mega"].get("default"), "false")

    def test_resolver_is_bound_to_the_plugin_settings(self):
        import resolver
        import resolver.settings as resolver_settings

        old_resolver = routes._RESOLVER
        old_failed = routes._RESOLVER_IMPORT_FAILED
        try:
            routes._RESOLVER = None
            routes._RESOLVER_IMPORT_FAILED = False
            with mock.patch.object(resolver, "Resolver") as factory, \
                    mock.patch.object(resolver_settings, "Settings") as settings:
                self.assertIs(routes._resolver(), factory.return_value)
            settings.assert_called_once_with(addon=routes.kodi.ADDON)
            factory.assert_called_once_with(settings=settings.return_value)
        finally:
            routes._RESOLVER = old_resolver
            routes._RESOLVER_IMPORT_FAILED = old_failed

    def test_screen_dependency_matches_the_plugin_version(self):
        plugin = ET.parse(os.path.join(ROOT, "addon.xml")).getroot()
        screen = ET.parse(os.path.join(
            ROOT, "script.raveplayer.ui", "addon.xml")).getroot()
        imports = {item.get("addon"): item.get("version")
                   for item in screen.findall("./requires/import")}
        self.assertEqual(imports.get("plugin.audio.raveplayer"),
                         plugin.get("version"))


if __name__ == "__main__":
    unittest.main()
