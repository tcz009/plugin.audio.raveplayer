# -*- coding: utf-8 -*-
"""Routing for Rave Player 3.0.

Everything the add-on shows is described by the SECTIONS tables below, so
adding a source is a one-line change rather than another 40-line scraper.
"""

import sys
import urllib.parse

import xbmcgui
import xbmcplugin

import os

from . import archive, kodi, radio, ui

ROWS_PER_PAGE = 50

# Archive.org phrase queries. These are broad on purpose: the Archive's
# full-text index is what keeps this add-on alive when fan sites disappear.
ARCHIVE_SECTIONS = [
    {
        "key": "rave",
        "art": "rave.png",
        "label": "Rave Tape Packs",
        "query": "collection:ravetapes AND mediatype:audio",
        "plot": "The Rave Tapes — a curated 1990s cassette collection, 724 packs.",
    },
    {
        "key": "jungle",
        "art": "jungle.png",
        "label": "Jungle / Drum & Bass",
        "query": 'collection:ravetapes AND (jungle OR "drum and bass")',
        "plot": "Jungle and drum & bass sets from the rave tapes collection.",
    },
    {
        "key": "hardcore",
        "art": "hardcore.png",
        "label": "Hardcore",
        "query": "collection:ravetapes AND hardcore",
        "plot": "Hardcore and happy hardcore sets.",
    },
    {
        "key": "house",
        "art": "house.png",
        "label": "House & Garage",
        "query": "collection:ravetapes AND (garage OR house)",
        "plot": "House, garage and speed garage sets.",
    },
    {
        "key": "pirate",
        "art": "pirate.png",
        "label": "Pirate Radio",
        "query": 'collection:ravetapes AND (Kool OR Centreforce OR "Don FM")',
        "plot": "Kool FM, Centreforce and Don FM sets from the archives.",
    },
    {
        "key": "tapepacks",
        "art": "tapepacks.png",
        "label": "All Tape Packs",
        "query": '(jungle OR "drum and bass" OR hardcore OR house) AND "tape pack"',
        "plot": "Everything the Archive tags as a tape pack, across genres.",
    },
]

RADIO_SECTIONS = [
    {"key": "oldskool", "label": "Oldskool & Rave", "tag": "oldskool", "art": "radio.png"},
    {"key": "jungle", "label": "Jungle", "tag": "jungle", "art": "jungle.png"},
    {"key": "dnb", "label": "Drum & Bass", "tag": "drum and bass", "art": "jungle.png"},
    {"key": "hardcore", "label": "Hardcore", "tag": "hardcore", "art": "hardcore.png"},
    {"key": "garage", "label": "House & Garage", "tag": "garage", "art": "house.png"},
    {"key": "breakbeat", "label": "Breakbeat", "tag": "breakbeat", "art": "rave.png"},
]

def art(name):
    return os.path.join(kodi.ADDON_PATH, "resources", "art", name)


ARCHIVE_BY_KEY = dict((section["key"], section) for section in ARCHIVE_SECTIONS)
RADIO_BY_KEY = dict((section["key"], section) for section in RADIO_SECTIONS)


# --------------------------------------------------------------------------- urls


def _base_url():
    base = sys.argv[0]
    return base.split("?", 1)[0]


def url_for(**params):
    return _base_url() + "?" + urllib.parse.urlencode(params)


def params_from_argv(argv):
    if len(argv) < 3 or not argv[2]:
        return {}
    query = argv[2]
    if query.startswith("?"):
        query = query[1:]
    return dict((key, values[0]) for key, values in urllib.parse.parse_qs(query).items())


# --------------------------------------------------------------------------- entry


def dispatch(argv):
    handle = int(argv[1])
    params = params_from_argv(argv)
    mode = params.get("mode", "root")
    handler = HANDLERS.get(mode, root)
    handler(handle, params)


def root(handle, params):
    menu_item = ui.menu_item

    action = url_for(mode="radio_menu")
    menu_item(handle, action, "Live Radio", icon=art("radio.png"),
              plot="Streaming pirate, oldskool and rave radio right now.")

    for section in ARCHIVE_SECTIONS:
        menu_item(
            handle,
            url_for(mode="archive_list", key=section["key"], page=1),
            section["label"],
            icon=art(section["art"]),
            plot=section["plot"],
        )

    menu_item(handle, url_for(mode="search"), "Search the Archive", icon=art("search.png"), plot="Search every tape pack on archive.org.")
    menu_item(handle, url_for(mode="about"), "About Rave Player", icon=art("about.png"), plot="Credits, sources and version.")

    kodi.end_directory(handle, "files")


def radio_menu(handle, params):
    for section in RADIO_SECTIONS:
        ui.menu_item(
            handle,
            url_for(mode="radio_tag", key=section["key"]),
            section["label"],
            icon=art(section["art"]),
            plot="Live stations tagged %s" % section["tag"],
        )
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def radio_tag(handle, params):
    section = RADIO_BY_KEY.get(params.get("key", ""))
    if not section:
        kodi.notify("That radio section no longer exists.")
        kodi.end_directory(handle, "files")
        return
    stations = radio.stations(section["tag"], limit=kodi.setting_int("radio_limit", 100))
    if not stations:
        kodi.notify("No working stations for %s right now." % section["label"])
    for station in stations:
        name, meta = radio.display(station)
        label = name if not meta else "%s  [I]%s[/I]" % (name, meta)
        ui.track_item(
            handle,
            url_for(mode="play", url=radio.stream_url(station), label=name, thumb=station.get("favicon") or ""),
            label,
            thumb=station.get("favicon") or None,
            plot="Live radio · %s" % (station.get("country") or ""),
            artist=meta or None,
        )
    kodi.end_directory(handle, "songs")


def archive_list(handle, params):
    section = ARCHIVE_BY_KEY.get(params.get("key", ""))
    if not section:
        kodi.notify("That section no longer exists.")
        kodi.end_directory(handle, "files")
        return
    try:
        page = max(1, int(params.get("page", 1)))
    except ValueError:
        page = 1
    rows = kodi.setting_int("results_per_page", ROWS_PER_PAGE)
    docs, total = archive.search(section["query"], page=page, rows=rows)

    if not docs and page == 1:
        kodi.notify("Nothing came back from the Archive. Try another section.")

    for doc in docs:
        identifier = doc.get("identifier", "")
        title = doc.get("title") or identifier
        year = doc.get("year") or str(doc.get("date", ""))[:4]
        label = title if not year else "%s  [COLOR gray](%s)[/COLOR]" % (title, year)
        ui.menu_item(
            handle,
            url_for(mode="archive_item", id=identifier),
            label,
            icon=archive.thumb(identifier),
            plot=_clean_description(doc.get("description")),
        )

    if total > page * rows:
        ui.menu_item(
            handle,
            url_for(mode="archive_list", key=section["key"], page=page + 1),
            "Next page  ›",
            plot="Page %d of %d" % (page + 1, (total + rows - 1) // rows),
        )
    kodi.end_directory(handle, "files")


def archive_item(handle, params):
    identifier = params.get("id", "")
    if not identifier:
        kodi.end_directory(handle, "songs")
        return
    tracks = archive.audio_files(identifier)
    if not tracks:
        kodi.notify("No audio files in that item.")
    for track in tracks:
        ui.track_item(
            handle,
            url_for(mode="play", url=track["url"], label=track["title"], thumb=archive.thumb(identifier)),
            track["title"],
            thumb=archive.thumb(identifier),
            plot="From archive.org item %s" % identifier,
            album=identifier.replace("-", " "),
        )
    kodi.end_directory(handle, "songs")


def search(handle, params):
    query = kodi.dialog().input("Search the Internet Archive", type=xbmcgui.INPUT_ALPHANUM)
    if not query:
        kodi.end_directory(handle, "files")
        return
    docs, total = archive.search(query, page=1, rows=ROWS_PER_PAGE)
    if not docs:
        kodi.notify("No results for “%s”." % query)
    for doc in docs:
        identifier = doc.get("identifier", "")
        ui.menu_item(
            handle,
            url_for(mode="archive_item", id=identifier),
            doc.get("title") or identifier,
            icon=archive.thumb(identifier),
            plot=_clean_description(doc.get("description")),
        )
    kodi.end_directory(handle, "files")


def about(handle, params):
    ui.menu_item(
        handle,
        url_for(mode="root"),
        "Rave Player %s — back for 2026" % kodi.ADDON_VERSION,
        plot="Rebuilt from the 2014 original. Sources: archive.org and radio-browser.info. No content is hosted by this add-on.",
    )
    kodi.end_directory(handle, "files")


def play(handle, params):
    stream = params.get("url", "")
    label = params.get("label", "Rave Player")
    thumb = params.get("thumb") or kodi.ICON
    if not stream:
        kodi.notify("Nothing to play for that item.")
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return
    item = xbmcgui.ListItem(path=stream)
    item.setArt({"thumb": thumb, "icon": thumb})
    item.setInfo("music", {"title": label})
    item.setProperty("IsPlayable", "true")
    xbmcplugin.setResolvedUrl(handle, True, item)


def _clean_description(value):
    if not value:
        return ""
    if isinstance(value, list):
        value = " ".join(str(part) for part in value)
    text = " ".join(str(value).split())
    return text[:600]


HANDLERS = {
    "root": root,
    "radio_menu": radio_menu,
    "radio_tag": radio_tag,
    "archive_list": archive_list,
    "archive_item": archive_item,
    "search": search,
    "about": about,
    "play": play,
}
