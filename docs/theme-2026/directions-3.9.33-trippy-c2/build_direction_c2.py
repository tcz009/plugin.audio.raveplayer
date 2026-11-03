#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Direction C2 — TRIPPY RAVE, re-cut for legibility.

C's treatment was accepted; C's *objects* were not. Owner, on C:

    "It's better, but we're talking about raves — one looks like a TV, one
     looks like a banana."

He is right, and the failure is specific: C drew shapes whose silhouette was
ambiguous at 64 px (a cabinet wearing fronds read as a TV with rabbit ears; a
crescent read as a banana), and several marks were not rave iconography at all
(arrow, gem, big-top, dynamic mic, transmitter mast, jolly roger).

C2 changes exactly one thing — the glyph vocabulary — and keeps every part of
the print treatment the owner liked:

    one spot field, one ink mass, hard chromatic misregistration, drips,
    halftone, scanlines, crop marks, RP-xx, signal bars, the rave.png grin.

Every object now comes from the rave list:

    cassette / tape reel · acid smiley · speaker stack · vinyl / turntable ·
    glowstick · whistle · smiley balloon · rave flyer · mixtape spine ·
    lazer / scan lines

...and nothing else. No arrows, gems, big-tops, letters, mics, TVs, bananas.

The print pipeline (wobble / melt / warp / plates / halftone / furniture) is
imported read-only from the Direction C builder so the two can never drift;
only the glyphs are new. Build-time only: Pillow + numpy.

    python3 build_direction_c2.py            # full sheets
    python3 build_direction_c2.py --preview  # fast silhouette check only

Writes only into this folder. Nothing is wired, committed or deployed.
"""
from __future__ import annotations

import importlib.util
import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
THEME = os.path.dirname(HERE)
C_DIR = os.path.join(THEME, "directions-3.9.33-trippy")
ROOT = os.path.dirname(os.path.dirname(THEME))
ART = os.path.join(ROOT, "resources", "art")

SHEET = os.path.join(HERE, "c2-contact-sheet.png")
BOARD = os.path.join(HERE, "c2-1to1.png")
ROWS = os.path.join(HERE, "c2-64px-rows.png")
BEFORE = os.path.join(HERE, "c2-before-after-64px.png")
VOCAB = os.path.join(HERE, "c2-vocabulary-64px.png")
PREVIEW = os.path.join(HERE, "_preview-glyphs.png")

S = 512
GLYPH_SCALE = 1.06
SS = 2
PX = S * SS
OUT = 256


# ------------------------------------------------------- Direction C pipeline
def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C = _load(os.path.join(C_DIR, "build_direction_c.py"), "rave_direction_c")

art = C.art
INK, INK_2, PAPER, MUTED = C.INK, C.INK_2, C.PAPER, C.MUTED
ACID, MAGENTA, CYAN, ORANGE = C.ACID, C.MAGENTA, C.CYAN, C.ORANGE
mix, rgba = C.mix, C.rgba
Pen = C.Pen
add_melt, spatter = C.add_melt, C.spatter
warp, warp_alpha, shift = C.warp, C.warp_alpha, C.shift
halftone, scanlines, grain = C.halftone, C.scanlines, C.grain
grin, eye = C.grin, C.eye
draw_squiggle, squiggle = C.draw_squiggle, C.squiggle
circle_pts, arc_pts, rrect_pts, resample = (C.circle_pts, C.arc_pts,
                                           C.rrect_pts, C.resample)
wobble = C.wobble


# ============================================================ RAVE VOCABULARY
# Ten allowed objects, eleven drawings (cassette and open reel are both in the
# "cassette / tape reel" slot). Everything below is a single silhouette that
# must survive a 64 px blind read. Nothing else is allowed on a tile.

def g_cassette(p, accent):
    """Cassette: shell, tape window, two spools, the grin on the label band."""
    p.rect((70, 148, 442, 366), INK, radius=30, wob=2.6, phase=0.15)
    # tape window (bright) with the two spools knocked out of it
    p.rect((112, 182, 400, 290), accent, radius=16, wob=1.8, phase=0.55)
    for cx in (176, 336):
        p.disc(cx, 236, 37, INK)
        p.disc(cx, 236, 12, accent)
        for k in range(3):                       # spool teeth
            a = math.radians(24 + k * 120)
            p.disc(cx + 25 * math.cos(a), 236 + 25 * math.sin(a), 6, accent)
    # the grin sits on the shell where the label band would be
    grin(p, 256, 312, 94, 24, 16, accent, step=22)
    for cx in (140, 372):                        # alignment holes
        p.disc(cx, 350, 7, accent)
    for (cx, cy) in ((96, 174), (416, 174)):     # shell screws
        p.disc(cx, cy, 7, accent)


def g_flyer(p, accent):
    """Rave flyer: ink sheet, torn hem, knocked-out grin sticker, line-up rules."""
    sheet = [(140, 82), (372, 82), (372, 402),
             (334, 388), (300, 410), (264, 390), (228, 408), (192, 390),
             (156, 406), (140, 390)]
    p.fill(sheet, INK, wob=2.0, freq=2, phase=0.3)
    # the face is the sticker on the flyer
    p.disc(256, 168, 58, accent)
    p.disc(234, 156, 9, INK)
    p.disc(280, 155, 8, INK)
    grin(p, 258, 178, 36, 20, 9, INK, step=16)
    # line-up rules
    for (y, w) in ((256, 170), (284, 128), (312, 152)):
        p.rect((174, y, 174 + w, y + 14), accent, radius=5, wob=1.0, phase=0.3)
    # door price / times tag
    p.rect((196, 348, 316, 378), accent, radius=6, wob=1.1, phase=0.6)


def g_speaker(p, accent):
    """Speaker stack: two cabinets, one driver each, stacked into a tower."""
    for (y0, y1, cy, r) in ((66, 208, 137, 54), (230, 418, 322, 68)):
        p.rect((170, y0, 342, y1), INK, radius=14, wob=2.2, phase=0.2 + cy * 0.001)
        p.disc(256, cy, r, accent)
        p.disc(256, cy, r * 0.68, INK)
        p.disc(256, cy, r * 0.32, accent)
        for sx in (188, 324):
            p.disc(sx, y0 + 18, 6, accent)       # cabinet screws
    for (x0, x1) in ((176, 222), (290, 336)):    # feet
        p.rect((x0, 410, x1, 438), INK, radius=6, wob=1.0, phase=0.5)


def g_vinyl(p, accent):
    """Turntable: deck, record with grooves, label, spindle, tonearm."""
    p.rect((82, 92, 430, 404), INK, radius=22, wob=2.4, phase=0.2)
    p.disc(244, 258, 128, accent)                # record
    for r in (116, 94):                          # grooves
        p.line(circle_pts(244, 258, r, 96), 5, INK, wob=0.6, closed=True)
    p.disc(244, 258, 46, INK)                    # label
    p.disc(244, 258, 9, accent)                  # spindle
    p.line([(226, 268), (262, 262)], 7, accent, wob=0.6)   # marker scrawl
    p.disc(400, 118, 19, INK)                    # tonearm pivot
    p.line([(400, 118), (340, 226)], 13, INK, wob=0.8,
           taper=lambda t: 1.0 - 0.18 * t)
    p.rect((314, 218, 358, 258), INK, radius=7, wob=1.0, phase=0.3)
    p.rect((106, 366, 148, 388), accent, radius=6, wob=0.8, phase=0.2)


def g_smiley(p, accent):
    """Acid smiley: heavy disc, two dot eyes, the rave.png grin underneath."""
    p.blob(256, 250, 154, INK, wob=4.6, lobes=3, phase=0.4)
    p.disc(196, 208, 24, accent)
    p.disc(316, 204, 22, accent)
    grin(p, 256, 258, 100, 62, 26, accent, step=26)
    p.star(428, 116, 20, INK, wob=0.8)           # flyer sparkle, kept clear
    p.star(98, 378, 13, INK, wob=0.6)


def g_glowsticks(p, accent):
    field_colour = accent
    """Two fat glowsticks crossed: dark sleeve, hot core, rounded ends."""
    def stick(a, b, width):
        dense = wobble([a, b], 1.4, 1.6, 0.2)
        p.line(dense, width, INK, wob=0)
        i0, i1 = int(len(dense) * 0.17), int(len(dense) * 0.94)
        p.line(dense[i0:i1], width * 0.66, accent, wob=0)
        # a couple of tape-style glints in the sleeve
        for t in (0.30, 0.44):
            k = int(len(dense) * t)
            x, y = dense[k]
            p.disc(x, y, width * 0.13, accent)
    stick((334, 402), (198, 190), 60)          # back stick
    # front stick gets a knocked-out gap so the pair reads as two objects
    knob = wobble([(150, 414), (358, 118)], 1.4, 1.6, 0.2)
    p.line(knob, 84, field_colour, wob=0)
    stick((150, 414), (358, 118), 62)
def g_lazer(p, accent):
    """Lazer / scan lines: two fat beams off the tile, scan stack clear of them."""
    for (y, x0, x1) in ((120, 96, 300), (170, 96, 250), (220, 96, 300),
                        (270, 96, 250)):
        p.rect((x0, y, x1, y + 13), accent, radius=6, wob=0.9, phase=0.3)
    src = (250, 414)
    for (ang, half, length) in ((-74, 32, 720), (-54, 26, 740)):
        a = math.radians(ang)
        dx, dy = math.cos(a), math.sin(a)
        nx, ny = -dy, dx
        tip = (src[0] + dx * length, src[1] + dy * length)
        p.fill([(src[0] + nx * 10, src[1] + ny * 10),
                (tip[0] + nx * half, tip[1] + ny * half),
                (tip[0] - nx * half, tip[1] - ny * half),
                (src[0] - nx * 10, src[1] - ny * 10)],
               INK, wob=1.0, freq=1.5, phase=0.2)
        p.line([(src[0] + dx * 24, src[1] + dy * 24),
                (tip[0] - dx * 40, tip[1] - dy * 40)], 6, accent, wob=0.4,
               taper=lambda t: 0.5 + 0.8 * t)
    p.rect((166, 398, 316, 434), INK, radius=12, wob=1.2, phase=0.4)
    p.disc(250, 416, 13, accent)

def g_balloon(p, accent):
    """Smiley balloon: fat balloon, knot, curled string, the rave.png grin."""
    p.blob(256, 198, 122, INK, wob=4.2, lobes=3, phase=0.3)
    p.fill([(234, 306), (278, 306), (256, 334)], INK, wob=1.2, phase=0.2)
    p.line([(258, 330), (248, 362), (276, 388), (258, 414), (286, 430),
            (300, 418)], 9, INK, wob=1.0, taper=lambda t: 1.0 - 0.3 * t)
    p.disc(214, 184, 16, accent)                 # eye
    eye(p, 294, 184, 15, accent, wink=True)      # wink
    grin(p, 254, 214, 54, 32, 15, accent, step=18)
    p.star(400, 132, 17, INK, wob=0.7)           # sparkle, clear of the body
    p.star(112, 300, 12, INK, wob=0.5)


def _bez(p0, p1, p2, p3, n=44):
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0]
                    + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1]
                    + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def g_tape(p, accent):
    """Archive cassette: the tape you kept - window, spools, hand-written label."""
    p.rect((98, 104, 398, 356), INK, radius=28, wob=2.4, phase=0.2)
    p.rect((134, 140, 362, 232), accent, radius=12, wob=1.6, phase=0.5)
    for cx in (180, 316):
        p.disc(cx, 186, 35, INK)
        p.disc(cx, 186, 11, accent)
        for k in range(3):
            a = math.radians(24 + k * 120)
            p.disc(cx + 24 * math.cos(a), 186 + 24 * math.sin(a), 5.5, accent)
    p.rect((134, 254, 362, 322), accent, radius=8, wob=1.2, phase=0.3)
    p.line([(160, 276), (306, 270), (296, 296), (172, 300)], 9, INK, wob=1.0)
    p.line([(160, 308), (252, 304)], 7, INK, wob=1.0)
    for cx in (120, 376):
        p.disc(cx, 128, 7, accent)

GLYPHS = {
    "cassette": g_cassette,
    "flyer": g_flyer,
    "speaker": g_speaker,
    "vinyl": g_vinyl,
    "smiley": g_smiley,
    "glowstick": g_glowsticks,
    "tape": g_tape,
    "lazer": g_lazer,
    "balloon": g_balloon,
}

OBJECT_NAME = {
    "cassette": "CASSETTE",
    "flyer": "RAVE FLYER",
    "speaker": "SPEAKER STACK",
    "vinyl": "VINYL / TURNTABLE",
    "smiley": "ACID SMILEY",
    "glowstick": "GLOWSTICKS",
    "tape": "CASSETTE, LABELLED",
    "lazer": "LAZER / SCAN LINES",
    "balloon": "SMILEY BALLOON",
}


# ============================================================ row recipes
# key, glyph, field, plate-1, plate-2, RP code, rotation, warp params, melt.
# `was` is C's object, `now` is the C2 object: the before/after audit.
RECIPES = [
    dict(key="tapepacks", glyph="cassette", field=ACID, pa=MAGENTA, pb=CYAN,
         code="RP-03", rot=-2.0,
         warp=dict(amp=8.0, freq=1.4, phase=0.20, sag=4.0),
         melt=dict(count=3, max_len=58, min_len=32),
         was="cassette with a grin", now="cassette, re-cut: window, spools, teeth"),
    dict(key="podcasts", glyph="flyer", field=MAGENTA, pa=CYAN, pb=ACID,
         code="RP-27", rot=1.5,
         warp=dict(amp=7.0, freq=1.6, phase=0.55, sag=5.0),
         melt=dict(count=3, max_len=54, min_len=30),
         was="dynamic mic", now="rave flyer (line-up sheet)"),
    dict(key="kool", glyph="lazer", field=CYAN, pa=MAGENTA, pb=ACID,
         code="RP-31", rot=-1.0,
         warp=dict(amp=6.0, freq=1.3, phase=0.10, sag=3.0),
         melt=dict(count=2, max_len=44, min_len=26),
         was="transmitter mast with an aerial head", now="lazer / scan lines"),
    dict(key="radio-jungle", glyph="speaker", field=ACID, pa=MAGENTA, pb=CYAN,
         code="RP-34", rot=2.0,
         warp=dict(amp=9.0, freq=1.5, phase=0.40, sag=4.0),
         melt=dict(count=3, max_len=52, min_len=30),
         was="cabinet with palm fronds (read as a TV)", now="speaker stack"),
    dict(key="dreamscape", glyph="balloon", field=PAPER, pa=MAGENTA, pb=CYAN,
         code="RP-40", rot=-5.0,
         warp=dict(amp=8.0, freq=1.6, phase=0.30, sag=3.0),
         melt=dict(count=2, max_len=44, min_len=26),
         was="crescent moon (read as a banana)", now="smiley balloon"),
    dict(key="downloads", glyph="tape", field=CYAN, pa=MAGENTA, pb=ACID,
         code="RP-55", rot=7.0,
         warp=dict(amp=6.0, freq=1.8, phase=0.15, sag=6.0),
         melt=dict(count=3, max_len=46, min_len=26),
         was="down arrow", now="archive cassette, hand-labelled"),
    dict(key="pirate", glyph="vinyl", field=MAGENTA, pa=ACID, pb=CYAN,
         code="RP-19", rot=-2.0,
         warp=dict(amp=7.0, freq=1.4, phase=0.65, sag=3.0),
         melt=dict(count=3, max_len=48, min_len=28),
         was="jolly-roger flag", now="vinyl / turntable (dubplate)"),
    dict(key="curated", glyph="smiley", field=ACID, pa=CYAN, pb=MAGENTA,
         code="RP-06", rot=1.0,
         warp=dict(amp=6.0, freq=1.7, phase=0.25, sag=5.0),
         melt=dict(count=2, max_len=52, min_len=30),
         was="gem", now="acid smiley (the rave.png face)"),
    dict(key="rave-nights", glyph="glowstick", field=CYAN, pa=MAGENTA, pb=ACID,
         code="RP-25", rot=-1.5,
         warp=dict(amp=8.0, freq=1.5, phase=0.45, sag=4.0),
         melt=dict(count=2, max_len=44, min_len=26),
         was="big-top tent", now="glowsticks"),
]

ROW_LABELS = {
    "tapepacks": ("Rave Tape Packs", "TAPE PACKS \u00b7 GENRE"),
    "podcasts": ("Podcasts", "MIXES & SHOWS"),
    "kool": ("Kool FM", "LIVE RADIO \u00b7 STATION"),
    "radio-jungle": ("Jungle", "LIVE RADIO \u00b7 GENRE"),
    "dreamscape": ("Dreamscape", "QUICK FILTER \u00b7 SERIES"),
    "downloads": ("Downloads", "MY LIBRARY \u00b7 WEB"),
    "pirate": ("Pirate Radio", "TAPE PACKS \u00b7 STATIONS"),
    "curated": ("Curated Gems", "CURATED GEMS"),
    "rave-nights": ("By Rave & Venue", "TAPE PACKS \u00b7 CATEGORY"),
}

# blind read: what I actually see at 64 px, honestly
BLIND = {
    "tapepacks": ("CASSETTE", "sure"),
    "podcasts": ("FLYER / GIG POSTER", "sure"),
    "kool": ("LAZER BEAMS", "good"),
    "radio-jungle": ("SPEAKER STACK", "sure"),
    "dreamscape": ("BALLOON", "sure"),
    "downloads": ("CASSETTE, LABELLED", "sure"),
    "pirate": ("RECORD DECK", "sure"),
    "curated": ("SMILEY", "sure"),
    "rave-nights": ("GLOWSTICKS", "good"),
}


# ============================================================ glyph rendering
def glyph_layer(name, field, rot=0.0, melt=None, spat=22, seed=11):
    layer = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    GLYPHS[name](Pen(layer), field)
    if melt:
        add_melt(layer, INK, seed=seed, **melt)
    if spat:
        spatter(layer, INK, count=spat, seed=seed + 7)
    if rot:
        layer = layer.rotate(rot, resample=Image.BICUBIC, center=(PX / 2, PX / 2))
    return layer


def build_tile(row, seed_extra=0):
    field, plate_a, plate_b = row["field"], row["pa"], row["pb"]
    rnd = random.Random(sum(ord(c) for c in row["key"]) * 7 + 3 + seed_extra)

    base = art.vertical_gradient(
        PX, mix(field, PAPER, 0.13), mix(field, INK, 0.17)).convert("RGBA")

    sun_c = (rnd.uniform(0.14, 0.86), rnd.uniform(0.10, 0.40))
    base.alpha_composite(halftone(plate_a, spacing=13, radius=2.6, alpha=82,
                                  seed=rnd.randint(1, 99),
                                  sun=(sun_c[0] * S, sun_c[1] * S, S * 0.58)))

    scrib = Pen(base)
    draw_squiggle(scrib, [(62, 92), (98, 70), (120, 100), (92, 122)], 5.5, 1.5,
                  plate_b, 7, phase=rnd.uniform(0, 6))

    layer = glyph_layer(row["glyph"], field, rot=row["rot"], melt=row["melt"],
                        spat=int(rnd.uniform(18, 26)), seed=rnd.randint(1, 500))
    if GLYPH_SCALE != 1.0:
        k = 1.0 / GLYPH_SCALE
        off = PX / 2 * (1 - k)
        layer = layer.transform((PX, PX), Image.AFFINE,
                                (k, 0, off, 0, k, off), resample=Image.BICUBIC)

    comp = base
    for colour, dx, dy, phase in (
            (plate_a, -7, -5, row["warp"]["phase"] + 0.20),
            (plate_b, 6, 6, row["warp"]["phase"] + 0.58)):
        params = dict(row["warp"])
        params["phase"] = phase
        params["amp2"] = 4.5
        comp.alpha_composite(shift(warp_alpha(layer, colour, **params), dx, dy))

    comp.alpha_composite(warp(layer, **row["warp"]))

    comp.alpha_composite(halftone(INK, spacing=16, radius=1.6, alpha=22,
                                  seed=rnd.randint(1, 99), jitter=0.9))
    comp.alpha_composite(scanlines(alpha=11))

    d = ImageDraw.Draw(comp)
    for (x, y, sx, sy) in ((26, 26, 1, 1), (486, 26, -1, 1),
                           (26, 486, 1, -1), (486, 486, -1, -1)):
        d.line([(x * SS, y * SS), ((x + 26 * sx) * SS, y * SS)],
               fill=rgba(INK, 225), width=3 * SS)
        d.line([(x * SS, y * SS), (x * SS, (y + 26 * sy) * SS)],
               fill=rgba(INK, 225), width=3 * SS)
    fnt = art.font(art.MONO, 27 * SS)
    d.text((36 * SS, 470 * SS), row["code"], font=fnt, fill=rgba(INK, 240),
           anchor="ls")
    d.line([(34 * SS, 476 * SS), (104 * SS, 476 * SS)], fill=rgba(INK, 190),
           width=3 * SS)
    for i, h in enumerate((10, 18, 26, 34)):
        x = (436 + i * 13) * SS
        d.rectangle([x, (478 - h) * SS, x + 8 * SS, 478 * SS],
                    fill=rgba(INK, 235))

    comp = grain(comp, amount=5, seed=rnd.randint(1, 40))
    return comp.convert("RGB").resize((OUT, OUT), Image.LANCZOS)


# ============================================================ sheets
def colour_name(c):
    for name, value in (("ACID", ACID), ("MAGENTA", MAGENTA), ("CYAN", CYAN),
                        ("PAPER", PAPER), ("ORANGE", ORANGE), ("INK", INK)):
        if c == value:
            return name
    return "MIX"


def contact_sheet(tiles):
    width, row_h, top = 1440, 388, 216
    height = top + row_h * len(tiles) + 60
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)
    d.text((32, 56), "DIRECTION C2 — TRIPPY RAVE, RE-CUT", font=art.font(art.DISPLAY, 48),
           fill=PAPER, anchor="ls")
    d.text((32, 86),
           "SAME MELTED RISO TREATMENT · EVERY OBJECT IS RAVE ICONOGRAPHY AT 64 PX",
           font=art.font(art.MONO, 13), fill=ACID, anchor="ls")
    d.text((width - 32, 56), "64 / 128 / 256 PX", font=art.font(art.MONO, 14),
           fill=MUTED, anchor="rs")
    d.text((width - 32, 78), "C2 · SHEET ONLY", font=art.font(art.MONO, 11),
           fill=MUTED, anchor="rs")

    refs = [("rave", "LATEST"), ("tapepacks", "TAPE PACKS"), ("jungle", "JUNGLE"),
            ("hardcore", "HARDCORE"), ("pirate", "PIRATE"), ("toronto", "TORONTO")]
    d.text((32, 132), "ACCEPTED ORIGINALS (64 PX) — THE FAMILY", font=art.font(art.MONO, 11),
           fill=MUTED, anchor="ls")
    x = width - 32 - len(refs) * 92
    for name, label in refs:
        path = os.path.join(ART, name + ".png")
        if not os.path.exists(path):
            continue
        ref = Image.open(path).convert("RGB").resize((64, 64), Image.LANCZOS)
        sheet.paste(ref, (x, 144))
        d.text((x + 32, 218), label, font=art.font(art.MONO, 8), fill=MUTED,
               anchor="ms")
        x += 92

    for index, (row, tile) in enumerate(tiles):
        y = top + index * row_h
        d.text((32, y + 30), row["key"], font=art.font(art.DISPLAY, 28), fill=PAPER,
               anchor="ls")
        d.text((32, y + 52), "%s · %s FIELD" % (row["code"], colour_name(row["field"])),
               font=art.font(art.MONO, 12), fill=row["field"], anchor="ls")
        d.text((32, y + 74), "%s / %s PLATES" % (colour_name(row["pa"]),
                                                 colour_name(row["pb"])),
               font=art.font(art.MONO, 11), fill=MUTED, anchor="ls")
        d.text((32, y + 100), "WAS  " + row["was"], font=art.font(art.MONO, 9),
               fill=MUTED, anchor="ls")
        d.text((32, y + 116), "NOW  " + row["now"], font=art.font(art.MONO, 9),
               fill=PAPER, anchor="ls")
        read, conf = BLIND[row["key"]]
        d.text((32, y + 146), "64 READ: " + read, font=art.font(art.MONO, 9),
               fill=row["pa"], anchor="ls")
        d.text((32, y + 162), conf.upper(), font=art.font(art.MONO, 8),
               fill=MUTED, anchor="ls")

        x64, x128, x256 = 400, 500, 660
        for size, px in ((64, x64), (128, x128), (256, x256)):
            small = tile.resize((size, size), Image.LANCZOS)
            sheet.paste(small, (px, y + 40))
            d.rectangle([px, y + 40, px + size - 1, y + 39 + size],
                        outline=rgba(MUTED, 110), width=1)
            d.text((px, y + 40 + size + 18), "%d" % size, font=art.font(art.MONO, 11),
                   fill=MUTED, anchor="ls")
        d.text((x256, y + 40 + 256 + 36), "ACTUAL PX", font=art.font(art.MONO, 10),
               fill=MUTED, anchor="ls")

        rx, ry, rw, rh = 1040, y + 40, 356, 84
        d.rectangle([rx, ry, rx + rw, ry + rh], fill=INK_2, outline=rgba(MUTED, 80))
        sheet.paste(tile.resize((64, 64), Image.LANCZOS), (rx + 10, ry + 10))
        label, note = ROW_LABELS[row["key"]]
        f = art.fit_display(d, label, art.DISPLAY, rw - 96, 22, 12)
        d.text((rx + 86, ry + 40), label, font=f, fill=PAPER, anchor="ls")
        d.text((rx + 86, ry + 62), note, font=art.font(art.MONO, 9), fill=row["field"],
               anchor="ls")
        d.text((rx, ry + rh + 22), "64 PX ROW ART", font=art.font(art.MONO, 10),
               fill=MUTED, anchor="ls")

        if index < len(tiles) - 1:
            d.line([(32, y + row_h - 22), (width - 32, y + row_h - 22)],
                   fill=(38, 38, 48), width=1)

    d.text((32, height - 28),
           "ART STUDY ONLY · NOTHING WIRED · ONE SPOT FIELD · CHROMATIC MISREGISTRATION · MELT ON EVERY MARK",
           font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")
    sheet.save(SHEET, "PNG", optimize=True)
    print("wrote", SHEET)


def board(tiles):
    cols = 3
    tile, gap, left, top = 256, 34, 40, 158
    rows = (len(tiles) + cols - 1) // cols
    width = left * 2 + cols * tile + (cols - 1) * gap
    height = top + rows * (tile + 62) + 58
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)
    d.text((left, 56), "C2 · 1:1 · 256 PX NATIVE · NOTHING SCALED",
           font=art.font(art.DISPLAY, 44), fill=PAPER, anchor="ls")
    d.text((left, 86), "JUDGE THE PRINT AT 100 % — NOT THE 64 PX READ",
           font=art.font(art.MONO, 12), fill=ACID, anchor="ls")
    for i, (row, tile_img) in enumerate(tiles):
        r, c = divmod(i, cols)
        x = left + c * (tile + gap)
        y = top + r * (tile + 62)
        sheet.paste(tile_img, (x, y))
        d.rectangle([x, y, x + tile, y + tile], outline=rgba(MUTED, 80))
        d.text((x, y + tile + 20), row["key"], font=art.font(art.DISPLAY, 18),
               fill=PAPER, anchor="ls")
        d.text((x + tile, y + tile + 20), row["code"], font=art.font(art.MONO, 10),
               fill=row["field"], anchor="rs")
        d.text((x, y + tile + 40), OBJECT_NAME[row["glyph"]],
               font=art.font(art.MONO, 9), fill=MUTED, anchor="ls")
    d.text((left, height - 26),
           "one field colour · two separately warped plates · drips off the flat underside · halftone + scanlines",
           font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")
    sheet.save(BOARD, "PNG", optimize=True)
    print("wrote", BOARD)


def row_strip(tiles):
    width, row_h, top = 1180, 78, 174
    height = top + row_h * len(tiles) + 210
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)
    d.text((32, 54), "C2 · 64 PX ROW CHECK", font=art.font(art.DISPLAY, 44),
           fill=PAPER, anchor="ls")
    d.text((32, 84), "THE SIZE THE KODI SKIN ACTUALLY DRAWS · LIST ROW ON A DARK PANEL",
           font=art.font(art.MONO, 12), fill=ACID, anchor="ls")

    for i, (row, tile_img) in enumerate(tiles):
        y = top + i * row_h
        d.rectangle([32, y, 32 + 700, y + 64], fill=INK_2, outline=rgba(MUTED, 50))
        sheet.paste(tile_img.resize((64, 64), Image.LANCZOS), (36, y))
        label, note = ROW_LABELS[row["key"]]
        d.text((116, y + 30), label, font=art.font(art.DISPLAY, 21), fill=PAPER,
               anchor="ls")
        d.text((116, y + 48), note, font=art.font(art.MONO, 9), fill=row["field"],
               anchor="ls")
        d.text((716, y + 40), "64", font=art.font(art.MONO, 11), fill=MUTED, anchor="ls")

    y0 = top + len(tiles) * row_h + 26
    d.text((32, y0), "ACCEPTED ORIGINALS AT 64 PX", font=art.font(art.MONO, 11),
           fill=MUTED, anchor="ls")
    for i, (name, label) in enumerate((("rave", "LATEST"), ("tapepacks", "PACKS"),
                                       ("jungle", "JUNGLE"), ("hardcore", "HARDCORE"),
                                       ("pirate", "PIRATE"), ("toronto", "TORONTO"))):
        path = os.path.join(ART, name + ".png")
        if not os.path.exists(path):
            continue
        x = 32 + i * 96
        ref = Image.open(path).convert("RGB").resize((64, 64), Image.LANCZOS)
        sheet.paste(ref, (x, y0 + 14))
        d.text((x + 32, y0 + 88), label, font=art.font(art.MONO, 8), fill=MUTED,
               anchor="ms")

    sheet.save(ROWS, "PNG", optimize=True)
    print("wrote", ROWS)


def before_after(tiles):
    """C at 64/128 beside C2 at 64/128 — the re-cut, row by row."""
    width, row_h, top = 1040, 168, 168
    height = top + row_h * len(tiles) + 72
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)
    d.text((32, 56), "C → C2 · THE RE-CUT", font=art.font(art.DISPLAY, 46),
           fill=PAPER, anchor="ls")
    d.text((32, 86), "LEFT: WHAT THE OWNER BOUNCED (C) · RIGHT: WHAT REPLACES IT (C2) · BOTH AT 64 AND 128 PX",
           font=art.font(art.MONO, 12), fill=ACID, anchor="ls")

    xc, xc2 = 336, 700
    d.text((xc, 130), "C — REJECTED", font=art.font(art.MONO, 10), fill=MUTED,
           anchor="ls")
    d.text((xc2, 130), "C2 — RAVE OBJECT", font=art.font(art.MONO, 10), fill=ACID,
           anchor="ls")
    for i, (row, tile) in enumerate(tiles):
        y = top + i * row_h
        d.text((32, y + 46), row["key"], font=art.font(art.DISPLAY, 20), fill=PAPER,
               anchor="ls")
        d.text((32, y + 66), row["was"], font=art.font(art.MONO, 8), fill=MUTED,
               anchor="ls")
        d.text((32, y + 96), "-> " + row["now"], font=art.font(art.MONO, 8),
               fill=row["field"], anchor="ls")
        d.text((32, y + 120), "READS: " + BLIND[row["key"]][0],
               font=art.font(art.MONO, 8), fill=MUTED, anchor="ls")

        old_path = os.path.join(C_DIR, "sample-%s.png" % row["key"])
        if os.path.exists(old_path):
            old = Image.open(old_path).convert("RGB")
            for size, dx in ((64, 0), (128, 76)):
                sheet.paste(old.resize((size, size), Image.LANCZOS), (xc + dx, y + 20))
        for size, dx in ((64, 0), (128, 76)):
            small = tile.resize((size, size), Image.LANCZOS)
            sheet.paste(small, (xc2 + dx, y + 20))
        d.rectangle([xc2 - 8, y + 12, xc2 + 76 + 128, y + 156],
                    outline=rgba(ACID, 70), width=1)
        d.line([(xc + 64, y + 140), (xc + 128, y + 140)], fill=rgba(MUTED, 90), width=1)
        if i < len(tiles) - 1:
            d.line([(32, y + row_h - 10), (width - 32, y + row_h - 10)],
                   fill=(34, 34, 44), width=1)

    d.text((32, height - 30),
           "C kept the treatment; only the objects change · no arrow · no gem · no big-top · no mic · no TV · no banana · no letters",
           font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")
    sheet.save(BEFORE, "PNG", optimize=True)
    print("wrote", BEFORE)


def vocabulary(tiles):
    """Every object C2 uses, at 64, 128 and 256, captioned."""
    order = [row["glyph"] for row in RECIPES]
    built = {row["glyph"]: tile for row, tile in tiles}
    cols, cell_w, cell_h = 3, 360, 268
    rows = (len(order) + cols - 1) // cols
    width = 64 + cols * cell_w
    height = 176 + rows * cell_h + 64
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)
    d.text((32, 56), "C2 VOCABULARY", font=art.font(art.DISPLAY, 44), fill=PAPER,
           anchor="ls")
    d.text((32, 88), "THE NINE OBJECTS THE SHEET DRAWS \u00b7 EACH AT 64 AND 128 PX",
           font=art.font(art.MONO, 12), fill=ACID, anchor="ls")
    for i, name in enumerate(order):
        r, c = divmod(i, cols)
        x = 32 + c * cell_w
        y = 176 + r * cell_h
        tile = built[name]
        sheet.paste(tile.resize((64, 64), Image.LANCZOS), (x, y))
        sheet.paste(tile.resize((128, 128), Image.LANCZOS), (x + 78, y))
        d.text((x, y + 150), OBJECT_NAME[name], font=art.font(art.DISPLAY, 20),
               fill=PAPER, anchor="ls")
        d.text((x, y + 172), "64 / 128 PX", font=art.font(art.MONO, 9), fill=MUTED,
               anchor="ls")
    d.text((32, height - 46),
           "cassette \u00b7 cassette (labelled) \u00b7 acid smiley \u00b7 speaker stack \u00b7 vinyl / turntable \u00b7 glowstick \u00b7 smiley balloon \u00b7 rave flyer \u00b7 lazer / scan lines",
           font=art.font(art.MONO, 9), fill=MUTED, anchor="ls")
    d.text((32, height - 30),
           "CUT after the 64 px blind test: whistle, mixtape spine, open reel, down-arrow, gem, big-top, dynamic mic, mast, jolly-roger",
           font=art.font(art.MONO, 9), fill=mix(MUTED, PAPER, 0.35), anchor="ls")
    sheet.save(VOCAB, "PNG", optimize=True)
    print("wrote", VOCAB)


# ============================================================ preview
def preview():
    """Fast silhouette check: no print effects, flat field, 256 / 128 / 96 / 64."""
    names = ["cassette", "flyer", "speaker", "vinyl", "smiley", "glowstick",
             "tape", "lazer", "balloon"]
    cols = 4
    cell_w, cell_h = 330, 480
    rows = (len(names) + cols - 1) // cols
    width = 40 + cols * cell_w
    height = 100 + rows * cell_h
    sheet = Image.new("RGB", (width, height), (24, 24, 30))
    d = ImageDraw.Draw(sheet)
    d.text((40, 52), "C2 GLYPH SILHOUETTE CHECK", font=art.font(art.DISPLAY, 38),
           fill=PAPER, anchor="ls")
    d.text((40, 76), "NO MELT / NO PLATES — JUST THE SHAPE, 256 / 128 / 96 / 64",
           font=art.font(art.MONO, 10), fill=ACID, anchor="ls")
    for i, name in enumerate(names):
        r, c = divmod(i, cols)
        x = 40 + c * cell_w
        y = 100 + r * cell_h
        layer = glyph_layer(name, ACID, rot=0.0, melt=None, spat=0)
        tile = Image.new("RGBA", (PX, PX), rgba(ACID, 255))
        tile.alpha_composite(layer)
        tile = tile.convert("RGB")
        sheet.paste(tile.resize((256, 256), Image.LANCZOS), (x, y))
        for size, dx in ((128, 0), (96, 136), (64, 240)):
            sheet.paste(tile.resize((size, size), Image.LANCZOS), (x + dx, y + 286))
            d.text((x + dx, y + 286 + size + 14), "%d" % size,
                   font=art.font(art.MONO, 9), fill=MUTED, anchor="ls")
        d.text((x, y + 428), name.upper(), font=art.font(art.DISPLAY, 16),
               fill=PAPER, anchor="ls")
    sheet.save(PREVIEW, "PNG", optimize=True)
    print("wrote", PREVIEW)


# ============================================================ main
def main():
    if "--preview" in sys.argv:
        preview()
        return
    tiles = [(row, build_tile(row)) for row in RECIPES]
    for size in (64, 128, 256):
        os.makedirs(os.path.join(HERE, str(size)), exist_ok=True)
    for row, tile in tiles:
        tile.save(os.path.join(HERE, "sample-%s.png" % row["key"]), "PNG",
                  optimize=True)
        for size in (64, 128, 256):
            tile.resize((size, size), Image.LANCZOS).save(
                os.path.join(HERE, str(size), "%s-%d.png" % (row["key"], size)),
                "PNG", optimize=True)
    contact_sheet(tiles)
    board(tiles)
    row_strip(tiles)
    before_after(tiles)
    vocabulary(tiles)


if __name__ == "__main__":
    main()
