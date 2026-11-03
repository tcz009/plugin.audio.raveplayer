#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Direction C — TRIPPY RAVE.

Art study for the 2026 duplicate-row stickers (3.9.33 / 1.6.41). This is the
third direction, after the owner's note that A (BIG MARK) and B (MONOGRAM) are
"not like rave ... too clean / too literal":

  rave.png, tapepacks.png, jungle.png, hardcore.png, pirate.png, toronto.png
  are not tidy vector objects. They are screen-printed acid-house stickers:
  a flat spot field, a heavy ink shape, hard misregistration, halftone, and a
  smiley somewhere in the DNA.

Direction C keeps that DNA and pushes the parts A/B left out:

  * shapes MELT — every mark sags, droops and drips off its own silhouette;
  * the ink is hand-drawn — wobbly marker strokes, not clean bezier curves;
  * smileys are a family motif, not a one-off;
  * squiggles / scribbles / sparkles carry the flyer energy;
  * misregistration is hard and chromatic (two plates, each warped on its own
    phase, so the edges separate like a bad riso run);
  * acid / magenta / cyan fields, riso halftone suns, scanlines, grain.

Nothing is wired, committed or deployed. This script writes only into its own
folder, never into resources/art/, static/art/, routes.py or preview.jpg.

Requires Pillow + numpy (build-time only), and reads palette/fonts from
scripts/make-art.py so the family tokens stay identical.

    python3 build_direction_c.py
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

SHEET = os.path.join(HERE, "direction-c-contact-sheet.png")
BOARD = os.path.join(HERE, "direction-c-1to1.png")
ROWS = os.path.join(HERE, "direction-c-64px-rows.png")

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


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


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
    """Displace a dense path along its normal with two smooth sine bands.

    This is the hand-drawn part: a marker line never runs straight, so every
    silhouette gets a slow wobble plus a smaller second harmonic.
    """
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
    # closed shapes need whole-number cycles so the seam matches
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


def circle_pts(cx, cy, r, n=150, rwob=0.0, lobes=3, phase=0.0, squash=1.0):
    """cx/cy/r are render px; squash < 1 flattens vertically."""
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r + rwob * math.sin(lobes * a + phase) + rwob * 0.45 * math.sin(
            2 * lobes * a + phase * 1.6)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a) * squash))
    return pts


def arc_pts(cx, cy, r, a0, a1, n=48):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def rrect_pts(box, radius, step=7.0):
    x0, y0, x1, y1 = box
    r = min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
    pts = []
    for (cx, cy, a0) in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0),
                         (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(9):
            a = math.radians(a0 + 90 * k / 8)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts.append(pts[0])
    return resample(pts, step)


# ---------------------------------------------------------------- pen
class Pen:
    """Draws in 512-space onto an oversized canvas."""

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
        pts = circle_pts(cx * SS, cy * SS, r * SS, 150, rwob=wob * SS, lobes=lobes,
                         phase=phase, squash=squash)
        self.d.polygon(pts, fill=colour)

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


# ---------------------------------------------------------------- face parts
def grin(p, cx, cy, rx, ry, thickness, colour, step=26):
    """A fat hand-drawn smile: a sagging arc with heavy ends."""
    pts = [(cx + rx * math.cos(math.radians(28 + 124 * i / step)),
            cy + ry * math.sin(math.radians(28 + 124 * i / step)))
           for i in range(step + 1)]
    p.line(pts, thickness, colour, wob=1.2,
           taper=lambda t: 0.6 + 0.72 * math.sin(math.pi * t))


def eye(p, cx, cy, r, colour, wink=False):
    if wink:
        p.line([(cx - r, cy - r * 0.2), (cx + r, cy - r * 0.2)], r * 1.7, colour,
               wob=0.8, taper=lambda t: 0.55 + 0.6 * math.sin(math.pi * t))
    else:
        p.disc(cx, cy, r, colour)


def squiggle(points, amp, waves, phase=0.0):
    dense = resample(points, 5.0)
    lens = [0.0]
    for i in range(1, len(dense)):
        lens.append(lens[-1] + math.hypot(dense[i][0] - dense[i - 1][0],
                                          dense[i][1] - dense[i - 1][1]))
    total = lens[-1] or 1.0
    out = []
    for i, (x, y) in enumerate(dense):
        t = lens[i] / total
        a = max(0, i - 1)
        b = min(len(dense) - 1, i + 1)
        tx, ty = dense[b][0] - dense[a][0], dense[b][1] - dense[a][1]
        tl = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / tl, tx / tl
        off = amp * math.sin(2 * math.pi * waves * t + phase)
        out.append((x + nx * off, y + ny * off))
    return out


def draw_squiggle(p, points, amp, waves, colour, width, phase=0.0):
    p.line(squiggle(points, amp, waves, phase), width, colour, wob=0.7,
           taper=lambda t: 0.8 + 0.4 * math.sin(math.pi * t))


# ---------------------------------------------------------------- melt
def bottom_profile(layer):
    a = np.asarray(layer.getchannel("A"))
    h, w = a.shape
    ink = a > 96
    return np.where(ink.any(0), h - 1 - np.argmax(ink[::-1], axis=0), -1)


def add_melt(layer, colour, count=3, seed=0, max_len=64.0, min_len=28.0,
             x0=56, x1=456, ycap=430):
    """Gravity pass: hang drips off the flat underside of the mark.

    Only columns whose bottom is locally flat qualify, so drips fall straight
    down from an edge instead of sprouting sideways off a slope.
    """
    rnd = random.Random(seed)
    ybot = bottom_profile(layer)
    h = ybot.shape[0]
    span = int(16 * SS)
    flat = []
    for x in range(int(x0 * SS), int(x1 * SS)):
        y = ybot[x]
        if y <= h * 0.35 or y > ycap * SS:
            continue
        if abs(int(ybot[x + span]) - int(ybot[x - span])) <= 12 * SS:
            flat.append((x, int(y)))
    if not flat:
        return layer
    rnd.shuffle(flat)
    chosen = []
    for x, y in flat:
        if all(abs(x - cx) > 46 * SS for cx, _ in chosen):
            chosen.append((x, y))
        if len(chosen) >= count:
            break
    chosen.sort()

    p = Pen(layer)
    for (x, y) in chosen:
        length = rnd.uniform(min_len, max_len)
        top = y / SS
        tip = min(ycap, top + length)
        drift = rnd.uniform(-5, 5)
        neck = rnd.uniform(7.0, 9.5)
        bulb = rnd.uniform(11.0, 14.0)
        pts = [(x / SS, top - 10),
               (x / SS + drift * 0.3, top + length * 0.5),
               (x / SS + drift, tip - bulb)]
        p.line(pts, neck * 2, colour, wob=0.8, taper=lambda t: 1.0 - 0.30 * t)
        p.blob(x / SS + drift, tip - bulb * 0.45, bulb, colour, wob=1.6, lobes=3,
               phase=rnd.uniform(0, 6))
    return layer


def spatter(layer, colour=INK, count=24, seed=0, radius=2.8):
    """Marker spit: a few dry flecks around the mark, never on top of it."""
    a = np.asarray(layer.getchannel("A"))
    ys, xs = np.nonzero(a > 96)
    if len(xs) == 0:
        return layer
    rnd = random.Random(seed)
    d = ImageDraw.Draw(layer)
    pad = int(30 * SS)
    for _ in range(count):
        i = rnd.randrange(len(xs))
        x = int(xs[i]) + rnd.randint(-pad, pad)
        y = int(ys[i]) + rnd.randint(-pad, pad)
        if not (0 <= x < PX and 0 <= y < PX) or a[y, x] > 30:
            continue
        r = rnd.uniform(1.1, radius) * SS
        d.ellipse([x - r, y - r, x + r, y + r],
                  fill=rgba(colour, rnd.randint(140, 230)))
    return layer


def leaf(p, base, tip, width, colour, bend=0.2, phase=0.0):
    """A fat drooping leaf: quadratic spine, width tapering to both ends."""
    bx, by = base
    tx, ty = tip
    dx, dy = tx - bx, ty - by
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    cx = (bx + tx) / 2 + nx * length * bend
    cy = (by + ty) / 2 + ny * length * bend
    left, right = [], []
    for i in range(31):
        t = i / 30
        sx = (1 - t) ** 2 * bx + 2 * (1 - t) * t * cx + t * t * tx
        sy = (1 - t) ** 2 * by + 2 * (1 - t) * t * cy + t * t * ty
        w = width * math.sin(math.pi * t) ** 0.7
        left.append((sx + nx * w, sy + ny * w))
        right.append((sx - nx * w, sy - ny * w))
    p.fill(left + right[::-1], colour, wob=1.8, phase=phase)
    return [(bx, by), (cx, cy), (tx, ty)]


def puddle(p, cx, cy, rx, ry, colour, seed=0):
    rnd = random.Random(seed)
    pts = circle_pts(cx * SS, cy * SS, rx * SS, 140, rwob=ry * SS * 0.4, lobes=4,
                     phase=rnd.uniform(0, 6), squash=ry / max(1.0, rx))
    p.d.polygon(pts, fill=colour)


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
             jitter=1.2):
    """Dot screen. With `sun` the dots swell towards a focal point (riso sun)."""
    layer = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rnd = random.Random(seed)
    step = spacing * SS
    for y in range(0, PX + int(step), int(step)):
        for x in range(0, PX + int(step), int(step)):
            cx = x + rnd.uniform(-jitter, jitter) * SS
            cy = y + rnd.uniform(-jitter, jitter) * SS
            r, a = radius, alpha
            if sun is not None:
                sxc, syc, srad = sun
                dist = math.hypot(cx - sxc * SS, cy - syc * SS) / (srad * SS)
                if dist > 1.0:
                    continue
                r = radius * (0.22 + 2.2 * (1.0 - dist) ** 1.4)
                a = int(alpha * (0.30 + 0.85 * (1.0 - dist)))
            rr = r * SS
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=rgba(colour, a))
    return layer


def scanlines(colour=INK, period=14, alpha=12):
    layer = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(0, PX, period * SS):
        d.line([(0, y), (PX, y)], fill=rgba(colour, alpha), width=SS)
    return layer


def grain(img, amount=5, seed=3):
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


# ---------------------------------------------------------------- glyphs
def g_tapepacks(p, accent):
    """A cassette with a grin: the reels are eyes, the shell is the face."""
    p.rect((74, 152, 438, 370), INK, radius=30, wob=2.8, phase=0.15)
    for cx in (188, 322):
        p.disc(cx, 224, 44, accent)
        p.disc(cx, 224, 15, INK)
        p.disc(cx + 10, 224 + 26, 6, INK)      # a tear of ink under the reel
    grin(p, 256, 276, 92, 34, 17, accent, step=24)
    for i in range(3):
        p.line([(126 + i * 16, 322), (134 + i * 16, 322)], 7, accent, wob=0.4)
    # ribbon: tape unspooling into a loop, hand-drawn, in the second plate
    draw_squiggle(p, [(430, 196), (472, 220), (486, 286), (452, 300),
                      (436, 264)], 7, 1.5, CYAN, 10, phase=0.4)


def g_podcasts(p, accent):
    """A melting dynamic mic, cable curling into a hand-drawn loop."""
    p.line([(262, 384), (262, 420), (330, 432), (372, 406), (354, 378)],
           13, INK, wob=1.6, taper=lambda t: 0.8 + 0.35 * t)
    p.disc(354, 378, 12, INK)
    p.fill([(210, 262), (302, 262), (294, 386), (220, 386)], INK,
           wob=2.2, freq=2, phase=0.2)
    p.rect((196, 246, 316, 280), INK, radius=11, wob=1.8, phase=0.7)
    p.blob(256, 172, 90, INK, wob=5.0, lobes=3, phase=0.9, squash=0.95)
    for y in (140, 176, 212):
        k = (y - 172) / 98.0
        half = 72 * math.sqrt(max(0.06, 1 - k * k))
        p.line([(256 - half, y), (256 + half, y)], 13, accent, wob=1.4,
               taper=lambda t: 0.7 + 0.45 * math.sin(math.pi * t))
    p.line([(212, 268), (300, 268)], 7, accent, wob=0.9)
    p.disc(230, 258, 5, accent)
    p.disc(282, 258, 5, accent)


def g_kool(p, accent):
    """An A-frame transmitter mast wearing a grinning smiley head."""
    p.rect((168, 428, 344, 450), INK, radius=12, wob=1.8, phase=0.8)
    # wide tapering lattice: the tower owns the silhouette at 64 px
    p.fill([(180, 438), (332, 438), (288, 212), (224, 212)], INK,
           wob=2.0, freq=2, phase=0.3)
    for y in (252, 296, 340, 384):
        t = (y - 212) / (438 - 212)
        half = 30 + 44 * t - 10
        p.line([(256 - half, y), (256 + half, y)], 10, accent, wob=0.5)
    p.rect((220, 200, 292, 220), INK, radius=6, wob=1.4, phase=0.2)
    # small grinning ball on the mast head: a face, not a person
    p.blob(256, 150, 48, INK, wob=4.0, lobes=3, phase=0.35)
    eye(p, 240, 140, 8, accent)
    eye(p, 272, 140, 7, accent, wink=True)
    grin(p, 257, 145, 26, 20, 9, accent, step=16)
    for r in (74, 104):
        for (a0, a1) in ((-52, 52), (128, 232)):
            p.line(arc_pts(256, 150, r, a0, a1), 10, accent, wob=1.4,
                   taper=lambda t: 0.55 + 0.65 * math.sin(math.pi * t))


def g_radio_jungle(p, accent):
    """A warped soundsystem cabinet wearing jungle fronds, bass squiggle out."""
    # two fat fronds that droop outwards and down: jungle, and melt
    for (base, tip, w, bend, ph) in (((250, 230), (118, 54), 24, 0.34, 0.2),
                                     ((250, 230), (392, 48), 24, -0.30, 0.9),
                                     ((250, 230), (452, 196), 20, -0.42, 1.4)):
        spine = leaf(p, base, tip, w, INK, bend=bend, phase=ph)
        p.line(spine, 6, accent, wob=1.4)
    p.rect((104, 190, 408, 404), INK, radius=22, wob=2.8, phase=0.2)
    p.disc(242, 318, 80, accent)
    p.disc(242, 318, 52, INK)
    p.disc(242, 318, 24, accent)
    p.disc(242, 318, 9, INK)
    p.disc(242, 226, 26, accent)
    p.disc(242, 226, 9, INK)
    for i in range(3):
        p.line([(120, 378 + i * 8), (392, 378 + i * 8)], 3, accent, wob=0.4)
    draw_squiggle(p, [(404, 330), (452, 308), (474, 350), (448, 390),
                      (412, 384)], 8, 1.5, MAGENTA, 10, phase=0.2)


def g_dreamscape(p, accent):
    """A melting crescent with a wink; sparkles thrown across the field."""
    moon = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    mp = Pen(moon)
    mp.blob(274, 250, 150, INK, wob=5.0, lobes=3, phase=0.2)
    cut = circle_pts(360 * SS, 218 * SS, 138 * SS, 160, rwob=4 * SS, lobes=3,
                     phase=1.1)
    mp.d.polygon(cut, fill=(0, 0, 0, 0))
    p.img.alpha_composite(moon)
    eye(p, 208, 240, 12, accent)
    eye(p, 246, 226, 11, accent, wink=True)
    grin(p, 222, 238, 44, 34, 13, accent, step=18)
    p.star(392, 350, 28, MAGENTA, wob=1.4)
    p.star(430, 268, 15, INK, wob=0.8)
    p.star(140, 118, 20, INK, wob=0.9)
    p.star(340, 118, 13, CYAN, wob=0.7)
    p.star(112, 356, 12, CYAN, wob=0.7)


def g_downloads(p, accent):
    """A fat arrow melting into its own puddle."""
    p.rect((226, 74, 288, 250), INK, radius=16, wob=1.6, phase=0.3)
    p.fill([(178, 242), (338, 242), (264, 386), (250, 386)], INK,
           wob=2.0, freq=2, phase=0.6)
    p.blob(258, 372, 26, INK, wob=2.2, lobes=3, phase=0.4)   # sagging tip
    for y in (140, 190):
        p.line([(126, y), (176, y)], 10, MAGENTA, wob=0.9,
               taper=lambda t: 0.55 + 0.5 * math.sin(math.pi * t))
        p.line([(338, y), (388, y)], 10, MAGENTA, wob=0.9,
               taper=lambda t: 0.55 + 0.5 * math.sin(math.pi * t))


def g_pirate(p, accent):
    """A hand-drawn jolly-roger flag, torn and dripping."""
    p.line([(126, 104), (124, 432)], 18, INK, wob=1.8)
    p.disc(126, 98, 15, INK)
    flag = [(140, 106), (300, 118), (438, 136), (418, 208), (432, 254),
            (384, 238), (342, 266), (298, 238), (252, 266), (208, 240),
            (166, 256), (146, 220)]
    p.fill(flag, INK, wob=2.4, freq=2, phase=0.5)
    # skull: big enough to survive 64 px, grinning
    p.blob(284, 176, 50, accent, wob=2.6, lobes=3, phase=0.4)
    p.rect((264, 208, 304, 240), accent, radius=9, wob=1.2)
    p.disc(268, 170, 13, INK)
    p.disc(300, 170, 13, INK)
    grin(p, 286, 166, 22, 18, 8, INK, step=14)
    p.line([(272, 224), (296, 224)], 5, INK, wob=0.4)
    p.line([(284, 208), (284, 240)], 5, INK, wob=0.4)
    p.line([(196, 300), (350, 346)], 12, INK, wob=2.2,
           taper=lambda t: 0.55 + 0.6 * math.sin(math.pi * t))
    p.line([(348, 300), (198, 346)], 12, INK, wob=2.2,
           taper=lambda t: 0.55 + 0.6 * math.sin(math.pi * t))
    for (x, y) in ((190, 296), (356, 296), (192, 352), (354, 352)):
        p.disc(x, y, 10, INK)


def g_curated(p, accent):
    """A gem with a sagging pavilion and melted facet lines."""
    # the pavilion sags: the lower facets bow outwards instead of running true
    p.fill([(204, 104), (308, 104), (420, 206), (330, 300), (300, 362),
            (256, 414), (212, 362), (182, 300), (92, 206)], INK,
           wob=3.0, freq=2, phase=0.35)
    p.line([(204, 104), (308, 104)], 8, accent, wob=1.4)
    p.line([(92, 206), (420, 206)], 7, accent, wob=1.6)
    p.line([(166, 208), (212, 362), (256, 414)], 7, accent, wob=1.8)
    p.line([(346, 208), (300, 362), (256, 414)], 7, accent, wob=1.8)
    p.line([(204, 104), (166, 208)], 6, accent, wob=1.2)
    p.line([(308, 104), (346, 208)], 6, accent, wob=1.2)
    p.star(410, 146, 26, CYAN, wob=1.4)
    p.star(96, 316, 18, INK, wob=0.9)
    p.star(140, 86, 13, INK, wob=0.7)
    p.star(422, 340, 12, MAGENTA, wob=0.7)


def g_rave_nights(p, accent):
    """A melting big-top: sagging canvas, stripes knocked out, flag on top."""
    p.fill([(256, 80), (108, 404), (404, 404)], INK, wob=3.0, freq=2, phase=0.25)
    for (a, b, c) in (((256, 92), (150, 398), (196, 398)),
                      ((256, 92), (258, 398), (302, 398)),
                      ((256, 92), (366, 398), (412, 398))):
        p.fill([a, b, c], accent, wob=1.8, freq=2, phase=0.6)
    for i in range(5):
        p.blob(150 + i * 53, 392, 15, INK, wob=1.8, lobes=3, phase=0.4 + i)
    for x in (152, 204, 306, 356):
        p.fill([(x, 150), (x + 32, 150), (x + 16, 180)], accent, wob=1.2, phase=0.2)
    p.line([(256, 36), (256, 84)], 9, INK, wob=0.8)
    p.fill([(258, 38), (330, 56), (258, 76)], accent, wob=1.4, phase=0.4)


# ---------------------------------------------------------------- recipes
# (key, field, plate-1, plate-2, painter, code, rotation, warp params)
RECIPES = [
    ("tapepacks", ACID, MAGENTA, CYAN, g_tapepacks, "RP-03", -2.0,
     dict(amp=8.0, freq=1.4, phase=0.20, sag=4.0)),
    ("podcasts", MAGENTA, CYAN, ACID, g_podcasts, "RP-27", 1.5,
     dict(amp=7.0, freq=1.6, phase=0.55, sag=5.0)),
    ("kool", CYAN, MAGENTA, ACID, g_kool, "RP-31", -1.0,
     dict(amp=6.0, freq=1.3, phase=0.10, sag=3.0)),
    ("radio-jungle", ACID, MAGENTA, CYAN, g_radio_jungle, "RP-34", 2.0,
     dict(amp=9.0, freq=1.5, phase=0.40, sag=4.0)),
    ("dreamscape", PAPER, MAGENTA, CYAN, g_dreamscape, "RP-40", -5.0,
     dict(amp=8.0, freq=1.6, phase=0.30, sag=3.0)),
    ("downloads", CYAN, MAGENTA, ACID, g_downloads, "RP-55", 0.0,
     dict(amp=6.0, freq=1.8, phase=0.15, sag=6.0)),
    ("pirate", MAGENTA, ACID, CYAN, g_pirate, "RP-19", -2.0,
     dict(amp=7.0, freq=1.4, phase=0.65, sag=3.0)),
    ("curated", ACID, CYAN, MAGENTA, g_curated, "RP-06", 1.0,
     dict(amp=6.0, freq=1.7, phase=0.25, sag=5.0)),
    ("rave-nights", CYAN, MAGENTA, ACID, g_rave_nights, "RP-25", -1.5,
     dict(amp=8.0, freq=1.5, phase=0.45, sag=4.0)),
]

ROW_LABELS = {
    "tapepacks": ("Rave Tape Packs", "TAPE PACKS · GENRE"),
    "podcasts": ("Podcasts", "MIXES & SHOWS"),
    "kool": ("Kool FM", "LIVE RADIO · STATION"),
    "radio-jungle": ("Jungle", "LIVE RADIO · GENRE"),
    "dreamscape": ("Dreamscape", "QUICK FILTER · SERIES"),
    "downloads": ("Downloads", "MY LIBRARY · WEB"),
    "pirate": ("Pirate Radio", "TAPE PACKS · STATIONS"),
    "curated": ("Curated Gems", "CURATED GEMS"),
    "rave-nights": ("By Rave & Venue", "TAPE PACKS · CATEGORY"),
}


# ---------------------------------------------------------------- tile
def build_tile(recipe):
    key, field, plate_a, plate_b, painter, code, rot, warp_kw = recipe
    rnd = random.Random(sum(ord(c) for c in key) * 7 + 3)

    base = art.vertical_gradient(
        PX, mix(field, PAPER, 0.13), mix(field, INK, 0.17)).convert("RGBA")

    # riso sun: a halftone burst of the first plate colour, off-centre
    sun_c = (rnd.uniform(0.12, 0.88), rnd.uniform(0.08, 0.42))
    base.alpha_composite(halftone(plate_a, spacing=13, radius=2.6, alpha=82,
                                  seed=rnd.randint(1, 99),
                                  sun=(sun_c[0] * S, sun_c[1] * S, S * 0.58)))
    # one hand-drawn corner tag, always in the same safe zone top-left
    scrib = Pen(base)
    draw_squiggle(scrib, [(62, 92), (98, 70), (120, 100), (92, 122)], 5.5, 1.5,
                  plate_b, 7, phase=rnd.uniform(0, 6))

    # ---- ink glyph
    layer = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    painter(Pen(layer), field)
    add_melt(layer, INK, count=rnd.randint(2, 3), seed=rnd.randint(1, 500),
             max_len=rnd.uniform(44, 66))
    spatter(layer, INK, count=int(rnd.uniform(18, 30)), seed=rnd.randint(1, 900))
    if rot:
        layer = layer.rotate(rot, resample=Image.BICUBIC, center=(PX / 2, PX / 2))

    # ---- chromatic plates: each warped on its own phase so edges separate
    comp = base
    for colour, dx, dy, phase in ((plate_a, -7, -5, warp_kw["phase"] + 0.20),
                                  (plate_b, 6, 6, warp_kw["phase"] + 0.58)):
        params = dict(warp_kw)
        params["phase"] = phase
        params["amp2"] = 4.5
        plate = warp_alpha(layer, colour, **params)
        comp.alpha_composite(shift(plate, dx, dy))

    ink = warp(layer, **warp_kw)
    comp.alpha_composite(ink)

    # ---- print texture
    comp.alpha_composite(halftone(INK, spacing=16, radius=1.6, alpha=22,
                                  seed=rnd.randint(1, 99), jitter=0.9))
    comp.alpha_composite(scanlines(alpha=11))

    # ---- furniture: crop marks, code, signal bars (the family glue)
    d = ImageDraw.Draw(comp)
    for (x, y, sx, sy) in ((26, 26, 1, 1), (486, 26, -1, 1),
                           (26, 486, 1, -1), (486, 486, -1, -1)):
        d.line([(x * SS, y * SS), ((x + 26 * sx) * SS, y * SS)],
               fill=rgba(INK, 225), width=3 * SS)
        d.line([(x * SS, y * SS), (x * SS, (y + 26 * sy) * SS)],
               fill=rgba(INK, 225), width=3 * SS)
    fnt = art.font(art.MONO, 27 * SS)
    d.text((36 * SS, 470 * SS), code, font=fnt, fill=rgba(INK, 240), anchor="ls")
    d.line([(34 * SS, 476 * SS), (104 * SS, 476 * SS)], fill=rgba(INK, 190),
           width=3 * SS)
    for i, h in enumerate((10, 18, 26, 34)):
        x = (436 + i * 13) * SS
        d.rectangle([x, (478 - h) * SS, x + 8 * SS, 478 * SS], fill=rgba(INK, 235))

    comp = grain(comp, amount=5, seed=rnd.randint(1, 40))
    return comp.convert("RGB").resize((OUT, OUT), Image.LANCZOS)


# ---------------------------------------------------------------- sheets
def colour_name(c):
    for name, value in (("ACID", ACID), ("MAGENTA", MAGENTA), ("CYAN", CYAN),
                        ("PAPER", PAPER), ("ORANGE", ORANGE), ("INK", INK)):
        if c == value:
            return name
    return "MIX"


def contact_sheet(tiles):
    width, row_h, top = 1440, 372, 208
    height = top + row_h * len(tiles) + 56
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)
    d.text((32, 56), "DIRECTION C — TRIPPY RAVE", font=art.font(art.DISPLAY, 52),
           fill=PAPER, anchor="ls")
    d.text((32, 84),
           "MELTED INK · CHROMATIC MISREGISTRATION · SMILEYS · SQUIGGLES · HALFTONE",
           font=art.font(art.MONO, 13), fill=ACID, anchor="ls")
    d.text((width - 32, 56), "64 / 128 / 256 PX", font=art.font(art.MONO, 14),
           fill=MUTED, anchor="rs")

    refs = [("rave", "LATEST"), ("tapepacks", "TAPE PACKS"), ("jungle", "JUNGLE"),
            ("hardcore", "HARDCORE"), ("pirate", "PIRATE"), ("toronto", "TORONTO")]
    d.text((32, 128), "ACCEPTED ORIGINALS (64 PX) — THE FAMILY", font=art.font(art.MONO, 11),
           fill=MUTED, anchor="ls")
    x = width - 32 - len(refs) * 92
    for name, label in refs:
        path = os.path.join(ART, name + ".png")
        if not os.path.exists(path):
            continue
        ref = Image.open(path).convert("RGB").resize((64, 64), Image.LANCZOS)
        sheet.paste(ref, (x, 140))
        d.text((x + 32, 214), label, font=art.font(art.MONO, 8), fill=MUTED, anchor="ms")
        x += 92

    for index, (recipe, tile) in enumerate(tiles):
        key, field, plate_a, plate_b, _painter, code, _rot, _warp = recipe
        y = top + index * row_h
        d.text((32, y + 30), key, font=art.font(art.DISPLAY, 28), fill=PAPER, anchor="ls")
        d.text((32, y + 52), "%s · %s FIELD" % (code, colour_name(field)),
               font=art.font(art.MONO, 12), fill=field, anchor="ls")
        d.text((32, y + 74), "%s / %s PLATES" % (colour_name(plate_a),
                                                 colour_name(plate_b)),
               font=art.font(art.MONO, 11), fill=MUTED, anchor="ls")

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
        label, note = ROW_LABELS[key]
        f = art.fit_display(d, label, art.DISPLAY, rw - 96, 22, 12)
        d.text((rx + 86, ry + 40), label, font=f, fill=PAPER, anchor="ls")
        d.text((rx + 86, ry + 62), note, font=art.font(art.MONO, 9), fill=field, anchor="ls")
        d.text((rx, ry + rh + 22), "64 PX ROW ART", font=art.font(art.MONO, 10),
               fill=MUTED, anchor="ls")

        if index < len(tiles) - 1:
            d.line([(32, y + row_h - 22), (width - 32, y + row_h - 22)],
                   fill=(38, 38, 48), width=1)

    d.text((32, height - 28),
           "ART STUDY ONLY · NOTHING WIRED · ACID / MAGENTA / CYAN · MELT PASS ON EVERY MARK",
           font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")
    sheet.save(SHEET, "PNG", optimize=True)
    print("wrote", SHEET)


def board(tiles):
    cols = 3
    tile, gap, left, top = 256, 34, 40, 150
    rows = (len(tiles) + cols - 1) // cols
    width = left * 2 + cols * tile + (cols - 1) * gap
    height = top + rows * (tile + 54) + 56
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)
    d.text((left, 56), "1:1 · 256 PX NATIVE · NOTHING SCALED", font=art.font(art.DISPLAY, 44),
           fill=PAPER, anchor="ls")
    d.text((left, 84), "JUDGE THE MELT / MISREGISTRATION / HAND-LINE AT 100 %",
           font=art.font(art.MONO, 12), fill=ACID, anchor="ls")
    for i, (recipe, tile_img) in enumerate(tiles):
        key, field, _pa, _pb, _p, code, _rot, _warp = recipe
        r, c = divmod(i, cols)
        x = left + c * (tile + gap)
        y = top + r * (tile + 54)
        sheet.paste(tile_img, (x, y))
        d.rectangle([x, y, x + tile, y + tile], outline=rgba(MUTED, 80))
        d.text((x, y + tile + 20), key, font=art.font(art.DISPLAY, 18), fill=PAPER,
               anchor="ls")
        d.text((x + tile, y + tile + 20), code, font=art.font(art.MONO, 10),
               fill=field, anchor="rs")
    d.text((left, height - 26),
           "accepted 2026 language + acid-house melt · one field colour · two chromatic plates",
           font=art.font(art.MONO, 10), fill=MUTED, anchor="ls")
    sheet.save(BOARD, "PNG", optimize=True)
    print("wrote", BOARD)


def row_strip(tiles):
    """Every sample as a 64 px Kodi list row, next to the accepted originals."""
    width = 1180
    row_h = 76
    top = 168
    height = top + row_h * len(tiles) + 210
    sheet = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(sheet)
    d.text((32, 54), "64 PX ROW CHECK", font=art.font(art.DISPLAY, 44), fill=PAPER,
           anchor="ls")
    d.text((32, 82), "THE SIZE THE SKIN ACTUALLY DRAWS · LIST ROW ON A DARK PANEL",
           font=art.font(art.MONO, 12), fill=ACID, anchor="ls")

    for i, (recipe, tile_img) in enumerate(tiles):
        key, field, _pa, _pb, _p, _code, _rot, _warp = recipe
        y = top + i * row_h
        d.rectangle([32, y, 32 + 700, y + 64], fill=INK_2, outline=rgba(MUTED, 50))
        sheet.paste(tile_img.resize((64, 64), Image.LANCZOS), (36, y))
        label, note = ROW_LABELS[key]
        d.text((116, y + 30), label, font=art.font(art.DISPLAY, 21), fill=PAPER,
               anchor="ls")
        d.text((116, y + 48), note, font=art.font(art.MONO, 9), fill=field, anchor="ls")
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


def main():
    tiles = [(recipe, build_tile(recipe)) for recipe in RECIPES]
    for size in (64, 128, 256):
        os.makedirs(os.path.join(HERE, str(size)), exist_ok=True)
    for recipe, tile in tiles:
        name = recipe[0]
        tile.save(os.path.join(HERE, "sample-%s.png" % name), "PNG", optimize=True)
        for size in (64, 128, 256):
            tile.resize((size, size), Image.LANCZOS).save(
                os.path.join(HERE, str(size), "%s-%d.png" % (name, size)),
                "PNG", optimize=True)
    contact_sheet(tiles)
    board(tiles)
    row_strip(tiles)


if __name__ == "__main__":
    main()
