# -*- coding: utf-8 -*-
"""Kodi wrappers kept in one place so the rest of the add-on stays testable."""

import os

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")
ADDON_VERSION = ADDON.getAddonInfo("version")
ADDON_PATH = ADDON.getAddonInfo("path")
ICON = ADDON.getAddonInfo("icon")
FANART = ADDON.getAddonInfo("fanart")
# Absolute round-face sticker used when a playable item has no real cover.
ROUND_FACE = os.path.join(ADDON_PATH, "resources", "art", "icon.png")


def _kodi_major():
    """Best-effort Kodi major version; 0 outside Kodi/test stubs."""
    try:
        raw = str(xbmc.getInfoLabel("System.BuildVersion") or "")
    except Exception:
        return 0
    digits = ""
    for char in raw:
        if char.isdigit():
            digits += char
        elif digits:
            break
    try:
        return int(digits)
    except ValueError:
        return 0


KODI_MAJOR = _kodi_major()


def music_info(title, plot="", **extra):
    """Build a music InfoTag without Kodi 22's unsupported ``plot`` key.

    Kodi 18-21 tolerate ``plot`` in a music InfoTag (the old add-on used it);
    Kodi 22 logs an ``Unknown Music Info Key "plot"`` error for every item.
    ``comment`` is the field shown by the music info dialog on all supported
    versions, so use it as the portable display field.
    """
    info = {"title": plain_text(title)}
    if plot:
        info["comment"] = plot
        if KODI_MAJOR and KODI_MAJOR < 22:
            info["plot"] = plot
    info.update(extra)
    return info


def plain_text(value):
    """No-op placeholder kept for callers that pass already-plain titles."""
    return str(value or "")


def video_info(plot):
    """Build the minimal video InfoTag that makes ``ListItem.Plot`` resolve.

    Estuary's info and poster panels read ``ListItem.Plot``, and Kodi maps that
    label to the **video** InfoTag (``VideoGUIInfo.cpp``) — the music
    ``comment`` field (Kodi 22's portable display field) never reaches it.
    Only ``plot`` is set: no title, no media type, so nothing can override the
    music tag that still drives the song panel and the OSD.
    """
    text = str(plot or "").strip()
    return {"plot": text} if text else {}


def log(message, level=xbmc.LOGDEBUG):
    xbmc.log("[%s] %s" % (ADDON_ID, message), level)


def notify(message, heading=None, icon=ICON, time=4000):
    """Show a Kodi notification; commas separate builtin arguments."""
    heading = str(heading or ADDON_NAME).replace(",", " ")
    message = str(message).replace(",", " ").replace("\n", " ")
    try:
        milliseconds = int(time)
    except (TypeError, ValueError):
        milliseconds = 4000
    xbmc.executebuiltin(
        "Notification(%s,%s,%d,%s)" % (heading, message, milliseconds, icon)
    )


def refresh():
    """Ask Kodi to re-run the current folder (after a favourite changes)."""
    xbmc.executebuiltin("Container.Refresh")


def translate_path(path):
    """Turn a Kodi ``special://`` path into a real filesystem path."""
    text = str(path or "")
    if not text.startswith("special://"):
        return text
    try:
        import xbmcvfs

        return xbmcvfs.translatePath(text)
    except Exception:  # Kodi API is unavailable outside Kodi
        return text


def setting(name, default=""):
    value = ADDON.getSetting(name)
    return value if value not in (None, "") else default


def setting_int(name, default):
    try:
        return int(ADDON.getSetting(name))
    except (TypeError, ValueError):
        return default


def setting_bool(name, default=False):
    value = ADDON.getSetting(name)
    if value in (None, ""):
        return default
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def dialog():
    return xbmcgui.Dialog()


_ended_handles = set()


def reset_directory(handle):
    """Forget any previous end-of-directory state for this plugin handle."""
    _ended_handles.discard(handle)


def directory_ended(handle):
    """True when ``end_directory`` already closed this handle."""
    return handle in _ended_handles


def end_directory(handle, content="files", cache=False, succeeded=True):
    """Finish a directory.

    ``cache=False`` by default: Kodi's on-disk directory cache otherwise keeps
    serving a favourites list (or a "Latest") folder after its contents have
    changed.  The add-on has its own HTTP cache, so re-running a route is cheap.

    The handle is remembered so ``routes.dispatch`` can close a directory that
    a crashing handler left open (and never call ``endOfDirectory`` twice).
    """
    _ended_handles.add(handle)
    xbmcplugin.setContent(handle, content)
    xbmcplugin.endOfDirectory(handle, succeeded=succeeded, cacheToDisc=cache)
