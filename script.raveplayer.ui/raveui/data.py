# -*- coding: utf-8 -*-
"""Data rows for the Rave Screen, built from the plugin's read-only helpers.

No network call happens when the window opens: the home screen is a fixed set
of six rows (Latest / Toronto / JungleTapes / RaveTapePacks / Live / Surprise).
Each row loads in a worker thread only after the user presses OK, which keeps
the GUI thread free for the skin and focus animations.
"""

import os
import random as _random
from dataclasses import dataclass

from . import pluginbridge

FRAME_COUNT = 10
FRAME_SIZE = 512
SECTION_ORDER = ("latest", "toronto", "jungletapes", "ravetapepacks", "live", "surprise")


@dataclass(frozen=True)
class Track:
    title: str
    pack: str
    url: str
    art: str = ""
    live: bool = False


@dataclass(frozen=True)
class Entry:
    key: str
    label: str
    subtitle: str = ""
    art: str = ""
    kind: str = "track"       # section | surprise | pack | genre | show | station | track
    source: str = ""
    target: str = ""
    track: object = None      # Track for playable rows
    hero: str = ""            # optional 1280x720 hero art; falls back to art
    fact: str = ""            # Label2: duration / count / source, <= 16 chars
    code: str = ""            # RP-xx print furniture, not a routing key
    plot: str = ""             # hero description line


def _text(value, fallback=""):
    if isinstance(value, (list, tuple)):
        value = " ".join(str(part) for part in value)
    text = " ".join(str(value or "").split())
    return text or fallback


MAX_FACT_CHARS = 16


def _fact(value, fallback=""):
    """Return a plain single-line Label2 fact capped at 16 characters."""
    text = _text(value, fallback)
    if len(text) <= MAX_FACT_CHARS:
        return text
    return text[:MAX_FACT_CHARS - 1].rstrip() + "…"


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


class RaveData(object):
    """Adapter over the plugin modules. Lazily imports them on first data use."""

    def __init__(self, modules=None, addon_factory=None, root=None,
                 random_module=None, script_root=None):
        self._modules = modules
        self._addon_factory = addon_factory
        self._root = root
        self._random = random_module or _random
        self._script_root = script_root or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
        self.load_error = ""

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

    def _art(self, name):
        path = os.path.join(self.root, "resources", "art", name)
        if os.path.isfile(path):
            return path
        fallback = os.path.join(self._script_root, "resources", "art",
                                "rave-screen-hero.jpg")
        return fallback if os.path.isfile(fallback) else ""

    def _safe_url(self, url):
        text = _text(url)
        if not text:
            return ""
        try:
            safe = self.modules.http.safe_stream_url(text)
        except Exception:  # noqa: BLE001 - malformed scraper URL
            return ""
        return _text(safe)

    # ------------------------------------------------------------------ home
    def home_rows(self):
        return [
            Entry("latest", "LATEST",
                  "Newest tape packs from the Internet Archive",
                  self._art("rave.png"), "section", source="latest",
                  hero=self._art("fanart-latest.jpg"),
                  fact="newest", code="RP-01",
                  plot="Newest packs, shows and radio rips — start here."),
            Entry("toronto", "TORONTO RAVE MIXTAPE ARCHIVE",
                  "1990–2014 · jungle, house and X-Static tapes",
                  self._art("toronto.png"), "section", source="toronto",
                  hero=self._art("fanart-toronto.jpg"),
                  fact="1990–2014", code="RP-19",
                  plot="Toronto rave mixtapes, 1990–2014."),
            Entry("jungletapes", "JUNGLETAPES.COM",
                  "Toronto jungle radio digitised from cassette",
                  self._art("jungletapes.png"), "section", source="jungletapes",
                  hero=self._art("fanart-hub-packs.jpg"),
                  fact="cassette", code="RP-27",
                  plot="Toronto jungle radio, digitised from cassette."),
            Entry("ravetapepacks", "RAVETAPEPACKS.COM",
                  "UK tape packs, 1992–2004",
                  self._art("ravetapepacks.png"), "section", source="ravetapepacks",
                  hero=self._art("fanart-tapepacks.jpg"),
                  fact="1992–2004", code="RP-03",
                  plot="UK rave tape packs, 1992–2004."),
            Entry("live", "LIVE RADIO",
                  "Kool FM · Rinse FM · Centreforce and more",
                  self._art("radio.png"), "section", source="live",
                  hero=self._art("fanart-live.jpg"),
                  fact="live", code="RP-31",
                  plot="Stations on air now: Kool, Rinse, Centreforce."),
            Entry("surprise", "SPINNING SURPRISE",
                  "One random pack + track · press OK",
                  self._art("surprise.png"), "surprise", source="surprise",
                  hero=self._art("fanart-surprise.jpg"),
                  fact="random", code="RP-02",
                  plot="One random pack and track; one spin, no re-roll."),
        ]

    # -------------------------------------------------------------- sections
    def section_entries(self, key):
        key = str(key or "")
        if key == "latest":
            return self._latest_entries()
        if key == "toronto":
            return self._toronto_entries()
        if key == "jungletapes":
            return self._jungletapes_entries()
        if key == "ravetapepacks":
            return self._ravetapepacks_entries()
        if key == "live":
            return self._live_entries()
        raise ValueError("unknown Rave Screen section %r" % key)

    def _latest_entries(self):
        rows = self.modules.latest.recent_packs(rows=20)
        entries = []
        for row in rows or []:
            identifier = _text(row.get("identifier"))
            if not identifier:
                continue
            year = _text(row.get("year"))
            entries.append(Entry(
                key=identifier,
                label=_text(row.get("title"), identifier),
                subtitle="Rave Tape Packs",
                art=self._archive_thumb(identifier),
                kind="pack", source="latest", target=identifier,
                hero=self._art("fanart-latest.jpg"),
                fact=_fact(year or "pack", "pack"),
                code="RP-01",
                plot="Tape pack from the Internet Archive" + (
                    " · " + year if year else "")))
        return entries

    def _toronto_entries(self):
        entries = []
        for row in self.modules.toronto.genres() or []:
            genre = _text(row.get("genre"))
            if not genre:
                continue
            entries.append(Entry(
                key=genre,
                label=_text(row.get("label"), genre.replace("-", " ").title()),
                subtitle="Toronto genre",
                art=self._art("toronto.png"),
                kind="genre", source="toronto", target=genre,
                hero=self._art("fanart-toronto.jpg"),
                fact="genre", code="RP-19",
                plot="Toronto rave mixtape genre"))
        return entries

    def _jungletapes_entries(self):
        entries = []
        for row in self.modules.legacy.jungle_shows() or []:
            key = _text(row.get("key"))
            if not key:
                continue
            entries.append(Entry(
                key=key,
                label=_text(row.get("name"), key),
                subtitle="JungleTapes show",
                art=self._art("jungletapes.png"),
                kind="show", source="jungletapes", target=key,
                hero=self._art("fanart-hub-packs.jpg"),
                fact="show", code="RP-27",
                plot="Toronto jungle radio show on JungleTapes.com"))
        return entries

    def _ravetapepacks_entries(self):
        entries = []
        for row in self.modules.legacy.packs() or []:
            key = _text(row.get("key"))
            if not key:
                continue
            tapes = row.get("tracks") or []
            count = "%d tape%s" % (len(tapes), "" if len(tapes) == 1 else "s")
            entries.append(Entry(
                key=key,
                label=_text(row.get("name"), key),
                subtitle=count,
                art=self._art("ravetapepacks.png"),
                kind="pack", source="ravetapepacks", target=key,
                hero=self._art("fanart-tapepacks.jpg"),
                fact=_fact(count, "pack"), code="RP-03",
                plot="UK rave tape pack on RaveTapePacks.com"))
        return entries

    def _live_entries(self):
        stations = []
        # The curated three are the reliable live set. Do not add a
        # radio-browser search here: three 8 s mirror timeouts can outlive the
        # whole load budget, and an empty Live row is worse than three known
        # stations that actually play.
        try:
            for token in ("kool", "rinse", "centreforce"):
                stations.extend(self.modules.radio.curated(token) or [])
        except Exception:  # noqa: BLE001 - one missing station must not empty the row
            pass
        entries, seen = [], set()
        for station in stations:
            if not isinstance(station, dict):
                continue
            url = self._safe_url(self.modules.radio.stream_url(station))
            if not url or url in seen:
                continue
            seen.add(url)
            name = _text(station.get("name"), "Live radio")
            entries.append(Entry(
                key=url,
                label=name,
                subtitle="Live radio",
                art=self._art("radio.png"),
                kind="station", source="live",
                track=Track(name, "Live radio", url,
                            self._art("radio.png"), live=True),
                hero=self._art("fanart-live.jpg"),
                fact="live", code="RP-31",
                plot="Live radio · Kool FM, Rinse FM, Centreforce"))
        return entries

    # -------------------------------------------------------------- children
    def entries_for(self, entry):
        if entry.kind == "genre":
            tracks = self.modules.toronto.tracks(entry.target)
            return self._track_entries(tracks, entry, source="toronto")
        if entry.kind == "show":
            tracks = self.modules.legacy.jungle_tracks(entry.target)
            return self._track_entries(tracks, entry, source="jungletapes")
        if entry.kind == "pack" and entry.source == "ravetapepacks":
            pack = self.modules.legacy.pack(entry.target)
            if not pack:
                return []
            tracks = []
            for track in pack.get("tracks") or []:
                candidate = dict(track)
                try:
                    candidate["url"] = self.modules.legacy.playable(track.get("url", ""))
                except Exception:  # noqa: BLE001 - skip unbuildable row
                    continue
                tracks.append(candidate)
            return self._track_entries(tracks, entry, source="ravetapepacks")
        if entry.kind == "pack" and entry.source == "latest":
            return self._track_entries(
                self.modules.archive.audio_files(entry.target), entry, source="latest")
        return []

    def _track_entries(self, tracks, parent, source):
        entries = []
        art = parent.art or self._art("rave.png")
        fallback_fact = parent.fact or _fact(source, "track")
        for track in tracks or []:
            if not isinstance(track, dict):
                continue
            url = self._safe_url(track.get("url"))
            if not url:
                continue
            title = _text(track.get("title") or track.get("name"), "Untitled")
            entries.append(Entry(
                key="%s:%s" % (parent.key, len(entries)),
                label=title,
                subtitle=parent.label,
                art=art,
                kind="track", source=source, target=url,
                track=Track(title, parent.label, url, art),
                hero=parent.hero or art,
                fact=_duration_fact(track.get("duration")) or fallback_fact,
                code=parent.code,
                plot=parent.plot or parent.label))
        return entries

    def _archive_thumb(self, identifier):
        try:
            thumb = _text(self.modules.archive.thumb(identifier))
        except Exception:  # noqa: BLE001 - art is optional
            thumb = ""
        if thumb.lower().startswith(("http://", "https://")):
            return thumb
        return self._art("rave.png")

    # -------------------------------------------------------------- surprise
    def random_pick(self):
        """Pick exactly one pack and one track. Never retries or loops."""
        pack = self.modules.latest.random_pack()
        if not pack or not _text(pack.get("identifier")):
            return None
        identifier = _text(pack.get("identifier"))
        tracks = self.modules.archive.audio_files(identifier) or []
        playable = []
        for track in tracks:
            if not isinstance(track, dict):
                continue
            url = self._safe_url(track.get("url"))
            if url:
                playable.append((track, url))
        if not playable:
            return None
        track, url = self._random.choice(playable)
        pack_title = _text(pack.get("title"), identifier)
        title = _text(track.get("title") or track.get("name"), "Untitled")
        return Track(title, pack_title, url, self._archive_thumb(identifier))

    # ------------------------------------------------------------------ art
    def spinner_frames(self):
        frames = []
        # Prefer this add-on's bundled frames so opening the window never waits
        # for the data add-on to import. The rave-screen copy is the design
        # snapshot; resources/art/spinner is the pre-3.9.48 fallback.
        roots = [self._script_root]
        try:
            roots.append(self.root)
        except Exception:  # noqa: BLE001 - plugin missing; the script copy is enough
            pass
        for root in roots:
            for directory in (os.path.join(root, "resources", "art", "rave-screen"),
                              os.path.join(root, "resources", "art", "spinner")):
                candidate = [os.path.join(directory, "head-%d-%02d.png" % (FRAME_SIZE, index))
                             for index in range(FRAME_COUNT)]
                if all(os.path.isfile(path) for path in candidate):
                    return candidate
        return frames
