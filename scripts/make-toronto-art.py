#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the Toronto Rave Mixtape Archive sticker + fanart.

The Toronto source was the last one falling back to the generic ``rave.png``
sticker.  This script draws its own mark in the 2026 language defined by
``docs/THEME-2026.md``:

    resources/art/toronto.png            256x256   Kodi list/folder icon
    resources/art/fanart-toronto.jpg     1280x720  Kodi per-source fanart
    ../Rave Player/static/art/toronto.png  256x256 web section icon (same bytes)
    docs/theme-2026/toronto-icon-sheet.png  64/128/256 proof sheet

Motif: the CN Tower over a Toronto skyline, with a cassette shell in front —
the city and the tape the archive was traded on.  One cyan spot-colour tile,
ink glyph, hard magenta misregistration, halftone, scanlines, crop marks and
the next catalogue code (``RP-20``).  Nothing is traced from a logo or photo.

The drawing primitives and sticker builder live in ``make-art.py``; this script
only adds the Toronto recipe so it can be regenerated on its own without
rewriting the other 19 icons and 17 fanarts.

    python3 scripts/make-toronto-art.py
    python3 scripts/make-toronto-art.py --skip-web --no-preview

Pillow is build-time only (not a runtime dependency).
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "resources", "art")
SHEET = os.path.join(ROOT, "docs", "theme-2026", "toronto-icon-sheet.png")
WEB_ART = os.path.join(os.path.dirname(ROOT), "Rave Player", "static", "art")

WORD = "TORONTO"
SUBLINE = "1990S RAVE MIXTAPES · DIRECT MP3"
INDEX = 20
CODE = "RP-20"


def load_make_art():
    """Import the hyphenated sibling module (``make-art.py``) as a module."""
    path = os.path.join(ROOT, "scripts", "make-art.py")
    spec = importlib.util.spec_from_file_location("rave_make_art", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_icon_sheet(art, icon):
    """A 64/128/256 proof sheet, plus one list-row simulation at 64 px."""
    width, height = 1040, 480
    sheet = art.Image.new("RGB", (width, height), art.INK)
    draw = art.ImageDraw.Draw(sheet)

    draw.text((32, 58), "TORONTO", font=art.font(art.DISPLAY, 62),
              fill=art.PAPER, anchor="ls")
    draw.text((32, 82), "RAVE MIXTAPE ARCHIVE · %s · KODI + WEB STICKER" % CODE,
              font=art.font(art.MONO, 15), fill=art.CYAN, anchor="ls")

    y = 120
    for size, x in ((256, 30), (128, 320), (64, 480)):
        tile = icon.resize((size, size), art.Image.LANCZOS)
        sheet.paste(tile, (x, y))
        draw.rectangle([x, y, x + size - 1, y + size - 1],
                       outline=art.MUTED + (120,), width=1)
        draw.text((x, y + size + 26), "%d PX" % size,
                  font=art.font(art.MONO, 17), fill=art.PAPER, anchor="ls")
        draw.text((x, y + size + 44), "ACTUAL", font=art.font(art.MONO, 11),
                  fill=art.MUTED, anchor="ls")

    # List-row proof: this is roughly how Kodi/skin and the web row draw it.
    row = (592, 118, 1008, 202)
    draw.rectangle(row, fill=art.INK_2, outline=art.MUTED + (110,), width=1)
    sheet.paste(icon.resize((64, 64), art.Image.LANCZOS), (row[0] + 12, row[1] + 10))
    draw.text((row[0] + 88, row[1] + 44), "Toronto Rave Mixtape Archive",
              font=art.font(art.DISPLAY, 25), fill=art.PAPER, anchor="ls")
    draw.text((row[0] + 88, row[1] + 66), "MIXES & SHOWS · DIRECT MP3",
              font=art.font(art.MONO, 11), fill=art.CYAN, anchor="ls")
    draw.text((row[0], row[3] + 24), "64 PX ROW ART",
              font=art.font(art.MONO, 12), fill=art.MUTED, anchor="ls")

    draw.text((32, height - 28), "SCREEN-PRINT PASS · CYAN / INK / MAGENTA MISREGISTRATION",
              font=art.font(art.MONO, 11), fill=art.MUTED, anchor="ls")
    return sheet


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kodi-art", default=ART, help="Kodi resources/art directory")
    ap.add_argument("--web-art", default=WEB_ART, help="web static/art directory")
    ap.add_argument("--sheet", default=SHEET, help="64/128/256 proof sheet path")
    ap.add_argument("--skip-web", action="store_true", help="do not write the web icon")
    ap.add_argument("--no-preview", action="store_true",
                    help="do not rebuild resources/art/preview.jpg")
    args = ap.parse_args()

    try:
        art = load_make_art()
    except ImportError as exc:
        sys.exit("Pillow is required to generate art: pip install pillow (%s)" % exc)

    os.makedirs(args.kodi_art, exist_ok=True)
    icon = art.build_icon(art.CYAN, art.MAGENTA, "toronto", CODE)
    icon_path = os.path.join(args.kodi_art, "toronto.png")
    icon.save(icon_path, "PNG", optimize=True)

    fanart = art.build_fanart(art.CYAN, WORD, SUBLINE, INDEX, "fanart-toronto",
                              glyph_scale=0.52, glyph_x=0.67, glyph_y=0.02)
    fanart_path = os.path.join(args.kodi_art, "fanart-toronto.jpg")
    fanart.save(fanart_path, "JPEG", quality=92, optimize=True)

    if not args.skip_web:
        if os.path.isdir(args.web_art):
            web_path = os.path.join(args.web_art, "toronto.png")
            shutil.copyfile(icon_path, web_path)
            print("wrote %s (identical bytes to the Kodi icon)" % web_path)
        else:
            print("skipped web art: %s does not exist" % args.web_art)

    os.makedirs(os.path.dirname(args.sheet), exist_ok=True)
    build_icon_sheet(art, icon).save(args.sheet, "PNG", optimize=True)

    if not args.no_preview:
        icon_paths = [os.path.join(args.kodi_art, name + ".png")
                      for name, _accent, _shadow, _glyph, _code in art.ICONS]
        art.make_contact_sheet(os.path.join(args.kodi_art, "preview.jpg"),
                               [path for path in icon_paths if os.path.exists(path)])

    print("wrote %s" % icon_path)
    print("wrote %s" % fanart_path)
    print("wrote %s" % args.sheet)


if __name__ == "__main__":
    main()
