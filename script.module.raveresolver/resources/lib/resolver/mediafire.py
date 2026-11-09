# -*- coding: utf-8 -*-
"""Mediafire file-page resolver (in-process).

A Mediafire share URL is an HTML page; the playable URL is a short-lived signed
``download###.mediafire.com`` link embedded in that page (sometimes base64 in a
``data-scrambled-url`` attribute).  This adapter ports the web build's proven
logic: one page fetch at a time, a courtesy gap, a two-hour signed-URL cache,
HTTP 429 ``Retry-After`` handling and typed failures.

Only Mediafire hosts are contacted.  The signed URL is returned to Kodi; it is
never logged.
"""

import base64
import html
import re
import threading
import time
import urllib.parse

from . import policy
from .base import (Adapter, BlockedURL, InvalidURL, NotFound, ProviderError,
                   RateLimited, Resolution, UnsupportedURL)
from .cache import MISSING
from .http import retry_after_seconds

MEDIAFIRE_HOSTS = ("mediafire.com",)
PAGE_PREFIXES = ("/file/", "/download/")
TTL = 2 * 60 * 60
# Web parity: a definitive negative answer is cached for 15 s only.  Five
# minutes turned a transient 5xx into a playback outage and kept 429s too long.
NEGATIVE_TTL = 15
MAX_NEGATIVE = 128
MIN_GAP = 1.2
MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_BACKOFF = 120

_SIGNED_RE = re.compile(
    r"""https?://(?:[a-z0-9-]+\.)*mediafire\.com/[^"'\s<>\\]+?\.(?:mp3|m4a)"""
    r"""(?:\?[^"'\s<>\\]*)?""",
    re.I,
)
_SCRAMBLED_RE = re.compile(r"""data-scrambled-url=["']([^"']+)["']""", re.I)


class MediafireAdapter(Adapter):
    name = "mediafire"

    def __init__(self, http, cache, logger=None, min_gap=MIN_GAP,
                 ttl=TTL, negative_ttl=NEGATIVE_TTL, clock=None,
                 monotonic=None, sleep=None):
        self.http = http
        self.cache = cache
        self.logger = logger
        self.min_gap = float(min_gap)
        self.ttl = int(ttl)
        self.negative_ttl = int(negative_ttl)
        self._clock = clock or time.time
        self._monotonic = monotonic or time.monotonic
        self._sleep = sleep or time.sleep
        self._lock = threading.RLock()
        self._last_fetch = 0.0
        self._backoff_until = 0.0
        self._negative = {}

    def matches(self, url):
        parts = policy.split_url(url)
        if parts is None:
            return False
        return policy.host_matches(parts.hostname, MEDIAFIRE_HOSTS)

    def resolve(self, url):
        page, signed = clean_page_url(url)
        if signed:
            return self._direct(signed)
        key = "mediafire:v1:" + page
        now = self._clock()
        cached = self.cache.get(key) if self.cache is not None else MISSING
        if cached is not MISSING and isinstance(cached, dict):
            value = str(cached.get("url") or "")
            expires_at = _float(cached.get("expires_at"))
            # A 2 h cache entry must never outlive the signed URL it stores.
            if value and (expires_at is None or expires_at > now):
                return Resolution(value, provider=self.name,
                                  expires_at=expires_at)
        with self._lock:
            now = self._monotonic()
            negative = self._negative.get(key)
            if negative and negative[0] > now:
                raise type(negative[1])(negative[1].message,
                                        code=negative[1].code)
            if self._backoff_until > now:
                raise RateLimited(
                    "Mediafire asked us to wait before trying again",
                    retry_after=int(self._backoff_until - now))
            self._wait_for_slot(now)
            try:
                response = self.http.fetch(
                    page, timeout=25,
                    headers={"Accept": "text/html,application/xhtml+xml",
                             "Referer": "https://www.mediafire.com/"},
                    max_bytes=MAX_PAGE_BYTES,
                    allowed_hosts=MEDIAFIRE_HOSTS)
            except BlockedURL:
                raise
            except Exception as exc:  # noqa: BLE001 - keep failures typed
                error = ProviderError(
                    "Mediafire could not be reached (%s)"
                    % type(exc).__name__)
                self._remember_negative(key, error)
                raise error
            finally:
                self._last_fetch = self._monotonic()

            status = int(getattr(response, "status", 0) or 0)
            if status == 429:
                retry_after = retry_after_seconds(
                    getattr(response, "headers", {}), default=5,
                    maximum=MAX_BACKOFF)
                self._backoff_until = self._monotonic() + retry_after
                error = RateLimited(
                    "Mediafire is rate-limiting requests; try again in %d seconds"
                    % retry_after, retry_after=retry_after)
                self._remember_negative(key, error)
                raise error
            if status in (404, 410):
                error = NotFound("that Mediafire file is no longer available")
                self._remember_negative(key, error)
                raise error
            if status < 200 or status >= 300:
                # 3xx included: redirects are not followed (web parity).
                error = ProviderError("Mediafire returned HTTP %s" % status)
                self._remember_negative(key, error)
                raise error

            body = getattr(response, "text", "")
            value = signed_url_from_page(body)
            if not value:
                error = ProviderError(
                    "Mediafire's page no longer contains a direct download link")
                self._remember_negative(key, error)
                raise error
            expires_at = self._clock() + self.ttl
            record = {"url": value, "expires_at": expires_at}
            if self.cache is not None:
                lifetime = max(1, int(min(self.ttl, expires_at - self._clock())))
                self.cache.put(key, record, ttl=lifetime)
            return Resolution(value, provider=self.name,
                              expires_at=expires_at)

    def _direct(self, value):
        normalised = policy.check_url(
            value, allowed_hosts=MEDIAFIRE_HOSTS, resolve_dns=False)
        return Resolution(normalised, provider=self.name,
                          expires_at=self._clock() + self.ttl)

    def _wait_for_slot(self, now):
        wait = self.min_gap - (now - self._last_fetch)
        if wait > 0:
            self._sleep(wait)

    def _remember_negative(self, key, error):
        now = self._monotonic()
        # Prune expired entries first, then cap the dict: a play-all of
        # hundreds of failing URLs must not grow this forever.
        for stale in [name for name, value in self._negative.items()
                      if value[0] <= now]:
            self._negative.pop(stale, None)
        if key not in self._negative and len(self._negative) >= MAX_NEGATIVE:
            try:
                oldest = min(self._negative, key=lambda name: self._negative[name][0])
            except ValueError:
                oldest = None
            if oldest is not None:
                self._negative.pop(oldest, None)
        self._negative[key] = (now + self.negative_ttl, error)


def clean_page_url(value):
    """Return ``(page_url, signed_url)`` for a Mediafire URL.

    ``("", signed)`` means the value already is a signed direct download;
    ``(page, "")`` means it is a file page that needs one fetch.  Unsupported
    or non-Mediafire values raise :class:`InvalidURL`.
    """
    parts = policy.split_url(value)
    if parts is None:
        raise InvalidURL("that is not a Mediafire URL")
    host = (parts.hostname or "").lower().rstrip(".")
    if not policy.host_matches(host, MEDIAFIRE_HOSTS):
        raise InvalidURL("that is not a Mediafire URL")
    if host.startswith("download") and host.endswith(".mediafire.com"):
        if _valid_signed_url(value):
            return "", _valid_signed_url(value)
        raise InvalidURL("that Mediafire download URL is malformed")
    path = parts.path or ""
    if not path.startswith(PAGE_PREFIXES):
        raise UnsupportedURL("that Mediafire URL is not a file page")
    page = urllib.parse.urlunsplit(("https", parts.netloc, parts.path,
                                    parts.query, ""))
    return page, ""


def _valid_signed_url(value):
    """A direct Mediafire download URL on a ``download*`` subdomain, or ``""``."""
    if not isinstance(value, str):
        return ""
    candidate = html.unescape(value).replace("\\/", "/").strip()
    parts = policy.split_url(candidate)
    if parts is None:
        return ""
    host = (parts.hostname or "").lower().rstrip(".")
    if not host.startswith("download") or not host.endswith(".mediafire.com"):
        return ""
    if parts.scheme.lower() != "https":
        return ""
    if not (parts.path or "").lower().endswith((".mp3", ".m4a")):
        return ""
    return urllib.parse.urlunsplit(
        ("https", parts.netloc, parts.path, parts.query, ""))


def _decode_scrambled(text):
    """Mediafire sometimes base64-encodes the direct URL in a data attribute."""
    for token in _SCRAMBLED_RE.findall(text or ""):
        token = token.strip()
        if not token:
            continue
        padded = token + ("=" * (-len(token) % 4))
        try:
            decoded = base64.b64decode(padded).decode("utf-8", "replace")
        except (TypeError, ValueError):
            continue
        if "mediafire.com" in decoded:
            text += "\n" + decoded
    return text


def signed_url_from_page(body):
    """Extract the signed Mediafire URL from a file page, or return ``""``."""
    if not isinstance(body, str) or not body:
        return ""
    text = html.unescape(_decode_scrambled(body))
    text = text.replace("\\/", "/")
    for match in _SIGNED_RE.findall(text):
        valid = _valid_signed_url(match)
        if valid:
            return valid
    return ""


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
