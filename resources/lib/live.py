# -*- coding: utf-8 -*-
"""Bounded reconnect playlists and fixed metadata for curated live radio.

Kodi's PAPlayer does not reconnect a dropped internet stream by itself: when
the Rinse proxy connection ends after a few minutes, playback stops with
"Kodi is not playing any media file".  The add-on resolves a local M3U with a
small, finite number of copies of the resolved live URL instead of one stream.
If a connection drops, Kodi advances to the next entry; when the list ends it
stops.  A user stop stops it immediately (Kodi does not advance a playlist
after Stop), and there is no infinite loop.

The same playlist carries fixed ``#EXTINF`` station labels so the stream's
placeholder ICY title is not the primary title.  The resolved ListItem also
sets fixed title/artist/album/art metadata.
"""

from __future__ import annotations

import hashlib
import os
import re
import urllib.parse

from . import kodi

LIVE_RECONNECT_ENTRIES = 6
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


def _clean_url(stream):
    text = str(stream or "").strip()
    if not text or "\n" in text or "\r" in text or _CONTROL_RE.search(text):
        return ""
    parts = _stream_parts(text)
    if parts is None or parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    return text


def playlist_text(stream, station, entries=LIVE_RECONNECT_ENTRIES):
    """Return a finite M3U body with fixed station labels and identical URLs."""
    url = _clean_url(stream)
    if not url:
        return ""
    try:
        count = max(1, min(int(entries), 12))
    except (TypeError, ValueError):
        count = LIVE_RECONNECT_ENTRIES
    name = _CONTROL_RE.sub(" ", station_name(url, station)).strip() or "Live radio"
    lines = ["#EXTM3U"]
    for _ in range(count):
        lines.append("#EXTINF:-1,%s" % name[:SAFE_LABEL])
        lines.append(url)
    return "\n".join(lines) + "\n"


def playlist_path(stream):
    """Stable temp path for one live URL (no user text in the filename)."""
    url = _clean_url(stream)
    if not url:
        return ""
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return "special://temp/raveplayer-live-%s.m3u" % digest


def write_playlist(stream, station):
    """Write the bounded M3U and return its real path, or "" on failure."""
    text = playlist_text(stream, station)
    special = playlist_path(stream)
    if not text or not special:
        return ""
    try:
        path = kodi.translate_path(special)
        if not path or not os.path.isabs(path):
            return ""
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path
    except Exception as exc:  # noqa: BLE001 - best effort; caller falls back
        kodi.log("live playlist unavailable (%s)" % exc.__class__.__name__, level=30)
        return ""
