# -*- coding: utf-8 -*-
"""2026 look overhaul: tokens, native-list row semantics and status lines.

Offline only (Kodi stubs, no network).  The design contract is
``docs/rave-screen/RAVE-SCREEN-DESIGN.md``; the implementation notes and
before/after boards are in ``docs/LOOK-OVERHAUL.md``.
"""

import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCREEN = os.path.join(ROOT, "script.raveplayer.ui")
XML = os.path.join(SCREEN, "resources", "skins", "Default", "720p",
                   "script-raveplayer-ui.xml")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)

import xbmcplugin  # noqa: E402

from resources.lib import kodi, look, routes, ui  # noqa: E402


def _items():
    return list(xbmcplugin.ITEMS)


def _reset():
    del xbmcplugin.ITEMS[:]
    del xbmcplugin.CONTENT[:]


class TokenTests(unittest.TestCase):
    def test_tokens_match_the_design_spec(self):
        self.assertEqual(look.TOKENS["ink"], "0xFF07070B")
        self.assertEqual(look.TOKENS["paper"], "0xFFF2EEE3")
        self.assertEqual(look.TOKENS["muted"], "0xFFA8A399")
        self.assertEqual(look.TOKENS["acid"], "0xFFE8FF00")
        self.assertEqual(look.TOKENS["magenta"], "0xFFFF2D8F")
        self.assertEqual(look.TOKENS["cyan"], "0xFF22E6FF")
        self.assertEqual(look.TOKENS["orange"], "0xFFFF6A1A")

    def test_status_tags_use_one_spot_per_state(self):
        self.assertEqual(look.STATUS["empty"], ("E8FF00", "STANDBY"))
        self.assertEqual(look.STATUS["error"], ("FF2D8F", "ERROR"))
        self.assertEqual(look.STATUS["loading"], ("22E6FF", "LOADING"))

    def test_rp_codes_are_print_furniture_only(self):
        self.assertEqual(look.rp_code("latest"), "RP-01")
        self.assertEqual(look.rp_code("packs_menu"), "RP-03")
        self.assertEqual(look.rp_code("about"), "RP-99")
        self.assertEqual(look.rp_code("not-a-route"), "")


class RootOrderTests(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_root_order_matches_the_web_rail_for_shared_rooms(self):
        routes.root(1, {})
        labels = [item["label"] for item in _items()]
        self.assertEqual(labels, [
            "Rave Screen", "Latest", "Tape Packs", "Pirate Radio",
            "Mixes & Shows", "Live Radio", "Favourites",
            "Search the Archive", "Surprise Me", "About & Sources",
        ])
        # The web rail's order for the shared rooms, in the same positions.
        shared = [label for label in labels if label in (
            "Latest", "Tape Packs", "Pirate Radio", "Mixes & Shows",
            "Live Radio", "Favourites")]
        self.assertEqual(shared, ["Latest", "Tape Packs", "Pirate Radio",
                                  "Mixes & Shows", "Live Radio", "Favourites"])

    def test_every_root_and_hub_row_has_a_fact_and_a_plot(self):
        for handler in (routes.root, routes.packs_menu, routes.shows_menu,
                        routes.radio_menu):
            _reset()
            handler(1, {})
            for item in _items():
                if item["label"] in ("Back", "End of list"):
                    continue
                with self.subTest(route=handler.__name__, row=item["label"]):
                    self.assertTrue(item["label2"], item["label"])
                    self.assertLessEqual(len(item["label2"]), ui.MAX_LABEL2_CHARS)
                    self.assertTrue((item["info"].get("video") or {}).get("plot"),
                                    item["label"])


class ArtSemanticsTests(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_archive_row_keeps_the_tape_sticker_and_the_pack_cover(self):
        with mock.patch.object(routes.archive, "thumb",
                               return_value="https://archive.example/cover.jpg"):
            routes._archive_items(1, [{"identifier": "pack-1",
                                       "title": "Dreamscape 19 - 1995"}])
        art = _items()[0]["art"]
        self.assertTrue(art["icon"].endswith("tapepacks.png"))
        self.assertEqual(art["thumb"], "https://archive.example/cover.jpg")
        self.assertEqual(art["poster"], "https://archive.example/cover.jpg")
        self.assertTrue(art["fanart"].endswith("fanart.jpg"))
        self.assertEqual(art["fanart"], art["landscape"])

    def test_track_row_uses_a_square_cover_and_16_9_fanart(self):
        with mock.patch.object(routes.archive, "audio_files",
                               return_value=[{"title": "Tape 1 - Carl Cox",
                                              "url": "https://archive.org/download/p/1.mp3",
                                              "duration": 2637}]), \
                mock.patch.object(routes.archive, "item_title",
                                  return_value="Dreamscape 19 - 1995"), \
                mock.patch.object(routes.archive, "thumb",
                                  return_value="https://archive.example/cover.jpg"):
            routes.archive_item(1, {"id": "pack-1"})
        art = _items()[0]["art"]
        self.assertEqual(art["thumb"], "https://archive.example/cover.jpg")
        self.assertEqual(art["poster"], "https://archive.example/cover.jpg")
        self.assertTrue(art["icon"].endswith("tapepacks.png"))
        self.assertEqual(art["fanart"], kodi.FANART)
        self.assertEqual(art["landscape"], kodi.FANART)

    def test_live_station_uses_the_radio_sticker_not_a_round_face(self):
        station = {"name": "Kool FM", "url": "https://stream.example/a",
                   "favicon": "http://127.0.0.1/icon.png"}
        with mock.patch.object(routes.radio, "display",
                               return_value=("Kool FM", "London")), \
                mock.patch.object(routes.radio, "stream_url",
                                  return_value="https://stream.example/a"), \
                mock.patch.object(routes.http.socket, "getaddrinfo",
                                  return_value=[(2, 1, 6, "",
                                                 ("93.184.216.34", 443))]):
            routes._station_items(1, [station], "Live")
        art = _items()[0]["art"]
        self.assertTrue(art["icon"].endswith("radio.png"))
        self.assertTrue(art["thumb"].endswith("radio.png"))

    def test_about_rows_carry_a_fact(self):
        routes.about(1, {})
        rows = [item for item in _items() if item["label"] != "Back"]
        self.assertEqual(len(rows), 15)
        for item in rows:
            with self.subTest(row=item["label"]):
                self.assertTrue(item["label2"], item["label"])


class StatusLineTests(unittest.TestCase):
    def setUp(self):
        _reset()

    def _status(self, rows):
        return [row for row in rows if "STANDBY" in row["label"]
                or "ERROR" in row["label"] or "LOADING" in row["label"]]

    def test_latest_empty_renders_a_retryable_standby_row(self):
        with mock.patch.object(routes.latest, "merge", return_value=[]), \
                mock.patch.object(routes.radio, "curated", return_value=[]), \
                mock.patch.object(routes.kodi, "notify"):
            routes.latest_view(1, {})
        rows = self._status(_items())
        self.assertEqual(len(rows), 1)
        self.assertIn("Nothing new right now", rows[0]["label"])
        self.assertEqual(rows[0]["label2"], "empty")
        self.assertTrue(rows[0]["isFolder"])
        self.assertIn("mode=latest", rows[0]["url"])
        self.assertIn("Retry", [label for label, _ in rows[0]["context"]])

    def test_archive_empty_renders_a_standby_row(self):
        with mock.patch.object(routes.archive, "search", return_value=([], 0)), \
                mock.patch.object(routes.kodi, "notify"):
            routes.archive_list(1, {"key": "jungle"})
        rows = self._status(_items())
        self.assertEqual(len(rows), 1)
        self.assertIn("Nothing in Jungle right now", rows[0]["label"])
        self.assertIn("key=jungle", rows[0]["url"])

    def test_search_empty_renders_a_standby_row(self):
        with mock.patch.object(routes.archive, "search", return_value=([], 0)), \
                mock.patch.object(routes.kodi, "notify"):
            routes.search(1, {"q": "dreamscape"})
        rows = self._status(_items())
        self.assertEqual(len(rows), 1)
        self.assertIn("No results", rows[0]["label"])
        self.assertIn("q=dreamscape", rows[0]["url"])

    def test_downloads_empty_renders_a_standby_row_and_back(self):
        with mock.patch.object(routes.downloads, "list_downloads",
                               return_value=[]), \
                mock.patch.object(routes.kodi, "notify"):
            routes.downloads_menu(1, {})
        labels = [item["label"] for item in _items()]
        self.assertEqual(len(self._status(_items())), 1)
        self.assertIn("Back", labels)

    def test_favourites_empty_keeps_downloads_visible(self):
        with mock.patch.object(routes.favourites, "load", return_value=[]), \
                mock.patch.object(routes.downloads, "list_downloads",
                                  return_value=[]), \
                mock.patch.object(routes.kodi, "notify"):
            routes.fav_list(1, {})
        labels = [item["label"] for item in _items()]
        self.assertTrue(any(label.startswith("Downloads") for label in labels))
        self.assertEqual(len(self._status(_items())), 1)


class RaveScreenXmlTests(unittest.TestCase):
    def test_every_texture_reference_exists(self):
        tree = ET.parse(XML)
        missing = []
        for control in tree.iter():
            if control.tag != "texture":
                continue
            texture = (control.text or "").strip()
            if not texture.startswith("special://home/addons/script.raveplayer.ui/"):
                continue
            relative = texture.split("script.raveplayer.ui/", 1)[1]
            if not os.path.isfile(os.path.join(SCREEN, relative)):
                missing.append(relative)
        self.assertEqual(missing, [])

    def test_only_stock_skin_fonts_are_used(self):
        tree = ET.parse(XML)
        fonts = {node.text for node in tree.iter("font") if node.text}
        self.assertLessEqual(fonts, {"font10", "font12", "font13"})

    def test_focus_furniture_is_present(self):
        with open(XML, encoding="utf-8") as handle:
            source = handle.read()
        for asset in ("focus-plate-474x40.png", "focus-plate-shadow-474x40.png",
                      "focus-bar-6x34.png", "row-separator-480x1.png",
                      "icon-shadow-36x36.png", "sticker-focus.png"):
            with self.subTest(asset=asset):
                self.assertIn(asset, source)
        self.assertIn("<focusedlayout", source)
        # No control may pin <visible>false</visible>: Kodi re-evaluates it and
        # it silently defeats Control.setVisible(True) (the 3.9.48 splash bug).
        tree = ET.parse(XML)
        pinned = [node.text for node in tree.iter("visible")
                  if (node.text or "").strip().lower() == "false"]
        self.assertEqual(pinned, [])

    def test_works_are_sentence_case_in_the_row_list(self):
        sys.path.insert(0, SCREEN)
        from raveui.data import RaveData

        data = RaveData(modules=object(), root=ROOT, script_root=SCREEN)
        labels = [row.label for row in data.home_rows()]
        self.assertEqual(labels, [
            "Latest", "Toronto Rave Mixtape Archive", "JungleTapes.com",
            "RaveTapePacks.com", "Live Radio", "Spinning Surprise",
        ])
        for label in labels:
            with self.subTest(label=label):
                self.assertFalse(re.search(r"\b[A-Z]{4,}\b", label), label)


if __name__ == "__main__":
    unittest.main()
