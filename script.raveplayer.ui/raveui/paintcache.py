# -*- coding: utf-8 -*-
"""Disk paint cache for the full-screen Rave app (perf/3.9.52).

Kodi starts a fresh Python interpreter for the shell and every plugin route,
so an in-memory page cache dies with the window.  This module stores the last
successful **finished page** (the rows the controller painted, not the raw
upstream response) under the script add-on's profile.  Opening a room then
paints that page in a few milliseconds while the controller refreshes the
source on a worker thread and repaints only when the rows actually changed.

Important properties:

* **Never blocks a paint.**  Reads are a single small JSON file, size-capped,
  with every filesystem/JSON error treated as a miss.
* **Versioned.**  The cache key carries the schema, screen version, plugin
  version and rows-per-page, so an add-on upgrade cannot paint a stale page
  built by old row code.  Old keys simply stop being found and are pruned by
  age/size.
* **Atomic writes.**  Temp file + ``os.replace``; a power cut cannot leave a
  half-written page that decodes into a broken list.
* **Rows only.**  Nothing playable is resolved or fetched here: a stale row
  still goes through the normal play hand-off, which validates the URL.

The cache is a *paint* optimisation, not a source of truth.  A miss, a corrupt
file or a full disk just means the room loads the old way.
"""

import hashlib
import json
import os
import tempfile
import time

from .data import Entry, Page, Track

SCHEMA = 1
CACHE_DIR_ENV = "RAVEPLAYER_SCREEN_CACHE_DIR"
MAX_ENTRY_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_AGE_SECONDS = 30 * 24 * 60 * 60
MAX_ENTRIES = 240
PRUNE_EVERY = 16

_writes = 0


def _translate(path):
    text = str(path or "")
    if not text.startswith("special://"):
        return text
    try:
        import xbmcvfs

        return xbmcvfs.translatePath(text)
    except Exception:  # noqa: BLE001 - Kodi API unavailable outside Kodi
        return text


def default_directory():
    """Profile cache directory, or ``""`` when there is no writable profile."""
    if os.environ.get("RAVEPLAYER_DISABLE_PAINT_CACHE"):
        return ""
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return override
    try:
        import xbmcaddon

        addon = xbmcaddon.Addon("script.raveplayer.ui")
        profile = addon.getAddonInfo("profile") or ""
    except Exception:  # noqa: BLE001 - tests/headless have no Kodi profile
        profile = ""
    if not profile:
        return ""
    return os.path.join(_translate(profile), "paint-cache")


def target_key(target):
    """A stable, short descriptor for a navigation target."""
    if target is None or target == "":
        return "home"
    if isinstance(target, str):
        return "room:" + target
    if isinstance(target, Entry):
        # The same pack can appear in Latest and in an RTP category: include
        # the source and the folder kind so those pages cannot collide.
        return "entry:%s:%s:%s:%s" % (
            target.kind, target.source, target.target, target.key)
    return "obj:" + type(target).__name__ + ":" + str(target)


def cache_key(kind, target, page, rows, versions="", nav=""):
    """Versioned key for one painted page.

    ``nav`` carries the navigation/layout token (home/room/entry/folder/list,
    page number).  The page integer alone is not enough: a folder page 2 and a
    list page 2 can otherwise share a key when their target descriptors
    coincide, and a clamped page could be painted under the requested number
    (advisor P2-5/P2-9).
    """
    raw = "%s|%s|%s|%s|%s|%s|%s" % (
        SCHEMA, versions, kind, target_key(target), page, rows, nav)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return "screen-paint-%s-%s" % (SCHEMA, digest)


# ------------------------------------------------------------------ encoding


def _encode_track(track):
    if track is None:
        return None
    if isinstance(track, Track):
        return {
            "title": track.title,
            "pack": track.pack,
            "url": track.url,
            "art": track.art,
            "live": bool(track.live),
            "duration": track.duration,
            "year": track.year,
            "genre": track.genre,
            "source": track.source,
            "download_source": track.download_source,
            "local": bool(track.local),
            "path": track.path,
        }
    # A foreign track-like object (a test double or a future row type) is not
    # worth guessing at: drop it so the row still paints, unplayable until the
    # refresh replaces it.
    return None


def _encode_entry(entry):
    return {
        "key": entry.key,
        "label": entry.label,
        "subtitle": entry.subtitle,
        "art": entry.art,
        "kind": entry.kind,
        "source": entry.source,
        "target": entry.target,
        "track": _encode_track(entry.track),
        "hero": entry.hero,
        "fact": entry.fact,
        "code": entry.code,
        "plot": entry.plot,
        "meta": entry.meta,
        "year": entry.year,
        "genre": entry.genre,
        "duration": entry.duration,
        "download_source": entry.download_source,
        "downloadable": bool(entry.downloadable),
        "fav_key": entry.fav_key,
    }


def _decode_track(data):
    if not isinstance(data, dict):
        return None
    return Track(
        title=str(data.get("title") or ""),
        pack=str(data.get("pack") or ""),
        url=str(data.get("url") or ""),
        art=str(data.get("art") or ""),
        live=bool(data.get("live")),
        duration=str(data.get("duration") or ""),
        year=str(data.get("year") or ""),
        genre=str(data.get("genre") or ""),
        source=str(data.get("source") or ""),
        download_source=str(data.get("download_source") or ""),
        local=bool(data.get("local")),
        path=str(data.get("path") or ""),
    )


def _decode_entry(data):
    if not isinstance(data, dict):
        return None
    try:
        return Entry(
            key=str(data.get("key") or ""),
            label=str(data.get("label") or ""),
            subtitle=str(data.get("subtitle") or ""),
            art=str(data.get("art") or ""),
            kind=str(data.get("kind") or "track"),
            source=str(data.get("source") or ""),
            target=str(data.get("target") or ""),
            track=_decode_track(data.get("track")),
            hero=str(data.get("hero") or ""),
            fact=str(data.get("fact") or ""),
            code=str(data.get("code") or ""),
            plot=str(data.get("plot") or ""),
            meta=str(data.get("meta") or ""),
            year=str(data.get("year") or ""),
            genre=str(data.get("genre") or ""),
            duration=str(data.get("duration") or ""),
            download_source=str(data.get("download_source") or ""),
            downloadable=bool(data.get("downloadable")),
            fav_key=str(data.get("fav_key") or ""),
        )
    except (TypeError, ValueError):
        return None


def encode_page(page, rows=None):
    """Encode a :class:`~raveui.data.Page` without losing row identity."""
    source_rows = list(getattr(page, "rows", []) or [])
    if rows is not None:
        source_rows = source_rows[:rows]
    encoded = []
    for row in source_rows:
        if isinstance(row, Entry):
            encoded.append(_encode_entry(row))
        elif isinstance(row, dict):
            encoded.append(dict(row))
        else:
            return None  # unknown row type: never write a lossy paint page
    return {
        "rows": encoded,
        "total": max(0, int(getattr(page, "total", 0) or 0)),
        "page": max(1, int(getattr(page, "page", 1) or 1)),
        "pages": max(0, int(getattr(page, "pages", 0) or 0)),
        "rows_per_page": max(1, int(getattr(page, "rows_per_page", 1) or 1)),
        "has_next": bool(getattr(page, "has_next", False)),
        "cursor": str(getattr(page, "cursor", "") or ""),
    }


def decode_page(data):
    if not isinstance(data, dict):
        return None
    rows = []
    for item in data.get("rows") or []:
        if not isinstance(item, dict):
            return None
        if "label" in item and "key" in item:
            row = _decode_entry(item)
        else:
            row = dict(item)  # live rows are plain mapping rows
        if row is None:
            return None
        rows.append(row)
    try:
        return Page(
            rows=rows,
            total=max(0, int(data.get("total", 0) or 0)),
            page=max(1, int(data.get("page", 1) or 1)),
            pages=max(0, int(data.get("pages", 0) or 0)),
            rows_per_page=max(1, int(data.get("rows_per_page", 1) or 1)),
            has_next=bool(data.get("has_next")),
            cursor=str(data.get("cursor") or ""),
        )
    except (TypeError, ValueError):
        return None


def signature(page):
    """Stable fingerprint of a page's painted content (or ``""``)."""
    encoded = encode_page(page)
    if encoded is None:
        return ""
    return hashlib.blake2b(
        json.dumps(encoded, sort_keys=True, ensure_ascii=False).encode("utf-8"),
        digest_size=16).hexdigest()


def encode_library_screen(screen):
    """Encode a :class:`raveui.screens.library.Screen` for a fast repaint.

    Library rows carry an action ``payload``.  It is normally plain JSON
    (strings/ints/lists), which round-trips through the store unchanged; if a
    future row carries a non-serialisable object, the write fails and the room
    simply loads the normal way.
    """
    rows = []
    for row in getattr(screen, "rows", ()) or ():
        try:
            rows.append({
                "label": str(getattr(row, "label", "") or ""),
                "kind": str(getattr(row, "kind", "") or ""),
                "fact": str(getattr(row, "fact", "") or ""),
                "icon": str(getattr(row, "icon", "") or ""),
                "fanart": str(getattr(row, "fanart", "") or ""),
                "code": str(getattr(row, "code", "") or ""),
                "payload": dict(getattr(row, "payload", {}) or {}),
                "subtitle": str(getattr(row, "subtitle", "") or ""),
                "plot": str(getattr(row, "plot", "") or ""),
            })
        except (TypeError, ValueError):
            return None
    return {
        "route": str(getattr(screen, "route", "") or ""),
        "title": str(getattr(screen, "title", "") or ""),
        "subtitle": str(getattr(screen, "subtitle", "") or ""),
        "rows": rows,
        "state": str(getattr(screen, "state", "") or ""),
        "page": max(1, int(getattr(screen, "page", 1) or 1)),
        "pages": max(1, int(getattr(screen, "pages", 1) or 1)),
        "total": max(0, int(getattr(screen, "total", 0) or 0)),
        "page_size": max(1, int(getattr(screen, "page_size", 1) or 1)),
        "query": str(getattr(screen, "query", "") or ""),
        "error": str(getattr(screen, "error", "") or ""),
        "noun": str(getattr(screen, "noun", "items") or "items"),
        "code": str(getattr(screen, "code", "") or ""),
    }


def decode_library_screen(data):
    if not isinstance(data, dict):
        return None
    from .screens.library import Row, Screen

    rows = []
    for item in data.get("rows") or []:
        if not isinstance(item, dict):
            return None
        payload = item.get("payload")
        rows.append(Row(
            label=str(item.get("label") or ""),
            kind=str(item.get("kind") or ""),
            fact=str(item.get("fact") or ""),
            icon=str(item.get("icon") or ""),
            fanart=str(item.get("fanart") or ""),
            code=str(item.get("code") or ""),
            payload=dict(payload) if isinstance(payload, dict) else {},
            subtitle=str(item.get("subtitle") or ""),
            plot=str(item.get("plot") or ""),
        ))
    try:
        return Screen(
            route=str(data.get("route") or ""),
            title=str(data.get("title") or ""),
            subtitle=str(data.get("subtitle") or ""),
            rows=tuple(rows),
            state=str(data.get("state") or ""),
            page=max(1, int(data.get("page", 1) or 1)),
            pages=max(1, int(data.get("pages", 1) or 1)),
            total=max(0, int(data.get("total", 0) or 0)),
            page_size=max(1, int(data.get("page_size", 1) or 1)),
            query=str(data.get("query") or ""),
            error=str(data.get("error") or ""),
            noun=str(data.get("noun") or "items"),
            code=str(data.get("code") or ""),
        )
    except (TypeError, ValueError):
        return None


def library_signature(screen):
    encoded = encode_library_screen(screen)
    if encoded is None:
        return ""
    return hashlib.blake2b(
        json.dumps(encoded, sort_keys=True, ensure_ascii=False).encode("utf-8"),
        digest_size=16).hexdigest()


# --------------------------------------------------------------------- store


class PaintCache(object):
    """Tiny JSON page store with versioned keys and best-effort writes."""

    def __init__(self, directory=None, versions=""):
        self.directory = directory if directory is not None else default_directory()
        self.versions = str(versions or "")

    @property
    def enabled(self):
        return bool(self.directory)

    def key(self, kind, target, page, rows, nav=""):
        return cache_key(kind, target, page, rows, self.versions, nav)

    def _path(self, key):
        return os.path.join(self.directory, key + ".json")

    def load(self, kind, target, page, rows, nav=""):
        """Return the cached payload, or ``None`` on any miss/error."""
        if not self.enabled:
            return None
        path = self._path(self.key(kind, target, page, rows, nav))
        try:
            if os.path.getsize(path) > MAX_ENTRY_BYTES:
                self._remove(path)
                return None
        except OSError:
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError, TypeError):
            self._remove(path)
            return None
        if not isinstance(payload, dict) or payload.get("v") != SCHEMA:
            self._remove(path)
            return None
        # Read-time age check: pruning only runs every 16 writes, so an
        # untouched month-old entry must not survive a paint just because no
        # write has happened since (advisor P2-16).
        try:
            stored = float(payload.get("ts"))
        except (TypeError, ValueError):
            self._remove(path)
            return None
        if time.time() - stored > MAX_AGE_SECONDS:
            self._remove(path)
            return None
        value = payload.get("value")
        return value if isinstance(value, dict) else None

    def delete(self, kind, target, page, rows, nav=""):
        """Remove one entry (destructive actions use this before a reload)."""
        if not self.enabled:
            return False
        path = self._path(self.key(kind, target, page, rows, nav))
        if not os.path.exists(path):
            return False
        self._remove(path)
        return True

    def store(self, kind, target, page, rows, value, nav=""):
        if not self.enabled or not isinstance(value, dict):
            return False
        path = self._path(self.key(kind, target, page, rows, nav))
        temporary = None
        try:
            os.makedirs(self.directory, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.directory,
                    prefix=".tmp-", suffix=".json", delete=False) as handle:
                temporary = handle.name
                json.dump({"v": SCHEMA, "ts": time.time(), "value": value},
                          handle, ensure_ascii=False, separators=(",", ":"))
            os.replace(temporary, path)
            self._maybe_prune()
            return True
        except (OSError, TypeError, ValueError):
            if temporary:
                self._remove(temporary)
            return False

    def clear(self):
        """Remove every paint entry (used when the add-on version changes)."""
        if not self.enabled:
            return 0
        removed = 0
        try:
            names = os.listdir(self.directory)
        except OSError:
            return 0
        for name in names:
            if name.startswith("screen-paint-") or name.startswith(".tmp-"):
                self._remove(os.path.join(self.directory, name))
                removed += 1
        return removed

    def _remove(self, path):
        try:
            os.remove(path)
        except OSError:
            pass

    def _maybe_prune(self):
        global _writes
        _writes += 1
        if _writes % PRUNE_EVERY:
            return
        self.prune()

    def prune(self, now=None, max_entries=MAX_ENTRIES,
              max_age=MAX_AGE_SECONDS, max_bytes=MAX_TOTAL_BYTES):
        """Drop old/excess/large entries; never raises into a paint.

        Count and byte budgets are both enforced, oldest first.  The byte cap
        stops 240 * 4 MiB theoretical growth and keeps search pages from
        crowding out room pages (advisor P2-16).
        """
        if not self.enabled:
            return 0
        now = time.time() if now is None else now
        try:
            names = os.listdir(self.directory)
        except OSError:
            return 0
        entries = []
        removed = 0
        for name in names:
            path = os.path.join(self.directory, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            if name.startswith(".tmp-"):
                if now - stat.st_mtime > 3600:
                    self._remove(path)
                    removed += 1
                continue
            if not (name.startswith("screen-paint-") and name.endswith(".json")):
                continue
            if now - stat.st_mtime > max_age:
                self._remove(path)
                removed += 1
                continue
            entries.append((stat.st_mtime, path, int(stat.st_size)))
        entries.sort(key=lambda item: item[0])
        if max_bytes is not None and max_bytes >= 0:
            total = sum(size for _mtime, _path, size in entries)
            while entries and total > max_bytes:
                _mtime, path, size = entries.pop(0)
                self._remove(path)
                total -= size
                removed += 1
        if max_entries is not None and len(entries) > max_entries:
            for _mtime, path, _size in entries[:len(entries) - max_entries]:
                self._remove(path)
                removed += 1
        return removed
