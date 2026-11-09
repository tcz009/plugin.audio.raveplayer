# -*- coding: utf-8 -*-
"""Bounded client for the web app's JSON source APIs.

The 2026 web build exposes the sources that only exist server-side as small,
uniform JSON pages:

    GET /api/20bensons
    GET /api/ukraves
    GET /api/ezgarage
    GET /api/live
    GET /api/podcast/<feed>

Every payload carries a list of rows with the same shape::

    {"label": ..., "sub": ..., "play": ..., "art": ...,
     "fav": ..., "download": ..., "fact": ...}

``play`` is either an absolute stream URL (20bensons, Podomatic podcast
enclosures, live radio) or a path relative to the web base (EZ Garage, UK
Raves, which the NAS resolves and proxies through ``/stream``).  Lists are
paginated either with ``total`` + ``pager`` metadata or with a ``next`` link
that is a plain ``?page=N`` query.

This module deliberately has no Kodi import and no dependency on the add-on's
larger ``http`` module: it is a tiny urllib client so it can be unit tested
with an injected opener.  Security rules are local and explicit:

* the base URL is the operator-configured ``resolver_service_url`` (the web
  app is normally on the LAN/Tailscale, so the public-host guard does not
  apply to it);
* the bearer token is sent only to that service origin;
* redirects are never followed off that origin;
* response bodies are bounded by a byte cap and a wall-clock timeout;
* a failure raises :class:`WebAPIError`; directory routes turn that into an
  empty/status page rather than a traceback.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_BYTES = 1024 * 1024
DEFAULT_CACHE_TTL = 60.0
MAX_REDIRECTS = 2
PAGE_SIZE = 40
CACHE_LIMIT = 64
USER_AGENT = ("RavePlayer/3.9 (Kodi; "
              "+https://github.com/tcz009/plugin.audio.raveplayer)")

# Platform pages are never offered as playable rows.  The web API already
# omits YouTube/external hand-offs from UK Raves, but this is the local
# defence so a future row shape cannot put a browser page behind OK.
EXTERNAL_HOSTS = (
    "youtube.com", "youtu.be", "soundcloud.com", "mixcloud.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "vimeo.com", "dailymotion.com", "bandcamp.com",
)


class WebAPIError(RuntimeError):
    """A web source request failed (configuration, auth, network or shape)."""


# --------------------------------------------------------------------- urls


def normalise_base(value):
    """Return a clean service base URL, or ``""`` when it is unusable.

    A bare ``host:port`` is accepted and gets ``http://``.  Credentials, query
    strings, fragments and non-http(s) schemes are refused; the path is kept
    (a reverse proxy may mount the app below a prefix) but a trailing slash is
    removed so joining is predictable.
    """
    text = str(value or "").strip()
    if not text or any(char in text for char in ("\r", "\n", "\x00", "\x7f")):
        return ""
    if "://" not in text:
        text = "http://" + text
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return ""
    if parts.username or parts.password or parts.query or parts.fragment:
        return ""
    try:
        parts.port
    except ValueError:
        return ""
    path = (parts.path or "").rstrip("/")
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc, path, "", ""))


def _host_of(value):
    try:
        return (urllib.parse.urlsplit(str(value or "")).hostname or "").lower()
    except ValueError:
        return ""


def same_origin(left, right):
    """True when both URLs share scheme, host and port."""
    try:
        a = urllib.parse.urlsplit(str(left or ""))
        b = urllib.parse.urlsplit(str(right or ""))
        return ((a.scheme.lower(), a.hostname, a.port) ==
                (b.scheme.lower(), b.hostname, b.port))
    except (ValueError, TypeError):
        return False


def resolve_url(value, base):
    """Resolve a relative web path against ``base``; return ``""`` if unsafe.

    Absolute http(s) URLs pass through.  Protocol-relative values inherit the
    base scheme.  Any other scheme (``file:``, ``javascript:``, ``plugin:``) is
    refused before it can reach Kodi.
    """
    text = str(value or "").strip()
    if not text or any(char in text for char in ("\r", "\n", "\x00", "\x7f")):
        return ""
    if text.startswith("//"):
        scheme = "https"
        try:
            scheme = urllib.parse.urlsplit(base).scheme or "https"
        except ValueError:
            pass
        text = "%s:%s" % (scheme, text)
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme:
        if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
            return ""
        return text
    if not base:
        return ""
    if text.startswith("/"):
        return base + text
    return base + "/" + text


def is_external_play(url):
    """True for a platform/browser page that must not be a playable row."""
    host = _host_of(url)
    if not host:
        return False
    return any(host == suffix or host.endswith("." + suffix)
               for suffix in EXTERNAL_HOSTS)


def playable_url(value, base):
    """Return a resolved stream URL, or ``""`` for external/invalid rows.

    Relative paths resolve to the configured web origin (which may be private).
    Absolute URLs must be public http(s): the web API is not allowed to turn a
    row into an arbitrary LAN probe through Kodi.
    """
    url = resolve_url(value, base)
    if not url or is_external_play(url):
        return ""
    if "|" in url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return ""
    if parts.username or parts.password:
        return ""
    if base and same_origin(url, base):
        return url
    # Absolute media from a web source must still be a public address.  Import
    # lazily so this module stays importable without the rest of the add-on.
    from . import http

    return url if http.looks_like_public_http_url(url) else ""


# --------------------------------------------------------------------- rows


def _text(value, fallback=""):
    if isinstance(value, (list, tuple)):
        value = " ".join(str(part) for part in value)
    text = " ".join(str(value or "").split())
    return text or fallback


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _page_from_next(value, fallback):
    """Extract ``page`` from a next link or a bare page number."""
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(text).query)
    except ValueError:
        return fallback
    pages = query.get("page") or []
    number = _as_int(pages[0] if pages else 0, 0)
    if number > 0:
        return number
    if text.isdigit() and int(text) > 0:
        return int(text)
    return fallback


@dataclass(frozen=True)
class WebRow:
    """One web row normalised for the Kodi layer.

    ``play``/``art`` are already resolved absolute URLs.  ``download``/``fav``
    keep the original JSON objects so a route can apply its own eligibility
    policy without this module knowing Kodi's download allowlist.
    """

    label: str
    sub: str = ""
    play: str = ""
    art: str = ""
    fact: str = ""
    fav: object = None
    download: object = None
    raw: object = field(default=None, repr=False, compare=False)

    def as_kodi(self):
        """Plain mapping for route/menu builders (no Kodi types)."""
        return {
            "label": self.label,
            "sub": self.sub,
            "url": self.play,
            "path": self.play,
            "art": self.art,
            "plot": self.sub,
            "label2": self.fact,
            "fact": self.fact,
            "fav": self.fav,
            "download": self.download,
        }


@dataclass(frozen=True)
class WebPage:
    """One parsed API page and its server-side pagination metadata."""

    rows: tuple
    page: int = 1
    pages: object = None          # int, or None for cursor-paged lists
    total: object = None          # int, or None when the server does not say
    per_page: int = PAGE_SIZE
    has_next: bool = False
    next_page: object = None
    title: str = ""
    subtitle: str = ""
    raw: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "rows", tuple(self.rows or ()))

    @property
    def is_empty(self):
        return not self.rows


def _row_from_json(raw, base):
    if not isinstance(raw, dict):
        return None
    label = _text(raw.get("label") or raw.get("title"))
    if not label:
        return None
    play = raw.get("play")
    if isinstance(play, dict):
        play = play.get("url") or play.get("target")
    play = playable_url(play, base)
    if not play:
        # A folder/external row (``open``/no play, YouTube, SoundCloud...) is
        # not a playable item and is deliberately omitted.
        return None
    art = resolve_url(raw.get("art"), base)
    if art and is_external_play(art):
        art = ""
    download = raw.get("download")
    if not isinstance(download, dict):
        download = None
    fav = raw.get("fav")
    if not isinstance(fav, dict):
        fav = None
    return WebRow(
        label=label,
        sub=_text(raw.get("sub") or raw.get("plot")),
        play=play,
        art=art,
        fact=_text(raw.get("fact")),
        fav=fav,
        download=download,
        raw=raw,
    )


def parse_page(payload, requested_page=1, base="", page_size=PAGE_SIZE):
    """Convert a web JSON payload into a :class:`WebPage`.

    Accepts the normal ``{"items": [...], "pager": {...}}`` shape, a bare list,
    or a legacy ``{"rows": [...]}`` response.  Pagination is read from
    ``pager``/``total``/``next`` in that order; when the server omits it, the
    requested page is kept as a single page.
    """
    if isinstance(payload, list):
        payload = {"items": payload}
    if not isinstance(payload, dict):
        raise WebAPIError("web source returned an unexpected JSON shape")
    items = payload.get("items")
    if not isinstance(items, list):
        items = payload.get("rows")
    if not isinstance(items, list):
        items = []
    requested_page = max(1, _as_int(requested_page, 1))
    pager = payload.get("pager")
    if not isinstance(pager, dict):
        pager = {}

    page = _as_int(pager.get("page") or payload.get("page"), requested_page)
    page = max(1, page or requested_page)
    per_page = _as_int(pager.get("per_page") or payload.get("per_page"),
                       page_size)
    if per_page <= 0:
        per_page = page_size
    total = pager.get("total")
    if total is None:
        total = payload.get("total")
    total = None if total is None else max(0, _as_int(total, 0))
    pages = pager.get("pages")
    if pages is None:
        pages = payload.get("pages")
    pages = None if pages is None else max(1, _as_int(pages, 1))

    next_link = payload.get("next") or pager.get("next")
    has_next = bool(next_link)
    if pages is not None:
        has_next = page < pages
    elif total is not None and per_page:
        pages = max(1, (total + per_page - 1) // per_page)
        has_next = page < pages
    next_page = _page_from_next(next_link, page + 1) if has_next else None

    rows = []
    for raw in items:
        row = _row_from_json(raw, base)
        if row is not None:
            rows.append(row)
    return WebPage(
        rows=tuple(rows),
        page=page,
        pages=pages,
        total=total,
        per_page=per_page,
        has_next=has_next,
        next_page=next_page,
        title=_text(payload.get("title")),
        subtitle=_text(payload.get("sub")),
        raw=payload,
    )


def kodi_items(page):
    """Return the page's rows as plain mappings ready for menu builders."""
    return [row.as_kodi() for row in getattr(page, "rows", ()) or ()]


# -------------------------------------------------------------------- cache

_CACHE = {}
_CACHE_LOCK = threading.Lock()


def clear_cache():
    with _CACHE_LOCK:
        _CACHE.clear()


def _cache_get(key, ttl, clock):
    if ttl <= 0:
        return None
    now = clock()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        stored, value = entry
        if now - stored > ttl:
            _CACHE.pop(key, None)
            return None
        return value


def _cache_put(key, value, clock):
    with _CACHE_LOCK:
        if len(_CACHE) >= CACHE_LIMIT:
            oldest = min(_CACHE.items(), key=lambda item: item[1][0])[0]
            _CACHE.pop(oldest, None)
        _CACHE[key] = (clock(), value)


# ------------------------------------------------------------------- opener

_OPENER = None


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse urllib's automatic redirects so every hop can be checked."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_opener():
    global _OPENER
    if _OPENER is None:
        _OPENER = urllib.request.build_opener(_NoRedirectHandler)
    return _OPENER


class _Response(object):
    """Tiny response protocol used by the tests and by urllib."""

    def __init__(self, status=200, headers=None, body=b"", url=""):
        self.status = status
        self.headers = headers if headers is not None else {}
        self._body = body
        self._url = url
        self.closed = False

    def read(self, amount=-1):
        if amount is None or amount < 0:
            amount = len(self._body)
        return self._body[:amount]

    def geturl(self):
        return self._url

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


# ------------------------------------------------------------------- client


class Client(object):
    """A small JSON client bound to one web service base/token.

    ``opener`` is injectable for unit tests; it only needs an ``open(request,
    timeout=...)`` method returning a file-like response.  The default opener
    refuses automatic redirects and this class follows at most
    :data:`MAX_REDIRECTS` same-origin hops.
    """

    def __init__(self, base, token="", opener=None, timeout=DEFAULT_TIMEOUT,
                 max_bytes=DEFAULT_MAX_BYTES, cache_ttl=DEFAULT_CACHE_TTL,
                 clock=None):
        self.base = normalise_base(base)
        if not self.base:
            raise WebAPIError("web service URL is not configured")
        self.token = str(token or "").strip()
        self._opener = opener
        self.timeout = max(0.1, float(timeout))
        self.max_bytes = max(1, int(max_bytes))
        self.cache_ttl = max(0.0, float(cache_ttl))
        self._clock = clock or time.monotonic

    # ------------------------------------------------------------- addresses
    def api_url(self, path, page=1):
        """Build an absolute API URL and, for page > 1, add ``?page=N``."""
        text = str(path or "").strip()
        if not text:
            raise WebAPIError("empty web API path")
        if text.lower().startswith(("http://", "https://")):
            url = text
            if not same_origin(url, self.base):
                raise WebAPIError("refusing an API URL off the web service")
        else:
            url = self.base + ("" if text.startswith("/") else "/") + text
        page = _as_int(page, 1)
        if page > 1:
            separator = "&" if "?" in url else "?"
            url = "%s%spage=%d" % (url, separator, page)
        return url

    def _headers(self):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = "Bearer %s" % self.token
        return headers

    # -------------------------------------------------------------- fetching
    def _read_response(self, response):
        headers = getattr(response, "headers", None)
        try:
            declared = int((headers.get("Content-Length")
                            if headers is not None else 0) or 0)
        except (TypeError, ValueError):
            declared = 0
        if declared > self.max_bytes:
            raise WebAPIError("web response is too large")
        try:
            body = response.read(self.max_bytes + 1)
        except TypeError:
            body = response.read()
        if isinstance(body, str):
            body = body.encode("utf-8", "replace")
        if not isinstance(body, (bytes, bytearray)):
            raise WebAPIError("web response was not bytes")
        if len(body) > self.max_bytes:
            raise WebAPIError("web response is too large")
        return bytes(body)

    @staticmethod
    def _close(response):
        try:
            response.close()
        except Exception:  # noqa: BLE001 - close is best effort
            pass

    def _fetch(self, url):
        opener = self._opener or _default_opener()
        current = url
        for hop in range(MAX_REDIRECTS + 1):
            request = urllib.request.Request(current, headers=self._headers())
            try:
                response = opener.open(request, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                location = None
                try:
                    if exc.headers is not None:
                        location = exc.headers.get("Location")
                except Exception:  # noqa: BLE001 - malformed headers
                    location = None
                if exc.code in (301, 302, 303, 307, 308) and location:
                    self._close(exc)
                    if hop >= MAX_REDIRECTS:
                        raise WebAPIError("too many web redirects")
                    try:
                        target = urllib.parse.urljoin(current, location)
                    except ValueError:
                        raise WebAPIError("invalid web redirect")
                    if not same_origin(target, self.base):
                        raise WebAPIError("web redirect left the service origin")
                    current = target
                    continue
                self._close(exc)
                raise WebAPIError("web service returned HTTP %s" % exc.code)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                raise WebAPIError("web service request failed (%s)"
                                  % type(exc).__name__)
            status = getattr(response, "status", 200)
            if status and int(status) >= 400:
                self._close(response)
                raise WebAPIError("web service returned HTTP %s" % status)
            try:
                body = self._read_response(response)
            finally:
                self._close(response)
            try:
                text = body.decode("utf-8")
            except UnicodeError:
                raise WebAPIError("web response was not UTF-8 JSON")
            try:
                return json.loads(text)
            except ValueError:
                raise WebAPIError("web response was not valid JSON")
        raise WebAPIError("too many web redirects")

    def get_url(self, url, ttl=None):
        """Fetch and cache one JSON URL (cache key is the URL only)."""
        ttl = self.cache_ttl if ttl is None else max(0.0, float(ttl))
        if not ttl:
            return self._fetch(url)
        cached = _cache_get(url, ttl, self._clock)
        if cached is not None:
            return cached
        payload = self._fetch(url)
        _cache_put(url, payload, self._clock)
        return payload

    def get(self, path, page=1, ttl=None):
        """Fetch one API path (and page) as decoded JSON."""
        return self.get_url(self.api_url(path, page), ttl=ttl)

    def signed_play(self, path):
        """Ask the web service for a short-lived signed playback URL.

        Only same-origin ``/api/ezgarage|ukraves/<id>/stream`` paths are
        eligible; the bearer token stays on this JSON request, never on a media
        URL handed to Kodi.
        """
        text = str(path or "").strip()
        if not text.startswith("/api/"):
            return ""
        if not same_origin(self.base + text, self.base):
            return ""
        try:
            url = self.api_url("/api/webplay") + "?path=" + urllib.parse.quote(
                text, safe="")
            payload = self.get_url(url, ttl=0)
        except Exception:  # noqa: BLE001 - signing is best effort
            return ""
        if not isinstance(payload, dict) or not payload.get("ok"):
            return ""
        signed = payload.get("url")
        if not isinstance(signed, str) or not signed:
            return ""
        if signed.startswith("/"):
            signed = self.base + signed
        return signed if same_origin(signed, self.base) else ""

    def page(self, path, page=1, ttl=None):
        """Fetch one API path and return a normalised :class:`WebPage`."""
        page = max(1, _as_int(page, 1))
        payload = self.get(path, page, ttl=ttl)
        return parse_page(payload, requested_page=page, base=self.base)


def fetch_page(base, token, path, page=1, opener=None, timeout=DEFAULT_TIMEOUT,
               max_bytes=DEFAULT_MAX_BYTES):
    """Convenience one-shot page fetch used by routes and tests."""
    return Client(base, token, opener=opener, timeout=timeout,
                  max_bytes=max_bytes).page(path, page)
