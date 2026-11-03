# -*- coding: utf-8 -*-
"""Podcast / mix feeds.

The most durable "internet-wide" source there is: an RSS feed only has to keep
existing, and the enclosures inside it are plain MP3s that Kodi can stream
directly. New feeds are added as data in resources/feeds.json.
"""

import html as html_module
import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET

from . import http, kodi

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.0}"
MEDIA = "{http://search.yahoo.com/mrss/}"
ATOM = "{http://www.w3.org/2005/Atom}"

FEED_TTL = 900
DESCRIPTION_LIMIT = 400
FEED_WORKERS = 5
_DESCRIPTION_SCAN_LIMIT = 8192
_TAG_RE = re.compile(r"<[A-Za-z/!][^>]{0,512}>")  # bounded parallelism for multi-feed routes


def registry():
    """Return the configured feeds, dropping malformed entries."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "feeds.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    feeds = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        feed_id = entry.get("id")
        url = entry.get("url")
        if not feed_id or not isinstance(url, str) or not url:
            continue
        feeds.append({
            "id": str(feed_id),
            "name": str(entry.get("name") or feed_id),
            "url": url,
            "plot": str(entry.get("plot") or ""),
        })
    return feeds


def feed(feed_id):
    return next((entry for entry in registry() if entry["id"] == feed_id), None)


def _elements(node, tag):
    """Find a child by its plain or Atom-namespaced name."""
    found = node.find(tag)
    if found is not None:
        return found
    return node.find(ATOM + tag)


def _decode(value):
    """Decode HTML entities, including titles a CMS encoded twice.

    Scrapers see ``&amp;`` in a text node and ``&amp;#x2013;`` when the source
    encoded the entity itself.  Loop until stable (bounded) so the rendered
    title carries ``&`` and ``–``, never the entity source.
    """
    text = str(value or "")
    for _ in range(3):
        decoded = html_module.unescape(text)
        if decoded == text:
            break
        text = decoded
    return text


def _text(node, *tags):
    for tag in tags:
        found = _elements(node, tag)
        if found is not None:
            value = " ".join(found.itertext()).strip()
            if value:
                return " ".join(_decode(value).split())
    return ""


def _links(item):
    return item.findall("link") + item.findall(ATOM + "link")


def _media_url(value):
    """Return a playable http(s) URL, or '' for any other scheme.

    Feed enclosures are third-party data; never hand Kodi a ``file:``,
    ``javascript:`` or relative URL supplied by a feed.
    """
    text = html_module.unescape(str(value or "")).strip()
    if not text:
        return ""
    try:
        split = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if split.scheme.lower() not in ("http", "https") or not split.netloc:
        return ""
    return text


def _enclosure_url(item):
    enclosure = _elements(item, "enclosure")
    if enclosure is not None and enclosure.get("url"):
        url = _media_url(enclosure.get("url"))
        if url:
            return url
    content = item.find(MEDIA + "content")
    if content is not None and content.get("url"):
        url = _media_url(content.get("url"))
        if url:
            return url
    for link in _links(item):
        if not link.get("href"):
            continue
        rel = (link.get("rel") or "").lower()
        kind = (link.get("type") or "").lower()
        if rel == "enclosure" or kind.startswith("audio"):
            url = _media_url(link.get("href"))
            if url:
                return url
    return ""


def _duration(item):
    raw = _text(item, ITUNES + "duration")
    if not raw:
        return None
    if ":" in raw:
        # Ignore a fractional-seconds tail: "1:02:03.500" is still 1h 2m 3s.
        clock = raw.split(".", 1)[0]
        try:
            parts = [int(part) for part in re.findall(r"\d+", clock)][:3]
        except (ValueError, OverflowError):
            return None
        if not parts:
            return None
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + part
        return seconds
    try:
        return int(float(raw))
    except (TypeError, ValueError, OverflowError):
        return None


def _description(item):
    """Return readable plot text: feeds usually ship HTML in <description>."""
    raw = _text(item, "description", ITUNES + "summary", ATOM + "summary")
    if not raw:
        return ""
    text = _decode(raw[:_DESCRIPTION_SCAN_LIMIT])
    # Bounded repetition keeps this linear on hostile "<a<a<a…" input (A4).
    text = _TAG_RE.sub(" ", text)
    return " ".join(text.split())[:DESCRIPTION_LIMIT]


def parse(xml_text):
    """Parse an RSS/Atom document into episode dicts (no I/O).

    Byte input is refused: the HTTP layer always decodes first, and scanning
    raw bytes for ``<!ENTITY`` was bypassable with UTF-16 (A5), where ElementTree
    auto-detects the encoding and expands entities we never saw as ASCII.
    """
    if isinstance(xml_text, (bytes, bytearray)):
        kodi.log("feed ignored: XML must be decoded before parsing", level=30)
        return []
    marker_text = str(xml_text or "")
    # A feed never needs internal entity declarations, and Expat's entity
    # expansion can be abused for a denial of service ("billion laughs").
    if "<!ENTITY" in marker_text.upper():
        kodi.log("feed ignored: entity declarations are not allowed", level=30)
        return []
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, ValueError, TypeError, RecursionError):
        return []
    items = root.findall("./channel/item")
    if not items:
        items = root.findall(".//" + ATOM + "entry")
    episodes = []
    for item in items:
        url = _enclosure_url(item)
        if not url:
            continue
        episodes.append({
            "title": _text(item, "title") or "Untitled",
            "url": url,
            "published": _text(item, "pubDate", ATOM + "updated"),
            "duration": _duration(item),
            "description": _description(item),
        })
    return episodes


def episodes(feed_id, limit=60):
    entry = feed(feed_id)
    if not entry:
        return []
    body = http.fetch(entry["url"], timeout=25, ttl=FEED_TTL)
    if not body:
        return []
    return parse(body)[:limit]


def episodes_many(entries, limit=60, workers=FEED_WORKERS):
    """Fetch several feeds concurrently and return ``[(entry, episodes)]``.

    The pool is bounded and results keep the caller's order, so callers can
    keep their deterministic rendering.  One failing feed yields ``[]`` for
    that entry only.  Every request still goes through the HTTP layer, so the
    per-route wall-clock budget and its per-fetch clamping apply (a slow feed
    cannot hold the batch past the caller's budget).
    """
    entries = list(entries or [])
    if not entries:
        return []
    try:
        count = max(1, min(int(workers or 1), len(entries)))
    except (TypeError, ValueError):
        count = len(entries)
    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(episodes, entry["id"], limit) for entry in entries]
            results = []
            for entry, future in zip(entries, futures):
                try:
                    results.append((entry, future.result()))
                except Exception as exc:  # one bad feed must not drop the batch
                    kodi.log("feed %s failed (%s)" % (entry.get("id"), exc), level=30)
                    results.append((entry, []))
            return results
    except Exception as exc:  # executor creation failed: fall back to serial
        kodi.log("feed batch failed (%s); falling back to serial fetch" % exc, level=30)
        results = []
        for entry in entries:
            try:
                results.append((entry, episodes(entry["id"], limit)))
            except Exception:  # never let one feed break the whole menu
                results.append((entry, []))
        return results
