# -*- coding: utf-8 -*-
"""Reliable Surprise pick: bounded retry, cache-first, single playback handoff.

The Shield intermittently showed *"No random pack found"* although the Archive
was reachable.  Each ``latest.random_pack_once()`` call makes two Archive
searches (count + page) and has no internal retry, so one transient empty/failed
response used to be reported as an exhausted catalogue.  This module wraps that
single pick with a deliberately small policy (Classic plugin routes keep
``random_pack()``'s own bounded retry):

1. **Prefer cached archive packs.**  Packs already seen by the Latest/screen
   load are free and cannot fail.  A cached pack skips the network entirely;
   the most recent few successful picks are avoided so Surprise does not repeat
   the same pack on the next press.
2. **At most three backend attempts** (never an unbounded loop), with short
   backoff between them (0.35 s, 0.8 s by default).  Every failure is retried:
   an exception, ``None``, a malformed pack, or — when a resolver is supplied —
   a pack with no playable audio.
3. **A clear failure only after real exhaustion.**  The result carries the
   attempt count and the last error; the UI should show ``result.message`` only
   when ``bool(result)`` is false.
4. **Never double-play.**  Picking and playing are separate; :class:`PlayOnce`
   is the one-shot gate the controller wraps around the handoff.  The gate is
   tripped *before* the player call, so an exception or a second OK press can
   never produce a second playback.

The module is pure Python (no ``xbmc`` import) and takes the backend, clock,
sleep and random source by injection, so all of this is testable offline.
"""

import inspect
import random as _random
import threading
import time
from dataclasses import dataclass, field

MAX_ATTEMPTS = 3
MIN_ATTEMPTS = 2
DEFAULT_BACKOFF = (0.35, 0.8)
CACHE_LIMIT = 48
RECENT_LIMIT = 8
MAX_IDENTIFIER = 120

FAILURE_MESSAGE = "No random pack found — try again."
CANCELLED_MESSAGE = "Random pick cancelled."
UNPLAYABLE_MESSAGE = "No playable track in the random packs — try again."


# --------------------------------------------------------------------- text
def _text(value, fallback=""):
    if isinstance(value, (list, tuple)):
        value = " ".join(str(part or "") for part in value)
    text = " ".join(str(value or "").split())
    return text or fallback


def clean_identifier(value):
    """Return a safe Archive identifier, or ``""``.

    Archive identifiers are third-party input.  They are used in a metadata URL
    path later, so control characters, slashes and dot segments are rejected
    rather than passed through.
    """
    raw = str(value or "")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        return ""
    text = " ".join(raw.split())
    if not text or len(text) > MAX_IDENTIFIER:
        return ""
    if any(char in text for char in "/\\\r\n\t"):
        return ""
    if text in (".", ".."):
        return ""
    return text


def clean_pack(pack):
    """Normalise a backend pack to ``{"identifier", "title"}``, or ``{}``."""
    if not isinstance(pack, dict):
        return {}
    identifier = clean_identifier(pack.get("identifier") or pack.get("id"))
    if not identifier:
        return {}
    title = _text(pack.get("title") or pack.get("label"), identifier)
    return {"identifier": identifier, "title": title}


# -------------------------------------------------------------------- cache
class PackCache(object):
    """Small bounded, thread-safe cache of archive pack dicts.

    ``latest`` rows and every successful pick can be remembered here.  The
    cache is deliberately in-memory: a restart loses it, which is fine — its job
    is to make the next Surprise press work when the Archive hiccups, not to be
    a catalogue.
    """

    def __init__(self, limit=CACHE_LIMIT):
        try:
            self.limit = max(1, int(limit))
        except (TypeError, ValueError):
            self.limit = CACHE_LIMIT
        self._lock = threading.Lock()
        self._packs = {}
        self._order = []

    def __len__(self):
        with self._lock:
            return len(self._order)

    def __contains__(self, identifier):
        with self._lock:
            return clean_identifier(identifier) in self._packs

    @property
    def identifiers(self):
        with self._lock:
            return list(self._order)

    def remember(self, packs):
        """Remember one pack dict or an iterable of pack dicts."""
        if isinstance(packs, dict):
            packs = [packs]
        try:
            iterator = list(packs or [])
        except TypeError:
            return 0
        added = 0
        with self._lock:
            for item in iterator:
                pack = clean_pack(item)
                if not pack:
                    continue
                identifier = pack["identifier"]
                if identifier in self._packs:
                    try:
                        self._order.remove(identifier)
                    except ValueError:
                        pass
                self._packs[identifier] = pack
                self._order.append(identifier)
                added += 1
            while len(self._order) > self.limit:
                stale = self._order.pop(0)
                self._packs.pop(stale, None)
        return added

    def remember_latest(self, items):
        """Remember ``latest.recent_packs``/row dicts that carry an identifier."""
        packs = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            identifier = item.get("identifier") or item.get("id")
            title = item.get("title") or item.get("label") or identifier
            packs.append({"identifier": identifier, "title": title})
        return self.remember(packs)

    def forget(self, identifier):
        identifier = clean_identifier(identifier)
        with self._lock:
            if identifier not in self._packs:
                return False
            self._packs.pop(identifier, None)
            try:
                self._order.remove(identifier)
            except ValueError:
                pass
            return True

    def clear(self):
        with self._lock:
            self._packs.clear()
            del self._order[:]

    def choose(self, random_module=None, avoid=()):
        """Return a random cached pack, preferring ones not in ``avoid``."""
        chooser = random_module or _random
        avoid = set(clean_identifier(item) for item in (avoid or ()))
        with self._lock:
            candidates = [(identifier, dict(self._packs[identifier]))
                          for identifier in self._order]
        if not candidates:
            return {}
        preferred = [item for item in candidates if item[0] not in avoid]
        pool = preferred or candidates
        try:
            return dict(chooser.choice(pool)[1])
        except (AttributeError, IndexError, TypeError):
            return dict(_random.choice(pool)[1])


# -------------------------------------------------------------------- model
class PickedTrack(dict):
    """Resolved audio track that is both a mapping and a playback-friendly bag.

    ``PlaybackService`` reads ``title``/``pack``/``url``/``art``/``live`` as
    attributes; callers that prefer mappings can use the same object directly.
    """

    __slots__ = ()

    def __init__(self, title="Untitled", url="", identifier="", pack="",
                 art="", live=False):
        super().__init__(title=str(title or "Untitled"), url=str(url or ""),
                         identifier=str(identifier or ""), pack=str(pack or ""),
                         art=str(art or ""), live=bool(live))

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


@dataclass(frozen=True)
class PickResult:
    """Outcome of one Surprise pick attempt-series.

    ``ok`` is the only success test.  On failure ``message`` is the clear,
    user-facing line to show *after* the bounded attempts are exhausted; it is
    never shown for an intermediate transient failure.
    """

    pack: dict = field(default_factory=dict)
    track: object = None
    attempts: int = 0
    source: str = ""           # "cache" | "backend" | ""
    reason: str = ""
    cancelled: bool = False
    last_error: str = ""

    @property
    def ok(self):
        return bool(self.pack) and not self.cancelled

    def __bool__(self):
        return self.ok

    def __len__(self):
        return 1 if self.ok else 0

    @property
    def identifier(self):
        return self.pack.get("identifier", "") if self.pack else ""

    @property
    def title(self):
        return self.pack.get("title", "") if self.pack else ""

    @property
    def message(self):
        if self.ok:
            return "Random pack: %s" % self.title
        if self.cancelled:
            return CANCELLED_MESSAGE
        if self.reason:
            return self.reason
        return FAILURE_MESSAGE


def make_resolver(archive_module, safe_url=None, random_module=None):
    """Return ``resolve(identifier) -> track dict`` for the plugin's archive.

    The returned callable selects one playable audio file and returns
    ``{"identifier", "title", "url"}``; it returns ``{}`` when the pack has no
    playable file.  Passing it to :class:`SurprisePicker` makes a
    pack-with-no-audio count as a failed attempt, so the retry can find a pack
    that actually plays instead of handing Kodi an empty folder.
    """
    chooser = random_module or _random

    def resolve(identifier):
        identifier = clean_identifier(identifier)
        if not identifier:
            return {}
        try:
            files = list(archive_module.audio_files(identifier) or [])
        except Exception:  # noqa: BLE001 - caller retries the whole pick
            return {}
        playable = []
        for item in files:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or ""
            if safe_url is not None:
                try:
                    url = safe_url(url)
                except Exception:  # noqa: BLE001 - bad third-party URL
                    url = ""
            if _text(url):
                playable.append((item, _text(url)))
        if not playable:
            return {}
        item, url = chooser.choice(playable)
        art = ""
        thumb = getattr(archive_module, "thumb", None)
        if callable(thumb):
            try:
                art = _text(thumb(identifier))
            except Exception:  # noqa: BLE001 - art is optional
                art = ""
        return PickedTrack(
            title=_text(item.get("title") or item.get("name"), "Untitled"),
            url=url,
            identifier=identifier,
            art=art,
            live=False,
        )

    return resolve


class SurprisePicker(object):
    """Cache-first, three-attempt Surprise picker."""

    def __init__(self, pick=None, cache=None, resolve=None, random_module=None,
                 sleep=None, logger=None, attempts=MAX_ATTEMPTS,
                 backoff=DEFAULT_BACKOFF, should_stop=None):
        self.pick = pick
        self.cache = cache if cache is not None else PackCache()
        self.resolve = resolve
        self.random = random_module or _random
        self._sleep = sleep or time.sleep
        self._logger = logger
        self.should_stop = should_stop
        try:
            requested = int(attempts)
        except (TypeError, ValueError):
            requested = MAX_ATTEMPTS
        self.attempts = max(MIN_ATTEMPTS, min(MAX_ATTEMPTS, requested))
        self.backoff = tuple(backoff or DEFAULT_BACKOFF)
        self.last_result = None
        # One shared gate per picker, so even a caller that forgets to pass a
        # guard cannot hand the same gesture to the player twice.
        self.guard = PlayOnce()

    # ----------------------------------------------------------------- public
    def pick_once(self):
        """One authoritative pick series.  Never raises and never plays."""
        try:
            result = self._run()
        except Exception as exc:  # noqa: BLE001 - the window must never crash
            self._log("surprise: unexpected pick failure: %s" % exc)
            result = PickResult(reason=FAILURE_MESSAGE,
                                last_error=str(exc), attempts=0)
        self.last_result = result
        return result

    # Kept as the obvious name for callers/tests.
    def __call__(self):
        return self.pick_once()

    # ---------------------------------------------------------------- internals
    def _cancelled(self):
        if self.should_stop is None:
            return False
        try:
            return bool(self.should_stop())
        except Exception:  # noqa: BLE001 - a broken predicate is not a cancel
            return False

    def _cancel_result(self, attempts):
        return PickResult(attempts=attempts, cancelled=True,
                          reason=CANCELLED_MESSAGE)

    def _resolve(self, pack):
        if self.resolve is None:
            return None, True
        try:
            track = self.resolve(pack["identifier"])
        except Exception as exc:  # noqa: BLE001 - treat as an unplayable pack
            self._log("surprise: resolve failed for %s: %s"
                      % (pack["identifier"], exc))
            return None, False
        if not track:
            return None, False
        if isinstance(track, dict):
            # Give PlaybackService the pack title for the footer/Album line and
            # normalise a plain mapping (custom resolver/test double) to the
            # attribute-friendly PickedTrack shape.
            track = PickedTrack(
                title=track.get("title") or track.get("name") or "Untitled",
                url=track.get("url") or "",
                identifier=track.get("identifier") or pack["identifier"],
                pack=track.get("pack") or pack["title"],
                art=track.get("art") or "",
                live=bool(track.get("live")),
            )
        return track, True

    def _cached(self, avoid, attempts):
        if self.cache is None:
            return None
        try:
            pack = self.cache.choose(self.random, avoid=avoid)
        except Exception as exc:  # noqa: BLE001 - cache must not block a pick
            self._log("surprise: cache read failed: %s" % exc)
            return None
        pack = clean_pack(pack)
        if not pack:
            return None
        track, playable = self._resolve(pack)
        if not playable:
            # A cached pack whose tracks are gone is worse than no cache; drop
            # it and let the backend try.  It still counts as an attempt.
            try:
                self.cache.forget(pack["identifier"])
            except Exception:  # noqa: BLE001
                pass
            self._log("surprise: cached pack %s had no playable track"
                      % pack["identifier"])
            return None
        return PickResult(pack=pack, track=track, attempts=attempts,
                          source="cache")

    def _run(self):
        if self._cancelled():
            return self._cancel_result(0)
        cached = self._cached(self.recent, 1)
        if cached is not None:
            self._remember(cached.pack)
            return cached
        if self.pick is None:
            return PickResult(attempts=0,
                              reason="Random picker is not available.")
        attempts = 0
        last_error = ""
        unplayable = 0
        for attempt in range(1, self.attempts + 1):
            if self._cancelled():
                # Back arrived between attempts: report the attempts that
                # actually ran, not the one that was about to run.
                return self._cancel_result(attempt - 1)
            if attempt > 1:
                self._wait(attempt - 1)
            attempts = attempt
            try:
                raw = self.pick()
            except Exception as exc:  # noqa: BLE001 - retry transient failures
                last_error = "%s: %s" % (exc.__class__.__name__, exc)
                self._log("surprise: attempt %d failed: %s"
                          % (attempt, last_error))
                continue
            pack = clean_pack(raw)
            if not pack:
                last_error = "empty pack"
                self._log("surprise: attempt %d returned no pack" % attempt)
                continue
            track, playable = self._resolve(pack)
            if not playable:
                unplayable += 1
                last_error = "pack %s has no playable audio" % pack["identifier"]
                self._log("surprise: attempt %d unplayable (%s)"
                          % (attempt, pack["identifier"]))
                continue
            result = PickResult(pack=pack, track=track, attempts=attempt,
                                source="backend")
            self._remember(pack)
            return result
        reason = UNPLAYABLE_MESSAGE if unplayable else FAILURE_MESSAGE
        if last_error:
            self._log("surprise: exhausted %d attempt(s): %s"
                      % (attempts, last_error))
        return PickResult(attempts=attempts, reason=reason,
                          last_error=last_error)

    def _wait(self, index):
        try:
            delay = float(self.backoff[min(max(0, index - 1),
                                          len(self.backoff) - 1)])
        except (IndexError, TypeError, ValueError):
            delay = DEFAULT_BACKOFF[0]
        if delay <= 0:
            return
        try:
            self._sleep(delay)
        except Exception as exc:  # noqa: BLE001 - a test sleep must not fail pick
            self._log("surprise: backoff sleep failed: %s" % exc)

    def _remember(self, pack):
        if not pack:
            return
        if self.cache is not None:
            try:
                self.cache.remember(pack)
            except Exception:  # noqa: BLE001
                pass
        # Keep the recent list on the picker too, so an injected fake cache
        # without .recent still avoids immediate repeats.
        recent = getattr(self, "_recent", None)
        if recent is None:
            recent = []
            self._recent = recent
        identifier = pack.get("identifier", "")
        if identifier in recent:
            recent.remove(identifier)
        recent.append(identifier)
        del recent[:-RECENT_LIMIT]

    @property
    def recent(self):
        return list(getattr(self, "_recent", []) or [])

    def _log(self, message):
        if self._logger is None:
            return
        try:
            self._logger(message)
        except Exception:  # noqa: BLE001 - logging is best effort
            pass


def _single_attempt_pick(latest):
    """Return the plugin's one-pick callable, or ``None`` when unavailable.

    The screen's :class:`SurprisePicker` owns retries.  ``random_pack_once`` is
    the explicit plugin API; for a plugin that only exposes ``random_pack`` we
    request ``attempts=1`` if it accepts the keyword.  A legacy no-argument
    callable is used as-is (it may still retry internally, but it is the only
    callable available).
    """
    once = getattr(latest, "random_pack_once", None)
    if callable(once):
        return once
    pick = getattr(latest, "random_pack", None)
    if not callable(pick):
        return None
    try:
        parameters = inspect.signature(pick).parameters
    except (TypeError, ValueError):
        return pick
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values())
    if accepts_kwargs or "attempts" in parameters:
        def pick_once():
            return pick(attempts=1)
        return pick_once
    return pick


def from_plugin(modules, cache=None, archive_module=None, **kwargs):
    """Build a picker wired to the plugin's ``latest``/``archive`` backend.

    ``modules`` is the namespace from :func:`raveui.pluginbridge.load_plugin`.
    The picker calls the plugin's one-shot pick exactly like the existing data
    layer, but through its own bounded retry policy, and resolves a playable
    track with ``archive.audio_files`` so a pack with no audio is retried
    instead of handed to Kodi.

    A missing/broken plugin yields a picker whose ``pick`` is ``None``: the
    first press fails once, clearly, without a traceback or an endless loop.
    """
    latest = getattr(modules, "latest", None) if modules is not None else None
    archive = archive_module or (getattr(modules, "archive", None)
                                 if modules is not None else None)
    pick = _single_attempt_pick(latest)
    safe_url = None
    http_module = getattr(modules, "http", None) if modules is not None else None
    if http_module is not None:
        safe_url = getattr(http_module, "safe_stream_url", None)
    resolver = None
    if archive is not None and callable(getattr(archive, "audio_files", None)):
        resolver = make_resolver(archive, safe_url=safe_url,
                                 random_module=kwargs.get("random_module"))
    return SurprisePicker(pick=pick, cache=cache, resolve=resolver, **kwargs)


# --------------------------------------------------------------- single play
class PlayOnce(object):
    """Thread-safe one-shot gate around a playback handoff.

    ``fire()`` trips the gate *before* invoking the callback, so a callback
    exception, a re-entrant GUI event, or a second OK press cannot produce a
    second playback.  Create a fresh gate for a new user gesture only via
    :meth:`reset` from the GUI thread.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._fired = False

    @property
    def fired(self):
        with self._lock:
            return self._fired

    def reset(self):
        with self._lock:
            self._fired = False

    def fire(self, callback, *args, **kwargs):
        """Run ``callback`` once; return True if this call ran it."""
        if not callable(callback):
            return False
        with self._lock:
            if self._fired:
                return False
            self._fired = True
        callback(*args, **kwargs)
        return True


def pick_and_handoff(picker, handoff, track_of=None, guard=None,
                     on_result=None):
    """Pick once, then hand off at most once.

    Returns the :class:`PickResult`; a failure is returned without calling
    ``handoff``.  ``track_of(result)`` extracts the object to play (defaults to
    ``result.track``).  This is the exact sequence the main shell should use,
    and it is intentionally impossible for a retry to trigger playback more
    than once.
    """
    result = picker.pick_once() if hasattr(picker, "pick_once") else picker()
    if on_result is not None:
        try:
            on_result(result)
        except Exception:  # noqa: BLE001 - UI callback is best effort
            pass
    if not result:
        return result
    track = track_of(result) if track_of is not None else result.track
    if track is None:
        return result
    gate = guard if guard is not None else getattr(picker, "guard", None)
    if gate is None:
        gate = PlayOnce()
    gate.fire(handoff, track)
    return result
