# -*- coding: utf-8 -*-
"""Tiny HTTP layer: standard library only, JSON in, friendly failures out.

Hardening in 3.9.11:

- response bodies are read in bounded chunks with a wall-clock deadline, so a
  broken or hostile server cannot stream forever or hand the plugin an
  unbounded body (the previous ``response.read()`` had no size or time bound);
- gzip/deflate bodies are capped *after* decompression as well (zip-bomb guard);
- every plugin invocation gets a network budget via :func:`begin_route`
  (``routes.dispatch`` sets it), and every fetch is clamped to the remaining
  budget, so no route can block Kodi on network I/O indefinitely.
"""

import codecs
import gzip
import http.client
import io
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

from . import cache, kodi

USER_AGENT = "RavePlayer/3.0 (Kodi; +https://github.com/tcz009/plugin.audio.raveplayer)"
DEFAULT_TIMEOUT = 20
MAX_BODY_BYTES = 8 * 1024 * 1024  # 8 MiB compressed body, and 8 MiB decompressed
READ_CHUNK_BYTES = 64 * 1024
ROUTE_BUDGET_SECONDS = 20.0

_XML_ENCODING_RE = re.compile(br"""<\?xml[^>]*encoding=["']([A-Za-z0-9._-]+)""", re.IGNORECASE)

_deadline = None
_budget_exhausted = False


# --------------------------------------------------------------------- budget


def begin_route(seconds=ROUTE_BUDGET_SECONDS):
    """Start a per-invocation network budget (called by ``routes.dispatch``).

    ``seconds`` bounds the total time all HTTP work on this plugin invocation
    may consume.  Callers that never call this (unit tests, direct helpers)
    keep the old per-request timeout behaviour.
    """
    global _deadline, _budget_exhausted
    try:
        budget = float(seconds)
    except (TypeError, ValueError):
        budget = ROUTE_BUDGET_SECONDS
    _deadline = time.monotonic() + max(0.0, budget)
    _budget_exhausted = False


def end_route():
    """Clear the per-invocation network budget."""
    global _deadline, _budget_exhausted
    _deadline = None
    _budget_exhausted = False


def remaining():
    """Seconds left in the current route budget, or None when unbudgeted."""
    if _deadline is None:
        return None
    return max(0.0, _deadline - time.monotonic())


def route_budget_exhausted():
    """True when a fetch was skipped because the route budget ran out."""
    return _budget_exhausted


def _effective_timeout(timeout):
    global _budget_exhausted
    left = remaining()
    if left is None:
        try:
            return float(timeout)
        except (TypeError, ValueError):
            return float(DEFAULT_TIMEOUT)
    if left <= 0:
        _budget_exhausted = True
        return 0.0
    try:
        wanted = float(timeout)
    except (TypeError, ValueError):
        wanted = float(DEFAULT_TIMEOUT)
    if wanted <= 0:
        return left
    return min(wanted, left)


# ------------------------------------------------------------------- decoding


def _charset(headers, raw):
    """Pick a text encoding, preferring a BOM or XML declaration.

    A surprising number of podcast feeds are served as ``application/xml``
    without a charset but declare ISO-8859-1 inside the document.  Trusting
    UTF-8 unconditionally mangles those titles.
    """
    if raw.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"
    charset = headers.get_content_charset()
    if not charset:
        match = _XML_ENCODING_RE.match(raw[:256])
        if match:
            charset = match.group(1).decode("ascii", "replace")
    if not charset:
        return "utf-8"
    try:
        codecs.lookup(charset)
    except LookupError:
        kodi.log("unknown charset %r; falling back to utf-8" % charset)
        return "utf-8"
    return charset


def _read_limited(response, timeout):
    """Read a response body with a byte cap and a wall-clock deadline.

    Returns ``bytes`` or ``None`` when the body is too large or took too long.
    """
    try:
        deadline = time.monotonic() + max(0.001, float(timeout))
    except (TypeError, ValueError):
        deadline = time.monotonic() + DEFAULT_TIMEOUT
    try:
        declared = int(response.headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        declared = 0
    if declared > MAX_BODY_BYTES:
        kodi.log("response declares %d bytes; abandoning" % declared, level=30)
        return None
    chunks, total = [], 0
    while True:
        if time.monotonic() > deadline:
            kodi.log("response read exceeded its deadline; abandoning", level=30)
            return None
        chunk = response.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        if not isinstance(chunk, (bytes, bytearray)):
            kodi.log("response returned non-byte data; abandoning", level=30)
            return None
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            kodi.log("response body exceeds %d bytes; abandoning" % MAX_BODY_BYTES, level=30)
            return None
        chunks.append(bytes(chunk))
    return b"".join(chunks)


def _decompress(headers, raw):
    """Undo Content-Encoding, capping the decompressed size (zip-bomb guard)."""
    encoding = (headers.get("Content-Encoding") or "").strip().lower()
    if not encoding:
        return raw
    try:
        if "gzip" in encoding:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                body = stream.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                kodi.log("decompressed response too large; abandoning", level=30)
                return None
            return body
        if encoding == "deflate":
            body = zlib.decompressobj().decompress(raw, MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                kodi.log("decompressed response too large; abandoning", level=30)
                return None
            return body
    except (OSError, EOFError, zlib.error) as exc:
        kodi.log("could not decompress response (%s)" % exc, level=30)
        return None
    return raw


def _decode(response, timeout=DEFAULT_TIMEOUT):
    """Read and decode a response body; ``None`` on any failure."""
    raw = _read_limited(response, timeout)
    if raw is None:
        return None
    raw = _decompress(response.headers, raw)
    if raw is None:
        return None
    try:
        return raw.decode(_charset(response.headers, raw), "replace")
    except (LookupError, UnicodeError) as exc:  # pragma: no cover - defensive
        kodi.log("could not decode response (%s)" % exc, level=30)
        return None


# ------------------------------------------------------------------- requests


def _cache_key(kind, url, headers):
    header_part = "&".join(
        "%s=%s" % (str(key).lower(), value)
        for key, value in sorted((headers or {}).items())
    )
    return "http:%s:%s:%s" % (kind, url, header_part)


def _request(url, timeout, headers):
    """Perform one request and return the decoded body, or None on failure."""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for key, value in (headers or {}).items():
            request.add_header(str(key), str(value))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _decode(response, timeout)
    except urllib.error.HTTPError as exc:
        try:
            exc.close()
        except Exception:
            pass
        kodi.log("fetch failed: %s (%s)" % (url, exc), level=30)
        return None
    except (
        urllib.error.URLError,
        http.client.HTTPException,
        socket.timeout,
        OSError,
        ValueError,
        TypeError,
        EOFError,
        zlib.error,
        UnicodeError,
    ) as exc:
        kodi.log("fetch failed: %s (%s)" % (url, exc), level=30)
        return None


def _fetch_for_cache(url, timeout, headers):
    """Fetch text for the cache; an empty 200 is a hiccup, not content."""
    body = _request(url, timeout, headers)
    return body if body else None


def fetch(url, timeout=DEFAULT_TIMEOUT, headers=None, ttl=0):
    """Return the response body as text, or None on any failure.

    When ``ttl`` is greater than zero the body is cached on disk for that
    many seconds.  Cache failures are ignored.  The timeout is clamped to the
    remaining route budget; when no budget remains the request is skipped.
    A cached body is still served after the budget is gone.
    """
    if not ttl:
        effective = _effective_timeout(timeout)
        if effective <= 0:
            kodi.log("network budget exhausted; skipping fetch of %s" % url, level=30)
            return None
        return _request(url, effective, headers)
    key = _cache_key("text", url, headers)
    cached = cache.get(key, ttl)
    if cached is not cache.MISSING:
        return cached
    effective = _effective_timeout(timeout)
    if effective <= 0:
        kodi.log("network budget exhausted; skipping fetch of %s" % url, level=30)
        return None
    return cache.remember(key, ttl, lambda: _fetch_for_cache(url, effective, headers))


def _parse_json(url, body):
    if body is None:
        return None
    try:
        return json.loads(body)
    except ValueError as exc:
        kodi.log("bad JSON from %s (%s)" % (url, exc), level=30)
        return None


def fetch_json(url, timeout=DEFAULT_TIMEOUT, headers=None, ttl=0):
    """Fetch and parse JSON, or return None when the server misbehaves."""
    if not ttl:
        return _parse_json(url, fetch(url, timeout=timeout, headers=headers))
    key = _cache_key("json", url, headers)
    return cache.remember(
        key, ttl, lambda: _parse_json(url, fetch(url, timeout=timeout, headers=headers))
    )


def quote(value):
    return urllib.parse.quote(value, safe="")
