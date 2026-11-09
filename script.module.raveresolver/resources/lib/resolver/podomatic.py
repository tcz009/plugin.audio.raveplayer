# -*- coding: utf-8 -*-
"""Podomatic adapter seam.

Podomatic episode pages expose direct MP3s on ``*.podomatic.com`` CDN hosts.
A URL that already points at one of those files is returned without a network
request.  Page scraping is still being implemented in the web resolver; until
it is vendored, this adapter raises :class:`AdapterNotReady` and the manager
asks the NAS service (if configured).  ``native=`` accepts a future in-process
page resolver without changing the manager.
"""

from . import policy
from .base import (Adapter, AdapterNotReady, InvalidURL, ProviderError,
                   ResolveError, Resolution)

PODOMATIC_HOSTS = ("podomatic.com",)
AUDIO_EXTENSIONS = policy.AUDIO_EXTENSIONS


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
        path = (parts.path or "").lower()
        if path.endswith(AUDIO_EXTENSIONS):
            normalised = policy.check_url(
                url, allowed_hosts=PODOMATIC_HOSTS, require_audio=True,
                resolve_dns=False)
            return Resolution(normalised, provider=self.name)
        if self.native is None:
            raise AdapterNotReady(
                "Podomatic page resolution needs the resolver service")
        try:
            value = self.native(url)
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
            target = str(value.get("url") or "")
            headers = value.get("headers") or {}
            expires_at = value.get("expires_at")
        else:
            target = str(value or "")
            headers = {}
            expires_at = None
        target = policy.check_url(target, resolve_dns=False)
        return Resolution(target, provider=self.name, expires_at=expires_at,
                          headers=headers)


# Kept for symmetry with the web resolver's helper names.
def is_podomatic_url(url):
    parts = policy.split_url(url)
    return bool(parts and policy.host_matches(parts.hostname, PODOMATIC_HOSTS))
