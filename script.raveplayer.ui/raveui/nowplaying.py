# -*- coding: utf-8 -*-
"""Footer / now-playing model for the full-screen Rave Screen.

The footer is a broadcast strip, not a generic Kodi player bar.  This module
turns whatever the player knows into one small, immutable :class:`Footer`
value; the window adapter only paints it.  Keeping the decisions here means the
live-radio rule ("never show a total or a progress bar") is testable without a
Kodi device.

States
------
``idle``
    Nothing playing.  Kicker ``STANDBY``; the focused room can be shown as the
    second line.  No duration, no progress, no ON AIR.
``playing``
    A tape/track.  ``NOW PLAYING``, title, artist · album, elapsed/total and a
    clamped 0..1 progress fraction.
``paused``
    The same metadata, but ON AIR is cleared (the design rule: ON AIR means
    *playing*, not paused).  Duration/progress stay available.
``live``
    A live radio station.  ON AIR stays set while playing, but duration,
    elapsed and progress are always hidden: a live stream has no truthful
    total, and a growing fake total is worse than no total.

Kodi's ``Player.*`` labels are useful but ambiguous (a live stream may report a
non-zero, ever-growing ``Player.Duration``).  Callers therefore pass an
explicit ``live=True`` for station rows; :func:`from_player` also accepts an
``is_live``/``live`` hint, but never guesses "live" from a missing duration.

The module is pure Python: no ``xbmc``/``xbmcgui`` import and no clock.  Text
formatting and progress maths are deterministic, so tests and the skin can rely
on the same output.
"""

from dataclasses import dataclass, replace

IDLE = "idle"
PLAYING = "playing"
PAUSED = "paused"
LIVE = "live"

KICKER_IDLE = "STANDBY"
KICKER_PLAYING = "NOW PLAYING"
KICKER_PAUSED = "PAUSED"
KICKER_LIVE = "ON AIR"

IDLE_TITLE = "NOTHING PLAYING"
IDLE_META = "PICK A ROOM · PRESS OK"
IDLE_HINT = "OK OPEN · B BACK"

MAX_TITLE = 48
MAX_META = 64


# --------------------------------------------------------------------- text
def clip(text, limit):
    """Collapse whitespace and clip one line to ``limit`` characters."""
    words = " ".join(str(text or "").split())
    if limit <= 0 or len(words) <= limit:
        return words
    return words[:max(1, limit - 1)].rstrip() + "…"


def _as_number(value, default=0.0):
    """Best-effort float from Kodi's numbers, numeric strings or ""."""
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _first(value):
    """Archive/Kodi occasionally hand back a list where a string is expected."""
    if isinstance(value, (list, tuple)):
        seen = []
        for part in value:
            text = " ".join(str(part or "").split())
            if text and text not in seen:
                seen.append(text)
        return ", ".join(seen)
    return " ".join(str(value or "").split())


def split_artist_title(stream_title):
    """Split an ICY-style stream title into ``(artist, title)``.

    ``"Vinylgroover - Dreamscape XII"`` -> ``("Vinylgroover", "Dreamscape XII")``.
    A title without a separator is returned as the title with an empty artist.
    The separator must be surrounded by spaces so hyphenated names survive.
    """
    text = " ".join(str(stream_title or "").split())
    if not text:
        return "", ""
    for separator in (" - ", " – ", " — "):
        if separator in text:
            artist, title = text.split(separator, 1)
            artist = artist.strip()
            title = title.strip()
            if artist and title:
                return artist, title
    return "", text


def format_clock(seconds):
    """Format seconds as ``M:SS`` or ``H:MM:SS``; ``""`` for unknown/<=0."""
    value = _as_number(seconds, 0.0)
    if value <= 0:
        return ""
    total = int(round(value))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


def format_milliseconds(value):
    """Format a millisecond count (Kodi InfoLabel style) as a clock."""
    return format_clock(_as_number(value, 0.0) / 1000.0)


def progress_fraction(elapsed, duration):
    """Return a clamped 0..1 progress fraction, or ``None`` without a total."""
    total = _as_number(duration, 0.0)
    if total <= 0:
        return None
    done = max(0.0, _as_number(elapsed, 0.0))
    return max(0.0, min(1.0, done / total))


def _duration_seconds(value):
    """Accept seconds, milliseconds (Kodi JSON ``time`` is ms) or ``M:SS``."""
    if isinstance(value, str):
        text = value.strip()
        if ":" in text:
            parts = text.split(":")
            try:
                parts = [int(part) for part in parts]
            except (TypeError, ValueError):
                return 0.0
            if len(parts) == 3:
                return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
            if len(parts) == 2:
                return float(parts[0] * 60 + parts[1])
            return 0.0
        return max(0.0, _as_number(text, 0.0))
    return max(0.0, _as_number(value, 0.0))


# -------------------------------------------------------------------- model
@dataclass(frozen=True)
class Footer:
    """One immutable footer state, ready for ``KodiView`` to paint."""

    mode: str = IDLE
    on_air: bool = False
    kicker: str = KICKER_IDLE
    title: str = IDLE_TITLE
    meta: str = IDLE_META
    elapsed: str = ""
    duration: str = ""
    progress: float = None
    show_duration: bool = False
    show_progress: bool = False
    room: str = ""
    fact: str = ""
    hint: str = IDLE_HINT
    # True when the *media* is a live stream, independent of the current mode:
    # a paused live stream is PAUSED but must resume as LIVE, not as a track.
    media_live: bool = False

    # ------------------------------------------------------------- predicates
    @property
    def idle(self):
        return self.mode == IDLE

    @property
    def playing(self):
        return self.mode in (PLAYING, LIVE)

    @property
    def paused(self):
        return self.mode == PAUSED

    @property
    def live(self):
        return self.mode == LIVE

    @property
    def has_media(self):
        return self.mode != IDLE

    # --------------------------------------------------------------- exports
    def as_dict(self):
        return {
            "mode": self.mode,
            "on_air": self.on_air,
            "kicker": self.kicker,
            "title": self.title,
            "meta": self.meta,
            "elapsed": self.elapsed,
            "duration": self.duration,
            "progress": self.progress,
            "show_duration": self.show_duration,
            "show_progress": self.show_progress,
            "room": self.room,
            "fact": self.fact,
            "hint": self.hint,
        }

    def properties(self, prefix="rp_now_"):
        """Window properties for skin bindings; booleans become ``1``/``0``."""
        values = {
            "mode": self.mode,
            "on_air": "1" if self.on_air else "0",
            "kicker": self.kicker,
            "title": self.title,
            "meta": self.meta,
            "elapsed": self.elapsed,
            "duration": self.duration,
            "progress": "" if self.progress is None else "%d" % round(self.progress * 100),
            "show_duration": "1" if self.show_duration else "0",
            "show_progress": "1" if self.show_progress else "0",
            "room": self.room,
            "fact": self.fact,
            "media_live": "1" if self.media_live else "0",
        }
        return {"%s%s" % (prefix, key): value for key, value in values.items()}

    def status_line(self):
        """One-line fallback for the existing ``CONTROL_STATUS`` label."""
        if self.idle:
            return self.meta
        if self.live:
            return "ON AIR · %s" % self.title if self.on_air else self.kicker
        parts = [self.kicker, self.title]
        if self.meta:
            parts.append(self.meta)
        return " · ".join(parts)


# ---------------------------------------------------------------- factories
def standby(room="", fact="", count=None):
    """Idle/standby footer; optionally shows the focused room instead of hint."""
    room = clip(room, MAX_TITLE)
    fact = clip(fact, MAX_TITLE)
    meta = IDLE_META
    if room:
        meta = "%s · %s" % (room, fact) if fact else room
    elif count is not None:
        try:
            total = max(0, int(count))
        except (TypeError, ValueError):
            total = 0
        meta = "%d ROOM%s · %s" % (total, "" if total == 1 else "S", IDLE_HINT)
    return Footer(mode=IDLE, on_air=False, kicker=KICKER_IDLE,
                  title=IDLE_TITLE, meta=clip(meta, MAX_META), room=room,
                  fact=fact)


def playing(title, artist="", album="", duration=0, elapsed=0, live=False,
            paused=False):
    """Build a playing/paused/live footer.

    ``duration`` and ``elapsed`` are seconds.  ``live=True`` always hides the
    total, elapsed and progress, even when Kodi reports a duration.
    """
    name = clip(_first(title), MAX_TITLE) or "Untitled"
    artist = clip(_first(artist), MAX_TITLE)
    album = clip(_first(album), MAX_TITLE)
    meta_parts = [part for part in (artist, album) if part]
    meta = clip(" · ".join(meta_parts), MAX_META)

    total = _duration_seconds(duration)
    done = max(0.0, _duration_seconds(elapsed))
    if total > 0:
        done = min(done, total)

    is_live = bool(live)
    if paused:
        mode = PAUSED
        kicker = KICKER_PAUSED
        on_air = False
    elif is_live:
        mode = LIVE
        kicker = KICKER_LIVE
        on_air = True
    else:
        mode = PLAYING
        kicker = KICKER_PLAYING
        on_air = True

    if is_live:
        return Footer(mode=mode, on_air=on_air, kicker=kicker, title=name,
                      meta=meta, elapsed="", duration="", progress=None,
                      show_duration=False, show_progress=False,
                      media_live=True, fact="LIVE")

    show_total = total > 0
    return Footer(
        mode=mode,
        on_air=on_air,
        kicker=kicker,
        title=name,
        meta=meta,
        elapsed=format_clock(done),
        duration=format_clock(total),
        progress=progress_fraction(done, total) if show_total else None,
        show_duration=show_total,
        show_progress=show_total,
    )


def live(station, title="", artist="", meta=""):
    """Convenience factory for a live-radio footer."""
    details = " · ".join(part for part in (artist, meta) if part)
    return playing(title or station, artist=details, live=True)


def from_player(values, live=False):
    """Build a footer from a Kodi-shaped player snapshot.

    Accepts the subset the screen needs::

        {"title": ..., "artist": ..., "album": ...,
         "duration": 2637, "elapsed": 1204,
         "time": {"hours": 0, "minutes": 20, "seconds": 4},
         "totaltime": {"hours": 0, "minutes": 43, "seconds": 57},
         "percentage": 45.7, "speed": 1, "paused": False,
         "playing": True, "is_live": False, "live": False}

    ``duration``/``elapsed`` are seconds; ``time``/``totaltime`` are Kodi's
    millisecond dictionaries.  An explicit ``live`` argument (or the
    ``is_live``/``live`` dict hint) wins.  A stream with no duration is *not*
    guessed live: it simply hides the total and progress, which is the honest
    result for an unknown tape too.
    """
    values = dict(values or {})
    title = values.get("title") or values.get("label") or ""
    if not title:
        artist, parsed = split_artist_title(values.get("stream_title"))
        title = parsed
        if not values.get("artist"):
            values["artist"] = artist

    is_live = bool(live or values.get("is_live") or values.get("live"))

    total = _duration_seconds(values.get("duration"))
    if total <= 0 and isinstance(values.get("totaltime"), dict):
        total_ms = (values["totaltime"].get("hours", 0) * 3600 * 1000
                    + values["totaltime"].get("minutes", 0) * 60 * 1000
                    + values["totaltime"].get("seconds", 0) * 1000
                    + values["totaltime"].get("milliseconds", 0))
        total = _duration_seconds(total_ms / 1000.0)
    done = _duration_seconds(values.get("elapsed"))
    if done <= 0 and isinstance(values.get("time"), dict):
        done_ms = (values["time"].get("hours", 0) * 3600 * 1000
                   + values["time"].get("minutes", 0) * 60 * 1000
                   + values["time"].get("seconds", 0) * 1000
                   + values["time"].get("milliseconds", 0))
        done = _duration_seconds(done_ms / 1000.0)

    paused = values.get("paused")
    if paused is None:
        speed = values.get("speed")
        if speed is not None:
            paused = _as_number(speed, 1.0) == 0.0
    paused = bool(paused)
    if values.get("playing") is False and not paused:
        # Player.Playing is false and speed is not zero: treat as idle.
        return standby()

    footer = playing(title, artist=values.get("artist"),
                     album=values.get("album"), duration=total, elapsed=done,
                     live=is_live, paused=paused)
    percentage = values.get("percentage")
    if footer.show_progress and percentage is not None:
        fraction = max(0.0, min(1.0, _as_number(percentage, 0.0) / 100.0))
        footer = replace(footer, progress=fraction)
    return footer


def pause(footer):
    """Return ``footer`` in the paused state; ON AIR is cleared."""
    if footer is None or footer.idle:
        return footer
    return replace(footer, mode=PAUSED, on_air=False, kicker=KICKER_PAUSED)


def resume(footer):
    """Return a paused footer as playing/live again."""
    if footer is None or footer.mode != PAUSED:
        return footer
    if footer.media_live:
        return replace(footer, mode=LIVE, on_air=True, kicker=KICKER_LIVE)
    return replace(footer, mode=PLAYING, on_air=True, kicker=KICKER_PLAYING)


def is_on_air(footer):
    """ON AIR means playing, never paused and never idle."""
    return bool(footer is not None and footer.on_air)


def for_station(station, is_playing=True, paused=False, stream_title=""):
    """Footer for one live station, with ICY metadata split when present."""
    artist, title = split_artist_title(stream_title)
    if not is_playing:
        return standby(room=station, fact="LIVE RADIO")
    return playing(title or station, artist=artist, live=True, paused=paused)
