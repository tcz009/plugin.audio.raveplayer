# -*- coding: utf-8 -*-
"""Hand-off to official Kodi add-ons instead of leaving Kodi.

The add-on never opens a browser or an external URL.  Sources that cannot be
streamed directly (Mixcloud, SoundCloud, YouTube) are handed to their official
Kodi add-ons via ``plugin://`` directory URLs built here.  If the relevant
add-on is not installed the caller hides the row entirely (see routes).
"""

import urllib.parse

import xbmc
import xbmcaddon

MIXCLOUD_ID = "plugin.audio.mixcloud"
SOUNDCLOUD_ID = "plugin.audio.soundcloud"
YOUTUBE_ID = "plugin.video.youtube"

ADDONS = {
    "mixcloud": MIXCLOUD_ID,
    "soundcloud": SOUNDCLOUD_ID,
    "youtube": YOUTUBE_ID,
}

MIXCLOUD = "plugin://plugin.audio.mixcloud/"
SOUNDCLOUD = "plugin://plugin.audio.soundcloud/"
YOUTUBE = "plugin://plugin.video.youtube/"


def _quote(value):
    return urllib.parse.quote(str(value or ""), safe="")


def available(kind):
    """True when the official hand-off add-on is installed.

    Checked via ``xbmcaddon.Addon`` (and AddonManager/CondVisibility as a
    fallback).  A missing add-on raises RuntimeError; a stub/foreign add-on
    returns a different id and is treated as unavailable.
    """
    addon_id = ADDONS.get(str(kind or ""))
    if not addon_id:
        return False
    try:
        addon = xbmcaddon.Addon(addon_id)
        if addon.getAddonInfo("id") == addon_id:
            return True
    except Exception:
        pass
    try:
        return bool(xbmc.getCondVisibility("System.HasAddon(%s)" % addon_id))
    except Exception:
        return False


def _split(value):
    try:
        return urllib.parse.urlsplit(str(value or ""))
    except ValueError:
        return None


def mixcloud_search(query):
    return MIXCLOUD + "?mode=30&key=cloudcast&offset=0&query=" + _quote(query)


def mixcloud_cloudcast(page_url):
    """Official Mixcloud add-on cloudcast path from a mixcloud.com page URL."""
    split = _split(page_url)
    if split is None or (split.hostname or "").lower() not in (
            "mixcloud.com", "www.mixcloud.com"):
        return ""
    path = split.path.rstrip("/")
    if not path or path.count("/") < 2:
        return ""
    return MIXCLOUD + "?mode=40&key=" + _quote(path)


def soundcloud_play(page_url):
    split = _split(page_url)
    if split is None or (split.hostname or "").lower() not in (
            "soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"):
        return ""
    return SOUNDCLOUD + "play/?url=" + _quote(page_url)


def soundcloud_search(query):
    return SOUNDCLOUD + "search/?query=" + _quote(query)


def youtube_search(query):
    return YOUTUBE + "search/?q=" + _quote(query)


def _youtube_id(page_url):
    split = _split(page_url)
    if split is None:
        return ""
    host = (split.hostname or "").lower()
    if host == "youtu.be":
        return split.path.strip("/").split("/")[0]
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        query = urllib.parse.parse_qs(split.query)
        return (query.get("v") or [""])[0]
    return ""


def youtube_play(page_url):
    video_id = _youtube_id(page_url)
    if not video_id:
        return ""
    return YOUTUBE + "play/?video_id=" + _quote(video_id)


def youtube_target(page_url, title=""):
    """Direct video play when possible, otherwise a search for the title/URL."""
    direct = youtube_play(page_url)
    if direct:
        return direct
    return youtube_search(title or page_url)


def soundcloud_target(page_url, title=""):
    direct = soundcloud_play(page_url)
    return direct or soundcloud_search(title or page_url)


def mixcloud_target(page_url, title=""):
    direct = mixcloud_cloudcast(page_url)
    return direct or mixcloud_search(title or page_url)
