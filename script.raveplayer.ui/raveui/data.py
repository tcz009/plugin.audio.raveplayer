# -*- coding: utf-8 -*-
"""Data rows for the full-screen Rave Player app.

The screen is the shell; ``plugin.audio.raveplayer`` is the data/playback
backend.  This module adapts the plugin's public data helpers into one flat
row/page vocabulary (``Entry``/``Track``/``Page``) and never re-implements a
scraper.

Rooms are ordinary paged collections.  The controller owns paging mechanics
(previous/next rows, 25/50/100), focus and Back; this module only knows how to
produce one page for a target:

* a room key (``latest``, ``toronto`` ... ``about``)
* an ``Entry`` folder (pack / genre / show / RTP index / post / feed ...)
* a :class:`SearchTarget` (query + scope)

Network work happens only when the controller asks for a page; opening the
window is static.  No notification, dialog or warning is raised here: a source
that is blocked/offline returns an empty list and the controller paints the
STANDBY/ERROR plate quietly (owner rule: no RTP warnings).
"""

import hashlib
import os
import random as _random
import xml.etree.ElementTree as _ET
from dataclasses import dataclass

from . import pluginbridge

FRAME_COUNT = 10
FRAME_SIZE = 512
PAGE_SIZES = (25, 50, 100)
DEFAULT_PAGE_SIZE = 50
MAX_FACT_CHARS = 16

ROOM_ORDER = (
    "latest", "toronto", "jungletapes", "ravetapepacks", "live", "mixes",
    "search", "favourites", "downloads", "about", "surprise",
)

SEARCH_SCOPES = (
    ("archive", "Tape packs", "Internet Archive · relevance"),
    ("jungletapes", "JungleTapes", "cassette shows"),
    ("live", "Live radio", "stations on air now"),
    ("favourites", "Favourites", "the sets you saved"),
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
    query: str
    scope: str = "archive"

    @property
    def label(self):
        return dict((key, label) for key, label, _plot in SEARCH_SCOPES).get(
            self.scope, "Tape packs")


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
                 random_module=None, script_root=None, download_queue=None,
                 screen_version="", plugin_version=""):
        self._modules = modules
        self._addon_factory = addon_factory
        self._root = root
        self._random = random_module or _random
        self._script_root = script_root or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
        self._download_queue = download_queue
        self._screen_version = screen_version
        self._plugin_version = plugin_version
        self.rows_per_page = DEFAULT_PAGE_SIZE
        self.load_error = ""
        self.last_surprise_reason = ""

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
    def _art(self, name):
        path = os.path.join(self.root, "resources", "art", name)
        if os.path.isfile(path):
            return path
        fallback = os.path.join(self._script_root, "resources", "art",
                                "rave-screen", "hero-fallback-640x360.jpg")
        return fallback if os.path.isfile(fallback) else ""

    def _neutral_hero(self):
        """A plain screen-bed hero for rows whose room is the visual context.

        Several plugin fanarts carry baked room text.  Using one under a
        JungleTapes show painted "TAPE PACKS" over the show; child rows use
        the unlabelled bed instead, with the selected row's own title/meta.
        """
        for name in ("screen-bed-1920x1080.jpg", "screen-bed-1280x720.jpg"):
            path = os.path.join(self._script_root, "resources", "art",
                                "rave-screen", name)
            if os.path.isfile(path):
                return path
        return self._art("fanart-screen.jpg")

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
            room("toronto", "Toronto Rave Mixtape Archive",
                 "1990–2014 · jungle, house and X-Static tapes",
                 "toronto.png", "fanart-toronto.jpg", "1990–2014", "RP-19",
                 "Toronto rave mixtapes, 1990–2014."),
            room("jungletapes", "JungleTapes.com",
                 "Toronto jungle radio digitised from cassette",
                 "jungletapes.png", "neutral", "310 shows", "RP-27",
                 "310 Toronto jungle radio shows, digitised from cassette."),
            room("ravetapepacks", "RaveTapePacks.com",
                 "UK tape packs, 1992–2004 · by event, DJ, MC and year",
                 "ravetapepacks.png", "fanart-tapepacks.jpg", "1992–2004", "RP-03",
                 "The UK rave tape-pack archive, filed every way."),
            room("live", "Live Radio",
                 "Kool FM · Rinse FM · Centreforce and more",
                 "radio.png", "fanart-live.jpg", "live", "RP-31",
                 "Stations on air now, plus scene genre doors."),
            room("mixes", "Mixes & Shows",
                 "DNBRADIO · Moxser · Hardscore · GetDarker · podcasts",
                 "mixes.png", "fanart-mixes.jpg", "shows", "RP-32",
                 "Studio mixes, archive sets and podcast shows."),
            Entry("search", "Search",
                  "Find a pack, show or station — scoped and paged",
                  self._art("search.png"), "search", source="search",
                  hero=self._art("fanart-search.jpg"), fact="find", code="RP-33",
                  plot="Type in the window; results are paged and relevance-sorted."),
            room("favourites", "Favourites",
                 "The sets you saved — play or remove",
                 "favourites.png", "fanart-favourites.jpg",
                 "%d saved" % self._fav_count(), "RP-34",
                 "Saved packs, shows and streams."),
            room("downloads", "Downloads",
                 "Offline copies, progress and removal",
                 "downloads.png", "neutral",
                 "%d saved" % self._download_count(), "RP-35",
                 "Files saved for offline playback."),
            room("about", "About",
                 "Version, sources and the app's real facts",
                 "about.png", "fanart-about.jpg", "credits", "RP-36",
                 "Version, licence, sources and storage facts."),
            Entry("surprise", "Spinning Surprise",
                  "One random pack + track · press OK",
                  self._art("surprise.png"), "surprise", source="surprise",
                  hero=self._art("fanart-surprise.jpg"), fact="random", code="RP-02",
                  plot="One random pack and track; one spin, no re-roll."),
        ]

    # ---------------------------------------------------------------- rooms
    def room(self, key, page=1, rows=None):
        key = str(key or "")
        rows = rows or self.rows_per_page
        if key == "latest":
            return _page_local(self._latest_entries(), page, rows)
        if key == "toronto":
            return _page_local(self._toronto_entries(), page, rows)
        if key == "jungletapes":
            return _page_local(self._jungletapes_entries(), page, rows)
        if key == "ravetapepacks":
            return _page_local(self._ravetapepacks_entries(), page, rows)
        if key == "live":
            return _page_local(self._live_entries(), page, rows)
        if key == "mixes":
            return _page_local(self._mixes_entries(), page, rows)
        if key == "favourites":
            return _page_local(self._favourite_rows(), page, rows)
        if key == "downloads":
            return _page_local(self._download_rows(), page, rows)
        if key == "about":
            return _page_local(self.about_rows(), page, rows)
        if key == "search":
            return _page_local([], page, rows)
        raise ValueError("unknown Rave Screen room %r" % key)

    def load(self, target, page=1, rows=None):
        """Return one :class:`Page` for a room key, folder Entry or search."""
        if target is None or target == "":
            entries = list(self.home_rows())
            return Page(entries, len(entries), 1, 1, len(entries) or 1)
        if isinstance(target, SearchTarget):
            return self.search(target, page, rows)
        if isinstance(target, str):
            return self.room(target, page, rows)
        return self.children(target, page, rows)

    def section_entries(self, key):
        """Compatibility view for older callers/tests: room page one."""
        return self.room(key, 1).rows

    def entries_for(self, entry):
        """Compatibility view: one folder's first page."""
        return self.children(entry, 1).rows

    # -------------------------------------------------------------- latest
    def _latest_entries(self):
        try:
            packs = self.modules.latest.recent_packs(rows=100)
        except Exception:  # noqa: BLE001 - quiet empty plate
            return []
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

    # ----------------------------------------------------------------- live
    def _live_entries(self):
        entries = []
        try:
            for token in ("kool", "rinse", "centreforce"):
                for station in self.modules.radio.curated(token) or []:
                    entry = self._station_entry(station)
                    if entry is not None:
                        entries.append(entry)
        except Exception:  # noqa: BLE001 - one missing station must not empty the room
            pass
        for tag, label, art in (
                ("hardcore", "Hardcore", "radio-hardcore.png"),
                ("jungle", "Jungle", "radio-jungle.png"),
                ("drum and bass", "Drum & Bass", "radio-dnb.png"),
                ("house", "House", "radio-house.png"),
                ("uk garage", "UK Garage", "radio-uk-garage.png"),
                ("dubstep", "Dubstep & Grime", "radio-dubstep-grime.png")):
            entries.append(Entry(
                key="live-genre-%s" % tag.replace(" ", "-"),
                label=label,
                subtitle="Live stations tagged %s" % tag,
                art=self._art(art),
                kind="live_genre", source="live", target=tag,
                hero=self._art("fanart-live.jpg"),
                fact="stations", code="RP-31",
                plot="Stations on air now, tagged %s" % tag,
                meta=_meta("LIVE DIRECTORY", "ON AIR", "RP-31")))
        return entries

    def _live_genre_children(self, entry, page, rows):
        tag = _text(entry.target)
        try:
            stations = self.modules.radio.stations(tag, limit=100) or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            return _page_local([], page, rows)
        entries = []
        seen = set()
        for station in stations:
            if not isinstance(station, dict):
                continue
            candidate = self._station_entry(station)
            if candidate is None or candidate.target in seen:
                continue
            seen.add(candidate.target)
            entries.append(candidate)
        return _page_local(entries, page, rows)

    def _station_entry(self, station):
        if not isinstance(station, dict):
            return None
        try:
            url = self._safe_url(self.modules.radio.stream_url(station))
        except Exception:  # noqa: BLE001 - station without a stream
            return None
        if not url:
            return None
        try:
            name, meta = self.modules.radio.display(station)
        except Exception:  # noqa: BLE001 - plain fallback
            name, meta = _text(station.get("name"), "Live radio"), ""
        name = _text(name, "Live radio")
        fact = _fact(meta or "live", "live")
        return Entry(
            key=url,
            label=name,
            subtitle="Live radio · no duration",
            art=self._art("radio.png"),
            kind="station", source="live",
            track=Track(name, "Live radio", url, self._art("radio.png"), live=True,
                        source="live"),
            hero=self._art("fanart-live.jpg"),
            fact=fact, code="RP-31",
            plot="Live radio · ON AIR while playing · no duration or progress",
            meta=_meta(meta, "LIVE RADIO", "RP-31"),
            download_source="")

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
    def _fav_count(self):
        try:
            return len(self.modules.favourites.load())
        except Exception:  # noqa: BLE001 - optional module
            return 0

    def _download_count(self):
        try:
            return len(self.modules.downloads.list_downloads())
        except Exception:  # noqa: BLE001 - optional module
            return 0

    def _favourite_rows(self):
        try:
            rows = self.modules.favourites.load() or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            return []
        entries = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            kind = _text(row.get("kind"), "stream")
            target = _text(row.get("target"))
            title = _text(row.get("title"), target)
            source = _text(row.get("source"))
            fav_key = ""
            try:
                fav_key = self.modules.favourites.key(row)
            except Exception:  # noqa: BLE001 - display only
                fav_key = "%s:%s" % (kind, target)
            if not target:
                continue
            if kind == "pack":
                entry = Entry(
                    key="fav-%s" % target, label=title,
                    subtitle="Favourite pack · %s" % (source or "Archive.org"),
                    art=self._archive_thumb(target), kind="pack", source="latest",
                    target=target, hero=self._art("fanart-favourites.jpg"),
                    fact="pack", code="RP-34",
                    plot="Saved tape pack", fav_key=fav_key,
                    meta=_meta("FAVOURITE", "ARCHIVE.ORG", "RP-34"))
            elif kind == "legacy_pack":
                entry = Entry(
                    key="fav-%s" % target, label=title,
                    subtitle="Favourite pack · RaveTapePacks.com",
                    art=self._art("ravetapepacks.png"), kind="pack",
                    source="ravetapepacks", target=target,
                    hero=self._art("fanart-favourites.jpg"), fact="pack",
                    code="RP-34", plot="Saved RaveTapePacks pack", fav_key=fav_key,
                    meta=_meta("FAVOURITE", "RAVETAPEPACKS.COM", "RP-34"))
            elif kind == "legacy_post":
                entry = Entry(
                    key="fav-%s" % target, label=title,
                    subtitle="Favourite pack · RaveTapePacks.com",
                    art=self._art("ravetapepacks.png"), kind="rtp_post",
                    source="ravetapepacks", target=target,
                    hero=self._art("fanart-favourites.jpg"), fact="pack",
                    code="RP-34", plot="Saved RaveTapePacks pack", fav_key=fav_key,
                    meta=_meta("FAVOURITE", "RAVETAPEPACKS.COM", "RP-34"))
            elif kind == "legacy_jt":
                entry = Entry(
                    key="fav-%s" % target, label=title,
                    subtitle="Favourite show · JungleTapes.com",
                    art=self._art("jungletapes.png"), kind="show",
                    source="jungletapes", target=target,
                    hero=self._art("fanart-favourites.jpg"), fact="show",
                    code="RP-34", plot="Saved JungleTapes show", fav_key=fav_key,
                    meta=_meta("FAVOURITE", "JUNGLETAPES.COM", "RP-34"))
            elif kind == "dnb":
                entry = Entry(
                    key="fav-dnb-%s" % target, label=title,
                    subtitle="Favourite show · DNB Radio",
                    art=self._art("dnb.png"), kind="dnb_show", source="dnb",
                    target=target, hero=self._art("fanart-favourites.jpg"),
                    fact="show", code="RP-34", plot="Saved DNBRADIO show",
                    fav_key=fav_key,
                    meta=_meta("FAVOURITE", "DNB RADIO", "RP-34"))
            else:
                live = "live radio" in source.lower()
                try:
                    live = live or self.modules.live.is_live_stream(target)
                except Exception:  # noqa: BLE001 - plain stream
                    pass
                entry = Entry(
                    key="fav-%s" % target, label=title,
                    subtitle="Saved stream · %s" % (source or "Rave Player"),
                    art=self._art("radio.png"),
                    kind="station" if live else "track", source="favourites",
                    target=target,
                    track=Track(title, "Favourites", target,
                                self._art("radio.png"), live=live,
                                source="favourites"),
                    hero=self._art("fanart-favourites.jpg"),
                    fact="live" if live else "saved",
                    code="RP-34",
                    plot="Saved stream · %s" % (source or "Rave Player"),
                    fav_key=fav_key,
                    meta=_meta("LIVE" if live else "STREAM", source.upper(), "RP-34"))
            entries.append(entry)
        return entries

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
    def _download_rows(self):
        entries = []
        queue = self._download_queue
        if queue is not None:
            try:
                active = queue.rows()
            except Exception:  # noqa: BLE001 - queue is advisory
                active = []
            for item in active:
                percent = int(item.get("percent") or 0)
                status = _text(item.get("status"), "queued").lower()
                entries.append(Entry(
                    key="dl-active-%s" % item.get("key", ""),
                    label=_text(item.get("title"), "Download"),
                    subtitle="Downloading · %s" % status,
                    art=self._art("downloads.png"),
                    kind="download_active", source="downloads",
                    target=_text(item.get("key")),
                    hero=self._art("fanart-favourites.jpg"),
                    fact=_fact("%d%% · %s" % (percent, status), "download"),
                    code="RP-35",
                    plot="Download in progress · %s" % _text(item.get("detail")),
                    meta=_meta("%d%%" % percent, status.upper(), "RP-35")))
        try:
            rows = self.modules.downloads.list_downloads() or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            rows = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = _text(row.get("key")) or _text(row.get("url"))
            title = _text(row.get("title"), "Downloaded set")
            exists = bool(row.get("exists"))
            try:
                size = self.modules.downloads.format_size(row.get("size") or 0)
            except Exception:  # noqa: BLE001 - metadata only
                size = ""
            added = _text(row.get("added"))[:10]
            entries.append(Entry(
                key="dl-%s" % key,
                label=title,
                subtitle="Downloaded · %s" % (_text(row.get("source")) or "Rave Player"),
                art=self._art("downloads.png"),
                kind="file" if exists else "download_missing",
                source="downloads", target=key,
                track=Track(title, "Downloads", _text(row.get("path")),
                            self._art("downloads.png"), local=True,
                            source="downloads") if exists else None,
                hero=self._neutral_hero(),
                fact=_fact(size if exists else "missing", "missing"),
                code="RP-35",
                plot="Offline copy · %s" % (_text(row.get("source")) or "Rave Player"),
                meta=_meta(size, added, "RP-35" if exists else "MISSING"),
                fav_key=key))
        return entries

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

    # ---------------------------------------------------------------- about
    def about_rows(self):
        try:
            import xbmc

            build = _text(xbmc.getInfoLabel("System.BuildVersion"), "Kodi")
        except Exception:  # noqa: BLE001 - tests/outside Kodi
            build = "Kodi"
        try:
            fav_count = self._fav_count()
            download_count = self._download_count()
            saved = self.modules.downloads.format_size(
                self.modules.downloads.total_saved_bytes())
        except Exception:  # noqa: BLE001 - optional modules
            fav_count, download_count, saved = 0, 0, "0 B"
        rows = [
            ("Rave Player %s" % (self.plugin_version() or "?"),
             "plugin", "The data and playback backend this screen drives.",
             "Backend"),
            ("Rave Screen %s" % (self.screen_version() or "?"),
             "screen", "The full-screen app shell (this window).", "Shell"),
            ("Kodi %s" % build, "kodi", "Kodi build on this device.", "Player"),
            ("Audio policy", "audio",
             "One audio owner: Kodi's player. Remote streams resolve through "
             "the plugin's mode=play route (RTP egress/bridge included). "
             "Downloaded files play from disk. Leaving the screen keeps audio "
             "playing; Stop (or the context menu) stops it.", "Kodi player"),
            ("Rows per page", "paging",
             "Section lists page at 25, 50 or 100 rows. Change it from any "
             "list's context menu.", "%d rows" % self.rows_per_page),
            ("Sources", "sources",
             "Internet Archive · Toronto Rave Mixtape Archive · JungleTapes.com "
             "· RaveTapePacks.com · radio-browser.info · DNBRADIO · Moxser · "
             "Hardscore · GetDarker · RSS feeds · Pirate Radio Archives.",
             "11 sources"),
            ("Favourites", "favourites", "Saved packs, shows and streams.",
             "%d saved" % fav_count),
            ("Downloads", "downloads",
             "Offline copies in the add-on profile. %s saved." % saved,
             "%d files" % download_count),
            ("Licence", "licence",
             "GNU General Public License v3.0 or later. Rave Player does not "
             "host or distribute any content.", "GPL-3.0"),
            ("Repository", "repo",
             "github.com/tcz009/plugin.audio.raveplayer", "github.com"),
        ]
        entries = []
        for index, (label, art_key, plot, fact) in enumerate(rows):
            entries.append(Entry(
                key="about-%d" % index,
                label=label,
                subtitle=plot,
                art=self._art({
                    "plugin": "rave.png", "screen": "screen.png",
                    "kodi": "about.png", "audio": "radio.png",
                    "paging": "sets.png", "sources": "tapepacks.png",
                    "favourites": "favourites.png", "downloads": "downloads.png",
                    "licence": "about.png", "repo": "about.png",
                }.get(art_key, "about.png")),
                kind="info", source="about",
                hero=self._art("fanart-about.jpg"),
                fact=_fact(fact), code="RP-36", plot=plot,
                meta=_meta(fact.upper(), "ABOUT", "RP-36")))
        return entries

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
        if kind == "live_genre":
            return self._live_genre_children(entry, page, rows)
        if kind == "hardscore_post":
            return self._mixes_children(entry, page, rows)
        return _page_local([], page, rows)

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

    # ----------------------------------------------------------------- search
    def search(self, target, page=1, rows=None):
        rows = rows or self.rows_per_page
        query = _text(getattr(target, "query", ""))
        scope = _text(getattr(target, "scope", "archive"), "archive")
        if not query:
            return _page_local([], page, rows)
        if scope == "jungletapes":
            return self._search_jungletapes(query, page, rows)
        if scope == "live":
            return self._search_live(query, page, rows)
        if scope == "favourites":
            return self._search_favourites(query, page, rows)
        return self._search_archive(query, page, rows)

    def _search_archive(self, query, page, rows):
        rows = max(1, _as_int(rows, DEFAULT_PAGE_SIZE))
        scoped = "%s AND %s" % (query, self.modules.latest.RAVE_COLLECTION)
        try:
            docs, total = self.modules.archive.search(
                scoped, page=page, rows=rows, sort="")
        except Exception:  # noqa: BLE001 - quiet empty plate
            return _page_server([], page, rows, 0)
        entries = [self._archive_pack_entry(doc) for doc in docs or []]
        entries = [entry for entry in entries if entry is not None]
        if page == 1 and total < 10:
            # Same bounded title-scoped widen as the plugin route: an unscoped
            # mediatype:audio search surfaces audiobooks/SFX before rave tapes.
            try:
                wider, _wider_total = self.modules.archive.search(
                    'title:(%s) AND mediatype:audio AND '
                    '(collection:ravetapes OR collection:cassettetapes OR '
                    'subject:(rave OR jungle OR hardcore OR "drum and bass" OR '
                    '"old skool" OR garage))' % query, rows=rows)
            except Exception:  # noqa: BLE001 - first page is still valid
                wider = []
            seen = set(entry.target for entry in entries)
            for doc in wider or []:
                entry = self._archive_pack_entry(doc)
                if entry is not None and entry.target not in seen:
                    seen.add(entry.target)
                    entries.append(entry)
        return _page_server(entries, page, rows, total,
                            has_next=bool(total) and page * rows < total)

    def _archive_pack_entry(self, doc):
        if not isinstance(doc, dict):
            return None
        identifier = _text(doc.get("identifier"))
        if not identifier:
            return None
        title = _text(doc.get("title"), identifier)
        year = _text(doc.get("year")) or _year_from_text(doc.get("date"))
        return Entry(
            key=identifier, label=title,
            subtitle="Internet Archive · search result",
            art=self._archive_thumb(identifier),
            kind="pack", source="latest", target=identifier,
            hero=self._art("fanart-search.jpg"),
            fact=_fact(year or "pack", "pack"), code="RP-33",
            plot="Internet Archive search result",
            meta=_meta(year, "SEARCH", "RP-33"), year=year)

    def _search_jungletapes(self, query, page, rows):
        try:
            shows = self.modules.legacy.jungle_shows() or []
        except Exception:  # noqa: BLE001 - quiet empty plate
            return _page_local([], page, rows)
        terms = [part for part in query.lower().split() if part]
        scored = []
        for show in shows:
            name = _text(show.get("name"), show.get("key"))
            score = self._match_score(name, terms)
            if score is not None:
                scored.append((score, name, show))
        scored.sort(key=lambda item: (item[0], item[1].lower()))
        entries = []
        for _score, name, show in scored:
            key = _text(show.get("key"))
            if not key:
                continue
            entries.append(Entry(
                key=key, label=name, subtitle="JungleTapes.com show",
                art=self._art("jungletapes.png"), kind="show",
                source="jungletapes", target=key,
                hero=self._art("fanart-search.jpg"), fact="show",
                code="RP-33", plot="JungleTapes.com search result",
                meta=_meta("SEARCH", "JUNGLETAPES.COM", "RP-33")))
        return _page_local(entries, page, rows)

    def _search_live(self, query, page, rows):
        try:
            entries = self._live_entries()
        except Exception:  # noqa: BLE001 - quiet empty plate
            return _page_local([], page, rows)
        terms = [part for part in query.lower().split() if part]
        matches = [row for row in entries if row.track is not None
                   and self._match_score(row.label + " " + row.subtitle, terms) is not None]
        return _page_local(matches, page, rows)

    def _search_favourites(self, query, page, rows):
        terms = [part for part in query.lower().split() if part]
        matches = [row for row in self._favourite_rows()
                   if self._match_score(row.label + " " + row.subtitle, terms) is not None]
        return _page_local(matches, page, rows)

    @staticmethod
    def _match_score(text, terms):
        text = str(text or "").lower()
        if not terms:
            return 0
        score = 0
        for term in terms:
            found = text.find(term)
            if found < 0:
                return None
            score += 0 if found == 0 else (1 if text[found - 1] == " " else 2)
        return score

    # ------------------------------------------------------------- surprise
    def random_pick(self):
        """Pick one pack + one playable track, bounded and retried.

        The old single attempt surfaced "No random pack found" whenever the
        Archive search returned an empty page or the picked identifier had no
        playable derivative. Four bounded attempts plus a recent-packs
        fallback remove the intermittent failure without an unbounded loop.
        """
        self.last_surprise_reason = ""
        attempts = 0
        while attempts < 4:
            attempts += 1
            try:
                pack = self.modules.latest.random_pack()
            except Exception as exc:  # noqa: BLE001 - try the next bounded pick
                self.last_surprise_reason = "pick failed: %s" % exc
                continue
            if not pack or not _text(pack.get("identifier")):
                self.last_surprise_reason = "empty pack"
                continue
            identifier = _text(pack.get("identifier"))
            try:
                tracks = self.modules.archive.audio_files(identifier) or []
            except Exception as exc:  # noqa: BLE001 - try another pack
                self.last_surprise_reason = "tracks failed: %s" % exc
                continue
            playable = []
            for track in tracks:
                if not isinstance(track, dict):
                    continue
                url = self._safe_url(track.get("url"))
                if url:
                    playable.append((track, url))
            if not playable:
                self.last_surprise_reason = "no playable tracks"
                continue
            track, url = self._random.choice(playable)
            pack_title = _text(pack.get("title"), identifier)
            title = _text(track.get("title") or track.get("name"), "Untitled")
            return Track(title, pack_title, url,
                         self._archive_thumb(identifier), live=False,
                         duration=_duration_fact(track.get("duration")),
                         genre=_text(track.get("genre")), source="latest",
                         download_source="Archive.org")
        # Bounded fallback: one of the 20 newest packs, still through plugin data.
        try:
            for doc in self.modules.latest.recent_packs(rows=20) or []:
                identifier = _text(doc.get("identifier"))
                if not identifier:
                    continue
                try:
                    tracks = self.modules.archive.audio_files(identifier) or []
                except Exception:  # noqa: BLE001 - next candidate
                    continue
                playable = []
                for track in tracks:
                    if not isinstance(track, dict):
                        continue
                    url = self._safe_url(track.get("url"))
                    if url:
                        playable.append((track, url))
                if not playable:
                    continue
                track, url = self._random.choice(playable)
                title = _text(track.get("title") or track.get("name"), "Untitled")
                return Track(title, _text(doc.get("title"), identifier), url,
                             self._archive_thumb(identifier), source="latest",
                             download_source="Archive.org")
        except Exception as exc:  # noqa: BLE001 - final quiet failure
            self.last_surprise_reason = "fallback failed: %s" % exc
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
