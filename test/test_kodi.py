# -*- coding: utf-8 -*-
"""Offline tests for the small Kodi wrapper layer."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

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


if __name__ == "__main__":
    unittest.main()
