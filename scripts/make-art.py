#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate Rave Player's Kodi artwork — 2026 theme pass.

Concept: "The Last Transmission" (see ../Rave Player/docs/ARTWORK.md), blinged
for a modern streaming app: bright spot-colour sticker tiles with a black ink
glyph, hard misregistration, halftone screens, crop marks and scanlines; plus
1280x720 fanart built from the same language.

Kodi sizes:
    resources/art/<name>.png        256x256   list / folder icons
    resources/art/fanart-*.jpg      1280x720  per-row / per-hub / per-source fanart

The add-on's wordmark identity (icon.png, fanart.jpg) is NOT generated here and
must not be redesigned by a theme pass: those two files are committed as-is.

    python3 scripts/make-art.py                 # icons + fanarts + preview sheet
    python3 scripts/make-art.py --sheet PATH    # extra contact sheet copy

Everything is drawn from code with Pillow (build-time only; Pillow is not a
runtime dependency). Nothing is downloaded or traced from a third party.
"""
from __future__ import annotations

import argparse
import math
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "resources", "art")

# ---------------------------------------------------------------- brand tokens
INK = (7, 7, 11)
INK_2 = (11, 11, 17)
PAPER = (242, 238, 227)
MUTED = (143, 138, 128)
ACID = (232, 255, 0)
MAGENTA = (255, 45, 143)
CYAN = (34, 230, 255)
ORANGE = (255, 106, 26)

FONTDIR = "/System/Library/Fonts/Supplemental"
DISPLAY = os.path.join(FONTDIR, "Impact.ttf")
CONDENSED = os.path.join(FONTDIR, "DIN Condensed Bold.ttf")
MONO = os.path.join(FONTDIR, "Courier New Bold.ttf")

ICON_SIZE = 256
FANART_SIZE = (1280, 720)
SS = 2  # supersample factor


# ---------------------------------------------------------------- primitives
_font_cache = {}


def font(path, size):
    key = (path, size)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(path, size)
        except OSError:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def vertical_gradient(size, top, bottom):
    w, h = (size, size) if isinstance(size, int) else size
    strip = Image.new("RGB", (1, h))
    px = strip.load()
    for y in range(h):
        px[0, y] = mix(top, bottom, y / max(1, h - 1))
    return strip.resize((w, h), Image.BILINEAR)


def halftone(size, colour, spacing=16, radius=2.2, alpha=40, angle=0.0, fade=None):
    w, h = (size, size) if isinstance(size, int) else size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for y in range(0, h + spacing, spacing):
        dx = math.cos(angle) * y * 0.35
        for x in range(0, w + spacing, spacing):
            a = alpha
            if fade is not None:
                a = int(alpha * fade(x / max(1, w - 1)))
            if a <= 0:
                continue
            cx = x + dx
            draw.ellipse([cx - radius, y - radius, cx + radius, y + radius],
                         fill=colour + (a,))
    return layer


def hatch(size, colour, spacing=18, width=2, angle=45, alpha=26):
    w, h = (size, size) if isinstance(size, int) else size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    span = int(math.hypot(w, h))
    for x in range(-span, span, spacing):
        draw.line([(x, -span), (x + span, span)], fill=colour + (alpha,), width=width)
    return layer.rotate(angle, expand=False, resample=Image.BICUBIC)


def scanlines(size, colour=INK, period=6, alpha=16):
    w, h = (size, size) if isinstance(size, int) else size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for y in range(0, h, period):
        draw.line([(0, y), (w, y)], fill=colour + (alpha,))
    return layer


def noise(img, amount=6, seed=11):
    import numpy as np
    rng = np.random.default_rng(seed)
    arr = np.asarray(img.convert("RGB"), np.int16)
    grain = rng.integers(-amount, amount + 1, arr.shape[:2], dtype=np.int16)
    arr = np.clip(arr + grain[:, :, None], 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def crop_marks(draw, size, colour, inset=18, length=26, width=4, alpha=210):
    w, h = (size, size) if isinstance(size, int) else size
    col = colour + (alpha,)
    for (x, y, dx, dy) in ((inset, inset, 1, 1), (w - inset, inset, -1, 1),
                           (inset, h - inset, 1, -1), (w - inset, h - inset, -1, -1)):
        draw.line([(x, y), (x + length * dx, y)], fill=col, width=width)
        draw.line([(x, y), (x, y + length * dy)], fill=col, width=width)


def tracked(draw, xy, text, fnt, fill, tracking=0, anchor="ls"):
    widths = [draw.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + tracking * max(0, len(text) - 1)
    x, y = xy
    if anchor[0] == "m":
        x -= total / 2
    elif anchor[0] == "r":
        x -= total
    for ch, width in zip(text, widths):
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += width + tracking
    return total


def fit_display(draw, text, path, max_width, start, min_size):
    size = start
    while size > min_size and draw.textlength(text, font=font(path, size)) > max_width:
        size -= 4
    return font(path, size)


def fit_tracked(draw, text, path, max_width, start, min_size, tracking):
    size = start
    while size > min_size:
        fnt = font(path, size)
        width = sum(draw.textlength(ch, font=fnt) for ch in text) + tracking * max(0, len(text) - 1)
        if width <= max_width:
            return fnt
        size -= 2
    return font(path, min_size)


# ---------------------------------------------------------------- glyph plates
class Pen:
    """ImageDraw wrapper so glyph painters work on any layer."""

    def __init__(self, image):
        self._image = image
        self._draw = ImageDraw.Draw(image)

    def __getattr__(self, name):
        return getattr(self._draw, name)


def _glyph_smiley(d, accent):
    d.ellipse([104, 112, 408, 416], fill=INK)
    d.ellipse([176, 218, 232, 274], fill=accent)                     # wink eye
    d.polygon([(300, 208), (300, 292), (382, 250)], fill=accent)     # play eye
    d.arc([150, 196, 362, 372], start=18, end=162, fill=accent, width=30)


def _glyph_die(d, accent):
    layer = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    g = ImageDraw.Draw(layer)
    g.rounded_rectangle([126, 126, 386, 386], radius=58, fill=INK)
    for (x, y) in ((192, 192), (320, 192), (256, 256), (192, 320), (320, 320)):
        g.ellipse([x - 22, y - 22, x + 22, y + 22], fill=accent)
    layer = layer.rotate(-13, expand=False, resample=Image.BICUBIC, center=(256, 256))
    d._image.paste(layer, (0, 0), layer)
    for i, yy in enumerate((196, 250, 304)):
        d.line([(52, yy), (108 + i * 10, yy)], fill=INK, width=12)


def _glyph_cassette(d, accent):
    d.rounded_rectangle([72, 148, 440, 372], radius=34, fill=INK)
    d.rounded_rectangle([118, 190, 394, 292], radius=16, fill=accent)
    for cx in (180, 332):
        d.ellipse([cx - 34, 206, cx + 34, 274], fill=INK)
        d.ellipse([cx - 12, 228, cx + 12, 252], fill=accent)
    d.rectangle([128, 312, 384, 340], fill=accent)
    for cx in (112, 400):
        for cy in (176, 344):
            d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=accent)


def _glyph_headphones(d, accent):
    d.arc([96, 96, 416, 416], start=180, end=360, fill=INK, width=34)
    d.rounded_rectangle([82, 236, 178, 388], radius=40, fill=INK)
    d.rounded_rectangle([334, 236, 430, 388], radius=40, fill=INK)
    d.rounded_rectangle([108, 268, 152, 356], radius=18, fill=accent)
    d.rounded_rectangle([360, 268, 404, 356], radius=18, fill=accent)
    d.line([(430, 380), (430, 424), (368, 424)], fill=INK, width=12)


def _glyph_tower(d, accent):
    for y in range(158, 400, 34):
        half = 92 - (y - 150) * 0.28
        d.line([(256 - half, y), (256 + half, y)], fill=INK, width=12)
    d.line([(256, 108), (160, 402)], fill=INK, width=13)
    d.line([(256, 108), (352, 402)], fill=INK, width=13)
    d.line([(256, 96), (256, 402)], fill=INK, width=9)
    for r in (58, 96, 134):
        d.arc([256 - r, 196 - r, 256 + r, 196 + r], start=196, end=344, fill=INK, width=11)
    d.ellipse([240, 86, 272, 118], fill=INK)
    d.rectangle([158, 402, 354, 422], fill=INK)
    d.rectangle([182, 422, 330, 434], fill=INK)


def _glyph_tower_flag(d, accent):
    _glyph_tower(d, accent)
    d.line([(216, 108), (216, 38)], fill=INK, width=10)
    d.polygon([(216, 38), (338, 74), (216, 112)], fill=INK)
    d.polygon([(238, 62), (304, 78), (238, 94)], fill=accent)


def _glyph_gem(d, accent):
    # brilliant-cut silhouette in ink, facet lines knocked out in accent
    d.polygon([(148, 176), (364, 176), (438, 268), (256, 438), (74, 268)], fill=INK)
    for (a, b) in (((148, 176), (364, 176)), ((148, 176), (74, 268)),
                   ((364, 176), (438, 268)), ((74, 268), (438, 268)),
                   ((74, 268), (256, 438)), ((438, 268), (256, 438)),
                   ((148, 176), (256, 438)), ((364, 176), (256, 438)),
                   ((74, 268), (256, 268)), ((438, 268), (256, 268))):
        d.line([a, b], fill=accent, width=7)
    # sparkle
    d.polygon([(120, 108), (136, 140), (168, 156), (136, 172), (120, 204),
               (104, 172), (72, 156), (104, 140)], fill=INK)


def _glyph_heart(d, accent):
    d.ellipse([108, 120, 264, 276], fill=INK)
    d.ellipse([248, 120, 404, 276], fill=INK)
    d.polygon([(108, 214), (404, 214), (256, 424)], fill=INK)
    d.polygon([(256, 208), (256, 350), (344, 279)], fill=accent)


def _glyph_search(d, accent):
    d.ellipse([96, 96, 348, 348], outline=INK, width=36)
    d.ellipse([128, 128, 316, 316], fill=accent)
    d.ellipse([128, 128, 316, 316], outline=INK, width=26)
    d.line([(330, 330), (430, 430)], fill=INK, width=40)


def _glyph_info(d, accent):
    d.ellipse([96, 96, 416, 416], outline=INK, width=30)
    d.ellipse([240, 158, 288, 206], fill=INK)
    d.rectangle([234, 236, 278, 388], fill=INK)


def _glyph_mask(d, accent):
    d.polygon([(256, 86), (410, 170), (382, 330), (256, 442), (130, 330), (102, 170)], fill=INK)
    d.polygon([(154, 208), (246, 208), (222, 274), (154, 252)], fill=accent)
    d.polygon([(358, 208), (266, 208), (290, 274), (358, 252)], fill=accent)
    d.polygon([(256, 160), (292, 208), (256, 236), (220, 208)], fill=accent)
    d.polygon([(190, 318), (322, 318), (256, 408)], fill=accent)
    for x in (206, 256, 306):
        d.line([(x, 318), (x, 356)], fill=INK, width=8)


def _glyph_bolt(d, accent):
    d.polygon([(310, 76), (168, 286), (250, 286), (206, 446), (356, 224), (268, 224)], fill=INK)
    d.polygon([(196, 150), (236, 150), (208, 210), (170, 210)], fill=accent)
    d.line([(330, 150), (396, 150)], fill=accent, width=14)
    d.line([(318, 194), (372, 194)], fill=accent, width=10)


def _glyph_house(d, accent):
    d.polygon([(256, 88), (428, 236), (84, 236)], fill=INK)
    d.rounded_rectangle([118, 236, 394, 412], radius=18, fill=INK)
    d.rounded_rectangle([226, 300, 286, 412], radius=10, fill=accent)
    d.rectangle([150, 268, 196, 314], fill=accent)
    d.rectangle([316, 268, 362, 314], fill=accent)


def _glyph_garage(d, accent):
    d.text((160, 404), "2", font=font(DISPLAY, 340), fill=INK, anchor="ms")
    for i, yy in enumerate((300, 350, 400, 450)):
        x0 = 330 + i * 6
        d.line([(x0, yy), (470, yy)], fill=INK, width=20)
        d.rectangle([x0, yy - 14, x0 + 26, yy + 14], fill=accent)


def _glyph_flag(d, accent):
    d.line([(176, 90), (176, 438)], fill=INK, width=16)
    d.polygon([(176, 100), (404, 160), (176, 232)], fill=INK)
    d.polygon([(216, 140), (330, 166), (216, 198)], fill=accent)
    for r in (60, 96, 132):
        d.arc([176 - r, 268 - r, 176 + r, 268 + r], start=300, end=420, fill=INK, width=12)
    d.rectangle([140, 438, 212, 456], fill=INK)


def _glyph_moxser(d, accent):
    d.text((256, 380), "M", font=font(DISPLAY, 360), fill=INK, anchor="ms")
    for i, hgt in enumerate((64, 112, 152, 104, 56)):
        x = 384 + i * 24
        d.rounded_rectangle([x, 300 - hgt // 2, x + 14, 300 + hgt // 2], radius=5, fill=INK)


def _glyph_hardscore(d, accent):
    d.polygon([(300, 78), (170, 286), (246, 286), (206, 440), (348, 226), (270, 226)], fill=INK)
    d.line([(96, 150), (170, 150)], fill=accent, width=16)
    d.line([(120, 300), (156, 300)], fill=accent, width=12)
    d.line([(100, 226), (150, 226)], fill=accent, width=12)


def _glyph_speaker(d, accent):
    d.rounded_rectangle([104, 128, 300, 384], radius=34, fill=INK)
    d.polygon([(300, 196), (412, 148), (412, 364), (300, 316)], fill=INK)
    d.ellipse([158, 198, 246, 286], fill=accent)
    d.ellipse([188, 228, 216, 256], fill=INK)
    for r in (58, 92):
        d.arc([412 - r, 256 - r, 412 + r, 256 + r], start=300, end=420, fill=INK, width=11)


def _glyph_eq(d, accent):
    d.arc([96, 96, 416, 416], start=180, end=360, fill=INK, width=32)
    d.rounded_rectangle([82, 236, 170, 388], radius=38, fill=INK)
    d.rounded_rectangle([342, 236, 430, 388], radius=38, fill=INK)
    for i, hgt in enumerate((58, 104, 74)):
        x = 206 + i * 40
        d.rectangle([x, 336 - hgt, x + 20, 336], fill=accent)


GLYPHS = {
    "smiley": _glyph_smiley,
    "die": _glyph_die,
    "cassette": _glyph_cassette,
    "headphones": _glyph_headphones,
    "tower": _glyph_tower,
    "tower_flag": _glyph_tower_flag,
    "gem": _glyph_gem,
    "heart": _glyph_heart,
    "search": _glyph_search,
    "info": _glyph_info,
    "mask": _glyph_mask,
    "bolt": _glyph_bolt,
    "house": _glyph_house,
    "garage": _glyph_garage,
    "flag": _glyph_flag,
    "moxser": _glyph_moxser,
    "hardscore": _glyph_hardscore,
    "speaker": _glyph_speaker,
    "eq": _glyph_eq,
}

# ---------------------------------------------------------------- icon recipes
# name, accent, misregistration colour, glyph, sticker code
ICONS = [
    ("rave", ACID, MAGENTA, "smiley", "RP-01"),
    ("surprise", MAGENTA, CYAN, "die", "RP-02"),
    ("tapepacks", CYAN, MAGENTA, "cassette", "RP-03"),
    ("mixes", MAGENTA, CYAN, "headphones", "RP-04"),
    ("radio", CYAN, MAGENTA, "tower", "RP-05"),
    ("curated", ACID, MAGENTA, "gem", "RP-06"),
    ("favourites", MAGENTA, CYAN, "heart", "RP-07"),
    ("search", PAPER, MAGENTA, "search", "RP-08"),
    ("about", PAPER, CYAN, "info", "RP-09"),
    ("jungle", MAGENTA, ACID, "mask", "RP-10"),
    ("hardcore", ORANGE, ACID, "bolt", "RP-11"),
    ("house", CYAN, MAGENTA, "house", "RP-12"),
    ("garage", PAPER, MAGENTA, "garage", "RP-13"),
    ("pirate", ACID, CYAN, "tower_flag", "RP-14"),
    ("djez", MAGENTA, ACID, "eq", "RP-15"),
    ("moxser", ACID, MAGENTA, "moxser", "RP-16"),
    ("hardscore", ORANGE, CYAN, "hardscore", "RP-17"),
    ("getdarker", MAGENTA, CYAN, "speaker", "RP-18"),
    ("pirate-archive", ACID, MAGENTA, "flag", "RP-19"),
]

# ---------------------------------------------------------------- fanart recipes
# name, accent, display word, subline
FANARTS = [
    ("fanart-latest", ACID, "LATEST", "NEW PACKS · SHOWS · RADIO RIPS"),
    ("fanart-surprise", MAGENTA, "SURPRISE", "RANDOM PACK · PRESS PLAY"),
    ("fanart-tapepacks", CYAN, "TAPE PACKS", "1987 → NOW · BY GENRE · YEAR · SERIES"),
    ("fanart-mixes", MAGENTA, "MIXES & SHOWS", "PODCASTS · DNB RADIO · MOXSER · HARDSCORE"),
    ("fanart-live", CYAN, "LIVE RADIO", "KOOL FM · RINSE FM · PIRATE SIGNALS"),
    ("fanart-curated", ACID, "CURATED GEMS", "PIRATE ARCHIVES · RAVE ARCHIVE UK · 2014 LEGACY"),
    ("fanart-favourites", MAGENTA, "FAVOURITES", "SAVED PACKS AND SHOWS"),
    ("fanart-search", PAPER, "SEARCH", "EVERY TAPE PACK ON ARCHIVE.ORG"),
    ("fanart-about", PAPER, "ABOUT & SOURCES", "VERSION · CREDITS · EVERY SOURCE"),
    ("fanart-hub-packs", CYAN, "TAPE PACKS", "BY GENRE · BY YEAR · SERIES · RAVE · VENUE"),
    ("fanart-hub-shows", MAGENTA, "MIXES & SHOWS", "EVERY STREAMING SOURCE · ONE HUB"),
    ("fanart-hub-live", CYAN, "LIVE RADIO", "ON AIR NOW · KOOL · RINSE · GENRE TAGS"),
    ("fanart-hub-curated", ACID, "CURATED GEMS", "HAND-PICKED RECORDINGS · LEGACY ARCHIVES"),
    ("fanart-moxser", ACID, "MOXSER", "DANCE MUSIC MIX ARCHIVE · DIRECT MP3"),
    ("fanart-hardscore", ORANGE, "HARDSCORE", "OLD SKOOL HARDCORE / JUNGLE SETS"),
    ("fanart-getdarker", MAGENTA, "GETDARKER", "DUBSTEP · GRIME · SETS AND MIXCLOUD"),
    ("fanart-pirate-archive", ACID, "PIRATE ARCHIVES", "RISK FM · WEEKEND RUSH · FLAVA FM"),
]


# ---------------------------------------------------------------- builders
def build_icon(accent, shadow, glyph, code, size=ICON_SIZE):
    px = size * SS
    tile = vertical_gradient(px, mix(accent, PAPER, 0.05), mix(accent, INK, 0.14)).convert("RGBA")
    tile = Image.alpha_composite(tile, halftone(px, mix(accent, INK, 0.45),
                                               spacing=7 * SS, radius=1.15 * SS, alpha=30))
    tile = Image.alpha_composite(tile, hatch(px, INK, spacing=26 * SS, width=1 * SS, alpha=10))

    # misregistered second plate: glyph alpha shifted up-left in a signal colour
    shadow_layer = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    GLYPHS[glyph](Pen(shadow_layer), accent)
    colour_layer = Image.new("RGBA", (px, px), shadow + (0,))
    colour_layer.putalpha(shadow_layer.getchannel("A"))
    colour_layer = colour_layer.transform(
        (px, px), Image.AFFINE, (1, 0, -5 * SS, 0, 1, -5 * SS), resample=Image.NEAREST)
    tile = Image.alpha_composite(tile, colour_layer)

    ink_layer = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    GLYPHS[glyph](Pen(ink_layer), accent)
    tile = Image.alpha_composite(tile, ink_layer)

    draw = ImageDraw.Draw(tile)
    draw.rectangle([0, 0, px - 1, px - 1], outline=INK + (255,), width=2 * SS)
    draw.rectangle([5 * SS, 5 * SS, px - 5 * SS, px - 5 * SS],
                   outline=INK + (70,), width=1 * SS)
    crop_marks(draw, (px, px), INK, inset=14 * SS, length=22 * SS, width=3 * SS, alpha=190)
    draw.text((16 * SS, px - 14 * SS), code, font=font(MONO, 20 * SS),
              fill=INK + (150,), anchor="ls")
    for i, hgt in enumerate((10, 18, 26)):
        x = px - (44 + i * 12) * SS
        draw.rectangle([x, px - (14 + hgt // 2) * SS, x + 7 * SS,
                        px - (14 - hgt // 2) * SS], fill=INK + (200,))
    tile = Image.alpha_composite(tile, scanlines((px, px), INK, period=7 * SS, alpha=12))
    return tile.resize((size, size), Image.LANCZOS).convert("RGB")


FANART_GLYPHS = {
    "latest": "smiley", "surprise": "die", "tapepacks": "cassette",
    "mixes": "headphones", "live": "tower", "curated": "gem",
    "favourites": "heart", "search": "search", "about": "info",
    "hub-packs": "cassette", "hub-shows": "headphones",
    "hub-live": "tower", "hub-curated": "gem",
    "moxser": "moxser", "hardscore": "hardscore",
    "getdarker": "speaker", "pirate-archive": "flag",
}


def _glyph_silhouette(glyph, colour, alpha, scale, rotate=0):
    layer = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    GLYPHS[glyph](Pen(layer), colour)
    mask = layer.getchannel("A")
    plate = Image.new("RGBA", (512, 512), colour + (0,))
    plate.putalpha(mask.point(lambda v: int(v * alpha / 255)))
    plate = plate.resize((scale, scale), Image.LANCZOS)
    if rotate:
        plate = plate.rotate(rotate, expand=True, resample=Image.BICUBIC)
    return plate


def build_fanart(accent, word, subline, index, name="", size=FANART_SIZE):
    w, h = size[0] * SS, size[1] * SS
    img = vertical_gradient((w, h), mix(INK, accent, 0.05), INK).convert("RGBA")
    img = Image.alpha_composite(
        img, halftone((w, h), accent, spacing=15 * SS, radius=2.0 * SS, alpha=30,
                      fade=lambda t: max(0.0, (t - 0.28) / 0.72)))

    sun = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sun)
    cx, cy = int(w * 0.80), int(h * 0.40)
    for r in range(int(h * 0.50), 0, -6 * SS):
        a = int(40 * (1 - r / (h * 0.50)) ** 1.5)
        if a:
            sd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent + (a,))
    img = Image.alpha_composite(img, sun)

    # oversized glyph silhouette as watermark on the artwork side
    slug = os.path.basename(name).replace("fanart-", "")
    glyph_name = FANART_GLYPHS.get(slug)
    if glyph_name:
        mark = _glyph_silhouette(glyph_name, accent, 46, scale=int(h * 0.60))
        img.alpha_composite(mark, (int(w * 0.66), -int(h * 0.06)))

    band = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for y in range(-int(h * 0.3), h, 46 * SS):
        bd.polygon([(0, y), (26 * SS, y), (0, y + 26 * SS)], fill=accent + (60,))
    img = Image.alpha_composite(img, band)

    draw = ImageDraw.Draw(img)
    left = int(w * 0.50)
    max_width = w - left - 50 * SS
    disp = fit_display(draw, word, DISPLAY, max_width, 150 * SS, 66 * SS)
    ty = int(h * 0.43)
    draw.text((left + 12 * SS, ty + 12 * SS), word, font=disp, fill=accent + (235,), anchor="ls")
    draw.text((left, ty), word, font=disp, fill=PAPER, anchor="ls")
    sub_track = 2 * SS
    sub_font = fit_tracked(draw, subline, MONO, max_width, 30 * SS, 16 * SS, sub_track)
    sub_y = ty + 96 * SS
    tracked(draw, (left + 2 * SS, sub_y), subline, sub_font,
            mix(PAPER, accent, 0.25) + (235,), tracking=sub_track, anchor="ls")
    sb = sub_font.getbbox(subline)
    rule_y = sub_y + sb[3] + 6 * SS
    draw.rectangle([left, rule_y, left + max_width * 0.55, rule_y + 4 * SS],
                   fill=accent + (200,))

    draw.text((34 * SS, h - 34 * SS), "RP · THEME 2026", font=font(MONO, 18 * SS),
              fill=MUTED + (200,), anchor="ls")
    draw.text((left, h - 34 * SS), "%02d" % index, font=font(DISPLAY, 34 * SS),
              fill=accent + (220,), anchor="ls")

    crop_marks(draw, (w, h), MUTED, inset=26 * SS, length=30 * SS, width=3 * SS, alpha=120)
    img = Image.alpha_composite(img, scanlines((w, h), INK, period=6 * SS, alpha=18))
    img = Image.alpha_composite(img, hatch((w, h), INK, spacing=30 * SS, width=1 * SS, alpha=8))
    return noise(img.convert("RGB"), amount=4, seed=index + 7).resize(size, Image.LANCZOS)


def make_contact_sheet(path, icon_paths):
    cols, cell = 5, 220
    rows = math.ceil(len(icon_paths) / cols)
    sheet = Image.new("RGB", (cols * cell, rows * cell + 44), INK)
    draw = ImageDraw.Draw(sheet)
    for index, icon_path in enumerate(icon_paths):
        icon = Image.open(icon_path).convert("RGB").resize((cell - 20, cell - 20), Image.LANCZOS)
        x = (index % cols) * cell + 10
        y = (index // cols) * cell + 10
        sheet.paste(icon, (x, y))
    draw.text((14, rows * cell + 12), "RAVE PLAYER · KODI THEME 2026 · ICONS",
              font=font(DISPLAY, 24), fill=ACID)
    sheet.save(path, "JPEG", quality=90)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default=os.path.join(ART, "preview.jpg"))
    args = ap.parse_args()
    os.makedirs(ART, exist_ok=True)

    icon_paths = []
    for name, accent, shadow, glyph, code in ICONS:
        path = os.path.join(ART, name + ".png")
        build_icon(accent, shadow, glyph, code).save(path, "PNG", optimize=True)
        icon_paths.append(path)

    for index, (name, accent, word, subline) in enumerate(FANARTS, start=1):
        path = os.path.join(ART, name + ".jpg")
        build_fanart(accent, word, subline, index, name).save(path, "JPEG", quality=92, optimize=True)

    make_contact_sheet(args.sheet, icon_paths)
    print("wrote %d icons + %d fanarts to %s" % (len(ICONS), len(FANARTS), ART))


if __name__ == "__main__":
    main()
