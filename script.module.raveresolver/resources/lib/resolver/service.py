# -*- coding: utf-8 -*-
"""Thin client for the NAS ``POST /api/resolve`` fallback.

The service is optional.  It exists for providers the Kodi SDK does not bundle
(Mega's AES client, Podomatic page scraping, any future source).  In-process
direct/Mediafire/Drive adapters always run first.

Contract (also documented in ``docs/KODI-RESOLVER.md``)::

    POST <service base>/api/resolve
    Accept: application/json
    Content-Type: application/json
    Authorization: Bearer <resolver_service_token>   # auth mode A
    Cookie: raveplayer_session=<signed cookie>       # auth mode B

    {"url": "https://...", "provider": "mega"}

    200 (web 1.6.64)::

        {"ok": true,
         "url": "https://gfs....userstorage.mega.co.nz/dl/...",
         "headers": {"Referer": "..."},
         "expires": 1760000000,
         "source": "mega",
         "host": "gfs....userstorage.mega.co.nz",
         "stream": "/api/mega/stream?u=...&e=1760000000&t=..."}

``url`` for a MEGA source is AES-CTR **ciphertext**, not audio.  When
``source == "mega"`` and ``stream`` is present the client returns the absolute
signed stream URL (base + relative path) and never the ciphertext.  If the
service omits ``stream`` the resolve fails with
:class:`ServiceProtocolError`; there is deliberately no ciphertext fallback.

Kodi asks the returned stream URL directly.  The HMAC is in the signed query,
so the player must not append ``Authorization``/``Cookie`` headers (or a
service token) to that media request.  Range/HEAD handling belongs to the
player and the web stream proxy; this module never proxies bytes.

The client never logs the token, the cookie, the request body or a returned
signed URL.  Non-Mega results must be public http(s) URLs, so a compromised or
misconfigured service cannot point Kodi at the LAN.  A MEGA stream URL is
built from the operator-configured service base, so a LAN/Tailscale base is
allowed there and no service-supplied absolute URL is followed.
"""

import datetime
import json
import re
import time
import urllib.parse

from . import policy
from .base import (NotFound, ProviderError, Resolution, ServiceAuthError,
                   ServiceError, ServiceProtocolError)
from .http import HttpTransportError

DEFAULT_PATH = "/api/resolve"
DEFAULT_COOKIE_NAME = "raveplayer_session"
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_STREAM_PATH = 8192
_DROP_HEADERS = frozenset(("authorization", "proxy-authorization", "host",
                           "cookie", "set-cookie", "content-length",
                           "transfer-encoding", "connection"))
_UNSAFE_PATH_RE = re.compile(r"[\x00-\x1f\x7f]")


def endpoint(base_url):
    """Return the validated ``.../api/resolve`` endpoint for ``base_url``.

    Accepts ``http://nas:8080`` (the common LAN case), a reverse-proxy prefix
    such as ``https://rave.example/resolver``, or an already-complete
    ``.../api/resolve`` URL.  Credentials in the URL are refused so the token
    has one place to live.
    """
    parts = policy.split_url(base_url)
    if parts is None:
        raise ServiceError("resolver_service_url is not a valid http(s) URL")
    if parts.query or parts.fragment:
        raise ServiceError("resolver_service_url must not carry a query/fragment")
    path = (parts.path or "").rstrip("/")
    if path.endswith(DEFAULT_PATH):
        final_path = path
    elif path.endswith("/api"):
        final_path = path + "/resolve"
    else:
        final_path = path + DEFAULT_PATH
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc, final_path, "", ""))


def stream_base(base_url):
    """Return the ``scheme://host[:port][/prefix]`` base for signed streams.

    The resolve endpoint is ``<base>/api/resolve``; the web returns ``stream``
    as a root-relative ``/api/mega/stream?...`` path.  A reverse-proxy prefix
    on the configured base (``https://rave.example/resolver``) is preserved so
    the media URL is ``https://rave.example/resolver/api/mega/stream?...``.
    """
    parts = policy.split_url(base_url)
    if parts is None:
        raise ServiceError("resolver_service_url is not a valid http(s) URL")
    if parts.query or parts.fragment:
        raise ServiceError("resolver_service_url must not carry a query/fragment")
    path = (parts.path or "").rstrip("/")
    if path.endswith(DEFAULT_PATH):
        path = path[:-len(DEFAULT_PATH)]
    elif path.endswith("/api"):
        path = path[:-len("/api")]
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc, path, "", ""))


def cookie_header(value, name=DEFAULT_COOKIE_NAME):
    """Normalise a configured session cookie into a ``Cookie`` header value.

    The setting accepts either the whole pair (``raveplayer_session=...``) or
    a bare value.  Line breaks are refused: a setting must never be able to
    inject a second header.  An empty value disables cookie auth.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if "\r" in text or "\n" in text or "\x00" in text:
        raise ServiceError("resolver_service_cookie must not contain line breaks")
    if "=" not in text:
        return "%s=%s" % (name or DEFAULT_COOKIE_NAME, text)
    return text


class ServiceClient(object):
    """POST JSON to the resolver service and validate its answer."""

    def __init__(self, base_url, token="", timeout=25, http=None, logger=None,
                 dns_resolver=None, cookie="", cookie_name=DEFAULT_COOKIE_NAME):
        self.base_url = str(base_url or "")
        self.endpoint = endpoint(self.base_url) if self.base_url else ""
        self.stream_base = stream_base(self.base_url) if self.base_url else ""
        self.token = str(token or "").strip()
        self.cookie = cookie_header(cookie, cookie_name)
        self.timeout = float(timeout or 25)
        self.http = http
        self.logger = logger
        self.dns_resolver = dns_resolver or policy.default_dns_resolver

    @property
    def auth_mode(self):
        """``bearer``, ``cookie`` or ``none`` (Bearer wins when both are set)."""
        if self.token:
            return "bearer"
        if self.cookie:
            return "cookie"
        return "none"

    def auth_headers(self):
        """Return the one configured auth header, never both.

        Bearer is the forward path (web ``RAVEWEB_RESOLVER_TOKEN``); the
        session cookie is the temporary compatibility mode for web builds
        that only accept a browser session.
        """
        if self.token:
            return {"Authorization": "Bearer " + self.token}
        if self.cookie:
            return {"Cookie": self.cookie}
        return {}

    @classmethod
    def from_settings(cls, settings, http, logger=None, dns_resolver=None):
        if not settings.service_configured:
            return None
        return cls(settings.service_url, token=settings.service_token,
                   cookie=settings.service_cookie,
                   timeout=settings.service_timeout, http=http,
                   logger=logger, dns_resolver=dns_resolver)

    def resolve(self, url, provider=None):
        if not self.endpoint:
            raise ServiceError("the resolver service is not configured")
        payload = {"url": str(url or "")}
        if provider:
            payload["provider"] = str(provider)
        headers = {"Accept": "application/json"}
        headers.update(self.auth_headers())
        try:
            response = self.http.request(
                "POST", self.endpoint, timeout=self.timeout,
                headers=headers, body=json.dumps(payload).encode("utf-8"),
                max_bytes=MAX_RESPONSE_BYTES, allow_private=True,
                allow_redirects=False)
        except HttpTransportError:
            raise ServiceError("the resolver service could not be reached")
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ServiceError("the resolver service request failed (%s)"
                               % type(exc).__name__)

        status = int(getattr(response, "status", 0) or 0)
        if status in (401, 403):
            raise ServiceAuthError(
                "the resolver service rejected the configured credentials")
        if status in (404, 410):
            raise NotFound("the resolver service has no stream for that URL")
        if status < 200 or status >= 300:
            raise ServiceError("the resolver service returned HTTP %s" % status)

        payload = _json_body(response)
        if payload is None:
            raise ServiceProtocolError(
                "the resolver service returned invalid JSON")
        if payload.get("ok") is False:
            raise ServiceError("the resolver service could not resolve that URL")
        result = payload
        for key in ("result", "data"):
            if isinstance(result.get(key), dict):
                result = result[key]
                break

        source = _source_name(result, provider)
        stream = result.get("stream")
        if source == "mega":
            return self._mega_resolution(result, stream)

        target = str(result.get("url") or "").strip()
        if not target:
            raise ServiceProtocolError(
                "the resolver service returned no URL")
        try:
            target = policy.check_url(
                target, resolve_dns=True, resolver=self.dns_resolver)
        except Exception:  # noqa: BLE001
            raise ServiceProtocolError(
                "the resolver service returned a non-public URL")
        headers = _safe_headers(result.get("headers"))
        return Resolution(
            target, provider=source or "service", source="service",
            expires_at=_expiry(result), headers=headers,
            title=str(result.get("title") or ""),
            mime=str(result.get("mime") or ""),
            size=_size(result.get("size")))

    # ------------------------------------------------------------- Mega stream
    def _mega_resolution(self, result, stream):
        """Build the playable signed URL for a MEGA payload.

        The raw ``url`` is AES-CTR ciphertext and is never returned.  If the
        web side did not include a usable ``stream`` the resolve fails closed.
        """
        signed = self.absolute_stream_url(stream)
        return Resolution(
            signed, provider="mega", source="service",
            # ``expires`` describes the storage URL; the playable token's own
            # ``e`` parameter is the expiry a caller should respect.
            expires_at=_stream_expiry(stream) or _expiry(result),
            # Headers in the payload belong to the raw storage request.  The
            # signed stream URL is self-authenticating, so adding them (or any
            # service auth header) could break the token and is not needed.
            headers={},
            title=str(result.get("title") or ""),
            mime=str(result.get("mime") or ""),
            size=_size(result.get("size")))

    def absolute_stream_url(self, stream):
        """Return ``stream_base + stream``, preserving the signed query.

        ``stream`` must be a root-relative path (the web contract).  It is
        appended to the operator-configured base, so a LAN or Tailscale base
        is allowed and no service-supplied absolute host is ever followed.
        """
        if not self.stream_base:
            raise ServiceProtocolError(
                "the resolver service has no stream base URL")
        text = str(stream or "").strip()
        if (not text or len(text) > MAX_STREAM_PATH
                or _UNSAFE_PATH_RE.search(text)
                or "\\" in text or "#" in text):
            raise ServiceProtocolError(
                "the resolver service returned an invalid MEGA stream path")
        if not text.startswith("/") or text.startswith("//"):
            raise ServiceProtocolError(
                "the resolver service returned a non-relative MEGA stream path")
        parts = urllib.parse.urlsplit(text)
        if parts.scheme or parts.netloc:
            raise ServiceProtocolError(
                "the resolver service returned a non-relative MEGA stream path")
        base = urllib.parse.urlsplit(self.stream_base)
        prefix = (base.path or "").rstrip("/")
        path = parts.path or ""
        if prefix and not (path == prefix or path.startswith(prefix + "/")):
            path = prefix + path
        absolute = urllib.parse.urlunsplit(
            (base.scheme, base.netloc, path, parts.query, ""))
        try:
            # allow_private: the service base is operator-configured and is
            # normally a LAN/Tailscale address.  Media hosts are not involved.
            return policy.check_url(
                absolute, allow_private=True, resolve_dns=False)
        except Exception:  # noqa: BLE001
            raise ServiceProtocolError(
                "the resolver service returned an invalid MEGA stream URL")


def _source_name(result, requested=None):
    """The web adapter id from ``source`` (new) or ``provider`` (legacy)."""
    for key in ("source", "provider"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return str(requested or "").strip().lower()


def _json_body(response):
    body = getattr(response, "body", b"") or b""
    if isinstance(body, str):
        text = body
    else:
        text = body.decode("utf-8", "replace")
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _stream_expiry(stream):
    """Parse the signed token's ``e`` expiry from a relative stream path."""
    try:
        query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(str(stream or "")).query,
            keep_blank_values=True)
        values = query.get("e") or []
        if not values:
            return None
        expiry = int(str(values[0]).strip())
    except (TypeError, ValueError):
        return None
    return float(expiry) if expiry > 0 else None


def _epoch(value):
    """Parse an epoch int/float/string or an ISO-8601 timestamp."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        number = None
    if number is not None:
        return number if number > 0 else None
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    try:
        return parsed.timestamp()
    except (OverflowError, OSError, ValueError):
        return None


def _expiry(result):
    """``expires`` (web 1.6.64), legacy ``expires_at``/``expires_in``."""
    for key in ("expires", "expires_at"):
        expiry = _epoch(result.get(key))
        if expiry is not None:
            return expiry
    value = result.get("expires_in")
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    return time.time() + max(0, seconds)


def _size(value):
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    return size if size > 0 else None


def _safe_headers(value):
    headers = {}
    if not isinstance(value, dict):
        return headers
    for key, item in value.items():
        name = str(key or "")
        if not name or name.lower() in _DROP_HEADERS:
            continue
        if isinstance(item, (str, int, float)):
            text = str(item)
            if "\r" in text or "\n" in text or "\r" in name or "\n" in name:
                continue
            headers[name] = text
    return headers
