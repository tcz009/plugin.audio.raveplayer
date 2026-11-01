# -*- coding: utf-8 -*-
"""Kodi wrappers kept in one place so the rest of the add-on stays testable."""

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


def open_external(url):
    """Best-effort open a source page for sources Kodi cannot stream.

    Android gets an external VIEW intent; elsewhere a dialog shows the URL
    (Kodi has no portable browser builtin).  Never raises to the plugin thread.
    """
    text = str(url or "").strip()
    if not text.lower().startswith(("http://", "https://")):
        return False
    try:
        if xbmc.getCondVisibility("System.Platform.Android"):
            xbmc.executebuiltin(
                "StartAndroidActivity(,android.intent.action.VIEW,,%s)" % text
            )
            return True
    except Exception as exc:  # pragma: no cover - platform-specific
        log("could not open Android intent (%s)" % exc, level=xbmc.LOGWARNING)
    try:
        dialog().ok("Open this page", text)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        log("could not show source URL (%s)" % exc, level=xbmc.LOGWARNING)
        return False


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
