# -*- coding: utf-8 -*-
"""Small, guarded HTTP client for resolver adapters.

Only the standard library is used.  Every request (including every redirect)
is re-checked by :mod:`resolver.policy`; the client never follows a redirect
blindly.  Bodies are capped, responses are closed promptly and errors carry a
host-only description so a signed URL never reaches a log.

The service adapter sets ``allow_private=True`` for its operator-configured
NAS URL.  That flag is never used for media URLs.
"""

import gzip
import urllib.error
import urllib.parse
import urllib.request
import zlib

from . import policy

USER_AGENT = "RaveResolver/1.0 (Kodi; +https://github.com/tcz009/plugin.audio.raveplayer)"
DEFAULT_TIMEOUT = 20
DEFAULT_MAX_BYTES = 4 * 1024 * 1024
MAX_REDIRECTS = 5
REDIRECT_CODES = (301, 302, 303, 307, 308)


class HttpTransportError(Exception):
    """The request did not complete (DNS, TLS, timeout, connection)."""

    def __init__(self, message, host=""):
        super(HttpTransportError, self).__init__(message)
        self.message = str(message)
        self.host = host


class ResponseTooLarge(Exception):
    """The peer sent more than the caller's byte cap."""


class HttpResponse(object):
    """A bounded response with a case-insensitive header helper."""

    def __init__(self, status, headers, body, final_url):
        self.status = int(status)
        self.headers = dict(headers or {})
        self.body = body or b""
        self.final_url = str(final_url or "")

    @property
    def text(self):
        return self.body.decode("utf-8", "replace")

    def header(self, name, default=""):
        wanted = str(name or "").lower()
        for key, value in self.headers.items():
            if str(key).lower() == wanted:
                return str(value or "")
        return default

    def __repr__(self):
        return "<HttpResponse status=%s bytes=%d>" % (self.status, len(self.body))


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Turn 3xx into an ``HTTPError`` so the caller can validate each hop."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpClient(object):
    """Guarded GET/POST helper.

    ``opener`` is injectable for tests; ``dns_resolver`` has the same contract
    as :func:`policy.default_dns_resolver` (returns address strings).
    """

    def __init__(self, timeout=DEFAULT_TIMEOUT, max_bytes=DEFAULT_MAX_BYTES,
                 dns_resolver=None, logger=None, opener=None):
        self.timeout = float(timeout)
        self.max_bytes = int(max_bytes)
        self.dns_resolver = dns_resolver or policy.default_dns_resolver
        self.logger = logger
        self._opener = opener or urllib.request.build_opener(
            _NoRedirectHandler())

    def fetch(self, url, timeout=None, headers=None, max_bytes=None,
              allowed_hosts=None, allow_private=False, allow_redirects=True,
              extra_hosts=None):
        return self.request("GET", url, timeout=timeout, headers=headers,
                            max_bytes=max_bytes, allowed_hosts=allowed_hosts,
                            allow_private=allow_private,
                            allow_redirects=allow_redirects,
                            extra_hosts=extra_hosts)

    def request(self, method, url, timeout=None, headers=None, body=None,
                max_bytes=None, allowed_hosts=None, allow_private=False,
                allow_redirects=True, extra_hosts=None):
        """Perform one guarded request and return :class:`HttpResponse`."""
        method = str(method or "GET").upper()
        cap = int(max_bytes or self.max_bytes)
        current = str(url or "").strip()
        request_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
        for key, value in (headers or {}).items():
            if key:
                request_headers[str(key)] = str(value)
        if body is not None and not any(
                str(key).lower() == "content-type" for key in request_headers):
            request_headers["Content-Type"] = "application/json"

        for hop in range(MAX_REDIRECTS + 1):
            try:
                policy.check_url(
                    current, allowed_hosts=allowed_hosts,
                    allow_private=allow_private, resolve_dns=False,
                    extra_hosts=extra_hosts)
            except Exception:
                raise
            if not allow_private:
                parts = policy.split_url(current)
                if parts is None or policy.host_is_blocked(
                        parts.hostname, parts.port, self.dns_resolver):
                    from .base import BlockedURL

                    raise BlockedURL("that URL resolves to a private address")
            encoded = body
            if isinstance(encoded, str):
                encoded = encoded.encode("utf-8")
            request = urllib.request.Request(
                current, data=encoded, headers=request_headers, method=method)
            effective_timeout = float(timeout or self.timeout)
            try:
                response = self._opener.open(request, timeout=effective_timeout)
                status = int(getattr(response, "status", 200) or 200)
                response_headers = dict(response.headers.items())
                final_url = str(response.geturl() or current)
            except urllib.error.HTTPError as exc:
                status = int(exc.code or 0)
                response_headers = dict(exc.headers.items()) if exc.headers else {}
                final_url = str(exc.geturl() or current)
                location = _header(response_headers, "Location")
                if (allow_redirects and status in REDIRECT_CODES and location
                        and hop < MAX_REDIRECTS):
                    try:
                        exc.close()
                    except Exception:  # noqa: BLE001
                        pass
                    current = urllib.parse.urljoin(current, location)
                    continue
                raw = _read_bounded(exc, cap)
                try:
                    exc.close()
                except Exception:  # noqa: BLE001
                    pass
                return HttpResponse(status, response_headers, raw, final_url)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                host = ""
                try:
                    host = (policy.split_url(current).hostname or "")
                except Exception:  # noqa: BLE001
                    pass
                raise HttpTransportError(
                    "request failed (%s)" % type(exc).__name__, host=host)

            raw = _read_bounded(response, cap)
            response_headers = _decode_body(response_headers, raw)
            raw = response_headers.pop("__body__", raw)
            try:
                response.close()
            except Exception:  # noqa: BLE001
                pass

            if (allow_redirects and status in REDIRECT_CODES
                    and _header(response_headers, "Location")
                    and hop < MAX_REDIRECTS):
                current = urllib.parse.urljoin(
                    final_url, _header(response_headers, "Location"))
                continue
            return HttpResponse(status, response_headers, raw, final_url)

        from .base import ProviderError

        raise ProviderError("too many redirects")


def _header(headers, name):
    wanted = str(name or "").lower()
    for key, value in (headers or {}).items():
        if str(key).lower() == wanted:
            return str(value or "")
    return ""


def _read_bounded(stream, cap):
    try:
        raw = stream.read(cap + 1)
    except Exception as exc:  # noqa: BLE001
        raise HttpTransportError("response read failed (%s)"
                                 % type(exc).__name__)
    if raw is None:
        raw = b""
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    if len(raw) > cap:
        raise ResponseTooLarge("response exceeded %d bytes" % cap)
    return bytes(raw)


def _decode_body(headers, raw):
    """Decompress a gzip/deflate body with the same byte cap.

    The decompressed result is stashed in a private header key so the caller
    can replace the body without changing the function signature.
    """
    encoding = _header(headers, "Content-Encoding").lower().strip()
    if not encoding or encoding == "identity":
        headers["__body__"] = raw
        return headers
    import io

    try:
        if "gzip" in encoding:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:
                decoded = handle.read(DEFAULT_MAX_BYTES + 1)
        elif "deflate" in encoding:
            decoded = zlib.decompress(raw, 15 + 32)
        else:
            decoded = raw
    except (OSError, EOFError, zlib.error, ValueError):
        decoded = raw
    if len(decoded) > DEFAULT_MAX_BYTES:
        raise ResponseTooLarge("decompressed response exceeded the cap")
    headers["__body__"] = decoded
    return headers
