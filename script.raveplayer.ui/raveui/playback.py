# -*- coding: utf-8 -*-
"""Hand playback to Kodi from the script add-on.

A script add-on has no plugin handle, so ``setResolvedUrl`` is not applicable
here. We build a one-item Kodi music playlist and call ``Player().play`` — the
same public playback path a plugin uses after it resolves a stream. The call is
made exactly once per explicit user action by the controller; there is no loop,
watchdog or retry in this module.
"""

from dataclasses import dataclass

import xbmc
import xbmcgui


@dataclass
class PlaybackResult:
    text: str
    url: str


class PlaybackService(object):
    def __init__(self, xbmc_module=None, xbmcgui_module=None):
        self.xbmc = xbmc_module or xbmc
        self.xbmcgui = xbmcgui_module or xbmcgui
        self.last_url = ""
        self.calls = 0

    def play(self, track):
        """Start ``track`` and return the now-playing line.

        Raises ``ValueError`` for an empty URL; the controller turns that into a
        status line instead of leaving the window in a playing-looking state.
        """
        url = str(getattr(track, "url", "") or "").strip()
        if not url:
            raise ValueError("empty stream URL")
        title = str(getattr(track, "title", "") or "Untitled")
        pack = str(getattr(track, "pack", "") or "")
        live = bool(getattr(track, "live", False))
        art = str(getattr(track, "art", "") or "")

        item = self.xbmcgui.ListItem(label=title, path=url)
        if art:
            item.setArt({"thumb": art, "icon": art})
        info = {"title": title}
        if pack:
            info["album"] = pack
        if live:
            info["artist"] = title
        item.setInfo("music", info)
        item.setProperty("IsPlayable", "true")
        if live:
            item.setProperty("IsLiveStream", "true")

        playlist = self.xbmc.PlayList(self.xbmc.PLAYLIST_MUSIC)
        playlist.clear()
        playlist.add(url, item)
        self.xbmc.Player().play(playlist)
        self.last_url = url
        self.calls += 1
        text = "Now playing: %s — %s" % (title, pack) if pack else \
            "Now playing: %s" % title
        return PlaybackResult(text, url)
