# -*- coding: utf-8 -*-
"""List item construction, kept tidy so routes read like a menu definition."""

import re

import xbmcgui
import xbmcplugin

from . import kodi

DEFAULT_FANART = kodi.FANART

# Kodi display markup, e.g. [COLOR gray]...[/COLOR] or [I]...[/I].  Label text
# may carry it; the media metadata title must not, or the OSD shows the tags.
_MARKUP_RE = re.compile(
    r"\[/?(?:COLOR|B|I|U|LIGHT|CAPITALIZE|LOWERCASE|UPPERCASE|CR)(?:[^\]]*)\]",
    re.IGNORECASE,
)


def plain(text):
    """Return display text without Kodi markup tags."""
    return _MARKUP_RE.sub("", str(text or ""))


def add_item(handle, url, label, is_folder=True, art=None, info=None, playable=False, context=None):
    item = xbmcgui.ListItem(label=label)
    if context:
        item.addContextMenuItems(context)
    if art:
        item.setArt(art)
    if info:
        item.setInfo("music", info)
    if playable:
        item.setProperty("IsPlayable", "true")
        item.setProperty("IsInternetStream", "true")
    xbmcplugin.addDirectoryItem(handle=handle, url=url, listitem=item, isFolder=is_folder)
    return item


def menu_item(handle, url, label, icon=None, fanart=None, plot=None, context=None, title=None):
    art = {
        "icon": icon or kodi.ICON,
        "thumb": icon or kodi.ICON,
        "fanart": fanart or DEFAULT_FANART,
        "poster": icon or kodi.ICON,
    }
    info = {"title": plain(title or label), "plot": plot or plain(label), "mediatype": "music"}
    return add_item(handle, url, label, is_folder=True, art=art, info=info, context=context)


def track_item(handle, url, label, thumb=None, fanart=None, plot=None, artist=None, album=None,
               duration=None, context=None, title=None):
    art = {
        "icon": thumb or kodi.ICON,
        "thumb": thumb or kodi.ICON,
        "fanart": fanart or DEFAULT_FANART,
    }
    info = {"title": plain(title or label), "plot": plot or "", "mediatype": "music"}
    if artist:
        info["artist"] = plain(artist)
    if album:
        info["album"] = plain(album)
    if duration:
        info["duration"] = duration
    return add_item(handle, url, label, is_folder=False, art=art, info=info, playable=True, context=context)
