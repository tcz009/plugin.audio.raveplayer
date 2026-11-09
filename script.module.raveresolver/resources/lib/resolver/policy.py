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
    "drive": ("drive.google.com", "docs.google.com",
              "drive.usercontent.google.com"),
    "podomatic": ("podomatic.com",),
    "mega": ("mega.nz", "mega.co.nz"),
}

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
    ".local", ".localhost", ".internal", ".home.arpa", ".lan", ".test",
    ".invalid", ".example", ".onion",
)

_HOST_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_CONTROL_RE = re.compile(r"[\x00-\x20\x7f]")
_MAX_URL = 8192


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
    return any(text.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES)


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


def split_url(value):
    """Return ``SplitResult`` for a conservative http(s) URL, or ``None``."""
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
    if port is not None and not 1 <= port <= 65535:
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
              extra_hosts=None):
    """Validate a URL and return its normalised form.

    Raises :class:`BlockedURL` for private/local targets, :class:`InvalidURL`
    for syntax errors and :class:`HostNotAllowed` when ``allowed_hosts`` is
    supplied and the host is outside it.
    """
    from .base import BlockedURL, HostNotAllowed, InvalidURL

    parts = split_url(value)
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


def describe_url(value):
    """A log-safe description: scheme and host only, never path/query/token."""
    parts = split_url(value)
    if parts is None:
        return "invalid-url"
    return "%s://%s" % (parts.scheme.lower(), (parts.hostname or "").lower())
