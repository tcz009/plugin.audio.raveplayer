# -*- coding: utf-8 -*-
"""Tiny HTTP layer: standards library only, JSON in, friendly failures out."""

import gzip
import io
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

from . import kodi

USER_AGENT = "RavePlayer/3.0 (Kodi; +https://github.com/tcz009/plugin.audio.raveplayer)"
DEFAULT_TIMEOUT = 20


def _decode(response):
    raw = response.read()
    if response.headers.get("Content-Encoding") == "gzip":
        raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
    charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, "replace")


def fetch(url, timeout=DEFAULT_TIMEOUT, headers=None):
    """Return the response body as text, or None on any failure."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _decode(response)
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, ValueError) as exc:
        kodi.log("fetch failed: %s (%s)" % (url, exc), level=30)
        return None


def fetch_json(url, timeout=DEFAULT_TIMEOUT, headers=None):
    body = fetch(url, timeout=timeout, headers=headers)
    if body is None:
        return None
    try:
        return json.loads(body)
    except ValueError as exc:
        kodi.log("bad JSON from %s (%s)" % (url, exc), level=30)
        return None


def quote(value):
    return urllib.parse.quote(value, safe="")
