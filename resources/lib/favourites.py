# -*- coding: utf-8 -*-
"""Favourites: a small JSON list in the add-on profile directory.

Best-effort like the cache — a read-only profile must never break the add-on,
it just means favourites are not saved.
"""

import json
import os
import tempfile

from . import kodi

FILENAME = "favourites.json"
MAX_ENTRIES = 300
FAV_DIR_ENV = "RAVEPLAYER_FAV_DIR"
VALID_KINDS = ("pack", "dnb", "stream", "legacy_pack", "legacy_jt")


def _path():
    override = os.environ.get(FAV_DIR_ENV)
    if override:
        directory = override
    else:
        try:
            profile = kodi.ADDON.getAddonInfo("profile") or ""
        except Exception:
            profile = ""
        directory = kodi.translate_path(profile) if profile else os.path.join(
            tempfile.gettempdir(), "raveplayer-favs")
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError:
        pass
    return os.path.join(directory, FILENAME)


def _clean(raw):
    """Normalise one stored entry; return None when it is unusable."""
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()
    target = str(raw.get("target") or "").strip()
    if not title or not target:
        return None
    kind = str(raw.get("kind") or "stream").strip().lower()
    if kind not in VALID_KINDS:
        kind = "stream"
    return {
        "kind": kind,
        "target": target,
        "title": title[:200],
        "source": str(raw.get("source") or "").strip()[:120],
    }


def load():
    try:
        with open(_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    entries = []
    for raw in data:
        entry = _clean(raw)
        if entry is not None:
            entries.append(entry)
    return entries[:MAX_ENTRIES]


def save(entries):
    """Write the list atomically, so a killed Kodi cannot corrupt it."""
    cleaned = []
    for raw in entries[:MAX_ENTRIES]:
        entry = _clean(raw)
        if entry is not None:
            cleaned.append(entry)
    path = _path()
    directory = os.path.dirname(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory,
            prefix=".favourites-", suffix=".json", delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(cleaned, handle, ensure_ascii=False, indent=0)
        os.replace(temporary, path)
        return True
    except OSError:
        if temporary:
            try:
                os.remove(temporary)
            except OSError:
                pass
        return False


def key(entry):
    return "%s:%s" % (entry.get("kind", ""), entry.get("target", ""))


def add(entry):
    """Add or refresh an entry; returns True when the list was saved."""
    cleaned = _clean(entry)
    if cleaned is None:
        return False
    entries = [item for item in load() if key(item) != key(cleaned)]
    entries.insert(0, cleaned)
    return save(entries)


def remove(entry_key):
    entries = [item for item in load() if key(item) != entry_key]
    return save(entries)


def has(entry):
    cleaned = _clean(entry)
    if cleaned is None:
        return False
    return any(key(item) == key(cleaned) for item in load())
