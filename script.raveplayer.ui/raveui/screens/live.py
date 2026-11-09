# -*- coding: utf-8 -*-
"""Live Radio screen data and actions.

The screen has four rows: the three curated stations that always play (Kool FM,
Rinse FM, Centreforce 883) and a Pirate Radio door into the plugin's pirate
directory.  There is deliberately no radio-browser search here: three mirror
timeouts can outlive a whole load, and a dead row is worse than three known
stations.

Row protocol
------------
Rows are plain dicts (with attribute access for convenience) carrying exactly
the six fields the full-screen list understands::

    title   str   display label
    fact    str   short Label2 fact, <= 16 chars ("ON AIR", "LIVE", "PIRATE")
    art     str   resolved local art path, or "" (the view falls back)
    code    str   RP print furniture, never a routing key
    kind    str   "station" (playable) or "section" (opens another screen)
    action  dict  {"type": "play"|"stop"|"open", ...}

``Row`` subclasses ``dict``, so ``row["title"]``, ``row.title``,
``dict(row)`` and ``json.dumps(row)`` all work.  This is intentional: the
parallel library screen may hand back either mappings or mapping-like objects,
and the controller can normalise without a second dataclass.

Live semantics
--------------
- A station row's ``fact`` becomes ``ON AIR`` while that station is playing.
- Live radio has no truthful duration, so the state/footer exposes
  ``has_duration=False`` and ``has_progress=False``.  The footer module enforces
  this independently as well.
- ``play()`` is single-shot: pressing OK on the already-playing station does
  not call the player again.  ``stop()`` is explicit; switching stations makes
  one new playback call, never stop-then-play.
- The plugin owns station URLs (``radio.curated`` / ``radio.stream_url``).
  Built-in canonical URLs are only a fallback when the plugin is unavailable,
  so the screen still renders in tests and in a broken install.
"""

import os
import urllib.parse
from dataclasses import dataclass, replace

from .. import nowplaying

ROW_FIELDS = ("title", "fact", "art", "code", "kind", "action")
STATION_ORDER = ("kool", "rinse", "centreforce")
MAX_FACT_CHARS = 16
MAX_TITLE_CHARS = 48
LIVE_FACT = "LIVE"
ON_AIR_FACT = "ON AIR"
PAUSED_FACT = "PAUSED"
PIRATE_FACT = "PIRATE"


class Row(dict):
    """A six-field row that is both a mapping and an attribute bag."""

    __slots__ = ()

    def __init__(self, title="", fact="", art="", code="", kind="station",
                 action=None):
        super().__init__(
            title=str(title or ""),
            fact=str(fact or ""),
            art=str(art or ""),
            code=str(code or ""),
            kind=str(kind or ""),
            action=dict(action) if isinstance(action, dict) else action,
        )

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if name not in ROW_FIELDS:
            raise AttributeError(name)
        self[name] = value

    def copy(self):
        return Row(**{field: self.get(field) for field in ROW_FIELDS})


@dataclass(frozen=True)
class Station:
    token: str
    name: str
    tagline: str
    url: str
    art: str = ""
    code: str = "RP-31"
    country: str = "GB"
    codec: str = ""
    bitrate: int = 0

    @property
    def live(self):
        return True


@dataclass(frozen=True)
class LiveTrack:
    """Playable shape understood by :class:`raveui.playback.PlaybackService`."""

    title: str
    pack: str
    url: str
    art: str = ""
    live: bool = True
    station: str = ""

    def __post_init__(self):
        # Keep the contract stable even if a caller passes a non-string station.
        if not isinstance(self.station, str):
            object.__setattr__(self, "station", str(self.station or ""))


@dataclass(frozen=True)
class StationState:
    token: str
    name: str
    mode: str = "idle"          # idle | playing | paused
    on_air: bool = False
    paused: bool = False
    title: str = ""
    artist: str = ""
    meta: str = ""
    is_live: bool = True
    # Live radio: these are always false/None.  Present so the footer and the
    # row builder share one shape with a normal track state.
    has_duration: bool = False
    has_progress: bool = False
    duration: object = None
    elapsed: object = None
    progress: object = None

    @property
    def playing(self):
        return self.mode == "playing"

    @property
    def idle(self):
        return self.mode == "idle"

    def as_dict(self):
        return {
            "token": self.token,
            "name": self.name,
            "mode": self.mode,
            "on_air": self.on_air,
            "paused": self.paused,
            "title": self.title,
            "artist": self.artist,
            "meta": self.meta,
            "is_live": self.is_live,
            "has_duration": self.has_duration,
            "has_progress": self.has_progress,
            "duration": self.duration,
            "elapsed": self.elapsed,
            "progress": self.progress,
        }


# Canonical fallbacks copied from plugin resources/lib/radio.py.  They are only
# used when the plugin module cannot be read; a working install always wins.
_FALLBACK_STATIONS = (
    Station("kool", "Kool FM", "London pirate radio, since 1991",
            "https://admin.stream.rinse.fm/proxy/kool/stream",
            "kool.png", "RP-32", codec="AAC+", bitrate=128),
    Station("rinse", "Rinse FM", "London underground, since 1994",
            "https://admin.stream.rinse.fm/proxy/rinse_uk/stream",
            "rinse.png", "RP-33", codec="AAC+", bitrate=128),
    Station("centreforce", "Centreforce 883", "Essex pirate radio, since 1988",
            "https://listen.centreforceradio.com/96",
            "centreforce.png", "RP-34", codec="MP3", bitrate=96),
)

PIRATE_ROW = Row(
    title="Pirate Radio",
    fact=PIRATE_FACT,
    art="pirate-radio.png",
    code="RP-35",
    kind="section",
    action={"type": "open", "source": "pirate", "target": "pirate"},
)

# Scene genre doors, identical to the classic radio_menu RADIO_SECTIONS.
GENRE_ROWS = (
    Row("Hardcore", "GENRE", "radio-hardcore.png", "RP-36", "section",
        {"type": "open", "source": "live_tag", "tag": "hardcore",
         "target": "hardcore", "title": "Hardcore"}),
    Row("Jungle", "GENRE", "radio-jungle.png", "RP-37", "section",
        {"type": "open", "source": "live_tag", "tag": "jungle",
         "target": "jungle", "title": "Jungle"}),
    Row("Drum & Bass", "GENRE", "radio-dnb.png", "RP-38", "section",
        {"type": "open", "source": "live_tag", "tag": "drum and bass",
         "target": "drum-and-bass", "title": "Drum & Bass"}),
    Row("House", "GENRE", "radio-house.png", "RP-39", "section",
        {"type": "open", "source": "live_tag", "tag": "house",
         "target": "house", "title": "House"}),
    Row("UK Garage", "GENRE", "radio-uk-garage.png", "RP-40", "section",
        {"type": "open", "source": "live_tag", "tag": "uk garage",
         "target": "uk-garage", "title": "UK Garage"}),
    Row("Dubstep & Grime", "GENRE", "radio-dubstep-grime.png", "RP-41", "section",
        {"type": "open", "source": "live_tag", "tag": "dubstep",
         "target": "dubstep-grime", "title": "Dubstep & Grime"}),
)


def _text(value, fallback=""):
    text = " ".join(str(value or "").split())
    return text or fallback


def _fact(value, fallback=""):
    text = _text(value, fallback)
    if len(text) <= MAX_FACT_CHARS:
        return text
    return text[:MAX_FACT_CHARS - 1].rstrip() + "…"


def _http_url(value):
    text = _text(value)
    if not text or any(char.isspace() for char in text):
        return ""
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    return text


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _safe_stream(modules, url):
    """Pass a scraper URL through the plugin's public-host guard when present."""
    text = _http_url(url)
    if not text:
        return ""
    if modules is not None:
        try:
            safe = modules.http.safe_stream_url(text)
            if safe:
                return _http_url(safe)
        except Exception:  # noqa: BLE001 - an optional guard must not empty a row
            pass
    return text


def load_stations(modules=None):
    """Return the three curated stations, preferring the plugin's live URLs.

    ``modules`` is the namespace returned by :func:`raveui.pluginbridge.load_plugin`.
    Missing/malformed plugin entries fall back to the canonical row rather than
    dropping the station, because all three have stable direct streams.
    """
    stations = [replace(station) for station in _FALLBACK_STATIONS]
    by_token = {station.token: station for station in stations}
    radio = getattr(modules, "radio", None) if modules is not None else None
    if radio is None:
        return stations
    for token in STATION_ORDER:
        station = by_token[token]
        try:
            found = list(radio.curated(token) or [])
        except Exception:  # noqa: BLE001 - one bad station entry is not fatal
            found = []
        if not found:
            continue
        candidate = found[0]
        if not isinstance(candidate, dict):
            continue
        try:
            url = radio.stream_url(candidate)
        except Exception:  # noqa: BLE001 - keep the fallback URL
            url = ""
        url = _safe_stream(modules, url) or station.url
        by_token[token] = replace(
            station,
            url=url,
            name=_text(candidate.get("name"), station.name),
            country=_text(candidate.get("countrycode"), station.country),
            codec=_text(candidate.get("codec"), station.codec),
            bitrate=_as_int(candidate.get("bitrate")) or station.bitrate,
        )
    return [by_token[token] for token in STATION_ORDER]


class LiveRadio(object):
    """State and actions for the Live Radio screen.

    ``playback`` is anything with a ``play(track)`` method, normally
    :class:`raveui.playback.PlaybackService`.  ``stopper`` is the matching
    no-argument stop (``Player().stop`` in the window adapter); it is injected
    because the pure layer must not import ``xbmc``.
    """

    def __init__(self, modules=None, playback=None, stopper=None,
                 stations=None, art_root=None, now_playing=None, logger=None):
        self.modules = modules
        self.playback = playback
        self.stopper = stopper
        self._stations = list(stations) if stations is not None else None
        self.art_root = art_root
        self._probe = now_playing
        self._logger = logger
        self._playing = ""
        self._paused = False
        self._now = {}
        self.status = "STANDBY"

    # --------------------------------------------------------------- stations
    @property
    def stations(self):
        if self._stations is None:
            self._stations = load_stations(self.modules)
            if self.art_root is None and self.modules is not None:
                self.art_root = getattr(self.modules, "root", None)
        return list(self._stations)

    def station(self, token):
        wanted = _text(token).lower()
        for station in self.stations:
            if station.token.lower() == wanted or station.name.lower() == wanted:
                return station
        return None

    @property
    def on_air(self):
        """Token of the station currently on air, or ``""``."""
        return self._playing

    @property
    def paused(self):
        return bool(self._playing and self._paused)

    def _art(self, name):
        if not name:
            return ""
        path = str(name)
        if os.path.isabs(path):
            return path if os.path.isfile(path) else ""
        if self.art_root:
            directory = os.path.join(str(self.art_root), "resources", "art")
            for candidate in (os.path.join(directory, path),
                              os.path.join(str(self.art_root), path)):
                if os.path.isfile(candidate):
                    return candidate
        # The view resolves a bare filename against its own art directory, so
        # keep the name instead of dropping the icon entirely.
        return path

    def state(self, token=None):
        station = self.station(token) if token else (
            self.station(self._playing) if self._playing else None)
        if station is None:
            station = self.stations[0] if self.stations else None
        if station is None:
            return StationState(token="", name="Live Radio", mode="idle")
        now = self.now_playing(station.token) if self._playing == station.token \
            else {"title": station.name}
        mode = "idle"
        if self._playing == station.token:
            mode = "paused" if self._paused else "playing"
        return StationState(
            token=station.token,
            name=station.name,
            mode=mode,
            on_air=bool(mode == "playing"),
            paused=bool(mode == "paused"),
            title=_text(now.get("title"), station.name),
            artist=_text(now.get("artist")),
            meta=_text(now.get("meta")),
        )

    # ------------------------------------------------------------------ rows
    def rows(self):
        rows = []
        for station in self.stations:
            state = self.state(station.token)
            fact = LIVE_FACT
            if state.on_air:
                fact = ON_AIR_FACT
            elif state.paused:
                fact = PAUSED_FACT
            rows.append(Row(
                title=station.name,
                fact=_fact(fact),
                art=self._art(station.art),
                code=station.code,
                kind="station",
                action=self.action(station.token),
            ))
        pirate = PIRATE_ROW.copy()
        pirate["art"] = self._art(PIRATE_ROW["art"])
        rows.append(pirate)
        for genre in GENRE_ROWS:
            row = genre.copy()
            row["art"] = self._art(genre["art"])
            rows.append(row)
        return rows

    def action(self, token):
        """Return the row action for ``token`` (play, or stop while on air)."""
        station = self.station(token)
        token = station.token if station is not None else _text(token).lower()
        if token and token == self._playing:
            if self._paused:
                return {"type": "play", "station": token, "live": True,
                        "url": station.url if station else "",
                        "title": station.name if station else ""}
            return {"type": "stop", "station": token}
        return {
            "type": "play",
            "station": token,
            "live": True,
            "url": station.url if station else "",
            "title": station.name if station else "",
        }

    # --------------------------------------------------------------- actions
    def play(self, token):
        """Start one station.  Replaying the current station is a no-op."""
        station = self.station(token)
        if station is None:
            self.status = "Unknown station."
            return False
        if self._playing == station.token and not self._paused:
            self.status = "Already on air — press OK to stop."
            return False
        if self.playback is None:
            self.status = "Playback is not available."
            self._log("live: no playback service")
            return False
        track = LiveTrack(
            title=station.name,
            pack="Live radio",
            url=station.url,
            art=self._art(station.art),
            live=True,
            station=station.token,
        )
        try:
            self.playback.play(track)
        except Exception as exc:  # noqa: BLE001 - a dead stream must not crash the window
            self._playing = ""
            self._paused = False
            self.status = "Could not start %s." % station.name
            self._log("live: play failed for %s: %s" % (station.token, exc))
            return False
        # One play call per user action.  Switching stations deliberately does
        # not call stop() first; PlaybackService clears the playlist and plays.
        self._playing = station.token
        self._paused = False
        self._now = {}
        self.status = "ON AIR · %s" % station.name
        return True

    def stop(self):
        """Stop the current station.  Returns False when nothing is on air."""
        if not self._playing:
            return False
        stopper = self.stopper
        if stopper is None:
            stopper = getattr(self.playback, "stop", None)
        if stopper is None:
            self.status = "Stop is not wired on this build."
            self._log("live: stop requested without a stopper")
            return False
        try:
            stopper()
        except Exception as exc:  # noqa: BLE001 - report, keep state honest
            self.status = "Could not stop the radio."
            self._log("live: stop failed: %s" % exc)
            return False
        self._playing = ""
        self._paused = False
        self._now = {}
        self.status = "STANDBY"
        return True

    def toggle(self, token):
        station = self.station(token)
        if station is None:
            self.status = "Unknown station."
            return False
        if self._playing == station.token and not self._paused:
            return self.stop()
        return self.play(station.token)

    def set_paused(self, paused):
        """Reflect a player pause/resume without issuing another play call."""
        if not self._playing:
            return False
        self._paused = bool(paused)
        station = self.station(self._playing)
        name = station.name if station is not None else "radio"
        self.status = ("PAUSED · %s" if self._paused else "ON AIR · %s") % name
        return True

    def clear(self, status="STANDBY"):
        """Stand down after Kodi stopped the stream or another item started.

        This never touches the player: the controller calls it when it has
        proved (from Kodi's own state) that this station is no longer playing.
        """
        self._playing = ""
        self._paused = False
        self._now = {}
        self.status = status or "STANDBY"
        return True

    def set_stopped(self, status="STANDBY"):
        """Alias used by the shell for an externally stopped stream."""
        return self.clear(status)

    def perform(self, action):
        """Execute a row action.  ``open`` is left to the controller."""
        if not isinstance(action, dict):
            return False
        kind = _text(action.get("type")).lower()
        if kind == "play":
            return self.play(action.get("station"))
        if kind == "stop":
            return self.stop()
        return False

    # ------------------------------------------------------------ now playing
    def now_playing(self, token=None):
        """Return live metadata; never invents a duration or progress."""
        token = _text(token) or self._playing
        station = self.station(token)
        name = station.name if station is not None else "Live Radio"
        title, artist, meta, stream_title = name, "", "", ""
        if token and token == self._playing and self._probe is not None:
            try:
                raw = self._probe(token)
            except Exception as exc:  # noqa: BLE001 - ICY probe is best effort
                raw = None
                self._log("live: now-playing probe failed: %s" % exc)
            if isinstance(raw, dict):
                title = _text(raw.get("title"), name)
                artist = _text(raw.get("artist"))
                meta = _text(raw.get("meta") or raw.get("station") or raw.get("album"))
                stream_title = _text(raw.get("stream_title"))
            elif raw:
                stream_title = _text(raw)
                artist, title = nowplaying.split_artist_title(stream_title)
                title = title or name
            if token == self._playing:
                self._now = {"title": title, "artist": artist,
                             "meta": meta or name,
                             "stream_title": stream_title}
        elif token == self._playing:
            cached = self._now or {}
            title = _text(cached.get("title"), name)
            artist = _text(cached.get("artist"))
            meta = _text(cached.get("meta"), name)
            stream_title = _text(cached.get("stream_title"))
        on_air = bool(token == self._playing and not self._paused)
        return {
            "token": token,
            "station": name,
            "live": True,
            "on_air": on_air,
            "paused": bool(token == self._playing and self._paused),
            "title": title,
            "artist": artist,
            "meta": meta or name,
            "stream_title": stream_title,
            "has_duration": False,
            "has_progress": False,
            "duration": None,
            "elapsed": None,
            "progress": None,
        }

    def footer(self):
        """Build the footer model for the Live Radio screen."""
        if not self._playing:
            return nowplaying.standby(room="Live Radio", fact=LIVE_FACT)
        station = self.station(self._playing)
        meta = self.now_playing()
        return nowplaying.for_station(
            station.name if station is not None else "Live Radio",
            is_playing=True,
            paused=self._paused,
            stream_title=meta.get("stream_title", ""),
        )

    # ------------------------------------------------------------------ misc
    def _log(self, message):
        if self._logger is None:
            return
        try:
            self._logger(message)
        except Exception:  # noqa: BLE001 - logging must never break the screen
            pass


def playable_rows(rows):
    """Return rows whose action starts playback (a small integration helper)."""
    playable = []
    for row in rows or []:
        action = row.get("action") if isinstance(row, dict) else None
        if isinstance(action, dict) and action.get("type") in ("play", "stop"):
            playable.append(row)
    return playable
