# -*- coding: utf-8 -*-
"""Legacy source that is genuinely still alive: ravetapepacks.com.

The 2014 add-on scraped ~30 fan sites; almost all are gone. This one survived
and still serves full tape packs. Its MP3s are hotlink-protected — a bare GET
returns 403 — so playback URLs carry a Referer suffix that Kodi turns into a
real header.
"""

import re
import urllib.parse

from . import http

BASE = "https://www.ravetapepacks.com/"
REFERER_SUFFIX = "|Referer=https://www.ravetapepacks.com/&User-Agent=Mozilla/5.0"

MUSIC_RE = re.compile(
    r"(?:https?://www\.ravetapepacks\.com)?/music/([^/\"'<>]+)/([^\"'<>]+?\.mp3)",
    re.IGNORECASE,
)


def _pretty(text):
    text = urllib.parse.unquote(text)
    text = text.replace("_", " ")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[0-9])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[A-Za-z])(?=[0-9])", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _pack_name(raw):
    """Folder names are camel-cased and run words together; space them out."""
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)
    name = re.sub(r"(?<=[0-9])(?=[A-Z])", " ", name)
    name = re.sub(r"(?<=[A-Za-z])(?=[0-9])", " ", name)
    name = urllib.parse.unquote(name).replace("_", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return name or raw


def packs():
    """Return [{'key': folder, 'name': label, 'tracks': [...]}, ...] sorted by name."""
    html = http.fetch(BASE, timeout=25)
    if not html:
        return []
    grouped = {}
    for pack, filename in MUSIC_RE.findall(html):
        entry = grouped.setdefault(pack, {"key": pack, "name": _pack_name(pack), "tracks": []})
        url = BASE + "music/" + urllib.parse.quote(pack) + "/" + urllib.parse.quote(filename)
        entry["tracks"].append({"name": _pretty(filename.rsplit(".", 1)[0]), "url": url})
    result = []
    for entry in grouped.values():
        entry["tracks"].sort(key=lambda track: track["name"])
        result.append(entry)
    result.sort(key=lambda entry: entry["name"].lower())
    return result


def playable(url):
    """Kodi header syntax: appends Referer so the hotlink check passes."""
    return url + REFERER_SUFFIX
