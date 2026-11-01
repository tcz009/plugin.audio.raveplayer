# -*- coding: utf-8 -*-
"""Offline route tests for downloads: context actions, view, start/delete."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import downloads, routes  # noqa: E402


class DownloadRouteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rave-dlr-")
        os.environ[downloads.DIR_ENV] = self.directory
        del xbmcplugin.ITEMS[:]

    def tearDown(self):
        os.environ.pop(downloads.DIR_ENV, None)
        shutil.rmtree(self.directory, ignore_errors=True)

    def _context(self, item):
        return dict(item["context"])

    def test_archive_track_has_download_context(self):
        track = {"title": "One", "url": "https://archive.org/download/pack/1.mp3",
                 "duration": 60}
        with mock.patch.object(routes.archive, "audio_files", return_value=[track]), \
                mock.patch.object(routes.archive, "item_title", return_value="Pack"):
            routes.archive_item(1, {"id": "pack"})
        command = self._context(xbmcplugin.ITEMS[0])["Download"]
        self.assertIn("mode=download_start", command)
        self.assertIn("source=Archive.org", command)
        self.assertIn("url=https", command)

    def test_moxser_and_hardscore_and_pirate_have_download_context(self):
        details = {"title": "Mix", "date": "", "mp3_url":
                   "https://enceladus.feralhosting.com/moxser/x.mp3"}
        with mock.patch.object(routes.moxser_source, "mix", return_value=details):
            routes.moxser_mix(1, {"page": "https://moxser.com/mixes/x"})
        self.assertIn("Download", self._context(xbmcplugin.ITEMS[0]))
        del xbmcplugin.ITEMS[:]

        rows = [{"title": "Set", "page_url": "https://www.hardscore.com/?p=1",
                 "date": "", "media_urls": ["https://hardscore.com/mixes/x.mp3"],
                 "description": ""}]
        with mock.patch.object(routes.hardscore_source, "items", return_value=rows):
            routes.hardscore(1, {})
        self.assertIn("Download", self._context(xbmcplugin.ITEMS[0]))
        del xbmcplugin.ITEMS[:]

        routes.pirate_station(1, {"station": "Weekend Rush 92.3"})
        self.assertIn("Download", self._context(xbmcplugin.ITEMS[0]))

    def test_platform_links_never_get_a_download_action(self):
        self.assertEqual(routes._download_context(
            "https://www.mixcloud.com/getdarker/x/", "Mix", "Archive.org"), [])
        self.assertEqual(routes._download_context(
            "https://soundcloud.com/x/y.mp3", "Mix", "Archive.org"), [])
        self.assertEqual(routes._download_context(
            "https://youtu.be/abc.mp3", "Mix", "Archive.org"), [])

    def test_only_approved_source_labels_are_downloadable(self):
        self.assertEqual(routes._download_context(
            "https://archive.org/download/p/1.mp3", "Podcast", "Podcasts"), [])
        self.assertEqual(routes._download_context(
            "https://hardscore.com/mixes/x.mp3", "Legacy", "Legacy"), [])
        self.assertTrue(routes._download_context(
            "https://archive.org/download/p/1.mp3", "Track", "Archive.org"))

    def test_favourites_shows_downloads_entry(self):
        with mock.patch.object(routes.favourites, "load", return_value=[]), \
                mock.patch.object(routes.kodi, "notify"):
            routes.fav_list(1, {})
        self.assertIn("Downloads", xbmcplugin.ITEMS[0]["label"])
        self.assertIn("mode=downloads_menu", xbmcplugin.ITEMS[0]["url"])

    def test_downloads_view_lists_local_file_and_missing_entry(self):
        name = "test-12345678.mp3"
        path = os.path.join(self.directory, name)
        with open(path, "wb") as handle:
            handle.write(b"x" * 100)
        downloads._save_index([{
            "key": "k1", "filename": name, "title": "Downloaded Set",
            "source": "Archive.org", "url": "https://archive.org/a.mp3",
            "size": 100, "added": "2026-01-01T00:00:00Z",
        }, {
            "key": "k2", "filename": "gone-12345678.mp3", "title": "Gone",
            "source": "Archive.org", "url": "https://archive.org/b.mp3",
            "size": 50, "added": "2026-01-02T00:00:00Z",
        }])
        routes.downloads_menu(1, {})
        self.assertEqual(len(xbmcplugin.ITEMS), 3)  # two downloads + Back
        local = [item for item in xbmcplugin.ITEMS if item["url"].endswith(name)]
        self.assertEqual(len(local), 1)
        self.assertIn("Delete download", self._context(local[0]))
        self.assertTrue(any("missing" in item["label"] for item in xbmcplugin.ITEMS))

    def test_download_start_confirms_and_calls_downloader(self):
        plan = {"allowed": True, "reason": "", "size": 1024,
                "free": 1024 * 1024 * 1024, "existing": False}
        dialog = mock.Mock()
        dialog.yesno.return_value = True
        with mock.patch.object(routes.downloads, "plan", return_value=plan), \
                mock.patch.object(routes.downloads, "download",
                                  return_value={"ok": True, "reason": ""}) as download, \
                mock.patch.object(routes.kodi, "dialog", return_value=dialog), \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.download_start(1, {"url": "https://archive.org/a.mp3",
                                      "title": "Set", "source": "Archive.org"})
        self.assertTrue(download.called)
        self.assertTrue(notify.called)
        message = " ".join(str(arg) for arg in dialog.yesno.call_args[0])
        self.assertIn("Size:", message)
        self.assertIn("Free space:", message)

    def test_download_start_refuses_low_space(self):
        plan = {"allowed": False, "reason": "Not enough free space.",
                "size": 0, "free": 0, "existing": False}
        with mock.patch.object(routes.downloads, "plan", return_value=plan), \
                mock.patch.object(routes.downloads, "download") as download, \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.download_start(1, {"url": "https://archive.org/a.mp3",
                                      "title": "Set", "source": "Archive.org"})
        self.assertFalse(download.called)
        self.assertTrue(notify.called)

    def test_download_delete_calls_store(self):
        with mock.patch.object(routes.downloads, "delete", return_value=True) as delete, \
                mock.patch.object(routes.kodi, "notify") as notify:
            routes.download_delete(1, {"key": "k1"})
        delete.assert_called_once_with("k1")
        self.assertTrue(notify.called)


if __name__ == "__main__":
    unittest.main()
