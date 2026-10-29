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
    xbmc.executebuiltin(
        "Notification(%s,%s,%d,%s)"
        % ((heading or ADDON_NAME).replace(",", " "), message.replace(",", " "), time, icon)
    )


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
    if value == "":
        return default
    return value.lower() == "true"


def dialog():
    return xbmcgui.Dialog()


def end_directory(handle, content="files"):
    xbmcplugin.setContent(handle, content)
    xbmcplugin.endOfDirectory(handle, cacheToDisc=True)
