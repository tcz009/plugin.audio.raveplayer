#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Production art rollout — Direction C2 (trippy rave) + station tiles.

Owner-approved direction: Direction C2 for the full duplicated-row set (all 38
rows) and the ten Live Radio station tiles.  This script is the production
generator: it imports the two approved studies read-only and renders the
accepted glyphs at the two real delivery sizes.

    resources/art/<name>.png          256x256  Kodi icons
    <web>/static/art/<name>.png       512x512  web / PWA icons
    docs/theme-2026/final-rollout-sheet.png   review surface (all rows 64 px)

The studies stay the source of truth:

    docs/theme-2026/directions-3.9.33-trippy-c2/build_direction_c2.py
    docs/theme-2026/stations/build_stations.py

The print pipeline (wobble / melt / warp / plates / halftone / furniture) comes
from those modules; only per-row poses live here so that a repeat of one object
is a different pose, not a recolour.

Naming rule: every filename this script writes is lowercase kebab-case
(``[a-z0-9]+(-[a-z0-9]+)*``).  ``uk-garage`` is the canonical spelling; the old
``ukg`` token is gone from file names, routes and tests.

    python3 scripts/make-rollout-art.py
    python3 scripts/make-rollout-art.py --no-web --no-sheet
    python3 scripts/make-rollout-art.py --check

Pillow + numpy are build-time only.
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import os
import random
import re
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "resources", "art")
WEB = os.environ.get("RAVE_WEB_ROOT") or os.path.join(
    os.path.dirname(ROOT), "Rave Player")
WEB_ART = os.path.join(WEB, "static", "art")
THEME = os.path.join(ROOT, "docs", "theme-2026")
SHEET = os.path.join(THEME, "final-rollout-sheet.png")
SHEET_PREVIEW = os.path.join(THEME, "final-rollout-64px.png")

C2_DIR = os.path.join(THEME, "directions-3.9.33-trippy-c2")
STUDY_DIR = os.path.join(THEME, "directions-3.9.33-trippy")
STN_DIR = os.path.join(THEME, "stations")

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
KODI_SIZE = 256
WEB_SIZE = 512


# --------------------------------------------------------------- study import
def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C2 = _load(os.path.join(C2_DIR, "build_direction_c2.py"), "rave_c2_rollout")
STN = _load(os.path.join(STN_DIR, "build_stations.py"), "rave_stations_rollout")
ART_MOD = C2.art
INK, PAPER, MUTED = C2.INK, C2.PAPER, C2.MUTED
ACID, MAGENTA, CYAN, ORANGE = C2.ACID, C2.MAGENTA, C2.CYAN, C2.ORANGE
GLYPHS = C2.GLYPHS
Pen = C2.Pen
rgba = C2.rgba
PX = C2.PX
SS = C2.SS


# --------------------------------------------------------------------- recipes
# The 38 rows that had no own sticker (3.9.32 / 1.6.40 set), re-cut in C2.
# field / plate pair / code follow the accepted colour rhythm; ``pose`` is what
# makes a repeat of one object read as a different drawing:
#   scale  - glyph scale about the tile centre
#   dx,dy  - design-space offset
#   pair   - draw the mark twice (a stack, not a lone object)
# ``fallback`` records the RATIONALE watch-list change where it was applied.
ROWS = [
    dict(name="rave-tapes", label="Rave Tape Packs", glyph="cassette",
         field=ACID, pa=MAGENTA, pb=CYAN, code="RP-21", rot=-2.0,
         warp=dict(amp=8.0, freq=1.4, phase=0.20, sag=4.0),
         melt=dict(count=3, max_len=54, min_len=30),
         pose=dict(scale=0.98, dx=0, dy=4, pair=True, pair_scale=0.62,
                   pair_dx=-64, pair_dy=-54)),
    dict(name="tapepacks-all", label="All Tape Packs", glyph="cassette",
         field=CYAN, pa=MAGENTA, pb=ACID, code="RP-22", rot=1.5,
         warp=dict(amp=7.0, freq=1.6, phase=0.50, sag=4.0),
         melt=dict(count=2, max_len=46, min_len=26),
         pose=dict(scale=0.92, dx=6, dy=-6)),
    dict(name="years", label="By Year", glyph="tape",
         field=ORANGE, pa=MAGENTA, pb=ACID, code="RP-23", rot=-4.0,
         warp=dict(amp=6.0, freq=1.8, phase=0.15, sag=6.0),
         melt=dict(count=3, max_len=46, min_len=26),
         pose=dict(scale=0.90, dx=-8, dy=4)),
    dict(name="series", label="Classic Pack Series", glyph="cassette",
         field=MAGENTA, pa=CYAN, pb=ACID, code="RP-24", rot=3.0,
         warp=dict(amp=7.5, freq=1.5, phase=0.30, sag=4.0),
         melt=dict(count=3, max_len=48, min_len=28),
         pose=dict(scale=0.98, dx=0, dy=-2, pair=True, pair_scale=0.62,
                   pair_dx=60, pair_dy=52)),
    dict(name="rave-nights", label="By Rave & Venue", glyph="flyer",
         field=CYAN, pa=MAGENTA, pb=ACID, code="RP-25", rot=-1.5,
         warp=dict(amp=8.0, freq=1.5, phase=0.45, sag=4.0),
         melt=dict(count=2, max_len=44, min_len=26),
         pose=dict(scale=0.96, dx=0, dy=0),
         fallback="glowsticks -> flyer (venue listings are flyers)"),
    dict(name="podcasts", label="Podcasts & Mixes", glyph="tape",
         field=MAGENTA, pa=CYAN, pb=ACID, code="RP-27", rot=7.0,
         warp=dict(amp=6.0, freq=1.8, phase=0.15, sag=6.0),
         melt=dict(count=3, max_len=46, min_len=26),
         pose=dict(scale=0.94, dx=-6, dy=2),
         fallback="flyer -> second cassette (the surest 64 px read)"),
    dict(name="dnb", label="DNB Radio", glyph="speaker",
         field=MAGENTA, pa=CYAN, pb=ACID, code="RP-26", rot=2.0,
         warp=dict(amp=9.0, freq=1.5, phase=0.40, sag=4.0),
         melt=dict(count=3, max_len=52, min_len=30),
         pose=dict(scale=0.90, dx=0, dy=6)),
    dict(name="dreamscape", label="Dreamscape", glyph="balloon",
         field=PAPER, pa=MAGENTA, pb=CYAN, code="RP-28", rot=-5.0,
         warp=dict(amp=8.0, freq=1.6, phase=0.30, sag=3.0),
         melt=dict(count=2, max_len=44, min_len=26),
         pose=dict(scale=1.0, dx=0, dy=0)),
    dict(name="legacy", label="Legacy Sites (2014)", glyph="flyer",
         field=PAPER, pa=MAGENTA, pb=CYAN, code="RP-29", rot=4.0,
         warp=dict(amp=6.5, freq=1.7, phase=0.60, sag=4.0),
         melt=dict(count=3, max_len=48, min_len=28),
         pose=dict(scale=0.88, dx=8, dy=4)),
    dict(name="rave-archive", label="Rave Archive UK", glyph="flyer",
         field=ORANGE, pa=CYAN, pb=MAGENTA, code="RP-30", rot=-2.5,
         warp=dict(amp=7.0, freq=1.5, phase=0.25, sag=4.0),
         melt=dict(count=2, max_len=44, min_len=26),
         pose=dict(scale=0.94, dx=-4, dy=-4)),
    dict(name="helter-skelter", label="Helter Skelter", glyph="smiley",
         field=ACID, pa=MAGENTA, pb=CYAN, code="RP-31", rot=1.0,
         warp=dict(amp=6.0, freq=1.7, phase=0.25, sag=5.0),
         melt=dict(count=2, max_len=52, min_len=30),
         pose=dict(scale=1.0, dx=0, dy=0)),
    dict(name="fantazia", label="Fantazia", glyph="glowstick",
         field=PAPER, pa=MAGENTA, pb=CYAN, code="RP-32", rot=-1.5,
         warp=dict(amp=8.0, freq=1.5, phase=0.45, sag=4.0),
         melt=dict(count=2, max_len=44, min_len=26),
         pose=dict(scale=0.94, dx=0, dy=2)),
    dict(name="one-nation", label="One Nation", glyph="glowstick",
         field=ACID, pa=CYAN, pb=MAGENTA, code="RP-33", rot=2.5,
         warp=dict(amp=7.0, freq=1.4, phase=0.60, sag=3.0),
         melt=dict(count=2, max_len=42, min_len=24),
         pose=dict(scale=0.90, dx=-4, dy=-2)),
    dict(name="centreforce", label="Centreforce", glyph="lazer",
         field=CYAN, pa=MAGENTA, pb=ACID, code="RP-34", rot=-3.0,
         warp=dict(amp=6.0, freq=1.3, phase=0.10, sag=3.0),
         melt=dict(count=2, max_len=44, min_len=26),
         pose=dict(scale=0.92, dx=6, dy=-6)),
    dict(name="don-fm", label="Don FM", glyph="speaker",
         field=CYAN, pa=MAGENTA, pb=ACID, code="RP-35", rot=1.0,
         warp=dict(amp=9.0, freq=1.5, phase=0.40, sag=4.0),
         melt=dict(count=3, max_len=52, min_len=30),
         pose=dict(scale=0.90, dx=0, dy=6)),
    dict(name="slammin-vinyl", label="Slammin Vinyl", glyph="vinyl",
         field=MAGENTA, pa=ACID, pb=CYAN, code="RP-36", rot=-2.0,
         warp=dict(amp=7.0, freq=1.4, phase=0.65, sag=3.0),
         melt=dict(count=3, max_len=48, min_len=28),
         pose=dict(scale=0.94, dx=0, dy=0)),
    dict(name="one-in-the-jungle", label="One in the Jungle", glyph="flyer",
         field=ACID, pa=MAGENTA, pb=CYAN, code="RP-37", rot=2.0,
         warp=dict(amp=7.0, freq=1.6, phase=0.55, sag=5.0),
         melt=dict(count=3, max_len=54, min_len=30),
         pose=dict(scale=0.90, dx=-6, dy=-4)),
    dict(name="jungle-fever", label="Jungle Fever", glyph="speaker",
         field=ACID, pa=MAGENTA, pb=CYAN, code="RP-38", rot=-2.5,
         warp=dict(amp=9.0, freq=1.5, phase=0.40, sag=4.0),
         melt=dict(count=3, max_len=52, min_len=30),
         pose=dict(scale=0.96, dx=0, dy=-2)),
    dict(name="roast", label="Roast", glyph="smiley",
         field=MAGENTA, pa=ACID, pb=CYAN, code="RP-39", rot=-1.0,
         warp=dict(amp=6.0, freq=1.7, phase=0.25, sag=5.0),
         melt=dict(count=2, max_len=52, min_len=30),
         pose=dict(scale=0.94, dx=4, dy=0)),
    dict(name="telepathy", label="Telepathy", glyph="flyer",
         field=MAGENTA, pa=CYAN, pb=ACID, code="RP-40", rot=-4.0,
         warp=dict(amp=6.5, freq=1.7, phase=0.60, sag=4.0),
         melt=dict(count=3, max_len=48, min_len=28),
         pose=dict(scale=0.92, dx=6, dy=2)),
    dict(name="world-dance", label="World Dance", glyph="smiley",
         field=CYAN, pa=MAGENTA, pb=ACID, code="RP-41", rot=3.0,
         warp=dict(amp=6.0, freq=1.7, phase=0.25, sag=5.0),
         melt=dict(count=2, max_len=52, min_len=30),
         pose=dict(scale=0.96, dx=-4, dy=-2)),
    dict(name="garage-nation", label="Garage Nation", glyph="vinyl",
         field=CYAN, pa=MAGENTA, pb=ACID, code="RP-42", rot=5.0,
         warp=dict(amp=7.0, freq=1.4, phase=0.65, sag=3.0),
         melt=dict(count=3, max_len=48, min_len=28),
         pose=dict(scale=0.92, dx=0, dy=4)),
    dict(name="ravetapepacks", label="RaveTapePacks.com", glyph="cassette",
         field=PAPER, pa=MAGENTA, pb=CYAN, code="RP-43", rot=-3.0,
         warp=dict(amp=7.0, freq=1.6, phase=0.50, sag=4.0),
         melt=dict(count=2, max_len=46, min_len=26),
         pose=dict(scale=0.90, dx=0, dy=6)),
    dict(name="jungletapes", label="JungleTapes.com", glyph="tape",
         field=ACID, pa=MAGENTA, pb=CYAN, code="RP-44", rot=5.0,
         warp=dict(amp=6.0, freq=1.8, phase=0.15, sag=6.0),
         melt=dict(count=3, max_len=46, min_len=26),
         pose=dict(scale=0.92, dx=4, dy=0)),
    dict(name="downloads", label="Downloads", glyph="tape",
         field=CYAN, pa=MAGENTA, pb=ACID, code="RP-45", rot=7.0,
         warp=dict(amp=6.0, freq=1.8, phase=0.15, sag=6.0),
         melt=dict(count=3, max_len=46, min_len=26),
         pose=dict(scale=0.94, dx=-6, dy=-2)),
    dict(name="mixcloud", label="Mixcloud Sets", glyph="vinyl",
         field=ORANGE, pa=ACID, pb=CYAN, code="RP-46", rot=-7.0,
         warp=dict(amp=7.0, freq=1.4, phase=0.65, sag=3.0),
         melt=dict(count=3, max_len=48, min_len=28),
         pose=dict(scale=0.90, dx=-8, dy=2)),
    dict(name="soundcloud", label="SoundCloud Sets", glyph="vinyl",
         field=ACID, pa=MAGENTA, pb=CYAN, code="RP-47", rot=8.0,
         warp=dict(amp=7.0, freq=1.4, phase=0.65, sag=3.0),
         melt=dict(count=3, max_len=48, min_len=28),
         pose=dict(scale=0.94, dx=6, dy=-4)),
    dict(name="sets", label="Club & Rave Sets", glyph="speaker",
         field=PAPER, pa=ACID, pb=CYAN, code="RP-48", rot=2.0,
         warp=dict(amp=9.0, freq=1.5, phase=0.40, sag=4.0),
         melt=dict(count=3, max_len=52, min_len=30),
         pose=dict(scale=0.96, dx=0, dy=-4)),
    dict(name="pirate-radio", label="Pirate Radio", glyph="vinyl",
         field=PAPER, pa=ACID, pb=CYAN, code="RP-19", rot=-4.0,
         warp=dict(amp=7.0, freq=1.4, phase=0.65, sag=3.0),
         melt=dict(count=3, max_len=48, min_len=28),
         pose=dict(scale=0.92, dx=0, dy=0)),
    dict(name="radio-jungle", label="Jungle (live)", glyph="speaker",
         field=ACID, pa=MAGENTA, pb=CYAN, code="STN-04", rot=3.0,
         warp=dict(amp=9.0, freq=1.5, phase=0.45, sag=4.0),
         melt=dict(count=3, max_len=56, min_len=34),
         pose=dict(scale=0.96, dx=0, dy=0), station="jungle"),
    dict(name="radio-dnb", label="Drum & Bass (live)", glyph="speaker",
         field=CYAN, pa=MAGENTA, pb=ACID, code="STN-05", rot=-2.0,
         warp=dict(amp=7.5, freq=1.6, phase=0.20, sag=3.0),
         melt=dict(count=2, max_len=34, min_len=22),
         pose=dict(scale=0.94, dx=0, dy=0), station="drum-and-bass"),
    dict(name="radio-hardcore", label="Hardcore (live)", glyph="smiley",
         field=ORANGE, pa=ACID, pb=MAGENTA, code="STN-06", rot=2.0,
         warp=dict(amp=8.0, freq=1.4, phase=0.55, sag=5.0),
         melt=dict(count=3, max_len=58, min_len=34),
         pose=dict(scale=0.96, dx=0, dy=0), station="hardcore"),
    dict(name="radio-house", label="House (live)", glyph="smiley",
         field=PAPER, pa=CYAN, pb=MAGENTA, code="STN-07", rot=0.0,
         warp=dict(amp=7.0, freq=1.7, phase=0.30, sag=3.0),
         melt=dict(count=2, max_len=44, min_len=28),
         pose=dict(scale=0.94, dx=0, dy=0), station="house"),
    dict(name="radio-uk-garage", label="UK Garage (live)", glyph="speaker",
         field=MAGENTA, pa=CYAN, pb=ACID, code="STN-08", rot=-3.0,
         warp=dict(amp=8.0, freq=1.55, phase=0.35, sag=4.0),
         melt=dict(count=2, max_len=48, min_len=30),
         pose=dict(scale=0.94, dx=0, dy=0), station="uk-garage"),
    dict(name="radio-breakbeat", label="Breakbeat (live)", glyph="vinyl",
         field=ACID, pa=CYAN, pb=MAGENTA, code="STN-09", rot=2.0,
         warp=dict(amp=8.0, freq=1.5, phase=0.25, sag=3.5),
         melt=dict(count=2, max_len=44, min_len=28),
         pose=dict(scale=0.94, dx=0, dy=0), station="breakbeat"),
    dict(name="kool", label="Kool FM", glyph="smiley",
         field=ACID, pa=MAGENTA, pb=CYAN, code="KOOL-01", rot=-1.0,
         warp=dict(amp=6.0, freq=1.3, phase=0.10, sag=3.0),
         melt=dict(count=2, max_len=44, min_len=26),
         pose=dict(scale=1.0, dx=0, dy=0), station="kool-fm"),
    dict(name="rinse", label="Rinse FM", glyph="balloon",
         field=CYAN, pa=MAGENTA, pb=ACID, code="STN-02", rot=0.0,
         warp=dict(amp=7.0, freq=1.5, phase=0.40, sag=2.5),
         melt=dict(count=2, max_len=44, min_len=28),
         pose=dict(scale=0.94, dx=0, dy=0), station="rinse-fm"),
    dict(name="oldskool", label="Oldskool & Rave", glyph="vinyl",
         field=MAGENTA, pa=ACID, pb=CYAN, code="STN-03", rot=-4.0,
         warp=dict(amp=8.5, freq=1.45, phase=0.25, sag=4.5),
         melt=dict(count=2, max_len=60, min_len=36),
         pose=dict(scale=0.94, dx=0, dy=0), station="oldskool-rave"),
]

# Ten station tiles: nine are the Live Radio rows, the tenth is the pirate
# archive row.  Drawn by the approved station study, not re-cut here.
STATIONS = [
    ("kool", "kool-fm"),
    ("rinse", "rinse-fm"),
    ("oldskool", "oldskool-rave"),
    ("radio-jungle", "jungle"),
    ("radio-dnb", "drum-and-bass"),
    ("radio-hardcore", "hardcore"),
    ("radio-house", "house"),
    ("radio-uk-garage", "uk-garage"),
    ("radio-breakbeat", "breakbeat"),
    ("pirate-stations", "pirate-stations"),
]

STATION_RECIPES = dict((recipe["key"], recipe) for recipe in STN.RECIPES)

# What each row actually reads as at 64 px, judged on the dark strip
# (docs/theme-2026/final-rollout-64px.png) without the label.
BLIND = {
    "lazer": ("beams, needs the label", "good"),
    "glowstick": ("two crossed tubes", "good"),
    "cassette": ("cassette", "sure"),
    "tape": ("cassette", "sure"),
    "flyer": ("flyer / poster", "sure"),
    "speaker": ("speaker cabinet", "sure"),
    "vinyl": ("record deck", "sure"),
    "smiley": ("smiley", "sure"),
    "balloon": ("balloon", "sure"),
}


# ------------------------------------------------------------------- rendering
def _glyph_layer(row):
    """Draw one glyph, with the row's pose applied after melt and spatter."""
    pose = row.get("pose") or {}
    scale = float(pose.get("scale", 1.0))
    rot = row.get("rot", 0.0)

    def draw(one_scale, dx, dy):
        layer = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
        GLYPHS[row["glyph"]](Pen(layer), row["field"])
        C2.add_melt(layer, INK, seed=sum(ord(c) for c in row["name"]) + 3,
                    **row["melt"])
        C2.spatter(layer, INK, count=22,
                   seed=sum(ord(c) for c in row["name"]) + 11)
        k = 1.0 / one_scale
        off = PX / 2.0 * (1.0 - k)
        layer = layer.transform(
            (PX, PX), Image.AFFINE,
            (k, 0, off - dx * SS * k, 0, k, off - dy * SS * k),
            resample=Image.BICUBIC)
        return layer

    if pose.get("pair"):
        out = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
        inner = float(pose.get("pair_scale", 0.62))
        pdx = float(pose.get("pair_dx", -58))
        pdy = float(pose.get("pair_dy", -50))
        out.alpha_composite(draw(scale * inner, pdx, pdy))
        out.alpha_composite(draw(scale * inner, -pdx, -pdy))
        layer = out
    else:
        layer = draw(scale, float(pose.get("dx", 0)), float(pose.get("dy", 0)))

    if rot:
        layer = layer.rotate(rot, resample=Image.BICUBIC,
                             center=(PX / 2, PX / 2))
    return layer


def build_row_tile(row, out):
    field, plate_a, plate_b = row["field"], row["pa"], row["pb"]
    rnd = random.Random(sum(ord(c) for c in row["name"]) * 7 + 3)

    base = ART_MOD.vertical_gradient(
        PX, C2.mix(field, PAPER, 0.13), C2.mix(field, INK, 0.17)).convert("RGBA")
    sun_c = (rnd.uniform(0.14, 0.86), rnd.uniform(0.10, 0.40))
    base.alpha_composite(C2.halftone(plate_a, spacing=13, radius=2.6, alpha=82,
                                     seed=rnd.randint(1, 99),
                                     sun=(sun_c[0] * C2.S, sun_c[1] * C2.S,
                                          C2.S * 0.58)))
    scrib = Pen(base)
    C2.draw_squiggle(scrib, [(62, 92), (98, 70), (120, 100), (92, 122)], 5.5,
                     1.5, plate_b, 7, phase=rnd.uniform(0, 6))

    layer = _glyph_layer(row)
    comp = base
    for colour, dx, dy, phase in (
            (plate_a, -7, -5, row["warp"]["phase"] + 0.20),
            (plate_b, 6, 6, row["warp"]["phase"] + 0.58)):
        params = dict(row["warp"])
        params["phase"] = phase
        params["amp2"] = 4.5
        comp.alpha_composite(C2.shift(C2.warp_alpha(layer, colour, **params),
                                      dx, dy))
    comp.alpha_composite(C2.warp(layer, **row["warp"]))
    comp.alpha_composite(C2.halftone(INK, spacing=16, radius=1.6, alpha=22,
                                     seed=rnd.randint(1, 99), jitter=0.9))
    comp.alpha_composite(C2.scanlines(alpha=11))

    d = ImageDraw.Draw(comp)
    for (x, y, sx, sy) in ((26, 26, 1, 1), (486, 26, -1, 1),
                           (26, 486, 1, -1), (486, 486, -1, -1)):
        d.line([(x * SS, y * SS), ((x + 26 * sx) * SS, y * SS)],
               fill=rgba(INK, 225), width=3 * SS)
        d.line([(x * SS, y * SS), (x * SS, (y + 26 * sy) * SS)],
               fill=rgba(INK, 225), width=3 * SS)
    fnt = ART_MOD.font(ART_MOD.MONO, max(18, int(27 * out / 256.0)) * SS)
    d.text((36 * SS, 470 * SS), row["code"], font=fnt, fill=rgba(INK, 240),
           anchor="ls")
    d.line([(34 * SS, 476 * SS), (104 * SS, 476 * SS)], fill=rgba(INK, 190),
           width=3 * SS)
    for i, h in enumerate((10, 18, 26, 34)):
        x = (436 + i * 13) * SS
        d.rectangle([x, (478 - h) * SS, x + 8 * SS, 478 * SS],
                    fill=rgba(INK, 235))

    comp = C2.grain(comp, amount=5, seed=rnd.randint(1, 40))
    return comp.convert("RGB").resize((out, out), Image.LANCZOS)


def build_station_tile(study_key, out):
    recipe = STATION_RECIPES[study_key]
    old = STN.OUT
    try:
        STN.OUT = out
        return STN.build_tile(recipe)
    finally:
        STN.OUT = old


def render_one(row, out):
    if row.get("station"):
        return build_station_tile(row["station"], out)
    return build_row_tile(row, out)


# ---------------------------------------------------------------------- sheets
def _paste64(sheet, tile, x, y):
    sheet.paste(tile.resize((64, 64), Image.LANCZOS), (x, y))


def contact_sheet(tiles, stations):
    cell_w, cell_h = 148, 132
    cols = 8
    row_count = math.ceil(len(tiles) / cols)
    width = max(32 + cols * cell_w + 32, 32 + 3 * 420 + 32)
    top = 292
    station_block = 1420
    height = top + row_count * cell_h + 70 + station_block + 70
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)

    d.text((32, 54), "RAVE PLAYER — FINAL ROLLOUT", font=ART_MOD.font(
        ART_MOD.DISPLAY, 48), fill=PAPER, anchor="ls")
    d.text((32, 84),
           "DIRECTION C2 · 38 NAVIGATION ROWS + 10 STATION TILES · 64 PX READ",
           font=ART_MOD.font(ART_MOD.MONO, 13), fill=ACID, anchor="ls")
    d.text((width - 32, 54), "KODI 256² · WEB 512²",
           font=ART_MOD.font(ART_MOD.MONO, 13), fill=MUTED, anchor="rs")
    d.text((width - 32, 76), "3.9.38 / 1.6.43 · NOT DEPLOYED",
           font=ART_MOD.font(ART_MOD.MONO, 11), fill=MUTED, anchor="rs")

    # accepted family strip
    d.text((32, 126), "ACCEPTED ORIGINALS · 64 PX", font=ART_MOD.font(
        ART_MOD.MONO, 10), fill=MUTED, anchor="ls")
    y = 146
    for i, name in enumerate(("rave", "tapepacks", "jungle", "hardcore",
                              "pirate", "toronto", "moxser")):
        path = os.path.join(ART, name + ".png")
        if os.path.exists(path):
            ref = Image.open(path).convert("RGB").resize((64, 64), Image.LANCZOS)
            sheet.paste(ref, (32 + i * 76, y))
            d.text((32 + i * 76 + 32, y + 72), name, font=ART_MOD.font(
                ART_MOD.MONO, 8), fill=MUTED, anchor="ms")

    y = top
    d.text((32, y - 18), "38 ROWS · EVERY TILE AT ITS REAL 64 PX LIST SIZE",
           font=ART_MOD.font(ART_MOD.MONO, 10), fill=MUTED, anchor="ls")
    for index, row in enumerate(tiles):
        cx = 32 + (index % cols) * cell_w
        cy = y + (index // cols) * cell_h
        _paste64(sheet, row["tile"], cx, cy)
        d.text((cx, cy + 68), row["label"], font=ART_MOD.font(
            ART_MOD.MONO, 9), fill=PAPER, anchor="la")
        d.text((cx, cy + 80), row["name"] + ".png", font=ART_MOD.font(
            ART_MOD.MONO, 7), fill=MUTED, anchor="la")
        verdict = row.get("verdict", "")
        colour = ACID if verdict == "sure" else (CYAN if verdict == "good"
                                                 else MUTED)
        d.text((cx, cy + 92), verdict.upper(), font=ART_MOD.font(
            ART_MOD.MONO, 8), fill=colour, anchor="la")

    y = top + row_count * cell_h + 54
    d.text((32, y - 20), "10 STATION TILES · 256 WITH 128 / 64 INSETS",
           font=ART_MOD.font(ART_MOD.MONO, 10), fill=MUTED, anchor="ls")
    for index, station in enumerate(stations):
        cx = 32 + (index % 3) * 400
        cy = y + (index // 3) * 340
        sheet.paste(station["tile"].resize((256, 256), Image.LANCZOS), (cx, cy))
        sheet.paste(station["tile"].resize((128, 128), Image.LANCZOS),
                    (cx + 268, cy))
        sheet.paste(station["tile"].resize((64, 64), Image.LANCZOS),
                    (cx + 268, cy + 140))
        d.text((cx, cy + 262), station["label"], font=ART_MOD.font(
            ART_MOD.MONO, 10), fill=PAPER, anchor="la")
        d.text((cx, cy + 276), station["name"] + ".png", font=ART_MOD.font(
            ART_MOD.MONO, 8), fill=MUTED, anchor="la")

    d.text((32, height - 26),
           "RP · THEME 2026 · C2 PRODUCTION ROLLOUT · SHEET ONLY UNTIL OWNER APPROVAL",
           font=ART_MOD.font(ART_MOD.MONO, 9), fill=MUTED, anchor="ls")
    return sheet


def preview_sheet(tiles, stations):
    """One flat 64 px strip: the blind-read surface, no labels."""
    cols = 12
    cell = 84
    rows = math.ceil(len(tiles) / cols)
    width = 24 + cols * cell
    height = 24 + rows * cell + 40 + 64 + 24
    sheet = Image.new("RGB", (width, height), INK)
    for index, row in enumerate(tiles):
        x = 24 + (index % cols) * cell
        y = 24 + (index // cols) * cell
        sheet.paste(row["tile"].resize((64, 64), Image.LANCZOS), (x, y))
    y = 24 + rows * cell + 30
    for index, station in enumerate(stations[:10]):
        x = 24 + index * cell
        sheet.paste(station["tile"].resize((64, 64), Image.LANCZOS), (x, y))
    return sheet


# --------------------------------------------------------------------- writing
def _targets(name):
    return (os.path.join(ART, name + ".png"),
            os.path.join(WEB_ART, name + ".png"))


def write_all(no_web=False, no_sheet=False):
    os.makedirs(ART, exist_ok=True)
    os.makedirs(THEME, exist_ok=True)
    if not no_web:
        os.makedirs(WEB_ART, exist_ok=True)

    tiles = []
    for row in ROWS:
        row = dict(row)
        row["blind"] = BLIND[row["glyph"]][0]
        row["verdict"] = BLIND[row["glyph"]][1]
        kodi = render_one(row, KODI_SIZE)
        web = render_one(row, WEB_SIZE) if not no_web else None
        kodi_path, web_path = _targets(row["name"])
        kodi.save(kodi_path, "PNG", optimize=True)
        if web is not None:
            web.save(web_path, "PNG", optimize=True)
        tiles.append(dict(row, tile=kodi))

    stations = []
    for name, study_key in STATIONS:
        recipe = STATION_RECIPES[study_key]
        kodi = build_station_tile(study_key, KODI_SIZE)
        web = build_station_tile(study_key, WEB_SIZE) if not no_web else None
        kodi_path, web_path = _targets(name)
        kodi.save(kodi_path, "PNG", optimize=True)
        if web is not None:
            web.save(web_path, "PNG", optimize=True)
        stations.append(dict(name=name, label=recipe["name"], tile=kodi))

    if not no_sheet:
        contact_sheet(tiles, stations).save(SHEET, "PNG", optimize=True)
        preview_sheet(tiles, stations).save(SHEET_PREVIEW, "PNG", optimize=True)
        icons = [os.path.join(ART, name) for name in sorted(os.listdir(ART))
                 if name.endswith(".png")]
        ART_MOD.make_contact_sheet(os.path.join(ART, "preview.jpg"), icons)
    print("wrote %d row tiles + %d station tiles" % (len(tiles), len(stations)))
    if not no_sheet:
        print("sheet:", SHEET)


def check():
    problems = []
    names = [row["name"] for row in ROWS] + [name for name, _ in STATIONS]
    unique = []
    for name in names:
        if name not in unique:
            unique.append(name)
    for name in unique:
        if not NAME_RE.match(name):
            problems.append("not kebab-case: %r" % name)
    for name in names:
        kodi_path, web_path = _targets(name)
        for path, size in ((kodi_path, KODI_SIZE), (web_path, WEB_SIZE)):
            if not os.path.exists(path):
                problems.append("missing: %s" % path)
                continue
            with Image.open(path) as img:
                if img.size != (size, size):
                    problems.append("%s is %r, want %r" % (path, img.size,
                                                           (size, size)))
    if problems:
        for line in problems:
            print("FAIL", line)
        return 1
    print("OK: %d kebab-case tiles at 256 (Kodi) and 512 (web)" % len(unique))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-web", action="store_true",
                    help="render Kodi only")
    ap.add_argument("--no-sheet", action="store_true",
                    help="skip the contact sheets")
    ap.add_argument("--check", action="store_true",
                    help="verify names, sizes and existence only")
    args = ap.parse_args()
    if args.check:
        return check()
    write_all(no_web=args.no_web, no_sheet=args.no_sheet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
