# -*- coding: utf-8 -*-
"""Curated Mixcloud sources.

Mixcloud's public API needs no key and exposes the cloudcast page/title/thumb.
There is deliberately no audio extraction here: Mixcloud streams are HLS and
the sanctioned player is their widget, which Kodi cannot embed.  The add-on
therefore lists only metadata; routes hand the cloudcast page/path to the
official ``plugin.audio.mixcloud`` add-on and hide the row if it is not
installed (see ``handoff.py``).
"""

import urllib.parse

from . import http

API = "https://api.mixcloud.com"
ACCOUNT_TTL = 60 * 60
MAX_CLOUDS = 1000

SOURCES = [
    {
        "key": "rave-archive-uk",
        "name": "Rave Archive UK",
        "account": "ravearchiveuk",
        "plot": "Rave Archive UK on Mixcloud — oldskool, hardcore, jungle and drum & bass.",
    },
    {
        "key": "getdarker",
        "name": "GetDarker",
        "account": "getdarker",
        "plot": "GetDarker on Mixcloud — dubstep, garage and underground sets.",
    },
]
SOURCES_BY_KEY = dict((source["key"], source) for source in SOURCES)


def registry():
    return list(SOURCES)


def source(key):
    return SOURCES_BY_KEY.get(str(key or ""))


def _clean(value):
    return " ".join(str(value or "").split())


def _page_url(value):
    text = str(value or "").strip()
    try:
        split = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if split.scheme == "https" and (split.hostname or "").lower() in (
            "www.mixcloud.com", "mixcloud.com"):
        return text
    return ""


def cloudcasts(account, limit=MAX_CLOUDS):
    """Return public cloudcasts for a curated account; [] on any failure."""
    try:
        limit = max(1, min(int(limit), MAX_CLOUDS))
    except (TypeError, ValueError):
        limit = MAX_CLOUDS
    account = str(account or "").strip().strip("/")
    if not account or "/" in account or not all(
            char.isalnum() or char in "-_" for char in account):
        return []
    url = "%s/%s/cloudcasts/?limit=%d" % (API, urllib.parse.quote(account), limit)
    data = http.fetch_json(url, timeout=20, ttl=ACCOUNT_TTL)
    if not isinstance(data, dict):
        return []
    rows = []
    for entry in data.get("data") or []:
        if not isinstance(entry, dict):
            continue
        page = _page_url(entry.get("url"))
        if not page:
            continue
        user = entry.get("user") or {}
        pictures = entry.get("pictures") or {}
        thumb = pictures.get("medium") or pictures.get("thumbnail") or ""
        rows.append({
            "title": _clean(entry.get("name")) or "Untitled",
            "url": page,
            "user": _clean(user.get("name")),
            "created": str(entry.get("created_time") or ""),
            "duration": entry.get("audio_length"),
            "thumb": thumb if isinstance(thumb, str) else "",
        })
    return rows
