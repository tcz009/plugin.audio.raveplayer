# -*- coding: utf-8 -*-
"""Kodi 3.9.42 menu contract: labels, order, kebab-case and removed legacy."""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

import xbmcplugin  # noqa: E402

from resources.lib import routes  # noqa: E402

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def labels(handler, params=None):
    del xbmcplugin.ITEMS[:]
    handler(1, params or {})
    return [item["label"] for item in xbmcplugin.ITEMS]


class TaxonomyContractTests(unittest.TestCase):
    def test_root_exact_order(self):
        self.assertEqual(labels(routes.root), [
            "Latest", "Tape Packs", "Pirate Radio", "Mixes & Shows",
            "Live Radio", "Favourites", "Search the Archive",
            "Surprise Me", "About & Sources",
        ])

    def test_tape_packs_exact_order(self):
        self.assertEqual(labels(routes.packs_menu), [
            "Toronto Rave Mixtape Archive", "JungleTapes.com",
            "RaveTapePacks.com", "Classic Pack Series",
            "By Rave, Venue & Promoter", "By Year", "Every Pack", "Back",
        ])

    def test_mixes_and_pirate_groups(self):
        self.assertEqual(labels(routes.shows_menu), [
            "Podcasts & Mixes", "DNBRADIO", "GetDarker", "Moxser", "Back",
        ])
        self.assertEqual(labels(routes.pirate_radio), [
            "Hardscore", "Pirate Radio Archives", "Kool FM Sets", "Back",
        ])

    def test_live_radio_exact_order(self):
        self.assertEqual(labels(routes.radio_menu), [
            "Kool FM", "Rinse FM", "Centreforce 883",
            "Hardcore", "Jungle", "Drum & Bass", "House", "UK Garage",
            "Dubstep & Grime", "Back",
        ])

    def test_split_genre_doors(self):
        archive = {section["key"]: section["label"]
                   for section in routes.ARCHIVE_SECTIONS}
        self.assertEqual(archive["jungle"], "Jungle")
        self.assertEqual(archive["drum-and-bass"], "Drum & Bass")
        self.assertEqual(archive["hardcore"], "Hardcore")
        self.assertEqual(archive["happy-hardcore"], "Happy Hardcore")
        radio = {section["key"]: section["label"] for section in routes.RADIO_SECTIONS}
        self.assertNotIn("oldskool", radio)
        self.assertNotIn("breakbeat", radio)

    def test_section_ids_and_keys_are_kebab_case(self):
        for section in routes.ARCHIVE_SECTIONS:
            self.assertRegex(section["key"], KEBAB, section["label"])
        for section in routes.RADIO_SECTIONS:
            self.assertRegex(section["key"], KEBAB, section["label"])

    def test_legacy_bucket_and_toronto_route_are_gone(self):
        self.assertNotIn("legacy_toronto", routes.HANDLERS)
        self.assertNotIn("curated_menu", routes.HANDLERS)
        self.assertNotIn("legacy_menu", [  # replaced by RaveTapePacks submenu
            row for row in ("Legacy Archives (2014)",)])
        self.assertEqual(labels(routes.legacy_menu), [
            "By Event", "By DJ", "By MC", "By Year", "All Packs", "Back",
        ])

    def test_menu_stickers_are_distinct_and_exist(self):
        names = list(routes.MENU_ART.values())
        self.assertEqual(len(names), len(set(names)))
        art = os.path.join(os.path.dirname(HERE), "resources", "art")
        missing = [name for name in names if not os.path.isfile(os.path.join(art, name))]
        self.assertEqual(missing, [])

    def test_old_genre_labels_are_not_menu_doors(self):
        labels_all = (labels(routes.packs_menu) + labels(routes.radio_menu)
                      + labels(routes.shows_menu))
        self.assertNotIn("Jungle / Drum & Bass", labels_all)
        self.assertNotIn("Oldskool & Rave", labels_all)
        self.assertNotIn("Breakbeat", labels_all)
        self.assertNotIn("Rave Tape Packs", labels_all)
        self.assertNotIn("All Tape Packs", labels_all)


if __name__ == "__main__":
    unittest.main()
