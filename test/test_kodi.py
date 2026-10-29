# -*- coding: utf-8 -*-
"""Offline tests for the small Kodi wrapper layer."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import kodi  # noqa: E402


class KodiWrapperTests(unittest.TestCase):
    def test_notify_strips_commas_and_newlines(self):
        with mock.patch.object(kodi.xbmc, "executebuiltin") as execute:
            kodi.notify("one, two\nthree", heading="Head, ing", time=1000)
        command = execute.call_args[0][0]
        self.assertIn("Head  ing", command)
        self.assertIn("one  two three", command)
        self.assertIn(",1000,", command)

    def test_notify_handles_bad_timeout(self):
        with mock.patch.object(kodi.xbmc, "executebuiltin") as execute:
            kodi.notify("message", time="soon")
        self.assertIn(",4000,", execute.call_args[0][0])

    def test_setting_bool_accepts_kodi_spellings(self):
        for raw in ("true", "TRUE", "1", "yes", "on"):
            with mock.patch.object(kodi.ADDON, "getSetting", return_value=raw):
                self.assertTrue(kodi.setting_bool("flag"), raw)
        for raw in ("false", "0", "", None):
            with mock.patch.object(kodi.ADDON, "getSetting", return_value=raw):
                self.assertFalse(kodi.setting_bool("flag"), raw)

    def test_setting_int_falls_back_on_bad_values(self):
        with mock.patch.object(kodi.ADDON, "getSetting", return_value="nope"):
            self.assertEqual(kodi.setting_int("n", 7), 7)
        with mock.patch.object(kodi.ADDON, "getSetting", return_value="12"):
            self.assertEqual(kodi.setting_int("n", 7), 12)

    def test_end_directory_does_not_cache_to_disk_by_default(self):
        del xbmcplugin.CACHE_FLAGS[:]
        kodi.end_directory(1, "songs")
        kodi.end_directory(2, "files", cache=True)
        self.assertEqual(xbmcplugin.CACHE_FLAGS, [False, True])

    def test_refresh_asks_kodi_to_reload_the_folder(self):
        with mock.patch.object(kodi.xbmc, "executebuiltin") as execute:
            kodi.refresh()
        self.assertEqual(execute.call_args[0][0], "Container.Refresh")

    def test_translate_path_leaves_plain_paths_alone(self):
        self.assertEqual(kodi.translate_path("/tmp/x"), "/tmp/x")
        self.assertEqual(kodi.translate_path(None), "")


if __name__ == "__main__":
    unittest.main()
