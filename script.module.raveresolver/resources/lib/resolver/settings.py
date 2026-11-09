# -*- coding: utf-8 -*-
"""Typed access to the module add-on's settings.

``xbmcaddon.Addon()`` with no id returns the *calling* add-on (the plugin),
not this module, so the SDK always asks for ``script.module.raveresolver``
explicitly.  A fake add-on object can be injected for tests.
"""

import os

from .cache import default_cache_dir, translate_path

ADDON_ID = "script.module.raveresolver"

DEFAULTS = {
    "resolver_service_url": "",
    "resolver_service_token": "",
    "resolver_service_cookie": "",
    "resolver_enable_mega": False,
    "resolver_http_timeout": 20,
    "resolver_service_timeout": 25,
    "resolver_cache_dir": "",
    "resolver_cache_ttl": 2 * 60 * 60,
}

MIN_TIMEOUT = 3
MAX_TIMEOUT = 120


class Settings(object):
    """Settings reader with stable defaults and range clamps."""

    def __init__(self, addon=None, addon_id=ADDON_ID):
        self._addon = addon
        self.addon_id = addon_id
        self._warned = False

    def _reader(self):
        if self._addon is not None:
            return self._addon
        try:
            import xbmcaddon

            self._addon = xbmcaddon.Addon(self.addon_id)
        except Exception:  # noqa: BLE001 - tests/smoke runs have no Kodi
            self._addon = _EmptyAddon()
        return self._addon

    def raw(self, name):
        try:
            value = self._reader().getSetting(name)
        except Exception:  # noqa: BLE001
            return ""
        return "" if value is None else str(value)

    def text(self, name, default=""):
        value = self.raw(name).strip()
        return value if value else default

    def integer(self, name, default, minimum=None, maximum=None):
        try:
            value = int(float(self.raw(name)))
        except (TypeError, ValueError):
            value = int(default)
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def boolean(self, name, default=False):
        value = self.raw(name).strip().lower()
        if not value:
            return bool(default)
        return value in ("true", "1", "yes", "on")

    @property
    def service_url(self):
        return self.text("resolver_service_url", DEFAULTS["resolver_service_url"])

    @property
    def service_token(self):
        return self.raw("resolver_service_token").strip()

    @property
    def service_cookie(self):
        """A web session cookie value/pair for cookie-auth mode.

        This is a bearer credential, not a preference: it is read exactly as
        configured (``name=value`` or a bare value) and is never included in
        logs or the public settings view.
        """
        return self.raw("resolver_service_cookie").strip()

    @property
    def enable_mega(self):
        return self.boolean("resolver_enable_mega",
                            DEFAULTS["resolver_enable_mega"])

    @property
    def http_timeout(self):
        return self.integer("resolver_http_timeout",
                            DEFAULTS["resolver_http_timeout"],
                            MIN_TIMEOUT, MAX_TIMEOUT)

    @property
    def service_timeout(self):
        return self.integer("resolver_service_timeout",
                            DEFAULTS["resolver_service_timeout"],
                            MIN_TIMEOUT, MAX_TIMEOUT)

    @property
    def cache_ttl(self):
        return self.integer("resolver_cache_ttl", DEFAULTS["resolver_cache_ttl"],
                            0, 24 * 60 * 60)

    @property
    def cache_dir(self):
        configured = self.text("resolver_cache_dir", "")
        if configured:
            return translate_path(configured)
        return default_cache_dir()

    @property
    def service_configured(self):
        return bool(self.service_url)

    def as_public_dict(self):
        """Settings safe for a status screen/log (never includes the token)."""
        return {
            "service_url": self.service_url,
            "service_configured": self.service_configured,
            "token_configured": bool(self.service_token),
            "cookie_configured": bool(self.service_cookie),
            "auth_mode": self.service_auth_mode,
            "enable_mega": self.enable_mega,
            "http_timeout": self.http_timeout,
            "service_timeout": self.service_timeout,
            "cache_dir": self.cache_dir,
            "cache_ttl": self.cache_ttl,
        }

    @property
    def service_auth_mode(self):
        """``bearer``, ``cookie`` or ``none``; matches ServiceClient."""
        if self.service_token:
            return "bearer"
        if self.service_cookie:
            return "cookie"
        return "none"

    def __repr__(self):
        return "<Settings service=%s auth=%s mega=%s cache=%s>" % (
            "yes" if self.service_configured else "no",
            self.service_auth_mode,
            "yes" if self.enable_mega else "no",
            os.path.basename(self.cache_dir) or "default")


class _EmptyAddon(object):
    def getSetting(self, _name):
        return ""
