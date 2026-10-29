# -*- coding: utf-8 -*-
"""Internet Archive provider.

The Archive's advancedsearch and metadata endpoints are public, stable and
need no key, which makes them a much better backbone than scraping the dead
fan sites the 2014 add-on relied on.
"""

import re
import urllib.parse

from . import http

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/%s"
DOWNLOAD_URL = "https://archive.org/download/%s/%s"
THUMB_URL = "https://archive.org/services/img/%s"

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".ogg", ".flac", ".wav", ".aac", ".opus")
FIELDS = ["identifier", "title", "year", "date", "downloads", "mediatype", "creator", "description"]


def thumb(identifier):
    return THUMB_URL % identifier


def search(query, page=1, rows=50, sort="downloads desc"):
    """Return (docs, total) for an Archive.org full-text query."""
    params = [
        ("q", query),
        ("rows", str(rows)),
        ("page", str(page)),
        ("output", "json"),
        ("sort[]", sort),
    ]
    params += [("fl[]", field) for field in FIELDS]
    url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
    data = http.fetch_json(url, timeout=25)
    if not data or "response" not in data:
        return [], 0
    response = data["response"]
    return response.get("docs", []), int(response.get("numFound", 0) or 0)


def item(identifier):
    """Return the metadata dict for one Archive.org item, or {}."""
    return http.fetch_json(METADATA_URL % identifier, timeout=25) or {}


def audio_files(identifier):
    """Return playable audio files for an item, best format first, de-duplicated."""
    data = item(identifier)
    files = data.get("files", [])
    by_name = {}
    for entry in files:
        name = entry.get("name") or ""
        lower = name.lower()
        if not lower.endswith(AUDIO_EXTENSIONS):
            continue
        if lower.endswith(("_spectrogram.png", "_sample.mp3")):
            continue
        # The Archive lists both the original and derived files; prefer the
        # original of each track and drop duplicates that differ only by dir.
        key = lower.split("/")[-1]
        existing = by_name.get(key)
        rank = _rank(entry)
        if existing is None or rank < existing[0]:
            by_name[key] = (rank, entry)
    ordered = [entry for _, entry in sorted(by_name.values(), key=lambda pair: pair[0])]
    item_title = " ".join(str(data.get("metadata", {}).get("title", "")).split())
    return [
        {
            "name": entry.get("name"),
            "title": _track_title(entry, item_title),
            "size": _as_int(entry.get("size")),
            "length": entry.get("length"),
            "url": DOWNLOAD_URL % (identifier, urllib.parse.quote(entry.get("name"))),
        }
        for entry in ordered
    ]


def _track_title(entry, item_title):
    """Return something a human can pick from a list.

    Archive rips are inconsistent: sometimes the only useful label is the
    filename ("TAPE 3 - MASTERVIBE.mp3"), sometimes every file repeats the
    same generic title ("Dreamscape XIX Arena 2"). Prefer a descriptive
    filename, then a distinct per-track title, then a tidied filename.
    """
    pretty = _pretty(entry.get("name"))
    title = " ".join(str(entry.get("title") or "").split())
    if _is_descriptive(pretty):
        return pretty
    if title and title != item_title:
        return title
    return pretty


def _is_descriptive(text):
    if not text or len(text) < 5:
        return False
    if re.match(r"^(track|audio|file|part)?\s*\d+$", text, re.IGNORECASE):
        return False
    return bool(re.search(r"[A-Za-z]", text))


def _rank(entry):
    source = (entry.get("source") or "").lower()
    if source == "original":
        return 0
    if entry.get("format", "").lower() in ("vbr mp3", "mp3"):
        return 1
    return 2


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _pretty(name):
    if not name:
        return "Untitled"
    base = name.split("/")[-1]
    for extension in AUDIO_EXTENSIONS:
        if base.lower().endswith(extension):
            base = base[: -len(extension)]
    return base.replace("_", " ").strip()
