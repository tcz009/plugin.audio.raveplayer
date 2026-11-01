# -*- coding: utf-8 -*-
"""Live radio via radio-browser.info — a community directory that stays current."""

import urllib.parse

from . import http

MIRRORS = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]

# Three mirrors are tried in sequence; keep each attempt short so a dead
# directory cannot block the plugin for a minute.
MIRROR_TIMEOUT = 8
STATIONS_TTL = 10 * 60  # station lists change slowly


def stations(tag, limit=100):
    """Return live, non-broken stations for a tag, most-clicked first."""
    limit = _clamp(limit, 100, 1000)
    query = (
        "/json/stations/search?tag=%s&limit=%d&hidebroken=true"
        "&order=clickcount&reverse=true" % (http.quote(str(tag)), limit)
    )
    return _search(query)


# Stations we know the canonical stream for. radio-browser's fuzzy name search
# returns lookalikes (KISSTORY, "Kool 97 FM" Jamaica, etc.); these are the
# current official feeds -- both Kool London and Rinse FM are served by the
# Rinse streaming proxy.
CURATED = [
    {
        "name": "Kool FM",
        "token": "kool",
        "url_resolved": "https://admin.stream.rinse.fm/proxy/kool/stream",
        "countrycode": "GB",
        "codec": "AAC+",
        "bitrate": 128,
        "favicon": "",
    },
    {
        "name": "Rinse FM",
        "token": "rinse",
        "url_resolved": "https://admin.stream.rinse.fm/proxy/rinse_uk/stream",
        "countrycode": "GB",
        "codec": "AAC+",
        "bitrate": 128,
        "favicon": "",
    },
]


def curated(name):
    """Canonical live station(s) for a known name, else []."""
    token = str(name or "").strip().lower()
    if not token:
        return []
    return [dict(station) for station in CURATED if station["token"] in token or token in station["token"]]


def stations_by_name(name, limit=20):
    """Live stations whose name matches (used for "Kool FM live now")."""
    limit = _clamp(limit, 20, 100)
    query = "/json/stations/search?name=%s&limit=%d&hidebroken=true&order=clickcount&reverse=true" % (
        http.quote(name), limit)
    return _search(query)


def _clamp(value, default, maximum):
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _search(query):
    """Try each mirror in turn; a dead mirror is not an empty result."""
    for mirror in MIRRORS:
        data = http.fetch_json(mirror + query, timeout=MIRROR_TIMEOUT, ttl=STATIONS_TTL)
        if not isinstance(data, list):
            continue
        found = []
        for station in data:
            if not isinstance(station, dict):
                continue
            if not stream_url(station):
                continue
            found.append(station)
        if found:
            return found
    return []


def stream_url(station):
    if not isinstance(station, dict):
        return ""
    url = station.get("url_resolved") or station.get("url") or ""
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if not url:
        return ""
    try:
        split = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    if split.scheme.lower() not in ("http", "https") or not split.netloc:
        return ""
    return url


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def display(station):
    if not isinstance(station, dict):
        station = {}
    name = str(station.get("name") or "Unknown station").strip() or "Unknown station"
    country = str(station.get("countrycode") or station.get("country") or "").strip()
    codec = str(station.get("codec") or "").upper()
    bitrate = _as_int(station.get("bitrate"))
    meta = " · ".join(
        part for part in (country, codec, ("%d kbps" % bitrate) if bitrate > 0 else "") if part
    )
    return name, meta
