# -*- coding: utf-8 -*-
"""One audio policy for the whole app.

A script add-on has no plugin handle, so ``setResolvedUrl`` is not applicable
here.  Every *remote* stream is handed to Kodi as a ``plugin://`` play URL, so
the plugin's own ``mode=play`` route owns host validation, the RTP egress proxy,
the loopback bridge and live reconnect.  The script never hands a raw remote
URL to the player.

Two deliberately local exceptions use the file directly:

* a downloaded file (already on disk, no network policy applies)
* a platform hand-off path (e.g. the Mixcloud add-on's ``plugin://`` URL)

``play`` is one playlist entry; ``play_collection`` queues the whole collection
(Play all / Shuffle).  ``stop`` is the explicit Stop action.  Leaving the window
does **not** stop audio: Kodi owns playback, so the fallback lists and the Kodi
home remain usable while the set continues.  This is the single, documented
policy; there is no auto-stop, auto-advance or watchdog.
"""

import urllib.parse
from dataclasses import dataclass

import xbmc
import xbmcgui

PLUGIN = "plugin://plugin.audio.raveplayer/"
PLUGIN_ID = "plugin.audio.raveplayer"


@dataclass
class PlaybackResult:
    text: str
    url: str
    count: int = 1


class PlaybackService(object):
    def __init__(self, xbmc_module=None, xbmcgui_module=None):
        self.xbmc = xbmc_module or xbmc
        self.xbmcgui = xbmcgui_module or xbmcgui
        self.last_url = ""
        self.calls = 0
        self.stops = 0
        self.last_paths = []

    def _plugin_path(self, track):
        url = str(getattr(track, "url", "") or "").strip()
        title = str(getattr(track, "title", "") or "Untitled")
        params = {"mode": "play", "url": url, "label": title}
        if getattr(track, "live", False):
            params["live"] = 1
            # The plugin's reconnect resolver keys on the station token
            # (kool/rinse/centreforce), not the generic "Live radio" album
            # label.  Fall back to pack/title only for a track without one.
            params["station"] = str(
                getattr(track, "station", "") or getattr(track, "pack", "")
                or title)
        return PLUGIN + "?" + urllib.parse.urlencode(params)

    @staticmethod
    def _is_direct(track):
        path = str(getattr(track, "path", "") or "")
        if path:
            return True
        if getattr(track, "local", False):
            return True
        return bool(str(getattr(track, "url", "") or "").startswith("file://"))

    def _item(self, track, path):
        title = str(getattr(track, "title", "") or "Untitled")
        pack = str(getattr(track, "pack", "") or "")
        live = bool(getattr(track, "live", False))
        art = str(getattr(track, "art", "") or "")
        item = self.xbmcgui.ListItem(label=title, path=path)
        if art:
            item.setArt({"thumb": art, "icon": art, "poster": art})
        info = {"title": title}
        if pack:
            info["album"] = pack
        if live:
            info["artist"] = pack or title
        item.setInfo("music", info)
        item.setProperty("IsPlayable", "true")
        if live:
            item.setProperty("IsLiveStream", "true")
            item.setProperty("IsInternetStream", "true")
        return item

    def play(self, track):
        """Start one item and return the now-playing line.

        Raises ``ValueError`` for an empty URL; the controller turns that into a
        quiet status line instead of leaving the window in a playing-looking
        state.
        """
        url = str(getattr(track, "url", "") or "").strip()
        if not url:
            raise ValueError("empty stream URL")
        path = str(getattr(track, "path", "") or "")
        if path:
            pass
        elif getattr(track, "local", False) or url.startswith("file://"):
            path = url
        else:
            path = self._plugin_path(track)
        item = self._item(track, path)
        playlist = self.xbmc.PlayList(self.xbmc.PLAYLIST_MUSIC)
        playlist.clear()
        playlist.add(path, item)
        self.xbmc.Player().play(playlist)
        self.last_url = url
        self.last_paths = [path]
        self.calls += 1
        title = str(getattr(track, "title", "") or "Untitled")
        pack = str(getattr(track, "pack", "") or "")
        text = "Now playing: %s — %s" % (title, pack) if pack else \
            "Now playing: %s" % title
        return PlaybackResult(text, url, 1)

    def play_collection(self, tracks, shuffle=False):
        """Queue a whole collection in one explicit user action."""
        tracks = [track for track in (tracks or [])
                  if str(getattr(track, "url", "") or "").strip()]
        if not tracks:
            raise ValueError("empty collection")
        if shuffle:
            import random
            tracks = list(tracks)
            random.shuffle(tracks)
        playlist = self.xbmc.PlayList(self.xbmc.PLAYLIST_MUSIC)
        playlist.clear()
        paths = []
        for track in tracks:
            url = str(getattr(track, "url", ""))
            path = str(getattr(track, "path", "") or "")
            if not path:
                path = url if getattr(track, "local", False) or url.startswith("file://") \
                    else self._plugin_path(track)
            playlist.add(path, self._item(track, path))
            paths.append(path)
        self.xbmc.Player().play(playlist)
        self.last_url = str(getattr(tracks[0], "url", ""))
        self.last_paths = paths
        self.calls += 1
        first = str(getattr(tracks[0], "title", "") or "Untitled")
        text = ("Shuffled %d tracks — %s" % (len(tracks), first)) if shuffle else \
            ("Playing %d tracks — %s" % (len(tracks), first))
        return PlaybackResult(text, self.last_url, len(paths))

    def stop(self):
        try:
            self.xbmc.Player().stop()
            self.stops += 1
            return True
        except Exception:  # noqa: BLE001 - nothing playing / player unavailable
            return False

    def is_playing(self):
        try:
            return bool(self.xbmc.Player().isPlaying())
        except Exception:  # noqa: BLE001 - player not ready
            return False
