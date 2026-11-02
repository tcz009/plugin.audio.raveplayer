# -*- coding: utf-8 -*-
"""Fixed metadata/identity helpers for curated live radio.

3.9.23/3.9.24 tried a local M3U to reconnect dropped streams. Kodi's audio
player treats a local .m3u supplied via setResolvedUrl as a codec input
("Unable to Init Codec"), so 3.9.25 resolves the known-good direct stream
again. Reconnect is deferred to a separate tested change.
"""

from __future__ import annotations

import re
import urllib.parse

LIVE_STATION = {
    "kool": "Kool FM",
    "rinse": "Rinse FM",
}
PLACEHOLDER_RE = re.compile(r"now\s+playing\s+info\s+goes\s+here", re.I)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
SAFE_LABEL = 80


def _stream_parts(stream):
    try:
        return urllib.parse.urlsplit(str(stream or ""))
    except ValueError:
        return None


def is_live_stream(stream):
    """True for the curated Kool/Rinse proxy URLs (not arbitrary streams)."""
    parts = _stream_parts(stream)
    if parts is None:
        return False
    return (parts.scheme in ("http", "https")
            and parts.netloc.lower() == "admin.stream.rinse.fm"
            and parts.path.startswith("/proxy/")
            and any(token in parts.path.lower() for token in ("kool", "rinse")))


def station_name(stream, fallback=""):
    """Fixed station name; never return an ICY placeholder or empty text."""
    parts = _stream_parts(stream)
    path = (parts.path.lower() if parts is not None else "")
    for token, name in LIVE_STATION.items():
        if token in path:
            return name
    text = " ".join(_CONTROL_RE.sub(" ", str(fallback or "")).split())
    if text and not PLACEHOLDER_RE.search(text):
        return text[:SAFE_LABEL]
    return "Live radio"
