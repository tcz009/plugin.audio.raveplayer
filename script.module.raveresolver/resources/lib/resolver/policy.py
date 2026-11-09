# -*- coding: utf-8 -*-
"""URL policy: provider selection, host allowlists and SSRF rejection.

Everything that turns a user-supplied URL into a network request passes
through this module first.  Two rules matter:

* only ``http``/``https`` URLs with a host, no userinfo and no control
  characters are accepted;
* loopback, link-local, private, multicast, reserved and local-only names are
  refused.  A literal address is checked without DNS; normal hostnames are
  resolved and every A/AAAA answer must be public.

The DNS check is opt-in (``resolve_dns=True``) so directory-building code and
unit tests can use the cheap syntax-only form.  :class:`resolver.http.
HttpClient` always resolves before it connects, and the direct adapter resolves
once because it does not fetch anything itself.
"""

import ipaddress
import re
import socket
import urllib.parse

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus",
                    ".flac", ".wav")

# Provider -> host suffixes.  A provider page is selected by host before the
# generic direct adapter gets a chance; ``direct`` then only handles files on
# these trusted hosts (or a caller-supplied extra allowlist).
PROVIDER_HOSTS = {
    "mediafire": ("mediafire.com",),
    # A Drive *file page* is drive.google.com/docs.google.com.  A
    # drive.usercontent.google.com URL is the signed direct download, not a
    # page, so the direct adapter owns it (audio extension + allowlist).
    "drive": ("drive.google.com", "docs.google.com"),
    "podomatic": ("podomatic.com", "pdcn.co"),
    "mega": ("mega.nz", "mega.co.nz", "mega.io"),
}

# Media requests are web requests: only the standard http/https ports.  The
# operator-configured resolver service base is the one exception and passes
# ``allowed_ports=None`` explicitly (a LAN service often listens on :8080).
MEDIA_PORTS = (80, 443)

# Direct audio hosts the Rave Player sources actually use.  This is not meant
# to be the whole internet: unknown public hosts return HostNotAllowed and the
# manager can still ask the NAS service.  Callers may pass ``extra_hosts`` for
# a source they own (the plugin does this from its download allowlist).
DIRECT_HOSTS = (
    "archive.org",
    "mediafire.com",
    "google.com",
    "googleusercontent.com",
    "podomatic.com",
    "mega.nz",
    "mega.co.nz",
    "moxser.com",
    "hardscore.com",
    "torontoravemixtapearchive.com",
    "jungletapes.com",
    "ravetapepacks.com",
    "ravearchive.com",
    "ukraves.co.uk",
    "dnbradio.com",
    "rinse.fm",
    "rinseout.fm",
)

_BLOCKED_HOST_SUFFIXES = (
    ".local", ".localhost", ".localdomain", ".internal", ".home.arpa",
    ".lan", ".test", ".invalid", ".example", ".onion",
)

# Link-local/metadata endpoints that must never receive the resolver service
# token, even though the service base is an explicit operator setting.  LAN
# and Tailscale private addresses stay allowed.
_METADATA_HOSTS = frozenset((
    "metadata", "metadata.google.internal", "metadata.goog", "instance-data",
    "metadata.azure.com",
))
_METADATA_IPV6 = "fd00:ec2::254"

_HOST_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_CONTROL_RE = re.compile(r"[\x00-\x20\x7f]")
_MAX_URL = 8192
_MAX_HEADERS = 24
_MAX_HEADER_BYTES = 8192

# Web resolver parity (W/base.py:49-64): response headers we replay to Kodi
# must be a media request's own headers, never credentials or framing.
_FORBIDDEN_HEADERS = frozenset((
    "authorization", "proxy-authorization", "cookie", "set-cookie", "host",
    "content-length", "content-type", "transfer-encoding", "connection",
    "keep-alive", "proxy-connection", "upgrade", "te", "trailer",
))
_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
_HEADER_VALUE_RE = re.compile(r"^[\x20-\x7e\x80-\xff\t]*$")


def default_dns_resolver(host, port):
    """Return the A/AAAA addresses for ``host`` using the stdlib resolver."""
    infos = socket.getaddrinfo(host, port or 0, 0, socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def blocked_address(address):
    """True for loopback/link-local/private/metadata-style IP addresses."""
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


def local_hostname(host):
    """True for local-only / reserved hostnames (no DNS involved)."""
    text = str(host or "").strip().strip("[]").rstrip(".").lower()
    if not text:
        return True
    if text == "localhost":
        return True
    if "." not in text and ":" not in text:
        # A dotless name is a LAN name (``nas``), never a public media host.
        # IPv6 literals keep their colons and are checked as addresses.
        return True
    return any(text.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES)


def service_host_blocked(host):
    """True for link-local / cloud-metadata service-base targets.

    The resolver service URL is an explicit operator setting, so private and
    Tailscale addresses are allowed.  Link-local (169.254/16, fe80::/10) and
    known metadata endpoints are not: posting the Bearer token there would be
    token exfiltration, not a resolver.
    """
    text = str(host or "").strip().strip("[]").rstrip(".").lower()
    if not text:
        return True
    if text in _METADATA_HOSTS or any(
            text.endswith("." + name) for name in _METADATA_HOSTS):
        return True
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(
        ip.is_link_local
        or ip.is_unspecified
        or ip.is_multicast
        or (ip.version == 4 and ip.is_reserved)
        or str(ip) == _METADATA_IPV6
    )


def host_is_blocked(host, port, resolver=None):
    """Resolve ``host`` and return True when any answer is non-public.

    Literal IPs are checked without DNS.  Every A/AAAA answer must be public:
    a mixed answer covers DNS-rebinding style hosts.  An unresolvable host is
    refused because Kodi could not play it anyway.
    """
    text = str(host or "").strip().strip("[]").rstrip(".")
    if not text:
        return True
    if local_hostname(text):
        return True
    try:
        literal = ipaddress.ip_address(text)
    except ValueError:
        literal = None
    if literal is not None:
        return blocked_address(literal)
    resolver = resolver or default_dns_resolver
    try:
        addresses = list(resolver(text, port or 0))
    except (socket.gaierror, OSError, UnicodeError, ValueError):
        return True
    if not addresses:
        return True
    return any(blocked_address(address) for address in addresses)


def split_url(value, allowed_ports=MEDIA_PORTS):
    """Return ``SplitResult`` for a conservative http(s) URL, or ``None``.

    ``allowed_ports`` defaults to :data:`MEDIA_PORTS` (80/443).  Only the
    operator-configured service base passes ``None`` to keep an ephemeral LAN
    port working.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > _MAX_URL or _CONTROL_RE.search(text):
        return None
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    if not parts.netloc or not parts.hostname:
        return None
    if parts.username or parts.password:
        return None
    host = parts.hostname.strip().rstrip(".")
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not _HOST_RE.match(host):
            return None
    try:
        port = parts.port
    except ValueError:
        return None
    if port is not None:
        if not 1 <= port <= 65535:
            return None
        if allowed_ports is not None and port not in tuple(allowed_ports):
            return None
    return parts


def host_matches(host, suffixes):
    """True when ``host`` equals or is a subdomain of one of ``suffixes``."""
    text = str(host or "").strip().rstrip(".").lower()
    if not text:
        return False
    for suffix in suffixes or ():
        suffix = str(suffix or "").strip().lstrip(".").rstrip(".").lower()
        if suffix and (text == suffix or text.endswith("." + suffix)):
            return True
    return False


def provider_for(value, extra_hosts=None):
    """Return the provider name for ``value``, or ``""`` when unknown.

    Provider pages win over the generic ``direct`` adapter even when their path
    happens to end in ``.mp3`` (a Mediafire page URL does).
    """
    parts = split_url(value)
    if parts is None:
        return ""
    host = (parts.hostname or "").lower().rstrip(".")
    for provider in ("mediafire", "drive", "podomatic", "mega"):
        if host_matches(host, PROVIDER_HOSTS[provider]):
            return provider
    if is_audio_url(value) and (host_matches(host, DIRECT_HOSTS)
                                or host_matches(host, extra_hosts)):
        return "direct"
    return ""


def is_audio_url(value):
    """True when the URL path ends in a known audio extension."""
    parts = split_url(value)
    if parts is None:
        return False
    path = (parts.path or "").lower()
    return any(path.endswith(extension) for extension in AUDIO_EXTENSIONS)


def _normalise(parts):
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    try:
        port = parts.port
    except ValueError:
        return ""
    netloc = "[%s]" % host if ":" in host else host
    if port is not None:
        netloc = "%s:%d" % (netloc, port)
    # Fragments are client-side only.  Mega keys live in the fragment, so the
    # Mega adapter parses the original value before this helper is used.
    return urllib.parse.urlunsplit((scheme, netloc, parts.path or "/",
                                    parts.query, ""))


def check_url(value, allowed_hosts=None, require_audio=False,
              allow_private=False, resolve_dns=False, resolver=None,
              extra_hosts=None, allowed_ports=MEDIA_PORTS):
    """Validate a URL and return its normalised form.

    Raises :class:`BlockedURL` for private/local targets, :class:`InvalidURL`
    for syntax errors and :class:`HostNotAllowed` when ``allowed_hosts`` is
    supplied and the host is outside it.  Non-80/443 media ports are treated
    as invalid syntax; only the service base opts out.
    """
    from .base import BlockedURL, HostNotAllowed, InvalidURL

    parts = split_url(value, allowed_ports=allowed_ports)
    if parts is None:
        raise InvalidURL("not a public http(s) URL")
    host = (parts.hostname or "").lower().rstrip(".")
    if not allow_private and local_hostname(host):
        raise BlockedURL("that host is local-only")
    if not allow_private:
        try:
            literal = ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            literal = None
        if literal is not None and blocked_address(literal):
            raise BlockedURL("that URL points at a private or loopback address")
        if resolve_dns and host_is_blocked(host, parts.port, resolver):
            raise BlockedURL("that host resolves to a private or loopback address")
    if allowed_hosts and not host_matches(
            host, tuple(allowed_hosts) + tuple(extra_hosts or ())):
        raise HostNotAllowed("host %s is not on the resolver allowlist" % host)
    if require_audio and not is_audio_url(value):
        raise InvalidURL("that URL is not a direct audio file")
    return _normalise(parts)


def sanitize_headers(value):
    """Return only safe media-request headers from an untrusted mapping.

    Mirrors the web resolver: at most 24 headers / 8 KiB, valid header-name
    and printable-value syntax, and no credentials, framing or Content-Type.
    A dropped header is safer than replaying it to Kodi.
    """
    headers = {}
    total = 0
    if not isinstance(value, dict):
        return headers
    for key, item in value.items():
        if len(headers) >= _MAX_HEADERS:
            break
        name = str(key or "").strip()
        if not name or len(name) > 256 or not _HEADER_NAME_RE.match(name):
            continue
        if name.lower() in _FORBIDDEN_HEADERS:
            continue
        if not isinstance(item, (str, int, float)):
            continue
        text = str(item).strip()
        if not text or not _HEADER_VALUE_RE.match(text):
            continue
        if total + len(name) + len(text) > _MAX_HEADER_BYTES:
            break
        headers[name] = text
        total += len(name) + len(text)
    return headers


def describe_url(value):
    """A log-safe description: scheme and host only, never path/query/token."""
    parts = split_url(value)
    if parts is None:
        return "invalid-url"
    return "%s://%s" % (parts.scheme.lower(), (parts.hostname or "").lower())
