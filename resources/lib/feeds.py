# -*- coding: utf-8 -*-
"""Podcast / mix feeds.

The most durable "internet-wide" source there is: an RSS feed only has to keep
existing, and the enclosures inside it are plain MP3s that Kodi can stream
directly. New feeds are added as data in resources/feeds.json.
"""

import json
import os
import re
import xml.etree.ElementTree as ET

from . import http

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.0}"
MEDIA = "{http://search.yahoo.com/mrss/}"


def registry():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "feeds.json")
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return []


def feed(feed_id):
    return next((entry for entry in registry() if entry["id"] == feed_id), None)


def _text(node, *tags):
    for tag in tags:
        found = node.find(tag)
        if found is not None and found.text and found.text.strip():
            return " ".join(found.text.split())
    return ""


def _enclosure_url(item):
    enclosure = item.find("enclosure")
    if enclosure is not None and enclosure.get("url"):
        return enclosure.get("url")
    content = item.find(MEDIA + "content")
    if content is not None and content.get("url"):
        return content.get("url")
    for link in item.findall("link"):
        if link.get("href") and (link.get("type") or "").startswith("audio"):
            return link.get("href")
    return ""


def _duration(item):
    raw = _text(item, ITUNES + "duration")
    if not raw:
        return None
    if ":" in raw:
        parts = [int(part) for part in re.findall(r"\d+", raw)]
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + part
        return seconds
    if raw.isdigit():
        return int(raw)
    return None


def parse(xml_text):
    """Parse an RSS/Atom document into episode dicts (no I/O)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = root.findall("./channel/item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    episodes = []
    for item in items:
        url = _enclosure_url(item)
        if not url:
            continue
        episodes.append({
            "title": _text(item, "title") or "Untitled",
            "url": url.replace("&amp;", "&"),
            "published": _text(item, "pubDate", "{http://www.w3.org/2005/Atom}updated"),
            "duration": _duration(item),
            "description": _text(item, "description", ITUNES + "summary")[:400],
        })
    return episodes


def episodes(feed_id, limit=60):
    entry = feed(feed_id)
    if not entry:
        return []
    body = http.fetch(entry["url"], timeout=25)
    if not body:
        return []
    return parse(body)[:limit]
