# -*- coding: utf-8 -*-
"""Curated ``Pirate Radio Archives`` data.

The data file uses the same field names as the web app:

    station, year, title, djs, source_url, stream_url, credit

``note`` is optional and is used when a page URL could not be confirmed (the
task requires the known metadata to stay even when a link is missing).  The
loader is deliberately forgiving: a malformed row is skipped, and one missing
data file yields an empty menu rather than a traceback.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILENAME = "pirate-radio.json"
FIELDS = ("station", "year", "title", "djs", "source_url", "stream_url", "credit")


def _clean(value):
    return " ".join(str(value or "").split()).strip()


def _year(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _entry(raw):
    if not isinstance(raw, dict):
        return None
    station = _clean(raw.get("station"))
    title = _clean(raw.get("title"))
    if not station or not title:
        return None
    djs = raw.get("djs")
    if not isinstance(djs, list):
        djs = [djs] if djs else []
    clean_djs = []
    for dj in djs:
        name = _clean(dj)
        if name:
            clean_djs.append(name)
    return {
        "station": station,
        "year": _year(raw.get("year")),
        "title": title,
        "djs": clean_djs,
        "source_url": _clean(raw.get("source_url")),
        "stream_url": _clean(raw.get("stream_url")),
        "credit": _clean(raw.get("credit")),
        "note": _clean(raw.get("note")),
    }


def entries():
    path = os.path.join(ROOT, "pirate-radio.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    rows = []
    for raw in data if isinstance(data, list) else []:
        entry = _entry(raw)
        if entry is not None:
            rows.append(entry)
    return rows


def stations():
    """Group entries into ``[{'station': name, 'entries': [...]}, ...]``."""
    grouped = {}
    order = []
    for entry in entries():
        station = entry["station"]
        if station not in grouped:
            grouped[station] = []
            order.append(station)
        grouped[station].append(entry)
    return [{"station": station, "entries": grouped[station]} for station in order]


def station(name):
    name = _clean(name)
    return next((group for group in stations() if group["station"] == name), None)
