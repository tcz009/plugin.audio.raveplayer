#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render Kodi-menu screenshots from the add-on's real ListItem output.

Dev-only helper for the 2026 theme pass (docs/THEME-2026.md).  No device is
needed: it drives the plugin through the same ``test/stubs`` Kodi shim the unit
tests use, captures exactly what the add-on emits (labels, plots, icons,
fanart), and draws a Kodi 22 / Estuary-style directory screen with Pillow.

    python3 scripts/make-theme-shots.py --label before
    python3 scripts/make-theme-shots.py --label after

Outputs, under docs/theme-2026/:
    root-<label>.png     nine-row root screen (focus on row 1)
    hubs-<label>.png     2x2 montage of the four hub screens
    downloads-<label>.png  Favourites > Downloads view with sample local files
    menu-<label>.json    the captured ListItem data the renders were made from

This is an approximation of Estuary's "List" view for review, not a device
capture: font metrics, row heights and focus styling follow Estuary loosely.
The data and artwork are the add-on's real output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "docs", "theme-2026")

sys.path.insert(0, os.path.join(ROOT, "test", "stubs"))
sys.path.insert(0, ROOT)

import xbmcplugin  # noqa: E402  (stub)

from resources.lib import routes, ui  # noqa: E402

# The test stubs resolve the add-on path to test/, not the repo root. Point the
# artwork helpers at the real worktree so captured paths are the shipped ones.
routes.kodi.ADDON_PATH = ROOT
routes.kodi.ICON = os.path.join(ROOT, "icon.png")
routes.kodi.FANART = os.path.join(ROOT, "fanart.jpg")
ui.DEFAULT_FANART = routes.kodi.FANART

# --------------------------------------------------------------------- tokens
INK = (7, 7, 11)
INK_2 = (11, 11, 17)
PAPER = (242, 238, 227)
MUTED = (168, 163, 153)
ACID = (232, 255, 0)
MAGENTA = (255, 45, 143)
CYAN = (34, 230, 255)

FONT_UI = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_UI_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_MONO = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"
FONT_MONO_REG = "/System/Library/Fonts/Supplemental/Courier New.ttf"
FONT_DISPLAY = "/System/Library/Fonts/Supplemental/Impact.ttf"

W, H = 1920, 1080
ICON = 72


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def capture(mode, **params):
    xbmcplugin.ITEMS.clear()
    xbmcplugin.CONTENT.clear()
    params["mode"] = mode
    query = "&".join("%s=%s" % (key, value) for key, value in params.items())
    routes.dispatch(["plugin://plugin.audio.raveplayer/", "1", "?" + query])
    return [
        {
            "label": item["label"],
            "url": item["url"],
            "isFolder": item["isFolder"],
            "icon": item["art"].get("icon") or item["art"].get("thumb") or "",
            "thumb": item["art"].get("thumb") or "",
            "fanart": item["art"].get("fanart") or "",
            "plot": (item["info"].get("music") or {}).get("plot") or "",
        }
        for item in xbmcplugin.ITEMS
    ]


def _fit(path, size):
    try:
        return Image.open(path).convert("RGB")
    except (OSError, ValueError):
        return Image.new("RGB", size, INK)


def cover(img, size):
    return ImageOps_fit(img, size)


def ImageOps_fit(img, size):
    from PIL import ImageOps
    return ImageOps.fit(img, size, Image.LANCZOS, centering=(0.5, 0.5))


def darken(img, amount, side="left"):
    """Ink gradient: heavy on the list side, open on the artwork side."""
    from PIL import Image as I
    w, h = img.size
    mask = I.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    for x in range(w):
        t = x / max(1, w - 1)
        if side == "left":
            v = int(amount * max(0.0, 1.0 - t / 0.62) ** 1.25)
        else:
            v = int(amount * (1.0 - t))
        draw.line([(x, 0), (x, h)], fill=min(255, v))
    return I.composite(I.new("RGB", (w, h), INK), img, mask)


def scanlines(img, period=4, alpha=16):
    from PIL import Image as I
    w, h = img.size
    layer = I.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(0, h, period):
        d.line([(0, y), (w, y)], fill=INK + (alpha,))
    return I.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def render_screen(items, fanart_path, version, page_label, size=(W, H)):
    w, h = size
    base = cover(_fit(fanart_path, size), size)
    base = darken(base, 238, "left")
    base = scanlines(base, 4, 14)

    draw = ImageDraw.Draw(base)
    # top rule + brand bug (the add-on's existing icon, untouched)
    draw.rectangle([0, 0, w, 4], fill=ACID)
    icon_path = os.path.join(ROOT, "icon.png")
    try:
        bug = Image.open(icon_path).convert("RGBA").resize((52, 52), Image.LANCZOS)
        base.paste(bug, (72, 54), bug)
    except OSError:
        pass
    draw.text((140, 58), "RAVE PLAYER", font=font(FONT_DISPLAY, 38), fill=PAPER)
    draw.text((140, 100), page_label, font=font(FONT_MONO_REG, 17), fill=MUTED)

    # directory rows
    row_h = 84
    list_x, list_w = 72, int(w * 0.46)
    top = 176
    for index, item in enumerate(items):
        y = top + index * row_h
        focused = index == 0
        if focused:
            panel = Image.new("RGBA", (list_w, row_h - 4), (242, 238, 227, 16))
            base.paste(panel, (list_x, y), panel)
            draw.rectangle([list_x, y, list_x + 5, y + row_h - 4], fill=ACID)
        ix = list_x + 26
        iy = y + (row_h - 4 - ICON) // 2
        try:
            tile = Image.open(item["icon"]).convert("RGB").resize((ICON, ICON), Image.LANCZOS)
            base.paste(tile, (ix, iy))
        except (OSError, ValueError):
            draw.rectangle([ix, iy, ix + ICON, iy + ICON], fill=INK_2, outline=MUTED)
        label_font = font(FONT_UI, 30)
        text_x = ix + ICON + 24
        text_w = list_x + list_w - text_x - 14
        label = item["label"]
        while draw.textlength(label, font=label_font) > text_w and len(label) > 4:
            label = label[:-1]
        if label != item["label"]:
            label = label[:-3] + "..."
        draw.text((text_x, y + 18), label, font=label_font,
                  fill=ACID if focused else PAPER)
        if focused and item.get("plot"):
            plot = item["plot"]
            plot_font = font(FONT_UI_REG, 17)
            while draw.textlength(plot, font=plot_font) > text_w and len(plot) > 4:
                plot = plot[:-1]
            if plot != item["plot"]:
                plot = plot[:-3] + "..."
            draw.text((text_x, y + 52), plot, font=plot_font, fill=MUTED)

    # footer
    draw.rectangle([0, h - 44, w, h], fill=(7, 7, 11, 180))
    draw.text((list_x, h - 32), "SELECT  OK      BACK  ESC      INFO  I",
              font=font(FONT_MONO_REG, 15), fill=MUTED)
    ver_font = font(FONT_MONO, 15)
    ver_w = draw.textlength(version, font=ver_font)
    draw.text((w - 72 - ver_w, h - 32), version, font=ver_font, fill=PAPER)
    meta = "Kodi 22 · Estuary · 1080p"
    meta_font = font(FONT_MONO_REG, 15)
    meta_w = draw.textlength(meta, font=meta_font)
    draw.text((w - 72 - ver_w - 28 - meta_w, h - 32), meta, font=meta_font, fill=MUTED)
    return base


def render_root(label, version):
    items = capture("root")
    fan = items[0]["fanart"] if items and items[0].get("fanart") else \
        os.path.join(ROOT, "fanart.jpg")
    img = render_screen(items, fan, version, "Add-ons › Rave Player")
    out = os.path.join(OUT, "root-%s.png" % label)
    img.save(out, "PNG", optimize=True)
    print("wrote", out)
    return items


def render_hubs(label, version):
    hubs = [
        ("packs_menu", "Tape Packs"),
        ("shows_menu", "Mixes & Shows"),
        ("radio_menu", "Live Radio"),
        ("curated_menu", "Curated Gems"),
    ]
    cell_w, cell_h = 960, 540
    sheet = Image.new("RGB", (W, H), INK)
    data = {}
    for index, (mode, title) in enumerate(hubs):
        items = capture(mode)
        data[mode] = items
        fan = items[0]["fanart"] if items and items[0].get("fanart") else \
            os.path.join(ROOT, "fanart.jpg")
        # render at full size (the layout is tuned for 1080p) then downscale
        img = render_screen(items[:5], fan, version, "Rave Player › " + title)
        img = img.resize((cell_w, cell_h), Image.LANCZOS)
        sheet.paste(img, ((index % 2) * cell_w, (index // 2) * cell_h))
    out = os.path.join(OUT, "hubs-%s.png" % label)
    sheet.save(out, "PNG", optimize=True)
    print("wrote", out)
    return data


def render_downloads(label, version):
    """Render the Favourites > Downloads list with a deterministic sample index."""
    import json
    import shutil
    import tempfile

    from resources.lib import downloads

    work = tempfile.mkdtemp(prefix="rave-downloads-shot-")
    old = os.environ.get(downloads.DIR_ENV)
    os.environ[downloads.DIR_ENV] = work
    try:
        files = [
            ("dreamscape-19-toil-and-trouble-1995-a1b2c3d4.mp3", 48 * 1024 * 1024,
             "Dreamscape 19 — Toil & Trouble", "Archive.org", "2026-10-31T20:14:00Z"),
            ("kool-fm-94-2-1994-e5f6a7b8.mp3", 27 * 1024 * 1024,
             "Kool FM 94.2 — 1994", "Pirate Radio Archives", "2026-10-30T19:42:00Z"),
        ]
        index = []
        for filename, size, title, source, added in files:
            path = os.path.join(work, filename)
            with open(path, "wb") as handle:
                handle.truncate(size)  # sparse: size is what the UI shows
            index.append({
                "key": filename.rsplit("-", 1)[-1].split(".")[0],
                "filename": filename,
                "title": title,
                "source": source,
                "url": "",
                "size": size,
                "added": added,
            })
        index.append({
            "key": "missingc",
            "filename": "missing-pack-c0ffee00.mp3",
            "title": "Missing pack — delete me",
            "source": "Archive.org",
            "url": "",
            "size": 12 * 1024 * 1024,
            "added": "2026-10-29T18:00:00Z",
        })
        with open(os.path.join(work, downloads.METADATA_NAME), "w", encoding="utf-8") as handle:
            json.dump(index, handle)
        items = capture("downloads_menu")
        # Kodi renders [COLOR] tags; this preview is plain text.
        for item in items:
            item["label"] = ui.plain(item["label"])
        fan = os.path.join(ROOT, "resources", "art", "fanart-favourites.jpg")
        img = render_screen(items[:5], fan, version, "Favourites › Downloads")
        out = os.path.join(OUT, "downloads-%s.png" % label)
        img.save(out, "PNG", optimize=True)
        print("wrote", out)
        return items
    finally:
        if old is None:
            os.environ.pop(downloads.DIR_ENV, None)
        else:
            os.environ[downloads.DIR_ENV] = old
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", choices=("before", "after"), required=True)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    import re
    with open(os.path.join(ROOT, "addon.xml"), encoding="utf-8") as handle:
        version = "v" + re.search(r'<addon[^>]*version="([^"]+)"', handle.read()).group(1)
    root_items = render_root(args.label, version)
    hub_items = render_hubs(args.label, version)
    download_items = render_downloads(args.label, version)
    data = {"version": version, "root": root_items, "hubs": hub_items,
            "downloads": download_items}
    path = os.path.join(OUT, "menu-%s.json" % args.label)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    print("wrote", path)


if __name__ == "__main__":
    main()
