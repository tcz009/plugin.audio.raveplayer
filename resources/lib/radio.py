# -*- coding: utf-8 -*-
"""Live radio via radio-browser.info — a community directory that stays current."""

from . import http

MIRRORS = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]


def stations(tag, limit=100):
    """Return live, non-broken stations for a tag, most-clicked first."""
    query = (
        "/json/stations/search?tag=%s&limit=%d&hidebroken=true"
        "&order=clickcount&reverse=true" % (http.quote(tag), limit)
    )
    for mirror in MIRRORS:
        data = http.fetch_json(mirror + query, timeout=20)
        if isinstance(data, list):
            return [station for station in data if station.get("url_resolved") or station.get("url")]
    return []


def stream_url(station):
    return station.get("url_resolved") or station.get("url") or ""


def display(station):
    name = (station.get("name") or "Unknown station").strip()
    country = (station.get("countrycode") or station.get("country") or "").strip()
    codec = (station.get("codec") or "").upper()
    bitrate = station.get("bitrate")
    meta = " · ".join(part for part in (country, codec, ("%s kbps" % bitrate) if bitrate else "") if part)
    return name, meta
