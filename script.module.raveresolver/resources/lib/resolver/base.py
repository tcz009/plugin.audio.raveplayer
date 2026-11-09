# -*- coding: utf-8 -*-
"""Resolver protocol, result object and typed failures.

The module is deliberately plain Python 3: no requests, no dataclasses, no
third-party packages.  Kodi 20 (Nexus) through Kodi 22 (Piers) can import it
unchanged, and the whole SDK can be exercised outside Kodi with the test stubs.

Adapters are small objects with two methods:

``matches(url)``
    Cheap, syntax-only check: does this adapter own the URL?

``resolve(url)``
    Return a :class:`Resolution` or raise a :class:`ResolveError` subclass.

An adapter must never log a full URL or a service token.  Errors carry a
short, host-only description instead (see :mod:`resolver.log`).
"""


class ResolveError(Exception):
    """Base class for every expected resolver failure.

    ``fallback`` tells the manager whether asking the NAS service could still
    succeed.  It is False for policy failures (private/loopback addresses,
    malformed URLs) so a service can never be used to bypass the SSRF guard.
    """

    code = 502
    fallback = True

    def __init__(self, message, code=None, fallback=None):
        super(ResolveError, self).__init__(message)
        self.message = str(message)
        if code is not None:
            self.code = int(code)
        if fallback is not None:
            self.fallback = bool(fallback)


class InvalidURL(ResolveError):
    """The value is not an absolute http(s) URL we are willing to handle."""

    code = 400
    fallback = False


class BlockedURL(ResolveError):
    """The URL points at loopback, a private network or a local-only host."""

    code = 403
    fallback = False


class HostNotAllowed(ResolveError):
    """Public host, but not on the direct-download allowlist.

    This is deliberately fallback-eligible: the NAS service keeps its own
    allowlist and may know a source the Kodi SDK does not.
    """

    code = 403
    fallback = True


class UnsupportedURL(ResolveError):
    """No in-process adapter knows this provider (or the provider is off)."""

    code = 400
    fallback = True


class AdapterNotReady(ResolveError):
    """The adapter exists but its network implementation is not bundled."""

    code = 503
    fallback = True


class NotFound(ResolveError):
    """The provider answered, but the file/page no longer exists."""

    code = 404
    fallback = False


class ProviderError(ResolveError):
    """The provider answered with an error we cannot fix in-process."""

    code = 502
    fallback = True


class ProviderTimeout(ProviderError):
    """The provider did not answer inside the configured timeout."""

    code = 504


class RateLimited(ProviderError):
    """The provider asked us to back off (HTTP 429)."""

    code = 429

    def __init__(self, message, retry_after=None, code=None, fallback=None):
        super(RateLimited, self).__init__(message, code=code, fallback=fallback)
        self.retry_after = retry_after


class ServiceError(ResolveError):
    """The NAS resolver service was configured but could not answer."""

    code = 502
    fallback = False


class ServiceAuthError(ServiceError):
    """The NAS resolver service rejected the configured token."""

    code = 401


class ServiceProtocolError(ServiceError):
    """The NAS resolver service returned something the SDK cannot trust."""

    code = 502


class Resolution(object):
    """One resolved, directly playable HTTP(S) URL.

    ``provider`` is ``direct``, ``mediafire``, ``drive``, ``podomatic``,
    ``mega`` or ``service``.  ``source`` says where the answer came from:
    ``in-process`` or ``service``.

    ``headers`` carries only headers a media request may need (for example a
    Referer).  The SDK never puts the service token in this mapping.
    """

    __slots__ = ("url", "provider", "source", "expires_at", "headers",
                 "title", "mime", "size")

    def __init__(self, url, provider="direct", source="in-process",
                 expires_at=None, headers=None, title="", mime="", size=None):
        self.url = str(url or "")
        self.provider = str(provider or "direct")
        self.source = str(source or "in-process")
        self.expires_at = expires_at
        self.headers = dict(headers or {})
        self.title = str(title or "")
        self.mime = str(mime or "")
        self.size = size

    def is_expired(self, now=None):
        """True when the signed URL is known to have expired."""
        if not self.expires_at:
            return False
        import time

        return float(self.expires_at) <= float(now if now is not None else time.time())

    @property
    def expired(self):
        return self.is_expired()

    def kodi_url(self):
        """Return the URL with Kodi's ``|Header=value`` suffix when needed.

        Kodi understands ``https://host/file.mp3|User-Agent=...&Referer=...``
        for both playback and :func:`resources.lib.http.open_media`.  Header
        names/values are percent-encoded so a query string cannot smuggle a
        second header through the suffix.
        """
        if not self.headers:
            return self.url
        import urllib.parse

        pairs = []
        for key, value in self.headers.items():
            if not key or value is None:
                continue
            if any(char in str(key) + str(value) for char in ("\r", "\n")):
                continue
            pairs.append("%s=%s" % (urllib.parse.quote(str(key), safe=""),
                                    urllib.parse.quote(str(value), safe="")))
        if not pairs:
            return self.url
        return self.url + "|" + "&".join(pairs)

    def as_dict(self):
        return {
            "url": self.url,
            "provider": self.provider,
            "source": self.source,
            "expires_at": self.expires_at,
            "headers": dict(self.headers),
            "title": self.title,
            "mime": self.mime,
            "size": self.size,
        }

    def __repr__(self):
        # Never include the URL itself: signed provider URLs are credentials.
        return "<Resolution %s provider=%s source=%s>" % (
            "expired" if self.expired else "ready", self.provider, self.source)


class Adapter(object):
    """Base adapter interface.

    Subclasses set ``name`` and implement :meth:`matches` and :meth:`resolve`.
    Keeping construction cheap matters: the manager builds all adapters for
    every plugin invocation that needs a resolve.
    """

    name = "base"

    def matches(self, url):
        raise NotImplementedError

    def resolve(self, url):
        raise NotImplementedError


# Historical/descriptive alias used by the docs and by downstream add-ons.
BaseAdapter = Adapter
