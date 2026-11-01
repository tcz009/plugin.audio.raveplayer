# -*- coding: utf-8 -*-
"""List item construction, kept tidy so routes read like a menu definition."""

import xbmcgui
import xbmcplugin

from . import handoff, kodi

DEFAULT_FANART = kodi.FANART

# Kodi display markup, e.g. [COLOR gray]...[/COLOR] or [I]...[/I].  Label text
# may carry it; the media metadata title must not, or the OSD shows the tags.
MAX_MARKUP_CHARS = 1024
_MARKUP_RE = None


def _markup_re():
    global _MARKUP_RE
    if _MARKUP_RE is None:
        import re

        _MARKUP_RE = re.compile(
            r"\[/?(?:COLOR|B|I|U|LIGHT|CAPITALIZE|LOWERCASE|UPPERCASE|CR)"
            r"(?:[^\]]{0,100})?\]",
            re.IGNORECASE,
        )
    return _MARKUP_RE


def plain(text):
    """Return display text without Kodi markup tags.

    Input is capped and the tag-attribute repetition is bounded so hostile
    "[COLOR" x N text cannot scan quadratically (A4).  The regex is compiled
    lazily so the warm root menu does not pay the regex import.
    """
    text = str(text or "")[:MAX_MARKUP_CHARS]
    if "[" not in text:
        return text
    return _markup_re().sub("", text)


def add_item(handle, url, label, is_folder=True, art=None, info=None, playable=False, context=None):
    # Final safety choke point: no raw platform page may ever become a Kodi
    # list-item URL (Android would hand it to Downloader). Routes hide these
    # rows or emit plugin:// hand-offs; this guard catches any missed path.
    if handoff.platform_kind(url):
        kodi.log("ui: refusing raw platform URL for %r" % str(label)[:80], level=30)
        return None
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


def info_item(handle, label, plot=None, icon=None):
    """A read-only information row (credits/sources) that cannot leave Kodi."""
    item = xbmcgui.ListItem(label=label)
    item.setArt({
        "icon": icon or kodi.ICON,
        "thumb": icon or kodi.ICON,
        "fanart": DEFAULT_FANART,
    })
    item.setInfo("music", {"title": plain(label), "plot": plot or plain(label)})
    item.setProperty("IsPlayable", "false")
    xbmcplugin.addDirectoryItem(handle=handle, url="", listitem=item, isFolder=False)
    return item


def end_marker(handle, label="End of list", plot=None):
    """Append a visible, deliberately non-playable terminator row.

    No URL and no IsPlayable property, so selecting it can never start
    playback, resolve a stream or make Kodi continue down a folder playlist.
    """
    item = xbmcgui.ListItem(label=label)
    item.setArt({
        "icon": kodi.ICON,
        "thumb": kodi.ICON,
        "fanart": DEFAULT_FANART,
    })
    item.setInfo("music", {"title": plain(label), "plot": plot or plain(label)})
    item.setProperty("IsPlayable", "false")
    xbmcplugin.addDirectoryItem(handle=handle, url="", listitem=item, isFolder=False)
    return item


def track_item(handle, url, label, thumb=None, fanart=None, plot=None, artist=None, album=None,
               duration=None, context=None, title=None):
    art = {
        "icon": thumb or kodi.ICON,
        "thumb": thumb or kodi.ICON,
        "fanart": fanart or DEFAULT_FANART,
    }
    # Kodi's music InfoTag has no plot; "comment" is the field the music
    # info dialog displays, so set both (plot kept for other consumers/tests).
    info = {"title": plain(title or label), "plot": plot or "", "comment": plot or "",
            "mediatype": "music"}
    if artist:
        info["artist"] = plain(artist)
    if album:
        info["album"] = plain(album)
    if duration:
        info["duration"] = duration
    return add_item(handle, url, label, is_folder=False, art=art, info=info, playable=True, context=context)
