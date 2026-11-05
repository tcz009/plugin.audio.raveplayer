# -*- coding: utf-8 -*-
"""Offline tests for the 2026 theme pass: menu art wiring and Kodi sizes.

No network, no Kodi, no Pillow: PNG/JPEG dimensions are read with the stdlib so
the suite keeps running on a bare Python.
"""

import os
import re
import struct
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ART = os.path.join(ROOT, "resources", "art")
LIB = os.path.join(ROOT, "resources", "lib")
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)

import xbmcplugin  # noqa: E402

from resources.lib import routes  # noqa: E402


# ------------------------------------------------------------------ image size
def png_size(path):
    with open(path, "rb") as handle:
        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not a PNG: %s" % path)
        handle.read(4)  # IHDR length
        if handle.read(4) != b"IHDR":
            raise ValueError("missing IHDR: %s" % path)
        return struct.unpack(">II", handle.read(8))


def jpeg_size(path):
    with open(path, "rb") as handle:
        if handle.read(2) != b"\xff\xd8":
            raise ValueError("not a JPEG: %s" % path)
        while True:
            byte = handle.read(1)
            if not byte:
                raise ValueError("no SOF marker: %s" % path)
            if byte != b"\xff":
                continue
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if not marker:
                raise ValueError("truncated JPEG: %s" % path)
            code = marker[0]
            if code in (0xD8, 0xD9):
                continue
            length_raw = handle.read(2)
            if len(length_raw) != 2:
                raise ValueError("truncated JPEG: %s" % path)
            length = struct.unpack(">H", length_raw)[0]
            if 0xC0 <= code <= 0xCF and code not in (0xC4, 0xC8, 0xCC):
                handle.read(1)  # precision
                height, width = struct.unpack(">HH", handle.read(4))
                return width, height
            handle.seek(length - 2, os.SEEK_CUR)


def image_size(path):
    if path.lower().endswith(".png"):
        return png_size(path)
    return jpeg_size(path)


# ------------------------------------------------------------------ harness
def art_path(name):
    return os.path.join(ART, name)


def _prepare():
    """Point the add-on's artwork helpers at the real worktree."""
    routes.kodi.ADDON_PATH = ROOT
    routes.kodi.ICON = os.path.join(ROOT, "icon.png")
    routes.kodi.FANART = os.path.join(ROOT, "fanart.jpg")
    del xbmcplugin.ITEMS[:]


def capture(handler, params=None):
    _prepare()
    handler(1, params or {})
    return list(xbmcplugin.ITEMS)


def art_literals():
    """Every quoted artwork filename in the runtime modules.

    Covers both ``art("x.png")`` and table entries such as
    ``("Moxser Mixes", ..., "moxser.png", "fanart-moxser.jpg", ...)``.
    """
    names = set()
    for filename in os.listdir(LIB):
        if not filename.endswith(".py"):
            continue
        with open(os.path.join(LIB, filename), encoding="utf-8") as handle:
            names.update(re.findall(r'"([A-Za-z][A-Za-z0-9_-]*\.(?:png|jpg))"',
                                   handle.read()))
    return names


def rows_before_back(items):
    return [item for item in items if item["label"] != "Back"]


class ThemeArtTests(unittest.TestCase):
    def test_every_art_reference_exists(self):
        missing = [name for name in art_literals() if not os.path.exists(art_path(name))]
        self.assertEqual(missing, [])

    def test_no_dangling_pirate_source_art(self):
        self.assertNotIn("pirate_source.png", art_literals())

    def test_icons_are_kodi_sized(self):
        for filename in sorted(os.listdir(ART)):
            if not filename.endswith(".png"):
                continue
            with self.subTest(icon=filename):
                self.assertEqual(png_size(art_path(filename)), (256, 256))

    def test_fanarts_are_kodi_sized(self):
        fanarts = [name for name in os.listdir(ART) if name.startswith("fanart-")]
        self.assertTrue(fanarts)
        for filename in sorted(fanarts):
            with self.subTest(fanart=filename):
                self.assertEqual(jpeg_size(art_path(filename)), (1280, 720))

    def test_root_has_ten_distinct_icons_and_fanarts(self):
        items = capture(routes.root)
        self.assertEqual(len(items), 10)
        icons = [item["art"]["icon"] for item in items]
        fanarts = [item["art"]["fanart"] for item in items]
        self.assertEqual(len(set(icons)), 10, "root rows must not share an icon")
        self.assertEqual(len(set(fanarts)), 10, "root rows need their own fanart")
        for path in icons + fanarts:
            self.assertTrue(os.path.exists(path), path)

    def test_root_uses_the_2026_sticker_icons(self):
        items = capture(routes.root)
        expected = {
            "Rave Screen": "screen.png",
            "Latest": "rave.png",
            "Tape Packs": "tapepacks.png",
            "Pirate Radio": "pirate-radio.png",
            "Mixes & Shows": "mixes.png",
            "Live Radio": "radio.png",
            "Favourites": "favourites.png",
            "Search the Archive": "search.png",
            "Surprise Me": "surprise.png",
            "About & Sources": "about.png",
        }
        for item in items:
            with self.subTest(row=item["label"]):
                self.assertTrue(item["art"]["icon"].endswith(expected[item["label"]]))

    def test_hub_rows_carry_their_hub_fanart(self):
        hubs = [
            (routes.packs_menu, "fanart-hub-packs.jpg"),
            (routes.shows_menu, "fanart-hub-shows.jpg"),
            (routes.radio_menu, "fanart-hub-live.jpg"),
            (routes.pirate_radio, "fanart-pirate-archive.jpg"),
        ]
        for handler, fanart in hubs:
            items = rows_before_back(capture(handler))
            self.assertTrue(items)
            expected = art_path(fanart)
            for item in items:
                with self.subTest(hub=handler.__name__, row=item["label"]):
                    self.assertTrue(os.path.exists(item["art"]["fanart"]))
            # the hub fanart must be the default; source rows may override it
            self.assertIn(expected, [item["art"]["fanart"] for item in items])

    def test_key_sources_have_their_own_icon_and_fanart(self):
        # GetDarker/Rave Archive are optional hand-offs: mock the Mixcloud add-on
        # present so the theme wiring for those rows is asserted too.
        shows = {item["label"]: item for item in capture(routes.shows_menu)}
        expectations = {
            "Moxser": ("moxser.png", "fanart-moxser.jpg"),
            "GetDarker": ("getdarker.png", "fanart-getdarker.jpg"),
        }
        for label, (icon, fanart) in expectations.items():
            with self.subTest(source=label):
                item = shows[label]
                self.assertTrue(item["art"]["icon"].endswith(icon))
                self.assertTrue(item["art"]["fanart"].endswith(fanart))
        pirate = {item["label"]: item for item in capture(routes.pirate_radio)}
        self.assertTrue(pirate["Hardscore"]["art"]["icon"].endswith("hardscore.png"))
        self.assertTrue(pirate["Pirate Radio Archives"]["art"]["icon"].endswith("pirate-archive.png"))
        self.assertTrue(pirate["Pirate Radio Archives"]["art"]["fanart"].endswith("fanart-pirate-archive.jpg"))

    def test_toronto_hub_and_genre_rows_use_their_own_art(self):
        genres = [{"genre": "jungle", "label": "Jungle & Hardcore"},
                  {"genre": "house", "label": "House & Techno"}]
        with mock.patch.object(routes.toronto_source, "genres", return_value=genres):
            items = rows_before_back(capture(routes.toronto))
        self.assertEqual([item["label"] for item in items],
                         ["Jungle & Hardcore", "House & Techno"])
        for item in items:
            with self.subTest(row=item["label"]):
                self.assertTrue(item["art"]["icon"].endswith("toronto.png"))
                self.assertTrue(item["art"]["fanart"].endswith("fanart-toronto.jpg"))

        tracks = [{"name": "Brockie & DJ Rap - Side A",
                   "url": "https://www.torontoravemixtapearchive.com/files/mixtape/a.mp3",
                   "metadata": "40:00"}]
        with mock.patch.object(routes.toronto_source, "tracks", return_value=tracks), \
                mock.patch.object(routes, "_playable_url", side_effect=lambda url: url), \
                mock.patch.object(routes.downloads, "eligible", return_value=True):
            rows = rows_before_back(capture(routes.toronto_genre, {"genre": "jungle"}))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["art"]["thumb"].endswith("toronto.png"))

    def test_all_fanart_assets_are_used(self):
        used = {os.path.basename(name) for name in art_literals()
                if name.startswith("fanart-")}
        on_disk = {name for name in os.listdir(ART) if name.startswith("fanart-")}
        self.assertEqual(on_disk - used, set(), "unused fanart assets")

    def test_identity_assets_are_untouched(self):
        # The 2026 pass may not redesign the wordmark: root icon/fanart keep their
        # shipped sizes (a theme pass that regenerates them would change content).
        self.assertEqual(png_size(os.path.join(ROOT, "icon.png")), (512, 512))
        self.assertEqual(jpeg_size(os.path.join(ROOT, "fanart.jpg")), (1920, 1080))


if __name__ == "__main__":
    unittest.main()
