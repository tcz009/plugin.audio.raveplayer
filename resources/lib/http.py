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
import contextlib
import io
import json
import os
import re
import threading
import time
import urllib.parse

from . import kodi


class _LazyCache(object):
    def __getattr__(self, name):
        from . import cache

        return getattr(cache, name)


cache = _LazyCache()

USER_AGENT = "RavePlayer/3.0 (Kodi; +https://github.com/tcz009/plugin.audio.raveplayer)"
DEFAULT_TIMEOUT = 20
MAX_BODY_BYTES = 8 * 1024 * 1024  # 8 MiB compressed body, and 8 MiB decompressed
READ_CHUNK_BYTES = 64 * 1024
ROUTE_BUDGET_SECONDS = 20.0
MAX_REDIRECTS = 3

# One page at a time per polite host, with a minimum gap.  Only a cache miss
# reaches ``_request``, and the slot is held for the whole request so two
# threads can never open two pages to the same source.  RaveTapePacks blocked
# this client's IP after a burst; the add-on stays deliberately single-flight
# there.
POLITE_HOSTS = {
    "www.ravetapepacks.com": 1.0,
    "ravetapepacks.com": 1.0,
}
_HOST_LOCKS = {}

# ---------------------------------------------------------------- RTP egress
# RaveTapePacks' edge firewall drops the home WAN address at TCP level, so its
# pages are unreachable directly.  The add-on sends *only* RaveTapePacks
# requests through the homelab VPN host's HTTP CONNECT proxy; every other
# provider keeps the direct path.  Configure the proxy in the add-on settings
# (General -> "RaveTapePacks egress proxy") or with RTP_EGRESS_PROXY.  A dead
# proxy falls back to direct once, so a stale setting never bricks the source.
EGRESS_PROXY_ENV = "RTP_EGRESS_PROXY"
EGRESS_HOSTS_ENV = "RTP_EGRESS_HOSTS"
EGRESS_FALLBACK_ENV = "RTP_EGRESS_FALLBACK"
EGRESS_PROXY_SETTING = "rtp_egress_proxy"
DEFAULT_EGRESS_HOSTS = ("ravetapepacks.com",)


def _egress_hosts():
    raw = os.environ.get(EGRESS_HOSTS_ENV, "")
    hosts = tuple(
        host.strip().lower().lstrip(".") for host in raw.split(",") if host.strip()
    )
    return hosts or DEFAULT_EGRESS_HOSTS


def _host_of(value):
    """Return the lowercase host of ``value`` (URL, hostname, or "")."""
    try:
        text = str(value or "").strip()
        if not text:
            return ""
        if "://" in text:
            host = urllib.parse.urlsplit(text).hostname or ""
        else:
            host = text
        return host.lower().rstrip(".")
    except (ValueError, AttributeError):
        return ""


def is_egress_host(value):
    """True when ``value`` (URL or hostname) should use the RTP egress route."""
    host = _host_of(value)
    if not host:
        return False
    return any(host == suffix or host.endswith("." + suffix)
               for suffix in _egress_hosts())


# JungleTapes serves its show pages to this client's Python stack but Kodi's
# libcurl fetch of the same MP3 times out on the Shield (CFileCache::Open
# failed, 0 % cache).  The stream is therefore routed through the same
# loopback bridge as RTP; the bridge fetches with Python, which works on the
# device.  This is a playback transport fix, not an egress-proxy rule: the
# bridge never becomes an open proxy.
BRIDGE_HOSTS = ("jungletapes.com",)


def is_bridge_host(value):
    """True when a media URL should be played through the loopback bridge."""
    host = _host_of(value)
    if not host:
        return False
    if is_egress_host(host):
        return True
    return any(host == suffix or host.endswith("." + suffix)
               for suffix in BRIDGE_HOSTS)


def egress_proxy():
    """Return the configured proxy URL, or ``""``.

    The add-on setting wins over the environment only when the environment is
    empty (env is the operator override for packaged/diagnostic runs).  An
    invalid value is treated as "not configured" so a typo cannot break RTP.
    """
    raw = (os.environ.get(EGRESS_PROXY_ENV, "") or "").strip()
    if not raw:
        try:
            raw = str(kodi.setting(EGRESS_PROXY_SETTING, "") or "").strip()
        except Exception:  # noqa: BLE001 - settings must never break a fetch
            raw = ""
    if not raw:
        return ""
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parts = urllib.parse.urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        return ""
    try:
        port = parts.port
    except ValueError:
        return ""
    if port is not None and not 1 <= port <= 65535:
        return ""
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def egress_proxy_for(url):
    """Proxy URL for ``url`` when it is an RTP host, else ``""``."""
    if not is_egress_host(url):
        return ""
    return egress_proxy()


def _egress_fallback_enabled():
    value = (os.environ.get(EGRESS_FALLBACK_ENV, "1") or "1").strip().lower()
    return value not in ("0", "false", "no", "off")
_HOST_LAST_END = {}
_HOST_META_LOCK = threading.Lock()


@contextlib.contextmanager
def _host_slot(url):
    """Serialise requests to a polite host and keep ``gap`` seconds between."""
    try:
        host = (urllib.parse.urlsplit(str(url)).hostname or "").lower()
    except ValueError:
        host = ""
    gap = POLITE_HOSTS.get(host)
    if not gap:
        yield
        return
    with _HOST_META_LOCK:
        lock = _HOST_LOCKS.setdefault(host, threading.Lock())
    with lock:
        wait = gap - (time.monotonic() - _HOST_LAST_END.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        try:
            yield
        finally:
            _HOST_LAST_END[host] = time.monotonic()

_REDIRECT_CODES = frozenset((301, 302, 303, 307, 308))


_NoRedirectHandler = None


def _build_opener(*extra_handlers):
    """Build a no-auto-redirect opener, optionally with extra handlers."""
    global _NoRedirectHandler
    import urllib.request

    if _NoRedirectHandler is None:
        class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            """Refuse automatic redirects; ``_request`` follows them
            manually so every hop can be validated and budgeted."""

            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

    return urllib.request.build_opener(_NoRedirectHandler, *extra_handlers)


class _LazyOpener(object):
    """Build the urllib opener on first use (keeps root import light)."""

    def __init__(self):
        self._real = None

    def _load(self):
        if self._real is None:
            self._real = _build_opener()
        return self._real

    def __getattr__(self, name):
        if name == "_real":
            raise AttributeError(name)
        return getattr(self._load(), name)


class _LazyProxyOpener(object):
    """One cached opener per proxy URL; only RTP hosts reach it."""

    def __init__(self):
        self._real = None
        self._proxy = None

    def for_proxy(self, proxy):
        if self._real is None or proxy != self._proxy:
            import urllib.request

            self._real = _build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
            self._proxy = proxy
        return self._real


_OPENER = _LazyOpener()
_PROXY_OPENER = _LazyProxyOpener()


class _LazyStdlib(object):
    """Lazy module attribute (tests patch http.socket.getaddrinfo)."""

    def __init__(self, name):
        self._name = name
        self._module = None

    def __getattr__(self, name):
        if name == "_module":
            raise AttributeError(name)
        if self._module is None:
            import importlib

            self._module = importlib.import_module(self._name)
        return getattr(self._module, name)


socket = _LazyStdlib("socket")


_XML_ENCODING_RE = re.compile(br"""<\?xml[^>]*encoding=["']([A-Za-z0-9._-]+)""", re.IGNORECASE)

_deadline = None
_budget_exhausted = False
_state_lock = threading.Lock()
_host_cache = {}
_HOST_CACHE_MAX = 256


# -------------------------------------------------------------- url safety


def blocked_address(address):
    """True for loopback/link-local/private/metadata-style IP addresses."""
    import ipaddress

    text = str(address or "").split("%", 1)[0].strip()
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return True  # not an address we can verify: refuse it
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def host_is_blocked(hostname, port):
    """Resolve a host and return True when any answer is non-public.

    Literal IPs are checked without a DNS lookup.  Every A/AAAA answer must be
    public (a mixed answer covers DNS-rebinding style hosts), and an
    unresolvable host is refused because Kodi could not play it anyway.
    """
    import ipaddress

    text = str(hostname or "").strip().strip("[]")
    if not text:
        return True
    try:
        literal = ipaddress.ip_address(text)
    except ValueError:
        literal = None
    if literal is not None:
        return blocked_address(literal)
    key = (text.lower(), port or 0)
    # Memoise per route only: one play_all can otherwise resolve the same
    # archive.org host for every track (A3/A10 performance), while direct
    # helper calls and tests stay uncached.
    budgeted = remaining() is not None
    if budgeted:
        with _state_lock:
            cached = _host_cache.get(key)
        if cached is not None:
            return cached
    try:
        infos = socket.getaddrinfo(text, port or 0, 0, socket.SOCK_STREAM)
    except (socket.gaierror, OSError, UnicodeError, ValueError):
        blocked = True
    else:
        blocked = not infos or any(blocked_address(info[4][0]) for info in infos)
    if budgeted:
        with _state_lock:
            if len(_host_cache) < _HOST_CACHE_MAX:
                _host_cache[key] = blocked
    return blocked


def is_public_http_url(value):
    """True for an http(s) URL whose host resolves only to public addresses."""
    text = str(value or "").strip()
    if not text:
        return False
    try:
        split = urllib.parse.urlsplit(text)
    except ValueError:
        return False
    if split.scheme.lower() not in ("http", "https") or not split.netloc:
        return False
    try:
        port = split.port
        hostname = split.hostname
    except ValueError:
        return False
    return not host_is_blocked(hostname, port)


def safe_stream_url(value):
    """Return a playable public http(s) stream URL (``|Header=`` preserved)."""
    text = str(value or "").strip()
    if not text:
        return ""
    base = text.split("|", 1)[0].strip()
    if not is_public_http_url(base):
        return ""
    return text


def _service_media_url(value):
    """Syntax-only check for the operator-configured resolver stream URL.

    The signed Mega endpoint normally lives on the LAN/Tailscale resolver
    service, so it cannot pass :func:`safe_stream_url`.  Only
    ``routes.download_start()`` passes ``allow_private=True``, and only after
    confirming the URL is the exact configured origin + ``/api/mega/stream``.
    This helper never decides trust; it rejects malformed URLs, credentials
    and header injection.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    base = text.split("|", 1)[0].strip()
    if any(char in base for char in ("\r", "\n", "\x00", "\x7f")):
        return ""
    try:
        split = urllib.parse.urlsplit(base)
    except ValueError:
        return ""
    if split.scheme.lower() not in ("http", "https") or not split.netloc:
        return ""
    if split.username or split.password or not split.hostname:
        return ""
    return text


def _same_origin(left, right):
    """True when both URLs share scheme and netloc (redirect containment)."""
    try:
        a = urllib.parse.urlsplit(str(left or ""))
        b = urllib.parse.urlsplit(str(right or ""))
    except ValueError:
        return False
    return (a.scheme.lower(), a.netloc.lower()) == (b.scheme.lower(), b.netloc.lower())


_PRIVATE_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".home.arpa")


def looks_like_public_http_url(value):
    """Cheap public-URL guard: syntax and literal addresses, **no DNS**.

    Directory routes call this for non-playable art URLs and for optional
    stream rows.  ``host_is_blocked`` costs one ``getaddrinfo`` per unique
    host; on a 100-station radio door that was 90+ serial lookups and 28–53 s
    (audit P0-2).  Art is fetched by Kodi, not by this process, and a stream is
    validated again — with resolution — by :func:`safe_stream_url` when the
    user actually plays it.  Literal loopback/private IPs and local-only
    hostnames are still refused here, so a hostile favicon/stream field cannot
    point at the LAN.
    """
    text = str(value or "").strip()
    if not text:
        return False
    try:
        split = urllib.parse.urlsplit(text)
    except ValueError:
        return False
    if split.scheme.lower() not in ("http", "https") or not split.netloc:
        return False
    if split.username or split.password:
        return False
    try:
        hostname = split.hostname
    except ValueError:
        return False
    host = str(hostname or "").strip().strip("[]").rstrip(".").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(_PRIVATE_HOST_SUFFIXES):
        return False
    import ipaddress

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        return not blocked_address(address)
    return True


def safe_art_url(value):
    """Return an http(s) art URL that cannot point at the LAN, without DNS.

    Third-party favicons/thumbnails are images, not media and not server-side
    fetches, so resolving their hosts would only add latency (P0-2).
    """
    text = str(value or "").strip()
    if not text or "|" in text:
        return ""
    return text if looks_like_public_http_url(text) else ""


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
    with _state_lock:
        _deadline = time.monotonic() + max(0.0, budget)
        _budget_exhausted = False
        _host_cache.clear()


def end_route():
    """Clear the per-invocation network budget."""
    global _deadline, _budget_exhausted
    with _state_lock:
        _deadline = None
        _budget_exhausted = False
        _host_cache.clear()


def remaining():
    """Seconds left in the current route budget, or None when unbudgeted."""
    with _state_lock:
        deadline = _deadline
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


def route_budget_exhausted():
    """True when a fetch was skipped because the route budget ran out."""
    with _state_lock:
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
        global _budget_exhausted
        with _state_lock:
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


def _set_read_timeout(response, seconds):
    """Best-effort: clamp the next socket recv to the remaining deadline."""
    sock = getattr(response, "_sock", None)
    if sock is None:
        fp = getattr(response, "fp", None)
        raw = getattr(fp, "raw", None) if fp is not None else None
        sock = getattr(raw, "_sock", None)
    if sock is not None:
        try:
            sock.settimeout(max(0.001, float(seconds)))
        except (OSError, ValueError, AttributeError):
            pass


def _recv(response, size):
    """Read whatever one recv/wake-up returns (A1 slow-drip guard).

    ``HTTPResponse.read(n)`` blocks until *n* bytes/EOF/timeout, which lets a
    one-byte-per-second upstream hold the plugin thread for the whole body.
    ``read1`` returns after a single socket recv, so the caller's wall-clock
    deadline is checked between every network wake-up.
    """
    reader = getattr(response, "read1", None)
    if reader is None:
        reader = response.read
    return reader(size)


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
        left = deadline - time.monotonic()
        if left <= 0:
            kodi.log("response read exceeded its deadline; abandoning", level=30)
            return None
        _set_read_timeout(response, left)
        chunk = _recv(response, READ_CHUNK_BYTES)
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
    import gzip
    import zlib

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
    # JSON encoding is injective: the old "k=v&k=v" form let header pairs like
    # ("Referer": "a&b=c") collide with ("Referer": "a", "b": "c").
    normalized = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    header_part = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return "http:%s:%s:%s" % (kind, url, header_part)


def _build_request(url, headers, method=None):
    import urllib.request

    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT}, method=method)
    for key, value in (headers or {}).items():
        request.add_header(str(key), str(value))
    return request


def _egress_open(url, headers, timeout, method=None):
    """Open ``url`` on its per-host route, with a one-shot direct fallback.

    Only RTP hosts take the proxy; a connection-level failure there retries
    direct so a stopped proxy degrades instead of failing forever.  HTTP
    statuses (403/407/redirects) are returned/raised untouched.
    """
    import http.client
    import urllib.error
    import urllib.request
    import zlib

    proxy = egress_proxy_for(url)
    if proxy:
        try:
            return _PROXY_OPENER.for_proxy(proxy).open(
                _build_request(url, headers, method), timeout=timeout)
        except urllib.error.HTTPError:
            raise
        except (
            urllib.error.URLError,
            http.client.HTTPException,
            OSError,
            ValueError,
            TypeError,
            EOFError,
            zlib.error,
            UnicodeError,
        ) as exc:
            kodi.log("RTP egress proxy unavailable for %s (%s); retrying direct"
                     % (url, type(exc).__name__), level=0)
            if not _egress_fallback_enabled():
                raise
    return _OPENER.open(_build_request(url, headers, method), timeout=timeout)


def _request(url, timeout, headers):
    """Perform one request and return the decoded body, or None on failure.

    Redirects are followed manually (max 3 hops): every hop is validated as a
    public http(s) URL, gets its own budget-clamped timeout, and never runs
    urllib's unvalidated automatic redirect chain (A2).  RTP hosts use the
    egress proxy on each hop; a redirect away from them goes direct.
    """
    import http.client
    import socket
    import urllib.error
    import urllib.request
    import zlib

    current = str(url or "")
    if not current.lower().startswith(("http://", "https://")):
        kodi.log("refusing non-http(s) request: %r" % current, level=30)
        return None
    hops = 0
    while True:
        hop_timeout = _effective_timeout(timeout)
        if hop_timeout <= 0:
            kodi.log("network budget exhausted; abandoning request to %s" % current, level=30)
            return None
        try:
            with _host_slot(current):
                with _egress_open(current, headers, hop_timeout) as response:
                    return _decode(response, hop_timeout)
        except urllib.error.HTTPError as exc:
            location = None
            try:
                if exc.headers:
                    location = exc.headers.get("Location")
            except Exception:
                location = None
            if exc.code in _REDIRECT_CODES and location:
                if hops >= MAX_REDIRECTS:
                    kodi.log("too many redirects for %s; abandoning" % url, level=30)
                    _close_quietly(exc)
                    return None
                try:
                    target = urllib.parse.urljoin(current, location)
                except ValueError:
                    target = ""
                if not is_public_http_url(target):
                    kodi.log("refusing redirect from %s to %r (non-public/invalid)"
                             % (current, target), level=30)
                    _close_quietly(exc)
                    return None
                hops += 1
                _close_quietly(exc)
                current = target
                continue
            kodi.log("fetch failed: %s (%s)" % (current, exc), level=30)
            _close_quietly(exc)
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
            kodi.log("fetch failed: %s (%s)" % (current, exc), level=30)
            return None


def _close_quietly(response):
    try:
        response.close()
    except Exception:
        pass


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
    # ``sync=False``: a fetched body is recomputable.  fsync on the Shield's
    # flash added tens of milliseconds to every cold page for no benefit — a
    # lost write after a power cut just means one more fetch.
    return cache.remember(key, ttl,
                          lambda: _fetch_for_cache(url, effective, headers),
                          sync=False)


def is_cached(url, ttl, headers=None):
    """True when ``fetch(url, ..., ttl=ttl)`` would be served from cache.

    Providers with a <=1 request/second courtesy gap use this so a warm page
    does not still sleep for it.
    """
    if not ttl:
        return False
    try:
        return cache.has(_cache_key("text", url, headers), ttl)
    except Exception:  # noqa: BLE001 - a cache hiccup must not break the fetch
        return False


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
        key, ttl,
        lambda: _parse_json(url, fetch(url, timeout=timeout, headers=headers)),
        sync=False,
    )


@contextlib.contextmanager
def open_media(url, timeout=DEFAULT_TIMEOUT, headers=None, method=None,
               allow_private=False):
    """Open a validated public media URL for streaming (downloads/bridge).

    Only direct media URLs are accepted (the caller checks the audio
    extension).  Redirects are blocked by the safe opener; a redirecting media
    URL fails the download rather than escaping validation.  ``|Header=``
    suffixes are parsed into request headers for compatibility.

    ``allow_private=True`` is reserved for the signed Mega stream endpoint on
    the operator-configured resolver service.  It still requires http(s) and
    no userinfo, and every redirect must stay on the same origin.
    """
    text = _service_media_url(url) if allow_private else safe_stream_url(url)
    if not text:
        raise ValueError("not a public media URL")
    base, separator, suffix = text.partition("|")
    request_headers = {"User-Agent": USER_AGENT}
    if separator:
        for pair in suffix.split("&"):
            key, _sep, value = pair.partition("=")
            if key:
                request_headers[key] = urllib.parse.unquote(value)
    for key, value in (headers or {}).items():
        if key:
            request_headers[str(key)] = str(value)
    import urllib.error as urllib_error
    import urllib.request as urllib_request

    current = base
    response = None
    for hop in range(MAX_REDIRECTS + 1):
        effective = _effective_timeout(timeout)
        if effective <= 0:
            raise ValueError("network budget exhausted")
        try:
            response = _egress_open(current, request_headers, effective, method=method)
            break
        except urllib_error.HTTPError as exc:
            location = exc.headers.get("Location") if exc.headers else None
            if exc.code not in _REDIRECT_CODES or not location \
                    or hop >= MAX_REDIRECTS:
                raise
            target = urllib.parse.urljoin(current, location)
            if allow_private:
                if not _same_origin(target, base):
                    raise ValueError("redirect left the resolver service origin")
            elif not is_public_http_url(target):
                raise ValueError("redirect is not a public http(s) URL")
            current = target
    if response is None:  # pragma: no cover - loop always returns or raises
        raise ValueError("could not open media URL")
    try:
        yield response
    finally:
        _close_quietly(response)


def probe_media(url, timeout=DEFAULT_TIMEOUT, allow_private=False):
    """HEAD a direct media URL and return size/type/final URL, or ``{}``.

    Redirects are blocked by the safe opener (the direct sources are final
    URLs); the final URL is re-checked against the public-host guard.
    ``allow_private`` follows :func:`open_media`: it is only for the signed
    Mega endpoint on the operator-configured resolver service, and redirects
    must stay on that origin.
    """
    text = _service_media_url(url) if allow_private else safe_stream_url(url)
    if not text:
        return {}
    import http.client
    import socket
    import urllib.error as urllib_error
    import urllib.request as urllib_request

    base, separator, suffix = text.partition("|")
    headers = {"User-Agent": USER_AGENT}
    if separator:
        # A RaveTapePacks-style suffix carries the Referer/UA the hotlink
        # guard needs; a bare HEAD was a guaranteed 403 for those sources.
        for pair in suffix.split("&"):
            key, _sep, value = pair.partition("=")
            key = key.strip()
            if key:
                headers[key] = urllib.parse.unquote(value)
    current = base
    for hop in range(MAX_REDIRECTS + 1):
        effective = _effective_timeout(timeout)
        if effective <= 0:
            return {}
        try:
            with _egress_open(current, headers, effective, method="HEAD") as response:
                final = response.geturl()
                if allow_private:
                    if not _same_origin(final, base):
                        return {}
                elif not is_public_http_url(final):
                    return {}
                response_headers = response.headers
                try:
                    size = int((response_headers.get("Content-Length")
                                if response_headers else 0) or 0)
                except (TypeError, ValueError):
                    size = 0
                content_type = str((response_headers.get("Content-Type")
                                    if response_headers else "") or "")
                return {
                    "size": max(0, size),
                    "content_type": content_type.split(";", 1)[0].strip().lower(),
                    "final_url": final,
                }
        except urllib_error.HTTPError as exc:
            location = exc.headers.get("Location") if exc.headers else None
            if exc.code not in _REDIRECT_CODES or not location \
                    or hop >= MAX_REDIRECTS:
                return {}
            target = urllib.parse.urljoin(current, location)
            if allow_private:
                if not _same_origin(target, base):
                    return {}
            elif not is_public_http_url(target):
                return {}
            current = target
        except (ValueError, TypeError, urllib_error.URLError,
                http.client.HTTPException, socket.timeout, OSError):
            return {}
    return {}


def quote(value):
    return urllib.parse.quote(value, safe="")
