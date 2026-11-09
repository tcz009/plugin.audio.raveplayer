# -*- coding: utf-8 -*-
"""Thin client for the NAS ``POST /api/resolve`` fallback.

The service is optional.  It exists for providers the Kodi SDK does not bundle
(Mega's AES client, Podomatic page scraping, any future source).  In-process
direct/Mediafire/Drive adapters always run first.

Contract (also documented in ``docs/KODI-RESOLVER.md``)::

    POST <resolver_service_url>/api/resolve
    Authorization: Bearer <resolver_service_token>
    Content-Type: application/json

    {"url": "https://...", "provider": "mediafire"}

    200 {"url": "https://direct...", "provider": "mediafire",
         "expires_at": 1760000000, "headers": {"Referer": "..."} }

The client never logs the token, the request body or the returned signed URL.
Only a public http(s) result is accepted, so a compromised/misconfigured
service cannot point Kodi at the LAN.
"""

import datetime
import json
import time
import urllib.parse

from . import policy
from .base import (NotFound, ProviderError, Resolution, ServiceAuthError,
                   ServiceError, ServiceProtocolError)
from .http import HttpTransportError

DEFAULT_PATH = "/api/resolve"
MAX_RESPONSE_BYTES = 1024 * 1024
_DROP_HEADERS = frozenset(("authorization", "proxy-authorization", "host",
                           "content-length", "transfer-encoding",
                           "connection"))


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


class ServiceClient(object):
    """POST JSON to the resolver service and validate its answer."""

    def __init__(self, base_url, token="", timeout=25, http=None, logger=None,
                 dns_resolver=None):
        self.base_url = str(base_url or "")
        self.endpoint = endpoint(self.base_url) if self.base_url else ""
        self.token = str(token or "")
        self.timeout = float(timeout or 25)
        self.http = http
        self.logger = logger
        self.dns_resolver = dns_resolver or policy.default_dns_resolver

    @classmethod
    def from_settings(cls, settings, http, logger=None, dns_resolver=None):
        if not settings.service_configured:
            return None
        return cls(settings.service_url, settings.service_token,
                   timeout=settings.service_timeout, http=http,
                   logger=logger, dns_resolver=dns_resolver)

    def resolve(self, url, provider=None):
        if not self.endpoint:
            raise ServiceError("the resolver service is not configured")
        payload = {"url": str(url or "")}
        if provider:
            payload["provider"] = str(provider)
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
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
                "the resolver service rejected the configured token")
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
        provider = str(result.get("provider") or provider or "service")
        headers = _safe_headers(result.get("headers"))
        return Resolution(
            target, provider=provider, source="service",
            expires_at=_expiry(result), headers=headers,
            title=str(result.get("title") or ""),
            mime=str(result.get("mime") or ""),
            size=_size(result.get("size")))


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


def _expiry(result):
    value = result.get("expires_at")
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return parsed.timestamp()
        except (ValueError, OverflowError):
            pass
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
