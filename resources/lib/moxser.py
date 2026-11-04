# -*- coding: utf-8 -*-
"""Moxser.com mix archive.

Moxser is a Craft CMS site whose sitemap index exposes the ``mixes`` section.
The sitemap gives us the page catalogue (one request per sitemap, >=1 h cache);
a mix page itself contains an ``og:title``/``og:image`` pair and a direct
``.mp3`` link on the site's media host.  MP3s are ``audio/mpeg`` with Range
support, so Kodi can stream them directly.

Be polite: one request per second at most, a browser User-Agent, aggressive
caching, and fail-soft (an unreachable sitemap/page yields no rows, not a
traceback).
"""

import datetime
import html
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET

from . import http

SITE = "https://moxser.com"
SITEMAP_INDEX = SITE + "/sitemaps-1-sitemap.xml"
SITEMAP_TTL = 6 * 60 * 60
MIX_TTL = 6 * 60 * 60
MIN_INTERVAL = 1.0  # <= 1 request/second
MAX_SITEMAPS = 20
MAX_MIXES = 5000
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_IMAGE = "{http://www.google.com/schemas/sitemap-image/1.1}"
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s+(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)[a-z]*\.?\s+(\d{4})(?!\d)",
    re.IGNORECASE,
)
_MP3_RE = re.compile(r"https?://[^\"'\s<>]+?\.mp3(?:\?[^\"'\s<>]*)?", re.IGNORECASE)
_H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_META_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)

_last_request = 0.0


def _throttle():
    """Enforce the <=1 request/second courtesy limit."""
    global _last_request
    now = time.monotonic()
    wait = MIN_INTERVAL - (now - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def _fetch(url, ttl, timeout=25):
    headers = {"User-Agent": BROWSER_UA}
    # Don't pay the <=1/s gap for a page that is already cached.
    if not http.is_cached(url, ttl, headers):
        _throttle()
    return http.fetch(url, timeout=timeout, headers=headers, ttl=ttl)


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
    text = _decode(urllib.parse.unquote_plus(str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value):
    """Return an ISO date from a Moxser title/slug, or ''."""
    match = _DATE_RE.search(str(value or ""))
    if not match:
        return ""
    try:
        return datetime.date(
            int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1))
        ).isoformat()
    except (KeyError, ValueError):
        return ""


def _meta(page, prop):
    for tag in _META_RE.findall(str(page or "")):
        if re.search(r'(?:property|name)=["\']%s["\']' % re.escape(prop), tag, re.I):
            match = re.search(r'content=["\']([^"\']*)["\']', tag, re.I)
            if match:
                return _clean(match.group(1))
    return ""


def _sitemap_urls(index_xml):
    """Pick the mixes sitemaps out of the index (max MAX_SITEMAPS)."""
    try:
        root = ET.fromstring(index_xml)
    except (ET.ParseError, ValueError, TypeError):
        return []
    urls = []
    for node in root.findall(_SM + "sitemap"):
        loc = node.findtext(_SM + "loc") or ""
        loc = loc.strip()
        if "section-mixes" in loc and loc.endswith(".xml") and loc not in urls:
            urls.append(loc)
    return urls[:MAX_SITEMAPS]


def _parse_mixes_sitemap(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, ValueError, TypeError):
        return []
    items = []
    for node in root.findall(_SM + "url"):
        page_url = (node.findtext(_SM + "loc") or "").strip()
        if not _is_page_url(page_url):
            continue
        image = node.find(_IMAGE + "image")
        flyer = ""
        title = ""
        if image is not None:
            flyer = (image.findtext(_IMAGE + "loc") or "").strip()
            title = _clean(image.findtext(_IMAGE + "title") or "")
        lastmod = (node.findtext(_SM + "lastmod") or "").strip()
        if not title:
            slug = page_url.rstrip("/").rsplit("/", 1)[-1]
            title = _clean(slug.replace("-", " "))
        date = parse_date(title) or parse_date(page_url)
        if not date and re.match(r"^\d{4}-\d{2}-\d{2}", lastmod):
            date = lastmod[:10]
        items.append({
            "page_url": page_url,
            "title": title or "Moxser mix",
            "date": date,
            "flyer": flyer,
            "lastmod": lastmod,
        })
    return items


def _is_page_url(value):
    try:
        split = urllib.parse.urlsplit(str(value or ""))
    except ValueError:
        return False
    return (
        split.scheme == "https"
        and split.hostname in ("moxser.com", "www.moxser.com")
        and split.path.startswith("/mixes/")
    )


def mixes(limit=60):
    """Return sitemap-derived mix rows (no per-page fetch).

    Each row has ``page_url``, ``title``, ``date``, ``flyer``; call :func:`mix`
    when the user picks one to obtain the direct MP3.
    """
    try:
        limit = max(1, min(int(limit), MAX_MIXES))
    except (TypeError, ValueError):
        limit = 60
    index = _fetch(SITEMAP_INDEX, SITEMAP_TTL)
    if not index:
        return []
    rows = []
    seen = set()
    for sitemap in _sitemap_urls(index):
        body = _fetch(sitemap, SITEMAP_TTL)
        if not body:
            continue
        for row in _parse_mixes_sitemap(body):
            if row["page_url"] in seen:
                continue
            seen.add(row["page_url"])
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows[:limit]


def mix(page_url):
    """Fetch one mix page and return title/date/flyer/direct MP3.

    Returns ``{}`` (not an exception) for a dead page.  The MP3 candidate goes
    through the shared public-stream guard; a missing/blocked MP3 leaves
    ``mp3_url`` empty so the route can offer the source page instead.
    """
    if not _is_page_url(page_url):
        return {}
    page = _fetch(str(page_url), MIX_TTL)
    if not page:
        return {}
    title = _meta(page, "og:title")
    if not title:
        match = _H1_RE.search(page)
        if match:
            title = _clean(re.sub(r"<[^>]+>", " ", match.group(1)))
    if not title:
        slug = str(page_url).rstrip("/").rsplit("/", 1)[-1]
        title = _clean(slug.replace("-", " "))
    date = parse_date(title) or parse_date(page_url)
    flyer = _meta(page, "og:image")
    mp3 = ""
    for candidate in _MP3_RE.findall(page):
        candidate = _decode(candidate)
        safe = http.safe_stream_url(candidate)
        if safe:
            mp3 = safe
            break
    return {
        "page_url": str(page_url),
        "title": title or "Moxser mix",
        "date": date,
        "flyer": flyer,
        "mp3_url": mp3,
    }

