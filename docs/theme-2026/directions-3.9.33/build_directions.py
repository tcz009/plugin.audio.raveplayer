#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draft direction study for the 38 duplicate-row stickers (3.9.33 / 1.6.41).

This is an ART STUDY, not the production generator. It draws two candidate
visual directions for a representative sample of the duplicated menu rows so
the owner/Lead can pick a direction before any wiring:

  Direction A — BIG MARK     one oversized, custom-drawn object; no type.
  Direction B — MONOGRAM     one custom heavy letterform, built as the object.

Both use the accepted 2026 language (see docs/THEME-2026.md and
scripts/make-art.py): one spot-colour field, ink glyph, a single partner-ink
misregistration plate, halftone, 45-degree hatch, scanlines, crop marks,
sticker code and signal bars. Nothing is copied or traced.

Outputs (all under this folder, nothing wired, no existing art overwritten):
  direction-a-contact-sheet.png   7 samples at 64 / 128 / 256 actual
  direction-b-contact-sheet.png   7 samples at 64 / 128 / 256 actual
  direction-1to1-preview.png      all 14 at native 256, 1:1, A above B
  DIRECTIONS.md                   short rationale + next step

    /path/to/python3 build_directions.py

Pillow is build-time only.
"""
from __future__ import annotations

import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SHEET_A = os.path.join(HERE, "direction-a-contact-sheet.png")
SHEET_B = os.path.join(HERE, "direction-b-contact-sheet.png")
PREVIEW = os.path.join(HERE, "direction-1to1-preview.png")

ROW_LABELS = {
    "rave-tapes": ("Rave Tape Packs", "TAPE PACKS · GENRE"),
    "podcasts": ("Podcasts", "MIXES & SHOWS"),
    "kool": ("Kool FM", "LIVE RADIO · STATION"),
    "dreamscape": ("Dreamscape", "QUICK FILTER · SERIES"),
    "downloads": ("Downloads", "MY LIBRARY · WEB"),
    "radio-jungle": ("Jungle", "LIVE RADIO · GENRE"),
    "rave-archive": ("Rave Archive UK", "CURATED GEMS"),
}


def load_make_art():
    path = os.path.join(ROOT, "scripts", "make-art.py")
    spec = importlib.util.spec_from_file_location("rave_make_art", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


art = load_make_art()
Image = art.Image
ImageDraw = art.ImageDraw
INK = art.INK
INK_2 = art.INK_2
PAPER = art.PAPER
MUTED = art.MUTED
ACID = art.ACID
MAGENTA = art.MAGENTA
CYAN = art.CYAN
ORANGE = art.ORANGE


# --------------------------------------------------------------------------- helpers
def _canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def _paste(d, layer, angle=0.0, center=(256, 256)):
    if angle:
        layer = layer.rotate(angle, resample=Image.BICUBIC, center=centre)
    d._image.alpha_composite(layer)


def _star(d, cx, cy, radius, colour, points=4, inner=0.36):
    pts = []
    for i in range(points * 2):
        r = radius if i % 2 == 0 else radius * inner
        a = -math.pi / 2 + i * math.pi / points
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=colour)


def _arc_band(d, cx, cy, r, thickness, start, end, colour=INK):
    """A thick open arc that reads as a signal ring at 64 px."""
    d.arc([cx - r, cy - r, cx + r, cy + r], start=start, end=end,
          fill=colour, width=thickness)


def _ticks(d, x0, y0, x1, y1, count, colour, width=6):
    for i in range(count):
        t = i / max(1, count - 1)
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        d.rectangle([x - width / 2, y - 10, x + width / 2, y + 10], fill=colour)


def _tape(g, accent, box, radius=22, label=True, window=True, screws=True):
    """Cassette shell, drawn in 512-space. `g` is an ImageDraw on a layer."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    g.rounded_rectangle(box, radius=radius, fill=INK)
    if label:
        pad = int(w * 0.08)
        g.rounded_rectangle([x0 + pad, y0 + int(h * 0.10),
                             x1 - pad, y0 + int(h * 0.38)],
                            radius=max(6, radius // 3), fill=accent)
        # label ticks, knocked out of the accent band
        for i in range(3):
            bx = x0 + pad + int(w * 0.10) + i * int(w * 0.18)
            g.rectangle([bx, y0 + int(h * 0.18), bx + int(w * 0.10),
                         y0 + int(h * 0.22)], fill=INK)
    if window:
        pad = int(w * 0.08)
        wt = y0 + int(h * 0.50)
        wb = y1 - int(h * 0.16)
        g.rounded_rectangle([x0 + pad, wt, x1 - pad, wb],
                            radius=max(4, radius // 4), fill=accent)
        cy = (wt + wb) // 2
        rr = int(h * 0.105)
        for cx in (x0 + int(w * 0.34), x0 + int(w * 0.66)):
            g.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=INK)
            g.ellipse([cx - rr // 3, cy - rr // 3, cx + rr // 3, cy + rr // 3],
                      fill=accent)
    if screws:
        pad = int(w * 0.055)
        for cx in (x0 + pad, x1 - pad):
            for cy in (y0 + pad, y1 - pad):
                r = max(4, int(w * 0.018))
                g.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)


def _spine(g, accent, box, radius=14, band=0.32, reel=True, lean=0.0):
    """A vertical tape spine: the shelf/archive object, not another cassette."""
    x0, y0, x1, y1 = box
    w = x1 - x0
    g.rounded_rectangle(box, radius=radius, fill=INK)
    pad = max(5, int(w * 0.12))
    # label strip with two ink ticks
    top = y0 + int((y1 - y0) * 0.06)
    bottom = top + int((y1 - y0) * band)
    g.rounded_rectangle([x0 + pad, top, x1 - pad, bottom], radius=6, fill=accent)
    for i in range(2):
        by = top + int((bottom - top) * (0.34 + i * 0.30))
        g.rectangle([x0 + pad + 6, by, x1 - pad - 6, by + 7], fill=INK)
    if reel:
        cy = y0 + int((y1 - y0) * 0.66)
        cx = (x0 + x1) // 2
        r = max(11, int(w * 0.30))
        g.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
        g.ellipse([cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2], fill=INK)
        g.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=accent)
    # bottom edge grip lines
    for i in range(3):
        gy = y1 - 30 + i * 8
        g.rectangle([x0 + pad, gy, x1 - pad, gy + 3], fill=accent)


# --------------------------------------------------------------------------- direction A
def _a_rave_tapes(d, accent):
    """A ghetto blaster: the object the packs were played on, one silhouette."""
    # handle
    d.line([(138, 186), (138, 104), (374, 104), (374, 186)],
           fill=INK, width=20, joint="curve")
    for x in (172, 212, 300, 340):
        d.rectangle([x, 96, x + 20, 112], fill=accent)
    # body
    d.rounded_rectangle([48, 174, 464, 420], radius=26, fill=INK)
    # speakers, knocked out of the body
    for cx in (138, 374):
        d.ellipse([cx - 72, 228, cx + 72, 372], fill=accent)
        d.ellipse([cx - 40, 260, cx + 40, 340], fill=INK)
        d.ellipse([cx - 13, 287, cx + 13, 313], fill=accent)
    # cassette deck
    d.rounded_rectangle([222, 224, 290, 322], radius=9, fill=accent)
    d.rounded_rectangle([232, 236, 280, 292], radius=6, fill=INK)
    for cx in (246, 266):
        d.ellipse([cx - 9, 260, cx + 9, 278], fill=accent)
        d.ellipse([cx - 3, 266, cx + 3, 272], fill=INK)
    # transport buttons
    for i in range(3):
        d.rectangle([224 + i * 24, 332, 240 + i * 24, 350], fill=accent)
    # antenna
    d.line([(420, 174), (452, 76)], fill=INK, width=10)
    d.ellipse([444, 64, 464, 84], fill=INK)


def _paste_to_layer(base, layer, angle, centre):
    if angle:
        layer = layer.rotate(angle, resample=Image.BICUBIC, center=centre)
    base.alpha_composite(layer)


def _a_podcasts(d, accent):
    """A single dynamic mic, head-on, with its cable curling into a jack."""
    # cable first, so the body sits on top of it
    d.line([(256, 356), (256, 430), (324, 430), (350, 398)],
           fill=INK, width=22, joint="curve")
    d.ellipse([338, 386, 366, 414], fill=INK)
    # body + collar
    d.polygon([(196, 246), (316, 246), (298, 388), (214, 388)], fill=INK)
    d.rectangle([184, 236, 328, 266], fill=INK)
    # head
    d.ellipse([152, 64, 360, 272], fill=INK)
    # grille: horizontal slots clipped to the head
    grille = _canvas()
    gg = ImageDraw.Draw(grille)
    for i, y in enumerate((112, 140, 168, 196, 224)):
        gg.rectangle([150, y, 362, y + 12], fill=accent)
    mask = Image.new("L", (512, 512), 0)
    ImageDraw.Draw(mask).ellipse([162, 74, 350, 262], fill=255)
    grille.putalpha(Image.composite(grille.getchannel("A"),
                                    Image.new("L", (512, 512), 0), mask))
    d._image.alpha_composite(grille)
    # collar screws and a knurled ring
    for x in (206, 256, 306):
        d.ellipse([x - 7, 242, x + 7, 256], fill=accent)
    d.rectangle([216, 360, 296, 372], fill=accent)


def _a_kool(d, accent):
    """A pirate aerial on a tower block: the roof, the rig, the signal."""
    # tower block with a stepped roof
    d.polygon([(48, 456), (48, 362), (78, 362), (78, 326), (224, 326),
               (224, 362), (252, 362), (252, 456)], fill=INK)
    # windows, knocked out
    for row in range(2):
        for col in range(3):
            d.rectangle([76 + col * 54, 378 + row * 40,
                         104 + col * 54, 404 + row * 40], fill=accent)
    # Yagi on the roof
    d.line([(176, 326), (392, 104)], fill=INK, width=30)
    d.line([(190, 254), (146, 384)], fill=INK, width=22)   # reflector
    length = 146
    for i in range(2):
        t = 0.42 + i * 0.28
        x = 176 + (392 - 176) * t
        y = 326 - (326 - 104) * t
        nx, ny = 0.761, 0.649
        half = length / 2 - i * 18
        d.line([(x - nx * half, y - ny * half),
                (x + nx * half, y + ny * half)], fill=INK, width=22)
        for sign in (-1, 1):
            d.ellipse([x + sign * nx * half - 8, y + sign * ny * half - 8,
                       x + sign * nx * half + 8, y + sign * ny * half + 8],
                      fill=accent)
    # signal rings off the tip
    for r in (36, 62, 90):
        _arc_band(d, 392, 104, r, 15, start=-56, end=54)
    d.ellipse([382, 94, 402, 114], fill=INK)
    d.ellipse([387, 99, 397, 109], fill=accent)
    # mast foot + roof beacon
    d.rectangle([156, 310, 200, 334], fill=INK)
    d.ellipse([60, 312, 76, 328], fill=accent)


def _a_dreamscape(d, accent):
    """A heavy crescent with knocked-out stars and one shooting star."""
    layer = _canvas()
    g = ImageDraw.Draw(layer)
    g.ellipse([66, 86, 430, 450], fill=INK)
    g.ellipse([176, 104, 508, 434], fill=(0, 0, 0, 0))
    layer = layer.rotate(-16, resample=Image.BICUBIC, center=(256, 256))
    d._image.alpha_composite(layer)
    # stars knocked out of the ink crescent
    _star(d, 146, 218, 24, accent)
    _star(d, 108, 320, 15, accent)
    _star(d, 218, 126, 12, accent)
    # shooting star: big head + one solid tapered trail
    d.polygon([(356, 118), (384, 146), (286, 232), (268, 208)], fill=INK)
    _star(d, 398, 112, 34, INK)
    _star(d, 392, 366, 16, INK)


def _a_downloads(d, accent):
    """A cassette unspooling into one classic, wide down-arrow."""
    sub = _canvas()
    sg = ImageDraw.Draw(sub)
    _tape(sg, accent, (110, 52, 388, 168), radius=22)
    sub = sub.rotate(-6, resample=Image.BICUBIC, center=(249, 110))
    d._image.alpha_composite(sub)
    # shaft and a head wider than the shaft: unmistakably an arrow
    d.rectangle([232, 160, 286, 306], fill=INK)
    d.polygon([(150, 296), (370, 296), (260, 446)], fill=INK)
    # accent play cut + one centre-line on the shaft
    d.polygon([(320, 74), (320, 138), (366, 106)], fill=accent)
    d.rectangle([255, 178, 263, 300], fill=accent)
    # motion ticks
    for y in (300, 340):
        d.rectangle([66, y, 116, y + 10], fill=accent)
        d.rectangle([396, y, 446, y + 10], fill=accent)


def _a_radio_jungle(d, accent):
    """A djembe + signal rings: jungle pressure, one unmistakable silhouette."""
    # signal rings from the head
    for r in (58, 90, 124):
        _arc_band(d, 256, 150, r, 12, start=204, end=336)
    # goblet body: wide bowl, narrow stem, flared foot
    d.polygon([(176, 186), (336, 186), (310, 300), (286, 336),
               (286, 392), (330, 450), (182, 450), (226, 392),
               (226, 336), (202, 300)], fill=INK)
    # head
    d.ellipse([170, 146, 342, 218], fill=INK)
    d.ellipse([184, 158, 328, 206], fill=accent)
    for i in range(5):
        a = math.radians(198 + i * 36)
        cx, cy = 256 + 78 * math.cos(a), 182 + 30 * math.sin(a)
        d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=INK)
    # tension ropes on the bowl and stem
    for (x0, y0, x1, y1) in ((214, 214, 238, 316), (256, 214, 256, 330),
                             (298, 214, 274, 316), (244, 348, 250, 388),
                             (268, 348, 262, 388)):
        d.line([(x0, y0), (x1, y1)], fill=accent, width=7)
    # stem band + foot ring
    d.rectangle([228, 372, 284, 384], fill=accent)
    d.rectangle([196, 438, 316, 450], fill=accent)
    # beat marks
    for y in (250, 300):
        d.rectangle([142, y, 166, y + 9], fill=accent)
        d.rectangle([346, y, 370, y + 9], fill=accent)


def _a_rave_archive(d, accent):
    """A VHS master tape: the archive object, with a play triangle and barcode."""
    d.rounded_rectangle([58, 168, 454, 428], radius=22, fill=INK)
    # top label strip
    d.rounded_rectangle([80, 186, 432, 230], radius=7, fill=accent)
    for i in range(4):
        bx = 98 + i * 74
        d.rectangle([bx, 200, bx + 46, 210], fill=INK)
    # reel window
    d.rounded_rectangle([96, 258, 306, 356], radius=10, fill=accent)
    for cx in (152, 250):
        d.ellipse([cx - 34, 274, cx + 34, 342], fill=INK)
        d.ellipse([cx - 13, 295, cx + 13, 321], fill=accent)
    # play triangle on the right
    d.polygon([(340, 258), (340, 354), (418, 306)], fill=accent)
    # barcode + spine lines
    for i in range(11):
        x = 96 + i * 14
        d.rectangle([x, 382, x + (6 if i % 3 else 9), 406], fill=accent)
    d.rectangle([320, 382, 432, 394], fill=accent)
    # flap notch
    d.rectangle([58, 240, 74, 356], fill=accent)


# --------------------------------------------------------------------------- direction B
def _erase(d, kind, box, radius=0):
    if kind == "rrect":
        d.rounded_rectangle(box, radius=radius, fill=(0, 0, 0, 0))
    elif kind == "ellipse":
        d.ellipse(box, fill=(0, 0, 0, 0))
    else:
        d.rectangle(box, fill=(0, 0, 0, 0))


def _b_rave_tapes(d, accent):
    """R: the bowl counter is opened into a tape reel; the leg is a ribbon."""
    # stem
    d.rectangle([112, 56, 202, 456], fill=INK)
    # bowl
    d.rounded_rectangle([182, 56, 392, 286], radius=104, fill=INK)
    _erase(d, "rrect", [206, 88, 366, 254], radius=76)
    # leg
    d.polygon([(300, 236), (392, 456), (300, 456), (236, 268)], fill=INK)
    # reel in the opened bowl
    cx, cy, r = 290, 166, 62
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
    d.ellipse([cx - r + 13, cy - r + 13, cx + r - 13, cy + r - 13], fill=INK)
    for i in range(3):
        a = math.radians(i * 120 + 15)
        d.line([(cx, cy), (cx + 42 * math.cos(a), cy + 42 * math.sin(a))],
               fill=accent, width=9)
    d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=accent)
    # tape window + screws on the stem
    d.rounded_rectangle([126, 322, 188, 434], radius=16, fill=accent)
    d.ellipse([146, 350, 168, 372], fill=INK)
    d.ellipse([146, 392, 168, 414], fill=INK)
    # ribbon curl off the leg
    d.line([(340, 420), (420, 420), (450, 384)], fill=INK, width=18, joint="curve")
    d.ellipse([438, 372, 462, 396], fill=INK)


def _b_podcasts(d, accent):
    """P: the bowl is a solid mic head; the stem is a handle with a cable."""
    d.rectangle([118, 56, 208, 456], fill=INK)
    d.ellipse([176, 56, 400, 280], fill=INK)
    # grille: bold horizontal slots, clipped to the head
    grille = _canvas()
    gg = ImageDraw.Draw(grille)
    for y in (92, 126, 160, 194, 228):
        gg.rectangle([178, y, 398, y + 13], fill=accent)
    mask = Image.new("L", (512, 512), 0)
    ImageDraw.Draw(mask).ellipse([186, 66, 390, 270], fill=255)
    grille.putalpha(Image.composite(grille.getchannel("A"),
                                    Image.new("L", (512, 512), 0), mask))
    d._image.alpha_composite(grille)
    # rim + collar + cable
    d.arc([184, 64, 392, 272], start=200, end=340, fill=accent, width=9)
    d.rectangle([164, 262, 412, 292], fill=accent)
    d.line([(208, 450), (208, 470), (318, 470), (348, 440)],
           fill=INK, width=18, joint="curve")
    d.ellipse([336, 428, 360, 452], fill=INK)
    for y in (326, 350, 374, 398):
        d.rectangle([134, y, 192, y + 8], fill=accent)


def _b_kool(d, accent):
    """K: a lattice mast whose arms are Yagi elements."""
    d.rectangle([112, 56, 202, 456], fill=INK)
    # lattice notches on the stem
    for y in (150, 260, 370):
        d.line([(120, y), (194, y - 26)], fill=accent, width=8)
    # arms
    d.polygon([(202, 236), (392, 56), (392, 148), (252, 268)], fill=INK)
    d.polygon([(202, 280), (392, 456), (392, 364), (252, 248)], fill=INK)
    # antenna tip + signal rings
    d.rectangle([148, 24, 164, 56], fill=INK)
    d.ellipse([144, 8, 168, 32], fill=INK)
    for r in (30, 52, 74):
        _arc_band(d, 156, 22, r, 9, start=-140, end=-40)
    # on-air beacon
    d.ellipse([322, 214, 350, 242], fill=accent)


def _b_dreamscape(d, accent):
    """D: a wide counter holds a crescent moon; stars are knocked from the face."""
    d.rectangle([112, 56, 214, 456], fill=INK)
    d.rounded_rectangle([190, 56, 438, 456], radius=128, fill=INK)
    _erase(d, "rrect", [214, 92, 404, 420], radius=104)
    # crescent moon inside the counter
    moon = _canvas()
    mg = ImageDraw.Draw(moon)
    mg.ellipse([228, 126, 418, 378], fill=INK)
    mg.ellipse([268, 104, 458, 356], fill=(0, 0, 0, 0))
    d._image.alpha_composite(moon)
    _star(d, 264, 178, 17, INK)
    _star(d, 252, 344, 11, INK)
    # knocked-out stars on the D face
    _star(d, 270, 110, 20, accent)
    _star(d, 356, 380, 15, accent)
    _star(d, 158, 330, 10, accent)


def _b_downloads(d, accent):
    """D: the counter is a download arrow dropping into a tray."""
    d.rectangle([112, 56, 214, 456], fill=INK)
    d.rounded_rectangle([190, 56, 438, 456], radius=128, fill=INK)
    _erase(d, "rrect", [214, 92, 404, 420], radius=104)
    # arrow inside the counter
    d.rectangle([292, 118, 330, 292], fill=INK)
    d.polygon([(252, 274), (370, 274), (311, 358)], fill=INK)
    # tray: a shallow U the arrow drops into
    d.rectangle([248, 388, 374, 404], fill=INK)
    d.rectangle([248, 362, 266, 404], fill=INK)
    d.rectangle([356, 362, 374, 404], fill=INK)
    # tape label band across the stem
    d.rounded_rectangle([128, 316, 200, 438], radius=14, fill=accent)
    d.ellipse([150, 344, 172, 366], fill=INK)
    # knocked-out speed ticks
    for y in (112, 142):
        d.rectangle([352, y, 406, y + 8], fill=accent)


def _b_radio_jungle(d, accent):
    """J: a mast stem dropping into a vine hook with broad leaves."""
    # hook path
    d.line([(300, 70), (300, 330), (292, 386), (250, 430), (186, 438), (140, 404)],
           fill=INK, width=86, joint="curve")
    # round the ends
    d.ellipse([257, 70, 343, 156], fill=INK)
    d.ellipse([102, 366, 178, 442], fill=INK)
    # signal rings off the stem
    for r in (36, 63, 90):
        _arc_band(d, 300, 210, r, 10, start=108, end=252)
    # two broad leaves on the hook
    d.polygon([(166, 414), (54, 348), (84, 466)], fill=INK)
    d.polygon([(232, 436), (258, 498), (304, 442)], fill=INK)
    # knocked-out veins
    d.line([(300, 96), (300, 352)], fill=accent, width=9)
    d.line([(152, 400), (74, 364)], fill=accent, width=9)
    d.line([(146, 426), (96, 456)], fill=accent, width=9)
    d.line([(238, 448), (260, 480)], fill=accent, width=7)


def _b_rave_archive(d, accent):
    """A: a big-top A with a flag apex, tape-spine crossbar and stage triangle."""
    # legs
    d.polygon([(232, 60), (318, 60), (446, 456), (354, 456)], fill=INK)
    d.polygon([(194, 60), (280, 60), (158, 456), (66, 456)], fill=INK)
    # crossbar = tape spine
    d.rectangle([132, 306, 380, 382], fill=INK)
    d.rounded_rectangle([148, 318, 364, 352], radius=8, fill=accent)
    for cx in (196, 256, 316):
        d.ellipse([cx - 10, 328, cx + 10, 348], fill=INK)
    # apex flag
    d.rectangle([246, 18, 260, 64], fill=INK)
    d.polygon([(260, 20), (374, 58), (260, 96)], fill=INK)
    d.polygon([(276, 44), (338, 58), (276, 74)], fill=accent)
    # stage triangle in the A counter
    d.polygon([(256, 186), (256, 276), (326, 231)], fill=INK)
    # bunting
    for x in (104, 146):
        d.polygon([(x, 116), (x + 30, 116), (x + 15, 148)], fill=accent)


# --------------------------------------------------------------------------- recipes
DIRECTION_A = [
    ("rave-tapes", ACID, MAGENTA, _a_rave_tapes, "RP-21",
     "Ghetto blaster: the pack player", "ACID / MAGENTA"),
    ("podcasts", MAGENTA, CYAN, _a_podcasts, "RP-27",
     "One dynamic mic, cable into a jack", "MAGENTA / CYAN"),
    ("kool", CYAN, MAGENTA, _a_kool, "RP-31",
     "Pirate Yagi on a tower block", "CYAN / MAGENTA"),
    ("dreamscape", PAPER, MAGENTA, _a_dreamscape, "RP-40",
     "Heavy crescent, knocked-out stars", "PAPER / MAGENTA"),
    ("downloads", ORANGE, ACID, _a_downloads, "RP-55",
     "Cassette unspooling into a down-arrow", "ORANGE / ACID"),
    ("radio-jungle", ACID, MAGENTA, _a_radio_jungle, "RP-34",
     "Jungle drum + signal rings", "ACID / MAGENTA"),
    ("rave-archive", PAPER, CYAN, _a_rave_archive, "RP-29",
     "VHS master tape + play triangle", "PAPER / CYAN"),
]

DIRECTION_B = [
    ("rave-tapes", ACID, MAGENTA, _b_rave_tapes, "RP-21",
     "R: the bowl counter becomes a reel", "ACID / MAGENTA"),
    ("podcasts", MAGENTA, CYAN, _b_podcasts, "RP-27",
     "P: the bowl becomes a mic head", "MAGENTA / CYAN"),
    ("kool", CYAN, MAGENTA, _b_kool, "RP-31",
     "K: a lattice mast with Yagi arms", "CYAN / MAGENTA"),
    ("dreamscape", PAPER, MAGENTA, _b_dreamscape, "RP-40",
     "D: crescent moon inside the counter", "PAPER / MAGENTA"),
    ("downloads", ORANGE, ACID, _b_downloads, "RP-55",
     "D: counter is a down-arrow into a tray", "ORANGE / ACID"),
    ("radio-jungle", ACID, MAGENTA, _b_radio_jungle, "RP-34",
     "J: mast stem into a vine hook", "ACID / MAGENTA"),
    ("rave-archive", PAPER, CYAN, _b_rave_archive, "RP-29",
     "A: big-top A with a stage triangle", "PAPER / CYAN"),
]


def render(recipe):
    name, accent, shadow, fn, code, _intent, _palette = recipe
    key = "dir_" + name
    art.GLYPHS[key] = fn
    return art.build_icon(accent, shadow, key, code)


# --------------------------------------------------------------------------- sheets
def build_contact(recipes, title, subtitle, path):
    tiles = [(recipe, render(recipe)) for recipe in recipes]
    width, row_h, top = 1440, 336, 118
    height = top + row_h * len(tiles) + 54
    sheet = Image.new("RGB", (width, height), INK)
    draw = ImageDraw.Draw(sheet)
    draw.text((32, 58), title, font=art.font(art.DISPLAY, 50),
              fill=PAPER, anchor="ls")
    draw.text((32, 84), subtitle, font=art.font(art.MONO, 13),
              fill=ACID, anchor="ls")
    draw.text((width - 32, 58), "64 / 128 / 256 PX",
              font=art.font(art.MONO, 14), fill=MUTED, anchor="rs")

    for index, (recipe, tile) in enumerate(tiles):
        name, accent, _shadow, _fn, code, intent, palette = recipe
        y = top + index * row_h
        draw.text((32, y + 30), name, font=art.font(art.DISPLAY, 27),
                  fill=PAPER, anchor="ls")
        draw.text((32, y + 52), "%s · %s" % (code, palette),
                  font=art.font(art.MONO, 12), fill=accent, anchor="ls")
        draw.text((32, y + 78), intent, font=art.font(art.MONO, 12),
                  fill=MUTED, anchor="ls")

        # 64 / 128 / 256 actual sizes
        x64, x128, x256 = 516, 612, 772
        for size, x in ((64, x64), (128, x128), (256, x256)):
            small = tile.resize((size, size), Image.LANCZOS)
            sheet.paste(small, (x, y + 34))
            draw.rectangle([x, y + 34, x + size - 1, y + 33 + size],
                           outline=MUTED + (120,), width=1)
            draw.text((x, y + 34 + size + 20), "%d" % size,
                      font=art.font(art.MONO, 12), fill=MUTED, anchor="ls")
        draw.text((x256, y + 34 + 256 + 38), "ACTUAL PX",
                  font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")

        # how the same file looks as a 64 px Kodi/web list row
        rx, ry, rw, rh = 1080, y + 34, 320, 80
        draw.rectangle([rx, ry, rx + rw, ry + rh], fill=INK_2,
                       outline=MUTED + (90,), width=1)
        sheet.paste(tile.resize((64, 64), Image.LANCZOS), (rx + 10, ry + 8))
        row_label, row_note = ROW_LABELS[name]
        row_font = art.fit_display(draw, row_label, art.DISPLAY, rw - 92, 20, 12)
        draw.text((rx + 86, ry + 36), row_label, font=row_font,
                  fill=PAPER, anchor="ls")
        draw.text((rx + 86, ry + 58), row_note,
                  font=art.font(art.MONO, 9), fill=accent, anchor="ls")
        draw.text((rx, ry + rh + 22), "64 PX ROW ART",
                  font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")
        if index < len(tiles) - 1:
            draw.line([(32, y + row_h - 20), (width - 32, y + row_h - 20)],
                      fill=(38, 38, 48), width=1)

    draw.text((32, height - 26),
              "SCREEN-PRINT PASS · ONE SPOT COLOUR + INK · MISREGISTRATION · HALFTONE · SCANLINES",
              font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")
    sheet.save(path, "PNG", optimize=True)
    print("wrote", path)


def build_preview(a_tiles, b_tiles, path):
    """All samples at native 256 (1:1), direction A above direction B."""
    cols = len(a_tiles)
    tile, gap, left = 256, 30, 40
    width = left * 2 + cols * tile + (cols - 1) * gap
    height = 880
    sheet = Image.new("RGB", (width, height), INK)
    draw = ImageDraw.Draw(sheet)
    draw.text((left, 56), "1:1 PREVIEW · 256 PX NATIVE",
              font=art.font(art.DISPLAY, 44), fill=PAPER, anchor="ls")
    draw.text((left, 82),
              "SAME SEVEN ROWS, TWO DIRECTIONS · NOTHING SCALED IN THIS IMAGE",
              font=art.font(art.MONO, 12), fill=ACID, anchor="ls")

    bands = [
        ("A", "BIG MARK", a_tiles, 128),
        ("B", "MONOGRAM", b_tiles, 500),
    ]
    for label, title, tiles, y in bands:
        draw.rectangle([left, y - 34, left + 46, y + 12], fill=PAPER)
        draw.text((left + 23, y - 12), label, font=art.font(art.DISPLAY, 34),
                  fill=INK, anchor="mm")
        draw.text((left + 62, y - 4), title, font=art.font(art.DISPLAY, 26),
                  fill=PAPER, anchor="ls")
        for i, (recipe, tile_img) in enumerate(tiles):
            name, accent, _shadow, _fn, code, _intent, _palette = recipe
            x = left + i * (tile + gap)
            sheet.paste(tile_img, (x, y))
            draw.rectangle([x, y, x + tile, y + tile],
                           outline=MUTED + (90,), width=1)
            draw.text((x, y + tile + 22), name, font=art.font(art.DISPLAY, 16),
                      fill=PAPER, anchor="ls")
            draw.text((x, y + tile + 38), code, font=art.font(art.MONO, 10),
                      fill=accent, anchor="ls")
    draw.text((left, height - 24),
              "accepted 2026 language · spot field · ink glyph · partner-ink misregistration",
              font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")
    sheet.save(path, "PNG", optimize=True)
    print("wrote", path)


def main():
    a_tiles = [(recipe, render(recipe)) for recipe in DIRECTION_A]
    b_tiles = [(recipe, render(recipe)) for recipe in DIRECTION_B]
    build_contact(DIRECTION_A, "DIRECTION A — BIG MARK", 
                  "DUPLICATE-ROW STICKERS · 3.9.33 STUDY · ONE CUSTOM OBJECT PER ROW · NO TYPE",
                  SHEET_A)
    build_contact(DIRECTION_B, "DIRECTION B — MONOGRAM",
                  "DUPLICATE-ROW STICKERS · 3.9.33 STUDY · ONE CUSTOM LETTERFORM PER ROW",
                  SHEET_B)
    build_preview(a_tiles, b_tiles, PREVIEW)


if __name__ == "__main__":
    main()
