# -*- coding: utf-8 -*-
"""List item construction, kept tidy so routes read like a menu definition."""

import datetime
import re

import xbmcgui
import xbmcplugin

from . import handoff, kodi, look

DEFAULT_FANART = kodi.FANART

# Estuary draws ListItem.Label2 in a narrow right-hand column (and some skins
# draw it inside the IconWall label plate).  The look-and-feel audit budgets it
# at 16 characters so it can never wrap, collide with the status icon or carry
# the row's primary identity.  Routes pass facts, never titles.
MAX_LABEL2_CHARS = 16

# Kodi display markup, e.g. [COLOR gray]...[/COLOR] or [I]...[/I].  Label text
# may carry it; the media metadata title must not, or the OSD shows the tags.
MAX_MARKUP_CHARS = 1024
_MARKUP_RE = None

_MONTH_ABBRS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_CLOCK_RE = re.compile(r"^\d{1,2}(?::\d{1,2}){1,2}$")
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


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


def fact(value):
    """Return a plain, single-line Label2 fact capped at 16 characters.

    Label2 is a secondary column: digits, a separator and a short word at most.
    Markup is stripped (a fact is not a label), whitespace is collapsed, and an
    over-long value is clipped with an ellipsis instead of wrapping or pushing
    the row's title out of shape.
    """
    text = " ".join(plain(value).split())
    if len(text) <= MAX_LABEL2_CHARS:
        return text
    return text[:MAX_LABEL2_CHARS - 1].rstrip() + "…"


def duration_fact(value):
    """Format a track duration for Label2 ("43:57", "1:02:03"), or "".

    Accepts the Archive's seconds (int/float/digit string) and already
    formatted clock strings from feeds.  Anything else is left blank so a row
    never shows a made-up fact.
    """
    if value is None or value == "":
        return ""
    text = str(value).strip()
    if _CLOCK_RE.match(text):
        return fact(text)
    try:
        total = int(float(text))
    except (TypeError, ValueError, OverflowError):
        return ""
    if total <= 0:
        return ""
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return fact("%d:%02d:%02d" % (hours, minutes, seconds))
    return fact("%d:%02d" % (minutes, seconds))


def count_fact(value):
    """Format an item count for Label2 ("1,204"), or "" when unknown."""
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return ""
    if number < 0:
        return ""
    return fact("{:,}".format(number))


def short_date(value):
    """Return a compact "31 Oct" from an ISO timestamp/date, or "".

    Used by Label2 facts where a full date would blow the 16-character budget.
    Unknown or malformed dates are blank rather than a guess.
    """
    match = _ISO_DATE_RE.match(str(value or "").strip())
    if not match:
        return ""
    try:
        month = int(match.group(2))
        day = int(match.group(3))
        datetime.date(int(match.group(1)), month, day)
    except (TypeError, ValueError, OverflowError):
        return ""
    if not 1 <= month <= 12:
        return ""
    return "%d %s" % (day, _MONTH_ABBRS[month - 1])


def size_date_fact(size_text, added):
    """Join a size and a short date within the Label2 budget.

    "48.0 MB · 31 Oct" is exactly the 16-character layout the audit measured;
    when both halves do not fit, the date is dropped and the size kept.
    """
    size_text = " ".join(plain(size_text).split())
    date_text = short_date(added)
    if size_text and date_text:
        combined = "%s · %s" % (size_text, date_text)
        if len(combined) <= MAX_LABEL2_CHARS:
            return combined
    return fact(size_text or date_text)


def add_item(handle, url, label, is_folder=True, art=None, info=None, playable=False,
             context=None, label2=None, plot=None):
    # Final safety choke point: no raw platform page may ever become a Kodi
    # list-item URL (Android would hand it to Downloader). Routes hide these
    # rows or emit plugin:// hand-offs; this guard catches any missed path.
    if handoff.platform_kind(url):
        kodi.log("ui: refusing raw platform URL for %r" % str(label)[:80], level=30)
        return None
    item = xbmcgui.ListItem(label=label)
    if label2:
        item.setLabel2(fact(label2))
    if context:
        item.addContextMenuItems(context)
    if art:
        item.setArt(art)
    if info:
        item.setInfo("music", info)
    # Estuary's ListBoxInfoVar and the poster/info panels read ListItem.Plot,
    # which Kodi 22 resolves from the *video* InfoTag only (VideoGUIInfo.cpp,
    # case LISTITEM_PLOT).  The music comment stays authoritative for the
    # music dialog/OSD; this minimal video tag is display-only and never
    # touches a resolved playback item.
    if plot:
        item.setInfo("video", kodi.video_info(plain(plot)))
    if playable:
        item.setProperty("IsPlayable", "true")
        item.setProperty("IsInternetStream", "true")
    xbmcplugin.addDirectoryItem(handle=handle, url=url, listitem=item, isFolder=is_folder)
    return item


def menu_item(handle, url, label, icon=None, fanart=None, plot=None, context=None, title=None,
              label2=None, is_folder=True, thumb=None):
    """A folder row.

    ``icon`` is the destination's 1:1 sticker; ``thumb`` is the real cover when
    one exists (an Archive pack front, a station favicon).  Kodi skins read
    different slots — IconWall reads ``poster`` first, the info panel reads
    ``thumb`` and the skinny list uses ``icon`` — so all three are set
    explicitly and the 16:9 ``fanart``/``landscape`` never gets a square image.
    """
    sticker = icon or kodi.ICON
    cover = thumb or sticker
    art = {
        "icon": sticker,
        "thumb": cover,
        "poster": cover,
        "fanart": fanart or DEFAULT_FANART,
        "landscape": fanart or DEFAULT_FANART,
    }
    info = kodi.music_info(plain(title or label), plot or plain(label),
                           mediatype="music")
    return add_item(handle, url, label, is_folder=is_folder, art=art, info=info,
                    context=context, label2=label2, plot=plot)


def info_item(handle, label, plot=None, icon=None, label2=None):
    """A read-only information row (credits/sources) that cannot leave Kodi."""
    sticker = icon or kodi.ICON
    item = xbmcgui.ListItem(label=label)
    item.setArt({
        "icon": sticker,
        "thumb": sticker,
        "poster": sticker,
        "fanart": DEFAULT_FANART,
        "landscape": DEFAULT_FANART,
    })
    item.setInfo("music", kodi.music_info(plain(label), plot or plain(label),
                                         mediatype="music"))
    if label2:
        item.setLabel2(fact(label2))
    if plot:
        item.setInfo("video", kodi.video_info(plain(plot)))
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
        "poster": kodi.ICON,
        "fanart": DEFAULT_FANART,
        "landscape": DEFAULT_FANART,
    })
    item.setInfo("music", kodi.music_info(plain(label), plot or plain(label),
                                         mediatype="music"))
    if plot:
        item.setInfo("video", kodi.video_info(plain(plot)))
    item.setProperty("IsPlayable", "false")
    xbmcplugin.addDirectoryItem(handle=handle, url="", listitem=item, isFolder=False)
    return item


def track_item(handle, url, label, thumb=None, fanart=None, plot=None, artist=None, album=None,
               duration=None, context=None, title=None, label2=None, year=None, genre=None,
               tracknumber=None, icon=None):
    cover = thumb or kodi.ROUND_FACE
    art = {
        # The playable row keeps its square cover in the art slots (Kodi's song
        # panel wants 1:1) and the brand's 16:9 fanart behind it.  ``icon`` lets
        # a route keep the source sticker (tape/radio) while the cover is real.
        "icon": icon or cover,
        "thumb": cover,
        "poster": cover,
        "fanart": fanart or DEFAULT_FANART,
        "landscape": fanart or DEFAULT_FANART,
    }
    # Kodi 22 rejects the music "plot" key; kodi.music_info keeps "comment"
    # (the music-dialog display field) and only adds plot on Kodi < 22.  The
    # visible plot is set on the video tag by add_item().
    info = kodi.music_info(plain(title or label), plot or "",
                           mediatype="music")
    if artist:
        info["artist"] = plain(artist)
    if album:
        info["album"] = plain(album)
    if duration:
        info["duration"] = duration
    if year:
        try:
            info["year"] = int(year)
        except (TypeError, ValueError):
            pass
    if genre:
        info["genre"] = plain(genre)
    if tracknumber:
        try:
            info["tracknumber"] = int(tracknumber)
        except (TypeError, ValueError):
            pass
    if label2 is None:
        # Duration is the best fact for a track; a known year is the fallback
        # when the source does not publish a length.
        label2 = duration_fact(duration)
        if not label2 and "year" in info:
            label2 = fact(str(info["year"]))
    return add_item(handle, url, label, is_folder=False, art=art, info=info,
                    playable=True, context=context, label2=label2, plot=plot)


def status_item(handle, label, plot=None, fact="empty", kind="empty", retry_url=None,
                icon=None):
    """A visible empty/error/loading line for a native directory.

    A toast is four seconds long; an empty screen is permanent.  This row is a
    status plate that survives on screen, carries the same 2026 spot colour as
    the Rave Screen's status line (``look.STATUS``), and — when a retry URL is
    given — is a real folder row, so OK re-runs the route instead of doing
    nothing.  Without a URL it is an unselectable information row.
    """
    colour, tag = look.STATUS.get(str(kind or "empty"), look.STATUS["empty"])
    prefix = "[COLOR 0xFF%s]%s[/COLOR]  " % (colour, tag)
    display = prefix + str(label or "")
    if retry_url:
        # Pass the context menu through addDirectoryItem: Kodi snapshots the
        # item at that call, so mutating it afterwards is invisible.
        return menu_item(handle, retry_url, display,
                         icon=icon or kodi.ICON,
                         plot=plot or "Press OK to try again.",
                         label2=fact or kind,
                         is_folder=True,
                         context=[("Retry", "Container.Refresh")])
    return info_item(handle, display, plot=plot or display,
                     icon=icon or kodi.ICON, label2=fact or kind)
