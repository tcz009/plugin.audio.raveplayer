# -*- coding: utf-8 -*-
"""Rave Screen controller — the whole app's behaviour, with no Kodi imports.

The window class in :mod:`raveui.window` is a thin adapter over this controller;
tests drive it with a fake view, data source, download queue and playback
service.  Every screen is a state of the same window:

* home -> room -> folder -> track list -> playback
* a list can be paged (25/50/100) with explicit previous/next rows
* search is an in-window keyboard; Search/Favourites/Downloads/About rows and
  actions come from :mod:`raveui.screens.library`
* Live Radio rows, ON AIR state and the footer come from
  :mod:`raveui.screens.live` and :mod:`raveui.nowplaying`
* Spinning Surprise uses one pick policy from :mod:`raveui.surprise_pick`
* a context menu (long-press OK) carries Play all / Shuffle / Download /
  Favourite / rows-per-page / Stop / Refresh
* loading, empty and error states are painted plates, not modal dialogs
* Spinning Surprise is one bounded pick series, one >=1.2 s reveal and one
  playback
* leaving the window never stops audio: Kodi owns the player (one policy)

The controller never opens a modal dialog, never calls ``xbmcgui`` and never
raises into Kodi: every failure becomes a quiet status line or a plate.
"""

import hashlib
import inspect
import threading
import time
from dataclasses import dataclass

from . import nowplaying
from .animation import FPS, MIN_DURATION, SpinnerAnimator, frame_index
from .data import (DEFAULT_PAGE_SIZE, PAGE_SIZES, Entry, SearchTarget, Track,
                   _page_local)
from .screens.library import (
    ACTION_CANCEL, ACTION_OPEN, ACTION_PLAY, ACTION_PLAY_ALL, ACTION_REMOVE,
    ACTION_RETRY, ACTION_SHUFFLE, KIND_ACTION, KIND_ROOM, KIND_TRACK,
    LibraryScreens,
    PluginBackend, ROUTE_ABOUT, ROUTE_DOWNLOADS, ROUTE_FAVOURITES,
    ROUTE_SEARCH, ROUTES as LIBRARY_ROUTES, Screen, TITLES,
)
from .paintcache import (PaintCache, decode_library_screen, decode_page,
                         encode_library_screen, encode_page, library_signature,
                         signature)
from .screens.live import LiveRadio, Station, load_stations
from .surprise_pick import PackCache, PlayOnce, from_plugin
from .tasks import (BackgroundTask, ImmediateTask, TaskCancelled, TaskTimeout,
                    ThreadTaskRunner)


_LIVE_SIGNATURE_FIELDS = (
    "key", "label", "title", "target", "subtitle", "art", "fact", "code",
    "kind", "plot", "meta",
)


def _row_field(row, name):
    """Read one row field from a mapping or an attribute-style row."""
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def _live_row_signature(row):
    """Stable, serialisable fields for one live row.

    Live rows reach this as ``_EntryLike`` objects, which are not mappings and
    whose ``repr`` contains the object address.  Hashing ``str(row)`` therefore
    produced a different signature for identical rows on every refresh.  Read
    the display/action fields explicitly instead; ``action.url`` carries the
    station stream so a re-resolved station still counts as changed.
    """
    fields = [str(_row_field(row, name) or "")
              for name in _LIVE_SIGNATURE_FIELDS]
    action = _row_field(row, "action")
    if isinstance(action, dict):
        stream = str(action.get("url") or "")
        action_type = str(action.get("type") or "")
        station = str(action.get("station") or "")
    else:
        stream = action_type = station = ""
    return tuple(fields) + (action_type, station, stream)


def _live_signature(rows):
    """Stable fingerprint of the live rows the controller painted."""
    payload = [_live_row_signature(row) for row in rows or []]
    return hashlib.blake2b(
        repr(payload).encode("utf-8", "replace"), digest_size=16).hexdigest()


HOME_TITLE = "RAVE SCREEN"
HOME_SUBTITLE = "11 rooms · OK opens · long-press OK for actions"
KEY_LIMIT = 48

# Stale-while-revalidate status lines (perf/3.9.52).  The status slot is the
# screen's quiet one-line footer above the key hints: never a dialog, never a
# plate, never anything that steals focus from Back.
PAINT_UPDATING = "UPDATING · showing saved list"
PAINT_CURRENT = "SAVED LIST · up to date"
PAINT_OFFLINE = "OFFLINE · showing saved list"
PAINT_EMPTY = "SOURCE EMPTY · showing saved list"
# A refresh is a background convenience; a source that takes longer than this
# is abandoned (the cached page stays and the row can be retried normally).
REFRESH_TIMEOUT_SECONDS = 45.0

KEY_GROUPS = (
    ("A B C D E F G H I".split(), "LETTERS"),
    ("J K L M N O P Q R".split(), "LETTERS"),
    ("S T U V W X Y Z".split(), "LETTERS"),
    ("0 1 2 3 4 5 6 7 8 9".split(), "DIGITS"),
)
KEY_ACTIONS = ("SPACE", "DELETE", "CLEAR", "SEARCH NOW", "CANCEL")


def _runner_accepts_poll(runner):
    """True when ``runner.run`` takes a per-call ``on_poll`` override."""
    try:
        parameters = inspect.signature(runner.run).parameters
    except (TypeError, ValueError):
        return False
    for parameter in parameters.values():
        if parameter.name == "on_poll":
            return True
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return True
    return False


@dataclass
class _Frame:
    kind: str
    target: object
    title: str
    subtitle: str
    page: int
    pages: int
    total: int
    rows: list
    index: int
    keyboard: object = None
    screen: object = None


@dataclass
class _Plate:
    kind: str                 # loading | empty | error
    title: str
    detail: str = ""
    hint: str = ""
    retry: object = None


class RaveScreenController(object):
    def __init__(self, view, data, playback, *, animator_factory=None,
                 task_runner=None, sleep=None, clock=None, monitor=None,
                 frames=None, logger=None, download_queue=None,
                 library=None, live=None, surprise_picker=None,
                 surprise_cache=None, surprise_sleep=None,
                 player_snapshot=None, paint_cache=None,
                 background_task_factory=None, boot_at=None):
        self.view = view
        self.data = data
        self.playback = playback
        # Kodi constructs the window (and therefore this controller) on the GUI
        # thread.  Every control mutation must happen there; a background task
        # runner's poll has no business painting even if it shares the runner.
        self._gui_thread = threading.current_thread()
        self._animator_factory = animator_factory or SpinnerAnimator
        self._sleep = sleep
        self._clock = clock
        self._logger = logger or self._default_log
        self._task_runner = task_runner or ThreadTaskRunner(
            sleep=self._sleep_ms, clock=clock, monitor=monitor,
            timeout=45.0, cancelled=lambda: self._closed,
            on_poll=self._on_runner_poll)
        self._frames = list(frames) if frames is not None else list(
            data.spinner_frames() if hasattr(data, "spinner_frames") else [])
        self._title = HOME_TITLE
        self._subtitle = HOME_SUBTITLE
        self._rows = []
        self._page_rows = []
        self._stack = []
        self._closed = False
        self._busy = False
        self._surprising = False
        self._handed_off = False
        self._playing_live = False
        self._view_kind = "list"          # list | keyboard | context
        self._target = None               # None home, room key, Entry, SearchTarget
        self._page = 1
        self._pages = 1
        self._total = 0
        self._page_has_next = False
        self._rows_per_page = DEFAULT_PAGE_SIZE
        self._page_size_explicit = False
        self._plate = None
        self._context_actions = []
        self._context_subject = None
        self._keyboard = None
        self._surprise_cancel = threading.Event()
        self._loading_cancel = threading.Event()
        self._loading_thread = None
        self._download_queue = download_queue
        self._boot_at = boot_at
        # Stale-while-revalidate: the last painted page is read from disk on
        # open (milliseconds) while a background task refreshes it.  A test or
        # a bench can inject its own cache/factory; both default to the real
        # device implementations.
        self._paint_cache = (paint_cache if paint_cache is not None
                             else PaintCache(versions=self._paint_versions()))
        self._background_task_factory = (background_task_factory
                                         or BackgroundTask)
        self._refresh = None
        self._refresh_seq = 0
        # Idle prefetch: after the first paint, warm Latest and the
        # RaveTapePacks index in the background so the first tap is cached.
        # It is strictly best-effort and stops the moment the user acts.
        self._prefetch_cancel = threading.Event()
        self._prefetch_thread = None
        self._user_active = False
        # Surprise runs are identified by a monotonically increasing token.  A
        # worker from an old run can never paint or play, even if it outlives
        # its timeout, because every UI/player callback checks the token.
        self._surprise_run = 0
        self._surprise_guard = None
        self._surprise_pending = None
        self._surprise_reveal = None
        self._surprise_thread = None
        self._state_lock = threading.Lock()
        self._loading_active = False
        self._loading_frame = -1
        self._loading_started = 0.0
        self._last_play_key = None
        self._last_play_at = 0.0
        self._live_started_at = 0.0
        # External-stop detection: Kodi can stop the player from JSON-RPC or
        # another add-on, so the footer tick polls the player and clears the
        # playback status line when an active player disappears (3.9.54 device
        # QA P2-2).  A short grace covers Player.play's asynchronous start.
        self._player_seen_active = False
        self._player_active_at = 0.0
        self._playback_status_active = False
        # One implementation per concern.  The screen modules own the four
        # library rooms, Live Radio and the Surprise policy; the shell only
        # adapts their rows and actions and keeps the navigation stack.
        self._library_ui = library
        self._live_ui = live
        self._surprise_picker = surprise_picker
        self._surprise_cache = surprise_cache or PackCache()
        self._surprise_sleep = surprise_sleep
        self._player_snapshot = player_snapshot
        self._library_screen = None
        self._footer = None
        self._footer_at = None
        self._surprise_played = False
        try:
            self.data.surprise_cache = self._surprise_cache
        except Exception:  # noqa: BLE001 - read-only test double
            pass
        try:
            self.data.rows_per_page = self._rows_per_page
        except Exception:  # noqa: BLE001 - read-only test double
            pass

    # ------------------------------------------------------------- lifecycle
    def start(self):
        rows = list(self.data.home_rows())
        self._title = HOME_TITLE
        self._subtitle = self._home_subtitle()
        self._target = None
        self._view_kind = "list"
        self._page = 1
        self._pages = 1
        self._total = len(rows)
        self._page_has_next = False
        self._page_rows = list(rows)
        self._render(rows)
        self.view.set_status("")
        self._paint_footer()
        self._trace("home rows=%d" % len(rows))
        if self._boot_at:
            self._trace("first paint %.0f ms" % (
                (time.monotonic() - self._boot_at) * 1000.0))
        self._start_prefetch()
        return rows

    @property
    def rows(self):
        return list(self._rows)

    @property
    def title(self):
        return self._title

    @property
    def closed(self):
        return self._closed

    @property
    def handed_off(self):
        return self._handed_off

    @property
    def stack_depth(self):
        return len(self._stack)

    @property
    def view_kind(self):
        return self._view_kind

    @property
    def page(self):
        return self._page

    @property
    def pages(self):
        return self._pages

    @property
    def rows_per_page(self):
        return self._rows_per_page

    @property
    def plate(self):
        return self._plate.kind if self._plate is not None else ""

    @property
    def search_query(self):
        return str((self._keyboard or {}).get("query", ""))

    def shutdown(self):
        """Mark closed without touching the window (called by the adapter)."""
        self._closed = True
        self._prefetch_cancel.set()
        self._cancel_refresh()
        self._surprise_cancel.set()
        self._loading_cancel.set()

    # ------------------------------------------------------------------ focus
    def on_focus(self):
        # D-pad focus movement is a user action: stop the speculative
        # prefetch immediately, not only when a row is clicked or Back is
        # pressed (advisor P2-19).
        self._user_active = True
        self._prefetch_cancel.set()
        if self._closed:
            return None
        if self._view_kind == "keyboard" and self._keyboard is not None:
            try:
                self._keyboard["row"] = int(self.view.selected_index())
            except (TypeError, ValueError, AttributeError):
                pass
            return None
        if self._view_kind == "context":
            return None
        entry = self._selected()
        if entry is not None:
            self.view.set_hero(entry)
            if not self._is_playing():
                self._paint_footer(nowplaying.standby(
                    room=entry.label, fact=getattr(entry, "fact", "")))
        return entry

    def on_horizontal(self, delta):
        self._user_active = True
        self._prefetch_cancel.set()
        """Left/right in the in-window keyboard; returns True when handled."""
        if self._view_kind != "keyboard" or self._keyboard is None:
            return False
        try:
            delta = int(delta)
        except (TypeError, ValueError):
            return True
        row = self._selected_keyboard_row()
        if row is None:
            return True
        action = getattr(row, "action", "")
        if not str(action).startswith("char:"):
            return True
        chars = list(getattr(row, "chars", None) or [])
        if not chars:
            return True
        index = int(self._keyboard.get("row") or 0)
        col = int(self._keyboard.setdefault("cols", {}).get(index, 0))
        col = (col + delta) % len(chars)
        self._keyboard["cols"][index] = col
        self._render_keyboard()
        return True

    # ------------------------------------------------------------------ click
    def on_click(self):
        self._user_active = True
        self._prefetch_cancel.set()
        if self._closed:
            return False
        if self._plate is not None:
            return self._click_plate()
        if self._view_kind == "keyboard":
            return self._keyboard_press()
        if self._view_kind == "context":
            return self._context_execute()
        if self._busy:
            self.view.set_status("Working…")
            return False
        entry = self._selected()
        if entry is None:
            self.view.set_status("Nothing selected.")
            return False
        kind = getattr(entry, "kind", "")
        action = getattr(entry, "action", None)
        if isinstance(action, dict):
            # Live Radio rows are dicts from raveui.screens.live; the module
            # owns play/stop and the shell only routes the action.
            return self._run_live_action(entry, action)
        if kind == "library_room":
            return self._open_library_room(entry)
        if kind == "library_track":
            return self._run_library_play(entry)
        if kind == "library_action":
            return self._run_library_action(entry)
        if kind == "section":
            return self._load_target(getattr(entry, "target", "") or
                                     getattr(entry, "key", None), 1, push=True)
        if kind == "search":
            return self._open_keyboard()
        if kind == "surprise":
            return self._start_surprise()
        if kind in ("page_next", "page_prev"):
            return self._goto_page(int(entry.target or self._page))
        if kind in ("track", "station", "file", "external"):
            track = getattr(entry, "track", None)
            if track is None:
                self.view.set_status("That row has no playable stream.")
                return False
            return self._handoff(track)
        if kind in ("dnb_show", "moxser_mix"):
            return self._resolve_and_play(entry)
        if kind == "info":
            self.view.set_status("Read-only credit — Back returns.")
            return False
        if kind == "download_active":
            self.view.set_status("Download running — long-press OK to cancel.")
            return False
        if kind == "download_missing":
            self.view.set_status("File missing — re-download it or delete the entry.")
            return False
        if kind == "action":
            return False
        if getattr(entry, "track", None) is not None:
            return self._handoff(entry.track)
        return self._load_target(entry, 1, push=True)

    def on_back(self):
        """Pop a level; return True when the caller must close the window."""
        self._user_active = True
        self._prefetch_cancel.set()
        if self._closed:
            return True
        # Back during a background refresh is already done with the painted
        # page: drop the refresh, never wait for it.
        self._cancel_refresh()
        # A running Surprise is a gesture, not a navigation level: Back cancels
        # the pick and keeps the window open.
        if self._surprising:
            self._cancel_surprise()
            return False
        if self._plate is not None:
            if self._plate.kind == "loading" or self._busy:
                # A load always sets _busy *and* a loading plate.  Back must be
                # able to abandon it at once; the runner's cancelled predicate
                # then drops the late result (no zombie invoker).
                self._close_loading_window()
                return True
            self._clear_plate()
            return False
        if self._busy:
            self._close_loading_window()
            return True
        if self._view_kind == "context":
            self._pop()
            return False
        if self._stack:
            self._restore(self._stack.pop())
            return False
        self._closed = True
        self._surprise_cancel.set()
        self._loading_cancel.set()
        self._stop_loading_animation()
        self._cancel_surprise_run()
        self.view.set_status("Closing — audio continues.")
        self.view.close()
        return True

    def _close_loading_window(self):
        """Abandon an in-flight load and close once (P1-1)."""
        self._closed = True
        self._surprise_cancel.set()
        self._loading_cancel.set()
        self._stop_loading_animation()
        self._cancel_surprise_run()
        self._plate = None
        self._busy = False
        try:
            self.view.set_status("Closing — audio continues.")
        except Exception:  # noqa: BLE001 - window may already be gone
            pass
        self.view.close()

    def on_context(self):
        self._user_active = True
        self._prefetch_cancel.set()
        """Long-press OK / remote context menu: in-window actions for the row."""
        if self._closed or self._busy or self._plate is not None:
            return False
        if self._view_kind in ("keyboard", "context"):
            return False
        entry = self._selected()
        if entry is None:
            return False
        actions = self._build_context(entry)
        if not actions:
            self.view.set_status("No actions on that row.")
            return False
        self._context_subject = entry
        self._context_actions = actions
        self._push_current()
        self._view_kind = "context"
        rows = [self._action_row(action) for action in actions]
        self._rows = rows
        self._title = "ACTION"
        self._subtitle = _clip(entry.label, 40)
        self.view.set_title(self._title)
        self.view.set_subtitle(self._subtitle)
        self._set_rows(rows, 0)
        self.view.set_hero(entry)
        self.view.set_status("OK runs the action · BACK returns")
        self._call_view("set_key_hints", "RUN", "BACK")
        self._call_view("set_page_info", "")
        self._set_room_count(len(rows), "ACTIONS")
        return True

    def on_stop(self):
        """Remote Stop: the only explicit way this app stops audio."""
        self._user_active = True
        self._prefetch_cancel.set()
        if self._closed:
            return False
        live = self._live_ui
        was_on_air = self._live_on_air()
        if was_on_air:
            try:
                stopped = bool(live.stop())
            except Exception:  # noqa: BLE001 - player unavailable
                stopped = False
        else:
            try:
                stopped = bool(self.playback.stop())
            except Exception:  # noqa: BLE001 - player unavailable
                stopped = False
        self._last_play_key = None
        self._playback_status_active = False
        self._player_seen_active = False
        self._call_view("set_now_playing", "")
        # Also clear a stale live latch: a normal stop must leave the live
        # footer/row honestly idle (P1-3).
        if live is not None and live.on_air:
            self._stand_down_live("STANDBY")
        self._playing_live = False
        self._live_started_at = 0.0
        self._call_view("set_live", False)
        if self._target == "live":
            self._paint_live_rows(index=self._current_index(), status="STANDBY")
        self._paint_footer(nowplaying.standby())
        self.view.set_status("Stopped." if stopped else "Nothing playing.")
        return stopped

    # ------------------------------------------------------------- surprises
    def _start_surprise(self):
        if self._closed or self._busy or self._surprising:
            return False
        if self._plate is not None:
            self._clear_plate()
        token = self._begin_surprise_run()
        self._busy = True
        self._surprising = True
        self.view.set_spinner_visible(True)
        if self._frames:
            self.view.set_spinner_image(self._frames[0])
        self.view.set_spinner_label("RANDOM PACK · RP-02")
        self.view.set_status("Spinning for one random pack and track…")
        worker = threading.Thread(target=self._surprise_worker, args=(token,),
                                  name="rave-surprise", daemon=True)
        self._surprise_thread = worker
        worker.start()
        return True

    def _begin_surprise_run(self):
        """Start a new gesture: a fresh token, event and one-shot guard.

        The old run's event is never cleared or reused.  A late worker from a
        previous run therefore sees its own cancellation (set event or stale
        token) and can neither paint nor play.
        """
        with self._state_lock:
            self._surprise_run += 1
            token = self._surprise_run
            self._surprise_cancel = threading.Event()
            self._surprise_guard = PlayOnce()
            self._surprise_pending = None
            self._surprise_reveal = None
            self._surprise_played = False
            event = self._surprise_cancel
        picker = self._surprise_picker_for()
        if picker is not None:
            # Reuse the picker's own gate (and reset it for this new gesture),
            # so code holding the picker sees the same one-shot truth.
            guard = getattr(picker, "guard", None)
            if not isinstance(guard, PlayOnce):
                try:
                    picker.guard = self._surprise_guard
                except Exception:  # noqa: BLE001 - read-only fake picker
                    pass
            else:
                guard.reset()
                self._surprise_guard = guard
            if not hasattr(self, "_surprise_stop_base"):
                # A caller-injected predicate (e.g. a test's immediate cancel)
                # keeps its meaning; this run's token is OR-ed on top once.
                self._surprise_stop_base = getattr(picker, "should_stop", None)

            def run_cancelled():
                base = self._surprise_stop_base
                if base is not None:
                    try:
                        if base():
                            return True
                    except Exception:  # noqa: BLE001 - advisory predicate
                        pass
                return self._run_cancelled(token, event)

            try:
                picker.should_stop = run_cancelled
            except Exception:  # noqa: BLE001 - read-only fake picker
                pass
        return token

    def _run_cancelled(self, token, event):
        return (self._closed or event.is_set()
                or token != self._surprise_run)

    def _run_active(self, token):
        return (not self._closed and token is not None
                and token == self._surprise_run
                and not self._surprise_cancel.is_set())

    def _surprise_picker_for(self):
        """The one Surprise policy, wired to the plugin's latest/archive."""
        if self._surprise_picker is not None:
            return self._surprise_picker
        modules = None
        try:
            modules = self.data.modules
        except Exception as exc:  # noqa: BLE001 - missing plugin fails clearly
            self._log("surprise: plugin unavailable: %s" % exc)
        kwargs = {}
        if self._surprise_sleep is not None:
            kwargs["sleep"] = self._surprise_sleep
        self._surprise_picker = from_plugin(
            modules, cache=self._surprise_cache, logger=self._logger,
            should_stop=lambda: self._closed or self._surprise_cancel.is_set(),
            **kwargs)
        return self._surprise_picker

    def _surprise_worker(self, token):
        """Background pick only: never touches a control or the player.

        The GUI loop (``tick``) owns the reveal and the handoff.  A late result
        is stored with its token and discarded when stale; a timeout
        invalidates the run before its error plate is painted.
        """
        picker = self._surprise_picker_for()
        try:
            result = self._run_pick(token, picker)
        except TaskCancelled:
            return
        except TaskTimeout as exc:
            self._store_surprise_outcome(
                token, error=("PICK TIMED OUT",
                              "The random pick took too long. Try again.", exc))
            return
        except Exception as exc:  # noqa: BLE001 - fail soft
            self._store_surprise_outcome(
                token, error=("SURPRISE FAILED",
                              "Could not pick a random pack: %s" % exc, exc))
            return
        self._store_surprise_outcome(token, result=result)

    def _run_pick(self, token, picker):
        """Run one pick on a worker, with a poll hook scoped to this run.

        The controller shares one runner, and a background caller would
        otherwise pump the runner's GUI ``on_poll`` from the ``rave-surprise``
        thread.  The per-run callback below is inert from any non-GUI thread
        and after cancel/timeout/close, so an abandoned worker cannot animate
        or otherwise mutate a control (P1-2/P2-5b).
        """
        function = lambda: picker.pick_once()
        poll = self._surprise_poll(token)
        if _runner_accepts_poll(self._task_runner):
            return self._task_runner.run(function, on_poll=poll)
        return self._task_runner.run(function)

    def _surprise_poll(self, token):
        """A poll hook that can only ever touch the GUI while the run is live."""
        def poll():
            if threading.current_thread() is not self._gui_thread:
                return
            if self._closed or not self._run_active(token):
                return
            self._advance_loading_frame()

        return poll

    def _store_surprise_outcome(self, token, result=None, error=None):
        with self._state_lock:
            if token != self._surprise_run or self._surprise_cancel.is_set():
                return
            self._surprise_pending = {"token": token, "result": result,
                                      "error": error}

    def surprise(self, prepared=False):
        """Pick one pack + track, spin for >=1.2s, then hand off once.

        Called synchronously by tests and by callers that already run on the
        GUI thread.  The window's normal entry point is ``_start_surprise()``:
        it runs only the network pick on a worker, and ``tick`` drives the
        reveal/handoff on the GUI thread.
        """
        if self._closed:
            return False
        if not prepared:
            return self._start_surprise()
        if self._surprise_guard is None or (
                not self._run_active(self._surprise_run)
                and not self._surprise_guard.fired):
            # Direct (synchronous) callers are the first gesture (or a retry
            # after a failed/cancelled run): give them the same fresh
            # token/event/one-shot gate as the async entry point.  A completed
            # gesture keeps its tripped gate, so a duplicate call cannot play.
            self._begin_surprise_run()
        token = self._surprise_run
        picker = self._surprise_picker_for()
        with self._state_lock:
            self._surprise_played = False
        try:
            result = self._run_pick(token, picker)
        except TaskCancelled:
            return False
        except TaskTimeout as exc:
            return self._abandon_surprise(
                token, "PICK TIMED OUT",
                "The random pick took too long. Try again.", exc)
        except Exception as exc:  # noqa: BLE001 - fail soft, no traceback
            return self._abandon_surprise(
                token, "SURPRISE FAILED",
                "Could not pick a random pack: %s" % exc, exc)
        if not self._run_active(token):
            return False
        if result is None or getattr(result, "cancelled", False):
            self._end_surprise_run()
            return False
        if getattr(result, "track", None) is None:
            return self._abandon_surprise(
                token, "NO PACK FOUND",
                getattr(result, "message", "") or
                "The random pick found nothing.")
        if not self._spin_surprise(token):
            return False
        return self._finish_surprise(token, result)

    def _surprise_result(self, result):
        """Status line while the worker owns the pick; failures wait for the plate."""
        if result is None or getattr(result, "cancelled", False):
            return
        if result:
            self.view.set_status("Random pack: %s" % result.title)

    def _spin_surprise(self, token=None):
        """The one >=1.2 s reveal.  False means playback must not start."""
        if token is None:
            token = self._surprise_run
        self.view.set_spinner_label("RANDOM PACK · RP-02")
        if not self._frames:
            self._surprise_failed("ART UNAVAILABLE",
                                  "The spinning-head frames are missing; "
                                  "playback was not started.", retry=False)
            return False
        if not self._run_active(token):
            return False
        animator = self._animator_factory(
            frames=self._frames,
            set_image=self.view.set_spinner_image,
            duration=MIN_DURATION,
            fps=FPS,
            sleep=self._sleep_ms,
            clock=self._clock,
            cancelled=lambda: not self._run_active(token),
        )
        try:
            completed = animator.run()
        except Exception as exc:  # noqa: BLE001 - dead control / bad frame
            completed = False
            self._log("surprise animation failed: %s" % exc)
        if not self._run_active(token):
            return False
        if not completed:
            self._surprise_failed("REVEAL FAILED",
                                  "The spin could not finish; playback was "
                                  "not started.", retry=True)
            return False
        return True

    def _finish_surprise(self, token, result):
        """Hand off once, on the GUI thread, if the run is still current."""
        if not self._run_active(token):
            return False
        track = getattr(result, "track", None)
        if track is None:
            return False
        played = []

        def handoff():
            if not self._run_active(token):
                return
            if self._handoff(track):
                self._surprise_played = True
                played.append(True)

        guard = self._surprise_guard
        if guard is None:
            # A direct caller still gets the picker's shared one-shot gate, so
            # no path can hand the same gesture to the player twice (P1-2).
            picker = self._surprise_picker_for()
            guard = getattr(picker, "guard", None) if picker is not None else None
        if guard is not None:
            guard.fire(handoff)
        else:
            handoff()
        self._end_surprise_run()
        return bool(played)

    def _end_surprise_run(self):
        self._hide_splash()
        with self._state_lock:
            self._surprising = False
            self._busy = False
            self._surprise_pending = None
            self._surprise_reveal = None

    def _abandon_surprise(self, token, title, detail, exc=None):
        """Invalidate a run before painting its failure plate (P1-2)."""
        with self._state_lock:
            if token == self._surprise_run:
                # Set the run's barrier first: any worker still alive sees it
                # and can never reach the handoff.
                self._surprise_cancel.set()
                self._surprise_run += 1
            self._surprise_pending = None
            self._surprise_reveal = None
        self._hide_splash()
        with self._state_lock:
            self._surprising = False
            self._busy = False
        self._show_plate("error", title, detail, "OK retry · BACK back",
                         retry=self._start_surprise)
        if exc is not None:
            self._log("surprise %s: %s" % (title.lower(), exc))
        return False

    def _drive_surprise(self):
        """Advance the async Surprise on the GUI thread (called by tick)."""
        with self._state_lock:
            pending = self._surprise_pending
            reveal = self._surprise_reveal
        if pending is not None:
            with self._state_lock:
                if self._surprise_pending is pending:
                    self._surprise_pending = None
            token = pending.get("token")
            if not self._run_active(token):
                self._end_surprise_run()
                return
            error = pending.get("error")
            if error is not None:
                title, detail, exc = error
                self._abandon_surprise(token, title, detail, exc)
                return
            result = pending.get("result")
            if result is None or getattr(result, "track", None) is None:
                self._abandon_surprise(
                    token, "NO PACK FOUND",
                    getattr(result, "message", "") if result is not None else
                    "The random pick found nothing.")
                return
            self._begin_reveal(token, result)
            return
        if reveal is not None:
            self._step_reveal(reveal)

    def _begin_reveal(self, token, result):
        if not self._run_active(token):
            self._end_surprise_run()
            return
        if not self._frames:
            self._abandon_surprise(
                token, "ART UNAVAILABLE",
                "The spinning-head frames are missing; playback was not "
                "started.", None)
            return
        reveal = {"token": token, "result": result,
                  "started": self._monotonic(), "index": -1}
        with self._state_lock:
            self._surprise_reveal = reveal
        self._step_reveal(reveal)

    def _step_reveal(self, reveal):
        token = reveal.get("token")
        if not self._run_active(token):
            with self._state_lock:
                if self._surprise_reveal is reveal:
                    self._surprise_reveal = None
            self._end_surprise_run()
            return
        elapsed = max(0.0, self._monotonic() - reveal.get("started", 0.0))
        index = frame_index(elapsed, len(self._frames), FPS)
        if index != reveal.get("index"):
            reveal["index"] = index
            if 0 <= index < len(self._frames):
                try:
                    self.view.set_spinner_image(self._frames[index])
                except Exception:  # noqa: BLE001 - dead control
                    self._end_surprise_run()
                    return
        if elapsed < MIN_DURATION:
            return
        with self._state_lock:
            if self._surprise_reveal is reveal:
                self._surprise_reveal = None
        self._finish_surprise(token, reveal.get("result"))

    def _monotonic(self):
        clock = self._clock
        if clock is None:
            return time.monotonic()
        try:
            return float(clock())
        except Exception:  # noqa: BLE001 - fake clocks may not be callable
            return time.monotonic()

    def _surprise_failed(self, title, detail, retry=True):
        self._hide_splash()
        self._show_plate("error", title, detail,
                         "OK retry · BACK back" if retry else "BACK back",
                         retry=self._start_surprise if retry else None)

    def _cancel_surprise_run(self):
        with self._state_lock:
            self._surprise_cancel.set()
            self._surprise_run += 1
            self._surprise_pending = None
            self._surprise_reveal = None

    def _cancel_surprise(self):
        self._cancel_surprise_run()
        self._hide_splash()
        with self._state_lock:
            self._surprising = False
            self._busy = False
        self.view.set_status("Surprise cancelled — no playback.")

    def _hide_splash(self):
        try:
            self.view.set_spinner_visible(False)
        except Exception:  # noqa: BLE001 - window already gone
            pass
    # --------------------------------------------------------------- playback
    def _mark_playback_started(self):
        """Remember that the app owns the current player status line.

        The player is shared with Kodi, so an external ``Player.Stop`` produces
        no callback here.  The footer tick uses this flag plus an active-player
        observation to clear the stale "Now playing" status.
        """
        self._player_seen_active = True
        self._player_active_at = time.monotonic()
        self._playback_status_active = True

    def _clear_playback_status(self):
        """Clear a status line this controller set for a now-stopped player."""
        self._last_play_key = None
        self._handed_off = False
        self._playback_status_active = False
        self._player_seen_active = False
        try:
            self.view.set_now_playing("")
        except Exception:  # noqa: BLE001 - optional view port
            pass
        try:
            self.view.set_status("")
        except Exception:  # noqa: BLE001 - optional view port
            pass

    def _handoff(self, track, live=None):
        if self._closed:
            return False
        is_live = bool(getattr(track, "live", False)) if live is None else bool(live)
        key = "%s|%s" % (getattr(track, "url", "") or "",
                         getattr(track, "title", "") or "")
        now = time.monotonic()
        # One GUI turn can deliver two OK events; Kodi would clear and restart
        # the playlist on the second call (P2-14).
        if (not is_live and key == self._last_play_key
                and 0.0 <= now - self._last_play_at < 0.75):
            self.view.set_status("Already playing — press Stop to restart.")
            return True
        if not is_live:
            # Playing a normal item stands the live latch down before the
            # footer is computed, so ON AIR cannot leak onto the new track.
            self._clear_live_latch()
        try:
            result = self.playback.play(track)
        except Exception as exc:  # noqa: BLE001 - bad URL / Kodi API failure
            self.view.set_status("Could not start playback — see the log.")
            self._log("playback handoff failed: %s" % exc)
            return False
        if not is_live:
            self._last_play_key = key
            self._last_play_at = now
        self._handed_off = True
        self._playing_live = is_live
        self._live_started_at = now if is_live else 0.0
        self._call_view("set_live", is_live)
        text = getattr(result, "text", None) or "Now playing: %s" % track.title
        self.view.set_now_playing(text)
        self.view.set_status("%s · Back leaves audio playing" % text)
        self._mark_playback_started()
        self._paint_footer(nowplaying.playing(
            getattr(track, "title", "") or "Untitled",
            artist=getattr(track, "pack", "") or "",
            live=is_live))
        self._trace("play %s live=%s" % (getattr(track, "url", ""), is_live))
        return True

    def _clear_live_latch(self):
        """Forget live state without issuing a player stop (P1-3)."""
        live = self._live_ui
        if live is not None and live.on_air:
            try:
                live.clear("STANDBY")
            except Exception:  # noqa: BLE001 - fake module may be read-only
                pass
        self._playing_live = False
        self._live_started_at = 0.0
        self._call_view("set_live", False)

    def _play_collection(self, entry, shuffle=False):
        if entry is None:
            self.view.set_status("No collection behind that row.")
            return False
        if self._closed or self._busy:
            return False
        self._busy = True
        self._start_loading("QUEUEING", "Building the playlist from %s…" % entry.label)
        tracks = []
        try:
            tracks = self._task_runner.run(lambda: self.data.collection(entry))
        except TaskCancelled:
            return False
        except TaskTimeout:
            self._show_error("SLOW COLLECTION",
                             "The source took too long to list. Try again.",
                             retry=lambda: self._play_collection(
                                 entry, shuffle=shuffle))
            return False
        except Exception as exc:  # noqa: BLE001 - never crash the window
            self._show_error("COLLECTION FAILED",
                             "Could not read the collection: %s" % exc,
                             retry=lambda: self._play_collection(
                                 entry, shuffle=shuffle))
            self._log("collection failed for %s: %s" % (entry.key, exc))
            return False
        finally:
            self._busy = False
            self._finish_loading()
        tracks = list(tracks or [])
        if self._closed:
            return False
        if not tracks:
            self._show_plate("empty", "STANDBY",
                             "There are no playable tracks in %s." % entry.label,
                             "BACK returns")
            return False
        try:
            result = self.playback.play_collection(tracks, shuffle=shuffle)
        except Exception as exc:  # noqa: BLE001 - quiet failure
            self.view.set_status("Could not queue the collection — see the log.")
            self._log("play_collection failed: %s" % exc)
            return False
        self._clear_live_latch()
        self._handed_off = True
        self._playing_live = False
        self._call_view("set_live", False)
        text = getattr(result, "text", None) or "Queued %d tracks" % len(tracks)
        self.view.set_now_playing(text)
        self.view.set_status("%s · Back leaves audio playing" % text)
        self._mark_playback_started()
        first = getattr(tracks[0], "title", "") or "Untitled"
        self._paint_footer(nowplaying.playing(
            first, album="%d tracks" % len(tracks)))
        self._trace("queue %d shuffle=%s" % (len(tracks), shuffle))
        return True

    def _resolve_and_play(self, entry):
        if self._closed or self._busy:
            return False
        self._busy = True
        self._start_loading("TUNING", "Resolving %s…" % entry.label)
        track = None
        try:
            track = self._task_runner.run(lambda: self.data.resolve(entry))
        except TaskCancelled:
            return False
        except TaskTimeout:
            self._show_error("SOURCE TIMEOUT",
                             "That source took too long to resolve. Try again.",
                             retry=lambda: self._resolve_and_play(entry))
            return False
        except Exception as exc:  # noqa: BLE001 - quiet failure
            self._show_error("SOURCE FAILED", "Could not resolve that set: %s" % exc,
                             retry=lambda: self._resolve_and_play(entry))
            self._log("resolve failed for %s: %s" % (entry.key, exc))
            return False
        finally:
            self._busy = False
            self._finish_loading()
        if self._closed:
            return False
        if track is None:
            self._show_plate("error", "NOT AVAILABLE",
                             "That source did not return a playable stream.",
                             "OK retry · BACK back",
                             retry=lambda: self._resolve_and_play(entry))
            return False
        return self._handoff(track)

    # --------------------------------------------------------------- loading
    # ------------------------------------------------------------- prefetch
    def _start_prefetch(self):
        """Warm Latest + the RaveTapePacks index once the home paint is done."""
        if self._prefetch_thread is not None:
            return
        try:
            thread = threading.Thread(target=self._prefetch_worker,
                                      name="rave-prefetch", daemon=True)
        except Exception:  # noqa: BLE001 - no thread means no prefetch
            return
        self._prefetch_thread = thread
        thread.start()

    def _prefetch_worker(self):
        # Let Home settle first: a user who immediately taps a room must not
        # compete with a speculative fetch for the network or the CPU.
        if self._prefetch_cancel.wait(2.0):
            return
        targets = ["latest",
                   Entry("rtp-index-events", "By Event", "prefetch", "",
                         "rtp_index", "ravetapepacks", "events")]
        for target in targets:
            if (self._prefetch_cancel.is_set() or self._closed
                    or self._user_active or self._busy
                    or self._refresh is not None):
                return
            try:
                page = self._load_page(target, 1)
            except Exception:  # noqa: BLE001 - speculative only
                continue
            if getattr(page, "rows", None):
                self._store_page(target, 1, page)
                self._trace("prefetch %r rows=%d" % (
                    target, len(page.rows)))

    # ------------------------------------------------ stale-while-revalidate
    def _paint_versions(self):
        """Version key for the paint cache: an upgrade must never repaint old rows."""
        screen = ""
        try:
            screen = self.data.screen_version()
        except Exception:  # noqa: BLE001 - optional manifest
            pass
        plugin = ""
        try:
            from .pluginbridge import plugin_addon

            plugin = str(plugin_addon().getAddonInfo("version") or "")
        except Exception:  # noqa: BLE001 - plugin may be missing
            pass
        return "%s/%s" % (screen, plugin)

    @staticmethod
    def _cache_nav(target, page):
        """Navigation/layout token for a cache key (folder vs list vs page)."""
        if target is None or target == "":
            kind = "home"
        elif isinstance(target, SearchTarget):
            kind = "search"
        elif isinstance(target, str):
            kind = "list"
        elif isinstance(target, Entry):
            kind = "entry:%s:%s" % (target.kind, target.source)
        else:
            kind = "obj:%s" % type(target).__name__
        return "%s:p%d" % (kind, max(1, int(page or 1)))

    def _cached_page(self, target, page):
        try:
            payload = self._paint_cache.load(
                "page", target, page, self._rows_per_page,
                nav=self._cache_nav(target, page))
        except Exception:  # noqa: BLE001 - a paint cache is always optional
            return None
        try:
            page_obj = decode_page(payload)
        except Exception:  # noqa: BLE001 - malformed entry is a miss
            return None
        if page_obj is None or not page_obj.rows:
            return None
        return page_obj

    def _store_page(self, target, page, page_obj):
        """Best-effort write: a bad row shape must never break a room load."""
        if page_obj is None or not getattr(page_obj, "rows", None):
            return
        try:
            actual = max(1, int(getattr(page_obj, "page", page) or page))
            encoded = encode_page(page_obj)
            if encoded is None:
                return
            if actual != int(page):
                # Never leave a clamped page's rows under the requested-key
                # page number: a later open would paint page 1 as page 3 and
                # its refresh would be discarded (advisor P2-5/P2-9).
                self._paint_cache.delete(
                    "page", target, page, self._rows_per_page,
                    nav=self._cache_nav(target, page))
            self._paint_cache.store(
                "page", target, actual, self._rows_per_page, encoded,
                nav=self._cache_nav(target, actual))
        except Exception as exc:  # noqa: BLE001 - cache is never load-bearing
            self._log("page cache write skipped: %s" % exc)

    def _cached_screen(self, route, query, page):
        try:
            payload = self._paint_cache.load(
                "library", "%s|%s" % (route, query), page,
                self._rows_per_page,
                nav="library:%s:%s:p%d" % (route, query, page))
        except Exception:  # noqa: BLE001
            return None
        try:
            screen = decode_library_screen(payload)
        except Exception:  # noqa: BLE001 - malformed entry is a miss
            return None
        if screen is None or not getattr(screen, "rows", None):
            return None
        return screen

    def _store_screen(self, route, query, page, screen):
        if screen is None or not getattr(screen, "rows", None):
            return
        if not getattr(screen, "is_ready", False):
            return
        target = "%s|%s" % (route, query)
        try:
            actual = max(1, int(getattr(screen, "page", page) or page))
            encoded = encode_library_screen(screen)
            if encoded is None:
                return
            if actual != int(page):
                self._paint_cache.delete(
                    "library", target, page, self._rows_per_page,
                    nav="library:%s:%s:p%d" % (route, query, page))
            self._paint_cache.store(
                "library", target, actual, self._rows_per_page, encoded,
                nav="library:%s:%s:p%d" % (route, query, actual))
        except Exception as exc:  # noqa: BLE001 - cache is never load-bearing
            self._log("screen cache write skipped: %s" % exc)

    def _cached_live(self):
        try:
            payload = self._paint_cache.load("live", "live", 1, 1,
                                             nav="live:p1")
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(payload, dict):
            return None
        stations = []
        for item in payload.get("stations") or []:
            if not isinstance(item, dict):
                return None
            try:
                stations.append(Station(
                    token=str(item.get("token") or ""),
                    name=str(item.get("name") or ""),
                    tagline=str(item.get("tagline") or ""),
                    url=str(item.get("url") or ""),
                    art=str(item.get("art") or ""),
                    code=str(item.get("code") or "RP-31"),
                    country=str(item.get("country") or "GB"),
                    codec=str(item.get("codec") or ""),
                    bitrate=int(item.get("bitrate") or 0),
                ))
            except (TypeError, ValueError):
                return None
        return stations or None

    def _store_live(self, stations):
        if not stations:
            return
        items = []
        for station in stations:
            items.append({
                "token": station.token,
                "name": station.name,
                "tagline": station.tagline,
                "url": station.url,
                "art": station.art,
                "code": station.code,
                "country": station.country,
                "codec": station.codec,
                "bitrate": int(station.bitrate or 0),
            })
        try:
            self._paint_cache.store("live", "live", 1, 1,
                                    {"stations": items}, nav="live:p1")
        except Exception:  # noqa: BLE001
            pass

    def _cancel_refresh(self):
        """Forget a pending refresh; its late result is ignored."""
        if self._refresh is not None:
            self._refresh = None
            self._refresh_seq += 1

    def _start_refresh(self, loader, apply, matches):
        """Run ``loader`` on a daemon thread and apply its result in ``tick``."""
        self._cancel_refresh()
        token = self._refresh_seq
        try:
            task = self._background_task_factory(loader)
            start = getattr(task, "start", None)
            if callable(start):
                start()
        except Exception as exc:  # noqa: BLE001 - cache paint still stands
            self._log("refresh could not start: %s" % exc)
            return False
        self._refresh = {
            "token": token,
            "task": task,
            "started": time.monotonic(),
            "apply": apply,
            "matches": matches,
        }
        return True

    def _poll_refresh(self):
        """Called from ``tick``: repaint only when the refreshed rows changed."""
        task = self._refresh
        if task is None:
            return
        if time.monotonic() - task["started"] > REFRESH_TIMEOUT_SECONDS:
            self._refresh = None
            self._refresh_seq += 1
            if self._matches(task):
                self.view.set_status(PAINT_OFFLINE)
            return
        status, value = task["task"].poll()
        if status == "running":
            return
        self._refresh = None
        if status == "error":
            self._log("refresh failed: %s" % value)
            if self._matches(task):
                self.view.set_status(PAINT_OFFLINE)
            return
        try:
            task["apply"](value)
        except Exception as exc:  # noqa: BLE001 - cached rows must remain usable
            self._log("refresh apply failed: %s" % exc)
            if self._matches(task):
                self.view.set_status(PAINT_OFFLINE)

    @staticmethod
    def _matches(task):
        try:
            return bool(task["matches"]())
        except Exception:  # noqa: BLE001 - a paint match is advisory
            return False

    def _apply_refreshed_page(self, target, painted_page, base_sig, page_obj):
        self._store_page(target, painted_page, page_obj)
        if self._closed or self._target != target or self._page != painted_page:
            return
        if self._view_kind != "list":
            return
        if not getattr(page_obj, "rows", None):
            self.view.set_status(PAINT_EMPTY)
            return
        try:
            changed = signature(page_obj) != base_sig
        except Exception:  # noqa: BLE001 - repaint rather than risk stale
            changed = True
        if not changed:
            self.view.set_status(PAINT_CURRENT)
            return
        # Restore the absolute content offset, not the on-screen row index:
        # page 2+ has a PREVIOUS PAGE nav row at index 0, so clamping that
        # index to len(rows)-1 can land on the nav row or one row early
        # (advisor P2-4).
        offset = self._content_offset()
        self._apply_page(target, page_obj)
        self._render_page(index=None)
        self._restore_offset(offset)
        self._trace("refresh repaint %r page=%s rows=%d" % (
            target, self._page, len(page_obj.rows)))

    def _apply_refreshed_screen(self, route, query, painted_page, base_sig,
                                screen):
        self._store_screen(route, query, painted_page, screen)
        if self._closed or self._view_kind != "list":
            return
        if self._target != (SearchTarget(query)
                            if route == ROUTE_SEARCH and query else route):
            return
        if self._page != painted_page:
            return
        if not getattr(screen, "is_ready", False):
            # The saved rows stay on screen (SWR), but a non-ready refresh is
            # terminal: without this the "UPDATING" line was left forever on
            # an empty/error source.  Error and empty get distinct notes.
            if screen is not None and getattr(screen, "has_error", False):
                self.view.set_status(PAINT_OFFLINE)
            else:
                self.view.set_status(PAINT_EMPTY)
            return
        if not getattr(screen, "rows", None):
            self.view.set_status(PAINT_EMPTY)
            return
        try:
            changed = library_signature(screen) != base_sig
        except Exception:  # noqa: BLE001
            changed = True
        if not changed:
            self.view.set_status(PAINT_CURRENT)
            return
        offset = self._content_offset()
        self._paint_library_screen(screen, route, query)
        self._restore_offset(offset)

    def _apply_refreshed_live(self, base_sig, stations):
        self._store_live(stations)
        live = self._live_ui
        if self._closed or live is None or self._target != "live":
            return
        if not stations:
            self.view.set_status(PAINT_EMPTY)
            return
        live._stations = list(stations)
        rows = [self._adopt_row(row) for row in live.rows()]
        try:
            changed = _live_signature(rows) != base_sig
        except Exception:  # noqa: BLE001
            changed = True
        if not changed:
            self.view.set_status(PAINT_CURRENT)
            return
        index = max(0, min(self._current_index(), len(rows) - 1)) if rows else 0
        self._rows = rows
        self._page_rows = rows
        self._total = len(rows)
        self._render_page(index=index)
        self._trace("refresh repaint live rows=%d" % len(rows))

    def _load_target(self, target, page=1, push=True):
        self._user_active = True
        self._prefetch_cancel.set()
        started = time.monotonic()
        if self._closed or self._busy:
            return False
        if isinstance(target, SearchTarget):
            return self._load_library_search(target.query, page, push=push)
        if isinstance(target, str):
            if target == "live":
                return self._open_live_room(push=push)
            if target in LIBRARY_ROUTES:
                return self._load_library_screen(target, page, push=push)
        self._cancel_refresh()
        cached = self._cached_page(target, page)
        if cached is not None:
            # Stale-while-revalidate: the saved page paints now; the source
            # refresh runs off the GUI thread and repaints only if it changed.
            if push:
                self._push_current()
            self._apply_page(target, cached)
            self._render_page(index=None)
            # The source may clamp an out-of-range page; the refresh belongs
            # to the page actually painted, not the requested integer.
            painted_page = self._page
            self.view.set_status(PAINT_UPDATING)
            try:
                base_sig = signature(cached)
            except Exception:  # noqa: BLE001 - repaint rather than risk stale
                base_sig = ""
            self._start_refresh(
                lambda: self._load_page(target, page),
                lambda refreshed: self._apply_refreshed_page(
                    target, painted_page, base_sig, refreshed),
                lambda: (self._target == target
                         and self._page == painted_page
                         and self._view_kind == "list" and not self._closed))
            self._trace("paint cache %r page=%s rows=%d in %.0f ms" % (
                target, page, len(cached.rows),
                (time.monotonic() - started) * 1000.0))
            return True
        self._busy = True
        label = self._label_for(target)
        self._start_loading("PLEASE WAIT", "Loading %s…" % label)
        try:
            result = self._task_runner.run(lambda: self._load_page(target, page))
        except TaskCancelled:
            return False
        except TaskTimeout as exc:
            self._show_error("SOURCE TIMEOUT",
                             "%s took too long to answer. Try again." % label,
                             retry=lambda: self._load_target(target, page, push))
            self._log("load timeout for %r: %s" % (target, exc))
            return False
        except Exception as exc:  # noqa: BLE001 - never crash the window
            self._show_error("SOURCE ERROR",
                             "Could not load %s: %s" % (label, exc),
                             retry=lambda: self._load_target(target, page, push))
            self._log("load failed for %r: %s" % (target, exc))
            return False
        finally:
            self._busy = False
            self._finish_loading()
        if self._closed:
            return False
        rows = list(getattr(result, "rows", []) or [])
        if not rows:
            detail = "Nothing in %s right now. The source may be blocked or " \
                     "offline." % label
            self._show_plate("empty", "STANDBY", detail, "OK retry · BACK back",
                             retry=lambda: self._load_target(target, page, push))
            self._trace("empty %r page=%s" % (target, page))
            return False
        self._store_page(target, page, result)
        if push:
            self._push_current()
        self._apply_page(target, result)
        self._render_page(index=None)
        self._trace("loaded %r page=%s/%s rows=%s total=%s in %.0f ms" %
                    (target, self._page, self._pages, len(self._rows),
                     self._total, (time.monotonic() - started) * 1000.0))
        return True

    # ------------------------------------------------- module-owned rooms
    def _library_handlers(self):
        """The one library-screen implementation, lazily wired to the plugin."""
        if self._library_ui is None:
            modules = None
            try:
                modules = self.data.modules
            except Exception as exc:  # noqa: BLE001 - plugin missing is a plate
                self._log("library: plugin unavailable: %s" % exc)
            self._library_ui = LibraryScreens(
                backend=PluginBackend(modules=modules),
                playback=None,  # the controller keeps the single playback path
                logger=self._logger, queue=self._download_queue,
                page_size=self._rows_per_page)
        else:
            # An injected LibraryScreens still needs the queue (P1-5) and the
            # controller's Rows-per-page choice (P2-2) if it supports them.
            if self._download_queue is not None and getattr(
                    self._library_ui, "queue", None) is None:
                try:
                    self._library_ui.queue = self._download_queue
                except Exception:  # noqa: BLE001 - fake may be read-only
                    pass
            setter = getattr(self._library_ui, "set_page_size", None)
            if callable(setter) and self._page_size_explicit:
                try:
                    setter(self._rows_per_page)
                except Exception:  # noqa: BLE001 - fake may be read-only
                    pass
        return self._library_ui

    def _load_library_screen(self, route, page=1, push=True):
        handlers = self._library_handlers()
        route = route if route in LIBRARY_ROUTES else ROUTE_SEARCH
        if route == ROUTE_SEARCH:
            return self._load_library_search("", page, push=push)
        function = {
            ROUTE_FAVOURITES: lambda: handlers.favourites(page),
            ROUTE_DOWNLOADS: lambda: handlers.downloads(page),
            ROUTE_ABOUT: lambda: handlers.about(),
        }.get(route, lambda: handlers.favourites(page))
        return self._run_library(route, "", page, push, function)

    def _load_library_search(self, query, page=1, push=True):
        query = " ".join(str(query or "").split())
        handlers = self._library_handlers()
        return self._run_library(
            ROUTE_SEARCH, query, page, push,
            lambda: handlers.search(query, page))

    def _run_library(self, route, query, page, push, function):
        """Paint a library loading plate, run its handler, then adopt the Screen."""
        started = time.monotonic()
        if self._closed or self._busy:
            return False
        self._cancel_refresh()
        cached = self._cached_screen(route, query, page)
        if cached is not None:
            if push:
                self._push_current()
            self._paint_library_screen(cached, route, query)
            painted_page = self._page
            self.view.set_status(PAINT_UPDATING)
            try:
                base_sig = library_signature(cached)
            except Exception:  # noqa: BLE001 - repaint rather than risk stale
                base_sig = ""
            self._start_refresh(
                function,
                lambda refreshed: self._apply_refreshed_screen(
                    route, query, painted_page, base_sig, refreshed),
                lambda: (self._view_kind == "list" and not self._closed
                         and self._page == painted_page
                         and self._target == (SearchTarget(query)
                                              if route == ROUTE_SEARCH and query
                                              else route)))
            self._trace("paint cache library %s page=%s rows=%d in %.0f ms" % (
                route, page, len(cached.rows),
                (time.monotonic() - started) * 1000.0))
            return True
        self._busy = True
        label = TITLES.get(route, route or "library").title()
        self._start_loading("PLEASE WAIT", "Loading %s…" % label)
        try:
            screen = self._task_runner.run(function)
        except TaskCancelled:
            return False
        except TaskTimeout as exc:
            self._show_error(
                "SOURCE TIMEOUT",
                "%s took too long to answer. Try again." % label,
                retry=lambda: self._run_library(route, query, page, push, function))
            self._log("library timeout for %r: %s" % (route, exc))
            return False
        except Exception as exc:  # noqa: BLE001 - never crash the window
            self._show_error(
                "SOURCE ERROR", "Could not load %s: %s" % (label, exc),
                retry=lambda: self._run_library(route, query, page, push, function))
            self._log("library load failed for %r: %s" % (route, exc))
            return False
        finally:
            self._busy = False
            self._finish_loading()
        if self._closed:
            return False
        if not isinstance(screen, Screen):
            self._show_error(
                "SCREEN ERROR", "%s returned no screen." % label,
                retry=lambda: self._run_library(route, query, page, push,
                                                function))
            return False
        self._store_screen(route, query, page, screen)
        if push:
            self._push_current()
        self._paint_library_screen(screen, route, query)
        self._trace("library %s page=%s/%s rows=%s total=%s state=%s" % (
            route, screen.page, screen.pages, len(screen.rows),
            screen.total, screen.state))
        return screen.is_ready

    def _paint_library_screen(self, screen, route, query=""):
        rows = [self._adopt_row(row) for row in screen.rows]
        self._library_screen = screen
        self._target = (SearchTarget(query)
                        if route == ROUTE_SEARCH and query else route)
        self._title = screen.title
        self._subtitle = screen.subtitle
        self._page = max(1, int(getattr(screen, "page", 1) or 1))
        self._pages = max(1, int(getattr(screen, "pages", 1) or 1))
        self._total = max(0, int(getattr(screen, "total", 0) or 0))
        self._rows_per_page = max(1, int(
            getattr(screen, "page_size", DEFAULT_PAGE_SIZE) or DEFAULT_PAGE_SIZE))
        # Keep the shell-owned rooms on the same page size: no leak where
        # Latest pages at 25 only because the user visited Favourites (P2-2).
        try:
            self.data.rows_per_page = self._rows_per_page
        except Exception:  # noqa: BLE001 - read-only test double
            pass
        self._page_has_next = bool(getattr(screen, "has_next", False))
        self._page_rows = rows
        self._view_kind = "list"
        index = 1 if (screen.has_previous and rows) else 0
        self._render_page(index=index)
        if screen.has_error:
            self.view.set_status(screen.error or "Could not load this room.")
        elif screen.is_empty:
            self.view.set_status(screen.subtitle or "")
        self._paint_footer()

    def _invalidate_library_cache(self, route=None, query="", page=None):
        """Drop one cached library page before a destructive reload.

        A remove/delete reload used to paint the old cached screen first, so
        the row the user just removed briefly reappeared until the background
        refresh finished (advisor P2-3).
        """
        route = self._target if route is None else route
        if isinstance(route, SearchTarget):
            query = route.query
            route = ROUTE_SEARCH
        if route not in LIBRARY_ROUTES:
            return False
        page = self._page if page is None else page
        try:
            return bool(self._paint_cache.delete(
                "library", "%s|%s" % (route, query), page,
                self._rows_per_page,
                nav="library:%s:%s:p%d" % (route, query, page)))
        except Exception:  # noqa: BLE001 - cache invalidation is best effort
            return False

    def _reload_library(self):
        screen = self._library_screen
        if screen is None:
            return False
        if screen.route == ROUTE_SEARCH:
            return self._load_library_search(screen.query, self._page, push=False)
        return self._load_library_screen(screen.route, self._page, push=False)

    def _run_library_play(self, entry):
        result = self._library_handlers().play(entry)
        if not result.ok:
            self.view.set_status(result.message)
            return False
        if result.track is None:
            self.view.set_status("That row has no playable stream.")
            return False
        return self._handoff(result.track)

    def _run_library_action(self, entry):
        action = str(getattr(entry, "action", "") or "")
        if action == ACTION_PLAY:
            return self._run_library_play(entry)
        if action == ACTION_REMOVE:
            result = self._library_handlers().remove(entry)
            message = result.message
            if result.ok and self._target in (ROUTE_FAVOURITES,
                                              ROUTE_DOWNLOADS):
                self._invalidate_library_cache()
                reloaded = self._reload_library()
                # _reload_library repaints and clears the status; put the
                # confirmation back so the user sees it (P2-3).
                self.view.set_status(message)
                return reloaded
            self.view.set_status(message)
            return bool(result.ok)
        if action == ACTION_CANCEL:
            result = self._library_handlers().cancel(entry)
            message = result.message
            if result.ok and self._target == ROUTE_DOWNLOADS:
                self._invalidate_library_cache()
                reloaded = self._reload_library()
                self.view.set_status(message)
                return reloaded
            self.view.set_status(message)
            return bool(result.ok)
        if action == ACTION_RETRY:
            return self._retry_library(entry)
        if action == ACTION_OPEN:
            url = str((getattr(entry, "payload", None) or {}).get("url") or "")
            self.view.set_status(
                "Source: %s" % url if url else "Read-only credit — Back returns.")
            return False
        return False

    def _retry_library(self, entry):
        payload = dict(getattr(entry, "payload", None) or {})
        route = str(payload.get("route") or "")
        query = str(payload.get("query") or "")
        page = int(payload.get("page") or 1)
        if route not in LIBRARY_ROUTES:
            return False
        handlers = self._library_handlers()
        return self._run_library(
            route, query, page, False,
            lambda: handlers.retry(entry))

    def _open_library_room(self, entry):
        """Map a library room payload onto the shell's existing room routes."""
        payload = dict(getattr(entry, "payload", None) or {})
        mode = str(payload.get("mode") or "")
        title = getattr(entry, "label", "") or "Untitled"
        base = dict(
            subtitle=getattr(entry, "subtitle", "") or "",
            art=getattr(entry, "art", "") or "",
            hero=getattr(entry, "hero", "") or getattr(entry, "art", "") or "",
            fact=getattr(entry, "fact", "") or "",
            code=getattr(entry, "code", "") or "",
            plot=getattr(entry, "plot", "") or title,
        )
        if mode == "archive_item":
            identifier = str(payload.get("identifier") or payload.get("target") or "")
            if not identifier:
                self.view.set_status("That pack has no identifier.")
                return False
            target = Entry(key=identifier, label=title, kind="pack",
                           source="latest", target=identifier, **base)
        elif mode == "legacy_pack":
            key = str(payload.get("pack") or payload.get("target") or "")
            if not key:
                return False
            target = Entry(key="library-pack-%s" % key, label=title,
                           kind="pack", source="ravetapepacks", target=key,
                           **base)
        elif mode == "legacy_post":
            key = str(payload.get("post") or payload.get("target") or "")
            if not key:
                return False
            target = Entry(key="library-post-%s" % key, label=title,
                           kind="rtp_post", source="ravetapepacks", target=key,
                           **base)
        elif mode == "legacy_jt_show":
            key = str(payload.get("key") or payload.get("target") or "")
            if not key:
                return False
            target = Entry(key="library-jt-%s" % key, label=title,
                           kind="show", source="jungletapes", target=key,
                           **base)
        elif mode == "dnb_play":
            show_id = str(payload.get("id") or payload.get("target") or "")
            if not show_id:
                self.view.set_status("That DNB show has no identifier.")
                return False
            target = Entry(key="library-dnb-%s" % show_id, label=title,
                           kind="dnb_show", source="dnb", target=show_id,
                           **base)
            # A saved show is a resolver row, not a folder: resolve its stream
            # and play it (P1-4).  _load_target would paint an empty STANDBY.
            return self._resolve_and_play(target)
        elif mode == "handoff":
            link = str(payload.get("target") or "")
            path = ""
            try:
                path = str(self.data.modules.handoff.target(link, title) or "")
            except Exception as exc:  # noqa: BLE001 - no matching add-on
                self._log("library hand-off failed for %s: %s" % (link, exc))
            if not link or not path:
                self.view.set_status("That link has no matching Kodi add-on.")
                return False
            track = Track(title, str(payload.get("platform") or "add-on"),
                          link, getattr(entry, "art", "") or "",
                          source="handoff", path=path)
            # The platform add-on owns the item; hand the plugin path straight
            # to the one player instead of opening an empty children room.
            return self._handoff(track)
        else:
            self.view.set_status("That saved row cannot be opened.")
            return False
        return self._load_target(target, 1, push=True)

    # --------------------------------------------------------------- live
    def _live_radio(self):
        """The one Live Radio implementation, wired to the controller handoff."""
        if self._live_ui is None:
            modules = None
            art_root = None
            try:
                modules = self.data.modules
                art_root = self.data.root
            except Exception as exc:  # noqa: BLE001 - fallback URLs still render
                self._log("live: plugin unavailable: %s" % exc)
            self._live_ui = LiveRadio(
                modules=modules, playback=_LiveHandoff(self),
                stopper=self._stop_player, art_root=art_root,
                logger=self._logger)
        elif getattr(self._live_ui, "playback", None) is None:
            # An injected screen still plays through the controller's one
            # handoff path; the live module never owns a second player.
            self._live_ui.playback = _LiveHandoff(self)
        if getattr(self._live_ui, "stopper", None) is None:
            self._live_ui.stopper = self._stop_player
        return self._live_ui

    def _stop_player(self):
        try:
            return bool(self.playback.stop())
        except Exception:  # noqa: BLE001 - player unavailable
            return False

    def _open_live_room(self, push=True):
        started = time.monotonic()
        if self._closed or self._busy:
            return False
        self._cancel_refresh()
        live = self._live_radio()
        cached = self._cached_live()
        if cached is not None:
            # Paint the last station list at once; resolve the live URLs and
            # names again in the background (a changed stream repaints itself).
            live._stations = list(cached)
            if push:
                self._push_current()
            self._target = "live"
            self._title = "LIVE RADIO"
            self._subtitle = "Kool FM · Rinse FM · Centreforce · pirate"
            rows = [self._adopt_row(row) for row in live.rows()]
            self._page = 1
            self._pages = 1
            self._total = len(rows)
            self._page_has_next = False
            self._page_rows = rows
            self._view_kind = "list"
            self._render_page(index=0)
            self.view.set_status(PAINT_UPDATING)
            base_sig = _live_signature(rows)
            self._start_refresh(
                lambda: load_stations(self.data.modules),
                lambda stations: self._apply_refreshed_live(base_sig, stations),
                lambda: (self._target == "live" and not self._closed
                         and self._view_kind == "list"))
            self._trace("paint cache live rows=%d in %.0f ms" % (
                len(rows), (time.monotonic() - started) * 1000.0))
            self._paint_footer(live.footer())
            return True
        if push:
            self._push_current()
        self._target = "live"
        self._title = "LIVE RADIO"
        self._subtitle = "Kool FM · Rinse FM · Centreforce · pirate"
        rows = [self._adopt_row(row) for row in live.rows()]
        self._page = 1
        self._pages = 1
        self._total = len(rows)
        self._page_has_next = False
        self._page_rows = rows
        self._view_kind = "list"
        self._render_page(index=0)
        self._store_live(live.stations)
        self.view.set_status(live.status or "STANDBY")
        self._paint_footer(live.footer())
        self._trace("live rows=%d" % len(rows))
        return True

    def _paint_live_rows(self, index=0, status=None):
        live = self._live_ui
        if live is None:
            return
        rows = [self._adopt_row(row) for row in live.rows()]
        self._rows = rows
        self._page_rows = rows
        self._total = len(rows)
        self._render_page(index=max(0, min(int(index or 0), len(rows) - 1))
                          if rows else 0)
        # _render_page clears the status line; put the action feedback back so
        # "ON AIR · Kool FM" / "Could not start…" is actually visible (P2-3).
        if status:
            self.view.set_status(status)

    def _run_live_action(self, entry, action):
        action_type = str(action.get("type") or "")
        if action_type == "open" and action.get("source") == "pirate":
            return self._open_pirate_room(entry)
        live = self._live_radio()
        ok = live.perform(action)
        # Keep the shell latch in step with the module: a station that stopped
        # (or failed to start) must not leave `set_live(True)` behind (P1-3).
        self._playing_live = bool(live.on_air)
        if not self._playing_live:
            self._live_started_at = 0.0
        self._call_view("set_live", self._playing_live)
        if self._playing_live:
            self._mark_playback_started()
        message = live.status
        if self._target == "live":
            self._paint_live_rows(index=self._current_index(), status=message)
        else:
            self.view.set_status(message)
        self._paint_footer(live.footer())
        return bool(ok)

    def _open_pirate_room(self, entry):
        art = getattr(entry, "art", "") or ""
        target = Entry(
            key="pirate_source", label="Pirate Radio Archives",
            subtitle="1990s pirate-radio recordings", art=art,
            kind="folder", source="pirate_source", target="pirate_source",
            hero=art, fact="1990s", code="RP-32",
            plot="Curated 1990s pirate-radio recordings")
        return self._load_target(target, 1, push=True)

    # ------------------------------------------------------- row normalisation
    def _adopt_row(self, row):
        """One normalisation for library Rows, live dicts and shell Entries."""
        if isinstance(row, Entry):
            return row
        payload = getattr(row, "payload", None)
        if isinstance(payload, dict):
            return self._adopt_library_row(row, payload)
        if isinstance(row, dict):
            return self._adopt_live_row(row)
        # Generic duck row: never crash on a foreign row shape.
        return _EntryLike(
            key=str(getattr(row, "key", "") or ""),
            label=str(getattr(row, "label", "") or getattr(row, "title", "")),
            subtitle=str(getattr(row, "subtitle", "") or ""),
            art=str(getattr(row, "art", "") or getattr(row, "icon", "")),
            kind=str(getattr(row, "kind", "") or ""),
            target=str(getattr(row, "target", "") or ""),
            hero=str(getattr(row, "hero", "") or ""),
            fact=str(getattr(row, "fact", "") or ""),
            code=str(getattr(row, "code", "") or ""),
            plot=str(getattr(row, "plot", "") or ""),
            meta=str(getattr(row, "meta", "") or ""))

    def _adopt_library_row(self, row, payload):
        payload = dict(payload or {})
        kind = {
            KIND_ROOM: "library_room",
            KIND_TRACK: "library_track",
            KIND_ACTION: "library_action",
        }.get(str(getattr(row, "kind", "") or ""), "library_action")
        art = str(getattr(row, "icon", "") or getattr(row, "art", "") or "")
        hero = str(getattr(row, "fanart", "") or
                   getattr(row, "hero", "") or art)
        subtitle = str(getattr(row, "subtitle", "") or
                       payload.get("source") or payload.get("mode") or "")
        plot = str(getattr(row, "plot", "") or subtitle)
        target = str(payload.get("identifier") or payload.get("target") or
                     payload.get("url") or getattr(row, "label", ""))
        fact = str(getattr(row, "fact", "") or "")
        code = str(getattr(row, "code", "") or "")
        meta = "%s · %s" % (fact, code) if fact and code else (fact or code)
        return _EntryLike(
            key="library-%s" % target,
            label=str(getattr(row, "label", "") or ""),
            subtitle=subtitle,
            art=art,
            kind=kind,
            source="library",
            target=target,
            hero=hero,
            fact=fact,
            code=code,
            plot=plot,
            meta=meta,
            payload=payload,
            action=str(getattr(row, "action", "") or ""))

    def _adopt_live_row(self, row):
        row = dict(row or {})
        title = str(row.get("title") or "")
        fact = str(row.get("fact") or "")
        code = str(row.get("code") or "")
        action = row.get("action")
        action = dict(action) if isinstance(action, dict) else {}
        art = str(row.get("art") or "")
        kind = str(row.get("kind") or "station")
        target = str(action.get("station") or action.get("target") or title)
        subtitle = ("Live radio · no duration" if kind == "station"
                    else "Pirate Radio Archives")
        meta = "%s · %s" % (fact, code) if fact and code else (fact or code)
        return _EntryLike(
            key="live-%s" % target, label=title, subtitle=subtitle,
            art=art, kind=kind, source="live", target=target, hero=art,
            fact=fact, code=code, plot=subtitle, meta=meta,
            action=action)

    # ------------------------------------------------------------- footer
    def _paint_footer(self, footer=None):
        if footer is None:
            footer = self._footer_for_current()
        self._footer = footer
        self._footer_at = time.monotonic()
        self._call_view("set_footer", footer)

    def _footer_for_current(self):
        if self._live_on_air():
            return self._live_ui.footer()
        if (self._footer is not None and self._footer.has_media
                and self._is_playing()):
            return self._footer
        entry = self._selected()
        if entry is None:
            return nowplaying.standby()
        return nowplaying.standby(room=getattr(entry, "label", ""),
                                  fact=getattr(entry, "fact", ""))

    def _live_on_air(self):
        """Both our live run and the live module must agree the station is on."""
        return bool(self._playing_live and self._live_ui is not None
                    and self._live_ui.on_air)

    def tick(self):
        """Refresh the footer at ~1 Hz; the window's idle loop calls this."""
        if self._closed:
            return
        # A completed stale-page refresh is applied on the GUI thread before
        # anything cosmetic, so a changed room is never held behind the footer.
        self._poll_refresh()
        # The async Surprise is driven from the GUI thread; it must run before
        # the footer throttle so a completed pick is never stuck behind it.
        self._drive_surprise()
        now = time.monotonic()
        if self._footer_at is not None and now - self._footer_at < 0.9:
            return
        snapshot = self._read_player_snapshot()
        # Observe the shared player across ticks.  When an app-owned status
        # line is on screen and the player disappears (JSON-RPC stop, another
        # add-on, or the end of the queue), clear it here: no Kodi callback is
        # delivered for an external stop (3.9.54 device QA P2-2).
        if snapshot:
            self._player_seen_active = True
            self._player_active_at = now
        elif (self._player_seen_active and self._playback_status_active
              and now - self._player_active_at >= 2.5
              and not self._is_playing()):
            self._clear_playback_status()
            if self._footer is not None and self._footer.has_media:
                self._paint_footer(nowplaying.standby())
        if self._reconcile_live(snapshot):
            return
        if not snapshot:
            if (self._footer is not None and self._footer.has_media
                    and not self._is_playing()):
                self._paint_footer()
            return
        if snapshot.get("starting"):
            # Kodi is opening the stream (Caching/HasMedia) but not decoding
            # yet; keep the live state instead of clearing it during buffering.
            if self._live_ui is not None and self._live_ui.on_air:
                self._paint_footer(self._live_ui.footer())
                return
        self._paint_footer(nowplaying.from_player(
            snapshot, live=self._playing_live))

    def _reconcile_live(self, snapshot):
        """One source of truth: Kodi's player decides whether live is on air.

        Returns True when the live footer was painted and the normal player
        path must be skipped.
        """
        live = self._live_ui
        if live is None or not live.on_air:
            if self._playing_live:
                self._playing_live = False
                self._call_view("set_live", False)
            return False
        if not snapshot:
            # Kodi reports no media at all.  Give a fresh station a short
            # start-up grace (Player.play is asynchronous), then stand down so
            # a stopped/never-started stream cannot leave ON AIR latched.
            if (self._playing_live
                    and self._monotonic() - self._live_started_at < 3.0):
                self._paint_footer(live.footer())
                return True
            self._stand_down_live("STANDBY")
            return True
        if not self._playing_live:
            # A normal track/collection started through another path; the live
            # latch is stale even though the module still remembers a station.
            self._stand_down_live("STANDBY")
            return False
        paused = bool(snapshot.get("paused"))
        if paused != live.paused:
            live.set_paused(paused)
            if self._target == "live":
                self._paint_live_rows(index=self._current_index())
        self._call_view("set_live", True)
        self._paint_footer(live.footer())
        return True

    def _stand_down_live(self, status="STANDBY"):
        live = self._live_ui
        if live is not None:
            try:
                live.clear(status)
            except Exception:  # noqa: BLE001 - a fake module may be read-only
                try:
                    live._playing = ""
                    live._paused = False
                except Exception:  # noqa: BLE001 - best effort
                    pass
        self._playing_live = False
        self._call_view("set_live", False)
        if self._target == "live":
            self._paint_live_rows(index=self._current_index(),
                                  status=status or "STANDBY")
        # The render above reuses the previous footer while the fake/real
        # player still reports playing; stand the footer down explicitly so a
        # stale ON AIR model cannot survive the reset (P1-3).
        self._paint_footer(nowplaying.standby())

    def _read_player_snapshot(self):
        if self._player_snapshot is not None:
            try:
                return self._player_snapshot()
            except Exception:  # noqa: BLE001 - a probe is advisory
                return None
        try:
            import xbmc

            player = xbmc.Player()
            if not player.isPlaying():
                # A stream that is still opening reports Caching/HasMedia but
                # not Playing.  Do not treat that buffering gap as "stopped".
                if (xbmc.getCondVisibility("Player.Caching")
                        or xbmc.getCondVisibility("Player.HasMedia")):
                    return {"starting": True, "playing": False,
                            "paused": False,
                            "title": xbmc.getInfoLabel("Player.Title"),
                            "duration": 0, "elapsed": 0}
                return None
            return {
                "title": xbmc.getInfoLabel("Player.Title"),
                "artist": xbmc.getInfoLabel("Player.Artist"),
                "album": xbmc.getInfoLabel("Player.Album"),
                "elapsed": player.getTime(),
                "duration": player.getTotalTime(),
                "paused": bool(xbmc.getCondVisibility("Player.Paused")),
                "playing": True,
            }
        except Exception:  # noqa: BLE001 - outside Kodi / player not ready
            return None

    def _load_page(self, target, page):
        if hasattr(self.data, "load"):
            return self.data.load(target, page, self._rows_per_page)
        # Compatibility with the 3.9.49 fake data adapter.
        if target is None or target == "":
            rows = list(self.data.home_rows())
        elif isinstance(target, str):
            rows = list(self.data.section_entries(target))
        else:
            rows = list(self.data.entries_for(target))
        return _page_local(rows, page, self._rows_per_page)

    def _goto_page(self, page):
        if self._closed or self._busy:
            return False
        if self._page == page:
            return False
        # Push the current page so Back returns to the page the user left,
        # not all the way to the room (focus and page both restored).
        return self._load_target(self._target, max(1, page), push=True)

    def _reload_current(self, keep_index=False):
        if self._closed or self._busy:
            return False
        # Remember the absolute content offset, not the on-screen row index:
        # the reload's render uses its own default index (1 on page 2+), which
        # is what made Refresh reset the hero to the first row (P2-4).
        offset = self._content_offset() if keep_index else 0
        ok = self._load_target(self._target, self._page, push=False)
        if ok and keep_index:
            self._restore_offset(offset)
        return ok

    def _content_offset(self):
        """Absolute 0-based index of the focused item in the whole target."""
        page = max(1, int(self._page or 1))
        rows_per_page = max(1, int(self._rows_per_page or 1))
        content = list(self._page_rows or [])
        nav = 1 if (page > 1 and content) else 0
        if content:
            content_index = max(0, min(self._current_index() - nav,
                                       len(content) - 1))
        else:
            content_index = 0
        return (page - 1) * rows_per_page + content_index

    def _restore_offset(self, offset):
        """Focus the same absolute item after a reload and repaint its hero."""
        page = max(1, int(self._page or 1))
        rows_per_page = max(1, int(self._rows_per_page or 1))
        content = list(self._page_rows or [])
        nav = 1 if (page > 1 and content) else 0
        content_index = max(0, int(offset) - (page - 1) * rows_per_page)
        if content:
            content_index = min(content_index, len(content) - 1)
        else:
            content_index = 0
        self._select_index(nav + content_index)

    # ----------------------------------------------------------------- plate
    def _start_loading(self, title, detail):
        self._show_plate("loading", title, detail, "Please wait…")
        self._loading_cancel.clear()
        self._loading_active = True
        self._loading_frame = -1
        self._loading_started = self._monotonic()
        # The first frame is painted here; later frames are advanced from the
        # task runner's poll, which runs on the caller's (GUI) thread.  No
        # control is ever touched from the worker thread (P2-5).
        self._advance_loading_frame()

    def _advance_loading_frame(self, force=False):
        if not self._loading_active or self._closed:
            return
        # Belt-and-braces for P2-5b: even if a custom runner wired this method
        # as its poll, a background thread must never call Control.setImage.
        if threading.current_thread() is not self._gui_thread:
            return
        frames = list(self._frames or [])
        head = getattr(self.view, "set_plate_head", None)
        if not frames or head is None:
            return
        elapsed = max(0.0, self._monotonic() - self._loading_started)
        index = frame_index(elapsed, len(frames), FPS)
        if not force and index == self._loading_frame:
            return
        self._loading_frame = index
        try:
            head(frames[index % len(frames)])
        except Exception:  # noqa: BLE001 - dead control is fail-soft
            self._loading_active = False

    def _on_runner_poll(self):
        """Task-runner poll hook (caller/GUI thread): animate the load plate.

        A runner shared with a background caller would otherwise invoke this
        from that caller's thread; the GUI-thread check makes the hook inert
        there instead of mutating a control (P2-5b).
        """
        if threading.current_thread() is not self._gui_thread:
            return
        if self._closed:
            return
        self._advance_loading_frame()

    def _stop_loading_animation(self):
        self._loading_active = False
        self._loading_frame = -1

    def _finish_loading(self):
        self._loading_cancel.set()
        self._loading_thread = None
        self._stop_loading_animation()
        if self._closed:
            self._plate = None
            return
        if self._plate is not None and self._plate.kind == "loading":
            self._clear_plate()

    def _show_plate(self, kind, title, detail="", hint="", retry=None):
        self._plate = _Plate(kind, title, detail, hint, retry)
        if self._closed:
            return
        setter = getattr(self.view, "set_plate", None)
        if setter is not None:
            setter(kind, title, detail, hint)
        self.view.set_status("%s · %s" % (title, detail) if detail else title)

    def _show_error(self, title, detail, retry=None):
        self._finish_loading()
        hint = "OK retry · BACK back" if retry is not None else "BACK back"
        self._show_plate("error", title, detail, hint, retry)

    def _clear_plate(self):
        if self._plate is None:
            return
        self._plate = None
        if self._closed:
            return
        clearer = getattr(self.view, "clear_plate", None)
        if clearer is not None:
            clearer()
        self.view.set_status("")

    def _click_plate(self):
        plate = self._plate
        if plate is None:
            return False
        if plate.kind == "loading":
            return False
        retry = plate.retry
        self._clear_plate()
        if retry is not None:
            return retry()
        return True

    # -------------------------------------------------------------- rendering
    def _apply_page(self, target, page_obj):
        self._target = target
        self._page = max(1, int(getattr(page_obj, "page", 1) or 1))
        self._pages = max(0, int(getattr(page_obj, "pages", 0) or 0))
        self._total = max(0, int(getattr(page_obj, "total", 0) or 0))
        self._rows_per_page = max(1, int(getattr(
            page_obj, "rows_per_page", self._rows_per_page) or self._rows_per_page))
        self._page_has_next = bool(getattr(page_obj, "has_next", False))
        self._page_rows = list(getattr(page_obj, "rows", []) or [])
        self._title = self._label_for(target)
        self._subtitle = self._subtitle_for(target, page_obj)
        self._view_kind = "list"

    def _render_page(self, index=None):
        content = list(self._page_rows)
        rows = []
        if self._page > 1:
            rows.append(self._nav_row("page_prev", "‹ PREVIOUS PAGE",
                                      self._page - 1, "PAGE %d" % (self._page - 1)))
        rows.extend(content)
        if self._page_has_next or (self._pages and self._page < self._pages):
            rows.append(self._nav_row("page_next", "NEXT PAGE ›",
                                      self._page + 1, "PAGE %d" % (self._page + 1)))
        self._rows = rows
        self.view.set_title(self._title)
        self.view.set_subtitle(self._subtitle)
        if index is None:
            index = 1 if (self._page > 1 and content) else 0
        self._set_rows(rows, index)
        if rows:
            self.view.set_hero(rows[max(0, min(index, len(rows) - 1))])
        else:
            self.view.set_hero(None)
        self._set_room_count(self._total or len(content), "ROWS")
        self._call_view("set_keyboard_mode", False)
        self._call_view("set_page_info", self._page_info())
        self.view.set_status("")
        self._call_view("set_key_hints", "OPEN", "BACK")
        self._call_view("set_live", self._playing_live)
        self._paint_footer()

    def _render(self, rows, index=0):
        """Compatibility renderer used by ``start`` and restored frames."""
        self._rows = list(rows or [])
        self.view.set_title(self._title)
        self.view.set_subtitle(self._subtitle)
        self._set_rows(self._rows, index)
        if self._rows:
            restore = index if 0 <= index < len(self._rows) else 0
            self.view.set_hero(self._rows[restore])
        else:
            self.view.set_hero(None)
        self._set_room_count(len(self._rows), "ROOMS" if self._target is None else "ROWS")
        self._call_view("set_keyboard_mode", False)
        self._call_view("set_page_info", self._page_info())
        self._call_view("set_key_hints", "OPEN", "BACK")
        self._call_view("set_live", self._playing_live)
        self._paint_footer()

    def _set_rows(self, rows, index):
        setter = self.view.set_rows
        try:
            setter(rows, index)
        except TypeError:
            setter(rows)

    def _select_index(self, index):
        if not self._rows:
            return
        index = max(0, min(int(index), len(self._rows) - 1))
        try:
            self.view.set_rows(self._rows, index)
        except Exception:  # noqa: BLE001 - a cosmetic restore
            return
        # set_rows moves focus but leaves the previous hero painted; keep both
        # in step so Refresh/rows-per-page do not show row 0's art (P2-4).
        try:
            self.view.set_hero(self._rows[index])
        except Exception:  # noqa: BLE001 - optional view port
            pass

    def _page_info(self):
        if self._pages > 1:
            return "P%d/%d" % (self._page, self._pages)
        if self._page_has_next:
            return "P%d/+" % self._page
        return ""

    def _nav_row(self, kind, label, target, fact):
        return _EntryLike(
            key="%s-%d" % (kind, target), label=label,
            subtitle="%s · %d rows per page" % (self._title, self._rows_per_page),
            kind=kind, target=str(target), fact=fact, code="PG",
            plot="Change page without leaving the list", meta=fact)

    def _set_room_count(self, count, unit):
        setter = getattr(self.view, "set_room_count", None)
        if setter is None:
            return
        try:
            setter(count, unit)
        except TypeError:
            setter(count)

    def _label_for(self, target):
        if target is None or target == "":
            return HOME_TITLE
        if isinstance(target, SearchTarget):
            return "SEARCH"
        if isinstance(target, str):
            try:
                for row in self.data.home_rows():
                    if getattr(row, "key", "") == target:
                        return row.label
            except Exception:  # noqa: BLE001 - title fallback
                pass
            return target.replace("_", " ").title()
        return getattr(target, "label", str(target))

    def _subtitle_for(self, target, page_obj):
        if target is None or target == "":
            return self._home_subtitle()
        if isinstance(target, SearchTarget):
            return _clip("“%s” · Tape packs" % target.query, 40)
        base = getattr(target, "subtitle", "") or ""
        return self._paged_subtitle(base, page_obj)

    def _home_subtitle(self):
        try:
            count = len(self.data.home_rows())
        except Exception:  # noqa: BLE001 - fixed fallback
            count = 11
        return "%d rooms · OK opens · long-press OK for actions" % count

    def _paged_subtitle(self, base, page_obj):
        total = max(0, int(getattr(page_obj, "total", 0) or 0))
        page = max(1, int(getattr(page_obj, "page", 1) or 1))
        pages = max(0, int(getattr(page_obj, "pages", 0) or 0))
        if pages > 1 and total:
            return "Page %d of %d · %s items" % (page, pages, _thousands(total))
        if getattr(page_obj, "has_next", False):
            return "Page %d · more" % page
        if base and total:
            unit = "row" if total == 1 else "rows"
            return "%s · %s %s" % (_clip(base, 26), _thousands(total), unit)
        return _clip(base, 40) if base else ""

    # ---------------------------------------------------------------- keyboard
    def _open_keyboard(self, query=""):
        if self._closed or self._busy:
            return False
        self._push_current()
        self._view_kind = "keyboard"
        self._keyboard = {"query": str(query or ""), "row": 0, "cols": {}}
        self._render_keyboard()
        return True

    def _render_keyboard(self):
        rows = self._keyboard_rows()
        try:
            selected = int(self._keyboard.get("row") or 0)
        except (TypeError, ValueError):
            selected = 0
        selected = max(0, min(selected, len(rows) - 1)) if rows else 0
        self._rows = rows
        self._title = "SEARCH"
        self._subtitle = "Tape packs · OK types · search now to run"
        self.view.set_title(self._title)
        self.view.set_subtitle(_clip(self._subtitle, 40))
        self._set_rows(rows, selected)
        self.view.set_hero(None)
        self._call_view("set_keyboard_mode", True)
        self._set_room_count(len(rows), "KEYS")
        self._call_view("set_page_info", "")
        self.view.set_status("QUERY: %s" % (self.search_query or "_"))
        self._call_view("set_key_hints", "TYPE", "BACK")
        self._call_view("set_live", self._playing_live)

    def _keyboard_rows(self):
        rows = []
        keyboard = self._keyboard or {}
        cols = keyboard.setdefault("cols", {})
        for row_index, (chars, fact) in enumerate(KEY_GROUPS):
            col = int(cols.get(row_index, 0))
            col = max(0, min(col, len(chars) - 1))
            cols[row_index] = col
            # Avoid Kodi label markup: "[B]" would render as bold, not the
            # literal bracket around the selected letter.
            shown = " ".join("\u00ab%s\u00bb" % char if index == col else char
                             for index, char in enumerate(chars))
            rows.append(_EntryLike(
                key="key-row-%d" % row_index,
                label=shown,
                subtitle="OK adds %s" % chars[col],
                kind="key", target="char:%s" % chars[col],
                action="char:%s" % chars[col], chars=list(chars),
                fact=fact, code="KEY", plot="In-window keyboard",
                meta="%s · RP-33" % fact))
        for action_index, action in enumerate(KEY_ACTIONS):
            if action == "SEARCH NOW":
                label = "SEARCH NOW"
                target = "search"
                fact = "GO"
            elif action == "CANCEL":
                label = "CANCEL"
                target = "cancel"
                fact = "BACK"
            else:
                label = action
                target = action.lower()
                fact = "KEY"
            rows.append(_EntryLike(
                key="key-action-%d" % action_index, label=label,
                subtitle="Search: %s" % (self.search_query or "empty"),
                kind="key", target=target, action=target, fact=fact, code="KEY",
                plot="In-window keyboard", meta="%s · RP-33" % fact))
        return rows

    def _selected_keyboard_row(self):
        try:
            index = int(self.view.selected_index())
        except (TypeError, ValueError, AttributeError):
            index = 0
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return None

    def _keyboard_press(self):
        if self._keyboard is None:
            return False
        row = self._selected_keyboard_row()
        if row is None:
            return False
        action = str(getattr(row, "target", ""))
        if action.startswith("char:"):
            char = action.split(":", 1)[1]
            if len(self._keyboard.get("query", "")) < KEY_LIMIT:
                self._keyboard["query"] = self._keyboard.get("query", "") + char
            self._render_keyboard()
            return True
        if action == "space":
            if len(self._keyboard.get("query", "")) < KEY_LIMIT:
                self._keyboard["query"] = self._keyboard.get("query", "") + " "
            self._render_keyboard()
            return True
        if action == "delete":
            self._keyboard["query"] = self._keyboard.get("query", "")[:-1]
            self._render_keyboard()
            return True
        if action == "clear":
            self._keyboard["query"] = ""
            self._render_keyboard()
            return True
        if action == "search":
            return self._submit_search()
        if action == "cancel":
            return self.on_back()
        return False

    def _submit_search(self):
        query = " ".join(str(self._keyboard.get("query", "")).split())
        if not query:
            self.view.set_status("Type a search first — letters, digits or SPACE.")
            return False
        self._push_current()
        return self._load_library_search(query, 1, push=False)

    # ----------------------------------------------------------------- context
    def _build_context(self, entry):
        kind = getattr(entry, "kind", "")
        actions = []
        payload = getattr(entry, "payload", None)
        if isinstance(payload, dict) and payload.get("action") in (
                ACTION_REMOVE, ACTION_RETRY, ACTION_OPEN, ACTION_CANCEL):
            mapped = str(payload.get("action"))
            labels = {
                ACTION_REMOVE: ("Remove", "DELETE", "Remove this saved row"),
                ACTION_RETRY: ("Retry", "AGAIN", "Run this room again"),
                ACTION_OPEN: ("Source link", "OPEN", "Show the source URL"),
                ACTION_CANCEL: ("Cancel download", "STOP",
                                "Stop this download"),
            }
            label, fact, plot = labels[mapped]
            actions.append({"action": "library_" + mapped, "label": label,
                            "fact": fact, "plot": plot})
        if kind in ("library_room", "library_track"):
            if kind == "library_room":
                actions.append({"action": "open", "label": "Open",
                                "fact": "OPEN", "plot": "Open this row"})
            else:
                actions.append({"action": "play", "label": "Play",
                                "fact": "PLAY", "plot": "Play this row"})
            if self._library_has_tracks():
                actions.append({"action": "play_all", "label": "Play all",
                                "fact": "QUEUE",
                                "plot": "Queue this page's playable rows"})
                actions.append({"action": "shuffle_all", "label": "Shuffle all",
                                "fact": "RANDOM",
                                "plot": "Queue this page's playable rows shuffled"})
            if isinstance(payload, dict) and (
                    payload.get("favourite_key") or payload.get("download_key")):
                actions.append({"action": "library_remove", "label": "Remove",
                                "fact": "REMOVE", "plot": "Remove this saved row"})
        if (kind in ("station", "section")
                and isinstance(getattr(entry, "action", None), dict)):
            actions.append({"action": "live", "label": "Play / stop",
                            "fact": "LIVE", "plot": "Play or stop this station"})
        if kind in ("section", "pack", "genre", "show", "rtp_index", "rtp_post",
                    "rtp_category", "feed", "folder", "hardscore_post",
                    "download_missing") and not isinstance(payload, dict):
            actions.append({"action": "open", "label": "Open",
                            "fact": "OPEN", "plot": "Open this row"})
        collection = self._collection_target(entry)
        if collection is not None:
            actions.append({"action": "play_all", "label": "Play all",
                            "fact": "QUEUE", "plot": "Queue the whole collection"})
            actions.append({"action": "shuffle_all", "label": "Shuffle all",
                            "fact": "RANDOM", "plot": "Queue the whole collection shuffled"})
        if kind in ("track", "station", "file", "external", "dnb_show", "moxser_mix"):
            actions.append({"action": "play", "label": "Play",
                            "fact": "PLAY", "plot": "Play this row"})
        if kind in ("track", "external") and getattr(entry, "downloadable", False):
            actions.append({"action": "download", "label": "Download",
                            "fact": "SAVE", "plot": "Download this file for offline playback"})
        if kind == "download_active":
            actions.append({"action": "cancel_download", "label": "Cancel download",
                            "fact": "STOP", "plot": "Stop this download"})
        if kind == "file":
            actions.append({"action": "delete_download", "label": "Delete download",
                            "fact": "DELETE", "plot": "Remove the local file and metadata"})
        if getattr(entry, "fav_key", ""):
            actions.append({"action": "remove_favourite", "label": "Remove favourite",
                            "fact": "REMOVE", "plot": "Remove this saved row"})
        elif self._can_favourite(entry):
            actions.append({"action": "favourite", "label": "Add to favourites",
                            "fact": "SAVE", "plot": "Save this row in Favourites"})
        actions.append({"action": "rows", "label": "Rows per page: %d" % self._rows_per_page,
                        "fact": "CHANGE", "plot": "Cycle 25 / 50 / 100 rows"})
        if self._is_playing():
            actions.append({"action": "stop", "label": "Stop playback",
                            "fact": "STOP", "plot": "Stop Kodi's player"})
        actions.append({"action": "refresh", "label": "Refresh",
                        "fact": "RELOAD", "plot": "Reload this list"})
        return actions

    def _action_row(self, action):
        return _EntryLike(
            key="action-%s" % action["action"], label=action["label"],
            subtitle=action.get("plot", ""), kind="action",
            target=action["action"], fact=action.get("fact", "RUN"),
            code="ACT", plot=action.get("plot", ""),
            meta="%s · ACTION" % action.get("fact", "RUN"))

    def _context_execute(self):
        entry = self._selected()
        if entry is None:
            return False
        action = str(getattr(entry, "target", ""))
        subject = self._context_subject
        self._pop()
        if subject is None:
            return False
        subject_kind = getattr(subject, "kind", "")
        if subject_kind.startswith("library_"):
            return self._library_context(action, subject)
        if subject_kind in ("station", "section") and isinstance(
                getattr(subject, "action", None), dict):
            if action == "live":
                return self._run_live_action(subject, dict(subject.action))
            if action == "favourite":
                return self._add_favourite(subject)
            if action == "refresh":
                return self._open_live_room(push=False)
            if action == "rows":
                return self._cycle_rows_per_page()
            if action == "stop":
                return self.on_stop()
            return False
        if action == "open":
            return self._load_target(subject, 1, push=True)
        if action == "play":
            track = getattr(subject, "track", None)
            if track is not None:
                return self._handoff(track)
            if getattr(subject, "kind", "") in ("dnb_show", "moxser_mix"):
                return self._resolve_and_play(subject)
            self.view.set_status("That row has no playable stream.")
            return False
        if action in ("play_all", "shuffle_all"):
            collection = self._collection_target(subject)
            return self._play_collection(collection, shuffle=(action == "shuffle_all"))
        if action == "download":
            return self._start_download(subject)
        if action == "favourite":
            return self._add_favourite(subject)
        if action == "remove_favourite":
            return self._remove_favourite(subject)
        if action == "delete_download":
            return self._delete_download(subject)
        if action == "cancel_download":
            key = str(getattr(subject, "target", ""))
            ok = False
            if hasattr(self.data, "cancel_download"):
                ok = self.data.cancel_download(key)
            self.view.set_status("Download cancelled." if ok
                                 else "That download is no longer running.")
            return True
        if action == "rows":
            return self._cycle_rows_per_page()
        if action == "stop":
            return self.on_stop()
        if action == "refresh":
            return self._reload_current(keep_index=True)
        return False

    def _library_has_tracks(self):
        screen = self._library_screen
        if screen is None:
            return False
        return any(getattr(row, "kind", "") == KIND_TRACK for row in screen.rows)

    def _library_context(self, action, subject):
        if action == "open":
            return self._open_library_room(subject)
        if action in ("play", "library_play"):
            if getattr(subject, "kind", "") == "library_track":
                return self._run_library_play(subject)
            return self._run_library_action(subject)
        if action in ("library_remove", "remove"):
            result = self._library_handlers().remove(subject)
            message = result.message
            if result.ok:
                self._invalidate_library_cache()
                reloaded = self._reload_library()
                self.view.set_status(message)
                return reloaded
            self.view.set_status(message)
            return False
        if action in ("library_cancel", "cancel_download"):
            return self._run_library_action(subject)
        if action == "library_retry":
            return self._retry_library(subject)
        if action == "library_open":
            url = str((getattr(subject, "payload", None) or {}).get("url") or "")
            self.view.set_status(
                "Source: %s" % url if url else "Read-only credit — Back returns.")
            return False
        if action == "rows":
            return self._cycle_rows_per_page()
        if action == "stop":
            return self.on_stop()
        if action == "favourite" or action == "library_favourite":
            result = self._library_handlers().favourite(subject)
            self.view.set_status(result.message)
            return bool(result.ok)
        if action == "refresh":
            return self._reload_library()
        if action in ("play_all", "shuffle_all"):
            screen = self._library_screen
            if screen is None:
                return False
            shuffle = action == "shuffle_all"
            handlers = self._library_handlers()
            result = (handlers.shuffle(screen) if shuffle
                      else handlers.play_all(screen))
            return self._queue_library(result, shuffle)
        return False

    def _queue_library(self, result, shuffle=False):
        tracks = list(getattr(result, "tracks", ()) or ())
        if not tracks:
            self.view.set_status(getattr(result, "message", "") or
                                 "Nothing to play on this page.")
            return False
        try:
            self.playback.play_collection(tracks, shuffle=shuffle)
        except Exception as exc:  # noqa: BLE001 - quiet failure
            self.view.set_status("Could not queue those tracks — see the log.")
            self._log("library play_all failed: %s" % exc)
            return False
        self._clear_live_latch()
        self._handed_off = True
        self._playing_live = False
        self._call_view("set_live", False)
        message = getattr(result, "message", "") or "Queued %d tracks" % len(tracks)
        self.view.set_now_playing(message)
        self.view.set_status("%s · Back leaves audio playing" % message)
        self._mark_playback_started()
        self._paint_footer(nowplaying.playing(
            getattr(tracks[0], "title", "") or "Untitled",
            album="%d tracks" % len(tracks)))
        return True

    def _cycle_rows_per_page(self):
        sizes = list(PAGE_SIZES)
        try:
            index = sizes.index(self._rows_per_page)
        except ValueError:
            index = 0
        new_rows = sizes[(index + 1) % len(sizes)]
        # Absolute item offset before the page size changes (the on-screen row
        # index includes the Previous-page row on page 2+).
        offset = (self._content_offset() if self._target is not None
                  else (max(1, self._page) - 1) * self._rows_per_page
                  + self._current_index())
        self._rows_per_page = new_rows
        self._page_size_explicit = True
        try:
            self.data.rows_per_page = new_rows
        except Exception:  # noqa: BLE001 - read-only test double
            pass
        # Library rooms compute their own page size; give them the user's
        # choice instead of letting their next load overwrite it (P2-2).
        setter = getattr(self._library_ui, "set_page_size", None)
        if callable(setter):
            try:
                setter(new_rows)
            except Exception:  # noqa: BLE001 - fake may be read-only
                pass
        self.view.set_status("Rows per page: %d" % new_rows)
        target = self._target
        if target is None:
            return True
        new_page = int(offset // new_rows) + 1
        if target == "live":
            ok = self._open_live_room(push=False)
        else:
            ok = self._load_target(target, new_page, push=False)
        # The reload paints its own default focus; restore the item that was
        # under the cursor and its hero at the new page size (P2-4).
        if ok:
            self._restore_offset(offset)
        # The reload repaints and clears the status; keep the user's choice
        # visible after it (P2-1/P2-3).
        self.view.set_status("Rows per page: %d" % new_rows)
        return ok

    # ------------------------------------------------------------------ actions
    def _start_download(self, entry):
        if not hasattr(self.data, "start_download"):
            self.view.set_status("Downloads are not available in this build.")
            return False
        try:
            ok, message = self.data.start_download(entry)
        except Exception as exc:  # noqa: BLE001 - queue failure is a status line
            ok, message = False, "Could not start the download (%s)." % exc
        self.view.set_status(message)
        return bool(ok)

    def _add_favourite(self, entry):
        if not hasattr(self.data, "add_favourite"):
            self.view.set_status("Favourites are not available in this build.")
            return False
        try:
            ok, message = self.data.add_favourite(entry)
        except Exception as exc:  # noqa: BLE001 - profile may be read-only
            ok, message = False, "Could not save that favourite (%s)." % exc
        self.view.set_status(message)
        self._trace("favourite %s: %s" % (getattr(entry, "label", ""), message))
        return bool(ok)

    def _remove_favourite(self, entry):
        if not hasattr(self.data, "remove_favourite"):
            return False
        key = getattr(entry, "fav_key", "")
        try:
            ok = self.data.remove_favourite(key)
        except Exception:  # noqa: BLE001 - profile may be read-only
            ok = False
        message = ("Removed from favourites" if ok
                   else "Could not remove that favourite.")
        self.view.set_status(message)
        if ok and self._target in ("favourites", ROUTE_FAVOURITES):
            self._invalidate_library_cache()
            self._reload_current(keep_index=False)
            self.view.set_status(message)
        return bool(ok)

    def _delete_download(self, entry):
        if not hasattr(self.data, "delete_download"):
            return False
        key = getattr(entry, "fav_key", "") or getattr(entry, "target", "")
        try:
            ok = self.data.delete_download(key)
        except Exception:  # noqa: BLE001 - file/profile unavailable
            ok = False
        message = ("Download deleted" if ok
                   else "That download was not found.")
        self.view.set_status(message)
        if ok and self._target in ("downloads", ROUTE_DOWNLOADS):
            self._invalidate_library_cache()
            self._reload_current(keep_index=False)
            self.view.set_status(message)
        return bool(ok)

    # ------------------------------------------------------------------ helpers
    def _collection_target(self, entry):
        """The folder whose complete track list Play all should queue."""
        if entry is None:
            return None
        kind = getattr(entry, "kind", "")
        if kind in ("pack", "genre", "show", "rtp_post", "feed",
                    "hardscore_post"):
            return entry
        if kind in ("track", "file", "external"):
            target = self._target
            if target is None or isinstance(target, (str, SearchTarget)):
                return None
            return target
        return None

    def _can_favourite(self, entry):
        if not hasattr(self.data, "favourite_payload"):
            return getattr(entry, "kind", "") in (
                "pack", "show", "rtp_post", "dnb_show", "track", "station")
        try:
            return self.data.favourite_payload(entry) is not None
        except Exception:  # noqa: BLE001 - do not offer a broken action
            return False

    def _is_playing(self):
        try:
            player = getattr(self.playback, "is_playing", None)
            if player is not None:
                return bool(player())
        except Exception:  # noqa: BLE001 - player unavailable
            pass
        return False

    # ------------------------------------------------------------------- stack
    def _push_current(self):
        if self._view_kind not in ("list", "keyboard"):
            return
        self._stack.append(_Frame(
            kind=self._view_kind,
            target=self._target,
            title=self._title,
            subtitle=self._subtitle,
            page=self._page,
            pages=self._pages,
            total=self._total,
            rows=list(self._rows),
            index=self._current_index(),
            keyboard=dict(self._keyboard) if self._keyboard is not None else None,
            screen=self._library_screen if self._view_kind == "list" else None))

    def _pop(self):
        if self._stack:
            self._restore(self._stack.pop())
            return True
        return False

    def _restore(self, frame):
        self._target = frame.target
        self._title = frame.title
        self._subtitle = frame.subtitle
        self._page = frame.page
        self._pages = frame.pages
        self._total = frame.total
        self._page_rows = list(frame.rows)
        self._rows = list(frame.rows)
        self._keyboard = frame.keyboard
        self._library_screen = frame.screen
        self._view_kind = frame.kind
        if frame.kind == "keyboard" and self._keyboard is not None:
            self._render_keyboard()
            return
        self._page_has_next = False
        self._render(frame.rows, frame.index)

    # ------------------------------------------------------------------- input
    def _selected(self):
        try:
            index = int(self.view.selected_index())
        except (TypeError, ValueError, AttributeError):
            index = 0
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return None

    def _current_index(self):
        try:
            return int(self.view.selected_index())
        except (TypeError, ValueError, AttributeError):
            return 0

    def _call_view(self, name, *args):
        function = getattr(self.view, name, None)
        if function is None:
            return
        try:
            function(*args)
        except TypeError:
            try:
                function(*args[:1])
            except Exception:  # noqa: BLE001 - optional view port
                pass
        except Exception:  # noqa: BLE001 - optional view port
            pass

    def _sleep_ms(self, milliseconds):
        if self._sleep is None:
            import xbmc

            xbmc.sleep(milliseconds)
        else:
            self._sleep(milliseconds)

    def _log(self, message):
        try:
            self._logger(message)
        except Exception:  # noqa: BLE001 - logging never breaks the screen
            pass

    def _trace(self, message):
        tracer = getattr(self._logger, "trace", None)
        if tracer is not None:
            try:
                tracer(message)
                return
            except Exception:  # noqa: BLE001 - logging never breaks the screen
                pass
        self._log(message)

    @staticmethod
    def _default_log(message):
        try:
            import xbmc

            xbmc.log("[script.raveplayer.ui] %s" % message, level=xbmc.LOGWARNING)
        except Exception:
            pass


class _LiveHandoff(object):
    """Playback port for ``LiveRadio``: every play goes through the controller."""

    def __init__(self, controller):
        self.controller = controller

    def play(self, track):
        if not self.controller._handoff(track):
            raise RuntimeError("live handoff failed")
        return True

    def stop(self):
        return self.controller._stop_player()


class _EntryLike(object):
    """Minimal row object for navigation/keyboard/action rows."""

    __slots__ = ("key", "label", "subtitle", "art", "kind", "source", "target",
                 "track", "hero", "fact", "code", "plot", "meta", "year",
                 "genre", "duration", "download_source", "downloadable",
                 "fav_key", "action", "chars", "payload")

    def __init__(self, key="", label="", subtitle="", art="", kind="",
                 source="", target="", track=None, hero="", fact="", code="",
                 plot="", meta="", year="", genre="", duration="",
                 download_source="", downloadable=False, fav_key="",
                 action="", chars=None, payload=None):
        self.key = key
        self.label = label
        self.subtitle = subtitle
        self.art = art
        self.kind = kind
        self.source = source
        self.target = target
        self.track = track
        self.hero = hero
        self.fact = fact
        self.code = code
        self.plot = plot
        self.meta = meta
        self.year = year
        self.genre = genre
        self.duration = duration
        self.download_source = download_source
        self.downloadable = downloadable
        self.fav_key = fav_key
        self.action = action
        self.chars = list(chars or [])
        self.payload = dict(payload) if isinstance(payload, dict) else None


def _clip(text, limit):
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[:max(1, limit - 1)].rstrip() + "…"


def _thousands(value):
    try:
        return "{:,}".format(int(value))
    except (TypeError, ValueError):
        return str(value)
