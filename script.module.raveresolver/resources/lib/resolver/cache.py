# -*- coding: utf-8 -*-
"""Best-effort TTL cache for resolved URLs.

Kodi add-ons are restarted constantly, so signed provider URLs are kept on
disk under ``resolver_cache_dir`` (default ``special://temp/raveresolver``).
The cache only holds resolved URLs and provider metadata; it never holds the
service token.  Keys are SHA-256 hashes of provider + URL so a cache file name
does not leak a signed URL either.

Every operation is optional: an unwritable profile, a corrupt file or a full
disk must fall back to an empty cache and never break playback.
"""

import hashlib
import json
import os
import tempfile
import threading
import time

try:  # kept importable outside Kodi
    import xbmcvfs
except Exception:  # pragma: no cover - only in odd embedded builds
    xbmcvfs = None

VERSION = 1
MAX_ENTRY_BYTES = 512 * 1024
DEFAULT_TTL = 2 * 60 * 60


class _Missing(object):
    def __repr__(self):
        return "resolver.cache.MISSING"


MISSING = _Missing()


def translate_path(path):
    text = str(path or "")
    if not text:
        return ""
    if text.startswith("special://"):
        if xbmcvfs is not None:
            try:
                return str(xbmcvfs.translatePath(text))
            except Exception:  # noqa: BLE001
                pass
        # A sensible non-Kodi fallback for tests/smoke runs.
        return os.path.join(tempfile.gettempdir(),
                            text.replace("special://", "").strip("/"))
    return text


def default_cache_dir():
    """The default resolver cache directory (translated for real file I/O)."""
    return translate_path("special://temp/raveresolver")


class Cache(object):
    """A tiny JSON-file cache with per-entry expiry."""

    def __init__(self, directory=None, ttl=DEFAULT_TTL, enabled=True,
                 clock=None):
        self.directory = translate_path(directory) if directory \
            else default_cache_dir()
        self.ttl = int(ttl if ttl is not None else DEFAULT_TTL)
        self.enabled = bool(enabled) and self.ttl > 0
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._memory = {}

    def key(self, *parts):
        raw = "\x1f".join(str(part) for part in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def path_for(self, key):
        return os.path.join(self.directory, key + ".json")

    def _ensure_directory(self):
        path = self.directory
        if not path:
            return False
        try:
            os.makedirs(path, exist_ok=True)
            return True
        except OSError:
            return False

    def get(self, key):
        """Return a cached value, or :data:`MISSING` on miss/expiry/corruption."""
        if not self.enabled:
            return MISSING
        with self._lock:
            record = self._memory.get(key)
            if record is not None:
                if record["expires"] > self._clock():
                    return record["value"]
                self._memory.pop(key, None)
        path = self.path_for(key)
        try:
            if os.path.getsize(path) > MAX_ENTRY_BYTES:
                self._remove(path)
                return MISSING
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return MISSING
        except (OSError, ValueError, TypeError):
            self._remove(path)
            return MISSING
        if not isinstance(payload, dict) or payload.get("v") != VERSION:
            self._remove(path)
            return MISSING
        expires = payload.get("expires")
        if not isinstance(expires, (int, float)) or expires <= self._clock():
            self._remove(path)
            return MISSING
        return payload.get("value", MISSING)

    def put(self, key, value, ttl=None):
        """Store ``value`` until ``ttl`` seconds from now.  Returns success."""
        if not self.enabled:
            return False
        lifetime = int(ttl if ttl is not None else self.ttl)
        if lifetime <= 0:
            return False
        expires = self._clock() + lifetime
        with self._lock:
            self._memory[key] = {"value": value, "expires": expires}
        if not self._ensure_directory():
            return False
        path = self.path_for(key)
        temporary = path + ".tmp"
        payload = {"v": VERSION, "expires": expires, "value": value}
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            os.replace(temporary, path)
            return True
        except (OSError, TypeError, ValueError):
            self._remove(temporary)
            return False

    def delete(self, key):
        with self._lock:
            self._memory.pop(key, None)
        self._remove(self.path_for(key))

    def clear(self):
        """Remove every JSON entry in the cache directory (best effort)."""
        with self._lock:
            self._memory.clear()
        try:
            names = os.listdir(self.directory)
        except OSError:
            return
        for name in names:
            if name.endswith(".json") or name.endswith(".tmp"):
                self._remove(os.path.join(self.directory, name))

    @staticmethod
    def _remove(path):
        try:
            os.remove(path)
        except OSError:
            pass
