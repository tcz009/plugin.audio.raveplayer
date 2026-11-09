# -*- coding: utf-8 -*-
"""The two blog archives from the 2014 add-on that still answer.

``Mikus Musik`` (Blogger) and ``Demodulated Mixtapes`` (WordPress) were part of
the original Kodi menu but were dropped when the 2026 rebuild kept only the
sources with a stable, directly scrapable index.  Both still publish a normal
RSS feed:

* Mikus posts are mostly Mixcloud embeds, so the set is played through the
  official Kodi Mixcloud add-on (the same hand-off GetDarker uses);
* Demodulated posts publish a direct preview MP3 in their feed content, so the
  set can play in Kodi even when the old download page is gone.

This module is deliberately small and fail-soft: a dead blog returns an empty
list, never an exception.  It performs no Kodi import at module level beyond the
shared HTTP wrapper.
"""

import html
import re
import urllib.parse
import xml.etree.ElementTree as ET

from . import http

CONTENT = "{http://purl.org/rss/1.0/modules/content/}"
FEED_TTL = 30 * 60
MAX_POSTS = 500

SOURCES = (
    {
        "id": "mikus",
        "name": "Mikus Musik",
        "feed_url": ("http://mikusmusik.blogspot.com/feeds/posts/default"
                     "?alt=rss&max-results=150"),
        "site_url": "http://mikusmusik.blogspot.com/",
        "plot": "Dub, jungle, house and garage sets from the Mikus Musik blog.",
        "kind": "blog",
    },
    {
        "id": "demodulated",
        "name": "Demodulated Mixtapes",
        "feed_url": "http://mixtapes.demodulated.com/feed/",
        "site_url": "http://mixtapes.demodulated.com/",
        "plot": "Old techno, jungle and rave mixtapes from Demodulated.",
        "kind": "blog",
    },
)

_MEDIA_RE = re.compile(
    r"https?://[^\"'\s<>]+?\.(?:mp3|m4a|aac|ogg)(?:\?[^\"'\s<>]*)?",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[A-Za-z/!][^>]{0,512}>")
_MIXCLOUD_IFRAME_RE = re.compile(
    r"mixcloud\.com/widget/iframe/[^\"'\s<>]*?(?:feed|cloudcast)=([^&\"'\s<>]+)",
    re.IGNORECASE,
)
_MIXCLOUD_RE = re.compile(
    r"https?://(?:www\.)?mixcloud\.com/([A-Za-z0-9%._~!$&'()*+,;=:@/-]+)",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def sources():
    return [dict(source) for source in SOURCES]


def source(source_id):
    key = str(source_id or "").strip().lower()
    return next((dict(item) for item in SOURCES if item["id"] == key), None)


def _decode(value):
    text = str(value or "")
    for _ in range(3):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return text


def _clean(value):
    text = _TAG_RE.sub(" ", _decode(value))
    text = _decode(text)
    return " ".join(text.split())


def _date(value):
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
    return match.group(0) if match else ""


def _safe(value):
    """Syntactic public-URL check; playback re-validates with DNS.

    A feed can carry 100+ post/media links and ``safe_stream_url`` resolves
    every host.  Directory building only needs to reject non-http and literal
    private addresses; the plugin's ``mode=play`` route applies the strict
    guard when the user actually plays the URL.
    """
    text = html.unescape(str(value or "")).strip()
    return text if http.looks_like_public_http_url(text) else ""


def _media_urls(text):
    urls = []
    for candidate in _MEDIA_RE.findall(str(text or "")):
        safe = _safe(candidate)
        if safe and safe not in urls:
            urls.append(safe)
    return urls


def _mixcloud_urls(text):
    """Return canonical Mixcloud cloudcast page URLs from post HTML.

    Blogger wraps players in ``mixcloud.com/widget/iframe/?feed=%2Fmikus%2F…``;
    the feed parameter is the cloudcast path.  Plain ``mixcloud.com/user/set``
    links are accepted too.  Search/profile pages are ignored.
    """
    found = []

    def add(candidate):
        safe = _safe(candidate)
        if not safe:
            return
        split = urllib.parse.urlsplit(safe)
        segments = [part for part in split.path.split("/") if part]
        if len(segments) < 2:
            return
        canonical = "https://www.mixcloud.com/" + "/".join(segments) + "/"
        if canonical not in found:
            found.append(canonical)

    for encoded in _MIXCLOUD_IFRAME_RE.findall(str(text or "")):
        add("https://www.mixcloud.com" + urllib.parse.unquote(encoded))
    for match in _MIXCLOUD_RE.findall(str(text or "")):
        if "widget" in match.split("/"):
            continue
        add("https://www.mixcloud.com/" + match)
    return found


def _text(node, *tags):
    for tag in tags:
        found = node.find(tag)
        if found is not None:
            value = " ".join(found.itertext()).strip()
            if value:
                return value
    return ""


def parse_feed(xml_text, source_id):
    """Parse one blog RSS document into post dicts (no I/O)."""
    if isinstance(xml_text, (bytes, bytearray)):
        return []
    marker = str(xml_text or "")
    if "<!ENTITY" in marker.upper():
        return []
    try:
        root = ET.fromstring(marker)
    except (ET.ParseError, ValueError, TypeError, RecursionError):
        return []
    posts = []
    for item in root.findall("./channel/item"):
        title = _clean(_text(item, "title")) or "Untitled"
        page_url = _text(item, "link") or _text(item, "guid")
        page_url = _safe(page_url)
        if not page_url:
            continue
        body = "\n".join((
            item.findtext("description") or "",
            item.findtext(CONTENT + "encoded") or "",
        ))
        posts.append({
            "source": str(source_id or ""),
            "title": title,
            "page_url": page_url,
            "date": _date(_text(item, "pubDate")),
            "media_urls": _media_urls(body),
            "mixcloud_urls": _mixcloud_urls(body),
            "summary": _clean(body)[:400],
        })
        if len(posts) >= MAX_POSTS:
            break
    return posts


def posts(source_id, limit=MAX_POSTS):
    entry = source(source_id)
    if not entry:
        return []
    try:
        limit = max(1, min(int(limit), MAX_POSTS))
    except (TypeError, ValueError):
        limit = MAX_POSTS
    body = http.fetch(entry["feed_url"], timeout=25, ttl=FEED_TTL)
    if not body:
        return []
    return parse_feed(body, entry["id"])[:limit]


def post(source_id, page_url):
    """Return one post's media and hand-off links, using the cached feed."""
    wanted = _safe(page_url)
    if not wanted:
        return {}
    for row in posts(source_id):
        if row["page_url"] == wanted:
            return row
    return {}


def page_title(body):
    match = _TITLE_RE.search(str(body or ""))
    return _clean(match.group(1)) if match else ""
