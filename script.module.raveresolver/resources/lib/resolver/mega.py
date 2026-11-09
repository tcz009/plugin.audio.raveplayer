# -*- coding: utf-8 -*-
"""Mega link parsing and the in-process adapter interface.

Mega downloads are encrypted with AES-CTR and the key lives in the URL
fragment.  A full client is therefore not a "small pure-Python helper"; the
web build is implementing it separately.  This module ships the complete,
tested URL parser and the adapter seam:

* when a native implementation is supplied (``MegaAdapter(native=...)``), it
  runs in-process and returns a signed CDN URL;
* when it is not, the adapter returns :class:`AdapterNotReady` so the manager
  can fall back to the NAS ``/api/resolve`` service;
* folders are rejected: one folder is not one playable audio file.
"""

import re
import urllib.parse

from . import policy
from .base import (Adapter, AdapterNotReady, InvalidURL, ProviderError,
                   ResolveError, Resolution, UnsupportedURL)

MEGA_HOSTS = ("mega.nz", "mega.co.nz", "mega.io")
_HANDLE_RE = re.compile(r"^[A-Za-z0-9_-]{6,32}$")
_KEY_RE = re.compile(r"^[A-Za-z0-9_=-]{16,128}$")


class MegaLink(object):
    """A parsed Mega file/folder link."""

    __slots__ = ("kind", "handle", "key", "url")

    def __init__(self, kind, handle, key, url):
        self.kind = str(kind)
        self.handle = str(handle)
        self.key = str(key)
        self.url = str(url)

    def as_dict(self):
        """A log-safe view: no fragment key and no URL (the URL embeds it).

        Equality compares the private fields, so two links with different
        keys remain distinct even though ``as_dict`` hides them.
        """
        return {"kind": self.kind, "handle": self.handle,
                "has_key": bool(self.key)}

    def __eq__(self, other):
        return isinstance(other, MegaLink) and (
            self.kind, self.handle, self.key, self.url
        ) == (other.kind, other.handle, other.key, other.url)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        # The key is a decryption secret: never print it.
        return "<MegaLink %s handle=%s key=%s>" % (
            self.kind, self.handle, "set" if self.key else "missing")


def parse_url(value):
    """Parse a Mega share URL into a :class:`MegaLink`.

    Supports the current ``/file/<handle>#<key>`` and
    ``/folder/<handle>#<key>`` forms plus the legacy
    ``/#!<handle>!<key>`` and ``/#F!<handle>!<key>`` forms.  ``mega.co.nz`` is
    normalised to ``mega.nz``.
    """
    parts = policy.split_url(value)
    if parts is None:
        raise InvalidURL("that is not a Mega URL")
    host = (parts.hostname or "").lower().rstrip(".")
    if not policy.host_matches(host, MEGA_HOSTS):
        raise InvalidURL("that is not a Mega URL")

    path = (parts.path or "").strip("/")
    fragment = (parts.fragment or "").strip()
    kind = ""
    handle = ""
    key = ""

    if path.startswith("file/"):
        kind = "file"
        handle = path[len("file/"):].split("/", 1)[0]
        key = fragment
    elif path.startswith("folder/"):
        kind = "folder"
        handle = path[len("folder/"):].split("/", 1)[0]
        key = fragment
    elif fragment.startswith("F!"):
        kind = "folder"
        handle, _sep, key = fragment[2:].partition("!")
    elif fragment.startswith("!"):
        kind = "file"
        handle, _sep, key = fragment[1:].partition("!")

    if not kind:
        raise UnsupportedURL("that Mega URL is neither a file nor a folder")
    handle = handle.strip()
    key = key.strip().rstrip("=")
    if not handle or not _HANDLE_RE.match(handle):
        raise InvalidURL("that Mega URL has an invalid file handle")
    if not key or not _KEY_RE.match(key):
        # A Mega URL without its key cannot be decrypted, even by the service.
        raise InvalidURL("that Mega URL is missing its decryption key")
    normalised = "https://mega.nz/%s/%s#%s" % (kind, handle, key)
    return MegaLink(kind, handle, key, normalised)


class MegaAdapter(Adapter):
    name = "mega"

    def __init__(self, enabled=False, native=None, logger=None):
        self.enabled = bool(enabled)
        self.native = native
        self.logger = logger

    def matches(self, url):
        parts = policy.split_url(url)
        if parts is None:
            return False
        return policy.host_matches(parts.hostname, MEGA_HOSTS)

    def resolve(self, url):
        link = parse_url(url)
        if link.kind == "folder":
            raise UnsupportedURL(
                "Mega folders are not a single playable audio file",
                fallback=False)
        if not self.enabled:
            raise UnsupportedURL(
                "Mega resolution is disabled in the Rave Resolver settings",
                fallback=False)
        if self.native is None:
            raise AdapterNotReady(
                "the in-process Mega adapter is not bundled; "
                "configure resolver_service_url or install the full adapter")
        try:
            value = self.native(link)
        except ResolveError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("Mega resolve failed (%s)" % type(exc).__name__)
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
