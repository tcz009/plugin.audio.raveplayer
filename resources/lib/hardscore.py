# -*- coding: utf-8 -*-
"""Hardscore.com — oldskool hardcore/jungle archive.

The WordPress RSS feed carries both tracklists and, for most posts, a direct
MP3/M4A enclosure on hardscore.com.  Every post also has an event/page URL;
when there is no direct media the route offers that page instead.  All parsing
is fixture-friendly and fail-soft; the HTTP layer supplies the route budget,
redirect guard and cache.
"""

import datetime
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET

from . import http, kodi

FEED_URL = "https://www.hardscore.com/?feed=rss2"
FEED_TTL = 30 * 60
PAGE_TTL = 6 * 60 * 60
MAX_ITEMS = 5000
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"

_MEDIA_RE = re.compile(
    r"https?://[^\"'\s<>]+?\.(?:mp3|m4a|aac|ogg)(?:\?[^\"'\s<>]*)?", re.IGNORECASE
)
_LINK_RE = re.compile(r"https?://[^\"'\s<>]+", re.IGNORECASE)
_H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _decode(value):
    """Decode HTML entities, including titles a CMS encoded twice.

    Scrapers see ``&amp;`` in a text node and ``&amp;#x2013;`` when the source
    encoded the entity itself.  Loop until stable (bounded) so the rendered
    title carries ``&`` and ``–``, never the entity source.
    """
    text = str(value or "")
    for _ in range(3):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return text


def _clean(value):
    text = _decode(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _decode(text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch(url, ttl, timeout=25):
    # Hardscore's WordPress "Bad Behavior" filter 403s a bare urllib UA; a
    # browser UA plus an RSS Accept header is enough.
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/rss+xml,application/xml,text/xml,*/*;q=0.8",
    }
    return http.fetch(url, timeout=timeout, headers=headers, ttl=ttl)


def _date(value):
    """RFC-822/ISO date -> YYYY-MM-DD, or ''."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(text)
        if parsed:
            return parsed.date().isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        try:
            return datetime.date(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            ).isoformat()
        except ValueError:
            return ""
    return ""


def _media_urls(text):
    """Extract public direct-media URLs from arbitrary post HTML."""
    urls = []
    for candidate in _MEDIA_RE.findall(str(text or "")):
        candidate = _decode(candidate).strip()
        safe = http.safe_stream_url(candidate)
        if safe and safe not in urls:
            urls.append(safe)
    return urls


def parse_feed(xml_text, limit=60):
    """Parse a Hardscore-style RSS document into row dicts (no I/O)."""
    try:
        limit = max(1, min(int(limit), MAX_ITEMS))
    except (TypeError, ValueError):
        limit = 60
    if isinstance(xml_text, (bytes, bytearray)):
        return []
    if "<!ENTITY" in str(xml_text or "").upper():
        kodi.log("hardscore feed ignored: entity declarations are not allowed", level=30)
        return []
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, ValueError, TypeError):
        return []
    rows = []
    for item in root.findall("./channel/item"):
        title = _clean(item.findtext("title")) or "Hardscore post"
        page_url = (item.findtext("link") or "").strip()
        description = item.findtext("description") or ""
        content = item.findtext(CONTENT + "encoded") or ""
        enclosure = item.find("enclosure")
        media_text = description + "\n" + content
        if enclosure is not None:
            media_text += "\n" + (enclosure.get("url") or "")
        media = _media_urls(media_text)
        if not page_url:
            page_url = (item.findtext("guid") or "").strip()
        if not page_url and not media:
            continue
        rows.append({
            "title": title,
            "page_url": page_url,
            "date": _date(item.findtext("pubDate")),
            "media_urls": media,
            "description": _clean(description + " " + content)[:600],
        })
        if len(rows) >= limit:
            break
    return rows


def items(limit=60):
    """Fetch and parse the Hardscore RSS feed; [] on any failure."""
    body = _fetch(FEED_URL, FEED_TTL)
    if not body:
        return []
    return parse_feed(body, limit=limit)


def _allowed_page(value, host):
    try:
        split = urllib.parse.urlsplit(str(value or ""))
    except ValueError:
        return False
    hostname = (split.hostname or "").lower()
    return (
        split.scheme in ("http", "https")
        and (hostname == host or hostname.endswith("." + host))
        and split.path.startswith("/")
    )


def parse_page(html_text, page_url):
    """Extract title/media/outbound links from a Hardscore-style post page."""
    title = ""
    match = _H1_RE.search(html_text or "")
    if match:
        title = _clean(match.group(1))
    if not title:
        match = _TITLE_RE.search(html_text or "")
        if match:
            title = _clean(match.group(1))
    media = _media_urls(html_text)
    links = []
    for candidate in _LINK_RE.findall(html_text or ""):
        candidate = _decode(candidate).strip().rstrip(".,);")
        if any(token in candidate for token in
               ("soundcloud.com/", "mixcloud.com/", "youtube.com/", "youtu.be/")):
            if candidate not in links:
                links.append(candidate)
    return {
        "url": page_url,
        "title": title or "Hardscore post",
        "media_urls": media,
        "links": links[:20],
    }


def page(page_url):
    """Fetch one Hardscore post page; {} when it is not a Hardscore URL/dead."""
    if not _allowed_page(page_url, "hardscore.com"):
        return {}
    body = _fetch(str(page_url), PAGE_TTL)
    if not body:
        return {}
    return parse_page(body, str(page_url))
