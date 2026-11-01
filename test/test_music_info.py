# -*- coding: utf-8 -*-
"""Kodi 22 music InfoTag compatibility."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import kodi  # noqa: E402


class MusicInfoTests(unittest.TestCase):
    def test_kodi_22_omits_plot_and_keeps_comment(self):
        with mock.patch.object(kodi, "KODI_MAJOR", 22):
            info = kodi.music_info("Track", "A plot")
        self.assertNotIn("plot", info)
        self.assertEqual(info["comment"], "A plot")

    def test_old_kodi_keeps_plot_for_compatibility(self):
        with mock.patch.object(kodi, "KODI_MAJOR", 21):
            info = kodi.music_info("Track", "A plot")
        self.assertEqual(info["plot"], "A plot")
        self.assertEqual(info["comment"], "A plot")
