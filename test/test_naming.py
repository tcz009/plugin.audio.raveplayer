# -*- coding: utf-8 -*-
"""Artwork naming rules for the 2026 rollout.

Every sticker filename is lowercase kebab-case (``[a-z0-9]+(-[a-z0-9]+)*``);
``ukg`` is spelled ``uk-garage`` everywhere a file, route or test refers to it.
The duplicate-art guard (one distinct sticker per navigation row) lives here too
so a new row has to be a deliberate decision, not a borrowed neighbour.
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ART = os.path.join(ROOT, "resources", "art")
LIB = os.path.join(ROOT, "resources", "lib")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)

from resources.lib import routes  # noqa: E402

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.(?:png|jpg)$")
REF = re.compile(r'"([A-Za-z0-9_. -]+\.(?:png|jpg))"')


class NamingTests(unittest.TestCase):
    def test_every_art_file_is_kebab_case(self):
        for name in sorted(os.listdir(ART)):
            if name in ("spinner",):
                continue
            with self.subTest(asset=name):
                self.assertRegex(name, NAME)

    def test_every_art_reference_is_kebab_case(self):
        for filename in ("routes.py", "ui.py", "kodi.py"):
            if not os.path.exists(os.path.join(LIB, filename)):
                continue
            with open(os.path.join(LIB, filename), encoding="utf-8") as handle:
                for name in REF.findall(handle.read()):
                    with self.subTest(module=filename, asset=name):
                        self.assertRegex(name, NAME)

    def test_uk_garage_is_spelled_out(self):
        self.assertIn("uk-garage", routes.RADIO_BY_KEY)
        self.assertNotIn("ukg", routes.RADIO_BY_KEY)
        for name in routes.MENU_ART.values():
            self.assertNotIn("ukg", name)
        self.assertEqual(routes.MENU_ART["radio_uk_garage"],
                         "radio-uk-garage.png")
        self.assertEqual(routes.RADIO_BY_KEY["uk-garage"]["art"],
                         "radio-uk-garage.png")

    def test_no_duplicate_copies_or_untracked_space_copies(self):
        duplicates = []
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [name for name in dirs
                       if name not in (".git", "repo", "dist", "build", "node_modules")]
            for name in files:
                if re.search(r" 2(?:\.|$)", name):
                    duplicates.append(os.path.join(base, name))
        self.assertEqual(duplicates, [], "remove untracked '* 2.*' duplicates")

    def test_menu_art_is_distinct(self):
        names = list(routes.MENU_ART.values())
        self.assertEqual(len(names), len(set(names)),
                         "two menu rows share a sticker")
        filters = list(routes.FILTER_ART.values())
        self.assertEqual(len(filters), len(set(filters)),
                         "two filter rows share a sticker")
        self.assertEqual(set(names) & set(filters), set(),
                         "a filter row borrows a menu sticker")

    def test_every_menu_sticker_exists(self):
        missing = [name for name in
                   list(routes.MENU_ART.values()) + list(routes.FILTER_ART.values())
                   if not os.path.exists(os.path.join(ART, name))]
        self.assertEqual(missing, [])

    def test_station_rows_use_station_tiles(self):
        stations = {
            "hardcore": "radio-hardcore.png",
            "jungle": "radio-jungle.png",
            "drum-and-bass": "radio-dnb.png",
            "house": "radio-house.png",
            "uk-garage": "radio-uk-garage.png",
            "dubstep-grime": "radio-dubstep-grime.png",
        }
        for key, art in stations.items():
            with self.subTest(station=key):
                self.assertEqual(routes.RADIO_BY_KEY[key]["art"], art)
        self.assertEqual(routes.MENU_ART["pack_pirate"], "pirate-stations.png")


if __name__ == "__main__":
    unittest.main()
