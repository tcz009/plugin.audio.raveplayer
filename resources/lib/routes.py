# -*- coding: utf-8 -*-
"""Routing for Rave Player 3.0.

Everything the add-on shows is described by the SECTIONS tables below, so
adding a source is a one-line change rather than another 40-line scraper.
"""

import os
import sys
import time
import urllib.parse

import xbmc
import xbmcgui
import xbmcplugin

from . import handoff, http, kodi, ui


class _LazyModule(object):
    """Lazy module attribute used to keep the warm root import path small."""

    def __init__(self, name):
        self._name = name
        self._module = None

    def _load(self):
        if self._module is None:
            import importlib

            self._module = importlib.import_module("." + self._name, __package__)
        return self._module

    def __getattr__(self, name):
        return getattr(self._load(), name)

    def __repr__(self):
        return "<lazy %s>" % self._name


def _lazy(name):
    return _LazyModule(name)


class _LazyStdlib(object):
    def __init__(self, name):
        self._name = name
        self._module = None

    def __getattr__(self, name):
        if name == "_module":
            raise AttributeError(name)
        if self._module is None:
            import importlib

            self._module = importlib.import_module(self._name)
        return getattr(self._module, name)


random = _LazyStdlib("random")

archive = _lazy("archive")
downloads = _lazy("downloads")
dnbradio = _lazy("dnbradio")
favourites = _lazy("favourites")
feeds = _lazy("feeds")
getdarker_source = _lazy("getdarker")
hardscore_source = _lazy("hardscore")
latest = _lazy("latest")
legacy = _lazy("legacy")
live = _lazy("live")
mixcloud_source = _lazy("mixcloud")
moxser_source = _lazy("moxser")
nowplaying = _lazy("nowplaying")
pirate_source = _lazy("pirate")
radio = _lazy("radio")
spinner = _lazy("spinner")
toronto_source = _lazy("toronto")

ROWS_PER_PAGE = 50
MAX_ROWS_PER_PAGE = 200
# Default to all entries a feed carries; the setting can cap deliberately.
EPISODES_PER_FEED = 5000
MAX_EPISODES_PER_FEED = 5000

# Total network time a single plugin invocation may spend before the
# remaining sources are skipped and the partial directory is shown.
ROUTE_BUDGET_SECONDS = http.ROUTE_BUDGET_SECONDS

# Routes that resolve a single stream instead of building a directory, and
# context-menu routes whose caller never expects a directory at all.
PLAYBACK_MODES = frozenset(("play", "dnb_play"))
RUNPLUGIN_MODES = frozenset(("play_all", "fav_add", "fav_remove",
                             "download_start", "download_delete"))

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
        "label": "House",
        "query": "collection:ravetapes AND house",
        "plot": "House sets. (Garage lives under UK Garage.)",
    },
    {
        "key": "pirate",
        "art": "pirate-archive.png",
        "label": "Pirate Radio",
        "query": 'collection:ravetapes AND (Kool OR Centreforce OR "Don FM")',
        "plot": "Kool FM, Centreforce and Don FM sets from the archives.",
    },
    {
        "key": "garage",
        "label": "UK Garage",
        "query": '(title:("uk garage") OR title:("garage nation") OR title:("pure garage") OR title:("speed garage")) AND mediatype:audio',
        "art": "garage.png",
        "plot": "UK garage, 90s to now.",
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
    {"key": "house", "label": "House", "tag": "house", "art": "house.png"},
    {"key": "ukg", "label": "UK Garage", "tag": "uk garage", "art": "garage.png"},
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
    if not isinstance(data, list):
        return []
    return [
        entry for entry in data
        if isinstance(entry, dict) and entry.get("id") and entry.get("query")
    ]


def _rave_catalog():
    import json
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rave-catalog.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    entries = []
    for entry in data if isinstance(data, list) else []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        try:
            count = int(entry.get("archive_count") or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0 and entry.get("archive_query"):
            entries.append({
                "name": str(entry["name"]),
                "query": entry["archive_query"],
                "count": count,
            })
    entries.sort(key=lambda item: item["count"], reverse=True)
    return entries


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
    return archive.as_text(value)


def _page_number(params):
    try:
        return max(1, int(params.get("page") or 1))
    except (TypeError, ValueError):
        return 1


def _start_index(params, count):
    try:
        start = int(params.get("start") or 0)
    except (TypeError, ValueError):
        start = 0
    return min(max(start, 0), max(count - 1, 0))


def _flag(params, name):
    """Read a boolean plugin URL parameter (``?shuffle=1``)."""
    return str(params.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _rows_per_page():
    rows = kodi.setting_int("results_per_page", ROWS_PER_PAGE)
    if rows <= 0:
        return ROWS_PER_PAGE
    return min(rows, MAX_ROWS_PER_PAGE)


def _episode_limit():
    limit = kodi.setting_int("episode_limit", EPISODES_PER_FEED)
    if limit <= 0:
        return EPISODES_PER_FEED
    return min(limit, MAX_EPISODES_PER_FEED)


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


def _favourite(kind, target, title, source=""):
    """Context-menu entry that saves an item to the favourites list."""
    return ("Add to favourites", "RunPlugin(%s)" % url_for(
        mode="fav_add", kind=kind, target=str(target), title=str(title)[:120], source=source))


def _pack_context(identifier, title):
    """Context menu for a folder that can be played as a whole."""
    return [
        ("Play all", "RunPlugin(%s)" % url_for(mode="play_all", id=identifier)),
        ("Shuffle pack", "RunPlugin(%s)" % url_for(mode="play_all", id=identifier, shuffle=1)),
        _favourite("pack", identifier, title, "Archive.org"),
    ]


def _archive_items(handle, docs):
    """Render Archive search docs as a folder list."""
    for doc in docs:
        identifier = str(doc.get("identifier") or "").strip()
        if not identifier:
            continue
        title = ui.plain(_as_text(doc.get("title")) or identifier)
        year = _year_label(doc)
        label = title if not year else "%s  [COLOR gray](%s)[/COLOR]" % (title, year)
        ui.menu_item(
            handle,
            url_for(mode="archive_item", id=identifier),
            label,
            icon=archive.thumb(identifier),
            plot=_clean_description(doc.get("description")),
            title=title,
            context=_pack_context(identifier, title),
        )


def _station_items(handle, stations, plot):
    """Render live radio stations, with a favourite and play URL each."""
    for station in stations:
        name, meta = radio.display(station)
        name = ui.plain(name)
        meta = ui.plain(meta)
        stream = _playable_url(radio.stream_url(station))
        if not stream:
            continue
        favicon = _safe_art(station.get("favicon"), None)
        label = "%s  [I]%s[/I]" % (name, meta) if meta else name
        ui.track_item(
            handle,
            url_for(mode="play", url=stream, label=name, thumb=favicon or "",
                    live=1, station=name),
            label,
            thumb=favicon,
            plot=plot,
            artist=name,
            album="Live radio",
            title=name,
            context=[_favourite("stream", stream, name, "Live radio · %s" % name)],
        )


def _page_plot(total, page, rows):
    pages = max(1, (total + rows - 1) // rows)
    return "Page %d of %d · %d items" % (page, pages, total)


# A4: bound the number of characters scanned after each "<" so hostile
# input like "<a" * 131072 cannot make the regex engine rescan to end-of-string
# (old pattern was O(n^2): 16.7 s for a 256 KiB description).
_TAG_RE = None
_DESCRIPTION_SCAN_LIMIT = 8192


def _clean_description(value):
    if not value:
        return ""
    import html
    import re

    global _TAG_RE
    if _TAG_RE is None:
        _TAG_RE = re.compile(r"<[A-Za-z/!][^>]{0,512}>")
    text = _as_text(value)[:_DESCRIPTION_SCAN_LIMIT]
    text = html.unescape(text)
    text = _TAG_RE.sub(" ", text)
    return " ".join(text.split())[:600]


def _play_tracks(tracks, identifier, start=0, shuffle=False):
    """Build and start a Kodi music playlist from Archive tracks.

    Every URL is re-validated here (A3): ``play_all`` builds the playlist
    directly, so it must not become a bypass of the ``play`` host guard.
    """
    selected = list(tracks)
    if shuffle:
        random.shuffle(selected)
    else:
        selected = selected[start:]
    if not selected:
        return False
    playable = []
    dropped = 0
    for track in selected:
        url = _playable_url(track.get("url", ""))
        if not url:
            dropped += 1
            kodi.log("play_all: skipping non-public track URL for %r" % track.get("title"),
                     level=30)
            continue
        playable.append((track, url))
    if dropped:
        kodi.notify("Skipped %d track%s with a non-public stream address."
                    % (dropped, "" if dropped == 1 else "s"))
    if not playable:
        return False
    album = identifier.replace("-", " ")
    thumb = archive.thumb(identifier)
    pack_title = archive.item_title(identifier) or album
    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    playlist.clear()
    for track, url in playable:
        details = nowplaying.parse(pack_title, track["title"])
        plotted = nowplaying.plot("From archive.org item %s" % identifier, details)
        item = xbmcgui.ListItem(path=url)
        item.setArt({"thumb": thumb, "icon": thumb, "fanart": thumb})
        info = kodi.music_info(ui.plain(track["title"]), plotted,
                               mediatype="music", album=album)
        if track.get("duration"):
            info["duration"] = track["duration"]
        item.setInfo("music", info)
        playlist.add(url, item)
    xbmc.Player().play(playlist)
    return True


# --------------------------------------------------------------------------- entry


def _failed_route(handle, mode):
    """Close a route that raised: notify, stop playback, always end the folder.

    Kodi gets no traceback and no directory is left open spinning.  Playback
    routes report a failed resolve; context-menu routes only notify; folder
    routes end with ``succeeded=False`` if the handler did not already end.
    """
    if mode in PLAYBACK_MODES:
        _fail_playback(handle, "Rave Player could not start that stream.")
        return
    kodi.notify("Rave Player hit an unexpected error — see the log.")
    if mode in RUNPLUGIN_MODES:
        return
    if not kodi.directory_ended(handle):
        kodi.end_directory(handle, "files", succeeded=False)


def dispatch(argv):
    try:
        handle = int(argv[1])
    except (IndexError, TypeError, ValueError):
        kodi.log("dispatch called without a valid plugin handle")
        return
    params = params_from_argv(argv)
    mode = params.get("mode", "root")
    handler = HANDLERS.get(mode, root)
    kodi.reset_directory(handle)
    http.begin_route(ROUTE_BUDGET_SECONDS)
    try:
        handler(handle, params)
    except Exception:
        import traceback

        kodi.log("unhandled error in mode %r:\n%s" % (mode, traceback.format_exc()),
                 level=40)
        _failed_route(handle, mode)
    else:
        if (http.route_budget_exhausted()
                and mode not in PLAYBACK_MODES and mode not in RUNPLUGIN_MODES):
            kodi.notify("Some sources were slow — showing partial results.")
    finally:
        http.end_route()


def root(handle, params):
    """Top-level menu: nine journey steps, not a source inventory.

    Each row carries its own sticker icon and 1280x720 fanart, so Estuary (and
    any skin that shows the focused item's fanart) gives every destination its
    own room. Art is declared in resources/art/; see docs/THEME-2026.md.
    """
    menu_item = ui.menu_item
    root_rows = [
        ("latest", "Latest", "rave.png", "fanart-latest.jpg",
         "Newest packs, shows and radio rips — start here."),
        ("surprise", "Surprise Me", "surprise.png", "fanart-surprise.jpg",
         "Plays a random tape pack."),
        ("packs_menu", "Tape Packs", "tapepacks.png", "fanart-tapepacks.jpg",
         "The ravetapes archive: by genre, by year, by series, by rave."),
        ("shows_menu", "Mixes & Shows", "mixes.png", "fanart-mixes.jpg",
         "Podcasts, DNB Radio, Moxser, Hardscore and GetDarker."),
        ("radio_menu", "Live Radio", "radio.png", "fanart-live.jpg",
         "Stations streaming now: Kool, Rinse and every genre tag."),
        ("curated_menu", "Curated Gems", "curated.png", "fanart-curated.jpg",
         "Pirate recordings, Rave Archive UK, the 2014 survivors."),
        ("fav_list", "Favourites", "favourites.png", "fanart-favourites.jpg",
         "The packs and shows you saved."),
        ("search", "Search the Archive", "search.png", "fanart-search.jpg",
         "Search every tape pack on archive.org."),
        ("about", "About & Sources", "about.png", "fanart-about.jpg",
         "Version, credits and every source used."),
    ]
    for mode, label, icon, fan, plot in root_rows:
        menu_item(handle, url_for(mode=mode), label,
                  icon=art(icon), fanart=art(fan), plot=plot)
    kodi.end_directory(handle, "files")


def packs_menu(handle, params):
    """Tape Packs hub: one door for the six tape-pack entry points."""
    rows = [
        ("Rave Tape Packs", url_for(mode="archive_list", key="rave", page=1), "rave.png",
         "The Rave Tapes — a curated 1990s cassette collection."),
        ("Jungle / Drum & Bass", url_for(mode="archive_list", key="jungle", page=1), "jungle.png",
         "Jungle and drum & bass sets from the rave tapes collection."),
        ("Hardcore", url_for(mode="archive_list", key="hardcore", page=1), "hardcore.png",
         "Hardcore and happy hardcore sets."),
        ("House", url_for(mode="archive_list", key="house", page=1), "house.png",
         "House sets from the archive."),
        ("UK Garage", url_for(mode="archive_list", key="garage", page=1), "garage.png",
         "UK garage, 90s to now."),
        ("Pirate Stations", url_for(mode="archive_list", key="pirate", page=1), "pirate.png",
         "Kool FM, Centreforce and Don FM sets from the archive."),
        ("All Tape Packs", url_for(mode="archive_list", key="tapepacks", page=1), "tapepacks.png",
         "Everything the Archive tags as a tape pack."),
        ("By Year", url_for(mode="years"), "tapepacks.png",
         "Browse the ravetapes collection one year at a time."),
        ("Classic Pack Series", url_for(mode="filters_menu"), "tapepacks.png",
         "Dreamscape, Fantazia, Telepathy and the other classic pack series."),
        ("By Rave & Venue", url_for(mode="rave_nights"), "rave.png",
         "Promotions, venues and pirate stations from the research catalogue."),
    ]
    hub_fanart = art("fanart-hub-packs.jpg")
    for label, url, icon, plot in rows:
        ui.menu_item(handle, url, label, icon=art(icon), fanart=hub_fanart, plot=plot)
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def shows_menu(handle, params):
    """Mixes & Shows hub: all streaming sources live behind one door."""
    rows = [
        ("Podcasts & Mixes", url_for(mode="media_menu"), "radio.png", None,
         "Current jungle, drum & bass, hardcore and rave shows — RSS feeds."),
        ("DNB Radio", url_for(mode="dnb_list"), "hardcore.png", None,
         "Recent jungle and drum & bass shows from DNBRADIO.com."),
        ("Moxser Mixes", url_for(mode="moxser"), "moxser.png", "fanart-moxser.jpg",
         "Moxser's curated dance-music mix archive — direct MP3s where available."),
        ("Hardscore.com", url_for(mode="hardscore"), "hardscore.png", "fanart-hardscore.jpg",
         "Oldskool hardcore/jungle sets, tracklists and direct MP3s."),
        ("Toronto Rave Mixtape Archive", url_for(mode="toronto"), "toronto.png",
         "fanart-toronto.jpg", "1990s Toronto rave mixtapes by genre — direct MP3s."),
    ]
    if handoff.available("mixcloud"):
        rows.append(("GetDarker (dubstep/grime)", url_for(mode="getdarker"),
                     "getdarker.png", "fanart-getdarker.jpg",
                     "GetDarker sets (RSS) plus the curated GetDarker Mixcloud archive."))
    hub_fanart = art("fanart-hub-shows.jpg")
    for label, url, icon, fan, plot in rows:
        ui.menu_item(handle, url, label, icon=art(icon),
                     fanart=art(fan) if fan else hub_fanart, plot=plot)
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def curated_menu(handle, params):
    """Curated Gems hub: hand-picked recordings and surviving sites."""
    rows = [
        ("Pirate Radio Archives", url_for(mode="pirate_menu"), "pirate-archive.png",
         "fanart-pirate-archive.jpg",
         "Curated 1990s pirate-radio recordings: Risk FM, Weekend Rush and Flava FM."),
        ("Legacy Archives (2014)", url_for(mode="legacy_menu"), "pirate.png", None,
         "The 2014 fan sites that are still standing."),
    ]
    if handoff.available("mixcloud"):
        rows.insert(1, ("Rave Archive UK",
                        url_for(mode="mixcloud_account", key="rave-archive-uk"),
                        "rave.png", None,
                        "Rave Archive UK on Mixcloud — via the Kodi Mixcloud add-on."))
    hub_fanart = art("fanart-hub-curated.jpg")
    for label, url, icon, fan, plot in rows:
        ui.menu_item(handle, url, label, icon=art(icon),
                     fanart=art(fan) if fan else hub_fanart, plot=plot)
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def radio_menu(handle, params):
    # Kool/Rinse first: each row offers its live stream plus the archive sets;
    # both were previously root rows competing with Live Radio.
    hub_fanart = art("fanart-hub-live.jpg")
    ui.menu_item(handle, url_for(mode="filter_list", key="kool"), "Kool FM",
                 icon=art("radio.png"), fanart=hub_fanart,
                 plot="Kool FM — live now, plus every Kool FM set in the archive.")
    ui.menu_item(handle, url_for(mode="filter_list", key="rinse"), "Rinse FM",
                 icon=art("radio.png"), fanart=hub_fanart,
                 plot="Rinse FM — live now, plus every Rinse FM set in the archive.")
    for section in RADIO_SECTIONS:
        ui.menu_item(
            handle,
            url_for(mode="radio_tag", key=section["key"]),
            section["label"],
            icon=art(section["art"]),
            fanart=hub_fanart,
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
    stations = radio.stations(section["tag"], limit=kodi.setting_int("radio_limit", 500))
    if not stations:
        kodi.notify("No working stations for %s right now." % section["label"])
    _station_items(handle, stations, "Live radio · %s" % section["label"])
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

    if docs and total > page * rows:
        ui.menu_item(
            handle,
            url_for(mode="archive_list", key=section["key"], page=page + 1),
            "Next page  ›",
            plot=_page_plot(total, page + 1, rows),
        )
    kodi.end_directory(handle, "files")


def archive_item(handle, params):
    identifier = params.get("id", "")
    if not identifier:
        kodi.notify("That pack is no longer listed.")
        kodi.end_directory(handle, "songs")
        return
    kodi.notify("Loading set…")
    tracks = archive.audio_files(identifier)
    if not tracks:
        kodi.notify("No audio files in that set — try another.")
    thumb = archive.thumb(identifier)
    pack_title = archive.item_title(identifier) or identifier.replace("-", " ")
    for index, track in enumerate(tracks):
        track_title = ui.plain(track["title"])
        details = nowplaying.parse(pack_title, track["title"])
        plotted = nowplaying.plot("From archive.org item %s" % identifier, details)
        ui.track_item(
            handle,
            url_for(
                mode="play",
                url=track["url"],
                label=track_title,
                thumb=thumb,
                fanart=thumb,
                plot=plotted,
            ),
            track_title,
            thumb=thumb,
            fanart=thumb,
            plot=plotted,
            album=identifier.replace("-", " "),
            duration=track.get("duration"),
            context=[
                ("Play all from here", "RunPlugin(%s)" % url_for(
                    mode="play_all", id=identifier, start=index)),
                _favourite("stream", track["url"], track_title, "Archive.org"),
            ] + _download_context(track["url"], track_title, "Archive.org"),
        )
    kodi.end_directory(handle, "songs")


def play_all(handle, params):
    """Start a whole pack, from a given track or shuffled (RunPlugin)."""
    identifier = params.get("id", "")
    if not identifier:
        kodi.notify("That pack is no longer listed.")
        return
    tracks = archive.audio_files(identifier)
    if not tracks:
        kodi.notify("No audio files in that pack.")
        return
    start = _start_index(params, len(tracks))
    if not _play_tracks(tracks, identifier, start=start, shuffle=_flag(params, "shuffle")):
        kodi.notify("Could not start that pack.")


def fav_list(handle, params):
    entries = favourites.load()
    if not entries:
        kodi.notify("No favourites yet — use the context menu on a pack or show.")
    download_rows = downloads.list_downloads()
    ui.menu_item(handle, url_for(mode="downloads_menu"),
                 "Downloads  [COLOR gray](%d)[/COLOR]" % len(download_rows),
                 icon=art("tapepacks.png"),
                 plot="Offline downloads — play from the local copy or delete.")
    for entry in entries:
        entry_key = favourites.key(entry)
        title = ui.plain(entry["title"])
        context = [("Remove from favourites", "RunPlugin(%s)" % url_for(mode="fav_remove", key=entry_key))]
        source = ui.plain(entry.get("source") or "")
        if entry["kind"] == "pack":
            ui.menu_item(handle, url_for(mode="archive_item", id=entry["target"]), title,
                         icon=archive.thumb(entry["target"]),
                         plot="Tape pack · %s" % source if source else "Tape pack",
                         context=context)
        elif entry["kind"] == "legacy_pack":
            ui.menu_item(handle, url_for(mode="legacy_pack", pack=entry["target"]), title,
                         icon=art("tapepacks.png"), plot="RaveTapePacks.com pack", context=context)
        elif entry["kind"] == "legacy_jt":
            ui.menu_item(handle, url_for(mode="legacy_jt_show", key=entry["target"]), title,
                         icon=art("jungle.png"), plot="JungleTapes.com show", context=context)
        elif entry["kind"] == "dnb":
            ui.track_item(handle, url_for(mode="dnb_play", id=entry["target"], label=title),
                          title, thumb=art("jungle.png"), plot="DNB Radio", context=context)
        else:
            kind = handoff.platform_kind(entry["target"])
            if kind:
                target = handoff.target(entry["target"], title)
                if not target:
                    continue  # missing add-on: hide, never emit a raw platform URL
                ui.menu_item(handle, target, title + "  [COLOR gray](add-on)[/COLOR]",
                             icon=art("radio.png"),
                             plot="Saved %s link — opens in the Kodi add-on." % kind,
                             context=context)
                continue
            play_params = {"url": entry["target"], "label": title}
            if "live radio" in source.lower() or live.is_live_stream(entry["target"]):
                play_params["live"] = 1
                station = source.split("·")[-1].strip() if "·" in source else ""
                if station:
                    play_params["station"] = station
            ui.track_item(handle, url_for(mode="play", **play_params),
                          title, thumb=art("radio.png"),
                          plot="Saved stream · %s" % source if source else "Saved stream",
                          context=context)
    kodi.end_directory(handle, "songs")


def fav_add(handle, params):
    entry = {
        "kind": params.get("kind", "pack"),
        "target": params.get("target", ""),
        "title": params.get("title", ""),
        "source": params.get("source", ""),
    }
    already = favourites.has(entry)
    saved = favourites.add(entry)
    if not saved:
        kodi.notify("Could not save that favourite")
    elif already:
        kodi.notify("Already in favourites")
    else:
        kodi.notify("Added to favourites")
    kodi.refresh()
    kodi.end_directory(handle, "files")


def fav_remove(handle, params):
    favourites.remove(params.get("key", ""))
    kodi.notify("Removed from favourites")
    kodi.refresh()
    kodi.end_directory(handle, "files")


def rave_nights(handle, params):
    entries = _rave_catalog()
    if not entries:
        kodi.notify("The rave catalogue is missing from the add-on.")
    for entry in entries:
        name = ui.plain(entry["name"])
        ui.menu_item(handle, url_for(mode="rave_list", key=entry["name"]),
                     "%s  [COLOR gray](%d items)[/COLOR]" % (name, entry["count"]),
                     icon=art("rave.png"),
                     plot="Archive packs and sets for %s" % name)
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def rave_list(handle, params):
    name = params.get("key", "")
    entry = next((item for item in _rave_catalog() if item["name"] == name), None)
    if not entry:
        kodi.notify("That rave is no longer in the catalogue.")
        kodi.end_directory(handle, "files")
        return
    try:
        page = max(1, int(params.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    rows = _rows_per_page()
    docs, total = archive.search(entry["query"], page=page, rows=rows)
    _archive_items(handle, docs)
    if total > page * rows:
        ui.menu_item(handle, url_for(mode="rave_list", key=name, page=page + 1),
                     "Next page  >", plot="More %s" % ui.plain(name))
    kodi.end_directory(handle, "files")


def filters_menu(handle, params):
    filters = _filters()
    if not filters:
        kodi.notify("No quick filters are configured.")
    icons = {"dj-ez": "djez.png", "garage-nation": "garage.png",
             "one-in-the-jungle": "jungle.png", "dreamscape": "tapepacks.png"}
    for entry in filters:
        if entry["id"] in ("kool", "rinse"):
            continue
        ui.menu_item(handle, url_for(mode="filter_list", key=entry["id"]), entry["name"],
                     icon=art(icons.get(entry["id"], "tapepacks.png")),
                     plot=entry.get("plot") or entry["name"])
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def filter_live(handle, params):
    entry = _filter(params.get("key", ""))
    if not entry or not entry.get("live_name"):
        kodi.notify("That live station is no longer configured.")
        kodi.end_directory(handle, "songs")
        return
    stations = radio.curated(entry["live_name"])
    if not stations:
        token = str(entry["live_name"] or "").lower()
        stations = [station for station in radio.stations_by_name(entry["live_name"], limit=200)
                    if token and token in str(station.get("name", "")).lower()]
    if not stations:
        kodi.notify("%s is not listed as live right now." % entry["name"])
    _station_items(handle, stations, "Live now · %s" % entry["name"])
    kodi.end_directory(handle, "songs")


def filter_list(handle, params):
    entry = _filter(params.get("key", ""))
    if not entry:
        kodi.notify("That filter no longer exists.")
        kodi.end_directory(handle, "files")
        return
    page = _page_number(params)
    rows = _rows_per_page()

    if page == 1 and entry.get("live_name"):
        ui.menu_item(handle, url_for(mode="filter_live", key=entry["id"]),
                     "▶ %s — live now" % entry["name"], icon=art("radio.png"),
                     plot="Live streams matching %s" % entry["live_name"])

    docs, total = archive.search(entry["query"], page=page, rows=rows)
    if not docs and page == 1:
        kodi.notify("Nothing in the archive for %s." % entry["name"])
    _archive_items(handle, docs)
    if docs and total > page * rows:
        ui.menu_item(handle, url_for(mode="filter_list", key=entry["id"], page=page + 1),
                     "Next page  ›", plot=_page_plot(total, page + 1, rows))
    kodi.end_directory(handle, "files")


def _fail_playback(handle, message):
    """Fail a resolve without touching the user's current playback.

    A playable item inside a mixed folder can make Kodi build a music playlist
    from the whole folder.  The "Latest" cascade is stopped at the source: its
    directory is typed ``files`` and unresolvable rows are dropped.  A failed
    resolve only reports failure for this plugin handle; it must not stop or
    clear a track the user is already playing (especially if a programmatic
    invocation hits an invalid play URL).
    """
    kodi.notify(message)
    xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())


def _latest_live_rows(handle):
    """Prepend the curated "on air now" rows to Latest (Kool/Rinse).

    Latest used to open with a mixed pack/show list, so row 1 was not reliably
    play-something.  These rows are direct streams, validated by the normal
    play route, and are omitted when a stream is unavailable.
    """
    count = 0
    for token, name in (("kool", "Kool FM"), ("rinse", "Rinse FM")):
        stations = radio.curated(token)
        if not stations:
            continue
        stream = radio.stream_url(stations[0])
        if not stream:
            continue
        label = "● On air now · %s" % name
        ui.track_item(
            handle,
            url_for(mode="play", url=stream, label=label,
                    live=1, station=name),
            label,
            thumb=art("radio.png"),
            plot="Live radio · %s" % name,
            artist=name,
            album="Live radio",
            title=name,
            context=[_favourite("stream", stream, label, "Live radio · %s" % name)],
        )
        count += 1
    return count


def latest_view(handle, params):
    items = latest.merge()
    live_count = _latest_live_rows(handle)
    if not items and not live_count:
        kodi.notify("Nothing came back from the sources — try again later.")
        kodi.end_directory(handle, "files")
        return

    # Resolve DNB URLs up front (concurrently, short timeout).  Kodi must never
    # receive a playable DNB row whose stream cannot resolve, or a failure makes
    # it auto-advance down the folder; unresolved rows are dropped here.
    streams = latest.resolve_dnb_streams(items)

    for item in items:
        when = item.get("when")
        stamp = when.strftime("%d %b %Y") if when else ""
        title = ui.plain(item["title"])
        source = ui.plain(item["source"])
        label = "%s  [COLOR gray](%s · %s)[/COLOR]" % (title, source, stamp) if stamp \
            else "%s  [COLOR gray](%s)[/COLOR]" % (title, source)
        if item["kind"] == "pack":
            ui.menu_item(handle, url_for(mode="archive_item", id=item["identifier"]), label,
                         icon=archive.thumb(item["identifier"]), plot="Tape pack",
                         title=title,
                         context=_pack_context(item["identifier"], title))
        elif item["kind"] == "episode":
            if handoff.platform_kind(item["url"]):
                if not _platform_item(handle, item["url"], label, title,
                                      art("radio.png"), source):
                    continue
                continue
            ui.track_item(handle, url_for(mode="play", url=item["url"], label=title), label,
                          thumb=art("radio.png"), plot=source, title=title,
                          duration=item.get("duration"),
                          context=[_favourite("stream", item["url"], title, source)])
        else:
            stream = streams.get(str(item.get("id") or ""))
            if not stream or handoff.platform_kind(stream):
                # Host unreachable / listen page changed: do not offer the row.
                continue
            ui.track_item(handle, url_for(mode="play", url=stream, label=title), label,
                          thumb=art("jungle.png"), plot="DNBRADIO.com", title=title,
                          context=[_favourite("dnb", item["id"], title, "DNB Radio")])

    # Visible terminator: folder+playable mix means Kodi should not wrap or
    # treat the whole screen as an endless playlist.
    ui.end_marker(handle, "End of list", plot="You have reached the end of Latest.")
    kodi.end_directory(handle, "files")


def surprise(handle, params):
    pack = latest.random_pack()
    if not pack or not pack.get("identifier"):
        kodi.notify("Could not pick a pack — try again.")
        kodi.end_directory(handle, "files")
        return
    kodi.notify("Random pack: %s" % str(pack["title"])[:60])
    archive_item(handle, {"id": pack["identifier"]})


def years(handle, params):
    import datetime

    this_year = datetime.date.today().year
    for year in range(this_year, 1987, -1):
        ui.menu_item(handle, url_for(mode="year_list", year=year), str(year),
                     icon=art("tapepacks.png"), plot="%s tape packs" % year)
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def year_list(handle, params):
    try:
        year = int(params.get("year", ""))
    except (TypeError, ValueError):
        kodi.notify("That year is not valid.")
        kodi.end_directory(handle, "files")
        return
    page = _page_number(params)
    rows = _rows_per_page()
    docs, total = archive.search(latest.year_query(year), page=page, rows=rows)
    if not docs and page == 1:
        kodi.notify("Nothing in the archive for %s." % year)
    _archive_items(handle, docs)
    if docs and total > page * rows:
        ui.menu_item(handle, url_for(mode="year_list", year=year, page=page + 1),
                     "More from %s" % year, plot=_page_plot(total, page + 1, rows))
    kodi.end_directory(handle, "files")


def media_menu(handle, params):
    entries = feeds.registry()
    if not entries:
        kodi.notify("No podcast feeds are configured.")
        kodi.end_directory(handle, "files")
        return
    limit = _episode_limit()
    hide_empty = kodi.setting_bool("hide_empty_feeds", False)
    shown = 0
    for entry, episodes in feeds.episodes_many(entries, limit=limit):
        if hide_empty and not episodes:
            continue
        shown += 1
        ui.menu_item(
            handle,
            url_for(mode="feed", key=entry["id"]),
            "%s  [COLOR gray](%d episodes)[/COLOR]" % (entry["name"], len(episodes)),
            icon=art("radio.png"),
            plot=entry.get("plot") or entry["name"],
        )
    if not shown:
        kodi.notify("None of the podcast feeds returned episodes.")
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def feed(handle, params):
    entry = feeds.feed(params.get("key", ""))
    if not entry:
        kodi.notify("That feed is no longer configured.")
        kodi.end_directory(handle, "songs")
        return
    episodes = feeds.episodes(entry["id"], limit=_episode_limit())
    if not episodes:
        kodi.notify("%s did not return any episodes." % entry["name"])
    for episode in episodes:
        title = ui.plain(episode["title"])
        label = title
        if episode.get("published"):
            label = "%s  [COLOR gray](%s)[/COLOR]" % (label, ui.plain(episode["published"])[:16])
        if handoff.platform_kind(episode["url"]):
            if not _platform_item(handle, episode["url"], label, title,
                                  art("radio.png"),
                                  episode.get("description") or entry.get("plot") or ""):
                continue
            continue
        ui.track_item(
            handle,
            url_for(mode="play", url=episode["url"], label=title),
            label,
            thumb=art("radio.png"),
            plot=episode.get("description") or entry.get("plot") or "",
            album=entry["name"],
            title=title,
            duration=episode.get("duration"),
            context=[_favourite("stream", episode["url"], title, entry["name"])],
        )
    kodi.end_directory(handle, "songs")


def dnb_list(handle, params):
    shows = dnbradio.mixes()
    if not shows:
        kodi.notify("DNBRADIO.com did not answer — try again later.")
    for show in shows:
        title = ui.plain(show["title"])
        date = ui.plain(show["date"])
        label = "%s  [COLOR gray](%s)[/COLOR]" % (title, date) if date else title
        ui.track_item(
            handle,
            url_for(mode="dnb_play", id=show["id"], label=title),
            label,
            thumb=art("jungle.png"),
            plot="DNBRADIO.com · %s" % date if date else "DNBRADIO.com",
            album="DNBRADIO.com",
            title=title,
            context=[_favourite("dnb", show["id"], title, "DNB Radio")],
        )
    kodi.end_directory(handle, "songs")


def dnb_play(handle, params):
    mix_id = params.get("id", "")
    label = params.get("label", "DNBRADIO")
    tuning = _start_tuning_spinner(label)
    url = ""
    try:
        if mix_id:
            try:
                url = dnbradio.stream_url(mix_id)
            except Exception as exc:  # never let a scraper error cascade playback
                kodi.log("DNB resolve failed for mix %s (%s)" % (mix_id, exc), level=30)
                url = ""
        if _tuning_aborted(handle, tuning):
            return
    finally:
        _close_tuning_spinner(tuning)
    if not url:
        _fail_playback(handle, "Could not resolve that DNBRADIO mix.")
        return
    play(handle, {"url": url, "label": label,
                  "thumb": params.get("thumb") or kodi.ICON})


def legacy_menu(handle, params):
    menu = [
        ("RaveTapePacks.com", "legacy_packs", "tapepacks.png", "Full tape packs, hotlink-protected MP3s."),
        ("JungleTapes.com", "legacy_jt", "jungle.png", "Toronto jungle & drum n bass radio shows from cassette."),
        ("Toronto Rave Mixtape Archive", "legacy_toronto", "toronto.png", "Rave mixtapes from Toronto, 1990s."),
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
        name = ui.plain(show["name"])
        ui.menu_item(
            handle,
            url_for(mode="legacy_jt_show", key=show["key"]),
            name,
            icon=art("jungle.png"),
            plot="JungleTapes.com · Toronto jungle radio",
            context=[_favourite("legacy_jt", show["key"], name, "JungleTapes.com")],
        )
    kodi.end_directory(handle, "files")


def legacy_jt_show(handle, params):
    key = params.get("key", "")
    if not key:
        kodi.notify("No show selected.")
        kodi.end_directory(handle, "songs")
        return
    tracks = legacy.jungle_tracks(key)
    if not tracks:
        kodi.notify("No audio on that show.")
    for track in tracks:
        stream = _playable_url(track["url"])
        if not stream:
            continue
        name = ui.plain(track["name"])
        ui.track_item(
            handle,
            url_for(mode="play", url=stream, label=name, thumb=art("jungle.png")),
            name,
            thumb=art("jungle.png"),
            plot="JungleTapes.com · %s" % ui.plain(key.replace("-", " ")),
            context=[_favourite("stream", stream, name, "JungleTapes.com")],
        )
    kodi.end_directory(handle, "songs")


def legacy_toronto(handle, params):
    tracks = legacy.toronto_tracks()
    if not tracks:
        kodi.notify("Toronto archive did not answer — try again later.")
    for track in tracks:
        stream = _playable_url(track["url"])
        if not stream:
            continue
        name = ui.plain(track["name"])
        ui.track_item(
            handle,
            url_for(mode="play", url=stream, label=name, thumb=art("toronto.png")),
            name,
            thumb=art("toronto.png"),
            plot="Toronto Rave Mixtape Archive",
            context=[_favourite("stream", stream, name, "Toronto Rave Archive")],
        )
    kodi.end_directory(handle, "songs")


def toronto(handle, params):
    """Toronto archive genre folders (jungle, house, studio, x-static, extras)."""
    rows = toronto_source.genres()
    if not rows:
        kodi.notify("Toronto archive did not answer — try again later.")
    hub_fanart = art("fanart-toronto.jpg")
    for row in rows:
        label = ui.plain(row["label"])
        ui.menu_item(
            handle,
            url_for(mode="toronto_genre", genre=row["genre"]),
            label,
            icon=art("toronto.png"),
            fanart=hub_fanart,
            plot="Toronto Rave Mixtape Archive · %s" % label,
        )
    ui.menu_item(handle, url_for(mode="shows_menu"), "Back")
    kodi.end_directory(handle, "files")


def toronto_genre(handle, params):
    """Direct MP3 rows for one Toronto genre page."""
    slug = params.get("genre", "")
    tracks = toronto_source.tracks(slug)
    genre_label = next((label for name, label in toronto_source.GENRES if name == slug), slug)
    if not tracks:
        kodi.notify("No Toronto mixtapes on that page right now.")
    for track in tracks:
        stream = _playable_url(track["url"])
        if not stream:
            continue
        name = ui.plain(track["name"])
        plot = "Toronto Rave Mixtape Archive · %s" % ui.plain(genre_label)
        context = [_favourite("stream", stream, name, "Toronto Rave Archive")]
        context.extend(_download_context(stream, name, "Toronto Rave Mixtape Archive"))
        ui.track_item(
            handle,
            url_for(mode="play", url=stream, label=name, thumb=art("toronto.png")),
            name,
            thumb=art("toronto.png"),
            plot=plot,
            album=ui.plain(genre_label),
            context=context,
        )
    ui.menu_item(handle, url_for(mode="toronto"), "Back")
    kodi.end_directory(handle, "songs")


def legacy_packs(handle, params):
    entries = legacy.packs()
    if not entries:
        kodi.notify("RaveTapePacks.com did not answer — try again later.")
    for entry in entries:
        name = ui.plain(entry["name"])
        ui.menu_item(
            handle,
            url_for(mode="legacy_pack", pack=entry["key"]),
            "%s  [COLOR gray](%d tape%s)[/COLOR]"
            % (name, len(entry["tracks"]), "" if len(entry["tracks"]) == 1 else "s"),
            icon=art("tapepacks.png"),
            plot="RaveTapePacks.com · %d tapes" % len(entry["tracks"]),
            title=name,
            context=[_favourite("legacy_pack", entry["key"], name, "RaveTapePacks.com")],
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
        url = _playable_url(legacy.playable(track["url"]))
        if not url:
            continue
        name = ui.plain(track["name"])
        ui.track_item(
            handle,
            url_for(mode="play", url=url, label=name, thumb=art("tapepacks.png")),
            name,
            thumb=art("tapepacks.png"),
            plot="RaveTapePacks.com · %s" % ui.plain(entry["name"]),
            album=ui.plain(entry["name"]),
            context=[_favourite("stream", url, name, "RaveTapePacks.com")],
        )
    kodi.end_directory(handle, "songs")


# --------------------------------------------------------------- new sources


def _handoff_target(url, title):
    """Return (addon kind, plugin:// URL) for a platform link, or None.

    Rules: only official Kodi add-ons are used; if the relevant add-on is not
    installed the link is not offered at all (no dead rows, no browser, no raw
    platform URL).  ``handoff.platform_kind`` is the single classifier.
    """
    kind = handoff.platform_kind(url)
    if not kind:
        return None
    target = handoff.target(url, title)
    if not target:
        return None
    return kind, target


def _download_context(url, title, source):
    """Context-menu Download action for eligible direct audio files only."""
    if not downloads.eligible(url, source, check_host=False):
        return []
    return [(
        "Download",
        "RunPlugin(%s)" % url_for(mode="download_start", url=url,
                                  title=title, source=source),
    )]


def _platform_item(handle, url, label, title, icon, plot):
    """Render a platform page as an add-on hand-off row, or omit it.

    Returns True when a row was emitted.  If the add-on is absent the row is
    omitted entirely (the single availability gate lives in ``handoff.target``).
    """
    target = handoff.target(url, title or label)
    if not target:
        return False
    ui.menu_item(handle, target, label, icon=icon, plot=plot)
    return True


_HANDOFF_LABELS = {
    "youtube": "YouTube",
    "mixcloud": "Mixcloud",
}


def _handoff_link_items(handle, links, title, icon, plot):
    """Render supported third-party links as Kodi add-on hand-off rows.

    Returns how many rows were shown.  Missing add-ons hide their links.
    """
    shown = 0
    for url in links or []:
        found = _handoff_target(url, title)
        if not found:
            continue
        kind, target = found
        ui.menu_item(
            handle,
            target,
            "Open in %s" % _HANDOFF_LABELS[kind],
            icon=icon,
            plot=plot,
        )
        shown += 1
    return shown


def moxser(handle, params):
    rows = moxser_source.mixes(limit=moxser_source.MAX_MIXES)
    if not rows:
        kodi.notify("Moxser did not answer — try again later.")
    for row in rows:
        title = ui.plain(row["title"])
        label = title
        if row.get("date"):
            label += "  [COLOR gray](%s)[/COLOR]" % ui.plain(row["date"])
        flyer = _safe_art(row.get("flyer"), art("rave.png"))
        ui.menu_item(
            handle,
            url_for(mode="moxser_mix", page=row["page_url"], label=row["title"],
                    flyer=row.get("flyer", "")),
            label,
            icon=flyer,
            plot="Moxser.com · direct MP3 when available",
            title=title,
        )
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def moxser_mix(handle, params):
    page = params.get("page", "")
    details = moxser_source.mix(page)
    if not details:
        kodi.notify("That Moxser mix page did not load.")
        kodi.end_directory(handle, "songs")
        return
    title = ui.plain(details["title"])
    flyer = _safe_art(params.get("flyer") or details.get("flyer"), art("rave.png"))
    plotted = "Moxser.com"
    if details.get("date"):
        plotted += " · %s" % details["date"]
    if details.get("mp3_url"):
        ui.track_item(
            handle,
            url_for(mode="play", url=details["mp3_url"], label=title,
                    thumb=flyer, fanart=flyer),
            title,
            thumb=flyer,
            fanart=flyer,
            plot=plotted,
            title=title,
            context=[_favourite("stream", details["mp3_url"], title, "Moxser.com")]
            + _download_context(details["mp3_url"], title, "Moxser.com"),
        )
    else:
        kodi.notify("No direct MP3 on that Moxser page — nothing to play in Kodi.")
    kodi.end_directory(handle, "files")


def hardscore(handle, params):
    rows = hardscore_source.items(limit=hardscore_source.MAX_ITEMS)
    if not rows:
        kodi.notify("Hardscore did not answer — try again later.")
    for row in rows:
        title = ui.plain(row["title"])
        date = row.get("date") or ""
        label = title + ("  [COLOR gray](%s)[/COLOR]" % ui.plain(date) if date else "")
        media = [url for url in row["media_urls"] if _playable_url(url)]
        if media:
            ui.track_item(
                handle,
                url_for(mode="play", url=media[0], label=title),
                label,
                thumb=art("hardcore.png"),
                plot=row.get("description") or "Hardscore.com",
                title=title,
                context=[
                    _favourite("stream", media[0], title, "Hardscore.com"),
                ] + _download_context(media[0], title, "Hardscore.com"),
            )
        elif row.get("page_url"):
            ui.menu_item(
                handle,
                url_for(mode="hardscore_event", page=row["page_url"], label=row["title"]),
                label + "  [COLOR gray](post)[/COLOR]",
                icon=art("hardcore.png"),
                plot=row.get("description") or "Hardscore.com post",
                title=title,
            )
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def hardscore_event(handle, params):
    page = params.get("page", "")
    details = hardscore_source.page(page)
    if not details:
        kodi.notify("That Hardscore post could not be loaded.")
        kodi.end_directory(handle, "files")
        return
    title = ui.plain(details["title"])
    for url in [u for u in details["media_urls"] if _playable_url(u)]:
        ui.track_item(
            handle, url_for(mode="play", url=url, label=title), title,
            thumb=art("hardcore.png"), plot="Hardscore.com",
            title=title,
            context=[_favourite("stream", url, title, "Hardscore.com")]
            + _download_context(url, title, "Hardscore.com"),
        )
    shown = _handoff_link_items(handle, details["links"], title,
                                art("hardcore.png"),
                                "Hardscore.com link — hand-off to a Kodi add-on.")
    if not details["media_urls"] and not shown:
        kodi.notify("No in-Kodi media on that Hardscore post.")
    kodi.end_directory(handle, "files")


def getdarker(handle, params):
    if not handoff.available("mixcloud"):
        kodi.notify("GetDarker needs the Kodi Mixcloud add-on — row hidden.")
        kodi.end_directory(handle, "files")
        return
    rows = getdarker_source.items(limit=hardscore_source.MAX_ITEMS)
    ui.menu_item(
        handle,
        handoff.mixcloud_search("GetDarker"),
        "GetDarker on Mixcloud",
        icon=art("jungle.png"),
        plot="Open the GetDarker cloudcasts in the Kodi Mixcloud add-on.",
    )
    if not rows:
        kodi.notify("GetDarker RSS did not answer — showing the Mixcloud archive only.")
    for row in rows:
        title = ui.plain(row["title"])
        date = row.get("date") or ""
        label = title + ("  [COLOR gray](%s)[/COLOR]" % ui.plain(date) if date else "")
        ui.menu_item(
            handle,
            url_for(mode="getdarker_page", page=row["page_url"], label=row["title"]),
            label,
            icon=art("jungle.png"),
            plot="GetDarker · RSS set page",
            title=title,
        )
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def getdarker_page(handle, params):
    page = params.get("page", "")
    details = getdarker_source.page(page)
    if not details:
        kodi.notify("That GetDarker page could not be loaded.")
        kodi.end_directory(handle, "files")
        return
    title = ui.plain(details["title"])
    for url in [u for u in details["media_urls"] if _playable_url(u)]:
        ui.track_item(handle, url_for(mode="play", url=url, label=title), title,
                      thumb=art("jungle.png"), plot="GetDarker",
                      title=title,
                      context=[_favourite("stream", url, title, "GetDarker")])
    shown = _handoff_link_items(handle, details["links"], title, art("jungle.png"),
                                "GetDarker link — hand-off to a Kodi add-on.")
    if not details["media_urls"] and not shown:
        kodi.notify("No in-Kodi media on that GetDarker page.")
    kodi.end_directory(handle, "files")


def mixcloud_account(handle, params):
    source = mixcloud_source.source(params.get("key", ""))
    if not source:
        kodi.notify("That Mixcloud source is not configured.")
        kodi.end_directory(handle, "files")
        return
    if not handoff.available("mixcloud"):
        kodi.notify("%s needs the Kodi Mixcloud add-on — row hidden." % source["name"])
        kodi.end_directory(handle, "files")
        return
    rows = mixcloud_source.cloudcasts(source["account"], limit=mixcloud_source.MAX_CLOUDS)
    if not rows:
        kodi.notify("%s did not return any cloudcasts." % source["name"])
    for row in rows:
        title = ui.plain(row["title"])
        target = handoff.mixcloud_cloudcast(row["url"]) or handoff.mixcloud_search(title)
        if not target:
            continue
        created = row.get("created") or ""
        label = title + ("  [COLOR gray](%s)[/COLOR]" % ui.plain(created[:10])
                         if created else "")
        ui.menu_item(
            handle,
            target,
            label,
            icon=_safe_art(row.get("thumb"), art("radio.png")),
            plot="%s · opens in the Kodi Mixcloud add-on." % source["name"],
            title=title,
        )
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def pirate_menu(handle, params):
    groups = pirate_source.stations()
    if not groups:
        kodi.notify("The Pirate Radio Archives data is missing from the add-on.")
    shown = 0
    for group in groups:
        # Policy: only direct in-add-on streams are rows; metadata-only
        # recordings (no stream, no official add-on) stay in the data file but
        # are not shown as dead rows.
        playable = [entry for entry in group["entries"] if entry["stream_url"]]
        if not playable:
            continue
        shown += 1
        ui.menu_item(
            handle,
            url_for(mode="pirate_station", station=group["station"]),
            "%s  [COLOR gray](%d recording%s)[/COLOR]"
            % (ui.plain(group["station"]), len(playable),
               "" if len(playable) == 1 else "s"),
            icon=art("pirate-archive.png"),
            plot="Curated 1990s pirate-radio archive.",
        )
    if not shown:
        kodi.notify("No Pirate Radio Archives recordings have a direct in-Kodi stream.")
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def pirate_station(handle, params):
    group = pirate_source.station(params.get("station", ""))
    if not group:
        kodi.notify("That station is no longer in the archive.")
        kodi.end_directory(handle, "files")
        return
    playable = [entry for entry in group["entries"] if entry["stream_url"]]
    if not playable:
        kodi.notify("That station has no direct in-Kodi recordings.")
        kodi.end_directory(handle, "files")
        return
    for entry in playable:
        stream = _playable_url(entry["stream_url"])
        if not stream:
            continue
        title = ui.plain(entry["title"])
        djs = ", ".join(entry["djs"])
        year = entry["year"] if entry["year"] is not None else "year unknown"
        plot = "%s · %s · %s" % (group["station"], year, djs or "DJs unknown")
        if entry["credit"]:
            plot += " · Credit: %s" % entry["credit"]
        if entry["note"]:
            plot += " · %s" % entry["note"]
        ui.track_item(
            handle,
            url_for(mode="play", url=stream, label=title),
            title,
            thumb=art("pirate-archive.png"),
            plot=plot,
            album=group["station"],
            title=title,
            context=[_favourite("stream", stream, title, group["station"])]
            + _download_context(stream, title, "Pirate Radio Archives"),
        )
    ui.menu_item(handle, url_for(mode="pirate_menu"), "Back")
    kodi.end_directory(handle, "files")


def downloads_menu(handle, params):
    rows = downloads.list_downloads()
    if not rows:
        kodi.notify("No downloads yet — use Download in an item's context menu.")
    for row in rows:
        label = ui.plain(row["title"])
        if row.get("exists"):
            label += "  [COLOR gray](%s)[/COLOR]" % downloads.format_size(row["size"])
            ui.track_item(
                handle,
                row["path"],
                label,
                thumb=art("tapepacks.png"),
                plot="Downloaded · %s · %s" % (row["source"], row["added"][:10]),
                album="Downloads",
                title=row["title"],
                context=[("Delete download", "RunPlugin(%s)" % url_for(
                    mode="download_delete", key=row["key"]))],
            )
        else:
            ui.menu_item(
                handle,
                url_for(mode="downloads_menu"),
                label + "  [COLOR gray](missing)[/COLOR]",
                icon=art("tapepacks.png"),
                plot="The file is missing — delete the entry or download it again.",
                context=[("Delete download", "RunPlugin(%s)" % url_for(
                    mode="download_delete", key=row["key"]))],
            )
    ui.menu_item(handle, url_for(mode="fav_list"), "Back")
    kodi.end_directory(handle, "files")


def download_start(handle, params):
    url = params.get("url", "")
    title = params.get("title", "Rave Player download")
    source = params.get("source", "")
    plan = downloads.plan(url, title, source)
    if not plan.get("allowed"):
        kodi.notify(plan.get("reason") or "Download not available.")
        return
    text = "%s\nSize: %s\nFree space: %s" % (
        ui.plain(title), downloads.format_size(plan["size"]),
        downloads.format_size(plan["free"]))
    heading = "Replace download?" if plan.get("existing") else "Download?"
    if not kodi.dialog().yesno(heading, text):
        return
    overlay = None
    dialog = None
    if kodi.setting_bool("spinner_overlay", False):
        try:
            candidate = spinner.SpinnerWindow()
            if candidate.open():
                overlay = candidate
        except Exception as exc:
            kodi.log("spinner overlay unavailable (%s)" % exc, level=30)
    if overlay is None:
        dialog = xbmcgui.DialogProgress()
        dialog.create("Rave Player", "Downloading…")
    started = time.monotonic()

    def update(done, total):
        try:
            percent = int((done * 100) / total) if total else 0
            if overlay is not None:
                overlay.update(done, total, time.monotonic() - started, title)
            elif dialog is not None:
                dialog.update(max(0, min(percent, 100)), message="Downloading…")
        except Exception:
            pass

    def cancelled():
        if overlay is not None:
            return overlay.iscanceled()
        return bool(dialog.iscanceled()) if dialog is not None else False

    try:
        result = downloads.download(plan, progress=update, cancelled=cancelled)
    finally:
        if overlay is not None:
            overlay.close()
        if dialog is not None:
            dialog.close()
    if result.get("ok"):
        kodi.notify("Downloaded: %s" % ui.plain(title)[:60])
    elif "cancel" in str(result.get("reason") or "").lower():
        kodi.notify("Download cancelled.")
    else:
        kodi.notify("Download failed: %s" % str(result.get("reason") or "unknown")[:120])


def download_delete(handle, params):
    key = params.get("key", "")
    if not key:
        return
    if not kodi.dialog().yesno("Delete download?", "Remove this file and its metadata?"):
        return
    if downloads.delete(key):
        kodi.notify("Download deleted")
    else:
        kodi.notify("That download was not found")
    kodi.refresh()


def search(handle, params):
    query = str(params.get("q") or "").strip()
    if not query:
        query = str(kodi.dialog().input("Search the Internet Archive", type=xbmcgui.INPUT_ALPHANUM) or "").strip()
    if not query:
        kodi.end_directory(handle, "files")
        return
    page = _page_number(params)
    rows = _rows_per_page()
    docs, total = archive.search(query, page=page, rows=rows)
    if not docs and page == 1:
        kodi.notify("No results for “%s”." % query)
    _archive_items(handle, docs)
    if docs and total > page * rows:
        ui.menu_item(
            handle,
            url_for(mode="search", q=query, page=page + 1),
            "Next page  ›",
            plot=_page_plot(total, page + 1, rows),
        )
    kodi.end_directory(handle, "files")


def about(handle, params):
    """Credits and every source used; read-only rows that stay in Kodi."""
    rows = [
        ("Rave Player %s — GPL-3.0" % kodi.ADDON_VERSION,
         "about.png", "Version %s · GNU General Public License v3.0 · "
         "github.com/tcz009/plugin.audio.raveplayer." % kodi.ADDON_VERSION),
        ("Source: Internet Archive (archive.org)",
         "rave.png", "Tape packs, rave tapes and audio collections."),
        ("Source: Mixcloud", "radio.png",
         "Rave Archive UK and GetDarker cloudcasts — via the Kodi Mixcloud add-on."),
        ("Source: SoundCloud", "radio.png",
         "Web version only — SoundCloud is not part of the Kodi build; "
         "there is no Kodi source row or hand-off."),
        ("Source: radio-browser.info", "radio.png", "Live radio station directory."),
        ("Source: Moxser.com", "rave.png",
         "Curated dance-music mix archive and direct MP3s."),
        ("Source: Hardscore.com", "hardcore.png",
         "Oldskool hardcore/jungle archive and direct MP3s."),
        ("Source: DNB Radio", "hardcore.png",
         "Jungle and drum & bass shows and direct MP3s from dnbradio.com."),
        ("Source: GetDarker.com", "jungle.png",
         "Dubstep/garage/underground sets (Kodi Mixcloud add-on)."),
        ("Source: Podcast & mix RSS feeds", "radio.png",
         "Jungle Lab, Viper, Toro and the other podcast feeds."),
        ("Source: Pirate Radio Archives", "pirate-archive.png",
         "Curated Risk FM, Weekend Rush and Flava FM recordings; "
         "credits are shown on each recording."),
        ("Live radio: Kool FM & Rinse FM", "radio.png",
         "Kool London and Rinse FM live streams (via admin.stream.rinse.fm)."),
        ("Source: RaveTapePacks.com", "tapepacks.png",
         "Full tape packs; playback URLs carry the required Referer header."),
        ("Source: JungleTapes.com", "jungle.png",
         "Toronto jungle/drum & bass radio shows from the site sitemap."),
        ("Source: Toronto Rave Mixtape Archive", "toronto.png",
         "1990s Toronto rave mixtapes by genre (jungle, house, studio, X-Static) — direct MP3s."),
    ]
    for label, icon, plot in rows:
        ui.info_item(handle, label, plot=plot, icon=art(icon))
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def _playable_url(value):
    """Return the URL only when it is a playable, public http(s) stream.

    Delegates to :func:`http.safe_stream_url` (scheme + resolved-host guard);
    Kodi ``|Header=…`` suffixes are preserved.  Platform page URLs
    (Mixcloud/YouTube/SoundCloud) are never direct media: reject them so a
    stale favourite/deep link cannot resolve to a raw page URL either.
    """
    if handoff.platform_kind(value):
        return ""
    return http.safe_stream_url(value)


def _safe_art(value, fallback=None):
    """Only public http(s) art URLs are accepted; anything else falls back.

    Third-party favicons/thumb parameters otherwise reach Kodi's image loader
    unchanged (A11).  Local add-on paths are replaced by the caller's fallback
    icon, which is the same image in the normal case.
    """
    text = str(value or "").strip()
    if not text:
        return fallback
    if text.lower().startswith(("http://", "https://")):
        return text if _playable_url(text) else fallback
    return fallback


def _resolve_live_player_url(stream, station):
    """Re-resolve a live station to its current direct URL, best effort."""
    try:
        for candidate in radio.curated(station or stream):
            url = radio.stream_url(candidate)
            if url:
                return url
    except Exception:  # noqa: BLE001 - keep last known direct URL
        pass
    return stream


def _start_tuning_spinner(label):
    """Start the delayed stream spinner when the separate toggle is on."""
    if not kodi.setting_bool("spinner_tuning", True):
        return None
    try:
        tuning = spinner.TuningSpinner(label)
        tuning.start()
        return tuning
    except Exception as exc:  # noqa: BLE001 - never block playback
        kodi.log("tuning spinner unavailable (%s)" % exc.__class__.__name__, level=30)
        return None


def _close_tuning_spinner(tuning):
    if tuning is not None:
        try:
            tuning.close()
        except Exception:
            pass


def _tuning_aborted(handle, tuning):
    """Return True (and fail the resolve) if timeout/Back cancelled tuning."""
    if tuning is None:
        return False
    if getattr(tuning, "expired", False):
        _fail_playback(handle, "Stream taking too long — check your connection.")
        return True
    if getattr(tuning, "cancelled", lambda: False)():
        _fail_playback(handle, "Cancelled.")
        return True
    return False


def play(handle, params):
    label = params.get("label", "Rave Player")
    tuning = _start_tuning_spinner(params.get("station") or label)
    try:
        stream = _playable_url(params.get("url", ""))
        thumb = _safe_art(params.get("thumb"), kodi.ICON)
        fanart = _safe_art(params.get("fanart"), "")
        plotted = params.get("plot") or ""
        if not stream:
            _fail_playback(handle,
                           "That stream address is not playable "
                           "(private, loopback or unresolved host).")
            return
        is_live = _flag(params, "live") or live.is_live_stream(stream)
        station = live.station_name(stream, params.get("station") or label) if is_live else ""
        display_label = station or label
        item = xbmcgui.ListItem(path=stream)
        art = {"thumb": thumb, "icon": thumb}
        if fanart:
            art["fanart"] = fanart
        item.setArt(art)
        info = kodi.music_info(ui.plain(display_label), plotted, mediatype="music")
        if is_live:
            info["artist"] = station
            info["album"] = "Live radio"
        item.setInfo("music", info)
        item.setProperty("IsPlayable", "true")
        if is_live:
            # Do not resolve a playlist file: PAPlayer cannot decode local .m3u
            # through setResolvedUrl.  Start a finite direct-URL playlist instead;
            # Kodi advances only when the current stream drops and a user Stop
            # ends it immediately (no add-on loop/watchdog).
            item.setProperty("IsLiveStream", "true")
            try:
                urls = live.reconnect_urls(
                    stream, station,
                    resolver=lambda name: _resolve_live_player_url(stream, name),
                )
                if urls:
                    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
                    playlist.clear()
                    for url in urls:
                        url = live.playback_url(url)
                        if not url:
                            continue
                        entry = xbmcgui.ListItem(path=url)
                        entry.setArt(art)
                        entry.setInfo("music", dict(info))
                        entry.setProperty("IsPlayable", "true")
                        entry.setProperty("IsLiveStream", "true")
                        playlist.add(url, entry)
                    if _tuning_aborted(handle, tuning):
                        return
                    _close_tuning_spinner(tuning)
                    xbmc.Player().play(playlist)
                    return
            except Exception as exc:  # noqa: BLE001 - direct stream fallback
                kodi.log("live reconnect playlist unavailable (%s); direct stream"
                         % exc.__class__.__name__, level=30)
            direct = live.playback_url(stream) if is_live else ""
            if direct:
                item.setPath(direct)
        if _tuning_aborted(handle, tuning):
            return
        _close_tuning_spinner(tuning)
        xbmcplugin.setResolvedUrl(handle, True, item)
    finally:
        _close_tuning_spinner(tuning)


HANDLERS = {
    "root": root,
    "packs_menu": packs_menu,
    "shows_menu": shows_menu,
    "curated_menu": curated_menu,
    "radio_menu": radio_menu,
    "radio_tag": radio_tag,
    "archive_list": archive_list,
    "archive_item": archive_item,
    "play_all": play_all,
    "fav_list": fav_list,
    "fav_add": fav_add,
    "fav_remove": fav_remove,
    "rave_nights": rave_nights,
    "rave_list": rave_list,
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
    "moxser": moxser,
    "moxser_mix": moxser_mix,
    "hardscore": hardscore,
    "hardscore_event": hardscore_event,
    "getdarker": getdarker,
    "getdarker_page": getdarker_page,
    "mixcloud_account": mixcloud_account,
    "downloads_menu": downloads_menu,
    "download_start": download_start,
    "download_delete": download_delete,
    "pirate_menu": pirate_menu,
    "pirate_station": pirate_station,
    "legacy_menu": legacy_menu,
    "legacy_jt": legacy_jt,
    "legacy_jt_show": legacy_jt_show,
    "legacy_toronto": legacy_toronto,
    "toronto": toronto,
    "toronto_genre": toronto_genre,
    "legacy_packs": legacy_packs,
    "legacy_pack": legacy_pack,
    "search": search,
    "about": about,
    "play": play,
}
