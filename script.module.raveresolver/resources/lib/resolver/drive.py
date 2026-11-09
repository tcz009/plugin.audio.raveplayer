# -*- coding: utf-8 -*-
"""Google Drive file-id resolver (in-process).

A Drive share link only carries a file id.  ``uc?export=download&id=...``
redirects to a signed ``drive.usercontent.google.com`` URL; for files over
~100 MB Google interposes a virus-scan page with a confirm form, so the
resolver parses that form and follows its hidden fields.  A ``Range`` probe
identifies the real media type without downloading a whole set, and successful
URLs are cached for two hours.

Only Drive hosts are ever contacted.
"""

import re
import time
import urllib.parse

from . import policy
from .base import (Adapter, BlockedURL, InvalidURL, NotFound, ProviderError,
                   RateLimited, ResolveError, Resolution)
from .cache import MISSING
from .http import retry_after_seconds

UC_URL = "https://drive.google.com/uc?export=download&id=%s"
VIEW_URL = "https://drive.google.com/file/d/%s/view"
FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,100}$")
PATH_ID_RE = re.compile(r"/file/d/([A-Za-z0-9_-]{10,100})")
QUERY_ID_RE = re.compile(r"(?:^|[?&])id=([A-Za-z0-9_-]{10,100})(?:&|$)")
FORM_RE = re.compile(
    r"<form[^>]*id=\"download-form\"[^>]*>(.*?)</form>",
    re.IGNORECASE | re.DOTALL)
ACTION_RE = re.compile(r"<form[^>]*\baction=\"([^\"]+)\"", re.IGNORECASE)
INPUT_RE = re.compile(r"<input\b[^>]*>", re.IGNORECASE)
ATTR_RE = re.compile(r"\b(name|value|type)\s*=\s*\"([^\"]*)\"", re.IGNORECASE)
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

GOOGLE_HOSTS = ("google.com", "googleusercontent.com")
TTL = 2 * 60 * 60
NEGATIVE_TTL = 5 * 60
TIMEOUT = 25
MAX_PROBE_BYTES = 4096
AUDIO_EXTENSIONS = (".mp3", ".m4a")


class DriveError(ProviderError):
    """A Drive file could not be resolved to a direct audio URL."""

    code = 502


class UnknownDriveFile(NotFound):
    code = 404


class DriveNotAudio(ProviderError):
    code = 404


class DriveAdapter(Adapter):
    name = "drive"

    def __init__(self, http, cache, logger=None, ttl=TTL,
                 negative_ttl=NEGATIVE_TTL, clock=None):
        self.http = http
        self.cache = cache
        self.logger = logger
        self.ttl = int(ttl)
        self.negative_ttl = int(negative_ttl)
        self._clock = clock or time.time

    def matches(self, url):
        parts = policy.split_url(url)
        if parts is None:
            return False
        return policy.host_matches(parts.hostname, policy.PROVIDER_HOSTS["drive"])

    def resolve(self, url):
        wanted = file_id(url)
        if not wanted:
            raise InvalidURL("unknown Google Drive file")
        key = "drive:v1:" + wanted
        now = self._clock()
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not MISSING and isinstance(cached, dict):
                value = str(cached.get("url") or "")
                expires_at = _float(cached.get("expires_at"))
                if value and (expires_at is None or expires_at > now):
                    return Resolution(value, provider=self.name,
                                      expires_at=expires_at)
        try:
            direct = self._resolve_unlocked(wanted)
        except ResolveError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep failures typed
            raise DriveError("Google Drive resolve failed (%s)"
                             % type(exc).__name__)
        expires_at = self._clock() + self.ttl
        if self.cache is not None:
            lifetime = max(1, int(min(self.ttl, expires_at - self._clock())))
            self.cache.put(key, {"url": direct, "expires_at": expires_at},
                           ttl=lifetime)
        return Resolution(direct, provider=self.name, expires_at=expires_at)

    def _probe(self, url):
        try:
            response = self.http.fetch(
                url, timeout=TIMEOUT,
                headers={
                    "User-Agent": BROWSER_UA,
                    "Accept": "*/*",
                    "Accept-Encoding": "identity",
                    "Range": "bytes=0-%d" % (MAX_PROBE_BYTES - 1),
                },
                max_bytes=MAX_PROBE_BYTES,
                allowed_hosts=GOOGLE_HOSTS,
                allow_redirects=True, max_redirects=3)
        except BlockedURL:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DriveError("Google Drive could not be reached (%s)"
                             % type(exc).__name__)
        return (int(getattr(response, "status", 0) or 0),
                dict(getattr(response, "headers", {}) or {}),
                str(getattr(response, "final_url", url) or url),
                getattr(response, "body", b"") or b"")

    def _resolve_unlocked(self, wanted):
        status, headers, final_url, body = self._probe(
            UC_URL % urllib.parse.quote(wanted, safe=""))
        if status == 429:
            raise _rate_limited(headers)
        if status in (401, 403):
            raise DriveError("Google Drive refused access to that file")
        if status in (404, 410):
            raise UnknownDriveFile("that Google Drive file is no longer available")
        if status < 200 or status >= 400:
            raise DriveError("Google Drive returned HTTP %s" % status)
        if _is_audio(headers):
            return _checked_final(final_url)
        text = body.decode("utf-8", "replace") if isinstance(body, bytes) \
            else str(body or "")
        confirm = parse_confirm_form(text)
        if not confirm:
            raise DriveNotAudio("that Google Drive file is not a playable audio file")
        status, headers, final_url, _body = self._probe(confirm)
        if status == 429:
            raise _rate_limited(headers)
        if status < 200 or status >= 400 or not _is_audio(headers):
            raise DriveNotAudio("that Google Drive file is not a playable audio file")
        return _checked_final(final_url)


def _rate_limited(headers):
    """Map Drive's 429 (and Retry-After) to the shared typed failure."""
    retry_after = retry_after_seconds(headers, default=5, maximum=120)
    return RateLimited(
        "Google Drive is rate-limiting requests; try again in %d seconds"
        % retry_after, retry_after=retry_after)


def _checked_final(value):
    try:
        return policy.check_url(value, allowed_hosts=GOOGLE_HOSTS,
                                resolve_dns=False)
    except Exception:  # noqa: BLE001 - Drive answered with an untrusted host
        raise DriveError("Google Drive returned an unexpected download host")


def _is_audio(headers):
    content_type = _header(headers, "content-type").split(";")[0].strip().lower()
    if content_type.startswith("audio/"):
        return True
    disposition = _header(headers, "content-disposition").lower()
    return any(disposition.rstrip("\"").endswith(extension)
               for extension in AUDIO_EXTENSIONS)


def _header(headers, name):
    wanted = (name or "").lower()
    for key, value in (headers or {}).items():
        if str(key).lower() == wanted:
            return str(value or "")
    return ""


def file_id(value):
    """Return the Drive file id in a URL/id, or ``""``.

    Accepts a bare id, ``/file/d/<id>/view``, ``uc?id=<id>`` and the
    ``open?id=<id>`` form used by older Blogger posts.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if FILE_ID_RE.match(text):
        return text
    parts = policy.split_url(text)
    if parts is None:
        return ""
    match = PATH_ID_RE.search(parts.path or "")
    if match:
        return match.group(1)
    match = QUERY_ID_RE.search(parts.query or "")
    if match:
        return match.group(1)
    return ""


def view_url(value):
    wanted = file_id(value)
    if not wanted:
        raise UnknownDriveFile("unknown Google Drive file")
    return VIEW_URL % urllib.parse.quote(wanted, safe="")


def _attr(tag, name):
    for match in ATTR_RE.finditer(tag or ""):
        if match.group(1).lower() == name:
            return match.group(2)
    return ""


def parse_confirm_form(body):
    """Build the confirmed download URL from Drive's virus-scan page."""
    if not isinstance(body, str) or not body:
        return ""
    form = FORM_RE.search(body)
    if not form:
        return ""
    block = form.group(0)
    action = ACTION_RE.search(block)
    if not action:
        return ""
    params = {}
    for tag in INPUT_RE.findall(block):
        name = _attr(tag, "name")
        kind = (_attr(tag, "type") or "text").lower()
        if not name or kind == "submit":
            continue
        params[name] = _attr(tag, "value")
    if not params:
        return ""
    action_url = action.group(1)
    parts = policy.split_url(action_url)
    if parts is None or parts.scheme.lower() != "https":
        return ""
    if not policy.host_matches(parts.hostname, ("google.com",)):
        return ""
    return action_url + "?" + urllib.parse.urlencode(params)


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
