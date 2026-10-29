# -*- coding: utf-8 -*-
"""Routing for Rave Player 3.0.

Everything the add-on shows is described by the SECTIONS tables below, so
adding a source is a one-line change rather than another 40-line scraper.
"""

import html
import os
import re
import sys
import urllib.parse

import xbmcgui
import xbmcplugin

from . import archive, dnbradio, favourites, feeds, kodi, latest, legacy, radio, ui

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


def _filters():
    import json
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "filters.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    return [entry for entry in data if isinstance(entry, dict) and entry.get("id") and entry.get("query")]


def _filter(key):
    return next((entry for entry in _filters() if entry["id"] == key), None)


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


# --------------------------------------------------------------------------- helpers


def _as_text(value):
    if isinstance(value, (list, tuple)):
        value = " ".join(str(part) for part in value)
    return " ".join(str(value or "").split())


def _page_number(params):
    try:
        return max(1, int(params.get("page") or 1))
    except (TypeError, ValueError):
        return 1


def _rows_per_page():
    rows = kodi.setting_int("results_per_page", ROWS_PER_PAGE)
    return rows if rows > 0 else ROWS_PER_PAGE


def _year_label(doc):
    """Return a year for the list label, tolerating lists and missing dates."""
    value = doc.get("year")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    text = str(value or "").strip()
    if not text:
        date = doc.get("date")
        if isinstance(date, (list, tuple)):
            date = date[0] if date else ""
        text = str(date or "").strip()[:4]
    return "" if text.lower() in ("none", "null") else text


def _archive_items(handle, docs):
    """Render Archive search docs as a folder list."""
    for doc in docs:
        identifier = str(doc.get("identifier") or "").strip()
        if not identifier:
            continue
        title = _as_text(doc.get("title")) or identifier
        year = _year_label(doc)
        label = title if not year else "%s  [COLOR gray](%s)[/COLOR]" % (title, year)
        ui.menu_item(
            handle,
            url_for(mode="archive_item", id=identifier),
            label,
            icon=archive.thumb(identifier),
            plot=_clean_description(doc.get("description")),
            context=[("Add to favourites", "RunPlugin(%s)" % url_for(
                mode="fav_add", kind="pack", target=identifier, title=title[:120]))],
        )


def _clean_description(value):
    if not value:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(part) for part in value)
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())[:600]


# --------------------------------------------------------------------------- entry


def dispatch(argv):
    try:
        handle = int(argv[1])
    except (IndexError, TypeError, ValueError):
        kodi.log("dispatch called without a valid plugin handle")
        return
    params = params_from_argv(argv)
    mode = params.get("mode", "root")
    handler = HANDLERS.get(mode, root)
    handler(handle, params)


def root(handle, params):
    menu_item = ui.menu_item

    menu_item(handle, url_for(mode="latest"), "Latest",
              icon=art("rave.png"),
              plot="Newest of everything: podcasts, tape packs and DNB Radio shows.")
    menu_item(handle, url_for(mode="surprise"), "Surprise me",
              icon=art("tapepacks.png"),
              plot="Drop into a random rave tape pack.")

    menu_item(handle, url_for(mode="filter_list", key="kool"), "Kool FM",
              icon=art("radio.png"),
              plot="Kool FM: the station live now, plus every Kool FM set in the archive.")
    menu_item(handle, url_for(mode="filters_menu"), "Quick Filters",
              icon=art("tapepacks.png"),
              plot="Jump straight to the classic pack series.")

    menu_item(handle, url_for(mode="fav_list"), "Favourites",
              icon=art("rave.png"),
              plot="The packs and shows you saved.")

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

    menu_item(
        handle,
        url_for(mode="media_menu"),
        "Podcasts & Mixes",
        icon=art("radio.png"),
        plot="Current jungle, drum & bass, hardcore and rave shows — RSS feeds.",
    )
    menu_item(
        handle,
        url_for(mode="dnb_list"),
        "DNB Radio Archive",
        icon=art("jungle.png"),
        plot="Recent jungle and drum & bass shows from DNBRADIO.com.",
    )

    menu_item(
        handle,
        url_for(mode="legacy_menu"),
        "Legacy Sites",
        icon=art("tapepacks.png"),
        plot="The fan sites from 2014 that are still standing.",
    )

    menu_item(
        handle,
        url_for(mode="years"),
        "Tape Packs by Year",
        icon=art("tapepacks.png"),
        plot="Browse the ravetapes collection one year at a time.",
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
    page = _page_number(params)
    rows = _rows_per_page()
    docs, total = archive.search(section["query"], page=page, rows=rows)

    if not docs and page == 1:
        kodi.notify("Nothing came back from the Archive. Try another section.")

    _archive_items(handle, docs)

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


def fav_list(handle, params):
    entries = favourites.load()
    if not entries:
        kodi.notify("No favourites yet — use the context menu on a pack or show.")
    for entry in entries:
        entry_key = favourites.key(entry)
        context = [("Remove from favourites", "RunPlugin(%s)" % url_for(mode="fav_remove", key=entry_key))]
        if entry["kind"] == "pack":
            ui.menu_item(handle, url_for(mode="archive_item", id=entry["target"]), entry["title"],
                         icon=archive.thumb(entry["target"]), plot="Tape pack · %s" % entry.get("source", ""),
                         context=context)
        elif entry["kind"] == "dnb":
            ui.track_item(handle, url_for(mode="dnb_play", id=entry["target"], label=entry["title"]),
                          entry["title"], thumb=art("jungle.png"), plot="DNB Radio", context=context)
        else:
            ui.track_item(handle, url_for(mode="play", url=entry["target"], label=entry["title"]),
                          entry["title"], thumb=art("radio.png"), plot="Show", context=context)
    kodi.end_directory(handle, "songs")


def fav_add(handle, params):
    saved = favourites.add({
        "kind": params.get("kind", "pack"),
        "target": params.get("target", ""),
        "title": params.get("title", ""),
    })
    kodi.notify("Added to favourites" if saved else "Could not save that favourite")
    kodi.end_directory(handle, "files")


def fav_remove(handle, params):
    favourites.remove(params.get("key", ""))
    kodi.notify("Removed from favourites")
    kodi.end_directory(handle, "files")


def filters_menu(handle, params):
    for entry in _filters():
        if entry["id"] == "kool":
            continue
        ui.menu_item(handle, url_for(mode="filter_list", key=entry["id"]), entry["name"],
                     icon=art("tapepacks.png"), plot=entry.get("plot") or entry["name"])
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def filter_live(handle, params):
    entry = _filter(params.get("key", ""))
    if not entry or not entry.get("live_name"):
        kodi.end_directory(handle, "songs")
        return
    stations = radio.stations_by_name(entry["live_name"], limit=20)
    if not stations:
        kodi.notify("%s is not listed as live right now." % entry["name"])
    for station in stations:
        name, meta = radio.display(station)
        ui.track_item(
            handle,
            url_for(mode="play", url=radio.stream_url(station), label=name, thumb=station.get("favicon") or ""),
            "%s  [I]%s[/I]" % (name, meta) if meta else name,
            thumb=station.get("favicon") or None,
            plot="Live now · %s" % entry["name"],
            artist=meta or None,
        )
    kodi.end_directory(handle, "songs")


def filter_list(handle, params):
    entry = _filter(params.get("key", ""))
    if not entry:
        kodi.notify("That filter no longer exists.")
        kodi.end_directory(handle, "files")
        return
    try:
        page = max(1, int(params.get("page", 1)))
    except ValueError:
        page = 1
    rows = kodi.setting_int("results_per_page", ROWS_PER_PAGE)

    if page == 1 and entry.get("live_name"):
        ui.menu_item(handle, url_for(mode="filter_live", key=entry["id"]),
                     "▶ %s — live now" % entry["name"], icon=art("radio.png"),
                     plot="Live streams matching %s" % entry["live_name"])

    docs, total = archive.search(entry["query"], page=page, rows=rows)
    if not docs and page == 1:
        kodi.notify("Nothing in the archive for %s." % entry["name"])
    _archive_items(handle, docs)
    if total > page * rows:
        ui.menu_item(handle, url_for(mode="filter_list", key=entry["id"], page=page + 1),
                     "Next page  ›", plot="More %s" % entry["name"])
    kodi.end_directory(handle, "files")


def latest_view(handle, params):
    items = latest.merge()
    if not items:
        kodi.notify("Nothing came back from the sources — try again later.")
    for item in items:
        when = item.get("when")
        stamp = when.strftime("%d %b %Y") if when else ""
        label = "%s  [COLOR gray](%s · %s)[/COLOR]" % (item["title"], item["source"], stamp) if stamp \
            else "%s  [COLOR gray](%s)[/COLOR]" % (item["title"], item["source"])
        if item["kind"] == "pack":
            ui.menu_item(handle, url_for(mode="archive_item", id=item["identifier"]), label,
                         icon=archive.thumb(item["identifier"]), plot="Tape pack")
        elif item["kind"] == "episode":
            ui.track_item(handle, url_for(mode="play", url=item["url"], label=item["title"]), label,
                          thumb=art("radio.png"), plot=item["source"], duration=item.get("duration"))
        else:
            ui.track_item(handle, url_for(mode="dnb_play", id=item["id"], label=item["title"]), label,
                          thumb=art("jungle.png"), plot="DNBRADIO.com")
    kodi.end_directory(handle, "songs")


def surprise(handle, params):
    pack = latest.random_pack()
    if not pack or not pack.get("identifier"):
        kodi.notify("Could not pick a pack — try again.")
        kodi.end_directory(handle, "files")
        return
    kodi.notify("Random pack: %s" % pack["title"][:60])
    archive_item(handle, {"id": pack["identifier"]})


def years(handle, params):
    this_year = __import__("datetime").date.today().year
    for year in range(this_year, 1987, -1):
        ui.menu_item(handle, url_for(mode="year_list", year=year), str(year),
                     icon=art("tapepacks.png"), plot="%s tape packs" % year)
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def year_list(handle, params):
    try:
        year = int(params.get("year", ""))
    except ValueError:
        kodi.notify("That year is not valid.")
        kodi.end_directory(handle, "files")
        return
    rows = kodi.setting_int("results_per_page", ROWS_PER_PAGE)
    docs, total = archive.search(latest.year_query(year), rows=rows)
    if not docs:
        kodi.notify("Nothing in the archive for %s." % year)
    _archive_items(handle, docs)
    if total > rows:
        ui.menu_item(handle, url_for(mode="year_list", year=year), "More from %s" % year,
                     plot="Refine with Search the Archive for now")
    kodi.end_directory(handle, "files")


def media_menu(handle, params):
    for entry in feeds.registry():
        count = len(feeds.episodes(entry["id"], limit=200))
        ui.menu_item(
            handle,
            url_for(mode="feed", key=entry["id"]),
            "%s  [COLOR gray](%d episodes)[/COLOR]" % (entry["name"], count),
            icon=art("radio.png"),
            plot=entry.get("plot") or entry["name"],
        )
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def feed(handle, params):
    entry = feeds.feed(params.get("key", ""))
    if not entry:
        kodi.notify("That feed is no longer configured.")
        kodi.end_directory(handle, "songs")
        return
    episodes = feeds.episodes(entry["id"])
    if not episodes:
        kodi.notify("%s did not return any episodes." % entry["name"])
    for episode in episodes:
        label = episode["title"]
        if episode.get("published"):
            label = "%s  [COLOR gray](%s)[/COLOR]" % (label, episode["published"][:16])
        ui.track_item(
            handle,
            url_for(mode="play", url=episode["url"], label=episode["title"]),
            label,
            thumb=art("radio.png"),
            plot=episode.get("description") or entry.get("plot") or "",
            album=entry["name"],
            duration=episode.get("duration"),
            context=[("Add to favourites", "RunPlugin(%s)" % url_for(
                mode="fav_add", kind="stream", target=episode["url"], title=episode["title"][:120]))],
        )
    kodi.end_directory(handle, "songs")


def dnb_list(handle, params):
    shows = dnbradio.mixes()
    if not shows:
        kodi.notify("DNBRADIO.com did not answer — try again later.")
    for show in shows:
        ui.track_item(
            handle,
            url_for(mode="dnb_play", id=show["id"], label=show["title"]),
            "%s  [COLOR gray](%s)[/COLOR]" % (show["title"], show["date"]) if show["date"] else show["title"],
            thumb=art("jungle.png"),
            plot="DNBRADIO.com · %s" % show["date"],
            album="DNBRADIO.com",
        )
    kodi.end_directory(handle, "songs")


def dnb_play(handle, params):
    mix_id = params.get("id", "")
    url = dnbradio.stream_url(mix_id) if mix_id else ""
    if not url:
        kodi.notify("Could not resolve that DNBRADIO mix.")
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return
    play(handle, {"url": url, "label": params.get("label", "DNBRADIO"),
                  "thumb": params.get("thumb") or kodi.ICON})


def legacy_menu(handle, params):
    menu = [
        ("RaveTapePacks.com", "legacy_packs", "tapepacks.png", "Full tape packs, hotlink-protected MP3s."),
        ("JungleTapes.com", "legacy_jt", "jungle.png", "Toronto jungle & drum n bass radio shows from cassette."),
        ("Toronto Rave Mixtape Archive", "legacy_toronto", "rave.png", "Rave mixtapes from Toronto, 1990s."),
    ]
    for label, mode, icon, plot in menu:
        ui.menu_item(handle, url_for(mode=mode), label, icon=art(icon), plot=plot)
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def legacy_jt(handle, params):
    shows = legacy.jungle_shows()
    if not shows:
        kodi.notify("Jungle Tapes did not answer — try again later.")
    for show in shows:
        ui.menu_item(
            handle,
            url_for(mode="legacy_jt_show", key=show["key"]),
            show["name"],
            icon=art("jungle.png"),
            plot="JungleTapes.com · Toronto jungle radio",
        )
    kodi.end_directory(handle, "files")


def legacy_jt_show(handle, params):
    key = params.get("key", "")
    if not key:
        kodi.notify("No audio on that show.")
        kodi.end_directory(handle, "songs")
        return
    tracks = legacy.jungle_tracks(key)
    if not tracks:
        kodi.notify("No audio on that show.")
    for track in tracks:
        ui.track_item(
            handle,
            url_for(mode="play", url=track["url"], label=track["name"], thumb=art("jungle.png")),
            track["name"],
            thumb=art("jungle.png"),
            plot="JungleTapes.com · %s" % key.replace("-", " "),
        )
    kodi.end_directory(handle, "songs")


def legacy_toronto(handle, params):
    tracks = legacy.toronto_tracks()
    if not tracks:
        kodi.notify("Toronto archive did not answer — try again later.")
    for track in tracks:
        ui.track_item(
            handle,
            url_for(mode="play", url=track["url"], label=track["name"], thumb=art("rave.png")),
            track["name"],
            thumb=art("rave.png"),
            plot="Toronto Rave Mixtape Archive",
        )
    kodi.end_directory(handle, "songs")


def legacy_packs(handle, params):
    entries = legacy.packs()
    if not entries:
        kodi.notify("RaveTapePacks.com did not answer — try again later.")
    for entry in entries:
        ui.menu_item(
            handle,
            url_for(mode="legacy_pack", pack=entry["key"]),
            "%s  [COLOR gray](%d tape%s)[/COLOR]"
            % (entry["name"], len(entry["tracks"]), "" if len(entry["tracks"]) == 1 else "s"),
            icon=art("tapepacks.png"),
            plot="RaveTapePacks.com · %d tapes" % len(entry["tracks"]),
        )
    kodi.end_directory(handle, "files")


def legacy_pack(handle, params):
    key = params.get("pack", "")
    if not key:
        kodi.notify("That pack is no longer listed.")
        kodi.end_directory(handle, "songs")
        return
    entry = next((item for item in legacy.packs() if item["key"] == key), None)
    if not entry:
        kodi.notify("That pack is no longer listed.")
        kodi.end_directory(handle, "songs")
        return
    for track in entry["tracks"]:
        ui.track_item(
            handle,
            url_for(mode="play", url=legacy.playable(track["url"]), label=track["name"],
                    thumb=art("tapepacks.png")),
            track["name"],
            thumb=art("tapepacks.png"),
            plot="RaveTapePacks.com · %s" % entry["name"],
            album=entry["name"],
        )
    kodi.end_directory(handle, "songs")


def search(handle, params):
    query = kodi.dialog().input("Search the Internet Archive", type=xbmcgui.INPUT_ALPHANUM)
    if not query:
        kodi.end_directory(handle, "files")
        return
    docs, _total = archive.search(query, page=1, rows=ROWS_PER_PAGE)
    if not docs:
        kodi.notify("No results for “%s”." % query)
    _archive_items(handle, docs)
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


HANDLERS = {
    "root": root,
    "radio_menu": radio_menu,
    "radio_tag": radio_tag,
    "archive_list": archive_list,
    "archive_item": archive_item,
    "fav_list": fav_list,
    "fav_add": fav_add,
    "fav_remove": fav_remove,
    "filters_menu": filters_menu,
    "filter_list": filter_list,
    "filter_live": filter_live,
    "latest": latest_view,
    "surprise": surprise,
    "years": years,
    "year_list": year_list,
    "media_menu": media_menu,
    "feed": feed,
    "dnb_list": dnb_list,
    "dnb_play": dnb_play,
    "legacy_menu": legacy_menu,
    "legacy_jt": legacy_jt,
    "legacy_jt_show": legacy_jt_show,
    "legacy_toronto": legacy_toronto,
    "legacy_packs": legacy_packs,
    "legacy_pack": legacy_pack,
    "search": search,
    "about": about,
    "play": play,
}
