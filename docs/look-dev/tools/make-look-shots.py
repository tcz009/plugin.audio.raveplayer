#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render Kodi/Estuary screenshots from the add-on's real ListItem output.

Design/UX audit tool for docs/LOOK-AND-FEEL-2026.md.  Dev-only: nothing here is
shipped inside the add-on, and no add-on code is modified.

The data is the add-on's own: the plugin is dispatched through ``test/stubs``
(the same Kodi shim the unit tests use) and the ListItems it emits are captured
verbatim.  Layout follows Estuary master, read from the skin XML:

    MyPrograms.xml            defaultcontrol 52, <views>50,52,55,500</views>
    View_52_IconWall.xml      card 396x245 in a 440x280 cell; art box 160x130
                              at (120,20); label plate 356x75 at (20,150)
    View_55_WideList.xml      list at x=594, row height 75, label x+105,
                              label2 right-aligned, 32px status icon at x+35
    View_50_List.xml          list at 596..1326, poster panel 540x850
    Constants_1080.xml        list_item_height 75, top 100, bottom 80
    Variables.xml             ListItem.Plot is video-only; ListItem.Label2 is
                              the plugin row's right column
    colors/defaults.xml       button_focus FF12A0C7, grey FFA0A0A0

Usage:
    python3 docs/look-dev/tools/make-look-shots.py

Outputs (docs/look-dev/):
    current/*.png      what Kodi draws today
    proposed/*.png     the same data with a proposed change
    capture.json       the captured ListItems
    board-before-after.png
"""
from __future__ import annotations

import json
import os
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
LOOK = os.path.dirname(HERE)                 # docs/look-dev
ROOT = os.path.dirname(os.path.dirname(LOOK))  # repo root
OUT_CURRENT = os.path.join(LOOK, "current")
OUT_PROPOSED = os.path.join(LOOK, "proposed")
ASSETS = os.path.join(LOOK, "assets")
FIXTURES = os.path.join(HERE, "fixtures")

sys.path.insert(0, os.path.join(ROOT, "test", "stubs"))
sys.path.insert(0, ROOT)

import xbmcplugin  # noqa: E402  (Kodi stub)

from resources.lib import downloads, routes, ui  # noqa: E402

# The stub resolves the add-on path to test/.  Point artwork helpers at the
# real worktree so captured paths are the shipped ones.
routes.kodi.ADDON_PATH = ROOT
routes.kodi.ICON = os.path.join(ROOT, "icon.png")
routes.kodi.FANART = os.path.join(ROOT, "fanart.jpg")
ui.DEFAULT_FANART = routes.kodi.FANART
routes.kodi.ADDON_VERSION = "3.9.36"

# --------------------------------------------------------------------- tokens
INK = (9, 9, 12)
INK_2 = (13, 13, 17)
PANEL = (16, 16, 20)
PAPER = (240, 240, 240)
MUTED = (160, 160, 160)
DIM = (110, 110, 116)
ACID = (232, 255, 0)
MAGENTA = (255, 45, 143)
CYAN = (34, 230, 255)
FOCUS = (18, 160, 199)          # Estuary's button_focus, FF12A0C7
FOCUS_DIM = (12, 96, 120)

FONT_DIR = "/System/Library/Fonts/Supplemental"
FONT_UI = os.path.join(FONT_DIR, "Arial.ttf")
FONT_UI_B = os.path.join(FONT_DIR, "Arial Bold.ttf")
FONT_MONO = os.path.join(FONT_DIR, "Courier New Bold.ttf")
FONT_MONO_R = os.path.join(FONT_DIR, "Courier New.ttf")
FONT_DISPLAY = os.path.join(FONT_DIR, "Impact.ttf")

W, H = 1920, 1080
_cache = {}


def font(path, size):
    key = (path, size)
    if key not in _cache:
        try:
            _cache[key] = ImageFont.truetype(path, size)
        except OSError:
            _cache[key] = ImageFont.load_default()
    return _cache[key]


def text_w(draw, text, f):
    return draw.textlength(text, font=f)


def truncate(draw, text, f, width):
    if text_w(draw, text, f) <= width:
        return text
    out = text
    while out and text_w(draw, out + "…", f) > width:
        out = out[:-1]
    return out + "…"


def wrap(draw, text, f, width, max_lines=2):
    words = text.split()
    lines, line = [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if text_w(draw, trial, f) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = truncate(draw, lines[-1] + "…", f, width)
    return lines


# ------------------------------------------------------------------- capture
def capture(mode, **params):
    """Dispatch one route through the Kodi stub and return its ListItems."""
    xbmcplugin.ITEMS.clear()
    xbmcplugin.CONTENT.clear()
    params["mode"] = mode
    query = "&".join("%s=%s" % (key, value) for key, value in params.items())
    routes.dispatch(["plugin://plugin.audio.raveplayer/", "1", "?" + query])
    items = []
    for raw in xbmcplugin.ITEMS:
        music = raw["info"].get("music") or {}
        items.append({
            "label": raw["label"],
            "label_plain": ui.plain(raw["label"]),
            "url": raw["url"],
            "isFolder": raw["isFolder"],
            "art": dict(raw["art"]),
            "info": dict(music),
            "comment": music.get("comment") or music.get("plot") or "",
            "context": list(raw["context"]),
            "content": xbmcplugin.CONTENT[-1] if xbmcplugin.CONTENT else "",
        })
    return items


def packs():
    with open(os.path.join(FIXTURES, "archive-packs.json"), encoding="utf-8") as handle:
        return {pack["identifier"]: pack for pack in json.load(handle)["packs"]}


PACKS = packs()
PACK = PACKS["dreamscape-12-august-bank-holiday-showcase-1994"]
PACK_PLUS = PACKS["ct_Dreamscape_14_29.10.94"]


def _patch_archive(pack):
    routes.archive.audio_files = lambda identifier: [
        {"title": track["title"], "size": track["size"],
         "duration": track["duration"], "url": "https://archive.org/x.mp3"}
        for track in pack["tracks"]
    ]
    routes.archive.item_title = lambda identifier: pack["title"]
    routes.archive.thumb = lambda identifier: os.path.join(ASSETS, "cover-dreamscape12-front.jpg")


def downloads_screen():
    """Favourites > Downloads with a deterministic sample index (no network)."""
    import shutil
    import tempfile

    work = tempfile.mkdtemp(prefix="rave-look-downloads-")
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
            with open(os.path.join(work, filename), "wb") as handle:
                handle.truncate(size)
            index.append({
                "key": filename.rsplit("-", 1)[-1].split(".")[0],
                "filename": filename, "title": title, "source": source,
                "url": "", "size": size, "added": added,
            })
        index.append({
            "key": "missingc", "filename": "missing-pack-c0ffee00.mp3",
            "title": "Missing pack — delete me", "source": "Archive.org",
            "url": "", "size": 12 * 1024 * 1024, "added": "2026-10-29T18:00:00Z",
        })
        with open(os.path.join(work, downloads.METADATA_NAME), "w", encoding="utf-8") as handle:
            json.dump(index, handle)
        return capture("downloads_menu")
    finally:
        if old is None:
            os.environ.pop(downloads.DIR_ENV, None)
        else:
            os.environ[downloads.DIR_ENV] = old
        shutil.rmtree(work, ignore_errors=True)


def empty_latest():
    routes.latest.merge = lambda: []
    routes._latest_live_rows = lambda handle: 0
    return capture("latest")


# ------------------------------------------------------------------ backdrop
def _art(path, size, mode="cover"):
    try:
        img = Image.open(path).convert("RGB")
    except (OSError, ValueError):
        return Image.new("RGB", size, INK)
    if mode == "cover":
        return ImageOps.fit(img, size, Image.LANCZOS, centering=(0.5, 0.5))
    return ImageOps.contain(img, size, Image.LANCZOS)


def fanart_for(items, index=0):
    for item in items[max(0, index):] + items[:max(0, index)]:
        path = item["art"].get("fanart")
        if path and os.path.exists(path):
            return path
    return os.path.join(ROOT, "fanart.jpg")


def backdrop(fanart_path, dim=0.34):
    """Estuary: fanart under a dark wash, plus the skin's background pattern."""
    base = _art(fanart_path, (W, H))
    base = Image.blend(base, Image.new("RGB", (W, H), INK), 1.0 - dim * 0.72)
    # soft bottom-left vignette so the list column always reads
    vignette = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(vignette)
    for x in range(0, W, 2):
        alpha = int(120 * max(0.0, 1.0 - x / (W * 0.62)))
        draw.rectangle([x, 0, x + 2, H], fill=alpha)
    base = Image.composite(Image.new("RGB", (W, H), INK), base, vignette)
    return base


def dot_pattern(img, spacing=7, alpha=9):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for y in range(0, img.size[1], spacing):
        for x in range(0, img.size[0], spacing):
            draw.point((x, y), fill=(255, 255, 255, alpha))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def top_bar(img, crumb, sub, clock="16:41"):
    draw = ImageDraw.Draw(img, "RGBA")
    band = Image.new("RGBA", (W, 150), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for y in range(150):
        alpha = int(225 * (1 - y / 150.0) ** 1.3)
        bd.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img.alpha_composite(band) if img.mode == "RGBA" else None
    draw.text((35, 14), crumb, font=font(FONT_UI_B, 29), fill=(236, 236, 236, 255))
    if sub:
        draw.text((35, 58), sub, font=font(FONT_UI, 18), fill=(170, 170, 170, 255))
    cw = text_w(draw, clock, font(FONT_UI, 26))
    draw.text((W - 40 - cw, 20), clock, font=font(FONT_UI, 26), fill=(225, 225, 225, 255))
    return img


def bottom_bar(img, hint="Options"):
    draw = ImageDraw.Draw(img, "RGBA")
    band = Image.new("RGBA", (W, 110), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for y in range(110):
        alpha = int(180 * (y / 110.0) ** 1.6)
        bd.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img.paste(Image.alpha_composite(img.crop((0, H - 110, W, H)).convert("RGBA"), band).convert("RGB"),
              (0, H - 110))
    draw = ImageDraw.Draw(img, "RGBA")
    draw.text((58, H - 52), "◀  " + hint, font=font(FONT_UI, 18), fill=(190, 190, 190, 255))
    return img


def shadow_card(img, box, radius=2):
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([x0 + 6, y0 + 10, x1 + 6, y1 + 10], fill=(0, 0, 0, 130))
    layer = layer.filter(ImageFilter.GaussianBlur(12))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0))


# ------------------------------------------------------------------ iconwall
CARD_W, CARD_H = 396, 245
CELL_W, CELL_H = 440, 280
GRID_X = 96
CARD_TOP = 150
ART_W, ART_H = 160, 130


def card_art(path, size):
    """`aspectratio keep` into the art box: contain, not crop."""
    try:
        img = Image.open(path).convert("RGB")
    except (OSError, ValueError):
        return Image.new("RGB", size, INK)
    return ImageOps.contain(img, size, Image.LANCZOS)


def card_slot(path, boost=1.12):
    """Proposal: art cut to Estuary's IconWall slot (160x130 = 1.23:1).

    The fanart's type block sits at 50% width; anchoring the crop just left of
    it keeps the word in the card instead of cropping it out.
    """
    try:
        img = Image.open(path).convert("RGB")
    except (OSError, ValueError):
        return Image.new("RGB", (640, 520), INK)
    w, h = img.size
    target_w = int(h * ART_W / float(ART_H))          # 1.23:1
    if target_w < w:
        left = min(w - target_w, int(w * 0.40))
        img = img.crop((left, 0, left + target_w, h))
    img = ImageOps.fit(img, (640, 520), Image.LANCZOS)
    if boost != 1.0:
        from PIL import ImageEnhance
        img = ImageEnhance.Brightness(img).enhance(boost)
        img = ImageEnhance.Contrast(img).enhance(1.05)
    return img


def draw_iconwall(items, focus=0, crumb="Programs / Rave Player", card_art_fn=None,
                  label_fn=None, font_boost=0.0):
    img = backdrop(fanart_for(items, focus)).convert("RGBA")
    img = dot_pattern(img).convert("RGBA")

    for index, item in enumerate(items):
        col, row = index % 4, index // 4
        cx = GRID_X + col * CELL_W
        cy = row * CELL_H
        focused = index == focus
        grow = 1.12 if focused else 1.0
        cw, ch = CARD_W * grow, CARD_H * grow
        bx = cx + (CELL_W - cw) / 2
        by = cy + CARD_TOP - (ch - CARD_H) / 2

        shadow_card(img, (int(bx), int(by), int(bx + cw), int(by + ch)))
        card = Image.new("RGBA", (int(cw), int(ch)), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rectangle([0, 0, int(cw) - 1, int(ch) - 1], fill=(20, 20, 24, 248),
                     outline=(255, 255, 255, 26), width=1)
        if focused:
            card = Image.alpha_composite(card, Image.new("RGBA", card.size, FOCUS + (46,)))
            cd = ImageDraw.Draw(card)
            cd.rectangle([0, 0, int(cw) - 1, int(ch) - 1], outline=FOCUS + (255,), width=2)

        s = cw / float(CARD_W)
        art = item["art"].get("poster") or item["art"].get("icon")
        if card_art_fn:
            art = card_art_fn(item) or art
        tw, th = int(ART_W * s), int(ART_H * s)
        if isinstance(art, Image.Image):
            fit = ImageOps.contain(art, (tw, th), Image.LANCZOS)
        else:
            fit = card_art(art, (tw, th))
        ox = int(120 * s + (tw - fit.size[0]) / 2)
        oy = int(20 * s + (th - fit.size[1]) / 2)
        card.paste(fit, (ox, oy))

        label = label_fn(item) if label_fn else item["label_plain"]
        plate = Image.new("RGBA", (int(356 * s), int(75 * s)), (0, 0, 0, 96))
        card.alpha_composite(plate, (int(20 * s), int(150 * s)))
        cd = ImageDraw.Draw(card)
        fsize = int((20 + font_boost) * s)
        lines = wrap(cd, label, font(FONT_UI, fsize), int(340 * s), max_lines=2)
        lh = int((fsize + 5) * 1.15)
        top = int(150 * s) + (int(75 * s) - lh * len(lines)) // 2
        for i, line in enumerate(lines):
            lw = cd.textlength(line, font=font(FONT_UI, fsize))
            cd.text(((cw - lw) / 2, top + i * lh), line,
                    font=font(FONT_UI, fsize), fill=(240, 240, 240, 255))
        img.alpha_composite(card, (int(bx), int(by)))

    total = len(items)
    img = top_bar(img.convert("RGB"), crumb, ("1 / %d" % total) if total else "", "16:41")
    img = bottom_bar(img)
    return img


def draw_iconwall_label(item):
    """Proposal: title + grey kicker in one string; wraps once in the card."""
    return item["_label2"]


# --------------------------------------------------------------------- list
def draw_list(items, focus=3, crumb="Programs / Rave Player", info_lines=None,
              show_panel=True, label_fn=None, label2_fn=None, title=None,
              poster_path=None):
    img = backdrop(fanart_for(items, focus)).convert("RGBA")
    img = dot_pattern(img).convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    # left info panel (View_55 ListThumbInfoPanel): x 0..656
    panel = Image.new("RGBA", (600, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    for x in range(600):
        alpha = int(215 * (1 - (x / 600.0) ** 2.2))
        pd.line([(x, 0), (x, H)], fill=(10, 10, 13, alpha))
    img.alpha_composite(panel, (0, 0))
    draw = ImageDraw.Draw(img, "RGBA")

    if show_panel:
        cover = poster_path or items[focus]["art"].get("thumb") or items[focus]["art"].get("icon")
        art = _art(cover, (540, 470))
        box = ImageOps.contain(art, (540, 470), Image.LANCZOS)
        ax = 30 + (540 - box.size[0]) // 2
        ay = 110 + (470 - box.size[1])  # aligny bottom
        draw.rectangle([30, 110, 570, 580], fill=(0, 0, 0, 90))
        img.paste(box, (ax, ay))

        y = 604
        block = info_lines or []
        for line in block:
            label, value, accent = line
            if label is None:
                draw.text((30, y), value, font=font(FONT_UI_B, 26), fill=(238, 238, 238, 255))
                y += 38
            else:
                draw.text((30, y), label + ": ", font=font(FONT_UI, 21),
                          fill=(FOCUS[0], FOCUS[1], FOCUS[2], 255))
                draw.text((30 + text_w(draw, label + ": ", font(FONT_UI, 21)), y), value,
                          font=font(FONT_UI, 21), fill=(226, 226, 226, 255))
                y += 30

    # the list: x 594..1920, rows 75, top 100, bottom 80
    x0, x1 = 594, W - 0
    top, bottom = 100, H - 80
    visible = (bottom - top) // 75
    start = max(0, min(len(items) - visible, focus - 4)) if len(items) > visible else 0
    rows = items[start:start + visible]
    for i, item in enumerate(rows):
        y = top + i * 75
        absolute = start + i
        focused = absolute == focus
        if focused:
            draw.rectangle([x0, y, x1, y + 74], fill=FOCUS + (150,))
        icon = item["art"].get("icon")
        if icon:
            tile = _art(icon, (32, 32))
            tint = Image.new("RGB", (32, 32), (68, 68, 68))
            tile = Image.blend(tile, tint, 0.55) if not focused else tile
            img.paste(tile, (x0 + 35, y + 21))

        label = label_fn(item) if label_fn else item["label_plain"]
        draw.text((x0 + 105, y + 21), truncate(draw, label, font(FONT_UI, 30), 1000),
                  font=font(FONT_UI, 30), fill=(245, 245, 245, 255))
        l2 = label2_fn(item) if label2_fn else item.get("_label2", "")
        if l2:
            right = W - 40
            lw = text_w(draw, l2, font(FONT_UI, 20))
            draw.text((right - lw, y + 27), l2, font=font(FONT_UI, 20),
                      fill=(235, 235, 235, 255) if focused else (160, 160, 160, 255))

    if len(items) > start + visible:
        # scrollbar
        draw.rectangle([W - 22, 100, W - 14, H - 80], fill=(0, 0, 0, 90))
        frac = visible / float(len(items))
        bar_h = int((H - 180) * frac)
        bar_y = 100 + int((H - 180 - bar_h) * (start / float(max(1, len(items) - visible))))
        draw.rectangle([W - 22, bar_y, W - 14, bar_y + bar_h], fill=(120, 120, 120, 160))

    img = top_bar(img.convert("RGB"), crumb, "%d / %d" % (focus + 1, len(items)), "16:41")
    img = bottom_bar(img)
    return img


# ---------------------------------------------------------------- annotations
def annotate(img, notes, marks=()):
    """Append an annotation strip; `marks` are (x, y, number) callouts."""
    img = img.convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    for x, y, number in marks:
        r = 19
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 45, 143, 255))
        n = str(number)
        f = font(FONT_UI_B, 22)
        tw = draw.textlength(n, font=f)
        draw.text((x - tw / 2, y - 14), n, font=f, fill=(255, 255, 255, 255))

    strip_h = 46 + 30 * len(notes)
    canvas = Image.new("RGBA", (W, H + strip_h), (12, 12, 15, 255))
    canvas.paste(img, (0, 0))
    sd = ImageDraw.Draw(canvas)
    sd.rectangle([0, H, W, H + 3], fill=(255, 45, 143, 255))
    y = H + 16
    for i, note in enumerate(notes, 1):
        sd.text((30, y), str(i), font=font(FONT_UI_B, 19), fill=(255, 45, 143, 255))
        sd.text((54, y), note, font=font(FONT_UI, 19), fill=(215, 215, 215, 255))
        y += 30
    return canvas.convert("RGB")


# -------------------------------------------------------------------- screens
def build_current():
    os.makedirs(OUT_CURRENT, exist_ok=True)
    root = capture("root")
    hub = capture("packs_menu")
    _patch_archive(PACK)
    tracks = capture("archive_item", id=PACK["identifier"])
    dls = downloads_screen()
    about = capture("about")
    latest_empty = empty_latest()

    def save(img, name):
        path = os.path.join(OUT_CURRENT, name)
        img.save(path, "PNG", optimize=True)
        print("wrote", path)

    save(draw_iconwall(root, focus=0, crumb="Programs / Rave Player"), "root.png")
    save(draw_iconwall(hub, focus=0, crumb="Programs / Rave Player / Tape Packs"), "packs.png")
    save(draw_iconwall(dls, focus=0, crumb="Programs / Rave Player / Favourites / Downloads"),
         "downloads.png")
    save(draw_iconwall(about, focus=0, crumb="Programs / Rave Player / About & Sources"), "about.png")
    save(draw_iconwall([], focus=0, crumb="Programs / Rave Player / Latest"), "empty.png")

    info = [
        (None, PACK["title"].replace(" – ", " — ")[:44], None),
        ("Artist", "—", None),
        ("Album", PACK["identifier"].replace("-", " ")[:42], None),
        ("Duration", "43:57", None),
    ]
    save(draw_list(tracks, focus=0, crumb="Programs / Rave Player", info_lines=info,
                   label_fn=lambda item: item["label_plain"], label2_fn=lambda item: ""),
         "tracks.png")

    # context menu over the track list
    base = draw_list(tracks, focus=0, crumb="Programs / Rave Player", info_lines=info)
    save(draw_context(base, tracks[0]["context"], title="Tape 1 (A) — Vinylgroover"), "context.png")
    return {"root": root, "hub": hub, "tracks": tracks, "downloads": dls,
            "about": about, "empty": latest_empty, "pack": PACK}


def draw_context(base, entries, title=""):
    img = base.convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 110))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img, "RGBA")
    rows = [e[0] for e in entries]
    # Estuary appends its own listitem actions under the add-on entries
    rows += ["Play", "Queue item", "Information"]
    ph = 46 + 65 * len(rows)
    px, py = 620, 176
    panel = Image.new("RGBA", (450, ph), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rectangle([0, 0, 449, ph - 1], fill=(22, 22, 26, 250), outline=(255, 255, 255, 30))
    pd.text((24, 14), truncate(pd, title, font(FONT_UI_B, 19), 400),
            font=font(FONT_UI_B, 19), fill=(200, 200, 200, 255))
    for i, row in enumerate(rows):
        y = 46 + i * 65
        if i == 0:
            pd.rectangle([0, y, 449, y + 64], fill=FOCUS + (150,))
        pd.text((24, y + 21), row, font=font(FONT_UI, 23), fill=(240, 240, 240, 255))
    img.alpha_composite(panel, (px, py))
    return img.convert("RGB")


def build_proposed():
    os.makedirs(OUT_PROPOSED, exist_ok=True)
    root = capture("root")
    hub = capture("packs_menu")
    _patch_archive(PACK)
    tracks = capture("archive_item", id=PACK["identifier"])
    dls = downloads_screen()
    about = capture("about")

    def save(img, name, notes=None, marks=()):
        clean = img
        if notes:
            img = annotate(img, notes, marks)
        for path, out in ((os.path.join(OUT_PROPOSED, name + ".png"), img),
                          (os.path.join(OUT_PROPOSED, name + "-clean.png"), clean)):
            out.save(path, "PNG", optimize=True)
            print("wrote", path)

    # 1. card art: a 4:3 cut of the destination fanart fills the 160x130 art
    #    box; the label gains a grey kicker (wraps to two lines in the card).
    kickers = {
        "Latest": "new packs, shows, radio",
        "Surprise Me": "random tape pack",
        "Tape Packs": "1990–2004",
        "Mixes & Shows": "podcasts · DNB · Moxser",
        "Live Radio": "Kool · Rinse · 9 genres",
        "Curated Gems": "pirate tapes · rave archive",
        "Favourites": "saved packs and shows",
        "Search the Archive": "every tape pack",
        "About & Sources": "version · credits · sources",
    }

    def kicker(item):
        tail = kickers.get(item["label_plain"], "")
        return item["label_plain"] + ("  ·  " + tail if tail else "")

    def card(item):
        fan = item["art"].get("fanart")
        if fan and os.path.exists(fan):
            return card_slot(fan, 1.06)
        return None

    img = draw_iconwall(root, focus=0, card_art_fn=card, label_fn=kicker)
    save(img, "root", [
        "Card art is a 4:3 cut of the destination fanart, so it fills Estuary's 160×130 art box.",
        "Today a 256² sticker sits at 130×130 inside a 396×245 card: 55% of every card is empty.",
        "Labels gain a grey kicker — one string, wraps to two lines in the card, one line in a list.",
        "Nine doors now say what is behind them without a second screen.",
    ], marks=[(120, 230, 1), (300, 430, 2), (200, 490, 3)])

    # 2. track list: Label2 carries duration; the panel is fed real fields.
    def duration(item):
        seconds = item["info"].get("duration")
        return "%d:%02d" % (seconds // 60, seconds % 60) if seconds else ""

    info = [
        (None, "Tape 1 (A) — Vinylgroover", None),
        ("Artist", "Vinylgroover", None),
        ("Album", "Dreamscape XII — The August Bank Holiday Showcase", None),
        ("Year", "1994", None),
        ("Genre", "Hardcore / Jungle", None),
        ("Duration", "43:57", None),
    ]
    img = draw_list(tracks, focus=0, info_lines=info,
                    poster_path=os.path.join(ASSETS, "cover-dreamscape12-front.jpg"),
                    label2_fn=duration)
    save(img, "tracks", [
        "Label2 carries duration: Estuary draws that column on every row and it is empty today.",
        "The panel is a spec sheet — Track / Artist / Album / Year / Genre / Duration — and Estuary",
        "fills only what the InfoTag has. Today Artist, Year and Genre are blank and Album is a slug.",
        "The 540×470 art is the item's own pack front (1699×2485) instead of archive's 180px thumb.",
        "Tape and side stay in the label: they are the only track identity the archive gives us.",
    ], marks=[(1700, 200, 1), (300, 780, 2), (300, 980, 3), (250, 350, 4), (800, 200, 5)])

    # 3. downloads: a playable list, so declare songs and use Label2.
    def dl_label(item):
        return item["label_plain"].split("  (")[0]

    def dl_label2(item):
        raw = item["label_plain"]
        size = ""
        if "(" in raw and raw.endswith(")"):
            size = raw[raw.rindex("(") + 1:-1]
        if "(missing)" in raw:
            return "missing"
        comment = item["comment"]
        parts = [p.strip() for p in comment.split("·")] if "Downloaded" in comment else []
        date = parts[-1][:10] if parts else ""
        return " · ".join(bit for bit in (size, date) if bit)

    info_dl = [
        (None, "Downloads", None),
        ("On device", "3 files · 87.0 MB", None),
        ("Newest", "Dreamscape 19 — 31 Oct 2026", None),
        ("Missing", "1 entry — delete or download again", None),
    ]
    img = draw_list(dls, focus=0, crumb="Programs / Rave Player / Favourites / Downloads",
                    info_lines=info_dl, label_fn=dl_label, label2_fn=dl_label2,
                    poster_path=os.path.join(ROOT, "resources", "art", "tapepacks.png"))
    save(img, "downloads", [
        "Favourites → Downloads is a list of playable files, but the route declares",
        "setContent(\"files\"), so Kodi gives it the folder grid: no duration column, no music panel.",
        "Declaring \"songs\" (as Favourites already does) restores the list, Label2 and the panel.",
        "Size and date move to Label2; the label keeps the title only.",
    ], marks=[(1200, 200, 1), (300, 780, 2)])

    # 4. about: grouped source families instead of 15 near-identical rows
    groups = [
        ("Internet Archive", "tape packs · rave tapes · 8,400 sets", "rave.png", "fanart-tapepacks.jpg"),
        ("Mixcloud", "Rave Archive UK · GetDarker", "mixes.png", "fanart-mixes.jpg"),
        ("Radio directory", "Kool · Rinse · 9 genre tags", "radio.png", "fanart-live.jpg"),
        ("Moxser · Hardscore", "mix archives · direct MP3s", "hardscore.png", "fanart-hardscore.jpg"),
        ("Podcast feeds", "Jungle Lab · Viper · Toro", "radio.png", "fanart-hub-shows.jpg"),
        ("Pirate Radio Archives", "Risk FM · Weekend Rush · Flava FM", "pirate-archive.png",
         "fanart-pirate-archive.jpg"),
        ("Toronto Mixtape Archive", "1990s Toronto jungle and house", "toronto.png", "fanart-toronto.jpg"),
        ("Credits & licence", "GPL-3.0 · 3.9.36 · GitHub", "about.png", "fanart-about.jpg"),
    ]
    fake = []
    for name, sub, icon, fan in groups:
        fake.append({
            "label": name, "label_plain": name, "isFolder": True, "url": "", "context": [],
            "info": {}, "comment": "", "content": "files",
            "art": {"icon": os.path.join(ROOT, "resources", "art", icon),
                    "fanart": os.path.join(ROOT, "resources", "art", fan)},
        })
    img = draw_iconwall(fake, focus=0, crumb="Programs / Rave Player / About & Sources",
                        label_fn=lambda item: item["label_plain"] + "  ·  " + dict(
                            (g[0], g[1]) for g in groups)[item["label_plain"]],
                        card_art_fn=lambda item: card_slot(item["art"]["fanart"], 1.0))
    save(img, "about", [
        "Fifteen rows become eight doors: one card per source family, kicker says what it carries.",
        "Today 15 rows reuse 6 icons — radio.png six times — so the grid reads as one repeated card.",
        "Long labels (\"Source: Toronto Rave Mixtape Archive\", 36 chars) overflow the 350px plate;",
        "short names plus a kicker fit and still say the same thing.",
    ], marks=[(200, 430, 1), (620, 430, 2)])

    # 5. empty state
    def state(label, kicker_text, icon, fanart):
        return {"label": label, "label_plain": label, "isFolder": True, "url": "",
                "context": [], "info": {}, "comment": "", "content": "files",
                "_kicker": kicker_text,
                "art": {"icon": os.path.join(ROOT, "resources", "art", icon),
                        "fanart": os.path.join(ROOT, "resources", "art", fanart)}}

    empty_items = [
        state("Nothing came back", "archive.org did not answer", "search.png", "fanart-latest.jpg"),
        state("Try again", "reload this folder", "rave.png", "fanart-latest.jpg"),
        state("Search instead", "every tape pack on archive.org", "search.png", "fanart-search.jpg"),
        state("Check sources", "what the add-on talks to", "about.png", "fanart-about.jpg"),
    ]
    img = draw_iconwall(empty_items, focus=0, crumb="Programs / Rave Player / Latest",
                        label_fn=lambda item: item["label_plain"] + "  ·  " + item["_kicker"],
                        card_art_fn=lambda item: card_slot(item["art"]["fanart"], 0.9))
    save(img, "empty", [
        "Today: a four-second toast and an empty folder; nothing to act on and nothing to read.",
        "A failed load should leave rows you can act on — retry, search, check the source list.",
        "Same shape for no favourites, no downloads and no search results.",
    ], marks=[(250, 430, 1), (650, 430, 2)])

    # 6. context menu: verb-first, ordered, queue early
    img = draw_context(draw_list(tracks, focus=0, info_lines=info), [
        ("Play from here", "RunPlugin(...)"),
        ("Queue this pack", "RunPlugin(...)"),
        ("Shuffle pack", "RunPlugin(...)"),
        ("Add to favourites", "RunPlugin(...)"),
        ("Download this track", "RunPlugin(...)"),
        ("Go to source", "RunPlugin(...)"),
    ], title="Tape 1 (A) — Vinylgroover")
    save(img, "context-menu", [
        "Kodi's context dialog is a flat 450px list: we cannot style it or nest it, only fill and order it.",
        "Today's order is emission order (Play all from here · Add to favourites · Download).",
        "Verb-first, most-used first, Queue high — and destructive actions only where they belong.",
        "Label budget 22 characters; no icons, no second column.",
    ], marks=[(700, 300, 1), (700, 430, 2)])

    return {"root": root, "hub": hub, "tracks": tracks, "downloads": dls, "about": about}


# ------------------------------------------------------- bold ideas (renders)
def now_playing_overlay():
    """Bold idea A: a WindowXML 'tape deck' overlay the add-on actually owns."""
    base = backdrop(os.path.join(ROOT, "resources", "art", "fanart-tapepacks.jpg"), 0.28)
    base = base.filter(ImageFilter.GaussianBlur(6))
    img = base.convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle([0, 0, W, H], fill=(0, 0, 0, 120))

    panel_w, panel_h = 1240, 560
    px, py = (W - panel_w) // 2, (H - panel_h) // 2 - 20
    draw.rectangle([px, py, px + panel_w, py + panel_h], fill=(14, 14, 18, 246),
                   outline=(232, 255, 0, 255), width=3)
    draw.rectangle([px, py, px + panel_w, py + 46], fill=(232, 255, 0, 255))
    draw.text((px + 24, py + 10), "NOW PLAYING  ·  SIDE A", font=font(FONT_MONO, 24),
              fill=(9, 9, 12, 255))
    draw.text((px + panel_w - 190, py + 10), "RP-12", font=font(FONT_MONO, 24), fill=(9, 9, 12, 255))

    cover = _art(os.path.join(ASSETS, "cover-dreamscape12-front.jpg"), (300, 440))
    img.paste(cover, (px + 34, py + 78))
    draw.rectangle([px + 34, py + 78, px + 334, py + 518], outline=(255, 255, 255, 40))

    tx = px + 372
    draw.text((tx, py + 92), "VINYLGROOVER", font=font(FONT_DISPLAY, 58), fill=(240, 238, 227, 255))
    draw.text((tx, py + 160), "TAPE 1 (A) — DREAMSCAPE XII", font=font(FONT_MONO, 24),
              fill=(232, 255, 0, 255))
    draw.text((tx, py + 196), "26 AUG 1994  ·  THE SANCTUARY, MILTON KEYNES",
              font=font(FONT_MONO, 19), fill=(168, 163, 153, 255))
    draw.line([tx, py + 236, tx + 800, py + 236], fill=(255, 255, 255, 40), width=1)

    # reel-to-reel motif
    for i, cx in enumerate((tx + 90, tx + 330)):
        r = 64
        draw.ellipse([cx - r, py + 300 - r, cx + r, py + 300 + r], outline=(232, 255, 0, 160), width=3)
        draw.ellipse([cx - 12, py + 288, cx + 12, py + 312], fill=(232, 255, 0, 200))
    draw.text((tx + 430, py + 268), "43:57", font=font(FONT_MONO, 46), fill=(240, 238, 227, 255))
    draw.text((tx + 430, py + 330), "TAPE 1 OF 8  ·  ARCHIVE.ORG", font=font(FONT_MONO, 19),
              fill=(168, 163, 153, 255))

    # progress
    draw.rectangle([tx, py + 400, tx + 810, py + 418], fill=(255, 255, 255, 30))
    draw.rectangle([tx, py + 400, tx + 300, py + 418], fill=(232, 255, 0, 255))
    draw.text((tx, py + 434), "12:04 / 43:57", font=font(FONT_MONO, 19), fill=(168, 163, 153, 255))
    draw.text((tx, py + 480), "INFO  liner notes      BACK  dismiss", font=font(FONT_MONO, 17),
              fill=(140, 140, 150, 255))
    return img.convert("RGB")


def focus_transition_strip():
    """Bold idea B: three frames of what a focus-driven fanart crossfade needs."""
    frames = []
    for focus in (2, 3, 4):
        items = capture("root")
        frames.append((draw_iconwall(items, focus=focus), items[focus]["label_plain"]))
    strip_w, strip_h = 620, 349
    canvas = Image.new("RGB", (W, 560), (12, 12, 15))
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 24), "FOCUS → FANART: what the skin costs us, and what we can supply",
              font=font(FONT_UI_B, 30), fill=(240, 240, 240))
    draw.text((40, 66), "Estuary cross-fades the focused item's fanart in 200–300 ms. The add-on cannot animate it —",
              font=font(FONT_UI, 20), fill=(170, 170, 170))
    draw.text((40, 94), "it can only make sure every row has a *different* still to fade to, and that the stills share a grid.",
              font=font(FONT_UI, 20), fill=(170, 170, 170))
    for i, (frame, label) in enumerate(frames):
        thumb = frame.resize((strip_w, strip_h), Image.LANCZOS)
        x = 40 + i * (strip_w + 20)
        canvas.paste(thumb, (x, 150))
        draw.rectangle([x, 150, x + strip_w, 150 + strip_h], outline=(60, 60, 60))
        draw.text((x, 510), label, font=font(FONT_MONO, 20), fill=(232, 255, 0))
    return canvas


# ------------------------------------------------------------------ before/after
def board():
    names = ("root", "tracks", "downloads")
    cur = {n: Image.open(os.path.join(OUT_CURRENT, n + ".png")) for n in names}
    pro = {n: Image.open(os.path.join(OUT_PROPOSED, n + "-clean.png")) for n in names}

    tw, th = 750, 422
    pad = 34
    gap = 16
    bw = pad * 2 + tw * 2 + gap
    rows = [
        ("root", "ROOT  ·  nine doors in Estuary's IconWall",
         "Before: a 256² sticker at 130×130 inside a 396×245 card — over half of every card is empty panel, and the label is one word.",
         "After: 1.23:1 card art cut from each destination's fanart fills the art box; a grey kicker names what is behind the door."),
        ("tracks", "TRACKS  ·  Dreamscape XII, fifteen tapes",
         "Before: label only. Label2 (Estuary's right column) is empty; the info panel shows a slug album, no artist, year or genre.",
         "After: Label2 carries duration; Artist / Year / Genre / real Album feed the panel; the 540×470 art is the pack front, not a 180px thumb."),
        ("downloads", "DOWNLOADS  ·  three files, one missing",
         "Before: a list of playable files rendered as a folder grid (setContent files), so no duration, no size column, no music panel.",
         "After: setContent songs gives the list, Label2 carries size and date, and the panel summarises the device."),
    ]
    head = 196
    row_h = 30 + 24 + th + 64
    bh = head + row_h * len(rows) + 96
    canvas = Image.new("RGB", (bw, bh), (10, 10, 13))
    draw = ImageDraw.Draw(canvas)
    draw.text((pad, 34), "RAVE PLAYER — LOOK & FEEL 2026", font=font(FONT_DISPLAY, 58),
              fill=(240, 238, 227))
    draw.text((pad, 108), "Every panel is the add-on's real ListItem output, rendered by docs/look-dev/tools/make-look-shots.py",
              font=font(FONT_UI, 21), fill=(170, 170, 170))
    draw.text((pad, 140), "through test/stubs, in Estuary master's own geometry: view 52 IconWall cards, view 55 WideList rows, 75px.",
              font=font(FONT_UI, 21), fill=(170, 170, 170))

    y = head
    for name, title, before, after in rows:
        draw.text((pad, y), title, font=font(FONT_UI_B, 27), fill=(232, 255, 0))
        y += 34
        draw.text((pad, y), "BEFORE  ·  3.9.36", font=font(FONT_MONO, 18), fill=(255, 45, 143))
        draw.text((pad + tw + gap, y), "AFTER  ·  proposal", font=font(FONT_MONO, 18), fill=(34, 230, 255))
        y += 26
        canvas.paste(cur[name].resize((tw, th), Image.LANCZOS), (pad, y))
        canvas.paste(pro[name].resize((tw, th), Image.LANCZOS), (pad + tw + gap, y))
        draw.rectangle([pad, y, pad + tw, y + th], outline=(64, 64, 70))
        draw.rectangle([pad + tw + gap, y, pad + tw + gap + tw, y + th], outline=(64, 64, 70))
        y += th + 10
        draw.text((pad, y), textwrap.fill(before, 92)[:200].split("\n")[0],
                  font=font(FONT_UI, 17), fill=(150, 150, 150))
        draw.text((pad + tw + gap, y), textwrap.fill(after, 92)[:200].split("\n")[0],
                  font=font(FONT_UI, 17), fill=(150, 150, 150))
        y += 24
        for line_no, line in enumerate(textwrap.wrap(before, 92)[1:3]):
            draw.text((pad, y + line_no * 19), line, font=font(FONT_UI, 17), fill=(150, 150, 150))
        for line_no, line in enumerate(textwrap.wrap(after, 92)[1:3]):
            draw.text((pad + tw + gap, y + line_no * 19), line, font=font(FONT_UI, 17),
                      fill=(150, 150, 150))
        y += 44

    draw.text((pad, bh - 62),
              "Full audit, eight ranked recommendations and two bolder ideas: docs/LOOK-AND-FEEL-2026.md",
              font=font(FONT_UI_B, 20), fill=(232, 255, 0))
    path = os.path.join(LOOK, "board-before-after.png")
    canvas.save(path, "PNG", optimize=True)
    print("wrote", path)


def main():
    data = build_current()
    build_proposed()
    os.makedirs(OUT_PROPOSED, exist_ok=True)
    now_playing_overlay().save(os.path.join(OUT_PROPOSED, "now-playing-overlay.png"), "PNG", optimize=True)
    focus_transition_strip().save(os.path.join(OUT_PROPOSED, "focus-transition.png"), "PNG", optimize=True)
    with open(os.path.join(LOOK, "capture.json"), "w", encoding="utf-8") as handle:
        json.dump({key: value for key, value in data.items() if key != "pack"},
                  handle, indent=2, default=str)
    board()


if __name__ == "__main__":
    main()
