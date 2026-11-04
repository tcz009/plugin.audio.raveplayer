# -*- coding: utf-8 -*-
"""Regression guard: only explicit play actions may start playback.

The Shield incident looked like random play; the add-on must build directories
and list items without ever calling PlayList/Player.play/setResolvedUrl.  These
tests exercise the real routes with network access mocked out.
"""

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


class PlaybackAuditTests(unittest.TestCase):
    def setUp(self):
        del xbmcplugin.ITEMS[:]
        del xbmcplugin.RESOLVED[:]
        del xbmcplugin.CONTENT[:]
        self.playlist = mock.patch.object(routes.xbmc, "PlayList").start()
        self.player = mock.patch.object(routes.xbmc, "Player").start()
        self.resolved = mock.patch.object(routes.xbmcplugin, "setResolvedUrl").start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(xbmcplugin.ITEMS.clear)

    def _dispatch(self, mode, query=""):
        argv = ["plugin://plugin.audio.raveplayer/", "1",
                "?" + query + ("&" if query else "") + "mode=" + mode]
        routes.dispatch(argv)
        self.assertFalse(self.playlist.called, mode)
        self.assertFalse(self.player.called, mode)
        self.assertFalse(self.resolved.called, mode)

    def test_root_hubs_and_read_only_pages_never_play(self):
        for mode in ("root", "packs_menu", "shows_menu", "radio_menu",
                     "pirate_radio", "about", "legacy_menu", "years",
                     "filters_menu", "rave_nights", "downloads_menu",
                     "legacy_index"):
            self._dispatch(mode)

    def test_latest_and_on_air_rows_only_build_items(self):
        stations = {"kool": [{"name": "Kool FM",
                              "url_resolved": "https://admin.stream.rinse.fm/proxy/kool/stream"}],
                    "rinse": [{"name": "Rinse FM",
                               "url_resolved": "https://admin.stream.rinse.fm/proxy/rinse_uk/stream"}]}
        with mock.patch.object(routes.latest, "merge", return_value=[]), \
                mock.patch.object(routes.latest, "resolve_dnb_streams", return_value={}), \
                mock.patch.object(routes.radio, "curated", side_effect=lambda token: stations.get(token, [])), \
                mock.patch.object(routes.kodi, "notify"):
            self._dispatch("latest")
        labels = [item["label"] for item in xbmcplugin.ITEMS]
        self.assertTrue(any("On air now" in label for label in labels))

    def test_archive_favourites_and_downloads_views_never_play(self):
        with mock.patch.object(routes.archive, "audio_files", return_value=[]), \
                mock.patch.object(routes.archive, "item_title", return_value="Pack"), \
                mock.patch.object(routes.favourites, "load",
                                  return_value=[{"kind": "stream", "target": "https://example.test/a.mp3",
                                                 "title": "Saved stream", "source": "Test"}]), \
                mock.patch.object(routes.downloads, "list_downloads",
                                  return_value=[{"key": "k", "title": "Local",
                                                 "path": "/tmp/local.mp3", "exists": True,
                                                 "size": 1024, "source": "Archive.org",
                                                 "added": "2026-11-01T00:00:00Z",
                                                 "filename": "local.mp3"}]):
            self._dispatch("archive_item", "id=pack")
            self._dispatch("fav_list")
            self._dispatch("downloads_menu")

    def test_explicit_play_routes_still_start_playback(self):
        with mock.patch.object(routes.http.socket, "getaddrinfo", return_value=PUBLIC_INFOS):
            routes.play(1, {"url": "https://example.test/a.mp3"})
        self.assertTrue(self.resolved.called)

    def test_explicit_play_all_still_starts_the_playlist(self):
        tracks = [{"title": "One", "url": "https://archive.org/download/p/1.mp3"}]
        with mock.patch.object(routes.archive, "audio_files", return_value=tracks), \
                mock.patch.object(routes.archive, "item_title", return_value="Pack"), \
                mock.patch.object(routes.http.socket, "getaddrinfo", return_value=PUBLIC_INFOS):
            routes.play_all(1, {"id": "pack"})
        self.assertTrue(self.playlist.called)
        self.assertTrue(self.player.called)

    def test_failed_resolve_does_not_stop_user_playback(self):
        routes._fail_playback(1, "not available")
        self.assertFalse(self.player.called)
        self.assertTrue(self.resolved.called)
        self.assertFalse(self.resolved.call_args[0][1])
