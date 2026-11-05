#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render the native-list before/after boards for docs/LOOK-OVERHAUL.md.

This is a dev-only review tool.  It reuses the 3.9.36 Estuary renderer in
``docs/look-dev/tools/make-look-shots.py`` (real ListItems captured through the
Kodi stubs) and renders a small set of screens from whichever worktree is
named by ``LOOK_REPO``.  Running it against the pristine base worktree and
against this branch produces the two halves of the board.

Usage:
    LOOK_REPO=/path/to/worktree LOOK_OUT=/path/to/out \
        python3 docs/look-overhaul/tools/make-native-shots.py

These are Estuary-geometry approximations, not device captures; the same
caveat as docs/LOOK-AND-FEEL-2026.md applies.
"""
from __future__ import annotations

import importlib.util
import os
import sys

REPO = os.path.abspath(os.environ.get("LOOK_REPO", ""))
OUT = os.path.abspath(os.environ.get("LOOK_OUT", ""))
if not REPO or not OUT:
    raise SystemExit("set LOOK_REPO and LOOK_OUT")

TOOL = os.path.join(REPO, "docs", "look-dev", "tools", "make-look-shots.py")
spec = importlib.util.spec_from_file_location("lookshots", TOOL)
shots = importlib.util.module_from_spec(spec)
sys.modules["lookshots"] = shots
spec.loader.exec_module(shots)

# The audit snapshot hardcodes 3.9.36; use the real add-on version instead.
import xml.etree.ElementTree as ET

shots.routes.kodi.ADDON_VERSION = ET.parse(
    os.path.join(REPO, "addon.xml")).getroot().get("version")

os.makedirs(OUT, exist_ok=True)


def capture(mode, **params):
    """The audit renderer drops Label2; the 2026 board needs it."""
    xbmcplugin = shots.xbmcplugin
    ui = shots.ui
    del xbmcplugin.ITEMS[:]
    del xbmcplugin.CONTENT[:]
    params["mode"] = mode
    query = "&".join("%s=%s" % (key, value) for key, value in params.items())
    shots.routes.dispatch(["plugin://plugin.audio.raveplayer/", "1", "?" + query])
    items = []
    for raw in xbmcplugin.ITEMS:
        music = raw["info"].get("music") or {}
        items.append({
            "label": raw["label"],
            "label_plain": ui.plain(raw["label"]),
            "label2": raw["label2"],
            "url": raw["url"],
            "isFolder": raw["isFolder"],
            "art": dict(raw["art"]),
            "info": dict(music),
            "comment": music.get("comment") or music.get("plot") or "",
            "context": list(raw["context"]),
            "content": xbmcplugin.CONTENT[-1] if xbmcplugin.CONTENT else "",
        })
    return items


def save(image, name):
    path = os.path.join(OUT, name)
    image.save(path, "PNG", optimize=True)
    print("wrote", path)


root = capture("root")
hub = capture("packs_menu")

shots._patch_archive(shots.PACK)
tracks = capture("archive_item", id=shots.PACK["identifier"])
about = capture("about")
shots.routes.latest.merge = lambda: []
shots.routes._latest_live_rows = lambda handle: 0
empty = capture("latest")

save(shots.draw_iconwall(root, focus=0, crumb="Programs / Rave Player"),
     "native-root.png")
save(shots.draw_iconwall(hub, focus=0,
                         crumb="Programs / Rave Player / Tape Packs"),
     "native-packs.png")

info = [
    (None, shots.PACK["title"].replace(" – ", " — ")[:44], None),
    ("Artist", "Vinylgroover", None),
    ("Album", shots.PACK["title"][:42], None),
    ("Year", "1994", None),
    ("Duration", "43:57", None),
]
save(shots.draw_list(tracks, focus=0, crumb="Programs / Rave Player",
                     info_lines=info,
                     label_fn=lambda item: item["label_plain"],
                     label2_fn=lambda item: item.get("label2", "")),
     "native-tracks.png")

save(shots.draw_list(about, focus=0,
                     crumb="Programs / Rave Player / About & Sources",
                     show_panel=False,
                     label_fn=lambda item: item["label_plain"],
                     label2_fn=lambda item: item.get("label2", "")),
     "native-about.png")

save(shots.draw_list(empty, focus=0,
                     crumb="Programs / Rave Player / Latest",
                     show_panel=False,
                     label_fn=lambda item: item["label_plain"],
                     label2_fn=lambda item: item.get("label2", "")),
     "native-empty.png")
