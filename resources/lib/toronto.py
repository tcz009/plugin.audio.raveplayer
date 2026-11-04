# -*- coding: utf-8 -*-
"""Toronto Rave Mixtape Archive — genre pages with direct MP3s.

The site exposes genre pages (``/jungle.html``, ``/house.html``,
``/studio.html``, ``/xstatic.html`` and any extra genre links in the nav) with
``<a download=... href="/files/...mp3">`` rows.  There is no API and no
hand-off add-on: each row is a direct MP3 that can be played or downloaded.

The scraper is deliberately fixture-friendly: pure parsing helpers, one cached
fetch per page, and a small serialised request gap so opening several genre
pages cannot hammer the archive.
"""

import html
import re
import time
import urllib.parse

from . import http

BASE = "https://www.torontoravemixtapearchive.com"
PAGE_TTL = 6 * 60 * 60
INDEX_TTL = 6 * 60 * 60
MIN_PAGE_GAP = 0.5
MAX_TRACKS = 5000
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Canonical order/labels for the four pages the owner named.  The homepage nav
# is parsed as well, so an added genre page appears without an add-on release.
GENRES = (
    ("jungle", "Jungle & Hardcore"),
    ("house", "House & Techno"),
    ("studio", "Studio"),
    ("xstatic", "X-Static"),
)
_GENRE_FALLBACK = dict(GENRES)

_NAV_RE = re.compile(
    r"<a\b[^>]*\bhref=[\"']/?([a-z0-9_-]+)\.html[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_NAV_ARIA_RE = re.compile(
    r"\baria-label=[\"']Navigate to ([^\"']+)[\"']", re.IGNORECASE
)
_FILE_RE = re.compile(
    r"<a\b([^>]*\bhref=[\"'](/files/[^\"']+?\.mp3)[\"'][^>]*)>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_DOWNLOAD_RE = re.compile(
    r"\bdownload=[\"']([^\"']*)[\"']", re.IGNORECASE
)
_HEADER_RE = re.compile(
    r"<div\b[^>]*\bclass=[\"'][^\"']*\bheader\b[^\"']*[\"'][^>]*>(.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)
_META_RE = re.compile(
    r"<div\b[^>]*\bclass=[\"'][^\"']*\bmetadata\b[^\"']*[\"'][^>]*>(.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
_TAG_RE = re.compile(r"<[^>]+>")

_last_fetch_at = 0.0


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
    text = _TAG_RE.sub(" ", text)
    text = _decode(text)
    text = _CONTROL_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch(url, ttl=PAGE_TTL):
    """Fetch one page with the archive's serialised request gap and cache TTL."""
    global _last_fetch_at
    headers = {"User-Agent": BROWSER_UA, "Accept": "text/html,*/*;q=0.8"}
    # The courtesy gap is for upstream requests only; a warm page is a disk
    # cache read and used to still sleep here on every directory refresh.
    if not http.is_cached(url, ttl, headers):
        now = time.monotonic()
        wait = MIN_PAGE_GAP - (now - _last_fetch_at)
        if wait > 0:
            time.sleep(wait)
        _last_fetch_at = time.monotonic()
    return http.fetch(url, timeout=25, ttl=ttl, headers=headers)


def _safe_mp3_url(path):
    """Return an absolute archive MP3 URL, or "" for hostile links."""
    raw = html.unescape(urllib.parse.unquote(str(path or "").strip()))
    if not raw.startswith("/files/"):
        return ""
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts[1:]):
        return ""
    lowered = raw.lower()
    if not lowered.endswith(".mp3"):
        return ""
    if "/files/mixtape/" not in lowered and "/files/mixtapes/" not in lowered \
            and "/files/xstatic/" not in lowered:
        return ""
    quoted = urllib.parse.quote(raw, safe="/")
    return BASE + quoted


def _file_link(attrs, body):
    match = _FILE_RE.search(body)
    if not match:
        return None
    path = match.group(2)
    url = _safe_mp3_url(path)
    if not url:
        return None
    download = _DOWNLOAD_RE.search(attrs or "")
    label = ""
    if download:
        label = _clean(download.group(1))
    if not label:
        header = _HEADER_RE.search(body)
        if header:
            label = _clean(header.group(1))
    if not label:
        label = _clean(urllib.parse.unquote(path.rsplit("/", 1)[-1]).rsplit(".", 1)[0])
    metadata = _META_RE.search(body)
    meta = _clean(metadata.group(1)) if metadata else ""
    return {"name": label, "url": url, "metadata": meta}


def parse_tracks(page):
    """Extract direct archive MP3 rows from one genre page (pure)."""
    if not page:
        return []
    tracks, seen = [], set()
    for match in _FILE_RE.finditer(page):
        item = _file_link(match.group(1), match.group(0))
        if not item or item["url"] in seen:
            continue
        seen.add(item["url"])
        tracks.append(item)
        if len(tracks) >= MAX_TRACKS:
            break
    return tracks


def parse_genres(page):
    """Extract genre links from the homepage nav (pure), stable/fallback order."""
    found = []
    seen = set()
    for match in _NAV_RE.finditer(page or ""):
        slug = match.group(1).strip().lower()
        if slug in ("updates", "contact-us", "contact", "index") or not slug:
            continue
        if slug in seen:
            continue
        text = _clean(match.group(2))
        label = text or _GENRE_FALLBACK.get(slug, slug.replace("-", " ").title())
        seen.add(slug)
        found.append({"genre": slug, "label": label})
    if not found:
        return [{"genre": slug, "label": label} for slug, label in GENRES]
    # Put the canonical four first, then any extra nav pages.
    canonical = [{"genre": slug, "label": LABEL}
                 for slug, LABEL in GENRES if slug in seen]
    extras = [row for row in found if row["genre"] not in _GENRE_FALLBACK]
    return canonical + extras


def genres():
    """Genre subfolders, cached/rate-limited via the homepage."""
    page = _fetch(BASE + "/", ttl=INDEX_TTL)
    return parse_genres(page)


def tracks(genre):
    """Direct MP3s for one genre page; never raises on a bad/empty page."""
    slug = str(genre or "").strip().lower()
    if not re.match(r"^[a-z0-9_-]{1,40}$", slug):
        return []
    page = _fetch(BASE + "/" + slug + ".html", ttl=PAGE_TTL)
    return parse_tracks(page)


def all_tracks():
    """Flat compatibility view used by older favourites/search surfaces."""
    tracks_out = []
    for row in genres():
        tracks_out.extend(tracks(row["genre"]))
    return tracks_out
