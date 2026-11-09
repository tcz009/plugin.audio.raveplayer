# -*- coding: utf-8 -*-
"""Data rows for the full-screen Rave Player app.

The screen is the shell; ``plugin.audio.raveplayer`` is the data/playback
backend.  This module adapts the plugin's public data helpers into one flat
row/page vocabulary (``Entry``/``Track``/``Page``) and never re-implements a
scraper.

Rooms are ordinary paged collections.  The controller owns paging mechanics
(previous/next rows, 25/50/100), focus and Back; this module only knows how to
produce one page for a target:

* a shell room key (``latest``, ``toronto``, ``jungletapes``,
  ``ravetapepacks``, ``mixes``)
* an ``Entry`` folder (pack / genre / show / RTP index / post / feed ...)

Search, Favourites, Downloads and About are owned by
:mod:`raveui.screens.library`; Live Radio by :mod:`raveui.screens.live`;
Spinning Surprise by :mod:`raveui.surprise_pick`.  :class:`SearchTarget` is
still the shell's navigation marker, but reaching it here is a programming
error: the library module owns that request.

Network work happens only when the controller asks for a page; opening the
window is static.  No notification, dialog or warning is raised here: a source
that is blocked/offline returns an empty list and the controller paints the
STANDBY/ERROR plate quietly (owner rule: no RTP warnings).
"""

import hashlib
import os
import urllib.parse
import xml.etree.ElementTree as _ET
from dataclasses import dataclass

from . import pluginbridge

FRAME_COUNT = 10
FRAME_SIZE = 512
PAGE_SIZES = (25, 50, 100)
DEFAULT_PAGE_SIZE = 50
MAX_FACT_CHARS = 16

ROOM_ORDER = (
    "latest", "packs", "pirate", "mixes", "live", "favourites", "downloads",
    "search", "surprise", "about",
)

# Plugin download source labels (resources/lib/downloads.py ALLOWED_SOURCES).
_DOWNLOAD_SOURCE = {
    "latest": "Archive.org",
    "archive": "Archive.org",
    "toronto": "Toronto Rave Mixtape Archive",
    "ravetapepacks": "RaveTapePacks.com",
    "moxser": "Moxser.com",
    "hardscore": "Hardscore.com",
    "pirate": "Pirate Radio Archives",
    "web_dejavu": "Rave Resolver",
}

_SOURCE_LABEL = {
    "latest": "Archive.org",
    "archive": "Archive.org",
    "toronto": "Toronto Rave Mixtape Archive",
    "jungletapes": "JungleTapes.com",
    "ravetapepacks": "RaveTapePacks.com",
    "moxser": "Moxser.com",
    "hardscore": "Hardscore.com",
    "pirate": "Pirate Radio Archives",
    "feeds": "Podcast feed",
    "dnb": "DNB Radio",
    "getdarker": "GetDarker",
    "live": "Live radio",
    "legacyblog": "Blog archive",
    "mixcloud": "Mixcloud",
    "web_20bensons": "20bensons.com",
    "web_ukraves": "UK Raves Downloads",
    "web_ezgarage": "EZ Garage Sets",
    "web_dejavu": "DejaVu FM",
}


@dataclass(frozen=True)
class Track:
    title: str
    pack: str
    url: str
    art: str = ""
    live: bool = False
    duration: str = ""
    year: str = ""
    genre: str = ""
    source: str = ""
    download_source: str = ""
    local: bool = False
    path: str = ""          # direct Kodi path (local file or platform plugin URL)
    station: str = ""       # live-radio reconnect token/name


@dataclass(frozen=True)
class Entry:
    key: str
    label: str
    subtitle: str = ""
    art: str = ""
    kind: str = "track"
    source: str = ""
    target: str = ""
    track: object = None      # Track for playable rows
    hero: str = ""
    fact: str = ""
    code: str = ""
    plot: str = ""
    meta: str = ""            # hero meta line: duration · year · genre · code
    year: str = ""
    genre: str = ""
    duration: str = ""
    download_source: str = ""
    downloadable: bool = False
    fav_key: str = ""


@dataclass(frozen=True)
class Page:
    rows: list
    total: int
    page: int
    pages: int
    rows_per_page: int
    has_next: bool = False
    cursor: str = ""

    @property
    def is_empty(self):
        return not self.rows


@dataclass(frozen=True)
class SearchTarget:
    """The one Search room's query, handed to ``raveui.screens.library``.

    The screen module owns the Archive scope and paging policy, so the shell
    target carries no scope of its own: there is one Search implementation.
    """

    query: str


def _text(value, fallback=""):
    if isinstance(value, (list, tuple)):
        value = " ".join(str(part) for part in value)
    text = " ".join(str(value or "").split())
    return text or fallback


def _fact(value, fallback=""):
    """Return a plain single-line Label2 fact capped at 16 characters."""
    text = _text(value, fallback)
    if len(text) <= MAX_FACT_CHARS:
        return text
    return text[:MAX_FACT_CHARS - 1].rstrip() + "…"


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _duration_fact(value):
    """Format a track duration for Label2 ("43:57", "1:02:03"), or ""."""
    text = _text(value)
    if not text:
        return ""
    if ":" in text and len(text) <= 8:
        return _fact(text)
    try:
        total = int(float(text))
    except (TypeError, ValueError, OverflowError):
        return ""
    if total <= 0:
        return ""
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return _fact("%d:%02d:%02d" % (hours, minutes, seconds))
    return _fact("%d:%02d" % (minutes, seconds))


def _duration_from_metadata(value):
    """Pull a "40:39" duration out of Toronto's bitrate/size metadata line."""
    text = _text(value)
    for token in text.replace("•", " ").split():
        if ":" in token and 4 <= len(token) <= 8:
            head, tail = token.split(":", 1)
            if head.isdigit() and tail.isdigit():
                return token
    return ""


def _year_from_text(*values):
    import re

    for value in values:
        text = _text(value)
        match = re.search(r"\b(19[5-9]\d|20[0-2]\d)\b", text)
        if match:
            return match.group(1)
    return ""


def _meta(*parts):
    return "  ·  ".join(str(part) for part in parts if part)


def _stable_key(parent_key, url):
    digest = hashlib.md5(str(url or "").encode("utf-8")).hexdigest()[:10]
    return "%s:%s" % (parent_key, digest)


def _page_local(entries, page=1, rows=DEFAULT_PAGE_SIZE, total=None):
    entries = list(entries or [])
    rows = max(1, _as_int(rows, DEFAULT_PAGE_SIZE))
    count = len(entries) if total is None else max(0, _as_int(total, len(entries)))
    pages = max(1, (count + rows - 1) // rows)
    page = max(1, min(_as_int(page, 1), pages))
    start = (page - 1) * rows
    return Page(entries[start:start + rows], count, page, pages, rows,
                has_next=page < pages)


def _page_server(entries, page, rows, total, has_next=None, cursor=""):
    entries = list(entries or [])
    rows = max(1, _as_int(rows, DEFAULT_PAGE_SIZE))
    page = max(1, _as_int(page, 1))
    total = max(0, _as_int(total, 0))
    if total:
        pages = max(1, (total + rows - 1) // rows)
        page = max(1, min(page, pages))
        next_page = page < pages
    else:
        pages = 0
        next_page = bool(has_next)
    return Page(entries, total, page, pages, rows,
                has_next=next_page, cursor=cursor)


class RaveData(object):
    """Adapter over the plugin modules. Lazily imports them on first data use."""

    def __init__(self, modules=None, addon_factory=None, root=None,
                 script_root=None, download_queue=None,
                 screen_version="", plugin_version=""):
        self._modules = modules
        self._addon_factory = addon_factory
        self._root = root
        self._script_root = script_root or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
        self._download_queue = download_queue
        self._screen_version = screen_version
        self._plugin_version = plugin_version
        self.rows_per_page = DEFAULT_PAGE_SIZE
        self.load_error = ""
        # The controller assigns the shared Surprise pack cache; a Latest load
        # seeds it so the picker can answer from cache when Archive hiccups.
        self.surprise_cache = None
        # Art is resolved once per room paint: fifty rows share a handful of
        # sticker names, and each miss is a filesystem stat on the Shield.
        self._art_cache = {}
        self._neutral_hero_cache = None

    @property
    def modules(self):
        if self._modules is None:
            self._modules = pluginbridge.load_plugin(self._addon_factory)
        return self._modules

    @property
    def root(self):
        if self._root:
            return self._root
        try:
            return self.modules.root
        except Exception as exc:  # noqa: BLE001 - window still opens
            self.load_error = str(exc)
            return self._script_root

    # ------------------------------------------------------------------ art
    def _web_art(self, value, fallback=""):
        """Use the add-on's local icon for a web /static/art URL.

        Kodi's image loader has no web session, so a remote /static/art URL is
        a 401 and paints the magenta placeholder.  The same icons ship in the
        add-on, so map by basename and keep the remote URL only when there is
        no local file.
        """
        text = str(value or "").replace("\\", "/")
        marker = "/static/art/"
        if marker in text:
            name = text.split(marker, 1)[1].split("?", 1)[0].split("#", 1)[0]
            name = name.rsplit("/", 1)[-1]
            if name and not name.startswith("."):
                local = self._art(name)
                if local:
                    return local
        return text or fallback

    def _art(self, name):
        key = str(name or "")
        cached = self._art_cache.get(key)
        if cached is not None:
            return cached
        path = os.path.join(self.root, "resources", "art", key)
        if not os.path.isfile(path):
            path = os.path.join(self._script_root, "resources", "art",
                                "rave-screen", "hero-fallback-640x360.jpg")
            if not os.path.isfile(path):
                path = ""
        self._art_cache[key] = path
        return path

    def _neutral_hero(self):
        """A plain screen-bed hero for rows whose room is the visual context.

        Several plugin fanarts carry baked room text.  Using one under a
        JungleTapes show painted "TAPE PACKS" over the show; child rows use
        the unlabelled bed instead, with the selected row's own title/meta.
        """
        if self._neutral_hero_cache is not None:
            return self._neutral_hero_cache
        for name in ("screen-bed-1920x1080.jpg", "screen-bed-1280x720.jpg"):
            path = os.path.join(self._script_root, "resources", "art",
                                "rave-screen", name)
            if os.path.isfile(path):
                self._neutral_hero_cache = path
                return path
        self._neutral_hero_cache = self._art("fanart-screen.jpg")
        return self._neutral_hero_cache

    def _safe_url(self, url):
        text = _text(url)
        if not text:
            return ""
        try:
            safe = self.modules.http.safe_stream_url(text)
        except Exception:  # noqa: BLE001 - malformed scraper URL
            return ""
        return _text(safe)

    def _downloadable(self, url, source):
        if not url or not source:
            return False
        try:
            return bool(self.modules.downloads.eligible(url, source, check_host=False))
        except Exception:  # noqa: BLE001 - optional module / offline
            return False

    # ------------------------------------------------------------- versions
    def plugin_version(self):
        if self._plugin_version:
            return self._plugin_version
        try:
            value = self.modules.addon.getAddonInfo("version")
            if value:
                self._plugin_version = str(value)
                return self._plugin_version
        except Exception:  # noqa: BLE001 - fall back to the manifest
            pass
        try:
            root = _ET.parse(os.path.join(self.root, "addon.xml")).getroot()
            self._plugin_version = str(root.get("version") or "")
        except Exception:  # noqa: BLE001 - no manifest
            self._plugin_version = ""
        return self._plugin_version

    def screen_version(self):
        if self._screen_version:
            return self._screen_version
        try:
            root = _ET.parse(os.path.join(self._script_root, "addon.xml")).getroot()
            self._screen_version = str(root.get("version") or "")
        except Exception:  # noqa: BLE001 - unpacked tree without manifest
            self._screen_version = ""
        return self._screen_version

    # ----------------------------------------------------------------- home
    def home_rows(self):
        def room(key, label, subtitle, art, hero, fact, code, plot):
            hero_path = self._neutral_hero() if hero == "neutral" else self._art(hero)
            return Entry(key, label, subtitle, self._art(art), "section",
                         source=key, target=key, hero=hero_path,
                         fact=fact, code=code, plot=plot)

        return [
            room("latest", "Latest",
                 "Newest tape packs from the Internet Archive",
                 "rave.png", "fanart-latest.jpg", "newest", "RP-01",
                 "Newest packs, shows and radio rips — start here."),
            room("packs", "Tape Packs",
                 "Cassette packs, classic series, by rave and year",
                 "tapepacks.png", "fanart-tapepacks.jpg", "1990–2004", "RP-37",
                 "Every tape-pack door: Toronto, JungleTapes, RaveTapePacks, "
                 "classic series, raves, years and the whole Archive."),
            room("pirate", "Pirate Radio",
                 "Hardscore · Pirate Radio Archives · Kool FM sets",
                 "pirate-radio.png", "fanart-curated.jpg", "1990s", "RP-38",
                 "1990s pirate-radio recordings and every Kool FM set."),
            room("mixes", "Mixes & Shows",
                 "DNBRADIO · Moxser · Hardscore · GetDarker · podcasts",
                 "mixes.png", "fanart-mixes.jpg", "shows", "RP-32",
                 "Studio mixes, archive sets and podcast shows."),
            room("live", "Live Radio",
                 "Kool · Rinse · Centreforce · DejaVu · OSA",
                 "radio.png", "fanart-live.jpg", "live", "RP-31",
                 "Stations on air now, plus scene genre doors."),
            room("favourites", "Favourites",
                 "The sets you saved — play or remove",
                 "favourites.png", "fanart-favourites.jpg",
                 "saved", "RP-34",
                 "Saved packs, shows and streams."),
            room("downloads", "Downloads",
                 "Offline copies, progress and removal",
                 "downloads.png", "neutral",
                 "offline", "RP-35",
                 "Files saved for offline playback."),
            Entry("search", "Search",
                  "Find a pack, show or station — scoped and paged",
                  self._art("search.png"), "search", source="search",
                  hero=self._art("fanart-search.jpg"), fact="find", code="RP-33",
                  plot="Type in the window; results are paged and relevance-sorted."),
            Entry("surprise", "Spinning Surprise",
                  "One random set from the whole archive",
                  self._art("surprise.png"), "surprise",
                  source="surprise", target="surprise",
                  hero=self._art("fanart-surprise.jpg"),
                  fact="random", code="RP-07",
                  plot="Plays a random set from across the archive."),
            room("about", "About",
                 "Version, sources and the app's real facts",
                 "about.png", "fanart-about.jpg", "credits", "RP-36",
                 "Version, licence, sources and storage facts."),
        ]

    # ---------------------------------------------------------------- rooms
    def room(self, key, page=1, rows=None):
        key = str(key or "")
        rows = rows or self.rows_per_page
        if key == "latest":
            return _page_local(self._latest_entries(), page, rows)
        if key == "packs":
            return _page_local(self._packs_entries(), page, rows)
        if key == "toronto":
            return _page_local(self._toronto_entries(), page, rows)
        if key == "jungletapes":
            return _page_local(self._jungletapes_entries(), page, rows)
        if key == "ravetapepacks":
            return _page_local(self._ravetapepacks_entries(), page, rows)
        if key == "pirate":
            return _page_local(self._pirate_entries(), page, rows)
        if key == "mixes":
            return _page_local(self._mixes_entries(), page, rows)
        if key == "filters":
            return _page_local(self._filter_index_entries(), page, rows)
        if key == "raves":
            return _page_local(self._rave_index_entries(), page, rows)
        if key == "packs_years":
            return _page_local(self._year_index_entries(), page, rows)
        if key == "live_tags":
            return _page_local(self._live_tag_index_entries(), page, rows)
        raise ValueError("unknown Rave Screen room %r" % key)

    def load(self, target, page=1, rows=None):
        """Return one :class:`Page` for a room key, folder Entry or search."""
        if target is None or target == "":
            entries = list(self.home_rows())
            return Page(entries, len(entries), 1, 1, len(entries) or 1)
        if isinstance(target, SearchTarget):
            raise ValueError("Search is owned by raveui.screens.library")
        if isinstance(target, str):
            return self.room(target, page, rows)
        return self.children(target, page, rows)

    def section_entries(self, key):
        """Compatibility view for older callers/tests: room page one."""
        return self.room(key, 1).rows

    def entries_for(self, entry):
        """Compatibility view: one folder's first page."""
        return self.children(entry, 1).rows

    # ---------------------------------------------------------- classic doors
    def _classic(self, name, fallback=()):
        try:
            return list(getattr(self.modules.routes, name)() or fallback)
        except Exception:  # noqa: BLE001 - old plugin without the helper
            return list(fallback)

    def _packs_entries(self):
        def door(key, label, subtitle, art, hero, fact, code, plot,
                 kind="section", source=None, target=None):
            return Entry(key, label, subtitle, self._art(art), kind,
                         source=source or target or key,
                         target=target or key, hero=self._art(hero),
                         fact=fact, code=code, plot=plot,
                         meta=_meta(fact.upper(), "TAPE PACKS", code))

        filter_count = len(self._classic("classic_filters"))
        rave_count = len(self._classic("classic_raves"))
        return [
            door("pack-toronto", "Toronto Rave Mixtape Archive",
                 "1990–2014 · jungle, house and X-Static tapes",
                 "toronto.png", "fanart-toronto.jpg", "1990–2014", "RP-19",
                 "Toronto rave mixtapes, 1990–2014.", target="toronto"),
            door("pack-jungletapes", "JungleTapes.com",
                 "Toronto jungle radio digitised from cassette",
                 "jungletapes.png", "fanart-tapepacks.jpg", "310 shows", "RP-27",
                 "Toronto jungle radio shows, digitised from cassette.",
                 target="jungletapes"),
            door("pack-ravetapepacks", "RaveTapePacks.com",
                 "UK tape packs, 1992–2004 · by event, DJ, MC and year",
                 "ravetapepacks.png", "fanart-tapepacks.jpg", "1992–2004", "RP-03",
                 "The UK rave tape-pack archive, filed every way.",
                 target="ravetapepacks"),
            door("pack-20bensons", "20bensons.com",
                 "Old-skool rave MP3s · web archive",
                 "20bensons.png", "fanart-hub-packs.jpg", "web archive", "RP-43",
                 "Old-skool rave MP3s from 20bensons.com, in homepage order.",
                 kind="web_list", source="web_20bensons", target="20bensons"),
            door("pack-ukraves", "UK Raves Downloads",
                 "UK Raves event sets · Mediafire via the web proxy",
                 "ukraves.png", "fanart-hub-packs.jpg", "web sets", "RP-44",
                 "UK Raves event downloads; Mediafire sets play through the "
                 "web service's /stream proxy.",
                 kind="web_list", source="web_ukraves", target="ukraves"),
            door("pack-ezgarage", "EZ Garage Sets",
                 "DJ EZ and old-skool garage · DNBForum thread",
                 "ezgarage.png", "fanart-hub-packs.jpg", "web sets", "RP-45",
                 "DJ EZ and old-skool garage sets from the DNBForum thread.",
                 kind="web_list", source="web_ezgarage", target="ezgarage"),
            door("pack-series", "Classic Pack Series",
                 "Dreamscape · Helter Skelter · Fantazia · One Nation",
                 "series.png", "fanart-hub-packs.jpg",
                 _fact("%d series" % filter_count if filter_count else "series"),
                 "RP-39",
                 "The UK pack canon, one filter per series.",
                 kind="filter_index", target="filters"),
            door("pack-raves", "By Rave, Venue & Promoter",
                 "Sanctuary · Bagleys · Bowlers · Que Club · Biology",
                 "rave-nights.png", "fanart-hub-packs.jpg",
                 _fact("%d raves" % rave_count if rave_count else "raves"),
                 "RP-40",
                 "Browse the researched rave catalogue one event at a time.",
                 kind="rave_index", target="raves"),
            door("pack-years", "By Year",
                 "Browse the Archive one year at a time, 1987–now",
                 "years.png", "fanart-hub-packs.jpg", "1987–now", "RP-41",
                 "Every year the Archive has tape packs for.",
                 kind="year_index", target="packs_years"),
            door("pack-every", "Every Pack",
                 "Everything the Archive tags as a tape pack",
                 "tapepacks-all.png", "fanart-tapepacks.jpg", "archive.org", "RP-42",
                 "Archive mixtapes — the broad Every Pack query.",
                 kind="archive_search", target="tapepacks"),
        ]

    def _pirate_entries(self):
        return [
            Entry("pirate-hardscore", "Hardscore",
                  "The best 1990s pirate archive: Kool FM, Don FM, Green Apple",
                  self._art("hardscore.png"), "folder",
                  source="hardscore_source", target="hardscore_source",
                  hero=self._art("fanart-hardscore.jpg"), fact="archive",
                  code="RP-32", plot="Oldskool hardcore and jungle archive.",
                  meta=_meta("ARCHIVE", "HARDSCORE.COM", "RP-32")),
            Entry("pirate-archives", "Pirate Radio Archives",
                  "Risk FM · Weekend Rush · Flava FM · 1990s recordings",
                  self._art("pirate-archive.png"), "folder",
                  source="pirate_source", target="pirate_source",
                  hero=self._art("fanart-pirate-archive.jpg"), fact="1990s",
                  code="RP-32", plot="Curated 1990s pirate-radio recordings.",
                  meta=_meta("1990S", "PIRATE ARCHIVES", "RP-32")),
            Entry("pirate-kool", "Kool FM Sets",
                  "Every Kool FM set in the Archive",
                  self._art("kool.png"), "filter",
                  source="filter", target="kool",
                  hero=self._art("fanart-live.jpg"), fact="sets",
                  code="RP-31", plot="Kool FM archive sets, live door included.",
                  meta=_meta("SETS", "KOOL FM", "RP-31")),
        ]

    def _filter_index_entries(self):
        entries = []
        for item in self._classic("classic_filters"):
            key = _text(item.get("id"))
            if not key:
                continue
            entries.append(Entry(
                key="filter-%s" % key,
                label=_text(item.get("name"), key),
                subtitle="Classic Pack Series",
                art=self._art(_text(item.get("art"), "series.png")),
                kind="filter", source="filter", target=key,
                hero=self._art(_text(item.get("fanart"), "fanart-hub-packs.jpg")),
                fact="series", code="RP-39",
                plot=_text(item.get("plot"), "Classic pack series"),
                meta=_meta("SERIES", "CLASSIC PACKS", "RP-39")))
        return entries

    def _rave_index_entries(self):
        entries = []
        for item in self._classic("classic_raves"):
            name = _text(item.get("name"))
            slug = _text(item.get("slug"))
            if not name or not slug:
                continue
            counts = []
            if item.get("count"):
                counts.append("%d packs" % item["count"])
            if item.get("mixcloud_count"):
                counts.append("%d sets" % item["mixcloud_count"])
            entries.append(Entry(
                key="rave-%s" % slug,
                label=name,
                subtitle="By rave, venue & promoter",
                art=self._art("rave-nights.png"),
                kind="rave", source="rave", target=slug,
                hero=self._art("fanart-hub-packs.jpg"),
                fact=_fact(" · ".join(counts) or "rave", "rave"),
                code="RP-40", plot="Archive packs and Mixcloud sets for %s" % name,
                meta=_meta(" · ".join(counts).upper() or "RAVE", "RAVE CATALOGUE",
                           "RP-40")))
        return entries

    def _year_index_entries(self):
        entries = []
        for year in self._classic("classic_years"):
            text = _text(year)
            if not text:
                continue
            entries.append(Entry(
                key="year-%s" % text,
                label=text,
                subtitle="By Year · Archive tape packs",
                art=self._art("years.png"),
                kind="year", source="year", target=text,
                hero=self._art("fanart-hub-packs.jpg"),
                fact="tape packs", code="RP-41",
                plot="%s tape packs from the Internet Archive" % text,
                meta=_meta("YEAR", "ARCHIVE.ORG", "RP-41")))
        return entries

    def _live_tag_index_entries(self):
        entries = []
        for section in self._classic("classic_radio_sections"):
            key = _text(section.get("key"))
            if not key:
                continue
            entries.append(Entry(
                key="live-tag-%s" % key,
                label=_text(section.get("label"), key),
                subtitle="Live Radio · genre door",
                art=self._art(_text(section.get("art"), "radio.png")),
                kind="live_tag", source="live_tag", target=key,
                hero=self._art("fanart-hub-live.jpg"),
                fact="stations", code="RP-31",
                plot=_text(section.get("plot"), "Live %s stations" % key),
                meta=_meta("LIVE", "GENRE", "RP-31")))
        return entries

    # -------------------------------------------------------------- latest
    def _latest_entries(self):
        try:
            packs = self.modules.latest.recent_packs(rows=100)
        except Exception:  # noqa: BLE001 - quiet empty plate
            return []
        cache = self.surprise_cache
        if cache is not None:
            try:
                cache.remember_latest(packs)
            except Exception:  # noqa: BLE001 - a cache miss is never fatal
                pass
        entries = []
        for row in packs or []:
            identifier = _text(row.get("identifier"))
            if not identifier:
                continue
            year = _text(row.get("year")) or _year_from_text(row.get("date"))
            entries.append(Entry(
                key=identifier,
                label=_text(row.get("title"), identifier),
                subtitle="Internet Archive · tape pack",
                art=self._archive_thumb(identifier),
                kind="pack", source="latest", target=identifier,
                hero=self._art("fanart-latest.jpg"),
                fact=_fact(year or "pack", "pack"),
                code="RP-01",
                plot="Tape pack from the Internet Archive" + (
                    " · " + year if year else ""),
                meta=_meta(year, "INTERNET ARCHIVE", "RP-01"),
                year=year))
        return entries

    # -------------------------------------------------------------- toronto
    def _toronto_entries(self):
        try:
            rows = self.modules.toronto.genres() or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            return []
        entries = []
        for row in rows:
            genre = _text(row.get("genre"))
            if not genre:
                continue
            entries.append(Entry(
                key=genre,
                label=_text(row.get("label"), genre.replace("-", " ").title()),
                subtitle="Toronto genre · direct MP3s",
                art=self._art("toronto.png"),
                kind="genre", source="toronto", target=genre,
                hero=self._art("fanart-toronto.jpg"),
                fact="genre", code="RP-19",
                plot="Toronto rave mixtape genre",
                meta=_meta("GENRE", "TORONTO", "RP-19")))
        return entries

    def _toronto_genre_entries(self, genre):
        try:
            tracks = self.modules.toronto.tracks(genre) or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            return []
        entries = []
        for track in tracks:
            if not isinstance(track, dict):
                continue
            url = self._safe_url(track.get("url"))
            if not url:
                continue
            duration = _duration_from_metadata(track.get("metadata"))
            year = _year_from_text(track.get("name"), track.get("metadata"))
            entries.append(self._track_entry(
                {"name": track.get("name"), "url": url, "duration": duration,
                 "year": year},
                parent_label="Toronto Rave Mixtape Archive",
                parent_key="toronto:%s" % genre,
                source="toronto", art=self._art("toronto.png"),
                hero=self._art("fanart-toronto.jpg"), code="RP-19",
                plot="Toronto rave mixtape · direct MP3"))
        return [entry for entry in entries if entry is not None]

    # ---------------------------------------------------------- jungletapes
    def _jungletapes_entries(self):
        try:
            rows = self.modules.legacy.jungle_shows() or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            return []
        entries = []
        for row in rows:
            key = _text(row.get("key"))
            if not key:
                continue
            name = _text(row.get("name"), key)
            year = _year_from_text(name)
            entries.append(Entry(
                key=key,
                label=name,
                subtitle="JungleTapes.com show",
                art=self._art("jungletapes.png"),
                kind="show", source="jungletapes", target=key,
                hero=self._neutral_hero(),
                fact=_fact(year or "show", "show"),
                code="RP-27",
                plot="Toronto jungle radio show on JungleTapes.com",
                meta=_meta(year, "JUNGLETAPES.COM", "RP-27"),
                year=year))
        return entries

    def _jungle_show_entries(self, key, label=""):
        try:
            tracks = self.modules.legacy.jungle_tracks(key) or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            return []
        entries = []
        for track in tracks:
            if not isinstance(track, dict):
                continue
            url = self._safe_url(track.get("url"))
            if not url:
                continue
            entries.append(self._track_entry(
                {"name": track.get("name"), "url": url},
                parent_label=label or "JungleTapes.com",
                parent_key="jungletapes:%s" % key,
                source="jungletapes", art=self._art("jungletapes.png"),
                hero=self._neutral_hero(), code="RP-27",
                plot="Toronto jungle radio, digitised from cassette"))
        return [entry for entry in entries if entry is not None]

    # -------------------------------------------------------- ravetapepacks
    def _ravetapepacks_entries(self):
        entries = []
        try:
            categories = self.modules.legacy.categories() or {}
        except Exception:  # noqa: BLE001 - the doors still work without counts
            categories = {}
        for kind, label, art in (
                ("events", "By Event", "rave-nights.png"),
                ("djs", "By DJ", "sets.png"),
                ("mcs", "By MC", "tapepacks.png"),
                ("years", "By Year", "years.png")):
            count = len(categories.get(kind) or [])
            entries.append(Entry(
                key="rtp-index-%s" % kind,
                label="%s (%d)" % (label, count) if count else label,
                subtitle="RaveTapePacks.com · full index",
                art=self._art(art),
                kind="rtp_index", source="ravetapepacks", target=kind,
                hero=self._art("fanart-tapepacks.jpg"),
                fact=_fact("%d categories" % count if count else "index"),
                code="RP-03",
                plot="Browse every %s in the RaveTapePacks archive" %
                     label.replace("By ", ""),
                meta=_meta("INDEX", "RAVETAPEPACKS.COM", "RP-03")))
        entries.append(Entry(
            key="rtp-index-all",
            label="All Packs",
            subtitle="Every RaveTapePacks pack, newest first",
            art=self._art("tapepacks-all.png"),
            kind="rtp_index", source="ravetapepacks", target="all",
            hero=self._art("fanart-tapepacks.jpg"),
            fact="archive", code="RP-03",
            plot="The complete RaveTapePacks blog archive, one cursor page at a time",
            meta=_meta("ARCHIVE", "RAVETAPEPACKS.COM", "RP-03")))
        return entries

    def _rtp_index_children(self, entry, page, rows):
        kind = _text(entry.target)
        if kind == "all":
            return self._rtp_all_page(page, rows)
        try:
            categories = self.modules.legacy.categories() or {}
        except Exception:  # noqa: BLE001 - empty plate
            return _page_local([], page, rows)
        labels = {"events": "By Event", "djs": "By DJ",
                  "mcs": "By MC", "years": "By Year"}
        entries = []
        for row in categories.get(kind) or []:
            cat_id = _text(row.get("id"))
            if not cat_id:
                continue
            name = _text(row.get("name"), cat_id)
            entries.append(Entry(
                key="rtp-%s-%s" % (kind, cat_id),
                label=name,
                subtitle="RaveTapePacks.com · %s" % labels.get(kind, "index"),
                art=self._art("ravetapepacks.png"),
                kind="rtp_category", source="ravetapepacks",
                target="%s:%s" % (kind, cat_id),
                hero=self._art("fanart-tapepacks.jpg"),
                fact="index", code="RP-03",
                plot="RaveTapePacks packs filed under %s" % name,
                meta=_meta(labels.get(kind, "INDEX").upper(),
                           "RAVETAPEPACKS.COM", "RP-03")))
        return _page_local(entries, page, rows)

    def _rtp_category_children(self, entry, page, rows):
        parts = _text(entry.target).split(":")
        if len(parts) != 2:
            return _page_server([], page, rows, 0)
        kind, cat_id = parts
        try:
            posts, next_url = self.modules.legacy.category_page(cat_id, page)
        except Exception:  # noqa: BLE001 - quiet empty plate
            return _page_server([], page, rows, 0)
        if posts is None:
            return _page_server([], page, rows, 0)
        return _page_server(self._rtp_posts(posts, kind=kind),
                            page, rows, 0, has_next=bool(next_url),
                            cursor=_text(next_url))

    def _rtp_all_page(self, page, rows):
        try:
            posts, next_url = self.modules.legacy.all_packs(page)
        except Exception:  # noqa: BLE001 - quiet empty plate
            return _page_server([], page, rows, 0)
        if posts is None:
            return _page_server([], page, rows, 0)
        return _page_server(self._rtp_posts(posts, kind="all"),
                            page, rows, 0, has_next=bool(next_url),
                            cursor=_text(next_url))

    def _rtp_posts(self, posts, kind="all"):
        rows = []
        for post in posts or []:
            if not isinstance(post, dict):
                continue
            post_id = _text(post.get("id"))
            if not post_id:
                continue
            name = _text(post.get("name"), "Pack %s" % post_id)
            year = _year_from_text(name)
            rows.append(Entry(
                key="rtp-post-%s" % post_id,
                label=name,
                subtitle="RaveTapePacks.com pack",
                art=self._art("ravetapepacks.png"),
                kind="rtp_post", source="ravetapepacks", target=post_id,
                hero=self._art("fanart-tapepacks.jpg"),
                fact=_fact(year or "pack", "pack"),
                code="RP-03",
                plot="UK rave tape pack on RaveTapePacks.com",
                meta=_meta(year, "RAVETAPEPACKS.COM", "RP-03"),
                year=year))
        return rows

    def _rtp_post_children(self, entry, page, rows):
        try:
            post = self.modules.legacy.post(entry.target)
        except Exception:  # noqa: BLE001 - quiet empty plate
            return _page_local([], page, rows)
        if not post:
            return _page_local([], page, rows)
        parent = _text(post.get("name"), entry.label)
        tracks = []
        for track in post.get("tracks") or []:
            if not isinstance(track, dict):
                continue
            candidate = dict(track)
            try:
                candidate["url"] = self.modules.legacy.playable(
                    track.get("url", ""))
            except Exception:  # noqa: BLE001 - skip unbuildable row
                continue
            tracks.append(candidate)
        entries = []
        for track in tracks:
            entries.append(self._track_entry(
                {"name": track.get("name"), "url": track.get("url"),
                 "year": _year_from_text(parent)},
                parent_label=parent,
                parent_key="rtp:%s" % entry.target,
                source="ravetapepacks", art=self._art("ravetapepacks.png"),
                hero=self._art("fanart-tapepacks.jpg"), code="RP-03",
                plot="UK rave tape pack · RaveTapePacks.com"))
        return _page_local([e for e in entries if e is not None], page, rows)

    # ---------------------------------------------------------------- mixes
    def _mixes_entries(self):
        def source(key, label, subtitle, art, fact, plot, hero, code="RP-32"):
            return Entry(key, label, subtitle, self._art(art), "folder",
                         source=key, target=key, hero=self._art(hero),
                         fact=fact, code=code, plot=plot,
                         meta=_meta(fact.upper(), "MIXES & SHOWS", code))

        return [
            source("dnb_source", "DNBRADIO Shows",
                   "24/7 jungle and drum & bass plus the show archive",
                   "dnb.png", "shows", "DNBRADIO.com show archive",
                   "fanart-mixes.jpg"),
            source("feeds_source", "Podcasts & Mixes",
                   "Current jungle, drum & bass, hardcore and rave RSS feeds",
                   "podcasts.png", "feeds",
                   "Podcast and mix RSS feeds, newest episodes first",
                   "fanart-hub-shows.jpg"),
            Entry("web-dejavu", "DejaVu FM Archive",
                  "Live rave radio · full show archive",
                  self._art("dejavu.png"), "web_feed",
                  source="web_dejavu", target="dejavu",
                  hero=self._art("fanart-hub-shows.jpg"), fact="podcast",
                  code="RP-46",
                  plot="The DejaVu FM show archive, newest episodes first.",
                  meta=_meta("PODCAST", "DEJAVU FM", "RP-46")),
            source("moxser_source", "Moxser",
                   "Old skool to new cool dance mixes · direct MP3s",
                   "moxser.png", "mixes", "Moxser.com mix archive",
                   "fanart-moxser.jpg"),
            source("hardscore_source", "Hardscore",
                   "Oldskool hardcore and jungle archive · direct files",
                   "hardscore.png", "sets", "Hardscore.com archive",
                   "fanart-hardscore.jpg"),
            source("getdarker_source", "GetDarker",
                   "Dubstep and grime, 2003 onwards · Mixcloud hand-off",
                   "getdarker.png", "sets", "GetDarker.com archive",
                   "fanart-getdarker.jpg"),
            source("pirate_source", "Pirate Radio Archives",
                   "Risk FM, Weekend Rush, Flava FM · 1990s recordings",
                   "pirate-archive.png", "1990s",
                   "Curated 1990s pirate-radio recordings",
                   "fanart-pirate-archive.jpg"),
            Entry("mikus_source", "Mikus Musik",
                  "Dub, jungle, house and garage sets from the blog",
                  self._art("podcasts.png"), "blog_source",
                  source="mikus_source", target="mikus",
                  hero=self._art("fanart-hub-shows.jpg"), fact="blog",
                  code="RP-32", plot="Mikus Musik blog archive",
                  meta=_meta("BLOG", "MIKUS MUSIK", "RP-32")),
            Entry("demodulated_source", "Demodulated Mixtapes",
                  "Old techno, jungle and rave mixtapes",
                  self._art("legacy.png"), "blog_source",
                  source="demodulated_source", target="demodulated",
                  hero=self._art("fanart-mixes.jpg"), fact="mixtapes",
                  code="RP-32", plot="Demodulated Mixtapes blog archive",
                  meta=_meta("BLOG", "DEMODULATED", "RP-32")),
        ]

    def _mixes_children(self, entry, page, rows):
        key = _text(entry.target)
        if getattr(entry, "kind", "") == "hardscore_post":
            key = "hardscore_post"
        if key == "dnb_source":
            try:
                shows = self.modules.dnbradio.mixes() or []
            except Exception:  # noqa: BLE001 - quiet empty plate
                return _page_local([], page, rows)
            out = []
            for show in shows:
                if not isinstance(show, dict) or not show.get("id"):
                    continue
                title = _text(show.get("title"), "DNBRADIO show")
                date = _text(show.get("date"))
                out.append(Entry(
                    key="dnb-%s" % show["id"],
                    label=title,
                    subtitle="DNBRADIO.com show",
                    art=self._art("dnb.png"),
                    kind="dnb_show", source="dnb", target=str(show["id"]),
                    hero=self._art("fanart-mixes.jpg"),
                    fact=_fact(date or "show", "show"),
                    code="RP-32",
                    plot="DNBRADIO.com archive show",
                    meta=_meta(date, "DNBRADIO.COM", "RP-32"), year=date[:4]))
            return _page_local(out, page, rows)
        if key == "feeds_source":
            try:
                feeds = self.modules.feeds.registry() or []
            except Exception:  # noqa: BLE001 - quiet empty plate
                return _page_local([], page, rows)
            out = []
            for feed in feeds:
                feed_id = _text(feed.get("id"))
                if not feed_id:
                    continue
                out.append(Entry(
                    key="feed-%s" % feed_id,
                    label=_text(feed.get("name"), feed_id),
                    subtitle="Podcast / mix feed",
                    art=self._art("podcasts.png"),
                    kind="feed", source="feeds", target=feed_id,
                    hero=self._art("fanart-hub-shows.jpg"),
                    fact="feed", code="RP-32",
                    plot=_text(feed.get("plot"), "Podcast and mix feed"),
                    meta=_meta("PODCAST", "RSS", "RP-32")))
            return _page_local(out, page, rows)
        if key == "moxser_source":
            try:
                mixes = self.modules.moxser.mixes(limit=200) or []
            except Exception:  # noqa: BLE001 - quiet empty plate
                return _page_local([], page, rows)
            out = []
            for mix in mixes:
                if not isinstance(mix, dict) or not mix.get("page_url"):
                    continue
                date = _text(mix.get("date"))
                out.append(Entry(
                    key="moxser-%s" % mix["page_url"],
                    label=_text(mix.get("title"), "Moxser mix"),
                    subtitle="Moxser.com mix",
                    art=_text(mix.get("flyer")) or self._art("moxser.png"),
                    kind="moxser_mix", source="moxser", target=mix["page_url"],
                    hero=self._art("fanart-moxser.jpg"),
                    fact=_fact(date or "mix", "mix"),
                    code="RP-32",
                    plot="Moxser.com dance mix",
                    meta=_meta(date, "MOXSER.COM", "RP-32"), year=date[:4]))
            return _page_local(out, page, rows)
        if key == "hardscore_source":
            try:
                items = self.modules.hardscore.items(limit=200) or []
            except Exception:  # noqa: BLE001 - quiet empty plate
                return _page_local([], page, rows)
            out = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                page_url = _text(item.get("page_url"))
                if not page_url:
                    continue
                out.append(Entry(
                    key="hardscore-%s" % page_url,
                    label=_text(item.get("title"), "Hardscore post"),
                    subtitle="Hardscore.com post",
                    art=self._art("hardscore.png"),
                    kind="hardscore_post", source="hardscore", target=page_url,
                    hero=self._art("fanart-hardscore.jpg"),
                    fact=_fact(_text(item.get("date")) or "post", "post"),
                    code="RP-32",
                    plot="Hardscore.com oldskool archive post",
                    meta=_meta(_text(item.get("date")), "HARDSCORE.COM", "RP-32")))
            return _page_local(out, page, rows)
        if key == "hardscore_post":
            try:
                page_data = self.modules.hardscore.page(entry.target)
            except Exception:  # noqa: BLE001 - quiet empty plate
                page_data = {}
            return self._media_page(page_data, page, rows, source="hardscore",
                                    art=self._art("hardscore.png"),
                                    hero=self._art("fanart-hardscore.jpg"),
                                    label="Hardscore.com")
        if key == "getdarker_source":
            try:
                items = self.modules.getdarker.items(limit=200) or []
            except Exception:  # noqa: BLE001 - quiet empty plate
                return _page_local([], page, rows)
            return _page_local(self._platform_rows(items, "getdarker"), page, rows)
        if key == "pirate_source":
            try:
                items = self.modules.pirate.entries() or []
            except Exception:  # noqa: BLE001 - quiet empty plate
                return _page_local([], page, rows)
            out = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = self._safe_url(item.get("stream_url"))
                if not url:
                    continue
                title = _text(item.get("title"), "Pirate radio recording")
                year = _text(item.get("year"))
                out.append(self._track_entry(
                    {"name": title, "url": url, "year": year},
                    parent_label=_text(item.get("station"), "Pirate Radio Archives"),
                    parent_key="pirate:%s" % url,
                    source="pirate", art=self._art("pirate-archive.png"),
                    hero=self._art("fanart-pirate-archive.jpg"), code="RP-32",
                    plot="1990s pirate-radio recording"))
            return _page_local([e for e in out if e is not None], page, rows)
        return _page_local([], page, rows)

    def _media_page(self, page_data, page, rows, source, art, hero, label):
        media = page_data.get("media_urls") or []
        entries = []
        for url in media:
            safe = self._safe_url(url)
            if not safe:
                continue
            entries.append(self._track_entry(
                {"name": page_data.get("title"), "url": safe},
                parent_label=label,
                parent_key="%s:%s" % (source, page_data.get("url")),
                source=source, art=art, hero=hero, code="RP-32",
                plot="%s set" % label))
        for link in page_data.get("links") or []:
            platform = ""
            try:
                platform = self.modules.handoff.platform_kind(link)
                target = self.modules.handoff.target(link, page_data.get("title", ""))
            except Exception:  # noqa: BLE001 - missing hand-off add-on
                target = ""
            if not target:
                continue
            entries.append(Entry(
                key="external-%s" % link,
                label=_text(page_data.get("title"), "Open in add-on"),
                subtitle="%s · %s" % (label, platform or "add-on"),
                art=art,
                kind="external", source=source, target=link,
                track=Track(_text(page_data.get("title"), "External set"),
                            label, link, art, source=source, path=target),
                hero=hero, fact=_fact(platform or "add-on"),
                code="RP-32",
                plot="Opens in the %s Kodi add-on" % (platform or "hand-off"),
                meta=_meta((platform or "ADD-ON").upper(), label.upper(), "RP-32")))
        return _page_local([e for e in entries if e is not None], page, rows)

    def _platform_rows(self, items, source):
        out = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            page_url = _text(item.get("page_url"))
            if not page_url:
                continue
            title = _text(item.get("title"), "GetDarker set")
            media = item.get("media_urls") or []
            if media:
                for url in media:
                    safe = self._safe_url(url)
                    if not safe:
                        continue
                    out.append(self._track_entry(
                        {"name": title, "url": safe},
                        parent_label="GetDarker", parent_key="getdarker:%s" % page_url,
                        source="getdarker", art=self._art("getdarker.png"),
                        hero=self._art("fanart-getdarker.jpg"), code="RP-32",
                        plot="GetDarker set"))
                continue
            try:
                kind = self.modules.handoff.platform_kind(page_url)
                target = self.modules.handoff.target(page_url, title)
            except Exception:  # noqa: BLE001 - missing hand-off add-on
                kind, target = "", ""
            if not target:
                continue
            out.append(Entry(
                key="external-%s" % page_url,
                label=title,
                subtitle="GetDarker · %s" % (kind or "add-on"),
                art=self._art("getdarker.png"),
                kind="external", source="getdarker", target=page_url,
                track=Track(title, "GetDarker", page_url,
                            self._art("getdarker.png"), source="getdarker",
                            path=target),
                hero=self._art("fanart-getdarker.jpg"),
                fact=_fact(kind or "add-on"),
                code="RP-32",
                plot="Opens in the %s Kodi add-on" % (kind or "hand-off"),
                meta=_meta((kind or "ADD-ON").upper(), "GETDARKER", "RP-32")))
        return [e for e in out if e is not None]

    def _feed_children(self, entry, page, rows):
        try:
            episodes = self.modules.feeds.episodes(entry.target, limit=200) or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            return _page_local([], page, rows)
        out = []
        for episode in episodes:
            if not isinstance(episode, dict):
                continue
            url = self._safe_url(episode.get("url"))
            if not url:
                continue
            title = _text(episode.get("title"), "Episode")
            published = _text(episode.get("published"))
            out.append(self._track_entry(
                {"name": title, "url": url,
                 "duration": episode.get("duration"),
                 "year": _year_from_text(published)},
                parent_label=entry.label,
                parent_key="feed:%s" % entry.target,
                source="feeds", art=self._art("podcasts.png"),
                hero=self._art("fanart-hub-shows.jpg"), code="RP-32",
                plot=_text(episode.get("description"), entry.label)))
        return _page_local([e for e in out if e is not None], page, rows)

    # ----------------------------------------------------------- favourites
    def favourite_payload(self, entry):
        """Map a row to the plugin's favourites JSON contract, or ``None``."""
        kind = getattr(entry, "kind", "")
        target = _text(getattr(entry, "target", ""))
        label = _text(getattr(entry, "label", ""))
        source = _text(getattr(entry, "source", ""))
        if entry.track is not None and getattr(entry.track, "url", ""):
            track_source = _text(getattr(entry.track, "source", "")) or source
            display = "Live radio · %s" % label if getattr(entry.track, "live", False) \
                else _SOURCE_LABEL.get(track_source, "Rave Player")
            return {"kind": "stream", "target": entry.track.url, "title": label,
                    "source": display}
        if kind == "station":
            # A live row carries its stream in the module action, not in
            # ``entry.track`` (P2-11).  Save it as a normal stream favourite so
            # the saved row plays through the same one playback policy.
            action = getattr(entry, "action", None)
            if isinstance(action, dict):
                url = _text(action.get("url"))
                if url:
                    station = _text(action.get("station")) or target
                    title = _text(action.get("title")) or label
                    return {"kind": "stream", "target": url, "title": title,
                            "source": "Live radio · %s" % station}
        if kind == "pack" and source == "latest":
            return {"kind": "pack", "target": target, "title": label,
                    "source": "Archive.org"}
        if kind == "pack" and source == "ravetapepacks":
            return {"kind": "legacy_pack", "target": target, "title": label,
                    "source": "RaveTapePacks.com"}
        if kind == "rtp_post":
            return {"kind": "legacy_post", "target": target, "title": label,
                    "source": "RaveTapePacks.com"}
        if kind == "show" and source == "jungletapes":
            return {"kind": "legacy_jt", "target": target, "title": label,
                    "source": "JungleTapes.com"}
        if kind == "dnb_show":
            return {"kind": "dnb", "target": target, "title": label,
                    "source": "DNB Radio"}
        if kind == "external":
            return {"kind": "stream", "target": target, "title": label,
                    "source": "add-on"}
        return None

    def add_favourite(self, entry):
        payload = self.favourite_payload(entry)
        if payload is None:
            return False, "This row cannot be saved to favourites."
        try:
            already = bool(self.modules.favourites.has(payload))
            saved = bool(self.modules.favourites.add(payload))
        except Exception:  # noqa: BLE001 - profile may be read-only
            return False, "Could not save that favourite."
        if not saved:
            return False, "Could not save that favourite."
        return True, "Already in favourites" if already else "Added to favourites"

    def remove_favourite(self, entry_key):
        try:
            saved = bool(self.modules.favourites.remove(str(entry_key or "")))
        except Exception:  # noqa: BLE001 - profile may be read-only
            return False
        return saved

    # ------------------------------------------------------------ downloads
    def start_download(self, entry):
        queue = self._download_queue
        if queue is None:
            return False, "Downloads are not available in this build."
        track = getattr(entry, "track", None)
        if track is None or getattr(track, "live", False):
            return False, "That row is not a downloadable file."
        url = _text(getattr(track, "url", ""))
        source = _text(getattr(track, "download_source", ""))
        if not url or not source:
            return False, "That source is not downloadable."
        try:
            return queue.start(url, _text(entry.label, "Rave Player download"),
                               source, key=_text(entry.key) or url)
        except Exception as exc:  # noqa: BLE001 - queue failure is a status line
            return False, "Could not start the download (%s)." % exc

    def cancel_download(self, key):
        queue = self._download_queue
        if queue is None:
            return False
        try:
            return bool(queue.cancel(key))
        except Exception:  # noqa: BLE001 - advisory
            return False

    def delete_download(self, key):
        try:
            return bool(self.modules.downloads.delete(key))
        except Exception:  # noqa: BLE001 - file/profile unavailable
            return False

    # -------------------------------------------------------------- children
    def children(self, entry, page=1, rows=None):
        rows = rows or self.rows_per_page
        kind = getattr(entry, "kind", "")
        source = getattr(entry, "source", "")
        if kind == "genre":
            return _page_local(self._toronto_genre_entries(entry.target), page, rows)
        if kind == "show":
            return _page_local(
                self._jungle_show_entries(entry.target, entry.label), page, rows)
        if kind == "pack" and source == "ravetapepacks":
            try:
                pack = self.modules.legacy.pack(entry.target) or {}
            except Exception:  # noqa: BLE001 - quiet empty plate
                pack = {}
            tracks = []
            for track in pack.get("tracks") or []:
                candidate = dict(track)
                try:
                    candidate["url"] = self.modules.legacy.playable(
                        track.get("url", ""))
                except Exception:  # noqa: BLE001 - skip unbuildable row
                    continue
                tracks.append(candidate)
            entries = []
            for track in tracks:
                entries.append(self._track_entry(
                    {"name": track.get("name"), "url": track.get("url"),
                     "year": _year_from_text(entry.label)},
                    parent_label=entry.label,
                    parent_key="rtp-pack:%s" % entry.target,
                    source="ravetapepacks",
                    art=self._art("ravetapepacks.png"),
                    hero=self._art("fanart-tapepacks.jpg"), code="RP-03",
                    plot="UK rave tape pack · RaveTapePacks.com"))
            return _page_local([e for e in entries if e is not None], page, rows)
        if kind == "pack" and source == "latest":
            try:
                tracks = self.modules.archive.audio_files(entry.target) or []
            except Exception:  # noqa: BLE001 - quiet empty plate
                return _page_local([], page, rows)
            return _page_local(self._archive_track_entries(
                tracks, entry.target, entry.label, entry.year), page, rows)
        if kind == "rtp_index":
            return self._rtp_index_children(entry, page, rows)
        if kind == "rtp_category":
            return self._rtp_category_children(entry, page, rows)
        if kind == "rtp_post":
            return self._rtp_post_children(entry, page, rows)
        if kind == "feed":
            return self._feed_children(entry, page, rows)
        if kind == "folder":
            return self._mixes_children(entry, page, rows)
        if kind == "hardscore_post":
            return self._mixes_children(entry, page, rows)
        if kind == "filter_index":
            return _page_local(self._filter_index_entries(), page, rows)
        if kind == "rave_index":
            return _page_local(self._rave_index_entries(), page, rows)
        if kind == "year_index":
            return _page_local(self._year_index_entries(), page, rows)
        if kind == "filter":
            return self._filter_children(entry, page, rows)
        if kind == "filter_live":
            return self._filter_live_children(entry, page, rows)
        if kind == "rave":
            return self._rave_children(entry, page, rows)
        if kind == "year":
            return self._year_children(entry, page, rows)
        if kind == "archive_search":
            return self._archive_search_children(entry, page, rows)
        if kind == "live_tag":
            return self._live_tag_children(entry, page, rows)
        if kind == "blog_source":
            return self._blog_posts(_text(entry.label), _text(entry.target),
                                    page, rows)
        if kind == "blog_post":
            return self._blog_post_children(entry, page, rows)
        if kind in ("web_list", "web_feed"):
            return self._web_children(entry, page, rows)
        return _page_local([], page, rows)

    # --------------------------------------------------------- web sources
    def _web_children(self, entry, page, rows):
        """One page of a web-only source (20bensons/UK Raves/EZ Garage/DejaVu)."""
        source = _text(entry.target)
        try:
            page_data = self.modules.routes.web_source_page(source, page)
        except Exception:  # noqa: BLE001 - quiet empty plate
            page_data = None
        if not isinstance(page_data, dict):
            return _page_server([], page, rows, 0)
        track_source = _text(entry.source, "web_%s" % source)
        label = _text(entry.label, source)
        download_source = ""
        if track_source == "web_dejavu":
            download_source = "Rave Resolver"
        art = entry.art or self._art("rave.png")
        hero = entry.hero or art
        entries = []
        for row in page_data.get("rows") or []:
            if not isinstance(row, dict):
                continue
            url = _text(row.get("url"))
            if not url:
                continue
            title = _text(row.get("label"), "Untitled")
            row_sub = _text(row.get("sub") or row.get("plot"))
            # Web rows already carry "event/venue · date · source".  Put the
            # event on the row itself: several DJs play the same event, and a
            # bare name is ambiguous.  Keep the date as the row fact.
            event = date = ""
            if row_sub:
                pieces = [part.strip() for part in row_sub.split("·")]
                if pieces:
                    event = pieces[0]
                    for piece in pieces[1:]:
                        if any(char.isdigit() for char in piece):
                            date = piece
                            break
            if event:
                title = "%s — %s" % (title, event)
            fact = _fact(date or row.get("fact") or page_data.get("noun")
                         or "set", "set")
            downloadable = bool(download_source and row.get("download")
                                and self._downloadable(url, download_source))
            row_art = self._web_art(row.get("art"), art)
            # Every web-source row goes through the plugin's web_play path:
            # it applies the public-DNS guard and mints a short-lived signed
            # URL for the session-only Mediafire streams.
            play_path = (
                "plugin://plugin.audio.raveplayer/?mode=web_play&url="
                + urllib.parse.quote(str(url), safe="")
                + "&label=" + urllib.parse.quote(title, safe="")
                + "&thumb=" + urllib.parse.quote(row_art, safe=""))
            track = Track(
                title, label, url, row_art, live=False, source=track_source,
                download_source=download_source if downloadable else "",
                path=play_path)
            entries.append(Entry(
                key=_stable_key("web:%s" % source, url),
                label=title,
                subtitle=row_sub or label,
                art=row_art,
                kind="track",
                source=track_source,
                target=url,
                track=track,
                hero=hero,
                fact=fact,
                code=_text(entry.code, "RP-46"),
                plot=row_sub or _text(row.get("plot"),
                                      "Web source · %s" % label),
                meta=_meta(_text(row.get("fact")), label.upper(),
                           _text(entry.code)),
                download_source=download_source if downloadable else "",
                downloadable=downloadable))
        per_page = max(1, _as_int(page_data.get("per_page"), 40))
        total = page_data.get("total")
        pages = page_data.get("pages")
        return Page(
            entries,
            max(0, _as_int(total, 0)) if total is not None else 0,
            max(1, _as_int(page_data.get("page"), page)),
            max(0, _as_int(pages, 0)) if pages is not None else 0,
            per_page,
            has_next=bool(page_data.get("has_next")),
            cursor=(_text(page_data.get("next_page"))
                    if page_data.get("next_page") not in (None, "", 0) else ""))

    def _archive_track_entries(self, tracks, identifier, title, year=""):
        entries = []
        for track in tracks or []:
            if not isinstance(track, dict):
                continue
            url = self._safe_url(track.get("url"))
            if not url:
                continue
            entries.append(self._track_entry(
                {"name": track.get("title") or track.get("name"),
                 "url": url, "duration": track.get("duration"),
                 "genre": track.get("genre"),
                 "year": _text(track.get("year")) or year},
                parent_label=title or identifier,
                parent_key="archive:%s" % identifier,
                source="latest", art=self._archive_thumb(identifier),
                hero=self._art("fanart-latest.jpg"), code="RP-01",
                plot="Tape pack from the Internet Archive"))
        return [entry for entry in entries if entry is not None]

    def _track_entry(self, track, parent_label, parent_key, source, art="",
                     hero="", code="", plot=""):
        raw_url = _text(track.get("url"))
        if not raw_url:
            return None
        url = raw_url if raw_url.startswith("file://") else self._safe_url(raw_url)
        if not url:
            return None
        title = _text(track.get("name") or track.get("title"), "Untitled")
        duration = _duration_fact(track.get("duration"))
        year = _text(track.get("year"))
        genre = _text(track.get("genre"))
        download_source = _DOWNLOAD_SOURCE.get(source, "")
        downloadable = self._downloadable(url, download_source)
        fact = duration or _fact(year or genre or _SOURCE_LABEL.get(source, "track"))
        meta = _meta(duration, year, genre, _SOURCE_LABEL.get(source, source).upper(),
                     code)
        return Entry(
            key=_stable_key(parent_key, url),
            label=title,
            subtitle=parent_label,
            art=art or self._art("rave.png"),
            kind="track", source=source, target=url,
            track=Track(title, parent_label, url, art, live=False,
                        duration=duration, year=year, genre=genre,
                        source=source, download_source=download_source),
            hero=hero or art or self._art("rave.png"),
            fact=fact, code=code, plot=plot or parent_label,
            meta=meta, year=year, genre=genre, duration=duration,
            download_source=download_source, downloadable=downloadable)

    # ------------------------------------------------------------ collection
    def collection(self, entry):
        """Return the *whole* collection behind a folder row (for Play all)."""
        kind = getattr(entry, "kind", "")
        source = getattr(entry, "source", "")
        try:
            if kind == "pack" and source == "latest":
                tracks = self.modules.archive.audio_files(entry.target) or []
                return [row.track for row in self._archive_track_entries(
                    tracks, entry.target, entry.label, entry.year) if row.track]
            if kind == "pack" and source == "ravetapepacks":
                return [row.track for row in self.children(entry, 1, 10000).rows
                        if row.track]
            if kind == "genre":
                return [row.track for row in self._toronto_genre_entries(entry.target)
                        if row.track]
            if kind == "show":
                return [row.track for row in self._jungle_show_entries(
                    entry.target, entry.label) if row.track]
            if kind == "rtp_post":
                return [row.track for row in self._rtp_post_children(
                    entry, 1, 10000).rows if row.track]
            if kind == "feed":
                return [row.track for row in self._feed_children(
                    entry, 1, 10000).rows if row.track]
            if kind == "hardscore_post":
                return [row.track for row in self._mixes_children(
                    entry, 1, 10000).rows if row.track]
        except Exception:  # noqa: BLE001 - play-all failure is a status line
            return []
        return []

    # --------------------------------------------- classic archive children
    def _archive_pack_entries(self, docs):
        entries = []
        for doc in docs or []:
            if not isinstance(doc, dict):
                continue
            identifier = _text(doc.get("identifier"))
            if not identifier:
                continue
            title = _text(doc.get("title"), identifier)
            year = _text(doc.get("year")) or _year_from_text(doc.get("date"))
            venue = ""
            try:
                venue = _text(self.modules.nowplaying.parse(title).get("venue"))
            except Exception:  # noqa: BLE001 - venue is cosmetic
                venue = ""
            entries.append(Entry(
                key="archive-%s" % identifier,
                label=title,
                subtitle="Internet Archive tape pack",
                art=self._archive_thumb(identifier),
                kind="pack", source="latest", target=identifier,
                hero=self._art("fanart-latest.jpg"),
                fact=_fact(year or "pack", "pack"), code="RP-39",
                plot="Tape pack from the Internet Archive.",
                meta=_meta(year, venue.upper(), "ARCHIVE.ORG", "RP-39"),
                year=year))
        return entries

    def _archive_children(self, query, page, rows):
        try:
            docs, total = self.modules.archive.search(query, page=page, rows=rows)
        except Exception:  # noqa: BLE001 - quiet empty plate
            return _page_server([], page, rows, 0)
        entries = self._archive_pack_entries(docs)
        return _page_server(entries, page, rows, total,
                            has_next=page * rows < total)

    def _filter_children(self, entry, page, rows):
        key = _text(entry.target)
        item = next((candidate for candidate in self._classic("classic_filters")
                     if _text(candidate.get("id")) == key), None)
        if item is None:
            return _page_server([], page, rows, 0)
        extra = []
        if page == 1 and item.get("live_name"):
            extra.append(Entry(
                key="filter-live-%s" % key,
                label="▶ %s — live now" % _text(item.get("name"), key),
                subtitle="Live Radio · genre door",
                art=self._art("radio.png"),
                kind="filter_live", source="filter_live",
                target=_text(item.get("live_name")),
                hero=self._art("fanart-live.jpg"), fact="live", code="RP-31",
                plot="Live streams matching %s" % item.get("live_name"),
                meta=_meta("LIVE", "RADIO", "RP-31")))
        try:
            docs, total = self.modules.archive.search(
                _text(item.get("query")), page=page, rows=rows)
        except Exception:  # noqa: BLE001 - quiet empty plate
            docs, total = [], 0
        entries = extra + self._archive_pack_entries(docs)
        return _page_server(entries, page, rows, total + len(extra),
                            has_next=page * rows < total)

    def _filter_live_children(self, entry, page, rows):
        name = _text(entry.target)
        stations = []
        try:
            stations = self.modules.radio.curated(name) or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            stations = []
        if not stations:
            try:
                stations = self.modules.radio.stations_by_name(name, limit=100) or []
            except Exception:  # noqa: BLE001 - quiet empty plate
                stations = []
        return _page_local(self._live_station_entries(stations, "Live now · %s" % name),
                           page, rows)

    def _rave_children(self, entry, page, rows):
        slug = _text(entry.target)
        item = next((candidate for candidate in self._classic("classic_raves")
                     if _text(candidate.get("slug")) == slug
                     or _text(candidate.get("name")) == slug), None)
        if item is None:
            return _page_server([], page, rows, 0)
        entries = []
        total = 0
        if item.get("query") and item.get("count"):
            try:
                docs, total = self.modules.archive.search(
                    _text(item.get("query")), page=page, rows=rows)
            except Exception:  # noqa: BLE001 - quiet empty plate
                docs, total = [], 0
            entries.extend(self._archive_pack_entries(docs))
        if page == 1 and item.get("mixcloud_query") and item.get("mixcloud_count"):
            try:
                if not self.modules.handoff.available("mixcloud"):
                    return _page_local(entries, page, rows)
            except Exception:  # noqa: BLE001 - unknown availability means skip
                return _page_local(entries, page, rows)
            link = ""
            try:
                link = self.modules.handoff.mixcloud_search(
                    _text(item.get("mixcloud_query")))
                path = link
            except Exception:  # noqa: BLE001 - add-on absent
                path = ""
            if path:
                entries.append(Entry(
                    key="rave-mixcloud-%s" % slug,
                    label="Open %s sets in the Kodi Mixcloud add-on" %
                          _text(item.get("name")),
                    subtitle="Mixcloud · hand-off",
                    art=self._art("mixcloud.png"),
                    kind="external", source="mixcloud", target=link,
                    track=Track(_text(item.get("name"), "Rave sets"),
                                "Mixcloud", link, self._art("mixcloud.png"),
                                source="mixcloud", path=path),
                    hero=self._art("fanart-hub-packs.jpg"), fact="mixcloud",
                    code="RP-40", plot="%d Mixcloud sets for %s." % (
                        item["mixcloud_count"], item.get("name")),
                    meta=_meta("MIXCLOUD", "HAND-OFF", "RP-40")))
        return _page_server(entries, page, rows, total + (1 if page == 1 and entries
                            and entries[-1].kind == "external" else 0),
                            has_next=page * rows < total)

    def _year_children(self, entry, page, rows):
        year = _text(entry.target)
        try:
            query = self.modules.latest.year_query(int(year))
            docs, total = self.modules.archive.search(query, page=page, rows=rows)
        except (TypeError, ValueError, Exception):  # noqa: BLE001
            return _page_server([], page, rows, 0)
        return _page_server(self._archive_pack_entries(docs), page, rows, total,
                            has_next=page * rows < total)

    def _archive_search_children(self, entry, page, rows):
        key = _text(entry.target)
        section = next((candidate
                        for candidate in self._classic("classic_archive_sections")
                        if _text(candidate.get("key")) == key), None)
        if section is None:
            return _page_server([], page, rows, 0)
        return self._archive_children(_text(section.get("query")), page, rows)

    def _live_tag_children(self, entry, page, rows):
        tag = _text(entry.target)
        try:
            stations = self.modules.radio.stations(tag, limit=500) or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            stations = []
        return _page_local(self._live_station_entries(stations, "Live · %s" % tag),
                           page, rows)

    def _live_station_entries(self, stations, label):
        entries = []
        for station in stations or []:
            if not isinstance(station, dict):
                continue
            try:
                name, meta = self.modules.radio.display(station)
                url = self.modules.radio.stream_url(station)
            except Exception:  # noqa: BLE001 - malformed directory row
                continue
            url = self._safe_url(url)
            if not url:
                continue
            name = _text(name, "Live station")
            art = _text(station.get("favicon") or station.get("favicon_url"))
            art = art if art.lower().startswith(("http://", "https://"))                 else self._art("radio.png")
            entries.append(Entry(
                key="live-%s" % url,
                label=name,
                subtitle=label,
                art=art,
                kind="track", source="live", target=url,
                track=Track(name, "Live radio", url, art, live=True,
                            station=name, source="live"),
                hero=self._art("fanart-live.jpg"),
                fact="LIVE", code="RP-31",
                plot=_text(meta, label),
                meta=_meta(_text(meta).upper(), "LIVE RADIO", "RP-31")))
        return entries

    # --------------------------------------------------------- blog archives
    def _blog_posts(self, kind, source_id, page, rows):
        try:
            posts = self.modules.legacyblog.posts(
                source_id, limit=self.modules.legacyblog.MAX_POSTS) or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            return _page_server([], page, rows, 0)
        total = len(posts)
        entries = []
        start = max(0, (page - 1) * rows)
        for post in posts[start:start + rows]:
            if not isinstance(post, dict):
                continue
            title = _text(post.get("title"), "Blog post")
            date = _text(post.get("date"))
            entries.append(Entry(
                key="blog-%s-%s" % (source_id, post.get("page_url")),
                label=title,
                subtitle="%s post" % kind,
                art=self._art("podcasts.png"),
                kind="blog_post",
                source="legacyblog",
                target="%s|%s" % (source_id, _text(post.get("page_url"))),
                hero=self._art("fanart-hub-shows.jpg"),
                fact=_fact(date or "post"), code="RP-32",
                plot=_text(post.get("summary"), "%s post" % kind),
                meta=_meta(date, kind.upper(), "RP-32"), year=date[:4]))
        return _page_server(entries, page, rows, total,
                            has_next=page * rows < total)

    def _blog_post_children(self, entry, page, rows):
        source_id, _, page_url = _text(entry.target).partition("|")
        try:
            details = self.modules.legacyblog.post(source_id, page_url) or {}
        except Exception:  # noqa: BLE001 - quiet empty plate
            details = {}
        source = self.modules.legacyblog.source(source_id) or {}
        label = _text(details.get("title"), entry.label)
        out = []
        for url in details.get("media_urls") or []:
            safe = self._safe_url(url)
            if not safe:
                continue
            out.append(self._track_entry(
                {"name": label, "url": safe},
                parent_label=label, parent_key="blog:%s" % source_id,
                source="legacyblog", art=self._art("podcasts.png"),
                hero=self._art("fanart-hub-shows.jpg"), code="RP-32",
                plot="%s · direct MP3" % _text(source.get("name"), "Blog")))
        for url in details.get("mixcloud_urls") or []:
            try:
                path = self.modules.handoff.target(url, label)
            except Exception:  # noqa: BLE001 - missing add-on hides the row
                path = ""
            if not path:
                continue
            out.append(Entry(
                key="blog-mixcloud-%s" % url,
                label=label,
                subtitle="%s · Mixcloud" % _text(source.get("name"), "Blog"),
                art=self._art("mixcloud.png"),
                kind="external", source="mixcloud", target=url,
                track=Track(label, _text(source.get("name"), "Mixcloud"), url,
                            self._art("mixcloud.png"), source="mixcloud",
                            path=path),
                hero=self._art("fanart-hub-shows.jpg"), fact="mixcloud",
                code="RP-32", plot="Opens in the Kodi Mixcloud add-on.",
                meta=_meta("MIXCLOUD", "HAND-OFF", "RP-32")))
        return _page_local([row for row in out if row is not None], page, rows)

    # ------------------------------------------------------------- resolvers
    def resolve(self, entry):
        """Resolve a lazy playable (DNB / Moxser) to a concrete Track."""
        kind = getattr(entry, "kind", "")
        if kind == "dnb_show":
            try:
                url = self.modules.dnbradio.stream_url(entry.target) or ""
            except Exception:  # noqa: BLE001 - quiet failure
                url = ""
            url = self._safe_url(url)
            if not url:
                return None
            return Track(entry.label, "DNB Radio", url, self._art("dnb.png"),
                         year=entry.year, source="dnb")
        if kind == "moxser_mix":
            try:
                page = self.modules.moxser.mix(entry.target) or {}
            except Exception:  # noqa: BLE001 - quiet failure
                page = {}
            url = self._safe_url(page.get("mp3_url"))
            if not url:
                return None
            return Track(_text(page.get("title"), entry.label), "Moxser.com", url,
                         _text(page.get("flyer")) or self._art("moxser.png"),
                         year=_text(page.get("date")), source="moxser",
                         download_source="Moxser.com")
        return None

    # ---------------------------------------------------------------- thumbs
    def _archive_thumb(self, identifier):
        try:
            thumb = _text(self.modules.archive.thumb(identifier))
        except Exception:  # noqa: BLE001 - art is optional
            thumb = ""
        if thumb.lower().startswith(("http://", "https://")):
            return thumb
        return self._art("rave.png")

    # ------------------------------------------------------------------ art
    def spinner_frames(self):
        frames = []
        roots = [self._script_root]
        try:
            roots.append(self.root)
        except Exception:  # noqa: BLE001 - plugin missing; script copy is enough
            pass
        for root in roots:
            for directory in (os.path.join(root, "resources", "art", "rave-screen"),
                              os.path.join(root, "resources", "art", "spinner")):
                candidate = [os.path.join(directory, "head-%d-%02d.png" % (FRAME_SIZE, index))
                             for index in range(FRAME_COUNT)]
                if all(os.path.isfile(path) for path in candidate):
                    return candidate
        return frames
