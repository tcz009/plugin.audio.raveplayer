# -*- coding: utf-8 -*-
"""Direct audio URLs.

This adapter performs **no network request**.  It validates the URL against
the source allowlist and returns it unchanged (fragment removed), which is what
keeps direct Archive/Hardscore/Moxser/Toronto playback working when the NAS is
offline.  A provider *page* URL is never treated as a direct file even when its
path ends in ``.mp3`` (Mediafire pages do exactly that).
"""

import urllib.parse

from . import policy
from .base import Adapter, InvalidURL, Resolution


def _is_provider_page(url):
    parts = policy.split_url(url)
    if parts is None:
        return True
    host = (parts.hostname or "").lower().rstrip(".")
    path = (parts.path or "").lower()
    if policy.host_matches(host, policy.PROVIDER_HOSTS["mediafire"]):
        if not host.startswith("download"):
            return True
    if policy.host_matches(host, ("drive.google.com", "docs.google.com")):
        return True
    if policy.host_matches(host, policy.PROVIDER_HOSTS["podomatic"]):
        return True
    if policy.host_matches(host, policy.PROVIDER_HOSTS["mega"]):
        return True
    return False


class DirectAdapter(Adapter):
    name = "direct"

    def __init__(self, allow_hosts=None, dns_resolver=None, logger=None):
        self.allow_hosts = tuple(policy.DIRECT_HOSTS) + tuple(allow_hosts or ())
        self.dns_resolver = dns_resolver or policy.default_dns_resolver
        self.logger = logger

    def matches(self, url):
        return policy.is_audio_url(url) and not _is_provider_page(url)

    def resolve(self, url):
        if _is_provider_page(url):
            raise InvalidURL("that URL is a provider page, not a direct file")
        normalised = policy.check_url(
            url, allowed_hosts=self.allow_hosts, require_audio=True,
            resolve_dns=True, resolver=self.dns_resolver)
        parts = urllib.parse.urlsplit(normalised)
        return Resolution(normalised, provider=self.name,
                          title=urllib.parse.unquote(
                              (parts.path or "").rsplit("/", 1)[-1]))
