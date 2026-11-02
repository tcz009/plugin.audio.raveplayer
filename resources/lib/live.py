# -*- coding: utf-8 -*-
"""Live station identity and bounded reconnect playlist helpers.

3.9.23/3.9.24 tried a local M3U; Kodi's PAPlayer rejected it through
setResolvedUrl. 3.9.26 uses a finite PlayList of direct stream URLs and
``xbmc.Player().play(playlist)`` instead. A resolver is called for every
entry, so a changing/stale live URL is refreshed while the playlist is built.
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
LIVE_RECONNECT_ENTRIES = 6
MAX_RECONNECT_ENTRIES = 12
NOSHOUT_SUFFIX = "|noshout=true"


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


def clean_url(stream):
    """Public http(s) URL only; no newlines/control characters."""
    text = str(stream or "").strip()
    if (not text or "\n" in text or "\r" in text
            or _CONTROL_RE.search(text)):
        return ""
    parts = _stream_parts(text)
    if parts is None or parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    return text


def reconnect_urls(stream, station, resolver=None, entries=LIVE_RECONNECT_ENTRIES):
    """Return a finite list of direct stream URLs for one live station.

    ``resolver`` is called once per entry (if supplied) so a URL that rotates
    or was stale at the previous attempt is refreshed while the playlist is
    built. A failed/empty resolve falls back to the last known direct URL.
    """
    base = clean_url(stream)
    if not base:
        return []
    try:
        count = max(1, min(int(entries), MAX_RECONNECT_ENTRIES))
    except (TypeError, ValueError):
        count = LIVE_RECONNECT_ENTRIES
    urls = []
    current = base
    for _ in range(count):
        if resolver is not None:
            try:
                candidate = clean_url(resolver(station))
            except Exception:  # noqa: BLE001 - resolver is best effort
                candidate = ""
            if candidate:
                current = candidate
        urls.append(current)
    return urls


def playback_url(stream):
    """Play-time URL with Kodi's per-item shoutcast off switch.

    The stored/config URL stays clean. Kodi must receive the option in its URL
    protocol-option syntax; otherwise its audio file layer re-opens the Rinse
    proxy as Shoutcast, opts into ICY metadata and replaces our fixed tags.
    """
    url = clean_url(stream)
    if not url:
        return ""
    if url.lower().endswith(NOSHOUT_SUFFIX):
        return url
    if "|" in url:
        if "noshout=true" in url.lower():
            return url
        return url + "&noshout=true"
    return url + NOSHOUT_SUFFIX
