# -*- coding: utf-8 -*-
"""Routing for Rave Player 3.0.

Everything the add-on shows is described by the SECTIONS tables below, so
adding a source is a one-line change rather than another 40-line scraper.
"""

import os
import re
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
rtp_bridge = _lazy("rtp_bridge")
spinner = _lazy("spinner")
toronto_source = _lazy("toronto")

ROWS_PER_PAGE = 50
MAX_ROWS_PER_PAGE = 200
# JungleTapes has 300+ sitemap shows; page the directory instead of sending one
# 310-row list (and keep the page size aligned with the web build).
JT_SHOWS_PER_PAGE = 50
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
        "key": "jungle",
        "art": "jungle.png",
        "label": "Jungle",
        "query": 'collection:ravetapes AND (jungle OR "jungle techno" OR ragga) AND mediatype:audio',
        "plot": "Jungle sets from the rave tapes collection.",
    },
    {
        "key": "drum-and-bass",
        "art": "dnb.png",
        "label": "Drum & Bass",
        "query": 'collection:ravetapes AND ("drum and bass" OR dnb) AND mediatype:audio',
        "plot": "Drum & bass sets from the rave tapes collection.",
    },
    {
        "key": "hardcore",
        "art": "hardcore.png",
        "label": "Hardcore",
        "query": 'collection:ravetapes AND hardcore AND mediatype:audio',
        "plot": "1990–93 breakbeat hardcore sets.",
    },
    {
        "key": "happy-hardcore",
        "art": "happy-hardcore.png",
        "label": "Happy Hardcore",
        "query": 'collection:ravetapes AND ("happy hardcore" OR happyhardcore) AND mediatype:audio',
        "plot": "Happy hardcore sets, 1993–98.",
    },
    {
        "key": "house",
        "art": "house.png",
        "label": "House",
        "query": "collection:ravetapes AND house AND mediatype:audio",
        "plot": "House sets. (Garage lives under UK Garage.)",
    },
    {
        "key": "pirate",
        "art": "pirate-radio.png",
        "label": "Pirate Radio",
        "query": 'collection:ravetapes AND (Kool OR Centreforce OR "Don FM") AND mediatype:audio',
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
        "art": "tapepacks-all.png",
        "label": "Every Pack",
        "query": '(jungle OR "drum and bass" OR hardcore OR house) AND "tape pack"',
        "plot": "Archive mixtapes — everything the Archive tags as a tape pack.",
    },
]
RADIO_SECTIONS = [
    {"key": "hardcore", "label": "Hardcore", "tag": "hardcore", "art": "radio-hardcore.png"},
    {"key": "jungle", "label": "Jungle", "tag": "jungle", "art": "radio-jungle.png"},
    {"key": "drum-and-bass", "label": "Drum & Bass", "tag": "drum and bass", "art": "radio-dnb.png"},
    {"key": "house", "label": "House", "tag": "house", "art": "radio-house.png"},
    {"key": "uk-garage", "label": "UK Garage", "tag": "uk garage", "art": "radio-uk-garage.png"},
    {"key": "dubstep-grime", "label": "Dubstep & Grime", "tag": "dubstep", "art": "radio-dubstep-grime.png"},
]
# Menu artwork: one distinct sticker per navigation row.  The duplicate-art
# test (test/test_theme_art.py) asserts these files are all different, so a new
# menu row must add a new key here rather than borrowing a neighbour's tile.
# Leaf rows (tracks, episodes, archive results, individual years/raves/stations)
# intentionally reuse their parent category sticker; those are the only allowed
# repeats and are listed in the test's shared-art exceptions.
MENU_ART = {
    # root
    "screen": "screen.png",
    "latest": "rave.png",
    "surprise": "surprise.png",
    "packs": "tapepacks.png",
    "shows": "mixes.png",
    "radio": "radio.png",
    "favourites": "favourites.png",
    "search": "search.png",
    "about": "about.png",
    # tape-pack genres and entry points
    "pack_rave": "rave-tapes.png",
    "pack_jungle": "jungle.png",
    "pack_hardcore": "hardcore.png",
    "pack_house": "house.png",
    "pack_garage": "garage.png",
    "pack_pirate": "pirate-stations.png",
    "pack_year": "years.png",
    "pack_series": "series.png",
    "pack_raves": "rave-nights.png",
    "pack_toronto": "toronto.png",
    "pack_jungletapes": "jungletapes.png",
    "pack_ravetapepacks": "ravetapepacks.png",
    "pack_every": "tapepacks-all.png",
    # pirate radio door and children
    "pirate": "pirate-radio.png",
    # shows and sources
    "shows_podcasts": "podcasts.png",
    "shows_dnb": "dnb.png",
    "shows_moxser": "moxser.png",
    "shows_hardscore": "hardscore.png",
    "shows_getdarker": "getdarker.png",
    # curated gems
    "curated_pirate": "pirate-archive.png",
    "curated_legacy": "legacy.png",
    # live radio stations and genre tags
    "radio_kool": "kool.png",
    "radio_rinse": "rinse.png",
    "radio_oldskool": "oldskool.png",
    "radio_jungle": "radio-jungle.png",
    "radio_dnb": "radio-dnb.png",
    "radio_hardcore": "radio-hardcore.png",
    "radio_house": "radio-house.png",
    "radio_uk_garage": "radio-uk-garage.png",
    "radio_breakbeat": "radio-breakbeat.png",
    "radio_centreforce": "radio-centreforce.png",
    "radio_dubstep_grime": "radio-dubstep-grime.png",
    # legacy sites
    # shared utility rows
    "downloads": "downloads.png",
}

# Classic pack series are distinct rows too, so each filter gets its own tile.
FILTER_ART = {
    "dreamscape": "dreamscape.png",
    "helter-skelter": "helter-skelter.png",
    "fantazia": "fantazia.png",
    "one-nation": "one-nation.png",
    "centreforce": "centreforce.png",
    "don-fm": "don-fm.png",
    "slammin-vinyl": "slammin-vinyl.png",
    "one-in-the-jungle": "one-in-the-jungle.png",
    "jungle-fever": "jungle-fever.png",
    "roast": "roast.png",
    "telepathy": "telepathy.png",
    "world-dance": "world-dance.png",
    "dj-ez": "djez.png",
    "garage-nation": "garage-nation.png",
}


_DATA_CACHE = {}


def _cached_json(name):
    """Parse one data file once per process, keyed by its mtime.

    ``filters.json`` / ``rave-catalog.json`` are package data that change only
    with a release, but the hub routes re-read and re-parsed them on every
    directory build.  The mtime check keeps a test (or a hot-swapped file)
    correct while the common path skips the disk read.
    """
    import json

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), name)
    try:
        modified = os.path.getmtime(path)
    except OSError:
        return []
    cached = _DATA_CACHE.get(name)
    if cached is not None and cached[0] == modified:
        return cached[1]
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        data = []
    _DATA_CACHE[name] = (modified, data)
    return data


def _filters():
    return [
        entry for entry in _cached_json("filters.json")
        if isinstance(entry, dict) and entry.get("id") and entry.get("query")
    ]


def _rave_slug(name):
    """Stable id for a rave, identical to the web build's slug."""
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")


def _rave_catalog():
    """Every researched rave with Archive packs and/or Mixcloud sets.

    Mirrors the web catalogue: alphabetical order, mixcloud-only rows
    included, and a stable slug as the route id (names still resolve, for old
    links). The parsed JSON is cached and invalidated by mtime.
    """
    entries = []
    for entry in _cached_json("rave-catalog.json"):
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        try:
            archive_count = int(entry.get("archive_count") or 0)
        except (TypeError, ValueError):
            archive_count = 0
        try:
            mixcloud_count = int(entry.get("mixcloud_count") or 0)
        except (TypeError, ValueError):
            mixcloud_count = 0
        archive_query = entry.get("archive_query") or ""
        mixcloud_query = entry.get("mixcloud_query") or ""
        if archive_count > 0 and not archive_query:
            archive_count = 0
        if mixcloud_count > 0 and not mixcloud_query:
            mixcloud_count = 0
        if not archive_count and not mixcloud_count:
            continue
        name = str(entry["name"])
        entries.append({
            "name": name,
            "slug": _rave_slug(name),
            "query": archive_query,
            "archive_query": archive_query,
            "mixcloud_query": mixcloud_query,
            "count": archive_count,
            "mixcloud_count": mixcloud_count,
        })
    entries.sort(key=lambda item: item["name"].lower())
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
        # The label already carries the year; the right-hand column carries the
        # event/venue parsed from the title (the audit's "year/venue where
        # known" fact).  Unknown titles leave Label2 empty rather than guess.
        venue = nowplaying.parse(title).get("venue") or ""
        ui.menu_item(
            handle,
            url_for(mode="archive_item", id=identifier),
            label,
            # 2026 semantics: a tape pack is a tape.  The cassette sticker is
            # the row icon; the pack front is cover/poster, so IconWall and the
            # info panel still show real art at the right ratio.
            icon=art(MENU_ART["packs"]),
            thumb=archive.thumb(identifier),
            plot=_clean_description(doc.get("description")),
            title=title,
            label2=venue or "pack",
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
        sticker = art(MENU_ART["radio"])
        label = "%s  [I]%s[/I]" % (name, meta) if meta else name
        ui.track_item(
            handle,
            url_for(mode="play", url=stream, label=name, thumb=favicon or sticker,
                    live=1, station=name),
            label,
            thumb=favicon or sticker,
            icon=sticker,
            plot=plot,
            artist=name,
            album="Live radio",
            title=name,
            label2="live",
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
    selected = list(enumerate(tracks))
    if shuffle:
        random.shuffle(selected)
    else:
        selected = selected[start:]
    if not selected:
        return False
    playable = []
    dropped = 0
    for index, track in selected:
        url = _playable_url(track.get("url", ""))
        if not url:
            dropped += 1
            kodi.log("play_all: skipping non-public track URL for %r" % track.get("title"),
                     level=30)
            continue
        playable.append((index, track, url))
    if dropped:
        kodi.notify("Skipped %d track%s with a non-public stream address."
                    % (dropped, "" if dropped == 1 else "s"))
    if not playable:
        return False
    album = identifier.replace("-", " ")
    thumb = archive.thumb(identifier) or kodi.ROUND_FACE
    pack_title = archive.item_title(identifier) or album
    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    playlist.clear()
    for index, track, url in playable:
        details = nowplaying.parse(pack_title, track["title"])
        plotted = nowplaying.plot("From archive.org item %s" % identifier, details)
        item = xbmcgui.ListItem(path=url)
        # 1:1 cover in the art slots, 16:9 brand fanart behind it.  The old
        # pass put the square cover in the fanart slot, which every skin
        # stretched across the whole 16:9 background.
        item.setArt({"thumb": thumb, "icon": thumb, "poster": thumb,
                     "fanart": kodi.FANART, "landscape": kodi.FANART})
        info = kodi.music_info(ui.plain(track["title"]), plotted,
                               mediatype="music", album=pack_title)
        if track.get("duration"):
            info["duration"] = track["duration"]
        # 3.9.44: stop discarding the metadata nowplaying/Archive already know.
        # The OSD and the song panel read these from the music InfoTag.
        if details["artist"]:
            info["artist"] = details["artist"]
        year = nowplaying.year(details)
        if year:
            info["year"] = year
        if track.get("genre"):
            info["genre"] = track["genre"]
        info["tracknumber"] = index + 1
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
    import time as _time

    started = _time.monotonic()
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
        # Wall-clock per directory is what the user feels; the cache/parse
        # split is in scripts/bench_sources.py.  Debug-level so normal Kodi
        # logs stay quiet.
        kodi.log("route %s took %.0f ms" % (mode, (_time.monotonic() - started) * 1000.0))


def root(handle, params):
    """Top-level 2026 taxonomy: product, pirate radio, shows, live, saved, find."""
    menu_item = ui.menu_item
    root_rows = [
        ("screen", "Rave Screen", MENU_ART["screen"], "fanart-screen.jpg",
         "Full-screen 2026 Rave UI — big art, D-pad rows and Spinning Surprise.",
         "full screen"),
        ("latest", "Latest", MENU_ART["latest"], "fanart-latest.jpg",
         "Newest packs, shows and radio rips — start here.", "newest"),
        ("packs_menu", "Tape Packs", MENU_ART["packs"], "fanart-tapepacks.jpg",
         "Cassette packs and rave tapes, by event, DJ, MC and year.", "1990–2004"),
        ("pirate_radio", "Pirate Radio", MENU_ART["pirate"], "fanart-curated.jpg",
         "1990s pirate-radio recordings: Kool FM, Don FM, Green Apple.", "1990s"),
        ("shows_menu", "Mixes & Shows", MENU_ART["shows"], "fanart-mixes.jpg",
         "Podcasts, DNBRADIO, GetDarker and studio mixes.", "podcasts"),
        ("radio_menu", "Live Radio", MENU_ART["radio"], "fanart-live.jpg",
         "Stations on air now: Kool, Rinse, Centreforce.", "live"),
        ("fav_list", "Favourites", MENU_ART["favourites"], "fanart-favourites.jpg",
         "The sets you saved.", "saved"),
        ("search", "Search the Archive", MENU_ART["search"], "fanart-search.jpg",
         "Search every tape pack on archive.org.", "archive.org"),
        ("surprise", "Surprise Me", MENU_ART["surprise"], "fanart-surprise.jpg",
         "Plays a random set from the archive.", "random"),
        ("about", "About & Sources", MENU_ART["about"], "fanart-about.jpg",
         "Version, credits and every source used.", kodi.ADDON_VERSION),
    ]
    for mode, label, icon, fan, plot, label2 in root_rows:
        # The screen row is a *program* item, not a folder: Kodi's
        # CGUIMediaWindow::OnClick routes a non-folder plugin item with no
        # IsPlayable property through CPluginDirectory::RunScriptWithParams(),
        # which runs this plugin without opening a directory window. That is
        # what keeps Back on the root list and removes the DialogBusy that used
        # to race the script's window activation (see docs/RAVE-SCREEN-DIAGNOSIS.md).
        menu_item(handle, url_for(mode=mode), label,
                  icon=art(icon), fanart=art(fan), plot=plot, label2=label2,
                  is_folder=(mode != "screen"))
    kodi.end_directory(handle, "files")


RAVE_SCREEN_ADDON = "script.raveplayer.ui"


def _condition(builder, addon_id):
    """Evaluate one Kodi info condition without letting an API change crash."""
    try:
        return bool(xbmc.getCondVisibility(builder % addon_id))
    except Exception:
        return False


def rave_screen(handle, params):
    """Run the full-screen script add-on; never open a plugin directory.

    The root row is a non-folder plugin item, so Kodi calls
    ``CPluginDirectory::RunScriptWithParams``: no directory window (and no
    DialogBusy) is created, and Back from the screen lands on the root list.
    ``System.HasAddon`` is true for a *disabled* add-on, so the enabled state is
    checked separately; otherwise the user is left on a row that does nothing.
    """
    enabled = _condition("System.AddonIsEnabled(%s)", RAVE_SCREEN_ADDON)
    if not enabled:
        if _condition("System.HasAddon(%s)", RAVE_SCREEN_ADDON):
            kodi.notify("Rave Screen is installed but disabled — enable it in "
                        "My add-ons, then select the row again.")
        else:
            kodi.notify("Rave Screen is not installed — install %s from the "
                        "Rave Player repository." % RAVE_SCREEN_ADDON)
        return
    # Only a folder invocation (a saved favourite/deep link) has a directory to
    # end; the normal program-style invocation passes handle -1.
    if handle is not None and handle >= 0:
        kodi.end_directory(handle, "files")
    xbmc.executebuiltin("RunScript(%s)" % RAVE_SCREEN_ADDON)


def packs_menu(handle, params):
    """Tape Packs: the three literal cassette sources first, Archive last."""
    rows = [
        ("Toronto Rave Mixtape Archive", url_for(mode="toronto"),
         MENU_ART["pack_toronto"],
         "Toronto rave tapes, 1990–2014. 2,600+ recordings.", "2,600+"),
        ("JungleTapes.com", url_for(mode="legacy_jt"),
         MENU_ART["pack_jungletapes"],
         "Toronto jungle radio from cassette, 1996–2000. 300+ shows.", "300+ shows"),
        ("RaveTapePacks.com", url_for(mode="legacy_menu"),
         MENU_ART["pack_ravetapepacks"],
         "UK tape packs, 1992–2004, by event, DJ, MC and year.", "1992–2004"),
        ("Classic Pack Series", url_for(mode="filters_menu"),
         MENU_ART["pack_series"],
         "The UK pack canon: Dreamscape, Helter Skelter, One Nation, Fantazia.",
         ui.fact("%d series" % len(_filters()))),
        ("By Rave, Venue & Promoter", url_for(mode="rave_nights"),
         MENU_ART["pack_raves"],
         "Sanctuary, Bagleys, Bowlers, Que Club, Biology and more.",
         ui.fact("%d raves" % len(_rave_catalog()))),
        ("By Year", url_for(mode="years"), MENU_ART["pack_year"],
         "Browse the archive one year at a time.", "1987–now"),
        ("Every Pack", url_for(mode="archive_list", key="tapepacks", page=1),
         MENU_ART["pack_every"],
         "Archive mixtapes — everything the Archive tags as a tape pack.",
         "archive.org"),
    ]
    hub_fanart = art("fanart-hub-packs.jpg")
    for label, url, icon, plot, label2 in rows:
        ui.menu_item(handle, url, label, icon=art(icon), fanart=hub_fanart, plot=plot,
                     label2=label2)
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")



def shows_menu(handle, params):
    """Mixes & Shows: living feeds only; Toronto/Hardscore moved elsewhere."""
    rows = [
        ("Podcasts & Mixes", url_for(mode="media_menu"), MENU_ART["shows_podcasts"], None,
         "Current jungle, drum & bass, hardcore and rave shows — RSS feeds.",
         ui.fact("%d feeds" % len(feeds.registry()))),
        ("DNBRADIO", url_for(mode="dnb_list"), MENU_ART["shows_dnb"], None,
         "24/7 jungle and drum & bass, plus the show archive.", "archive"),
        ("GetDarker", url_for(mode="getdarker"), MENU_ART["shows_getdarker"],
         "fanart-getdarker.jpg", "Dubstep and grime, 2003 onwards.", "dubstep/grime"),
        ("Moxser", url_for(mode="moxser"), MENU_ART["shows_moxser"], "fanart-moxser.jpg",
         "Old skool to new cool dance mixes.", "old skool"),
    ]
    hub_fanart = art("fanart-hub-shows.jpg")
    for label, url, icon, fan, plot, label2 in rows:
        ui.menu_item(handle, url, label, icon=art(icon),
                     fanart=art(fan) if fan else hub_fanart, plot=plot, label2=label2)
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")




def radio_menu(handle, params):
    """Named stations first, then scene genre doors."""
    hub_fanart = art("fanart-hub-live.jpg")
    stations = [
        ("Kool FM", url_for(mode="filter_list", key="kool"), "radio_kool",
         "Kool FM — live now, plus every Kool FM set in the archive."),
        ("Rinse FM", url_for(mode="filter_list", key="rinse"), "radio_rinse",
         "Rinse FM — live now, plus every Rinse FM set in the archive."),
        ("Centreforce 883", url_for(mode="station_live", token="centreforce"),
         "radio_centreforce", "The 1989 acid-house pirate, still broadcasting."),
    ]
    for label, url, art_key, plot in stations:
        ui.menu_item(handle, url, label, icon=art(MENU_ART[art_key]),
                     fanart=hub_fanart, plot=plot, label2="live")
    for section in RADIO_SECTIONS:
        ui.menu_item(
            handle,
            url_for(mode="radio_tag", key=section["key"]),
            section["label"],
            icon=art(section["art"]),
            fanart=hub_fanart,
            plot="Live stations tagged %s" % section["tag"],
            label2="stations",
        )
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def station_live(handle, params):
    token = params.get("token", "")
    stations = radio.curated(token)
    if not stations:
        kodi.notify("That station is not listed live right now.")
        ui.status_item(
            handle, "This station is off air",
            plot="The station directory has no working stream for it right now. "
                 "Press OK to check again.",
            fact="empty", kind="empty",
            retry_url=url_for(mode="station_live", token=token))
    _station_items(handle, stations, "Live now")
    kodi.end_directory(handle, "songs")



def radio_tag(handle, params):
    section = RADIO_BY_KEY.get(params.get("key", ""))
    if not section:
        kodi.notify("That radio section no longer exists.")
        kodi.end_directory(handle, "files")
        return
    stations = radio.stations(section["tag"], limit=kodi.setting_int("radio_limit", 500))
    if not stations:
        kodi.notify("No working stations for %s right now." % section["label"])
        ui.status_item(
            handle, "No working %s stations" % section["label"].lower(),
            plot="The radio directory returned no stream that passed the "
                 "public-host check. Press OK to scan again.",
            fact="empty", kind="empty",
            retry_url=url_for(mode="radio_tag", key=section["key"]))
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
        ui.status_item(
            handle, "Nothing in %s right now" % section["label"],
            plot="The Archive returned no items for this section. Press OK to "
                 "ask again, or pick another room.",
            fact="empty", kind="empty",
            retry_url=url_for(mode="archive_list", key=section["key"], page=1))

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
    thumb = archive.thumb(identifier) or art(MENU_ART["packs"])
    sticker = art(MENU_ART["packs"])
    pack_title = archive.item_title(identifier) or identifier.replace("-", " ")
    if not tracks:
        ui.status_item(
            handle, "This pack has no playable audio",
            plot="The Archive item exists but returned no audio files. Press "
                 "OK to reload the pack, or go Back and pick another set.",
            fact="error", kind="error",
            retry_url=url_for(mode="archive_item", id=identifier))
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
                plot=plotted,
            ),
            track_title,
            thumb=thumb,
            # The square pack front belongs in the 1:1 art slot; the 16:9
            # background stays the brand fanart instead of stretching a cover.
            icon=sticker,
            plot=plotted,
            artist=details["artist"],
            album=pack_title,
            year=nowplaying.year(details),
            genre=track.get("genre"),
            tracknumber=index + 1,
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
                 icon=art(MENU_ART["downloads"]),
                 plot="Offline downloads — play from the local copy or delete.",
                 label2="%d saved" % len(download_rows) if download_rows else "empty")
    if not entries:
        ui.status_item(
            handle, "No favourites yet",
            plot="Open a pack or show, then use Add to favourites in its context "
                 "menu. Press OK to refresh this list.",
            fact="empty", kind="empty", retry_url=url_for(mode="fav_list"))
    for entry in entries:
        entry_key = favourites.key(entry)
        title = ui.plain(entry["title"])
        context = [("Remove from favourites", "RunPlugin(%s)" % url_for(mode="fav_remove", key=entry_key))]
        source = ui.plain(entry.get("source") or "")
        if entry["kind"] == "pack":
            ui.menu_item(handle, url_for(mode="archive_item", id=entry["target"]), title,
                         icon=art(MENU_ART["packs"]),
                         thumb=archive.thumb(entry["target"]),
                         plot="Tape pack · %s" % source if source else "Tape pack",
                         label2=source,
                         context=context)
        elif entry["kind"] == "legacy_pack":
            ui.menu_item(handle, url_for(mode="legacy_pack", pack=entry["target"]), title,
                         icon=art(MENU_ART["pack_ravetapepacks"]),
                         plot="RaveTapePacks.com pack", label2="RaveTapePacks",
                         context=context)
        elif entry["kind"] == "legacy_post":
            ui.menu_item(handle, url_for(mode="legacy_post", post=entry["target"]), title,
                         icon=art(MENU_ART["pack_ravetapepacks"]),
                         plot="RaveTapePacks.com pack", label2="RaveTapePacks",
                         context=context)
        elif entry["kind"] == "legacy_jt":
            ui.menu_item(handle, url_for(mode="legacy_jt_show", key=entry["target"]), title,
                         icon=art(MENU_ART["pack_jungletapes"]),
                         plot="JungleTapes.com show", label2="JungleTapes",
                         context=context)
        elif entry["kind"] == "dnb":
            ui.track_item(handle, url_for(mode="dnb_play", id=entry["target"], label=title),
                          title, thumb=art(MENU_ART["shows_dnb"]),
                          plot="DNB Radio", label2="DNB Radio", context=context)
        else:
            kind = handoff.platform_kind(entry["target"])
            if kind:
                target = handoff.target(entry["target"], title)
                if not target:
                    continue  # missing add-on: hide, never emit a raw platform URL
                ui.menu_item(handle, target, title + "  [COLOR gray](add-on)[/COLOR]",
                             icon=art("radio.png"),
                             plot="Saved %s link — opens in the Kodi add-on." % kind,
                             label2="add-on", context=context)
                continue
            play_params = {"url": entry["target"], "label": title}
            if "live radio" in source.lower() or live.is_live_stream(entry["target"]):
                play_params["live"] = 1
                station = source.split("·")[-1].strip() if "·" in source else ""
                if station:
                    play_params["station"] = station
            saved_live = str(play_params.get("live") or "") == "1"
            ui.track_item(handle, url_for(mode="play", **play_params),
                          title, thumb=art("radio.png"),
                          plot="Saved stream · %s" % source if source else "Saved stream",
                          label2="live" if saved_live else source, context=context)
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
        bits = []
        if entry.get("count"):
            bits.append("%d packs" % entry["count"])
        if entry.get("mixcloud_count"):
            bits.append("%d sets" % entry["mixcloud_count"])
        ui.menu_item(handle,
                     url_for(mode="rave_list", key=entry.get("slug") or entry["name"]),
                     "%s  [COLOR gray](%s)[/COLOR]" % (
                         name, " · ".join(bits) or "content"),
                     icon=art(MENU_ART["pack_raves"]),
                     plot="Archive packs and Mixcloud sets for %s" % name)
    ui.menu_item(handle, url_for(mode="root"), "Back")
    kodi.end_directory(handle, "files")


def rave_list(handle, params):
    key = params.get("key", "")
    entry = next((item for item in _rave_catalog()
                  if key in (item.get("slug"), item["name"])), None)
    if not entry:
        kodi.notify("That rave is no longer in the catalogue.")
        kodi.end_directory(handle, "files")
        return
    try:
        page = max(1, int(params.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    rows = _rows_per_page()
    if entry.get("query") and entry.get("count"):
        docs, total = archive.search(entry["query"], page=page, rows=rows)
        _archive_items(handle, docs)
        if total > page * rows:
            ui.menu_item(handle, url_for(mode="rave_list",
                                         key=entry.get("slug") or entry["name"],
                                         page=page + 1),
                         "Next page  ›", plot="More %s" % ui.plain(entry["name"]))
    elif entry.get("mixcloud_query") and entry.get("mixcloud_count"):
        kodi.notify("No Archive packs for that rave — open its Mixcloud sets.")
    if entry.get("mixcloud_query") and entry.get("mixcloud_count"):
        if handoff.available("mixcloud"):
            ui.menu_item(handle,
                         handoff.mixcloud_search(entry["mixcloud_query"]),
                         "Open %s sets in the Kodi Mixcloud add-on" % entry["name"],
                         icon=art(MENU_ART["pack_raves"]),
                         plot="%d Mixcloud sets for %s." % (
                             entry["mixcloud_count"], entry["name"]))
    kodi.end_directory(handle, "files")


def filters_menu(handle, params):
    filters = _filters()
    if not filters:
        kodi.notify("No quick filters are configured.")
    for entry in filters:
        ui.menu_item(handle, url_for(mode="filter_list", key=entry["id"]), entry["name"],
                     icon=art(FILTER_ART.get(entry["id"], MENU_ART["pack_series"])),
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


def _fail_playback(handle, message, quiet=False):
    """Fail a resolve without touching the user's current playback.

    A playable item inside a mixed folder can make Kodi build a music playlist
    from the whole folder.  The "Latest" cascade is stopped at the source: its
    directory is typed ``files`` and unresolvable rows are dropped.  A failed
    resolve only reports failure for this plugin handle; it must not stop or
    clear a track the user is already playing (especially if a programmatic
    invocation hits an invalid play URL).
    """
    if message and not quiet:
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
            thumb=art(MENU_ART["radio_kool" if token == "kool" else "radio_rinse"]),
            plot="Live radio · %s" % name,
            artist=name,
            album="Live radio",
            title=name,
            label2="live",
            context=[_favourite("stream", stream, label, "Live radio · %s" % name)],
        )
        count += 1
    return count


def latest_view(handle, params):
    items = latest.merge()
    live_count = _latest_live_rows(handle)
    if not items and not live_count:
        kodi.notify("Nothing came back from the sources — try again later.")
        ui.status_item(
            handle, "Nothing new right now",
            plot="The sources did not answer. Press OK to fetch Latest again, "
                 "or try another room while you wait.",
            fact="empty", kind="empty", retry_url=url_for(mode="latest"))
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
                         icon=art(MENU_ART["packs"]),
                         thumb=archive.thumb(item["identifier"]),
                         plot="Tape pack from the Internet Archive.",
                         title=title, label2=stamp or "pack",
                         context=_pack_context(item["identifier"], title))
        elif item["kind"] == "episode":
            if handoff.platform_kind(item["url"]):
                if not _platform_item(handle, item["url"], label, title,
                                      art(MENU_ART["shows_podcasts"]), source):
                    continue
                continue
            ui.track_item(handle, url_for(mode="play", url=item["url"], label=title), label,
                          thumb=art(MENU_ART["shows_podcasts"]), plot=source, title=title,
                          duration=item.get("duration"),
                          context=[_favourite("stream", item["url"], title, source)])
        else:
            stream = streams.get(str(item.get("id") or ""))
            if not stream or handoff.platform_kind(stream):
                # Host unreachable / listen page changed: do not offer the row.
                continue
            ui.track_item(handle, url_for(mode="play", url=stream, label=title), label,
                          thumb=art(MENU_ART["shows_dnb"]), plot="DNBRADIO.com", title=title,
                          label2=when.strftime("%d %b") if when else "",
                          context=[_favourite("dnb", item["id"], title, "DNB Radio")])

    # Visible terminator: folder+playable mix means Kodi should not wrap or
    # treat the whole screen as an endless playlist.
    ui.end_marker(handle, "End of list", plot="You have reached the end of Latest.")
    kodi.end_directory(handle, "files")


def surprise(handle, params):
    reveal = None
    try:
        if kodi.setting_bool("surprise_animate", True):
            try:
                reveal = spinner.SurpriseReveal(
                    code=params.get("code") or "RANDOM PACK")
                reveal.show()
            except Exception as exc:  # noqa: BLE001 - reveal must never block
                kodi.log("surprise reveal failed (%s)" % exc.__class__.__name__,
                         level=30)
    finally:
        if reveal is not None:
            try:
                reveal.close()
            except Exception:
                pass
    if reveal is not None and reveal.cancelled:
        kodi.end_directory(handle, "files")
        return
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
                     icon=art(MENU_ART["pack_year"]), plot="%s tape packs" % year)
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
            icon=art(MENU_ART["shows_podcasts"]),
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
                                  art(MENU_ART["shows_podcasts"]),
                                  episode.get("description") or entry.get("plot") or ""):
                continue
            continue
        ui.track_item(
            handle,
            url_for(mode="play", url=episode["url"], label=title),
            label,
            thumb=art(MENU_ART["shows_podcasts"]),
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
            thumb=art(MENU_ART["shows_dnb"]),
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
                  "thumb": params.get("thumb") or kodi.ROUND_FACE})


def legacy_menu(handle, params):
    """RaveTapePacks.com index (source's own Event/DJ/MC/Year taxonomy)."""
    rows = [
        ("By Event", url_for(mode="legacy_index", kind="event"),
         MENU_ART["pack_rave"], "Browse event categories: Dreamscape, One Nation, Roast…",
         "events"),
        ("By DJ", url_for(mode="legacy_index", kind="dj"),
         MENU_ART["pack_jungle"], "Browse every DJ category: Brockie, Randall, Hype…", "DJs"),
        ("By MC", url_for(mode="legacy_index", kind="mc"),
         MENU_ART["pack_hardcore"], "Browse every MC category: Det, Fearless, Skibadee…",
         "MCs"),
        ("By Year", url_for(mode="legacy_index", kind="year"),
         MENU_ART["pack_year"], "Browse packs by release year, 1992–2004.", "1992–2004"),
        ("All Packs", url_for(mode="legacy_packs"),
         MENU_ART["curated_legacy"], "Every RaveTapePacks pack.", "all"),
    ]
    hub_fanart = art("fanart-hub-packs.jpg")
    for label, url, icon, plot, label2 in rows:
        ui.menu_item(handle, url, label, icon=art(icon), fanart=hub_fanart, plot=plot,
                     label2=label2)
    ui.menu_item(handle, url_for(mode="packs_menu"), "Back")
    kodi.end_directory(handle, "files")


# RaveTapePacks index kind -> plural group in legacy.categories().  The menu
# uses the singular form so every existing legacy_index link keeps working.
RTP_INDEX_KINDS = {"event": "events", "dj": "djs", "mc": "mcs", "year": "years"}
RTP_INDEX_LABELS = {"event": "By Event", "dj": "By DJ", "mc": "By MC", "year": "By Year"}
RTP_INDEX_ART = {"event": MENU_ART["pack_rave"], "dj": MENU_ART["pack_jungle"],
                 "mc": MENU_ART["pack_hardcore"], "year": MENU_ART["pack_year"]}


def legacy_index(handle, params):
    """List one RaveTapePacks category kind (event/dj/mc/year)."""
    kind = params.get("kind", "")
    group = RTP_INDEX_KINDS.get(kind)
    if not group:
        kodi.notify("That RaveTapePacks index is not available.")
        kodi.end_directory(handle, "files")
        return
    entries = legacy.categories().get(group, [])
    if not entries:
        kodi.notify("RaveTapePacks did not return that index — try again later.")
    for entry in entries:
        name = ui.plain(entry["name"])
        ui.menu_item(
            handle,
            url_for(mode="legacy_category", kind=kind, cat=entry["id"], label=name),
            name,
            icon=art(RTP_INDEX_ART[kind]),
            plot="RaveTapePacks.com · %s category" % RTP_INDEX_LABELS[kind],
            title=name,
            label2=RTP_INDEX_LABELS[kind],
        )
    ui.menu_item(handle, url_for(mode="legacy_menu"), "Back")
    kodi.end_directory(handle, "files")


def legacy_category(handle, params):
    """One page of packs (WordPress posts) inside a RaveTapePacks category."""
    kind = params.get("kind", "")
    cat_id = params.get("cat", "")
    label = params.get("label", "")
    if kind not in RTP_INDEX_KINDS or not str(cat_id).isdigit():
        kodi.notify("That RaveTapePacks category is not available.")
        kodi.end_directory(handle, "files")
        return
    page = _page_number(params)
    posts, next_url = legacy.category_page(cat_id, page)
    if posts is None:
        kodi.notify("RaveTapePacks did not answer — try again later.")
        kodi.end_directory(handle, "files")
        return
    if not posts and page == 1:
        kodi.notify("No packs in that RaveTapePacks category.")
    for entry in posts:
        name = ui.plain(entry["name"])
        ui.menu_item(
            handle,
            url_for(mode="legacy_post", post=entry["id"], kind=kind, cat=cat_id,
                    label=name),
            name,
            icon=art(MENU_ART["pack_ravetapepacks"]),
            plot="RaveTapePacks.com · %s" % (ui.plain(label) or RTP_INDEX_LABELS[kind]),
            title=name,
            label2=RTP_INDEX_LABELS[kind],
            context=[_favourite("legacy_post", entry["id"], name, "RaveTapePacks.com")],
        )
    if next_url:
        ui.menu_item(handle, url_for(mode="legacy_category", kind=kind, cat=cat_id,
                                     label=label, page=page + 1),
                     "Next page  ›", plot="More packs in this category")
    ui.menu_item(handle, url_for(mode="legacy_index", kind=kind), "Back")
    kodi.end_directory(handle, "files")


def _rtp_track_context(url, name):
    """Play + Download context for one RaveTapePacks track."""
    context = [_favourite("stream", url, name, "RaveTapePacks.com")]
    context.extend(_download_context(url, name, "RaveTapePacks.com"))
    return context


def legacy_post(handle, params):
    """List the MP3s on one RaveTapePacks post (a pack's detail page)."""
    post_id = params.get("post", "")
    if not post_id:
        kodi.end_directory(handle, "songs")
        return
    entry = legacy.post(post_id)
    if not entry:
        kodi.notify("RaveTapePacks did not answer — try again later.")
        kodi.end_directory(handle, "songs")
        return
    album = ui.plain(entry["name"])
    if not entry["tracks"]:
        kodi.notify("No tracks on that RaveTapePacks pack.")
    for track in entry["tracks"]:
        url = _playable_url(legacy.playable(track["url"]))
        if not url:
            continue
        name = ui.plain(track["name"])
        ui.track_item(
            handle,
            url_for(mode="play", url=url, label=name,
                    thumb=art(MENU_ART["pack_ravetapepacks"])),
            name,
            thumb=art(MENU_ART["pack_ravetapepacks"]),
            plot="RaveTapePacks.com · %s" % album,
            album=album,
            context=_rtp_track_context(url, name),
        )
    kodi.end_directory(handle, "songs")


def legacy_jt(handle, params):
    shows = legacy.jungle_shows()
    if not shows:
        kodi.notify("Jungle Tapes did not answer — try again later.")
    page = _page_number(params)
    start = (page - 1) * JT_SHOWS_PER_PAGE
    window = shows[start:start + JT_SHOWS_PER_PAGE]
    for show in window:
        name = ui.plain(show["name"])
        ui.menu_item(
            handle,
            url_for(mode="legacy_jt_show", key=show["key"]),
            name,
            icon=art(MENU_ART["pack_jungletapes"]),
            plot="JungleTapes.com · Toronto jungle radio",
            context=[_favourite("legacy_jt", show["key"], name, "JungleTapes.com")],
        )
    if start + JT_SHOWS_PER_PAGE < len(shows):
        ui.menu_item(handle, url_for(mode="legacy_jt", page=page + 1),
                     "Next page  ›", plot=_page_plot(len(shows), page + 1,
                                                     JT_SHOWS_PER_PAGE))
    ui.menu_item(handle, url_for(mode="packs_menu"), "Back")
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
            url_for(mode="play", url=stream, label=name,
                    thumb=art(MENU_ART["pack_jungletapes"])),
            name,
            thumb=art(MENU_ART["pack_jungletapes"]),
            plot="JungleTapes.com · %s" % ui.plain(key.replace("-", " ")),
            context=[_favourite("stream", stream, name, "JungleTapes.com")],
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
    ui.menu_item(handle, url_for(mode="packs_menu"), "Back")
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
            url_for(mode="play", url=stream, label=name, thumb=kodi.ROUND_FACE),
            name,
            thumb=kodi.ROUND_FACE,
            plot=plot,
            album=ui.plain(genre_label),
            genre=ui.plain(genre_label),
            context=context,
        )
    ui.menu_item(handle, url_for(mode="toronto"), "Back")
    kodi.end_directory(handle, "songs")


def legacy_packs(handle, params):
    """Every RaveTapePacks post, from the paginated blog archive (?cat=0)."""
    page = _page_number(params)
    posts, next_url = legacy.all_packs(page)
    if posts is None:
        kodi.notify("RaveTapePacks did not answer — try again later.")
        kodi.end_directory(handle, "files")
        return
    if not posts and page == 1:
        kodi.notify("No packs in the RaveTapePacks archive.")
    for entry in posts:
        name = ui.plain(entry["name"])
        ui.menu_item(
            handle,
            url_for(mode="legacy_post", post=entry["id"], label=name),
            name,
            icon=art(MENU_ART["pack_ravetapepacks"]),
            plot="RaveTapePacks.com · tape pack",
            title=name,
            context=[_favourite("legacy_post", entry["id"], name, "RaveTapePacks.com")],
        )
    if next_url:
        ui.menu_item(handle, url_for(mode="legacy_packs", page=page + 1),
                     "Next page  ›", plot="More RaveTapePacks packs")
    kodi.end_directory(handle, "files")


def legacy_pack(handle, params):
    key = params.get("pack", "")
    if not key:
        kodi.end_directory(handle, "songs")
        return
    entry = legacy.pack(key)
    if not entry:
        kodi.end_directory(handle, "songs")
        return
    for track in entry["tracks"]:
        url = _playable_url(legacy.playable(track["url"]))
        if not url:
            continue
        name = ui.plain(track["name"])
        ui.track_item(
            handle,
            url_for(mode="play", url=url, label=name, thumb=kodi.ROUND_FACE),
            name,
            thumb=kodi.ROUND_FACE,
            plot="RaveTapePacks.com · %s" % ui.plain(entry["name"]),
            album=ui.plain(entry["name"]),
            context=_rtp_track_context(url, name),
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
        flyer = _safe_art(row.get("flyer"), art(MENU_ART["shows_moxser"]))
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
    flyer = _safe_art(params.get("flyer") or details.get("flyer"),
                      kodi.ROUND_FACE)
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
            year=nowplaying.year({"date": details.get("date") or ""}),
            label2=ui.short_date(details.get("date")) or "",
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
                thumb=art(MENU_ART["shows_hardscore"]),
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
                icon=art(MENU_ART["shows_hardscore"]),
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
            thumb=art(MENU_ART["shows_hardscore"]), plot="Hardscore.com",
            title=title,
            context=[_favourite("stream", url, title, "Hardscore.com")]
            + _download_context(url, title, "Hardscore.com"),
        )
    shown = _handoff_link_items(handle, details["links"], title,
                                art(MENU_ART["shows_hardscore"]),
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
        icon=art(MENU_ART["shows_getdarker"]),
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
            icon=art(MENU_ART["shows_getdarker"]),
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
                      thumb=art(MENU_ART["shows_getdarker"]), plot="GetDarker",
                      title=title,
                      context=[_favourite("stream", url, title, "GetDarker")])
    shown = _handoff_link_items(handle, details["links"], title,
                                art(MENU_ART["shows_getdarker"]),
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


def pirate_radio(handle, params):
    """Pirate Radio root door."""
    hub_fanart = art("fanart-pirate-archive.jpg")
    rows = [
        ("Hardscore", url_for(mode="hardscore"), MENU_ART["shows_hardscore"],
         "fanart-hardscore.jpg",
         "The best 1990s pirate archive: Kool FM 94.5, Don FM, Green Apple."),
        ("Pirate Radio Archives", url_for(mode="pirate_menu"),
         MENU_ART["curated_pirate"], "fanart-pirate-archive.jpg",
         "Curated 1990s pirate-radio recordings: Risk FM, Weekend Rush and Flava FM."),
        ("Kool FM Sets", url_for(mode="filter_list", key="kool"),
         MENU_ART["radio_kool"], "fanart-live.jpg",
         "Every Kool FM set in the archive."),
    ]
    for label, url, icon, fan, plot in rows:
        ui.menu_item(handle, url, label, icon=art(icon), fanart=art(fan), plot=plot)
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
            icon=art(MENU_ART["curated_pirate"]),
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
            year=entry["year"] if entry["year"] is not None else None,
            label2=str(entry["year"]) if entry["year"] is not None else "",
            context=[_favourite("stream", stream, title, group["station"])]
            + _download_context(stream, title, "Pirate Radio Archives"),
        )
    ui.menu_item(handle, url_for(mode="pirate_menu"), "Back")
    kodi.end_directory(handle, "files")


def downloads_menu(handle, params):
    rows = downloads.list_downloads()
    if not rows:
        kodi.notify("No downloads yet — use Download in an item's context menu.")
        ui.status_item(
            handle, "No downloads yet",
            plot="Use Download in a pack or track's context menu. Saved files "
                 "appear here and play without a network connection.",
            fact="empty", kind="empty",
            retry_url=url_for(mode="downloads_menu"),
            icon=art(MENU_ART["downloads"]))
    for row in rows:
        label = ui.plain(row["title"])
        if row.get("exists"):
            label += "  [COLOR gray](%s)[/COLOR]" % downloads.format_size(row["size"])
            ui.track_item(
                handle,
                row["path"],
                label,
                thumb=art(MENU_ART["downloads"]),
                plot="Downloaded · %s · %s" % (row["source"], row["added"][:10]),
                album="Downloads",
                title=row["title"],
                label2=ui.size_date_fact(downloads.format_size(row["size"]),
                                         row.get("added")),
                context=[("Delete download", "RunPlugin(%s)" % url_for(
                    mode="download_delete", key=row["key"]))],
            )
        else:
            ui.menu_item(
                handle,
                url_for(mode="downloads_menu"),
                label + "  [COLOR gray](missing)[/COLOR]",
                icon=art(MENU_ART["downloads"]),
                plot="The file is missing — delete the entry or download it again.",
                label2=ui.short_date(row.get("added")) or "missing",
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
    # Scope the full-text query to the curated collection, exactly as the web
    # build does.  An unscoped search for "dreamscape" used to return YouTube
    # rips, audiobooks and sound-effect records before any actual rave tape.
    docs, total = archive.search("%s AND %s" % (query, latest.RAVE_COLLECTION),
                                 page=page, rows=rows)
    if page == 1 and total < 10:
        # Title-scoped widen: an unscoped mediatype:audio search returns
        # audiobooks and sound effects before the rave tapes.
        widen_query = (
            'title:(%s) AND mediatype:audio AND '
            '(collection:ravetapes OR collection:cassettetapes OR '
            'subject:(rave OR jungle OR hardcore OR "drum and bass" OR '
            '"old skool" OR garage))' % query)
        wider, _ = archive.search(widen_query, rows=rows)
        seen = {doc.get("identifier") for doc in docs if isinstance(doc, dict)}
        docs += [doc for doc in wider
                 if isinstance(doc, dict) and doc.get("identifier") not in seen]
    if not docs and page == 1:
        kodi.notify("No results for “%s”." % query)
        ui.status_item(
            handle, "No results for “%s”" % query,
            plot="Nothing in the Archive matched that search. Press OK to "
                 "search again with a different word.",
            fact="empty", kind="empty",
            retry_url=url_for(mode="search", q=query, page=1))
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
    # The right-hand column finally tells the truth: every About row is a
    # licence, a host or a delivery mode, never a second title.
    facts = ("GPL-3.0", "archive.org", "add-on", "web only", "directory",
             "moxser.com", "hardscore.com", "dnbradio.com", "getdarker.com",
             "podcast rss", "pirate archive", "live radio", "rave tapes",
             "jungletapes.com", "toronto")
    for (label, icon, plot), fact in zip(rows, facts):
        ui.info_item(handle, label, plot=plot, icon=art(icon), label2=fact)
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


PREBUFFER_BYTES = 64 * 1024
PREBUFFER_TIMEOUT = 12.0
PREBUFFER_HOSTS = ("torontoravemixtapearchive.com",
                   "www.torontoravemixtapearchive.com")


def _should_prebuffer(stream):
    """Only sources known to be slow get the extra pre-buffer request.

    The URL has already passed the public-stream guard.  Local/fast sources and
    the live playlist path are untouched.
    """
    try:
        host = (urllib.parse.urlsplit(str(stream or "").split("|", 1)[0]).hostname or "").lower()
    except ValueError:
        return False
    return host in PREBUFFER_HOSTS


def _prebuffer_stream(stream, timeout=PREBUFFER_TIMEOUT):
    """Read the first bytes while the tuning spinner is visible.

    Returns True on any non-empty chunk.  A timeout/error is logged and treated
    as a slow source; the caller still resolves so Kodi can take over.
    """
    try:
        with http.open_media(stream, timeout=timeout) as response:
            chunk = response.read(PREBUFFER_BYTES)
        if chunk:
            return True
    except Exception as exc:  # noqa: BLE001 - pre-buffer is advisory
        kodi.log("pre-buffer failed (%s); Kodi will take over"
                 % exc.__class__.__name__, level=30)
        return False
    kodi.log("pre-buffer returned no bytes; Kodi will take over", level=30)
    return False


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
    is_rtp = http.is_egress_host(params.get("url", ""))
    # RTP failures must stay silent: no spinner notification/dialog/banner.
    tuning = None if is_rtp else _start_tuning_spinner(params.get("station") or label)
    bridge = None
    try:
        stream = _playable_url(params.get("url", ""))
        thumb = _safe_art(params.get("thumb"), kodi.ROUND_FACE)
        # A missing fanart must fall back to the 1920x1080 brand still, not to
        # the square thumb: Kodi's OSD/background is a 16:9 surface.
        fanart = _safe_art(params.get("fanart"), kodi.FANART)
        plotted = params.get("plot") or ""
        if not stream:
            _fail_playback(handle,
                           "That stream address is not playable "
                           "(private, loopback or unresolved host).",
                           quiet=is_rtp)
            return
        if is_rtp:
            try:
                bridge = rtp_bridge.RTPBridge()
                if bridge.start():
                    bridged = bridge.url_for(stream)
                    if bridged:
                        stream = bridged
                    else:
                        bridge.close()
                        bridge = None
                else:
                    bridge = None
            except Exception as exc:  # noqa: BLE001 - fall back direct silently
                kodi.log("RTP bridge unavailable (%s)" % exc.__class__.__name__,
                         level=10)
                bridge = None
        if tuning is not None and not live.is_live_stream(stream) \
                and _should_prebuffer(stream):
            prebuffered = _prebuffer_stream(stream)
            if not prebuffered:
                try:
                    kodi.notify("Slow source — Kodi will continue buffering.")
                except Exception:
                    pass
            if _tuning_aborted(handle, tuning):
                return
        is_live = _flag(params, "live") or live.is_live_stream(stream)
        station = live.station_name(stream, params.get("station") or label) if is_live else ""
        display_label = station or label
        item = xbmcgui.ListItem(path=stream)
        art = {"thumb": thumb, "icon": thumb, "poster": thumb,
               "fanart": fanart or kodi.FANART,
               "landscape": fanart or kodi.FANART}
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
        if bridge is not None:
            bridge.wait_for_playback()
    finally:
        _close_tuning_spinner(tuning)
        if bridge is not None:
            try:
                bridge.close()
            except Exception:
                pass


HANDLERS = {
    "root": root,
    "screen": rave_screen,
    "packs_menu": packs_menu,
    "shows_menu": shows_menu,
    "radio_menu": radio_menu,
    "station_live": station_live,
    "pirate_radio": pirate_radio,
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
    "legacy_index": legacy_index,
    "legacy_category": legacy_category,
    "legacy_post": legacy_post,
    "legacy_jt": legacy_jt,
    "legacy_jt_show": legacy_jt_show,
    "toronto": toronto,
    "toronto_genre": toronto_genre,
    "legacy_packs": legacy_packs,
    "legacy_pack": legacy_pack,
    "search": search,
    "about": about,
    "play": play,
}
