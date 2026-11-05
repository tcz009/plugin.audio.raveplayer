# -*- coding: utf-8 -*-
"""Small best-effort on-disk cache for network responses.

Kodi add-ons are killed and restarted constantly, so an in-memory cache would
not help much: the menu count for five podcast feeds would still mean five
HTTP requests on every load.  This stores one JSON file per key under the
add-on's profile directory and treats every disk operation as optional — a
read-only profile, a full disk or a corrupt file must never stop playback.

``ttl`` is in seconds.  Entries older than the TTL are ignored.  Only JSON
values are stored; callers keep JSON text or parsed JSON in the cache.

Hardening in 3.9.11: writes stay atomic (temp file + ``os.replace``), and a
small periodic maintenance pass bounds the directory so it cannot grow for
ever (old entries and stale temp files are removed, and the entry count is
capped).  Reads also reject oversized entry files instead of loading them.
"""

import hashlib
import json
import os
import tempfile
import threading
import time

from . import kodi

VERSION = 1
CACHE_DIR_ENV = "RAVEPLAYER_CACHE_DIR"

MAX_ENTRY_BYTES = 16 * 1024 * 1024  # larger files cannot be ours; drop them
MAX_ENTRIES = 2000                  # cap on live cache entries
MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # 30 days
STALE_TEMP_SECONDS = 60 * 60        # abandoned .tmp-* files after a crash
CLEANUP_EVERY = 64                  # run maintenance after this many writes

_writes_since_maintenance = 0
_write_lock = threading.Lock()


class _Missing(object):
    """Sentinel distinct from a cached ``None``/empty value."""

    def __repr__(self):
        return "cache.MISSING"


MISSING = _Missing()


def _directory():
    """Return the cache directory, preferring the add-on profile."""
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return override
    try:
        profile = kodi.ADDON.getAddonInfo("profile") or ""
    except Exception:  # Kodi API is unavailable outside Kodi
        profile = ""
    if profile:
        return os.path.join(kodi.translate_path(profile), "cache")
    # The smoke runner and unit tests have no real Kodi profile.
    return os.path.join(tempfile.gettempdir(), "raveplayer-cache")


def _log(message, level=10):
    try:
        kodi.log("cache: " + message, level=level)
    except Exception:
        pass


def path_for(key):
    """Return the file path for a cache key (exposed for tests/debugging)."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return os.path.join(_directory(), digest + ".json")


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _read(key):
    path = path_for(key)
    try:
        if os.path.getsize(path) > MAX_ENTRY_BYTES:
            _log("dropping oversized cache entry %s" % key)
            _remove(path)
            return MISSING
    except OSError:
        return MISSING
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return MISSING
    except (OSError, ValueError, TypeError) as exc:
        _log("ignoring unreadable entry %s (%s)" % (key, exc))
        _remove(path)
        return MISSING

    if not isinstance(payload, dict) or payload.get("v") != VERSION:
        _remove(path)
        return MISSING
    timestamp = payload.get("ts")
    if not isinstance(timestamp, (int, float)):
        _remove(path)
        return MISSING
    if "value" not in payload or payload["value"] is None:
        # A truncated or hand-edited file must read as a miss, never as the
        # MISSING sentinel: callers would treat that object as real data.
        _remove(path)
        return MISSING
    return timestamp, payload["value"]


def get(key, ttl, now=None):
    """Return a cached value, or :data:`MISSING` when absent/stale.

    ``ttl`` may be ``None`` for an entry that never expires.  Any disk or
    decode problem is logged at debug level and reported as a miss.
    """
    result = _read(key)
    if result is MISSING:
        return MISSING
    timestamp, value = result
    now = time.time() if now is None else now
    age = now - timestamp
    if ttl is not None and (ttl <= 0 or age < 0 or age > ttl):
        return MISSING
    return value


def has(key, ttl, now=None):
    """True when :func:`get` would return a value (no deep copy / no return)."""
    result = _read(key)
    if result is MISSING:
        return False
    timestamp, _value = result
    now = time.time() if now is None else now
    age = now - timestamp
    return not (ttl is not None and (ttl <= 0 or age < 0 or age > ttl))


def _maybe_maintain():
    if _writes_since_maintenance % CLEANUP_EVERY:
        return
    try:
        maintain()
    except Exception as exc:  # maintenance must never break a cache write
        _log("maintenance failed (%s)" % exc)


def put(key, value, sync=True):
    """Store a JSON-serialisable value.  Returns True on success.

    ``sync=False`` skips ``fsync`` for derived/recomputable entries (parsed
    pages): the rename is still atomic, and a lost entry just re-parses.
    """
    global _writes_since_maintenance
    if value is None:
        return False
    path = path_for(key)
    temporary = None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=os.path.dirname(path),
            prefix=".tmp-", suffix=".json", delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(
                {"v": VERSION, "ts": time.time(), "value": value},
                handle, ensure_ascii=False, separators=(",", ":"),
            )
            handle.flush()
            if sync:
                os.fsync(handle.fileno())
        os.replace(temporary, path)
        with _write_lock:
            _writes_since_maintenance += 1
            due = _writes_since_maintenance % CLEANUP_EVERY == 0
        if due:
            _maybe_maintain()
        return True
    except (OSError, TypeError, ValueError) as exc:
        _log("could not write %s (%s)" % (key, exc))
        if temporary:
            _remove(temporary)
        return False


def maintain(now=None, max_entries=MAX_ENTRIES, max_age=MAX_AGE_SECONDS,
             stale_temp=STALE_TEMP_SECONDS):
    """Remove stale/oversized cache files and cap the directory size.

    Returns the number of files removed.  Best-effort: every filesystem error
    is ignored so a read-only profile keeps working.
    """
    directory = _directory()
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    now = time.time() if now is None else now
    removed = 0
    entries = []
    for name in names:
        path = os.path.join(directory, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        if name.startswith(".tmp-"):
            if now - stat.st_mtime > stale_temp:
                _remove(path)
                removed += 1
            continue
        if not name.endswith(".json"):
            continue
        if now - stat.st_mtime > max_age:
            _remove(path)
            removed += 1
            continue
        entries.append((stat.st_mtime, path))
    if len(entries) > max_entries:
        entries.sort(key=lambda item: item[0])
        for _mtime, path in entries[: len(entries) - max_entries]:
            _remove(path)
            removed += 1
    return removed


def remember(key, ttl, producer, sync=True):
    """Return a cached value, otherwise call ``producer`` and cache its result.

    ``producer`` results of ``None`` are treated as failures and are not
    cached, so a temporary network error does not stick for the whole TTL.
    ``sync=False`` skips fsync: correct for derived/recomputable entries such
    as raw HTTP bodies, where a lost write just means one more fetch.
    """
    value = get(key, ttl)
    if value is not MISSING:
        return value
    value = producer()
    if value is not None:
        put(key, value, sync=sync)
    return value


def fingerprint(text):
    """Stable (cross-process) fingerprint of an exact page body."""
    return hashlib.blake2b(str(text).encode("utf-8", "replace"),
                           digest_size=8).hexdigest()


def parsed(key, ttl, body, parser):
    """Return the parsed form of ``body``, re-parsing only when it changes.

    Kodi starts a fresh Python process for every directory, so a parsed page
    has to live on disk to survive a refresh.  The raw body is fingerprinted
    first: a changed page (or a test fixture) re-parses, while a warm refresh
    skips the regex/XML pass.  A parser result that is not JSON-safe is
    returned but not cached.
    """
    if body is None:
        return None
    digest = fingerprint(body)
    record = get(key, ttl)
    if isinstance(record, dict) and record.get("fingerprint") == digest:
        value = record.get("value")
        if isinstance(value, (list, dict)):
            return value
    value = parser(body)
    if isinstance(value, (list, dict)):
        put(key, {"fingerprint": digest, "value": value}, sync=False)
    return value
