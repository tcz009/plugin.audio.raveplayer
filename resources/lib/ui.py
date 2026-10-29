# -*- coding: utf-8 -*-
"""List item construction, kept tidy so routes read like a menu definition."""

import xbmcgui
import xbmcplugin

from . import kodi

DEFAULT_FANART = kodi.FANART


def add_item(handle, url, label, is_folder=True, art=None, info=None, playable=False):
    item = xbmcgui.ListItem(label=label)
    if art:
        item.setArt(art)
    if info:
        item.setInfo("music", info)
    if playable:
        item.setProperty("IsPlayable", "true")
        item.setProperty("IsInternetStream", "true")
    xbmcplugin.addDirectoryItem(handle=handle, url=url, listitem=item, isFolder=is_folder)
    return item


def menu_item(handle, url, label, icon=None, fanart=None, plot=None):
    art = {
        "icon": icon or kodi.ICON,
        "thumb": icon or kodi.ICON,
        "fanart": fanart or DEFAULT_FANART,
        "poster": icon or kodi.ICON,
    }
    info = {"title": label, "plot": plot or label, "mediatype": "music"}
    return add_item(handle, url, label, is_folder=True, art=art, info=info)


def track_item(handle, url, label, thumb=None, fanart=None, plot=None, artist=None, album=None, duration=None):
    art = {
        "icon": thumb or kodi.ICON,
        "thumb": thumb or kodi.ICON,
        "fanart": fanart or DEFAULT_FANART,
    }
    info = {"title": label, "plot": plot or "", "mediatype": "music"}
    if artist:
        info["artist"] = artist
    if album:
        info["album"] = album
    if duration:
        info["duration"] = duration
    return add_item(handle, url, label, is_folder=False, art=art, info=info, playable=True)
