#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Placeholder artwork for the 3.9.47 Rave Screen add-on.

The parallel design specialist owns the final Rave Screen hero/sticker. These
files exist so the add-on builds, the skin loads and the tests can assert Kodi
sizes without waiting for the final art pass. They deliberately use only the
published 2026 tokens (ink/paper/acid/magenta/cyan) and the same screen-print
language as scripts/make-art.py.

    python3 scripts/make-screen-art.py
    python3 scripts/make-screen-art.py --force

Generated:
    resources/art/screen.png                     256x256  (plugin root row)
    resources/art/fanart-screen.jpg              1280x720 (plugin root row)
    script.raveplayer.ui/icon.png                512x512
    script.raveplayer.ui/fanart.jpg              1280x720
    script.raveplayer.ui/resources/art/rave-screen-hero.jpg  1280x720
"""

from __future__ import annotations

import argparse
import math
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_ART = os.path.join(ROOT, "resources", "art")
SCREEN = os.path.join(ROOT, "script.raveplayer.ui")

INK = (7, 7, 11)
INK_2 = (11, 11, 17)
PAPER = (242, 238, 227)
MUTED = (168, 163, 153)
ACID = (232, 255, 0)
MAGENTA = (255, 45, 143)
CYAN = (34, 230, 255)

FONTDIR = "/System/Library/Fonts/Supplemental"
DISPLAY = os.path.join(FONTDIR, "Impact.ttf")
MONO = os.path.join(FONTDIR, "Courier New Bold.ttf")


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def gradient(size, top, bottom):
    w, h = size
    strip = Image.new("RGB", (1, h))
    px = strip.load()
    for y in range(h):
        px[0, y] = mix(top, bottom, y / max(1, h - 1))
    return strip.resize((w, h), Image.BILINEAR)


def halftone(size, colour, spacing=9, radius=1.4, alpha=34):
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for y in range(0, h + spacing, spacing):
        for x in range(0, w + spacing, spacing):
            draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                         fill=colour + (alpha,))
    return layer


def scanlines(size, period=7, alpha=12):
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for y in range(0, h, period):
        draw.line([(0, y), (w, y)], fill=INK + (alpha,))
    return layer


def crop_marks(draw, w, h, inset=14, length=22, colour=INK):
    for x in (inset, w - inset):
        draw.line([(x, inset), (x + (length if x == inset else -length), inset)],
                  fill=colour, width=3)
        draw.line([(x, h - inset), (x + (length if x == inset else -length), h - inset)],
                  fill=colour, width=3)
    for y in (inset, h - inset):
        draw.line([(inset, y), (inset, y + (length if y == inset else -length))],
                  fill=colour, width=3)
        draw.line([(w - inset, y), (w - inset, y + (length if y == inset else -length))],
                  fill=colour, width=3)


def screen_glyph(draw, box, colour=INK, accent=MAGENTA):
    """A big screen/play mark: monitor outline + play triangle + signal bars."""
    x, y, w, h = box
    # misregistration plate
    draw.rounded_rectangle([x - 6, y - 6, x + w + 2, y + h + 2], radius=18,
                           outline=accent, width=8)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=16, outline=colour, width=10)
    draw.polygon([(x + w * 0.42, y + h * 0.34),
                  (x + w * 0.42, y + h * 0.66),
                  (x + w * 0.68, y + h * 0.50)], fill=colour)
    # aerial + bars
    draw.line([(x + w * 0.50, y), (x + w * 0.50, y - 26)], fill=colour, width=8)
    for index, height in enumerate((16, 26, 38, 26, 16)):
        bx = x + w * 0.18 + index * 17
        draw.rectangle([bx, y + h + 24 - height, bx + 9, y + h + 24], fill=colour)


def make_icon(path, size=256):
    img = gradient((size, size), mix(ACID, PAPER, 0.05), mix(ACID, INK, 0.14)).convert("RGBA")
    img.alpha_composite(halftone((size, size), INK))
    draw = ImageDraw.Draw(img)
    crop_marks(draw, size, size)
    draw.rounded_rectangle([16, 16, size - 16, size - 16], radius=6,
                           outline=INK + (70,), width=1)
    screen_glyph(draw, (size * 0.20, size * 0.23, size * 0.60, size * 0.40))
    code = font(MONO, max(12, size // 18))
    draw.text((22, size - 36), "RP-47", font=code, fill=INK)
    # signal bars bottom right
    for index in range(3):
        height = 6 + index * 5
        draw.rectangle([size - 34 + index * 9, size - 20 - height,
                        size - 30 + index * 9, size - 20], fill=INK)
    img.alpha_composite(scanlines((size, size)))
    img.convert("RGB").save(path)


def make_fanart(path, size=(1280, 720), title="RAVE SCREEN", sub="FULL SCREEN · 1280×720"):
    w, h = size
    img = gradient((w, h), INK_2, (18, 8, 20)).convert("RGBA")
    # left 46% quiet for Kodi's list panel
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse([int(w * 0.58), int(h * 0.12), int(w * 1.04), int(h * 0.90)],
                 fill=MAGENTA + (30,))
    img.alpha_composite(glow)
    img.alpha_composite(halftone((w, h), PAPER, spacing=13, radius=1.5, alpha=14))
    draw = ImageDraw.Draw(img)
    # hazard strip
    for y in range(-40, h + 40, 48):
        draw.polygon([(0, y), (22, y), (52, y + 48), (30, y + 48)], fill=ACID)
    crop_marks(draw, w, h, inset=28, length=34, colour=PAPER)
    # oversized screen glyph
    screen_glyph(draw, (int(w * 0.70), int(h * 0.20), int(w * 0.20), int(h * 0.22)),
                 colour=PAPER, accent=CYAN)
    title_font = font(DISPLAY, int(h * 0.15))
    sub_font = font(MONO, 20)
    x = int(w * 0.50)
    y = int(h * 0.49)
    draw.text((x + 10, y + 10), title, font=title_font, fill=MAGENTA)
    draw.text((x, y), title, font=title_font, fill=PAPER)
    draw.line([(x, y + int(h * 0.16)), (x + int(w * 0.31), y + int(h * 0.16))],
              fill=ACID, width=5)
    draw.text((x, y + int(h * 0.19)), sub, font=sub_font, fill=MUTED)
    draw.text((28, h - 48), "RP · RAVE SCREEN 2026", font=font(MONO, 14), fill=MUTED)
    img.alpha_composite(scanlines((w, h), period=8, alpha=10))
    img.convert("RGB").save(path, quality=92)


def make_focus_plate(path, size=(518, 76)):
    w, h = size
    img = gradient((w, h), ACID, mix(ACID, MAGENTA, 0.55)).convert("RGBA")
    img.alpha_composite(halftone((w, h), INK, spacing=7, radius=1.0, alpha=24))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w - 1, h - 1], outline=INK, width=4)
    # misregistration edge
    draw.line([(4, h - 7), (w - 4, h - 7)], fill=MAGENTA, width=4)
    img.alpha_composite(scanlines((w, h), period=6, alpha=12))
    img.convert("RGB").save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="overwrite files (the design specialist may have replaced them)")
    args = ap.parse_args()
    targets = [
        os.path.join(PLUGIN_ART, "screen.png"),
        os.path.join(PLUGIN_ART, "fanart-screen.jpg"),
        os.path.join(SCREEN, "icon.png"),
        os.path.join(SCREEN, "fanart.jpg"),
        os.path.join(SCREEN, "resources", "art", "rave-screen-hero.jpg"),
    ]
    if not args.force:
        existing = [path for path in targets if os.path.exists(path)]
        if existing:
            print("refusing to overwrite existing art (use --force):")
            for path in existing:
                print(" ", os.path.relpath(path, ROOT))
            return 1
    os.makedirs(os.path.dirname(os.path.join(SCREEN, "resources", "art", "rave-screen-hero.jpg")),
                exist_ok=True)
    make_icon(os.path.join(PLUGIN_ART, "screen.png"), 256)
    make_fanart(os.path.join(PLUGIN_ART, "fanart-screen.jpg"))
    make_icon(os.path.join(SCREEN, "icon.png"), 512)
    make_fanart(os.path.join(SCREEN, "fanart.jpg"))
    make_fanart(os.path.join(SCREEN, "resources", "art", "rave-screen-hero.jpg"),
                title="RAVE", sub="SPINNING SURPRISE")
    media = os.path.join(SCREEN, "resources", "skins", "Default", "media")
    os.makedirs(media, exist_ok=True)
    make_focus_plate(os.path.join(media, "focus-plate.png"))
    make_fanart(os.path.join(media, "screen-bg.jpg"))
    print("wrote Rave Screen placeholders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
