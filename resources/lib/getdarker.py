# -*- coding: utf-8 -*-
"""GetDarker — dubstep/garage archive (RSS pages + curated Mixcloud account).

The RSS feed lists audio set pages (no direct enclosure in most items); the
matching Mixcloud account (``getdarker``) is the playable/public surface in the
web app.  Kodi cannot embed Mixcloud, so the route lists the pages and opens
the source/Mixcloud link; direct media is used when a page actually exposes it.
"""

import urllib.parse

from . import hardscore, http

FEED_URL = "https://getdarker.com/feed/"
FEED_TTL = 30 * 60
PAGE_TTL = 6 * 60 * 60
BROWSER_UA = hardscore.BROWSER_UA


def _fetch(url, ttl, timeout=25):
    return http.fetch(url, timeout=timeout, headers={"User-Agent": BROWSER_UA}, ttl=ttl)


def items(limit=60):
    body = _fetch(FEED_URL, FEED_TTL)
    if not body:
        return []
    return hardscore.parse_feed(body, limit=limit)


def page(page_url):
    try:
        split = urllib.parse.urlsplit(str(page_url or ""))
    except ValueError:
        return {}
    hostname = (split.hostname or "").lower()
    if split.scheme not in ("http", "https") or not (
            hostname == "getdarker.com" or hostname.endswith(".getdarker.com")):
        return {}
    body = _fetch(str(page_url), PAGE_TTL)
    if not body:
        return {}
    return hardscore.parse_page(body, str(page_url))
