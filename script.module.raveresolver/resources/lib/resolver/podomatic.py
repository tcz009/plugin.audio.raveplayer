# -*- coding: utf-8 -*-
"""Podomatic adapter seam.

Podomatic episode pages expose direct MP3s on ``*.podomatic.com`` enclosure
URLs.  A URL that already points at one of those files is returned without a
network request.  ``pdcn.co/e/...`` wrapper links are canonicalised locally to
the Podomatic enclosure they point at (web parity) instead of following the
wrapper's redirect.  Page scraping is still being implemented in the web
resolver; until it is vendored, a page raises :class:`AdapterNotReady` and the
manager asks the NAS service (if configured).  ``native=`` accepts a future
in-process page resolver without changing the manager.
"""

import urllib.parse

from . import policy
from .base import (Adapter, AdapterNotReady, InvalidURL, ProviderError,
                   ResolveError, Resolution, UnsupportedURL)

PODOMATIC_HOSTS = ("podomatic.com", "pdcn.co")
PODOMATIC_CANONICAL_HOSTS = ("podomatic.com",)
AUDIO_EXTENSIONS = policy.AUDIO_EXTENSIONS
_ENCLOSURE_PREFIX = "/enclosure/"
_PAGE_SUFFIXES = (
    ".m3u", ".m3u8", ".pls", ".rss", ".xml", ".html", ".htm", ".json",
)


def canonical_url(value):
    """Return the canonical Podomatic HTTPS URL for ``value``.

    ``pdcn.co/e/<target>`` is decoded locally (the wrapper is a 301 in a
    browser) and must point at a Podomatic enclosure audio file.  A plain
    Podomatic host is forced to HTTPS with the fragment dropped.
    """
    parts = policy.split_url(value)
    if parts is None:
        raise InvalidURL("that is not a Podomatic URL")
    host = (parts.hostname or "").lower().rstrip(".")
    if host == "pdcn.co" or host.endswith(".pdcn.co"):
        return _canonical_pdcn(parts)
    if not policy.host_matches(host, PODOMATIC_CANONICAL_HOSTS):
        raise InvalidURL("that is not a Podomatic URL")
    return urllib.parse.urlunsplit(
        ("https", host, parts.path or "/", parts.query, ""))


def _canonical_pdcn(parts):
    path = parts.path or ""
    if not path.startswith("/e/"):
        raise UnsupportedURL("pdcn.co links must use the /e/ form",
                             fallback=False)
    rest = path[3:]
    # The target may be percent-encoded as a whole absolute URL.  Decode only
    # when it looks encoded; a literal ``%20`` in a filename survives.
    if rest.lower().startswith(("http%3a", "https%3a")) \
            or "%2f%2f" in rest.lower():
        for _ in range(2):
            decoded = urllib.parse.unquote(rest)
            if decoded == rest:
                break
            rest = decoded
    if not rest:
        raise UnsupportedURL("pdcn.co link has no target", fallback=False)
    if "://" not in rest:
        rest = "https://" + rest
    inner = policy.split_url(rest)
    if inner is None:
        raise UnsupportedURL("pdcn.co link target is malformed",
                             fallback=False)
    target_host = (inner.hostname or "").lower().rstrip(".")
    if not policy.host_matches(target_host, PODOMATIC_CANONICAL_HOSTS):
        raise UnsupportedURL("pdcn.co link does not target Podomatic",
                             fallback=False)
    target_path = inner.path or "/"
    lowered = target_path.lower().rstrip("/")
    if not lowered.startswith(_ENCLOSURE_PREFIX):
        raise UnsupportedURL("pdcn.co link is not a Podomatic enclosure",
                             fallback=False)
    if lowered.endswith(_PAGE_SUFFIXES) or not lowered.endswith(AUDIO_EXTENSIONS):
        raise UnsupportedURL("pdcn.co link is not an audio enclosure",
                             fallback=False)
    query = inner.query or parts.query
    return urllib.parse.urlunsplit(
        ("https", target_host, target_path, query, ""))


class PodomaticAdapter(Adapter):
    name = "podomatic"

    def __init__(self, native=None, logger=None):
        self.native = native
        self.logger = logger

    def matches(self, url):
        parts = policy.split_url(url)
        if parts is None:
            return False
        return policy.host_matches(parts.hostname, PODOMATIC_HOSTS)

    def resolve(self, url):
        parts = policy.split_url(url)
        if parts is None:
            raise InvalidURL("that is not a Podomatic URL")
        if not policy.host_matches(parts.hostname, PODOMATIC_HOSTS):
            raise InvalidURL("that is not a Podomatic URL")
        target = canonical_url(url)
        canonical = policy.split_url(target)
        if canonical is None:
            raise InvalidURL("that is not a Podomatic URL")
        path = (canonical.path or "").lower()
        if path.endswith(AUDIO_EXTENSIONS):
            normalised = policy.check_url(
                target, allowed_hosts=PODOMATIC_CANONICAL_HOSTS,
                require_audio=True, resolve_dns=False)
            return Resolution(normalised, provider=self.name)
        if self.native is None:
            raise AdapterNotReady(
                "Podomatic page resolution needs the resolver service")
        try:
            value = self.native(target)
        except ResolveError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("Podomatic resolve failed (%s)"
                                % type(exc).__name__)
        if isinstance(value, Resolution):
            value.provider = self.name
            value.url = policy.check_url(value.url, resolve_dns=False)
            return value
        if isinstance(value, dict):
            target_url = str(value.get("url") or "")
            headers = value.get("headers") or {}
            expires_at = value.get("expires_at")
        else:
            target_url = str(value or "")
            headers = {}
            expires_at = None
        target_url = policy.check_url(target_url, resolve_dns=False)
        return Resolution(target_url, provider=self.name, expires_at=expires_at,
                          headers=headers)


# Kept for symmetry with the web resolver's helper names.
def is_podomatic_url(url):
    parts = policy.split_url(url)
    return bool(parts and policy.host_matches(parts.hostname, PODOMATIC_HOSTS))
