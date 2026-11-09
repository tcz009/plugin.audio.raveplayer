# -*- coding: utf-8 -*-
"""Search, Favourites, Downloads and About as renderable full-screen rooms.

The Rave Screen shell (``raveui.window`` / ``raveui.controller``) paints a
:class:`Screen` and calls the handlers on :class:`LibraryScreens`.  This module
contains no Kodi import at module level and performs no network request of its
own: every read or write goes through a backend (by default
:class:`PluginBackend`, which reuses the plugin's public data modules via
:mod:`raveui.pluginbridge`), exactly like :mod:`raveui.data`.

Two layers live here:

* the **protocol** — :class:`Row`, :class:`Screen`, :class:`ActionResult` —
  plain dataclasses with no Kodi types, so the shell can render them and tests
  can assert on them;
* the **adapter** — :class:`LibraryScreens` — maps plugin data to rows, pages
  it at 25/50/100, turns failures into a retryable error screen and applies
  play / play-all / shuffle / download / favourite / remove / retry actions.

The owner-facing wording lives in the constants below; the shell never has to
know which plugin module supplied a fact.
"""

import importlib
import os
import random as _random
import re
import threading
from dataclasses import dataclass, field

from .. import pluginbridge

# --------------------------------------------------------------- protocol IDs
ROUTE_SEARCH = "search"
ROUTE_FAVOURITES = "favourites"
ROUTE_DOWNLOADS = "downloads"
ROUTE_ABOUT = "about"
ROUTES = (ROUTE_SEARCH, ROUTE_FAVOURITES, ROUTE_DOWNLOADS, ROUTE_ABOUT)

STATE_READY = "ready"
STATE_EMPTY = "empty"
STATE_LOADING = "loading"
STATE_ERROR = "error"
STATES = (STATE_READY, STATE_EMPTY, STATE_LOADING, STATE_ERROR)

KIND_ROOM = "room"       # opens one level deeper in the shell
KIND_TRACK = "track"     # playable now (remote URL or a local download)
KIND_ACTION = "action"   # invokes an action payload
ROW_KINDS = (KIND_ROOM, KIND_TRACK, KIND_ACTION)

ACTION_PLAY = "play"
ACTION_PLAY_ALL = "play_all"
ACTION_SHUFFLE = "shuffle"
ACTION_DOWNLOAD = "download"
ACTION_FAVOURITE = "favourite"
ACTION_REMOVE = "remove"
ACTION_RETRY = "retry"
ACTION_CANCEL = "cancel"   # stop an active DownloadQueue row
# Not one of the seven shell actions: About links use it so a remote can still
# open the project page.  A shell that does not handle it may ignore the row.
ACTION_OPEN = "open"

# The plugin setting offers exactly these; anything else (0, 75, a stale
# profile) snaps to the nearest allowed size.  This is the "25/50/100" rule.
PAGE_SIZES = (25, 50, 100)
DEFAULT_PAGE_SIZE = 50
DEFAULT_SCOPE = "collection:ravetapes AND mediatype:audio"
MAX_QUERY_CHARS = 120
MAX_FACT_CHARS = 16
MAX_ERROR_CHARS = 200

PROJECT_URL = "https://github.com/tcz009/plugin.audio.raveplayer"
LICENCE_URL = "https://www.gnu.org/licenses/gpl-3.0.html"
KODI_URL = "https://kodi.tv"

TITLE_SEARCH = "SEARCH"
TITLE_FAVOURITES = "FAVOURITES"
TITLE_DOWNLOADS = "DOWNLOADS"
TITLE_ABOUT = "ABOUT"
TITLES = {
    ROUTE_SEARCH: TITLE_SEARCH,
    ROUTE_FAVOURITES: TITLE_FAVOURITES,
    ROUTE_DOWNLOADS: TITLE_DOWNLOADS,
    ROUTE_ABOUT: TITLE_ABOUT,
}

# Cosmetic RP codes.  These four match the 3.9.51 RaveData.home_rows() room
# codes (search RP-33, favourites RP-34, downloads RP-35, about RP-36); the
# older look.RP_CODES aliases (RP-44/RP-12/RP-05/RP-99) are print furniture only.
CODE_SEARCH = "RP-33"
CODE_FAVOURITES = "RP-34"
CODE_DOWNLOADS = "RP-35"
CODE_ABOUT = "RP-36"
CODES = {
    ROUTE_SEARCH: CODE_SEARCH,
    ROUTE_FAVOURITES: CODE_FAVOURITES,
    ROUTE_DOWNLOADS: CODE_DOWNLOADS,
    ROUTE_ABOUT: CODE_ABOUT,
}

SEARCH_IDLE_SUBTITLE = "Type a word and press OK"
FAVOURITES_IDLE_SUBTITLE = "Saved packs, shows and streams"
DOWNLOADS_IDLE_SUBTITLE = "Offline copies · saved on this device"
_NOTHING_TO_RETRY = "Nothing to retry"


# ---------------------------------------------------------------------- rows
@dataclass(frozen=True)
class Row:
    """One renderable line in a :class:`Screen`.

    The field names match ``raveui.data.Entry`` so the existing WindowXML
    adapter can render a library screen without knowing this module exists:
    ``label`` is the title, ``fact`` is Label2 (already capped at 16 chars),
    ``icon``/``fanart`` are the two art slots, ``code`` is the RP print
    furniture and ``payload`` is the action metadata.

    ``kind`` says what pressing the row means:

    * ``room``   — ``payload["room"]`` / ``payload["mode"]`` name the next
      screen (a pack, show, platform hand-off…); the shell owns that route.
    * ``track``  — ``payload["url"]`` is playable now.  ``local`` marks a
      downloaded file that must not go through the stream URL guard.
    * ``action`` — ``payload["action"]`` is one of the seven actions below.
    """

    label: str
    kind: str = KIND_ACTION
    fact: str = ""
    icon: str = ""
    fanart: str = ""
    code: str = ""
    payload: dict = field(default_factory=dict)
    subtitle: str = ""
    plot: str = ""

    @property
    def art(self):
        """Alias for the existing window adapter's icon slot."""
        return self.icon

    @property
    def title(self):
        """Alias for shells that name the row field ``title`` (live screens)."""
        return self.label

    @property
    def hero(self):
        """Alias for the existing window adapter's fanart slot."""
        return self.fanart or self.icon

    @property
    def action(self):
        """The action name in the payload, or ``""`` for a room/track row."""
        return str(self.payload.get("action") or "")


def _count(value):
    try:
        return "{:,}".format(max(0, int(value)))
    except (TypeError, ValueError, OverflowError):
        return "0"


@dataclass(frozen=True)
class Screen:
    """Everything the shell needs to paint one room.

    ``rows`` is a tuple of :class:`Row` (content rows only; navigation is the
    shell's job).  ``page``/``pages``/``total``/``page_size`` describe the
    current page and drive the shell's "Page N of M" line.  ``state`` is one of
    ``ready`` / ``empty`` / ``loading`` / ``error``; the shell paints a loading
    Screen while a worker calls the handler, and empty/error Screens include a
    retry action row.
    """

    route: str
    title: str
    subtitle: str = ""
    rows: tuple = ()
    state: str = STATE_READY
    page: int = 1
    pages: int = 1
    total: int = 0
    page_size: int = DEFAULT_PAGE_SIZE
    query: str = ""
    error: str = ""
    noun: str = "items"
    code: str = ""

    def __post_init__(self):
        object.__setattr__(self, "rows", tuple(self.rows or ()))

    @property
    def is_ready(self):
        return self.state == STATE_READY

    @property
    def is_empty(self):
        return self.state == STATE_EMPTY

    @property
    def has_error(self):
        return self.state == STATE_ERROR

    @property
    def has_previous(self):
        return self.page > 1

    @property
    def rows_per_page(self):
        """Alias for the parent shell's Page field."""
        return self.page_size

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def page_label(self):
        """``"Page 2 of 3 · 120 favourites"`` (empty on a single page)."""
        if self.pages <= 1:
            return ""
        return "Page %d of %d · %s %s" % (
            self.page, self.pages, _count(self.total), self.noun)

    @property
    def retry_row(self):
        for row in self.rows:
            if row.payload.get("action") == ACTION_RETRY:
                return row
        return None


@dataclass(frozen=True)
class PlayItem:
    """A validated play request handed to ``PlaybackService``.

    The attribute names deliberately match ``raveui.data.Track`` (``pack`` is
    an alias for ``album``) so the existing playback service accepts it
    unchanged.
    """

    title: str
    url: str
    album: str = ""
    art: str = ""
    live: bool = False
    local: bool = False
    source: str = ""

    @property
    def pack(self):
        return self.album


@dataclass(frozen=True)
class ActionResult:
    """The result of one action, suitable for a footer line or notification.

    ``tracks`` is populated by ``play_all``/``shuffle``; a shell with no
    playlist support can queue the ``payload["tracks"]`` list itself.
    """

    ok: bool
    action: str
    message: str = ""
    payload: dict = field(default_factory=dict)
    track: object = None
    tracks: tuple = ()
    refresh: str = ""

    def __post_init__(self):
        object.__setattr__(self, "tracks", tuple(self.tracks or ()))


@dataclass(frozen=True)
class Link:
    """One About link or source credit."""

    label: str
    url: str = ""
    fact: str = ""


@dataclass(frozen=True)
class AboutInfo:
    """Facts, versions and links the About room renders.

    ``version`` is the data plugin's version; ``screen_version`` is this
    script add-on's version.  Keeping them separate matters because the two
    add-ons are released independently.
    """

    name: str = "Rave Player"
    version: str = ""
    screen_version: str = ""
    kodi_version: str = ""
    licence: str = "GPL-3.0-or-later"
    links: tuple = ()
    sources: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "links", tuple(self.links or ()))
        object.__setattr__(self, "sources", tuple(self.sources or ()))


# The About rows match the plugin's credits list; URL targets are data, never
# fetched by this module.
ABOUT_LINKS = (
    Link("Project page", PROJECT_URL, "github"),
    Link("Licence", LICENCE_URL, "GPL-3.0"),
    Link("Changelog", PROJECT_URL + "/blob/main/changelog.txt", "changes"),
)

ABOUT_SOURCES = (
    Link("Internet Archive", "https://archive.org", "archive.org"),
    Link("Mixcloud", "https://www.mixcloud.com", "add-on"),
    Link("SoundCloud", "https://soundcloud.com", "web only"),
    Link("radio-browser.info", "https://www.radio-browser.info", "directory"),
    Link("Moxser.com", "https://moxser.com", "moxser.com"),
    Link("Hardscore.com", "https://hardscore.com", "hardscore.com"),
    Link("DNB Radio", "https://dnbradio.com", "dnbradio.com"),
    Link("GetDarker.com", "https://getdarker.com", "getdarker.com"),
    Link("Pirate Radio Archives", "https://www.hardscore.com", "pirate archive"),
    Link("RaveTapePacks.com", "https://ravetapepacks.com", "rave tapes"),
    Link("JungleTapes.com", "https://jungletapes.com", "jungletapes.com"),
    Link("Toronto Rave Mixtape", "https://torontoravemixtapearchive.com",
         "toronto"),
)


# -------------------------------------------------------------------- texts
def _text(value, fallback=""):
    """Collapse whitespace (and lists); return ``fallback`` when empty."""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(part) for part in value)
    text = " ".join(str(value or "").split())
    return text or fallback


_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _clip(value, limit):
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[:max(0, limit - 1)].rstrip() + "…"


def _fact(value, fallback=""):
    """Return a single-line Label2 fact capped at 16 characters."""
    text = _text(value, fallback)
    if len(text) <= MAX_FACT_CHARS:
        return text
    return text[:MAX_FACT_CHARS - 1].rstrip() + "…"


def _clean_query(value):
    """Collapse, strip control characters and cap a user search term."""
    text = _text(_CONTROL_RE.sub(" ", str(value or "")))
    return text[:MAX_QUERY_CHARS].strip()


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _as_page(value):
    return max(1, _as_int(value, 1))


def normalise_page_size(value):
    """Snap any setting to the nearest of the 25/50/100 sizes."""
    size = _as_int(value, 0)
    if size <= 0:
        return DEFAULT_PAGE_SIZE
    return min(PAGE_SIZES, key=lambda allowed: abs(allowed - size))


def _paged(items, page, rows):
    """Return ``(window, page, pages, total)`` for an already-known list."""
    rows = max(1, _as_int(rows, DEFAULT_PAGE_SIZE))
    total = len(items)
    pages = max(1, (total + rows - 1) // rows)
    page = min(max(1, _as_int(page, 1)), pages)
    start = (page - 1) * rows
    return list(items[start:start + rows]), page, pages, total


def _size_fact(size):
    """Format a byte count as a <= 16 character Label2 fact."""
    size = _as_int(size, 0)
    if size <= 0:
        return ""
    if size >= 1024 * 1024 * 1024:
        return _fact("%.1f GB" % (size / float(1024 * 1024 * 1024)))
    if size >= 1024 * 1024:
        return _fact("%.1f MB" % (size / float(1024 * 1024)))
    if size >= 1024:
        return _fact("%.0f KB" % (size / float(1024)))
    return _fact("%d B" % size)


def _payload(row):
    """Read a row's action payload, accepting Row/dict/duck types."""
    if isinstance(row, Row):
        return dict(row.payload or {})
    if isinstance(row, dict):
        payload = row.get("payload")
        if isinstance(payload, dict):
            return dict(payload)
        return dict(row)
    payload = getattr(row, "payload", None)
    return dict(payload) if isinstance(payload, dict) else {}


def _rows_of(screen):
    """Return the rows from a Screen or a row list."""
    if isinstance(screen, Screen):
        return list(screen.rows)
    if isinstance(screen, (list, tuple)):
        return list(screen)
    if isinstance(screen, Row):
        return [screen]
    rows = getattr(screen, "rows", None)
    if isinstance(rows, (list, tuple)):
        return list(rows)
    return []


def _link(value):
    """Normalise a Link or a ``{label,url,fact}`` dict."""
    if isinstance(value, Link):
        return value
    if isinstance(value, dict):
        return Link(_text(value.get("label")), _text(value.get("url")),
                    _text(value.get("fact")))
    if isinstance(value, (list, tuple)) and value:
        return Link(_text(value[0]),
                    _text(value[1]) if len(value) > 1 else "",
                    _text(value[2]) if len(value) > 2 else "")
    return Link(_text(value))


def _about_info(value):
    """Normalise an AboutInfo or dict returned by a custom backend."""
    if isinstance(value, AboutInfo):
        return value
    if isinstance(value, dict):
        return AboutInfo(
            name=_text(value.get("name"), "Rave Player"),
            version=_text(value.get("version")),
            screen_version=_text(value.get("screen_version")),
            kodi_version=_text(value.get("kodi_version")),
            licence=_text(value.get("licence"), "GPL-3.0-or-later"),
            links=tuple(_link(link) for link in value.get("links") or ()),
            sources=tuple(_link(link) for link in value.get("sources") or ()),
        )
    return AboutInfo()


def _default_log(message):
    try:
        import xbmc

        xbmc.log("[script.raveplayer.ui] %s" % message, level=xbmc.LOGWARNING)
    except Exception:  # noqa: BLE001 - logging never breaks a screen
        pass


def _script_root():
    """The ``script.raveplayer.ui`` directory (three levels above this file)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


# ------------------------------------------------------------------ backend
class PluginBackend:
    """Read/write adapter over ``plugin.audio.raveplayer``'s public modules.

    Every method is lazy: nothing is imported until a handler asks for data.
    ``modules`` can be injected with a test namespace, following
    :class:`raveui.data.RaveData`'s pattern.
    """

    def __init__(self, modules=None, addon_factory=None):
        self._modules = modules
        self._addon_factory = addon_factory

    @property
    def modules(self):
        if self._modules is None:
            self._modules = pluginbridge.load_plugin(self._addon_factory)
        return self._modules

    def _module(self, name):
        """Return a plugin module not pre-loaded by ``pluginbridge``.

        ``pluginbridge`` installs the plugin tree under the private
        ``raveplayer_plugin`` alias, so extra public modules (favourites,
        downloads, handoff) can be imported without editing the bridge or
        colliding with this add-on's own ``resources`` package.
        """
        module = getattr(self.modules, name, None)
        if module is not None:
            return module
        module = importlib.import_module(
            "%s.resources.lib.%s" % (pluginbridge.PLUGIN_ALIAS, name))
        try:
            setattr(self.modules, name, module)
        except Exception:  # noqa: BLE001 - read-only namespace is still enough
            pass
        return module

    # ------------------------------------------------------------- reading
    def scope(self):
        try:
            return _text(self.modules.latest.RAVE_COLLECTION, DEFAULT_SCOPE)
        except Exception:  # noqa: BLE001 - default scope keeps search useful
            return DEFAULT_SCOPE

    def page_size(self):
        try:
            value = self.modules.kodi.setting_int(
                "results_per_page", DEFAULT_PAGE_SIZE)
        except Exception:  # noqa: BLE001 - missing setting means 50
            value = DEFAULT_PAGE_SIZE
        return normalise_page_size(value)

    def search(self, query, page, rows):
        docs, total = self.modules.archive.search(
            query, page=page, rows=rows)
        if not isinstance(docs, list):
            docs = []
        return docs, max(0, _as_int(total))

    def archive_thumb(self, identifier):
        return _text(self.modules.archive.thumb(identifier))

    def art(self, name):
        """Return a real sticker path from the plugin (or script) art tree."""
        name = _text(name)
        if not name:
            return ""
        try:
            root = _text(self.modules.root)
        except Exception:  # noqa: BLE001 - the plugin may be unavailable
            root = ""
        candidates = []
        if root:
            candidates.append(os.path.join(root, "resources", "art", name))
        candidates.append(os.path.join(
            _script_root(), "resources", "art", "rave-screen", name))
        for path in candidates:
            if os.path.isfile(path):
                return path
        return ""

    def favourites(self):
        return list(self._module("favourites").load() or [])

    def favourite_key(self, entry):
        return _text(self._module("favourites").key(entry))

    def favourite_has(self, entry):
        return bool(self._module("favourites").has(entry))

    def favourite_add(self, entry):
        return bool(self._module("favourites").add(entry))

    def favourite_remove(self, key):
        return bool(self._module("favourites").remove(key))

    def downloads(self):
        return list(self._module("downloads").list_downloads() or [])

    def download_plan(self, url, title, source):
        return self._module("downloads").plan(url, title, source)

    def download(self, plan, progress=None, cancelled=None):
        return self._module("downloads").download(
            plan, progress=progress, cancelled=cancelled)

    def download_delete(self, key):
        return bool(self._module("downloads").delete(key))

    def playable_url(self, url):
        return _text(self._module("http").safe_stream_url(url))

    def platform_kind(self, url):
        try:
            return _text(self._module("handoff").platform_kind(url))
        except Exception:  # noqa: BLE001 - no hand-off is not a fatal error
            return ""

    def about(self):
        version = ""
        try:
            version = _text(self.modules.addon.getAddonInfo("version"))
        except Exception:  # noqa: BLE001 - About still renders without plugin
            version = ""
        return AboutInfo(
            name="Rave Player",
            version=version,
            screen_version=_script_addon_version(),
            kodi_version=_kodi_version(),
            licence="GPL-3.0-or-later",
            links=ABOUT_LINKS,
            sources=ABOUT_SOURCES,
        )


def _script_addon_version():
    try:
        import xbmcaddon

        return _text(xbmcaddon.Addon().getAddonInfo("version"))
    except Exception:  # noqa: BLE001 - tests / missing add-on metadata
        return ""


def _kodi_version():
    try:
        import xbmc

        raw = _text(xbmc.getInfoLabel("System.BuildVersion"))
    except Exception:  # noqa: BLE001 - outside Kodi
        return ""
    return raw.split()[0] if raw else ""


# ------------------------------------------------------------------ screens
class LibraryScreens:
    """Handlers for the four library rooms.

    A shell creates one instance, paints :meth:`loading` while a worker runs a
    room handler, then paints the returned :class:`Screen`.  Actions are
    deliberately synchronous and tiny; only :meth:`download` blocks (the shell
    should run it on a worker and pass a progress callback).
    """

    def __init__(self, backend=None, playback=None, page_size=None,
                 logger=None, random_module=None, queue=None):
        self.backend = backend if backend is not None else PluginBackend()
        self.playback = playback
        self.queue = queue
        self._page_size_override = (
            None if page_size is None else normalise_page_size(page_size))
        self._logger = logger or _default_log
        self._random = random_module or _random.Random()
        self._lock = threading.Lock()
        self._progress = {}
        self._page_size_cache = None

    # ----------------------------------------------------------- primitives
    def page_size(self):
        if self._page_size_override is not None:
            return self._page_size_override
        try:
            resolved = normalise_page_size(self.backend.page_size())
        except Exception:  # noqa: BLE001 - a broken setting never blocks a list
            resolved = DEFAULT_PAGE_SIZE
        self._page_size_cache = resolved
        return resolved

    def set_page_size(self, size):
        """Apply the shell's Rows-per-page choice to every library room."""
        try:
            self._page_size_override = normalise_page_size(size)
        except Exception:  # noqa: BLE001 - keep the last valid size
            return self.page_size()
        self._page_size_cache = self._page_size_override
        return self._page_size_override

    def _page_size_hint(self):
        """The page size for a loading/back screen without loading the plugin."""
        if self._page_size_override is not None:
            return self._page_size_override
        return self._page_size_cache or DEFAULT_PAGE_SIZE

    def scope(self):
        try:
            return _text(self.backend.scope(), DEFAULT_SCOPE)
        except Exception:  # noqa: BLE001
            return DEFAULT_SCOPE

    def loading(self, route, query="", page=1):
        """The Screen the shell paints while a worker runs a handler."""
        route = route if route in TITLES else ROUTE_SEARCH
        return Screen(
            route=route,
            title=TITLES.get(route, TITLE_SEARCH),
            subtitle="Loading…",
            state=STATE_LOADING,
            page=_as_page(page),
            page_size=self._page_size_hint(),
            query=_clean_query(query),
            code=CODES.get(route, ""),
        )

    def back(self, screen):
        """Return the parent Screen, or ``None`` for "leave to Rave home".

        Search results step back to the idle Search room (the query cleared,
        no request); every other room — and an already-idle Search — returns
        ``None`` so the shell pops the library overlay and shows the Rave
        Screen home.  Paging is explicit (``search(query, page ± 1)``); Back
        never silently changes page.
        """
        if screen is None:
            return None
        route = getattr(screen, "route", "")
        query = _clean_query(getattr(screen, "query", ""))
        if route == ROUTE_SEARCH and query:
            size = normalise_page_size(
                getattr(screen, "page_size", DEFAULT_PAGE_SIZE))
            return self._idle_search(size)
        return None

    def retry(self, target, page=None):
        """Re-run the handler named by a Screen, retry row or route string."""
        route, query, target_page = self._target(target)
        wanted = _as_page(page if page is not None else target_page)
        if route == ROUTE_SEARCH:
            return self.search(query, wanted)
        if route == ROUTE_FAVOURITES:
            return self.favourites(wanted)
        if route == ROUTE_DOWNLOADS:
            return self.downloads(wanted)
        if route == ROUTE_ABOUT:
            return self.about()
        return Screen(route=route, title=TITLE_SEARCH,
                      subtitle="Nothing to retry", state=STATE_ERROR,
                      page_size=self.page_size(), error=_NOTHING_TO_RETRY,
                      code=CODES.get(route, ""))

    # --------------------------------------------------------------- rooms
    def search(self, query, page=1):
        """Scoped Archive.org search, one page at a time.

        The user's words are always AND-ed with the curated collection scope
        (``latest.RAVE_COLLECTION``) — the same guard the plugin route uses, so
        "dreamscape" cannot return YouTube rips or audiobooks.
        """
        term = _clean_query(query)
        size = self.page_size()
        page = _as_page(page)
        if not term:
            return self._idle_search(size)
        scoped = "%s AND %s" % (term, self.scope())
        try:
            docs, total = self._fetch_search(scoped, page, size)
            pages = max(1, (total + size - 1) // size)
            if page > pages:
                # The archive is server-side; jump to the last real page
                # instead of showing an empty screen for a stale bookmark.
                page = pages
                docs, total = self._fetch_search(scoped, page, size)
                pages = max(1, (total + size - 1) // size)
                if page > pages:
                    page = pages
        except Exception as exc:  # noqa: BLE001 - show a retry row, never crash
            return self._error_screen(ROUTE_SEARCH, term, page, size, exc)
        rows = []
        for doc in docs:
            row = self._search_row(doc)
            if row is not None:
                rows.append(row)
        if not rows:
            return self._empty_screen(
                ROUTE_SEARCH, term, page, size, "No matching packs",
                "Search again")
        subtitle = "%s · %s packs" % (_clip(term, 22), _count(total))
        return Screen(
            route=ROUTE_SEARCH,
            title=TITLE_SEARCH,
            subtitle=subtitle,
            rows=tuple(rows),
            state=STATE_READY,
            page=page,
            pages=pages,
            total=total,
            page_size=size,
            query=term,
            noun="packs",
            code=CODE_SEARCH,
        )

    def favourites(self, page=1):
        """Saved packs, shows, stations and streams, newest first."""
        size = self.page_size()
        page = _as_page(page)
        try:
            entries = [entry for entry in (self.backend.favourites() or [])
                       if isinstance(entry, dict)]
        except Exception as exc:  # noqa: BLE001
            return self._error_screen(ROUTE_FAVOURITES, "", page, size, exc)
        rows = [row for row in (self._favourite_row(entry)
                                for entry in entries) if row is not None]
        window, page, pages, total = _paged(rows, page, size)
        if not total:
            return self._empty_screen(
                ROUTE_FAVOURITES, "", page, size, "No favourites yet",
                "Refresh favourites", FAVOURITES_IDLE_SUBTITLE)
        subtitle = "%s saved" % _count(total)
        if pages > 1:
            subtitle += " · p%d/%d" % (page, pages)
        return Screen(
            route=ROUTE_FAVOURITES,
            title=TITLE_FAVOURITES,
            subtitle=subtitle,
            rows=tuple(window),
            state=STATE_READY,
            page=page,
            pages=pages,
            total=total,
            page_size=size,
            noun="favourites",
            code=CODE_FAVOURITES,
        )

    def downloads(self, page=1):
        """Offline copies plus the live DownloadQueue's active rows.

        The queue is the only source of in-flight progress/cancel; the plugin
        index is the only source of completed files.  Merging them here means
        the Downloads room can never again promise progress it does not show
        (P1-5).
        """
        size = self.page_size()
        page = _as_page(page)
        try:
            entries = [entry for entry in (self.backend.downloads() or [])
                       if isinstance(entry, dict)]
        except Exception as exc:  # noqa: BLE001
            return self._error_screen(ROUTE_DOWNLOADS, "", page, size, exc)
        rows = []
        queue_rows = []
        if self.queue is not None:
            try:
                queue_rows = [row for row in (self.queue.rows() or [])
                              if isinstance(row, dict)]
            except Exception as exc:  # noqa: BLE001 - a dead queue is not fatal
                self._log("download queue read failed: %s" % exc)
                queue_rows = []
        for item in queue_rows:
            row = self._queue_row(item)
            if row is not None:
                rows.append(row)
        rows.extend(row for row in (self._download_row(entry)
                                    for entry in entries) if row is not None)
        window, page, pages, total = _paged(rows, page, size)
        if not total:
            return self._empty_screen(
                ROUTE_DOWNLOADS, "", page, size, "No downloads yet",
                "Refresh downloads", DOWNLOADS_IDLE_SUBTITLE)
        saved = sum(_as_int(entry.get("size")) for entry in entries
                    if entry.get("exists"))
        active = sum(1 for row in queue_rows
                     if _text(row.get("status")).lower() in
                     ("queued", "checking", "downloading", "cancelling"))
        subtitle = "%s files" % _count(total)
        if active:
            subtitle = "%d active · %s" % (active, subtitle)
        size_fact = _size_fact(saved)
        if size_fact:
            subtitle += " · %s" % size_fact
        if pages > 1:
            subtitle += " · p%d/%d" % (page, pages)
        return Screen(
            route=ROUTE_DOWNLOADS,
            title=TITLE_DOWNLOADS,
            subtitle=subtitle,
            rows=tuple(window),
            state=STATE_READY,
            page=page,
            pages=pages,
            total=total,
            page_size=size,
            noun="downloads",
            code=CODE_DOWNLOADS,
        )

    def about(self):
        """Versions, licence, links and every source the add-on uses."""
        size = self.page_size()
        try:
            info = _about_info(self.backend.about())
        except Exception as exc:  # noqa: BLE001
            return self._error_screen(ROUTE_ABOUT, "", 1, size, exc)
        icon = self._art("about.png")
        fanart = self._art("fanart-about.jpg")
        rows = [
            self._about_row("Rave Player", info.version or "unknown",
                            PROJECT_URL, icon, fanart,
                            "Rave Player data add-on version."),
            self._about_row("Rave Screen", info.screen_version or "dev",
                            PROJECT_URL, icon, fanart,
                            "Full-screen Rave UI script version."),
            self._about_row("Kodi", info.kodi_version or "unknown",
                            KODI_URL, icon, fanart, "Kodi build in use."),
            self._about_row("Licence", info.licence or "GPL-3.0",
                            LICENCE_URL, icon, fanart,
                            "GNU General Public License v3.0 or later."),
        ]
        for link in tuple(info.links or ()) + tuple(info.sources or ()):
            link = _link(link)
            rows.append(self._about_row(
                link.label, link.fact or "open", link.url, icon, fanart,
                link.url or link.label))
        subtitle = _clip("%s %s · %s" % (info.name or "Rave Player",
                                         info.version or "",
                                         info.licence or ""), 40)
        return Screen(
            route=ROUTE_ABOUT,
            title=TITLE_ABOUT,
            subtitle=subtitle.strip(" ·"),
            rows=tuple(rows),
            state=STATE_READY,
            page=1,
            pages=1,
            total=len(rows),
            page_size=size,
            noun="facts",
            code=CODE_ABOUT,
        )

    # ------------------------------------------------------------- actions
    def play(self, row, playback=None):
        """Play one track row.  Unsafe or empty URLs are refused, not passed on."""
        payload = _payload(row)
        url = self._play_url(payload)
        title = _text(payload.get("title"), "Untitled")
        if not url:
            return ActionResult(
                False, ACTION_PLAY, "That stream is not playable.",
                payload=dict(payload, title=title))
        item = self._play_item(payload, url)
        player = playback if playback is not None else self.playback
        if player is None:
            return ActionResult(
                True, ACTION_PLAY, "Playing %s" % title,
                payload=dict(payload, url=url, title=title), track=item)
        try:
            result = player.play(item)
        except Exception as exc:  # noqa: BLE001 - bad URL / Kodi API failure
            self._log("play failed for %s: %s" % (title, exc))
            return ActionResult(False, ACTION_PLAY,
                                "Could not start playback.", track=item)
        message = _text(getattr(result, "text", ""), "Playing %s" % title)
        return ActionResult(
            True, ACTION_PLAY, message,
            payload=dict(payload, url=url, title=title), track=item)

    def play_all(self, screen, shuffle=False):
        """Queue every playable row on a Screen (current page).

        ``PlaybackService`` has no queue method, so without an injected
        ``playback.play_all`` this returns the validated ordered track list in
        ``payload["tracks"]`` for the shell to queue.  With a player that
        exposes ``play_all(tracks, shuffle=...)`` the shell can consume the
        result directly.
        """
        action = ACTION_SHUFFLE if shuffle else ACTION_PLAY_ALL
        items = []
        for row in _rows_of(screen):
            payload = _payload(row)
            if (getattr(row, "kind", "") != KIND_TRACK
                    and payload.get("action") != ACTION_PLAY):
                continue
            url = self._play_url(payload)
            if url:
                items.append(self._play_item(payload, url))
        if not items:
            return ActionResult(False, action, "Nothing to play on this page.")
        if shuffle:
            self._random.shuffle(items)
        message = "Queued %d track%s%s" % (
            len(items), "" if len(items) == 1 else "s",
            " · shuffled" if shuffle else "")
        queue = [self._item_payload(item) for item in items]
        runner = getattr(self.playback, "play_all", None)
        if callable(runner):
            try:
                result = runner(items, shuffle=shuffle)
            except Exception as exc:  # noqa: BLE001
                self._log("play_all failed: %s" % exc)
                return ActionResult(False, action, "Could not start playback.",
                                    tracks=tuple(items),
                                    payload={"tracks": queue,
                                             "shuffle": shuffle})
            message = _text(getattr(result, "text", ""), message)
        return ActionResult(
            True, action, message, payload={"tracks": queue,
                                            "shuffle": shuffle},
            tracks=tuple(items))

    def shuffle(self, screen):
        """Alias for ``play_all(screen, shuffle=True)``."""
        return self.play_all(screen, shuffle=True)

    def download(self, row, progress=None, cancelled=None):
        """Plan and download a track row; ``progress(done, total)`` is forwarded.

        This is the one blocking action; the shell should run it on a worker
        and poll :meth:`progress` for the footer.  It never raises for a
        refused plan (the plugin's eligibility/size checks are surfaced in the
        message) and records the last progress under the row's URL.
        """
        payload = _payload(row)
        url = _text(payload.get("url"))
        title = _text(payload.get("title"), "Rave Player download")
        source = _text(payload.get("source"))
        if payload.get("local"):
            return ActionResult(False, ACTION_DOWNLOAD,
                                "That track is already downloaded.",
                                payload=dict(payload))
        if not url:
            return ActionResult(False, ACTION_DOWNLOAD,
                                "That row has no download URL.",
                                payload=dict(payload))
        try:
            plan = self.backend.download_plan(url, title, source)
        except Exception as exc:  # noqa: BLE001 - network/probe failure
            self._log("download plan failed for %s: %s" % (title, exc))
            return ActionResult(False, ACTION_DOWNLOAD,
                                "Could not prepare the download.",
                                payload=dict(payload, title=title,
                                             source=source))
        if not isinstance(plan, dict):
            plan = {}
        if not plan.get("allowed"):
            return ActionResult(
                False, ACTION_DOWNLOAD,
                _text(plan.get("reason"), "Download not available."),
                payload=dict(payload, title=title, source=source))
        total = _as_int(plan.get("size"))
        self._set_progress(url, {
            "url": url, "title": title, "source": source,
            "done": 0, "total": total,
            "percent": 0, "active": True, "error": "",
        })

        def report(done, total_bytes):
            done = max(0, _as_int(done))
            total_bytes = max(0, _as_int(total_bytes)) or total
            percent = int(done * 100 / total_bytes) if total_bytes else 0
            self._set_progress(url, {
                "url": url, "title": title, "source": source,
                "done": done, "total": total_bytes,
                "percent": max(0, min(100, percent)),
                "active": True, "error": "",
            })
            if progress is not None:
                try:
                    progress(done, total_bytes)
                except Exception:  # noqa: BLE001 - UI progress is decorative
                    pass

        try:
            result = self.backend.download(
                plan, progress=report, cancelled=cancelled)
        except Exception as exc:  # noqa: BLE001 - report, never traceback
            self._log("download failed for %s: %s" % (title, exc))
            self._finish_progress(url, error=str(exc))
            return ActionResult(
                False, ACTION_DOWNLOAD, "Download failed.",
                payload=dict(payload, title=title, source=source))
        if isinstance(result, dict):
            ok = bool(result.get("ok"))
            reason = _text(result.get("reason"))
        else:
            ok = bool(result)
            reason = ""
        current = self.progress(url)
        self._finish_progress(
            url,
            done=current.get("total", total) if ok else current.get("done", 0),
            error="" if ok else (reason or "Download failed."))
        message = ("Downloaded %s" % title) if ok else (
            _clip(reason or "Download failed.", 80))
        return ActionResult(
            ok, ACTION_DOWNLOAD, message,
            payload=dict(payload, title=title, source=source,
                         path=_text(plan.get("path")),
                         download_key=_text(plan.get("key"))),
            refresh=ROUTE_DOWNLOADS)

    def favourite(self, row):
        """Add (or refresh) the row's source as a favourite."""
        payload = _payload(row)
        kind = _text(payload.get("favourite_kind"), "stream")
        target = _text(payload.get("target") or payload.get("url"))
        title = _text(payload.get("title"))
        source = _text(payload.get("source"))
        if payload.get("local"):
            return ActionResult(False, ACTION_FAVOURITE,
                                "That file is already downloaded.")
        if not target or not title:
            return ActionResult(False, ACTION_FAVOURITE,
                                "That row cannot be favourited.")
        entry = {"kind": kind, "target": target, "title": title,
                 "source": source}
        try:
            already = bool(self.backend.favourite_has(entry))
            saved = bool(self.backend.favourite_add(entry))
        except Exception as exc:  # noqa: BLE001 - read-only profile, bad store
            self._log("favourite failed for %s: %s" % (title, exc))
            return ActionResult(False, ACTION_FAVOURITE,
                                "Could not save that favourite.",
                                payload=entry)
        if not saved:
            return ActionResult(False, ACTION_FAVOURITE,
                                "Could not save that favourite.",
                                payload=entry)
        return ActionResult(
            True, ACTION_FAVOURITE,
            "Already in favourites" if already else "Added to favourites",
            payload=entry, refresh=ROUTE_FAVOURITES)

    def remove(self, row):
        """Remove a favourite or delete a downloaded file, whichever the row is."""
        payload = _payload(row)
        key = _text(payload.get("favourite_key"))
        if key:
            try:
                ok = bool(self.backend.favourite_remove(key))
            except Exception as exc:  # noqa: BLE001
                self._log("favourite remove failed: %s" % exc)
                return ActionResult(False, ACTION_REMOVE,
                                    "Could not remove that favourite.")
            return ActionResult(ok, ACTION_REMOVE,
                                "Removed from favourites" if ok else
                                "That favourite was not found.",
                                refresh=ROUTE_FAVOURITES)
        key = _text(payload.get("download_key"))
        if key and payload.get("queue"):
            # A failed/cancelled queue row is not in the plugin's completed
            # index; clear it from the queue store instead (P1-5).
            try:
                ok = bool(self.queue is not None and self.queue.dismiss(key))
            except Exception as exc:  # noqa: BLE001
                self._log("download queue dismiss failed: %s" % exc)
                ok = False
            return ActionResult(ok, ACTION_REMOVE,
                                "Download removed" if ok else
                                "That download is no longer in the queue.",
                                refresh=ROUTE_DOWNLOADS)
        if key:
            try:
                ok = bool(self.backend.download_delete(key))
            except Exception as exc:  # noqa: BLE001
                self._log("download delete failed: %s" % exc)
                return ActionResult(False, ACTION_REMOVE,
                                    "Could not delete that download.")
            return ActionResult(ok, ACTION_REMOVE,
                                "Download deleted" if ok else
                                "That download was not found.",
                                refresh=ROUTE_DOWNLOADS)
        return ActionResult(False, ACTION_REMOVE, "Nothing to remove.")

    # ----------------------------------------------------------- progress
    def progress(self, url=""):
        """Return a copy of one download's progress, or all of them."""
        with self._lock:
            if url:
                item = self._progress.get(url)
                return dict(item) if item else {}
            return [dict(item) for item in self._progress.values()]

    def _set_progress(self, url, values):
        with self._lock:
            self._progress[url] = dict(values)

    def _finish_progress(self, url, done=None, error=""):
        with self._lock:
            item = self._progress.get(url)
            if item is None:
                return
            item = dict(item)
            if done is not None:
                item["done"] = max(0, _as_int(done))
                if item.get("total"):
                    item["percent"] = max(0, min(
                        100, int(item["done"] * 100 / item["total"])))
            item["active"] = False
            item["error"] = _text(error)[:MAX_ERROR_CHARS]
            self._progress[url] = item

    # ------------------------------------------------------------ internals
    def _fetch_search(self, scoped, page, size):
        docs, total = self.backend.search(scoped, page, size)
        if not isinstance(docs, list):
            docs = []
        return [doc for doc in docs if isinstance(doc, dict)], max(0, _as_int(total))

    def _target(self, target):
        if isinstance(target, Screen):
            return target.route, _clean_query(target.query), target.page
        if isinstance(target, Row):
            target = target.payload
        if isinstance(target, dict):
            return (_text(target.get("route")), _clean_query(target.get("query")),
                    _as_page(target.get("page")))
        if isinstance(target, str):
            return _text(target), "", 1
        return "", "", 1

    def _idle_search(self, size):
        return Screen(
            route=ROUTE_SEARCH,
            title=TITLE_SEARCH,
            subtitle=SEARCH_IDLE_SUBTITLE,
            state=STATE_EMPTY,
            page=1,
            pages=1,
            total=0,
            page_size=size,
            query="",
            noun="packs",
            code=CODE_SEARCH,
        )

    def _empty_screen(self, route, query, page, size, subtitle, retry_label,
                      detail=""):
        payload = {"action": ACTION_RETRY, "route": route,
                   "query": query, "page": page}
        row = Row(
            label=retry_label,
            kind=KIND_ACTION,
            fact="again",
            icon=self._art("about.png") if route == ROUTE_ABOUT else "",
            code=CODES.get(route, ""),
            payload=payload,
            plot=detail or "Press OK to load this room again.",
        )
        return Screen(
            route=route,
            title=TITLES.get(route, TITLE_SEARCH),
            subtitle=subtitle,
            rows=(row,),
            state=STATE_EMPTY,
            page=page,
            pages=1,
            total=0,
            page_size=size,
            query=query,
            noun="items",
            code=CODES.get(route, ""),
        )

    def _error_screen(self, route, query, page, size, exc):
        self._log("%s screen failed: %s" % (route or "library", exc))
        payload = {"action": ACTION_RETRY, "route": route,
                   "query": query, "page": page}
        row = Row(
            label="Retry",
            kind=KIND_ACTION,
            fact="again",
            code=CODES.get(route, ""),
            payload=payload,
            plot="Press OK to try that room again.",
        )
        return Screen(
            route=route,
            title=TITLES.get(route, TITLE_SEARCH),
            subtitle="Could not load",
            rows=(row,),
            state=STATE_ERROR,
            page=page,
            pages=1,
            total=0,
            page_size=size,
            query=query,
            error=_clip(_text(exc, "Unknown error"), MAX_ERROR_CHARS),
            noun="items",
            code=CODES.get(route, ""),
        )

    def _search_row(self, doc):
        identifier = _text(doc.get("identifier"))
        if not identifier:
            return None
        title = _text(doc.get("title"), identifier)
        year = _text(doc.get("year"))
        thumb = self._thumb(identifier)
        payload = {
            "room": "pack",
            "mode": "archive_item",
            "identifier": identifier,
            "source": "Archive.org",
            "favourite_kind": "pack",
            "target": identifier,
            "title": title,
        }
        return Row(
            label=title,
            kind=KIND_ROOM,
            fact=_fact(year, "pack"),
            icon=thumb or self._art("search.png"),
            fanart=self._art("fanart-search.jpg"),
            code=CODE_SEARCH,
            payload=payload,
            subtitle="Internet Archive" + (" · " + year if year else ""),
            plot="Tape pack on the Internet Archive." + (
                " · " + year if year else ""),
        )

    def _thumb(self, identifier):
        try:
            return _text(self.backend.archive_thumb(identifier))
        except Exception:  # noqa: BLE001 - art is optional
            return ""

    def _favourite_row(self, entry):
        kind = _text(entry.get("kind"), "stream").lower()
        target = _text(entry.get("target"))
        if not target:
            return None
        title = _text(entry.get("title"), target)
        source = _text(entry.get("source"))
        key = self._favourite_key(entry)
        base = {"favourite_key": key, "favourite_kind": kind,
                "target": target, "title": title, "source": source}
        icon = self._art("favourites.png")
        fanart = self._art("fanart-favourites.jpg")
        if kind == "pack":
            return self._room_row(
                title, "pack", source or "Archive.org",
                dict(base, room="pack", mode="archive_item",
                     identifier=target),
                icon, fanart, "Tape pack · Internet Archive")
        if kind == "legacy_pack":
            return self._room_row(
                title, "legacy_pack", source or "RaveTapePacks",
                dict(base, room="pack", mode="legacy_pack", pack=target),
                icon, fanart, "Tape pack · RaveTapePacks.com")
        if kind == "legacy_post":
            return self._room_row(
                title, "legacy_post", source or "RaveTapePacks",
                dict(base, room="pack", mode="legacy_post", post=target),
                icon, fanart, "Tape pack · RaveTapePacks.com")
        if kind == "legacy_jt":
            return self._room_row(
                title, "legacy_jt", source or "JungleTapes",
                dict(base, room="pack", mode="legacy_jt_show", key=target),
                icon, fanart, "Jungle radio show · JungleTapes.com")
        if kind == "dnb":
            return self._room_row(
                title, "dnb", source or "DNB Radio",
                dict(base, room="track", mode="dnb_play", id=target),
                icon, fanart, "DNB Radio show")
        platform = self._platform(target)
        if platform:
            return self._room_row(
                title, "platform", "add-on",
                dict(base, room="platform", mode="handoff",
                     platform=platform),
                icon, fanart,
                "Saved %s link — opens in its Kodi add-on." % platform)
        playable = self._playable(target)
        if playable:
            live = "live" in source.lower()
            payload = dict(
                base, action=ACTION_PLAY, url=playable, album=source or "Favourites",
                art=icon, live=live)
            return Row(
                label=title,
                kind=KIND_TRACK,
                fact=_fact(source, "stream"),
                icon=icon,
                fanart=fanart,
                code=CODE_FAVOURITES,
                payload=payload,
                subtitle=source,
                plot="Saved stream" + (" · " + source if source else ""),
            )
        # Unplayable/dead target: keep the row so it can be removed.
        return Row(
            label=title,
            kind=KIND_ACTION,
            fact="stale",
            icon=icon,
            fanart=fanart,
            code=CODE_FAVOURITES,
            payload=dict(base, action=ACTION_REMOVE),
            subtitle=source,
            plot="That link is no longer playable — remove it or save it again.",
        )

    def cancel(self, row):
        """Cancel one active DownloadQueue row from the Downloads room."""
        payload = _payload(row)
        key = _text(payload.get("download_key") or payload.get("target"))
        if self.queue is None:
            return ActionResult(False, ACTION_CANCEL,
                                "Downloads are not available in this build.")
        try:
            ok = bool(self.queue.cancel(key))
        except Exception as exc:  # noqa: BLE001 - queue failure is a row state
            self._log("download cancel failed: %s" % exc)
            ok = False
        return ActionResult(
            ok, ACTION_CANCEL,
            "Cancelling download…" if ok else "That download is no longer running.",
            payload=dict(payload), refresh=ROUTE_DOWNLOADS)

    def _queue_row(self, entry):
        """One in-flight/failed DownloadQueue row as a Downloads list row."""
        key = _text(entry.get("key"))
        if not key:
            return None
        status = _text(entry.get("status"), "queued").lower()
        title = _text(entry.get("title"), "Download")
        source = _text(entry.get("source"))
        detail = _text(entry.get("detail"))
        icon = self._art("downloads.png")
        # Download rows are their own room: the neutral screen bed.  They used
        # to borrow fanart-favourites.jpg, which made Downloads paint the
        # FAVOURITES hero (3.9.54 device QA P2-1).
        fanart = self._downloads_hero()
        if status in ("queued", "checking", "downloading", "cancelling"):
            percent = max(0, min(100, _as_int(entry.get("percent"))))
            if status == "downloading" and (_as_int(entry.get("total"))
                                            or percent):
                fact = "%d%%" % percent
            elif status == "downloading":
                fact = "downloading"
            elif status == "cancelling":
                fact = "cancelling"
            elif status == "checking":
                fact = "checking"
            else:
                fact = "queued"
            return Row(
                label=title,
                kind=KIND_ACTION,
                fact=_fact(fact),
                icon=icon,
                fanart=fanart,
                code=CODE_DOWNLOADS,
                payload={"action": ACTION_CANCEL, "download_key": key,
                         "target": key, "title": title, "queue": True},
                subtitle=("Downloading" if source else "Download queue"),
                plot=detail or "Active download — press OK to cancel.",
            )
        # A failed/cancelled attempt stays visible until the user clears it.
        return Row(
            label=title,
            kind=KIND_ACTION,
            fact=_fact(status, "failed"),
            icon=icon,
            fanart=fanart,
            code=CODE_DOWNLOADS,
            payload={"action": ACTION_REMOVE, "download_key": key,
                     "target": key, "title": title, "queue": True},
            subtitle=("Download failed" if status == "failed"
                      else "Download cancelled"),
            plot=detail or "That download did not finish — remove it.",
        )

    def _download_row(self, entry):
        key = _text(entry.get("key"))
        path = _text(entry.get("path"))
        title = _text(entry.get("title"), "Download")
        source = _text(entry.get("source"))
        exists = bool(entry.get("exists"))
        icon = self._art("downloads.png")
        fanart = self._downloads_hero()
        if exists and path:
            payload = {
                "action": ACTION_PLAY,
                "url": path,
                "title": title,
                "album": "Downloads",
                "local": True,
                "source": source,
                "download_key": key,
            }
            return Row(
                label=title,
                kind=KIND_TRACK,
                fact=_size_fact(entry.get("size")),
                icon=icon,
                fanart=fanart,
                code=CODE_DOWNLOADS,
                payload=payload,
                subtitle="Offline copy",
                plot="Downloaded%s — plays without a network." % (
                    " · " + source if source else ""),
            )
        return Row(
            label=title,
            kind=KIND_ACTION,
            fact="missing",
            icon=icon,
            fanart=fanart,
            code=CODE_DOWNLOADS,
            payload={"action": ACTION_REMOVE, "download_key": key,
                     "target": path, "title": title},
            subtitle="Offline copy",
            plot="The file is missing — delete the entry or download it again.",
        )

    def _room_row(self, title, room, fact, payload, icon, fanart, plot):
        return Row(
            label=title,
            kind=KIND_ROOM,
            fact=_fact(fact, "saved"),
            icon=icon,
            fanart=fanart,
            code=CODE_FAVOURITES,
            payload=payload,
            subtitle=fact,
            plot=plot,
        )

    def _about_row(self, label, fact, url, icon, fanart, plot):
        return Row(
            label=label,
            kind=KIND_ACTION,
            fact=_fact(fact, "open"),
            icon=icon,
            fanart=fanart,
            code=CODE_ABOUT,
            payload={"action": ACTION_OPEN, "url": _text(url)},
            subtitle="About & Sources",
            plot=_text(plot),
        )

    def _favourite_key(self, entry):
        try:
            key = _text(self.backend.favourite_key(entry))
        except Exception:  # noqa: BLE001 - derive the same key locally
            key = ""
        return key or "%s:%s" % (_text(entry.get("kind")), _text(entry.get("target")))

    def _platform(self, url):
        try:
            return _text(self.backend.platform_kind(url))
        except Exception:  # noqa: BLE001 - no platform match
            return ""

    def _playable(self, url):
        try:
            return _text(self.backend.playable_url(url))
        except Exception:  # noqa: BLE001 - treat an unusable URL as stale
            return ""

    def _play_url(self, payload):
        """Validate a play URL; local downloads bypass the public-stream guard."""
        url = _text(payload.get("url"))
        if not url:
            return ""
        if payload.get("local"):
            # Downloaded files are filesystem paths (or special://); the
            # stream guard would reject them for not being public http(s).
            return url
        return self._playable(url)

    def _play_item(self, payload, url):
        return PlayItem(
            title=_text(payload.get("title"), "Untitled"),
            url=url,
            album=_text(payload.get("album") or payload.get("source")),
            art=_text(payload.get("art")) or self._art("rave.png"),
            live=bool(payload.get("live")),
            local=bool(payload.get("local")),
            source=_text(payload.get("source")),
        )

    @staticmethod
    def _item_payload(item):
        return {
            "title": item.title,
            "url": item.url,
            "album": item.album,
            "art": item.art,
            "live": item.live,
            "local": item.local,
            "source": item.source,
        }

    def _downloads_hero(self):
        """The unlabelled screen bed used by the Downloads room.

        A Downloads row must never carry another room's branded fanart: the
        Favourites fanart says FAVOURITES on the poster, so reusing it made the
        Downloads room look like Favourites (3.9.54 device QA P2-1).
        """
        for name in ("screen-bed-1920x1080.jpg", "screen-bed-1280x720.jpg",
                     "fanart-screen.jpg"):
            path = self._art(name)
            if path:
                return path
        return ""

    def _art(self, name):
        try:
            return _text(self.backend.art(name))
        except Exception:  # noqa: BLE001 - optional art
            return ""

    def _log(self, message):
        try:
            self._logger(message)
        except Exception:  # noqa: BLE001 - logging never breaks a screen
            pass
