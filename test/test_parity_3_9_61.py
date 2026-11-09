# -*- coding: utf-8 -*-
"""Classic-menu ↔ full-screen parity contract for 3.9.61.

The plugin's ``classic_root`` is the documented fallback and the owner's old
directory.  Every page mode it can reach must have a screen room, row or
action.  This test keeps the two release surfaces honest:

* :data:`MATRIX` is the reviewed destination matrix (old mode → screen path);
* ``routes.HANDLERS`` may not grow a page mode that is absent from the matrix;
* the screen graph is walked with the same fake plugin data the screen tests
  use, so a row that exists only in the matrix but not in the UI fails.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCREEN = os.path.join(ROOT, "script.raveplayer.ui")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, SCREEN)

from resources.lib import routes  # noqa: E402
from raveui.data import RaveData  # noqa: E402
from raveui.screens.live import GENRE_ROWS, LiveRadio  # noqa: E402
from test_rave_screen import fake_modules  # noqa: E402


# destination, classic mode, screen path
MATRIX = (
    ("Latest", "latest", "Home → Latest"),
    ("Tape Packs", "packs_menu", "Home → Tape Packs"),
    ("Toronto Rave Mixtape Archive", "toronto", "Tape Packs → Toronto"),
    ("Toronto genre page", "toronto_genre", "Tape Packs → Toronto → genre"),
    ("JungleTapes.com", "legacy_jt", "Tape Packs → JungleTapes"),
    ("JungleTapes show", "legacy_jt_show", "Tape Packs → JungleTapes → show"),
    ("RaveTapePacks.com", "legacy_menu", "Tape Packs → RaveTapePacks"),
    ("RaveTapePacks index", "legacy_index", "Tape Packs → RaveTapePacks → index"),
    ("RaveTapePacks category", "legacy_category",
     "Tape Packs → RaveTapePacks → index → category"),
    ("RaveTapePacks pack", "legacy_post", "Tape Packs → RaveTapePacks → pack"),
    ("Saved RaveTapePacks pack", "legacy_pack",
     "Favourites → saved RaveTapePacks pack"),
    ("RaveTapePacks all packs", "legacy_packs",
     "Tape Packs → RaveTapePacks → All Packs"),
    ("Classic Pack Series", "filters_menu", "Tape Packs → Classic Pack Series"),
    ("Classic filter", "filter_list",
     "Tape Packs → Classic Pack Series → series"),
    ("Filter live door", "filter_live",
     "Tape Packs → Classic Pack Series → series → live now"),
    ("By Rave, Venue & Promoter", "rave_nights", "Tape Packs → By Rave"),
    ("Rave list", "rave_list", "Tape Packs → By Rave → rave"),
    ("By Year", "years", "Tape Packs → By Year"),
    ("Year list", "year_list", "Tape Packs → By Year → year"),
    ("Every Pack", "archive_list", "Tape Packs → Every Pack"),
    ("Archive pack detail", "archive_item", "Tape Packs → Every Pack → pack"),
    ("Pirate Radio", "pirate_radio", "Home → Pirate Radio"),
    ("Hardscore", "hardscore", "Pirate Radio → Hardscore"),
    ("Hardscore post", "hardscore_event", "Pirate Radio → Hardscore → post"),
    ("Pirate Radio Archives", "pirate_menu", "Pirate Radio → Archives"),
    ("Pirate station", "pirate_station", "Pirate Radio → Archives → station"),
    ("Kool FM sets", "filter_list", "Pirate Radio → Kool FM Sets"),
    ("Mixes & Shows", "shows_menu", "Home → Mixes & Shows"),
    ("Podcasts & Mixes", "media_menu", "Mixes & Shows → Podcasts & Mixes"),
    ("Podcast feed", "feed", "Mixes & Shows → Podcasts & Mixes → feed"),
    ("DNBRADIO", "dnb_list", "Mixes & Shows → DNBRADIO"),
    ("DNBRADIO show", "dnb_play", "Mixes & Shows → DNBRADIO → show"),
    ("GetDarker", "getdarker", "Mixes & Shows → GetDarker"),
    ("GetDarker page", "getdarker_page", "Mixes & Shows → GetDarker → set"),
    ("Moxser", "moxser", "Mixes & Shows → Moxser"),
    ("Moxser mix", "moxser_mix", "Mixes & Shows → Moxser → mix"),
    ("Mikus Musik", "legacy_blog", "Mixes & Shows → Mikus Musik"),
    ("Mikus post", "legacy_blog_post", "Mixes & Shows → Mikus Musik → post"),
    ("Demodulated Mixtapes", "legacy_blog", "Mixes & Shows → Demodulated"),
    ("Live Radio", "radio_menu", "Home → Live Radio"),
    ("Live station", "station_live", "Live Radio → curated station"),
    ("Live genre door", "radio_tag", "Live Radio → genre door → stations"),
    ("Favourites", "fav_list", "Home → Favourites"),
    ("Downloads", "downloads_menu", "Home → Downloads"),
    ("Search", "search", "Home → Search"),
    ("Surprise Me", "surprise", "Home → Spinning Surprise"),
    ("About & Sources", "about", "Home → About"),
    ("Classic lists fallback", "classic_root", "About → Classic lists action"),
)

# Routes that are playback/context actions rather than directory pages.
ACTION_MODES = frozenset((
    "play", "dnb_play", "play_all", "play_all_collection", "fav_add",
    "fav_remove", "download_start", "download_delete",
))
ROOT_MODES = frozenset(("root", "screen"))
# Registered but with no menu/deep-link path from classic_root: keep this list
# explicit so it cannot quietly grow.
ORPHAN_MODES = frozenset(("mixcloud_account",))


class ParityMatrixTests(unittest.TestCase):
    def data(self):
        return RaveData(modules=fake_modules(), root=ROOT, script_root=SCREEN)

    def test_matrix_modes_all_exist_in_the_plugin(self):
        for label, mode, path in MATRIX:
            with self.subTest(destination=label):
                self.assertIn(mode, routes.HANDLERS, label)
                self.assertTrue(path)

    def test_no_classic_page_mode_is_missing_from_the_matrix(self):
        mapped = {mode for _, mode, _ in MATRIX}
        expected = mapped | set(ACTION_MODES) | set(ROOT_MODES) | set(ORPHAN_MODES)
        self.assertEqual(set(routes.HANDLERS) - expected, set())
        self.assertEqual(mapped - set(routes.HANDLERS), set())

    def test_screen_walks_every_classic_destination(self):
        data = self.data()
        home = {row.key: row for row in data.home_rows()}
        for key in ("latest", "packs", "pirate", "mixes", "live", "search",
                    "favourites", "downloads", "about", "surprise"):
            self.assertIn(key, home)

        packs = {row.target: row for row in data.room("packs").rows}
        for target in ("toronto", "jungletapes", "ravetapepacks", "filters",
                       "raves", "packs_years", "tapepacks"):
            self.assertIn(target, packs)
        series = data.children(packs["filters"], 1, 50)
        self.assertTrue(series.rows)
        self.assertEqual(series.rows[0].kind, "filter")
        self.assertTrue(data.children(series.rows[0], 1, 50).rows)
        raves = data.children(packs["raves"], 1, 50)
        self.assertEqual(raves.rows[0].kind, "rave")
        self.assertTrue(data.children(raves.rows[0], 1, 50).rows)
        years = data.children(packs["packs_years"], 1, 50)
        self.assertEqual(years.rows[0].kind, "year")
        self.assertTrue(data.children(years.rows[0], 1, 50).rows)
        self.assertTrue(data.children(packs["tapepacks"], 1, 50).rows)

        pirate = {row.target: row for row in data.room("pirate").rows}
        self.assertEqual(set(pirate), {"hardscore_source", "pirate_source",
                                       "kool"})
        self.assertTrue(data.children(pirate["hardscore_source"], 1, 50).rows)
        self.assertTrue(data.children(pirate["pirate_source"], 1, 50).rows)
        self.assertTrue(data.children(pirate["kool"], 1, 50).rows)

        mixes = data.room("mixes").rows
        labels = {row.label for row in mixes}
        for label in ("Podcasts & Mixes", "DNBRADIO Shows", "GetDarker",
                      "Moxser", "Mikus Musik", "Demodulated Mixtapes",
                      "Hardscore", "Pirate Radio Archives"):
            self.assertIn(label, labels)
        for row in mixes:
            self.assertTrue(data.children(row, 1, 25).rows or
                            row.kind in ("dnb_show", "moxser_mix"))

        live_rows = LiveRadio(modules=data.modules).rows()
        self.assertIn("Pirate Radio", [row.title for row in live_rows])
        self.assertEqual([row.title for row in live_rows[4:]],
                         [row.title for row in GENRE_ROWS])

    def test_about_keeps_the_classic_directory_reachable(self):
        from raveui.screens.library import LibraryScreens

        screen = LibraryScreens(backend=_AboutBackend()).about()
        row = next(row for row in screen.rows if row.label == "Classic lists")
        self.assertEqual(row.payload["action"], "classic")
        self.assertEqual(row.payload["url"],
                         "plugin://plugin.audio.raveplayer/?mode=classic_root")


class _AboutBackend(object):
    def page_size(self):
        return 50

    def about(self):
        return {"name": "Rave Player", "version": "3.9.61"}

    def art(self, name):
        return "/art/" + name


if __name__ == "__main__":
    unittest.main()
