# -*- coding: utf-8 -*-
"""Logging with token/URL redaction.

Kodi's log is world-readable over ``kodi.log`` uploads.  A resolver service
token, a Bearer header or a signed Mediafire/Drive URL must never land there.
Every message in this SDK goes through :class:`Logger`; the logger replaces
registered secrets, strips query strings, and refuses to raise if xbmc is
missing (tests and headless use).
"""

import re

_TOKEN_RE = re.compile(
    r"(?i)\b(authorization|bearer|token|api[_-]?key|signature|sig|password)"
    r"\s*[:=]\s*[^\s,;]+")
_URL_RE = re.compile(r"https?://[^\s'\"<>]+")


def _xbmc_log(message, level):
    try:
        import xbmc

        xbmc.log("raveresolver: " + message, level=level)
    except Exception:  # noqa: BLE001 - logging must never break a resolve
        pass


class Logger(object):
    """Small logger with explicit redaction.

    ``sink`` is a callable ``(message, level)`` used by tests.  ``secrets`` is
    a sequence of strings (the service token, for example) that must never be
    printed even if a third-party exception embeds them.
    """

    def __init__(self, sink=None, secrets=None):
        self._sink = sink or _xbmc_log
        self._secrets = [str(secret) for secret in (secrets or ()) if secret]

    def add_secret(self, secret):
        if secret and str(secret) not in self._secrets:
            self._secrets.append(str(secret))

    def redact(self, message):
        """Return ``message`` with secrets and URL query strings removed."""
        text = str(message if message is not None else "")
        for secret in self._secrets:
            if secret:
                text = text.replace(secret, "***")
        text = _URL_RE.sub(lambda match: _safe_match(match.group(0)), text)
        text = _TOKEN_RE.sub(lambda match: match.group(1) + "=***", text)
        return text

    def log(self, message, level=10):
        try:
            self._sink(self.redact(message), level)
        except Exception:  # noqa: BLE001
            pass

    def debug(self, message):
        self.log(message, 10)

    def info(self, message):
        self.log(message, 20)

    def warning(self, message):
        self.log(message, 30)

    def error(self, message):
        self.log(message, 40)


def _safe_match(value):
    """Keep scheme://host for diagnostics; drop path/query/fragment."""
    try:
        import urllib.parse

        parts = urllib.parse.urlsplit(value)
        host = (parts.hostname or "").lower()
        if not host:
            return "https://***"
        return "%s://%s/***" % (parts.scheme.lower(), host)
    except Exception:  # noqa: BLE001
        return "https://***"
