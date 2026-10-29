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


# --------------------------------------------------------------------------- jungletapes.com

JT_BASE = "https://jungletapes.com"
JT_SHOW_RE = re.compile(r'href="/show/([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
JT_MP3_RE = re.compile(r'href="([^"]+\.mp3)"', re.IGNORECASE)


def _strip_tags(value):
    return re.sub(r"<[^>]+>", "", value or "").strip()


def jungle_shows():
    """Toronto jungle/DnB radio shows digitised from cassette — one page each.

    The site's front page only lists the newest two, so the sitemap is the
    catalogue: 300+ /show/ pages.
    """
    xml = http.fetch(JT_BASE + "/sitemap.xml", timeout=30)
    slugs = []
    if xml:
        slugs = re.findall(r"<loc>[^<]*?/show/([^<]+)</loc>", xml)
    if not slugs:
        html = http.fetch(JT_BASE + "/", timeout=25) or ""
        slugs = [slug for slug, _ in JT_SHOW_RE.findall(html)]
    shows, seen = [], set()
    for slug in slugs:
        slug = slug.strip().strip("/")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        shows.append({"key": slug, "name": _jt_label(slug)})
    shows.sort(key=lambda item: item["name"], reverse=True)
    return shows


def _jt_label(slug):
    text = slug.replace("tapes/", "").replace("_", " ").replace("-", " ")
    text = re.sub(r"\b000000\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1].upper() + text[1:] if text else slug


def jungle_tracks(slug):
    html = http.fetch(JT_BASE + "/show/" + urllib.parse.quote(slug), timeout=25)
    if not html:
        return []
    tracks = []
    for url in JT_MP3_RE.findall(html):
        if url.startswith("//"):
            url = "https:" + url
        filename = urllib.parse.unquote(url.rsplit("/", 1)[-1]).rsplit(".", 1)[0]
        tracks.append({"name": _pretty(filename), "url": url})
    return tracks


# --------------------------------------------------------------------------- torontoravemixtapearchive.com

TR_BASE = "https://www.torontoravemixtapearchive.com"
TR_MP3_RE = re.compile(r'href="(/files/mixtapes?/[^"]+\.mp3)"', re.IGNORECASE)


def toronto_tracks():
    """Flat index of Toronto rave mixtapes."""
    html = http.fetch(TR_BASE + "/", timeout=25)
    if not html:
        return []
    tracks = []
    for path in TR_MP3_RE.findall(html):
        filename = urllib.parse.unquote(path.rsplit("/", 1)[-1]).rsplit(".", 1)[0]
        tracks.append({"name": _pretty(filename), "url": TR_BASE + urllib.parse.quote(path, safe="/:~")})
    return tracks
