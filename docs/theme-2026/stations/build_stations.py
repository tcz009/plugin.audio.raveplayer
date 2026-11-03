#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Station-inspired Live Radio tiles for Rave Player — ART STUDY ONLY.

Ten original, code-drawn station stickers for the Live Radio rows:

    Kool FM · Rinse FM · Oldskool & Rave · Jungle · Drum & Bass ·
    Hardcore · House · UK Garage · Breakbeat · Pirate Stations

The owner's brief: the stations' identities should "blend in" with the accepted
2026 sticker language, but these are *evocations*, not copies. Kool FM gets the
acid smiley / melted grin and a KOOL code texture; Rinse FM gets broken ripple
rings and a rinse wave, with no wordmark. The genre rows get one distinct
trippy/rave motif each, not a shared transmitter or a template.

Family grammar (coordinated with the in-progress Direction C trippy study):
wobbled hand-drawn ink, melt drips, two chromatic misregistration plates,
halftone sun, scanlines, grain, crop marks, code, signal bars. Station tiles
are deliberately a little bolder than Direction C: one large hero silhouette,
0–3 drips instead of 4, and a quieter field so the mark reads at 64 px. The
wobble/melt/warp primitives follow that study; this file is self-contained so
the station sheet stays reproducible if the study folder moves.

This script writes ONLY inside this folder. It does not touch resources/art/,
static/art/, routes.py, the tests, preview.jpg, git, or any deployed asset.

    python3 build_stations.py

Requires Pillow + numpy (build-time only). Palette/fonts are read from
../../../scripts/make-art.py so the family tokens stay identical.
"""
from __future__ import annotations

import importlib.util
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
ART = os.path.join(ROOT, "resources", "art")

CONTACT = os.path.join(HERE, "contact-sheet.png")
BOARD = os.path.join(HERE, "stations-1to1.png")
ROWS = os.path.join(HERE, "stations-64px-rows.png")
SAMPLES = os.path.join(HERE, "samples")

S = 512          # design space (the accepted glyph grid is 512)
SS = 2           # render scale -> 1024, then downsample to 256
PX = S * SS
OUT = 256


# ---------------------------------------------------------------- family tokens
def _load_make_art():
    path = os.path.join(ROOT, "scripts", "make-art.py")
    spec = importlib.util.spec_from_file_location("rave_make_art", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


art = _load_make_art()
INK = art.INK
INK_2 = art.INK_2
PAPER = art.PAPER
MUTED = art.MUTED
ACID = art.ACID
MAGENTA = art.MAGENTA
CYAN = art.CYAN
ORANGE = art.ORANGE

mix = art.mix
DEEP_TEAL = mix(CYAN, INK, 0.58)
PALE_CYAN = mix(CYAN, PAPER, 0.56)
PINK = mix(MAGENTA, PAPER, 0.38)


def rgba(c, a=255):
    return (c[0], c[1], c[2], int(a))


# ---------------------------------------------------------------- geometry
def resample(pts, step=6.0, closed=False):
    """Densify a polyline so a wobble can be applied along its length."""
    if closed:
        pts = list(pts) + [pts[0]]
    out = []
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        d = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(d / step))
        for j in range(n):
            t = j / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    out.append(pts[-1])
    if closed:
        out.pop()
    return out


def wobble(pts, amp=3.0, freq=2.0, phase=0.0, closed=False, seed=0):
    """Displace a dense path along its normal with two smooth sine bands."""
    if amp <= 0:
        return pts
    pts = resample(pts, 5.0, closed)
    n = len(pts)
    if n < 3:
        return pts
    lens = [0.0]
    for i in range(1, n):
        lens.append(lens[-1] + math.hypot(pts[i][0] - pts[i - 1][0],
                                          pts[i][1] - pts[i - 1][1]))
    total = lens[-1] or 1.0
    f1 = round(freq) if closed else freq
    f2 = round(freq * 2.37) if closed else freq * 2.37
    out = []
    for i, (x, y) in enumerate(pts):
        t = lens[i] / total
        p = (i - 1) % n
        q = (i + 1) % n
        tx, ty = pts[q][0] - pts[p][0], pts[q][1] - pts[p][1]
        tl = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / tl, tx / tl
        off = (amp * math.sin(2 * math.pi * (f1 * t + phase))
               + amp * 0.45 * math.sin(2 * math.pi * (f2 * t + phase * 1.7 + seed)))
        out.append((x + nx * off, y + ny * off))
    return out


def circle_path(cx, cy, r, n=160, rwob=0.0, lobes=3, phase=0.0, squash=1.0):
    """A wobbly circle in 512 design space."""
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r + rwob * math.sin(lobes * a + phase) + rwob * 0.45 * math.sin(
            2 * lobes * a + phase * 1.6)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a) * squash))
    return pts


def rrect_pts(box, radius, step=7.0):
    x0, y0, x1, y1 = box
    r = min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
    pts = []
    for (cx, cy, a0) in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0),
                         (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(9):
            a = math.radians(a0 + 90 * k / 8)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return resample(pts, step)


# ---------------------------------------------------------------- pen
class Pen:
    """Draws in 512 design space onto an oversized RGBA canvas."""

    def __init__(self, img):
        self.img = img
        self.d = ImageDraw.Draw(img)

    @staticmethod
    def _p(point):
        return (point[0] * SS, point[1] * SS)

    @staticmethod
    def _w(width):
        return max(1, int(round(width * SS)))

    def fill(self, pts, colour, wob=0.0, freq=2.0, phase=0.0, closed=True, seed=0):
        pts = wobble(pts, wob, freq, phase, closed=closed, seed=seed) if wob else pts
        self.d.polygon([self._p(p) for p in pts], fill=colour)

    def blob(self, cx, cy, r, colour, wob=2.2, lobes=3, phase=0.0, squash=1.0):
        pts = circle_path(cx, cy, r, 160, rwob=wob, lobes=lobes,
                          phase=phase, squash=squash)
        self.d.polygon([self._p(p) for p in pts], fill=colour)

    def rect(self, box, colour, radius=0, wob=2.0, phase=0.0):
        if radius:
            pts = rrect_pts(box, radius)
        else:
            x0, y0, x1, y1 = box
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        self.fill(pts, colour, wob=wob, phase=phase)

    def line(self, pts, width, colour, wob=1.6, taper=None, closed=False):
        dense = wobble(pts, wob, 3.0, 0.0, closed=closed)
        n = len(dense)
        for i in range(n - 1):
            t = i / max(1, n - 2)
            w = width * (taper(t) if taper else 1.0)
            self.d.line([self._p(dense[i]), self._p(dense[i + 1])],
                        fill=colour, width=self._w(w))
        for i in (0, n - 1):
            t = 0.0 if i == 0 else 1.0
            w = width * (taper(t) if taper else 1.0)
            r = w * SS / 2
            x, y = self._p(dense[i])
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=colour)

    def disc(self, cx, cy, r, colour):
        r = r * SS
        x, y = cx * SS, cy * SS
        self.d.ellipse([x - r, y - r, x + r, y + r], fill=colour)

    def star(self, cx, cy, r, colour, points=4, inner=0.34, wob=0.0):
        pts = []
        for i in range(points * 2):
            rr = r if i % 2 == 0 else r * inner
            a = -math.pi / 2 + i * math.pi / points
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        self.fill(pts, colour, wob=wob, closed=True)

    # erasers — used to knock holes through a drawn mark
    def erase_ellipse(self, cx, cy, rx, ry):
        self.d.ellipse([(cx - rx) * SS, (cy - ry) * SS,
                        (cx + rx) * SS, (cy + ry) * SS], fill=(0, 0, 0, 0))

    def erase_rect(self, box):
        x0, y0, x1, y1 = box
        self.d.rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=(0, 0, 0, 0))

    def erase_poly(self, pts):
        self.d.polygon([self._p(p) for p in pts], fill=(0, 0, 0, 0))


# ---------------------------------------------------------------- face parts
def grin(p, cx, cy, rx, ry, thickness, colour, tilt=0.0, step=26):
    pts = []
    for i in range(step + 1):
        a = math.radians(28 + (124 * i / step))
        x = cx + rx * math.cos(a)
        y = cy + ry * math.sin(a) + tilt
        pts.append((x, y))
    p.line(pts, thickness, colour, wob=1.4,
           taper=lambda t: 0.55 + 0.75 * math.sin(math.pi * t))


def almond(p, cx, cy, w, h, colour):
    top, bot = [], []
    for i in range(25):
        t = i / 24
        x = cx - w / 2 + w * t
        top.append((x, cy - h * math.sin(math.pi * t)))
        bot.append((x, cy + h * math.sin(math.pi * t)))
    p.fill(top + bot[::-1], colour, wob=1.0, closed=True)


def spiral_pts(cx, cy, r0, r1, turns, n=90, phase=0.0):
    pts = []
    for i in range(n + 1):
        t = i / n
        a = 2 * math.pi * turns * t + phase
        r = r0 + (r1 - r0) * t
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def ring(p, cx, cy, r, width, colour, a0=0, a1=360, wob=1.4, phase=0.0,
         taper=None):
    n = max(12, int(abs(a1 - a0) / 4))
    pts = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    p.line(pts, width, colour, wob=wob, taper=taper)


def jagged_arc(cx, cy, r, a0, a1, zig=8, n=16):
    pts = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        rr = r + (zig if i % 2 else -zig)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def squiggle(points, amp, waves, colour, width, phase=0.0):
    dense = resample(points, 5.0)
    lens = [0.0]
    for i in range(1, len(dense)):
        lens.append(lens[-1] + math.hypot(dense[i][0] - dense[i - 1][0],
                                          dense[i][1] - dense[i - 1][1]))
    total = lens[-1] or 1.0
    out = []
    for i, (x, y) in enumerate(dense):
        t = lens[i] / total
        p = max(0, i - 1)
        q = min(len(dense) - 1, i + 1)
        tx, ty = dense[q][0] - dense[p][0], dense[q][1] - dense[p][1]
        tl = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / tl, tx / tl
        off = amp * math.sin(2 * math.pi * waves * t + phase)
        out.append((x + nx * off, y + ny * off))
    return out


def draw_squiggle(p, points, amp, waves, colour, width, phase=0.0):
    p.line(squiggle(points, amp, waves, colour, width, phase=phase), width,
           colour, wob=0.8, taper=lambda t: 0.8 + 0.4 * math.sin(math.pi * t))


# ---------------------------------------------------------------- melt
def bottom_profile(layer):
    a = np.asarray(layer.getchannel("A"))
    h = a.shape[0]
    ink = a > 96
    ybot = np.where(ink.any(0), h - 1 - np.argmax(ink[::-1], axis=0), -1)
    return ybot


def add_melt(layer, colour, count=3, seed=0, max_len=60.0, min_len=28.0,
             x0=60, x1=452, ycap=438):
    """Gravity pass: hang a few drips off the bottom silhouette."""
    if count <= 0:
        return layer
    rnd = random.Random(seed)
    ybot = bottom_profile(layer)
    ok = [(x, int(ybot[x])) for x in range(int(x0 * SS), int(x1 * SS), 2)
          if ybot[x] > 0 and ybot[x] < ycap * SS]
    if not ok:
        return layer
    lows = []
    for i, (x, y) in enumerate(ok):
        window = [yy for _xx, yy in ok[max(0, i - 9):i + 10]]
        if y >= max(window) - 2:
            lows.append((x, y))
    pool = lows or ok
    rnd.shuffle(pool)
    chosen = []
    for x, y in pool:
        if all(abs(x - cx) > 34 * SS for cx, _cy in chosen):
            chosen.append((x, y))
        if len(chosen) >= count:
            break

    p = Pen(layer)
    for (x, y) in chosen:
        length = rnd.uniform(min_len, max_len)
        top = y / SS
        tipy = min(ycap, top + length)
        drift = rnd.uniform(-10, 10)
        neck = rnd.uniform(9, 15)
        bulb = rnd.uniform(9, 15)
        pts = [(x / SS, top - 6),
               (x / SS + drift * 0.25, top + length * 0.45),
               (x / SS + drift * 0.7, tipy - bulb * 0.6)]
        p.line(pts, neck * 1.6, colour, wob=1.2,
               taper=lambda t: 1.0 - 0.45 * t)
        p.blob(x / SS + drift * 0.7, tipy - bulb * 0.4, bulb * 0.82, colour,
               wob=1.6, lobes=3, phase=rnd.uniform(0, 6))
    return layer


def puddle(p, cx, cy, rx, ry, colour, seed=0):
    rnd = random.Random(seed)
    pts = circle_path(cx, cy, rx, 140, rwob=ry * 0.35, lobes=4,
                      phase=rnd.uniform(0, 6), squash=ry / max(1.0, rx))
    p.fill(pts, colour, wob=0.8, closed=True)


# ---------------------------------------------------------------- texture
def warp(img, amp=9.0, freq=1.5, phase=0.0, amp2=3.4, freq2=2.6, phase2=0.0,
         sag=0.0):
    """Sine displacement: the whole mark sags and leans like wet ink."""
    a = np.asarray(img)
    h, w = a.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    nx, ny = xs / w, ys / h
    A, A2 = amp * SS, amp2 * SS
    dx = A * np.sin(2 * math.pi * (freq * ny + phase)) + A2 * np.sin(
        2 * math.pi * (freq2 * nx - phase2))
    dy = 0.55 * A * np.sin(2 * math.pi * (freq * 0.85 * nx + phase * 1.4)) + \
        0.5 * A2 * np.sin(2 * math.pi * (freq2 * ny + phase2 * 0.7))
    dy = dy + sag * SS * (ny ** 3)
    sx = np.clip(xs + dx, 0, w - 1).astype(np.int32)
    sy = np.clip(ys + dy, 0, h - 1).astype(np.int32)
    return Image.fromarray(a[sy, sx], "RGBA")


def halftone(colour, spacing=14.0, radius=2.0, alpha=44, seed=1, sun=None,
             jitter=1.6):
    """Dot screen. With `sun` the dots swell towards a focal point."""
    layer = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rnd = random.Random(seed)
    step = spacing * SS
    for y in range(0, PX + int(step), int(step)):
        for x in range(0, PX + int(step), int(step)):
            cx = x + rnd.uniform(-jitter, jitter) * SS
            cy = y + rnd.uniform(-jitter, jitter) * SS
            r = radius
            a = alpha
            if sun is not None:
                sxc, syc, srad = sun
                dist = math.hypot(cx - sxc * SS, cy - syc * SS) / (srad * SS)
                if dist > 1.0:
                    continue
                r = radius * (0.25 + 2.6 * (1.0 - dist) ** 1.5)
                a = int(alpha * (0.35 + 0.9 * (1.0 - dist)))
            rr = r * SS
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=rgba(colour, a))
    return layer


def scanlines(colour=INK, period=14, alpha=15):
    layer = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(0, PX, period * SS):
        d.line([(0, y), (PX, y)], fill=rgba(colour, alpha), width=SS)
    return layer


def grain(img, amount=7, seed=3):
    rng = np.random.default_rng(seed)
    arr = np.asarray(img.convert("RGB"), np.int16)
    g = rng.integers(-amount, amount + 1, arr.shape[:2], dtype=np.int16)
    g = np.repeat(np.repeat(g, 2, axis=0), 2, axis=1)[:arr.shape[0], :arr.shape[1]]
    arr = np.clip(arr + g[:, :, None], 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def warp_alpha(layer, colour, **kw):
    plate = Image.new("RGBA", (PX, PX), rgba(colour, 255))
    plate.putalpha(layer.getchannel("A"))
    return warp(plate, **kw)


def shift(img, dx, dy):
    if dx == 0 and dy == 0:
        return img
    return img.transform(img.size, Image.AFFINE,
                         (1, 0, -dx * SS, 0, 1, -dy * SS), resample=Image.BICUBIC)


def split_shift(layer, dx, dy, split_x=250):
    """Offset the right half of a mark, as if the print broke at the seam."""
    left = layer.copy()
    right = layer.copy()
    ml = Image.new("L", (PX, PX), 0)
    mr = Image.new("L", (PX, PX), 0)
    ImageDraw.Draw(ml).rectangle([0, 0, int(split_x * SS), PX], fill=255)
    ImageDraw.Draw(mr).rectangle([int(split_x * SS), 0, PX, PX], fill=255)
    left.putalpha(Image.composite(left.getchannel("A"),
                                  Image.new("L", (PX, PX), 0), ml))
    right.putalpha(Image.composite(right.getchannel("A"),
                                   Image.new("L", (PX, PX), 0), mr))
    out = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    out.alpha_composite(left)
    out.alpha_composite(shift(right, dx, dy))
    return out


def microtext(base, text, x0, y0, x1, y1, size=10, alpha=120, colour=INK,
              gap=3.0):
    """A sticker-code texture: tiny repeated type, readable only up close."""
    d = ImageDraw.Draw(base)
    f = art.font(art.MONO, size * SS)
    word = text + "  "
    word_w = d.textlength(word, font=f) / SS
    y = y0 + size
    while y <= y1:
        x = x0
        while x + word_w <= x1:
            d.text((x * SS, y * SS), word, font=f, fill=rgba(colour, alpha),
                   anchor="ls")
            x += word_w + gap
        y += size + 4
    return base


# ---------------------------------------------------------------- glyphs
def g_kool(p, field):
    """Melted acid smiley: X eye, spiral eye, dripped grin, KOOL code."""
    # magenta sticker rim behind the ink face
    p.disc(256, 222, 168, MAGENTA)
    p.blob(256, 220, 150, INK, wob=5.5, lobes=3, phase=0.4, squash=1.02)

    # left eye: an X; right eye: a spiral. Two trippy states, one face.
    for a, b in (((186, 176), (228, 218)), ((228, 176), (186, 218))):
        p.line([a, b], 17, ACID, wob=1.0,
               taper=lambda t: 0.8 + 0.3 * math.sin(math.pi * t))
    sp = spiral_pts(322, 196, 7, 37, 1.8, 70, phase=-0.4)
    p.line(sp, 13, ACID, wob=0.8, taper=lambda t: 0.7 + 0.5 * t)

    # wide grin, sagging in the middle
    pts = []
    for i in range(31):
        t = i / 30
        pts.append((168 + 176 * t, 292 + 44 * math.sin(math.pi * t)))
    p.line(pts, 31, ACID, wob=1.2,
           taper=lambda t: 0.55 + 0.8 * math.sin(math.pi * t))
    # teeth knocked back out of the grin
    for x in (214, 250, 286):
        p.rect((x, 292, x + 15, 318), INK, radius=4, wob=1.0)

    # magenta drips off the grin, and two sparkles
    for x0, y0, ln, dr in ((256, 320, 42, 4), (208, 318, 26, -3), (304, 318, 22, 3)):
        p.line([(x0, y0), (x0 + dr, y0 + ln)], 18, MAGENTA, wob=1.0,
               taper=lambda t: 1.0 - 0.4 * t)
        p.disc(x0 + dr, y0 + ln + 4, 11, MAGENTA)
    p.star(88, 116, 20, MAGENTA, wob=1.0)
    p.star(426, 350, 14, MAGENTA, wob=0.8)


def g_rinse(p, field):
    """Three ripple rings cut by one clean rinse wave; cyan + ink, no type."""
    for r, w in ((150, 36), (104, 25), (58, 20)):
        p.line(circle_path(250, 245, r, 160, 2.6, 3, 0.4), w, INK, wob=1.6)

    # the wave is a clear channel through the rings, not a drawn stripe
    wave = [(58, 380), (130, 350), (200, 310), (250, 250),
            (300, 190), (370, 150), (454, 104)]
    p.line(wave, 34, (0, 0, 0, 0), wob=2.6,
           taper=lambda t: 0.8 + 0.35 * math.sin(math.pi * t))

    # droplet at the eye of the rinse
    p.blob(250, 245, 38, INK, wob=2.2, lobes=3, phase=0.3)
    sp = spiral_pts(250, 245, 4, 27, 1.7, 55)
    p.line(sp, 7, CYAN, wob=0.8)
    p.disc(242, 236, 5, CYAN)


def g_oldskool(p, field):
    """A melting clock face on an acid rave starburst, sagging into a puddle."""
    cx, cy = 256, 228
    for i in range(10):
        a = -math.pi / 2 + i * 2 * math.pi / 10
        half = 0.075
        tip = 190 if i % 2 == 0 else 174
        pts = [(cx + 100 * math.cos(a - half), cy + 100 * math.sin(a - half)),
               (cx + tip * math.cos(a), cy + tip * math.sin(a)),
               (cx + 100 * math.cos(a + half), cy + 100 * math.sin(a + half))]
        p.fill(pts, ACID, wob=1.4, closed=True)

    # melted base: the face sags into a puddle
    puddle(p, 256, 392, 104, 18, INK, seed=4)
    p.rect((218, 344, 294, 402), INK, radius=22, wob=2.4)
    p.blob(cx, cy, 132, INK, wob=5.0, lobes=3, phase=0.3, squash=1.02)

    # four heavy ticks
    for a in (-90, 0, 90, 180):
        aa = math.radians(a)
        p.line([(cx + 94 * math.cos(aa), cy + 94 * math.sin(aa)),
                (cx + 119 * math.cos(aa), cy + 119 * math.sin(aa))],
               14, ACID, wob=0.8)

    # hands at ten-to-two, plus a squiggly seconds hand
    p.line([(cx, cy), (cx + 66 * math.cos(math.radians(210)),
                        cy + 66 * math.sin(math.radians(210)))],
           18, ACID, wob=1.0, taper=lambda t: 0.65 + 0.5 * math.sin(math.pi * t))
    p.line([(cx, cy), (cx + 100 * math.cos(math.radians(330)),
                        cy + 100 * math.sin(math.radians(330)))],
           16, ACID, wob=1.0, taper=lambda t: 0.65 + 0.5 * math.sin(math.pi * t))
    draw_squiggle(p, [(cx, cy), (cx + 30, cy + 62), (cx + 76, cy + 50)],
                  5, 2.0, ACID, 7)
    p.disc(cx, cy, 13, ACID)
    p.disc(cx, cy, 5, INK)

    p.star(90, 110, 18, ACID, wob=1.0)
    p.star(424, 372, 13, ACID, wob=0.8)


def g_jungle(p, field):
    """A fiddlehead fern curled around an eye: botanical jungle, not a mask."""
    pts = spiral_pts(250, 246, 148, 24, 1.3, 120, phase=-0.7)

    # broad leaves sit behind the coil, so the spiral reads on top
    leaves = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    lp = Pen(leaves)
    for t in (0.12, 0.30, 0.48, 0.66):
        i = int(t * (len(pts) - 1))
        x, y = pts[i]
        dx, dy = x - 250, y - 246
        l = math.hypot(dx, dy) or 1
        nx, ny = dx / l, dy / l
        tx, ty = -ny, nx
        base = 60
        b1 = (x - tx * base / 2, y - ty * base / 2)
        b2 = (x + tx * base / 2, y + ty * base / 2)
        mid = (x + nx * 44, y + ny * 44)
        s1 = (mid[0] + tx * 30, mid[1] + ty * 30)
        s2 = (mid[0] - tx * 30, mid[1] - ty * 30)
        tip = (x + nx * 94 + tx * 8, y + ny * 94 + ty * 8)
        lp.fill([b1, s1, tip, s2, b2], INK, wob=1.6, closed=True)
        lp.line([(x, y), tip], 4, ACID, wob=0.8)
    p.img.alpha_composite(leaves)

    p.line(pts, 38, INK, wob=1.8, taper=lambda t: 1.0 - 0.4 * t)

    # the eye at the heart of the curl
    almond(p, 250, 246, 80, 46, ACID)
    p.erase_ellipse(250, 246, 17, 24)
    p.disc(242, 238, 6, ACID)

    # spores
    for (x, y, r) in ((92, 120, 9), (420, 170, 7), (390, 382, 8)):
        p.blob(x, y, r, INK, wob=1.2, lobes=3, phase=0.4)
    p.star(410, 330, 13, INK, wob=0.8)


def g_dnb(p, field):
    """A snare drum over a sub-bass wave: the two halves of drum & bass."""
    # crossed sticks behind the shell
    for (x0, y0, x1, y1) in ((88, 120, 424, 326), (424, 120, 88, 326)):
        p.line([(x0, y0), (x1, y1)], 14, INK, wob=1.6,
               taper=lambda t: 0.8 + 0.35 * math.sin(math.pi * t))
        p.disc(x1, y1, 12, ACID)

    # shell + bottom head
    p.rect((126, 190, 386, 344), INK, radius=30, wob=2.4)
    p.blob(256, 344, 130, INK, wob=2.0, lobes=2, phase=0.3, squash=0.26)

    # top head: acid skin with ink snare wires
    p.blob(256, 190, 122, INK, wob=2.0, lobes=3, phase=0.2, squash=0.40)
    p.blob(256, 190, 104, ACID, wob=1.8, lobes=3, phase=0.2, squash=0.38)
    for dy in (-8, 0, 8):
        p.line([(180, 190 + dy), (332, 190 + dy)], 4, INK, wob=0.6)

    # lugs + tension rods + bottom rim
    for x in (150, 210, 302, 362):
        p.rect((x - 7, 232, x + 7, 268), ACID, radius=4, wob=0.8)
        p.line([(x, 190), (x, 232)], 5, ACID, wob=0.5)
    p.line([(150, 338), (362, 338)], 8, ACID, wob=0.8)

    # sub-bass wave: a clean two-cycle sine, wide enough to read at 64 px
    wave = []
    for i in range(61):
        t = i / 60
        wave.append((76 + 364 * t, 412 - 20 * math.sin(2 * math.pi * 2.0 * t)))
    p.line(wave, 16, ACID, wob=1.0,
           taper=lambda t: 0.8 + 0.3 * math.sin(math.pi * t))


def g_hardcore(p, field):
    """A circular siren beacon: radial grille, lightning bolt, jagged air."""
    cx, cy = 250, 238

    # one jagged pressure ring, broken left/right so it reads as sound not sun
    p.line(jagged_arc(cx, cy, 192, -150, -30, zig=12, n=14),
           11, INK, wob=1.0)
    p.line(jagged_arc(cx, cy, 192, 30, 150, zig=12, n=14),
           11, INK, wob=1.0)

    p.blob(cx, cy, 142, INK, wob=4.0, lobes=3, phase=0.2)

    # radial grille slots
    for a in (0, 45, 90, 135, 180, 225, 270, 315):
        if a in (90, 270):
            continue
        aa = math.radians(a)
        p.line([(cx + 68 * math.cos(aa), cy + 68 * math.sin(aa)),
                (cx + 120 * math.cos(aa), cy + 120 * math.sin(aa))],
               16, ACID, wob=0.8)

    # the bolt is the one hero detail
    bolt = [(274, 64), (206, 214), (248, 214), (216, 330),
            (318, 176), (268, 176), (306, 64)]
    p.fill(bolt, ACID, wob=1.0, closed=True)

    # base, with hazard ticks
    p.rect((190, 382, 310, 414), INK, radius=16, wob=1.8)
    for x in (214, 242, 270, 298):
        p.line([(x, 386), (x, 406)], 5, ACID, wob=0.5)


def g_house(p, field):
    """Four kick drums + a clap star: four-on-the-floor, not a house icon."""
    for (cx, cy) in ((176, 176), (336, 176), (176, 336), (336, 336)):
        p.blob(cx, cy, 72, INK, wob=2.4, lobes=3, phase=0.3)
        p.disc(cx, cy, 22, ACID)
        ring(p, cx, cy, 50, 9, ACID, a0=0, a1=360, wob=0.8)

    p.star(256, 256, 44, ACID, points=4, inner=0.35, wob=1.5)
    draw_squiggle(p, [(232, 426), (272, 412), (312, 426)],
                  5, 1.5, ACID, 8)


def g_ukg(p, field):
    """A warped roller garage door with a 2-step bass skip and a rewind."""
    # side tracks + canopy box make the shutter read as a door at 64 px
    p.rect((116, 102, 136, 422), INK, radius=6, wob=1.5)
    p.rect((374, 102, 394, 422), INK, radius=6, wob=1.5)
    p.rect((108, 74, 402, 112), INK, radius=10, wob=2.0)
    p.line([(124, 92), (386, 92)], 5, ACID, wob=0.8)

    p.rect((140, 112, 370, 422), INK, radius=10, wob=2.0)
    for i in range(7):
        y = 128 + i * 38
        p.rect((152, y, 358, y + 14), ACID, radius=3, wob=1.0)
    p.rect((140, 396, 370, 422), INK, radius=6, wob=1.2)
    p.rect((244, 402, 276, 416), ACID, radius=6, wob=0.8)

    # two cyan chevrons: the 2-step skip
    for i in range(2):
        x = 270 + i * 34
        p.line([(x, 380), (x + 24, 350), (x, 320)], 14, CYAN, wob=0.8)

    # rewind loop + bass skip
    ring(p, 432, 292, 32, 10, ACID, a0=20, a1=300, wob=1.0)
    p.fill([(418, 258), (446, 252), (440, 282)], ACID, wob=0.6)
    draw_squiggle(p, [(362, 384), (404, 362), (414, 332), (430, 318)],
                  6, 1.2, ACID, 12)

    for (x, y, r) in ((100, 150, 10), (86, 220, 7), (108, 286, 8)):
        p.disc(x, y, r, ACID)


def g_breakbeat(p, field):
    """A vinyl record snapped at the break; the two halves are offset."""
    tmp = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    tp = Pen(tmp)
    tp.disc(250, 235, 162, INK)
    tp.erase_ellipse(250, 235, 78, 78)
    tp.disc(250, 235, 72, INK)
    tp.fill([(220, 200), (220, 270), (286, 235)], ACID, wob=1.2)
    tp.line(circle_path(250, 235, 118, 140, 1.5), 8, ACID, wob=1.0)

    tmp = split_shift(tmp, 22, 26, split_x=250)
    p.img.alpha_composite(tmp)

    # a wide jagged break channel; the acid field shows through
    crack = [(238, 58), (212, 112), (252, 164), (224, 224), (262, 282),
             (236, 340), (258, 394), (246, 420)]
    p.line(crack, 34, (0, 0, 0, 0), wob=2.2)

    p.star(200, 132, 13, ACID, wob=0.8)
    p.star(300, 350, 11, ACID, wob=0.8)


def g_pirate(p, field):
    """Pirate radio: a skull in headphones over crossed Yagi aerials."""
    for (x0, y0, x1, y1) in ((118, 382, 394, 118), (118, 118, 394, 382)):
        p.line([(x0, y0), (x1, y1)], 16, INK, wob=1.8)
        dx, dy = x1 - x0, y1 - y0
        l = math.hypot(dx, dy)
        nx, ny = -dy / l, dx / l
        for t in (0.28, 0.5, 0.72):
            x, y = x0 + dx * t, y0 + dy * t
            p.line([(x - nx * 42, y - ny * 42), (x + nx * 42, y + ny * 42)],
                   12, INK, wob=1.0)
        p.disc(x0, y0, 8, ACID)
        p.disc(x1, y1, 8, ACID)

    p.blob(256, 214, 112, INK, wob=4.5, lobes=3, phase=0.2, squash=0.95)
    p.rect((198, 292, 314, 378), INK, radius=28, wob=2.4)

    for cx in (214, 298):
        p.erase_ellipse(cx, 210, 30, 34)
        p.disc(cx, 198, 6, ACID)
    p.erase_poly([(256, 250), (242, 282), (270, 282)])
    for x in (222, 246, 270, 294):
        p.erase_rect((x, 330, x + 12, 366))

    # headphones: band + cups, in acid so they read against the ink skull
    ring(p, 256, 214, 130, 20, ACID, a0=205, a1=335, wob=1.2)
    for (x0, x1) in ((118, 165), (347, 394)):
        p.rect((x0, 205, x1, 285), ACID, radius=18, wob=1.4)
        p.d.ellipse([(x0 + 12) * SS, 231 * SS, (x1 - 12) * SS, 259 * SS],
                    fill=INK)
    for r in (30, 50, 70):
        ring(p, 394, 245, r, 7, ACID, a0=-60, a1=60, wob=1.0)


# ---------------------------------------------------------------- recipes
# name, field, misregistration plates, painter, code, rotation, warp, sun
RECIPES = [
    dict(key="kool-fm", name="Kool FM", field=ACID, plate_a=MAGENTA, plate_b=PINK,
         painter=g_kool, code="KOOL-01", rot=-3.0,
         warp=dict(amp=7.5, freq=1.35, phase=0.15, sag=3.5), sun=(360, 96, 310),
         melt=3, melt_len=(34, 58), palette="ACID / MAGENTA",
         motif="Melted grin · X/spiral eyes · KOOL code",
         evokes="acid-house smiley and pirate transmitter energy",
         guard="no Kool logo or wordmark · KOOL only as code texture",
         row=("Kool FM", "LIVE RADIO · PIRATE")),
    dict(key="rinse-fm", name="Rinse FM", field=CYAN, plate_a=DEEP_TEAL, plate_b=PALE_CYAN,
         painter=g_rinse, code="STN-02", rot=0.0,
         warp=dict(amp=7.0, freq=1.5, phase=0.4, sag=2.5), sun=(150, 120, 290),
         melt=2, melt_len=(28, 44), palette="CYAN / INK",
         motif="Broken ripple rings cut by one rinse wave",
         evokes="circular rinse/ripple mark; no wordmark anywhere",
         guard="no Rinse wordmark · no ring logo trace",
         row=("Rinse FM", "LIVE RADIO · LONDON")),
    dict(key="oldskool-rave", name="Oldskool & Rave", field=MAGENTA, plate_a=ACID, plate_b=CYAN,
         painter=g_oldskool, code="STN-03", rot=-4.0,
         warp=dict(amp=8.5, freq=1.45, phase=0.25, sag=4.5), sun=(96, 96, 310),
         melt=0, melt_len=(36, 60), palette="MAGENTA / ACID",
         motif="A melting clock face on a rave starburst",
         evokes="old-skool flyer sun + the clock turned back",
         guard="no event or station logo · generic rave motifs only",
         row=("Oldskool & Rave", "LIVE RADIO · GENRE")),
    dict(key="jungle", name="Jungle", field=ACID, plate_a=MAGENTA, plate_b=CYAN,
         painter=g_jungle, code="STN-04", rot=3.0,
         warp=dict(amp=9.0, freq=1.5, phase=0.45, sag=4.0), sun=(382, 360, 310),
         melt=3, melt_len=(34, 56), palette="ACID / MAGENTA",
         motif="Fiddlehead fern curled around a single eye",
         evokes="jungle canopy, dub pressure, a watching eye",
         guard="no mask or third-party mark · original botanical motif",
         row=("Jungle", "LIVE RADIO · GENRE")),
    dict(key="drum-and-bass", name="Drum & Bass", field=CYAN, plate_a=MAGENTA, plate_b=ACID,
         painter=g_dnb, code="STN-05", rot=-2.0,
         warp=dict(amp=7.5, freq=1.6, phase=0.2, sag=3.0), sun=(402, 120, 300),
         melt=2, melt_len=(22, 34), palette="CYAN / MAGENTA",
         motif="A snare drum over a sub-bass wave",
         evokes="the drum and the bass, one above the other",
         guard="no label or station logo · instrument build",
         row=("Drum & Bass", "LIVE RADIO · GENRE")),
    dict(key="hardcore", name="Hardcore", field=ORANGE, plate_a=ACID, plate_b=MAGENTA,
         painter=g_hardcore, code="STN-06", rot=2.0,
         warp=dict(amp=8.0, freq=1.4, phase=0.55, sag=5.0), sun=(120, 360, 300),
         melt=3, melt_len=(34, 58), palette="ORANGE / ACID",
         motif="A klaxon with a lightning bolt and jagged rings",
         evokes="siren pressure, hardcore speed, alarm energy",
         guard="no event or station logo · no bolt copy",
         row=("Hardcore", "LIVE RADIO · GENRE")),
    dict(key="house", name="House", field=PAPER, plate_a=CYAN, plate_b=MAGENTA,
         painter=g_house, code="STN-07", rot=0.0,
         warp=dict(amp=7.0, freq=1.7, phase=0.3, sag=3.0), sun=(382, 96, 290),
         melt=2, melt_len=(28, 44), palette="PAPER / CYAN",
         motif="Four kick drums around a jackin' clap star",
         evokes="four-on-the-floor pulse, not a house pictogram",
         guard="no label or station logo · rhythm diagram only",
         row=("House", "LIVE RADIO · GENRE")),
    dict(key="uk-garage", name="UK Garage", field=MAGENTA, plate_a=CYAN, plate_b=ACID,
         painter=g_ukg, code="STN-08", rot=-3.0,
         warp=dict(amp=8.0, freq=1.55, phase=0.35, sag=4.0), sun=(100, 380, 300),
         melt=2, melt_len=(30, 48), palette="MAGENTA / CYAN",
         motif="Warped roller door with a 2-step bass skip",
         evokes="garage door, speed-garage bass, rewind",
         guard="no label or station logo · no '2' monogram",
         row=("UK Garage", "LIVE RADIO · GENRE")),
    dict(key="breakbeat", name="Breakbeat", field=ACID, plate_a=CYAN, plate_b=MAGENTA,
         painter=g_breakbeat, code="STN-09", rot=2.0,
         warp=dict(amp=8.0, freq=1.5, phase=0.25, sag=3.5), sun=(402, 380, 300),
         melt=2, melt_len=(28, 44), palette="ACID / CYAN",
         motif="Vinyl snapped at the break, two halves offset",
         evokes="the break itself: a record cracked off-grid",
         guard="no label or station logo · no existing break logo",
         row=("Breakbeat", "LIVE RADIO · GENRE")),
    dict(key="pirate-stations", name="Pirate Stations", field=PAPER, plate_a=MAGENTA, plate_b=ACID,
         painter=g_pirate, code="STN-10", rot=-2.0,
         warp=dict(amp=7.0, freq=1.45, phase=0.6, sag=3.0), sun=(118, 96, 300),
         melt=2, melt_len=(28, 46), palette="PAPER / MAGENTA",
         motif="Skull in headphones over crossed Yagi aerials",
         evokes="pirate flag + unlicensed broadcast rig",
         guard="no station logo · generic pirate-radio code",
         row=("Pirate Stations", "TAPE PACKS · STATIONS")),
]


# ---------------------------------------------------------------- tile
def build_tile(recipe):
    key = recipe["key"]
    field = recipe["field"]
    plate_a = recipe["plate_a"]
    plate_b = recipe["plate_b"]
    rnd = random.Random(sum(ord(c) for c in key) * 7 + 3)

    base = art.vertical_gradient(
        PX, mix(field, PAPER, 0.18), mix(field, INK, 0.28)).convert("RGBA")

    # riso sun: halftone burst of the first plate colour, off-centre
    base.alpha_composite(halftone(plate_a, spacing=12, radius=3.2, alpha=118,
                                  seed=rnd.randint(1, 99), sun=recipe["sun"]))

    # loose field squiggles, in the second plate colour
    scrib = Pen(base)
    for _ in range(2):
        x = rnd.uniform(40, 300)
        y = rnd.uniform(60, 380)
        draw_squiggle(scrib, [(x, y), (x + 40, y + 16), (x + 8, y + 48)],
                      rnd.uniform(5, 9), rnd.choice((1.5, 2.0)),
                      rgba(plate_b, 210), 6, phase=rnd.uniform(0, 6))

    # Kool FM only: the station name as a repeated sticker-code texture.
    if key == "kool-fm":
        microtext(base, "KOOL", 38, 70, 78, 400, size=10, alpha=118)
        microtext(base, "KOOL", 436, 70, 474, 400, size=10, alpha=118)
        microtext(base, "KOOL", 112, 438, 400, 452, size=10, alpha=150)

    # ink glyph
    layer = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    recipe["painter"](Pen(layer), field)
    add_melt(layer, INK, count=recipe["melt"],
             seed=rnd.randint(1, 500), max_len=recipe["melt_len"][1],
             min_len=recipe["melt_len"][0])
    if recipe["rot"]:
        layer = layer.rotate(recipe["rot"], resample=Image.BICUBIC,
                             center=(PX / 2, PX / 2))

    # two chromatic plates, each warped on its own phase
    comp = base
    for colour, dx, dy, phase, extra in (
            (plate_a, -8, -6, recipe["warp"]["phase"] + 0.18, dict(amp2=6.0)),
            (plate_b, 7, 7, recipe["warp"]["phase"] + 0.55, dict(amp2=5.0))):
        params = dict(recipe["warp"])
        params.update(extra)
        params["phase"] = phase
        plate = warp_alpha(layer, colour, **params)
        comp.alpha_composite(shift(plate, dx, dy))

    comp.alpha_composite(warp(layer, **recipe["warp"]))

    # print texture
    comp.alpha_composite(halftone(INK, spacing=16, radius=1.7, alpha=26,
                                  seed=rnd.randint(1, 99), jitter=1.1))
    comp.alpha_composite(scanlines(alpha=13))

    # furniture: border, crop marks, code, signal bars
    d = ImageDraw.Draw(comp)
    d.rectangle([0, 0, PX - 1, PX - 1], outline=rgba(INK, 255), width=2 * SS)
    d.rectangle([5 * SS, 5 * SS, PX - 5 * SS, PX - 5 * SS],
                outline=rgba(INK, 70), width=SS)
    for (x, y, sx, sy) in ((26, 26, 1, 1), (486, 26, -1, 1),
                           (26, 486, 1, -1), (486, 486, -1, -1)):
        d.line([(x * SS, y * SS), ((x + 26 * sx) * SS, y * SS)],
               fill=rgba(INK, 225), width=3 * SS)
        d.line([(x * SS, y * SS), (x * SS, (y + 26 * sy) * SS)],
               fill=rgba(INK, 225), width=3 * SS)

    fnt = art.font(art.MONO, 20 * SS)
    code = recipe["code"]
    d.text((34 * SS, 470 * SS), code, font=fnt, fill=rgba(INK, 240), anchor="ls")
    cw = d.textlength(code, font=fnt) / SS
    d.line([(32 * SS, 476 * SS), ((38 + cw) * SS, 476 * SS)],
           fill=rgba(INK, 190), width=3 * SS)
    for i, h in enumerate((10, 18, 26, 34)):
        x = (436 + i * 13) * SS
        d.rectangle([x, (478 - h) * SS, x + 8 * SS, 478 * SS],
                    fill=rgba(INK, 235))

    comp = grain(comp, amount=6, seed=rnd.randint(1, 40))
    return comp.convert("RGB").resize((OUT, OUT), Image.LANCZOS)


# ---------------------------------------------------------------- sheets
def _wrap(draw, text, font, max_width):
    words = text.split(" ")
    lines, line = [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def contact_sheet(tiles):
    width, row_h, top = 1440, 340, 216
    height = top + row_h * len(tiles) + 56
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)
    d.text((32, 56), "STATION TILES — LIVE RADIO",
           font=art.font(art.DISPLAY, 50), fill=PAPER, anchor="ls")
    d.text((32, 84),
           "KOOL FM · RINSE FM · GENRE SIGNALS · 2026 STICKER STUDY",
           font=art.font(art.MONO, 13), fill=ACID, anchor="ls")
    d.text((width - 32, 56), "64 / 128 / 256 PX",
           font=art.font(art.MONO, 14), fill=MUTED, anchor="rs")
    d.text((width - 32, 82), "UNOFFICIAL · NO AFFILIATION",
           font=art.font(art.MONO, 11), fill=MAGENTA, anchor="rs")

    # family check: accepted originals at 64 px
    refs = [("rave", "LATEST"), ("tapepacks", "PACKS"), ("jungle", "JUNGLE"),
            ("hardcore", "HARDCORE"), ("toronto", "TORONTO")]
    d.text((32, 126), "ACCEPTED ORIGINALS (64 PX) — THE FAMILY",
           font=art.font(art.MONO, 11), fill=MUTED, anchor="ls")
    x = width - 32 - len(refs) * 88
    for name, label in refs:
        path = os.path.join(ART, name + ".png")
        if not os.path.exists(path):
            continue
        ref = Image.open(path).convert("RGB").resize((64, 64), Image.LANCZOS)
        sheet.paste(ref, (x, 136))
        d.text((x + 32, 212), label, font=art.font(art.MONO, 8),
               fill=MUTED, anchor="ms")
        x += 88

    for index, (recipe, tile) in enumerate(tiles):
        y = top + index * row_h
        d.text((32, y + 30), recipe["name"],
               font=art.font(art.DISPLAY, 28), fill=PAPER, anchor="ls")
        d.text((32, y + 52), "%s · %s" % (recipe["code"], recipe["palette"]),
               font=art.font(art.MONO, 12), fill=recipe["field"], anchor="ls")

        font_motif = art.font(art.MONO, 11)
        for i, line in enumerate(_wrap(d, recipe["motif"], font_motif, 330)):
            d.text((32, y + 78 + i * 15), line, font=font_motif,
                   fill=PAPER, anchor="ls")
        font_ev = art.font(art.MONO, 10)
        for i, line in enumerate(_wrap(d, "EVOKES: " + recipe["evokes"],
                                       font_ev, 330)):
            d.text((32, y + 118 + i * 14), line, font=font_ev,
                   fill=MUTED, anchor="ls")
        font_guard = art.font(art.MONO, 9)
        for i, line in enumerate(_wrap(d, "NOT COPIED: " + recipe["guard"],
                                       font_guard, 330)):
            d.text((32, y + 158 + i * 13), line, font=font_guard,
                   fill=recipe["field"], anchor="ls")

        x64, x128, x256 = 400, 500, 660
        for size, px in ((64, x64), (128, x128), (256, x256)):
            small = tile.resize((size, size), Image.LANCZOS)
            sheet.paste(small, (px, y + 40))
            d.rectangle([px, y + 40, px + size - 1, y + 39 + size],
                        outline=rgba(MUTED, 110), width=1)
            d.text((px, y + 40 + size + 18), "%d" % size,
                   font=art.font(art.MONO, 11), fill=MUTED, anchor="ls")
        d.text((x256, y + 40 + 256 + 36), "ACTUAL PX",
               font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")

        # 64 px Kodi/web list row
        rx, ry, rw, rh = 1040, y + 40, 356, 84
        d.rectangle([rx, ry, rx + rw, ry + rh], fill=INK_2,
                    outline=rgba(MUTED, 80), width=1)
        sheet.paste(tile.resize((64, 64), Image.LANCZOS), (rx + 10, ry + 10))
        label, note = recipe["row"]
        f = art.fit_display(d, label, art.DISPLAY, rw - 96, 22, 12)
        d.text((rx + 86, ry + 40), label, font=f, fill=PAPER, anchor="ls")
        d.text((rx + 86, ry + 62), note, font=art.font(art.MONO, 9),
               fill=recipe["field"], anchor="ls")
        d.text((rx, ry + rh + 22), "64 PX ROW ART",
               font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")

        if index < len(tiles) - 1:
            d.line([(32, y + row_h - 22), (width - 32, y + row_h - 22)],
                   fill=(38, 38, 48), width=1)

    d.text((32, height - 28),
           "ORIGINAL CODE-DRAWN EVOCATIONS · NO TRACED OR EXPORTED BRAND ART · "
           "NOMINATIVE USE ONLY · ART STUDY, NOTHING WIRED",
           font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")
    sheet.save(CONTACT, "PNG", optimize=True)
    print("wrote", CONTACT)


def board(tiles):
    cols = 4
    tile, gap, left, top = 256, 34, 40, 150
    rows = (len(tiles) + cols - 1) // cols
    width = left * 2 + cols * tile + (cols - 1) * gap
    height = top + rows * (tile + 54) + 56
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)
    d.text((left, 56), "STATION TILES · 1:1 · 256 PX NATIVE",
           font=art.font(art.DISPLAY, 44), fill=PAPER, anchor="ls")
    d.text((left, 84), "JUDGE THE INK / MELT / MISREGISTRATION AT 100 %",
           font=art.font(art.MONO, 12), fill=ACID, anchor="ls")
    for i, (recipe, tile_img) in enumerate(tiles):
        r, c = divmod(i, cols)
        x = left + c * (tile + gap)
        y = top + r * (tile + 54)
        sheet.paste(tile_img, (x, y))
        d.rectangle([x, y, x + tile, y + tile], outline=rgba(MUTED, 80), width=1)
        d.text((x, y + tile + 20), recipe["name"],
               font=art.font(art.DISPLAY, 18), fill=PAPER, anchor="ls")
        d.text((x + tile, y + tile + 20), recipe["code"],
               font=art.font(art.MONO, 10), fill=recipe["field"], anchor="rs")
    d.text((left, height - 26),
           "accepted 2026 language + Direction C grammar · one hero mark per station · "
           "no traced logos",
           font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")
    sheet.save(BOARD, "PNG", optimize=True)
    print("wrote", BOARD)


def row_strip(tiles):
    width = 1180
    row_h = 76
    top = 168
    height = top + row_h * len(tiles) + 210
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)
    d.text((32, 54), "64 PX ROW CHECK", font=art.font(art.DISPLAY, 44),
           fill=PAPER, anchor="ls")
    d.text((32, 82), "THE SIZE KODI ACTUALLY DRAWS · LIST ROW ON A DARK PANEL",
           font=art.font(art.MONO, 12), fill=ACID, anchor="ls")

    for i, (recipe, tile_img) in enumerate(tiles):
        y = top + i * row_h
        d.rectangle([32, y, 32 + 700, y + 64], fill=INK_2,
                    outline=rgba(MUTED, 50), width=1)
        sheet.paste(tile_img.resize((64, 64), Image.LANCZOS), (36, y))
        label, note = recipe["row"]
        d.text((116, y + 28), label, font=art.font(art.DISPLAY, 21),
               fill=PAPER, anchor="ls")
        d.text((116, y + 46), note, font=art.font(art.MONO, 9),
               fill=recipe["field"], anchor="ls")
        d.text((716, y + 40), "64", font=art.font(art.MONO, 11),
               fill=MUTED, anchor="ls")

    y0 = top + len(tiles) * row_h + 30
    d.text((32, y0), "ACCEPTED ORIGINALS AT 64 PX",
           font=art.font(art.MONO, 11), fill=MUTED, anchor="ls")
    for i, (name, label) in enumerate((("rave", "LATEST"), ("tapepacks", "PACKS"),
                                       ("jungle", "JUNGLE"), ("hardcore", "HARDCORE"),
                                       ("toronto", "TORONTO"))):
        path = os.path.join(ART, name + ".png")
        if not os.path.exists(path):
            continue
        x = 32 + i * 96
        ref = Image.open(path).convert("RGB").resize((64, 64), Image.LANCZOS)
        sheet.paste(ref, (x, y0 + 14))
        d.text((x + 32, y0 + 88), label, font=art.font(art.MONO, 8),
               fill=MUTED, anchor="ms")

    sheet.save(ROWS, "PNG", optimize=True)
    print("wrote", ROWS)


def main():
    os.makedirs(SAMPLES, exist_ok=True)
    tiles = [(recipe, build_tile(recipe)) for recipe in RECIPES]
    for recipe, tile in tiles:
        for size in (64, 128, 256):
            path = os.path.join(SAMPLES, "%s-%d.png" % (recipe["key"], size))
            img = tile if size == 256 else tile.resize((size, size), Image.LANCZOS)
            img.save(path, "PNG", optimize=True)
    contact_sheet(tiles)
    board(tiles)
    row_strip(tiles)
    print("wrote %d station tiles + 3 sheets under %s" % (len(tiles), HERE))


if __name__ == "__main__":
    main()
