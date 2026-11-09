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
import threading
import time
import urllib.parse

from . import policy
from .base import (BlockedURL, InvalidURL, NotFound, ProviderError,
                   ProviderTimeout, RateLimited, Resolution, ServiceAuthError,
                   ServiceError, ServiceProtocolError, UnsupportedURL)
from .http import HttpTransportError, retry_after_seconds

DEFAULT_PATH = "/api/resolve"
DEFAULT_COOKIE_NAME = "raveplayer_session"
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_STREAM_PATH = 8192
MAX_RETRY_AFTER = 120
DEFAULT_RESULT_TTL = 300.0
MAX_RESULT_ENTRIES = 256
MAX_INFLIGHT = 64
_UNSAFE_PATH_RE = re.compile(r"[\x00-\x1f\x7f]")
_CODE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


def _service_base_parts(base_url):
    """Parse ``base_url`` for the operator-configured service.

    A bare ``host:port`` is accepted (``http://`` is assumed), matching the
    plugin's ``webapi.normalise_base``.  The service base is the one URL that
    may use a non-80/443 port, but link-local and cloud-metadata targets are
    still refused: the request carries the Bearer token.
    """
    text = str(base_url or "").strip()
    if (not text or len(text) > 8192
            or any(char in text for char in ("\r", "\n", "\x00", "\x7f"))):
        raise ServiceError("resolver_service_url is not a valid http(s) URL")
    if "://" not in text:
        text = "http://" + text
    parts = policy.split_url(text, allowed_ports=None)
    if parts is None:
        raise ServiceError("resolver_service_url is not a valid http(s) URL")
    if parts.query or parts.fragment:
        raise ServiceError("resolver_service_url must not carry a query/fragment")
    if policy.service_host_blocked(parts.hostname):
        raise ServiceError(
            "resolver_service_url must not point at a link-local or "
            "metadata address")
    return parts


def endpoint(base_url):
    """Return the validated ``.../api/resolve`` endpoint for ``base_url``.

    Accepts ``nas:8080`` or ``http://nas:8080`` (the common LAN case), a
    reverse-proxy prefix such as ``https://rave.example/resolver``, or an
    already-complete ``.../api/resolve`` URL.  Credentials in the URL are
    refused so the token has one place to live.
    """
    parts = _service_base_parts(base_url)
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
    parts = _service_base_parts(base_url)
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


class _Flight(object):
    """One in-progress resolve that identical callers can wait on."""

    __slots__ = ("event", "result", "error")

    def __init__(self):
        self.event = threading.Event()
        self.result = None
        self.error = None


class ServiceResultCache(object):
    """Bounded TTL cache + single-flight for ``POST /api/resolve`` results.

    Keys are the requested URL, so two callers asking for the same page share
    one service request (the provider hint is derived from the URL by the
    manager and never splits the cache).  A successful
    result is kept for at most :data:`DEFAULT_RESULT_TTL`, clamped to the
    result's own ``expires_at``: a signed stream that expires in 30 seconds is
    never served for five minutes.  Errors are never cached (a transient 429
    must not keep failing after the back-off).

    The cache is in memory only: it is bounded (LRU) and dies with the Kodi
    process, which avoids writing signed service URLs to disk on top of the
    adapter cache.
    """

    def __init__(self, ttl=DEFAULT_RESULT_TTL, max_entries=MAX_RESULT_ENTRIES,
                 clock=None, max_inflight=MAX_INFLIGHT, wait_timeout=90.0):
        try:
            self.ttl = max(0.0, float(ttl))
        except (TypeError, ValueError, OverflowError):
            self.ttl = DEFAULT_RESULT_TTL
        self.max_entries = max(1, int(max_entries))
        self.max_inflight = max(1, int(max_inflight))
        self.wait_timeout = max(0.1, float(wait_timeout))
        self.clock = clock or time.time
        self._entries = {}
        self._order = []
        self._inflight = {}
        self._lock = threading.RLock()

    @staticmethod
    def key(url, provider=None):
        return str(url or "")

    def get(self, url, provider=None):
        """Return a live :class:`Resolution` or ``None``."""
        key = self.key(url, provider)
        now = self.clock()
        with self._lock:
            record = self._entries.get(key)
            if record is None:
                return None
            expires_at, result = record
            if expires_at <= now:
                self._drop_locked(key)
                return None
            self._touch_locked(key)
            return result

    def put(self, url, provider, result):
        """Store one successful resolution; returns True when cached."""
        if not isinstance(result, Resolution):
            return False
        now = self.clock()
        lifetime = self.ttl
        if result.expires_at:
            try:
                remaining = float(result.expires_at) - now
            except (TypeError, ValueError, OverflowError):
                remaining = 0.0
            if remaining <= 0:
                return False
            lifetime = min(lifetime, remaining)
        if lifetime <= 0:
            return False
        key = self.key(url, provider)
        with self._lock:
            self._entries[key] = (now + lifetime, result)
            self._touch_locked(key)
            while len(self._order) > self.max_entries:
                self._drop_locked(self._order[0])
        return True

    def run(self, url, provider, factory):
        """Return the cached result, or resolve once for identical callers."""
        key = self.key(url, provider)
        cached = self.get(url, provider)
        if cached is not None:
            return cached
        flight = None
        owner = False
        with self._lock:
            # Close the race between the first lookup and taking the flight:
            # another caller may have filled the cache in that window.
            record = self._entries.get(key)
            if record is not None and record[0] > self.clock():
                self._touch_locked(key)
                return record[1]
            flight = self._inflight.get(key)
            if flight is None and len(self._inflight) < self.max_inflight:
                flight = _Flight()
                self._inflight[key] = flight
                owner = True
        if flight is not None and not owner:
            flight.event.wait(self.wait_timeout)
            if flight.error is not None:
                raise flight.error
            if flight.result is not None:
                return flight.result
            # The owner died without publishing a result; resolve ourselves.
        try:
            result = factory()
        except Exception as exc:
            if owner:
                self._finish(key, flight, error=exc)
            raise
        if owner:
            self.put(url, provider, result)
            self._finish(key, flight, result=result)
        return result

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._order = []
            self._inflight.clear()

    def __len__(self):
        now = self.clock()
        with self._lock:
            for key in list(self._entries):
                if self._entries[key][0] <= now:
                    self._drop_locked(key)
            return len(self._entries)

    def _finish(self, key, flight, result=None, error=None):
        with self._lock:
            self._inflight.pop(key, None)
        flight.result = result
        flight.error = error
        flight.event.set()

    def _touch_locked(self, key):
        try:
            self._order.remove(key)
        except ValueError:
            pass
        self._order.append(key)

    def _drop_locked(self, key):
        self._entries.pop(key, None)
        try:
            self._order.remove(key)
        except ValueError:
            pass


class ServiceClient(object):
    """POST JSON to the resolver service and validate its answer."""

    def __init__(self, base_url, token="", timeout=25, http=None, logger=None,
                 dns_resolver=None, cookie="", cookie_name=DEFAULT_COOKIE_NAME,
                 result_cache=None):
        self.base_url = str(base_url or "")
        self.endpoint = endpoint(self.base_url) if self.base_url else ""
        self.stream_base = stream_base(self.base_url) if self.base_url else ""
        self.token = str(token or "").strip()
        self.cookie = cookie_header(cookie, cookie_name)
        self.timeout = float(timeout or 25)
        self.http = http
        self.logger = logger
        self.dns_resolver = dns_resolver or policy.default_dns_resolver
        self.result_cache = result_cache

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
    def from_settings(cls, settings, http, logger=None, dns_resolver=None,
                      result_cache=None):
        if not settings.service_configured:
            return None
        return cls(settings.service_url, token=settings.service_token,
                   cookie=settings.service_cookie,
                   timeout=settings.service_timeout, http=http,
                   logger=logger, dns_resolver=dns_resolver,
                   result_cache=result_cache)

    def resolve(self, url, provider=None):
        if not self.endpoint:
            raise ServiceError("the resolver service is not configured")
        if self.result_cache is not None:
            return self.result_cache.run(
                url, provider, lambda: self._resolve_once(url, provider))
        return self._resolve_once(url, provider)

    def _resolve_once(self, url, provider=None):
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
        if status < 200 or status >= 300:
            _raise_service_error(response, status)

        payload = _json_body(response)
        if payload is None:
            raise ServiceProtocolError(
                "the resolver service returned invalid JSON")
        if payload.get("ok") is False:
            error = _typed_error(_error_code(payload),
                                 _retry_after(response, payload))
            if error is not None:
                raise error
            raise ServiceError(
                "the resolver service could not resolve that URL")
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
            # normally a LAN/Tailscale address.  allowed_ports=None keeps a
            # non-standard service port; media hosts are not involved.
            return policy.check_url(
                absolute, allow_private=True, resolve_dns=False,
                allowed_ports=None)
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


def _error_code(payload):
    """The web's stable error ``code`` from a top-level or nested payload."""
    if not isinstance(payload, dict):
        return ""
    for candidate in (payload, payload.get("result"), payload.get("data")):
        if not isinstance(candidate, dict):
            continue
        value = candidate.get("code")
        if isinstance(value, str):
            text = value.strip().lower()
            if _CODE_RE.match(text):
                return text
    return ""


def _retry_after(response, payload):
    """Numeric/date ``Retry-After`` header, then a JSON ``retry_after``."""
    retry = retry_after_seconds(
        getattr(response, "headers", {}), default=None,
        maximum=MAX_RETRY_AFTER)
    if retry is not None:
        return retry
    if not isinstance(payload, dict):
        return None
    for candidate in (payload, payload.get("result"), payload.get("data")):
        if not isinstance(candidate, dict):
            continue
        for key in ("retry_after", "retryAfter"):
            value = candidate.get(key)
            try:
                seconds = int(float(value))
            except (TypeError, ValueError):
                continue
            return max(1, min(seconds, MAX_RETRY_AFTER))
    return None


def _typed_error(code, retry_after=None):
    """Map a web error ``code`` to the SDK's typed exception, or ``None``."""
    if not code:
        return None
    if code == "not_found":
        return NotFound("the resolver service has no stream for that URL")
    if code == "rate_limited":
        return RateLimited(
            "the resolver service is rate-limiting requests",
            retry_after=retry_after)
    if code == "timeout":
        return ProviderTimeout("the resolver service timed out")
    if code == "upstream":
        return ProviderError("the resolver service could not reach the provider")
    if code == "blocked":
        return BlockedURL("the resolver service blocked that URL")
    if code == "invalid":
        return InvalidURL("the resolver service rejected that URL")
    if code in ("unsupported", "unknown", "not_supported"):
        return UnsupportedURL("the resolver service cannot resolve that source")
    if code == "unauthorized":
        return ServiceAuthError(
            "the resolver service rejected the configured credentials")
    return None


def _raise_service_error(response, status):
    """Raise a typed error for a non-2xx ``/api/resolve`` response.

    The web returns HTTP 400 for policy failures and puts the specific reason
    in the JSON ``code``; collapsing all of these into ``ServiceError`` would
    discard the reason (and a 429's ``Retry-After``).
    """
    payload = _json_body(response)
    code = _error_code(payload)
    retry = _retry_after(response, payload or {})
    if status in (401, 403):
        raise ServiceAuthError(
            "the resolver service rejected the configured credentials")
    if status in (301, 302, 303, 307, 308):
        raise ServiceProtocolError(
            "the resolver service redirected unexpectedly")
    error = _typed_error(code, retry)
    if error is not None:
        raise error
    if status == 429:
        raise RateLimited(
            "the resolver service is rate-limiting requests",
            retry_after=retry if retry is not None else 5)
    if status == 504:
        raise ProviderTimeout("the resolver service timed out")
    if status in (404, 410):
        raise NotFound("the resolver service has no stream for that URL")
    if status in (502, 503):
        raise ProviderError(
            "the resolver service could not answer (HTTP %s)" % status)
    raise ServiceError("the resolver service returned HTTP %s" % status)


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
    """Only media-request headers survive; see :func:`policy.sanitize_headers`."""
    return policy.sanitize_headers(value)
