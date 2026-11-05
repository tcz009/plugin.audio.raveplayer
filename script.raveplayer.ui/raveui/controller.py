# -*- coding: utf-8 -*-
"""Rave Screen controller — the whole app's behaviour, with no Kodi imports.

The window class in :mod:`raveui.window` is a thin adapter over this controller;
tests drive it with a fake view, data source, download queue and playback
service.  Every screen is a state of the same window:

* home -> room -> folder -> track list -> playback
* a list can be paged (25/50/100) with explicit previous/next rows
* search is an in-window keyboard, results are paged, Back restores the keys
* a context menu (long-press OK) carries Play all / Shuffle / Download /
  Favourite / rows-per-page / Stop / Refresh
* loading, empty and error states are painted plates, not modal dialogs
* Spinning Surprise is one bounded pick, one >=1.2 s reveal and one playback
* leaving the window never stops audio: Kodi owns the player (one policy)

The controller never opens a modal dialog, never calls ``xbmcgui`` and never
raises into Kodi: every failure becomes a quiet status line or a plate.
"""

import threading
from dataclasses import dataclass

from .animation import FPS, MIN_DURATION, SpinnerAnimator
from .data import (DEFAULT_PAGE_SIZE, PAGE_SIZES, SEARCH_SCOPES, SearchTarget,
                   _page_local)
from .tasks import TaskCancelled, TaskTimeout, ThreadTaskRunner

HOME_TITLE = "RAVE SCREEN"
HOME_SUBTITLE = "11 rooms · OK opens · long-press OK for actions"
KEY_LIMIT = 48

KEY_GROUPS = (
    ("A B C D E F G H I".split(), "LETTERS"),
    ("J K L M N O P Q R".split(), "LETTERS"),
    ("S T U V W X Y Z".split(), "LETTERS"),
    ("0 1 2 3 4 5 6 7 8 9".split(), "DIGITS"),
)
KEY_ACTIONS = ("SPACE", "DELETE", "CLEAR", "SCOPE", "SEARCH NOW", "CANCEL")


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
                 frames=None, logger=None, download_queue=None):
        self.view = view
        self.data = data
        self.playback = playback
        self._animator_factory = animator_factory or SpinnerAnimator
        self._sleep = sleep
        self._clock = clock
        self._logger = logger or self._default_log
        self._task_runner = task_runner or ThreadTaskRunner(
            sleep=self._sleep_ms, clock=clock, monitor=monitor,
            timeout=45.0, cancelled=lambda: self._closed)
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
        self._plate = None
        self._context_actions = []
        self._context_subject = None
        self._keyboard = None
        self._surprise_cancel = threading.Event()
        self._loading_cancel = threading.Event()
        self._loading_thread = None
        self._download_queue = download_queue
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
        self._trace("home rows=%d" % len(rows))
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
        self._surprise_cancel.set()
        self._loading_cancel.set()

    # ------------------------------------------------------------------ focus
    def on_focus(self):
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
        return entry

    def on_horizontal(self, delta):
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
        if getattr(row, "action", "") == "scope":
            self._cycle_scope(1 if delta > 0 else -1)
            self._render_keyboard()
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
        if self._closed:
            return True
        if self._plate is not None:
            if self._plate.kind == "loading" or self._busy:
                return False
            self._clear_plate()
            return False
        if self._busy or self._surprising:
            if self._surprising:
                self._cancel_surprise()
                return False
            self._closed = True
            self.view.set_status("Closing…")
            self.view.close()
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
        self.view.set_status("Closing — audio continues.")
        self.view.close()
        return True

    def on_context(self):
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
        if self._closed:
            return False
        stopped = False
        try:
            stopped = bool(self.playback.stop())
        except Exception:  # noqa: BLE001 - player unavailable
            stopped = False
        self._playing_live = False
        self._call_view("set_live", False)
        self.view.set_status("Stopped." if stopped else "Nothing playing.")
        return stopped

    # ------------------------------------------------------------- surprises
    def _start_surprise(self):
        if self._closed or self._busy or self._surprising:
            return False
        if self._plate is not None:
            self._clear_plate()
        self._busy = True
        self._surprising = True
        self._surprise_cancel.clear()
        self.view.set_spinner_visible(True)
        if self._frames:
            self.view.set_spinner_image(self._frames[0])
        self.view.set_spinner_label("RANDOM PACK · RP-02")
        self.view.set_status("Spinning for one random pack and track…")
        worker = threading.Thread(target=self.surprise, args=(True,),
                                  name="rave-surprise", daemon=True)
        worker.start()
        return True

    def surprise(self, prepared=False):
        """Pick one pack + track, spin for >=1.2s, then hand off once."""
        if self._closed:
            return False
        if not prepared:
            if not self._start_surprise():
                return False
            return True
        try:
            pick = self._task_runner.run(self.data.random_pick)
            if self._closed or self._surprise_cancel.is_set():
                return False
            if pick is None:
                reason = getattr(self.data, "last_surprise_reason", "") or \
                    "the Archive returned no playable pack"
                self._surprise_failed("NO PACK FOUND",
                                      "The random pick found nothing. %s" % reason,
                                      retry=True)
                return False
            self.view.set_spinner_label("RANDOM PACK · RP-02")
            if not self._frames:
                self._surprise_failed("ART UNAVAILABLE",
                                      "The spinning-head frames are missing; "
                                      "playback was not started.", retry=False)
                return False
            animator = self._animator_factory(
                frames=self._frames,
                set_image=self.view.set_spinner_image,
                duration=MIN_DURATION,
                fps=FPS,
                sleep=self._sleep_ms,
                clock=self._clock,
                cancelled=lambda: self._closed or self._surprise_cancel.is_set(),
            )
            try:
                completed = animator.run()
            except Exception as exc:  # noqa: BLE001 - dead control / bad frame
                completed = False
                self._log("surprise animation failed: %s" % exc)
            if self._closed or self._surprise_cancel.is_set():
                return False
            if not completed:
                self._surprise_failed("REVEAL FAILED",
                                      "The spin could not finish; playback was "
                                      "not started.", retry=True)
                return False
            return self._handoff(pick)
        except TaskCancelled:
            return False
        except TaskTimeout as exc:
            self._surprise_failed("PICK TIMED OUT",
                                  "The random pick took too long. Try again.",
                                  retry=True)
            self._log("surprise pick timeout: %s" % exc)
            return False
        except Exception as exc:  # noqa: BLE001 - fail soft, no traceback to Kodi
            self._surprise_failed("SURPRISE FAILED",
                                  "Could not pick a random pack: %s" % exc,
                                  retry=True)
            self._log("surprise pick failed: %s" % exc)
            return False
        finally:
            self._hide_splash()
            self._surprising = False
            self._busy = False

    def _surprise_failed(self, title, detail, retry=True):
        self._hide_splash()
        self._show_plate("error", title, detail, "OK retry · BACK back",
                         retry=self._start_surprise if retry else None)

    def _cancel_surprise(self):
        self._surprise_cancel.set()
        self._hide_splash()
        self._surprising = False
        self._busy = False
        self.view.set_status("Surprise cancelled — no playback.")

    def _hide_splash(self):
        try:
            self.view.set_spinner_visible(False)
        except Exception:  # noqa: BLE001 - window already gone
            pass

    # --------------------------------------------------------------- playback
    def _handoff(self, track, live=None):
        if self._closed:
            return False
        is_live = bool(getattr(track, "live", False)) if live is None else bool(live)
        try:
            result = self.playback.play(track)
        except Exception as exc:  # noqa: BLE001 - bad URL / Kodi API failure
            self.view.set_status("Could not start playback — see the log.")
            self._log("playback handoff failed: %s" % exc)
            return False
        self._handed_off = True
        self._playing_live = is_live
        self._call_view("set_live", is_live)
        text = getattr(result, "text", None) or "Now playing: %s" % track.title
        self.view.set_now_playing(text)
        self.view.set_status("%s · Back leaves audio playing" % text)
        self._trace("play %s live=%s" % (getattr(track, "url", ""), is_live))
        return True

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
                             "The source took too long to list. Try again.")
            return False
        except Exception as exc:  # noqa: BLE001 - never crash the window
            self._show_error("COLLECTION FAILED",
                             "Could not read the collection: %s" % exc)
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
        self._handed_off = True
        self._playing_live = False
        self._call_view("set_live", False)
        text = getattr(result, "text", None) or "Queued %d tracks" % len(tracks)
        self.view.set_now_playing(text)
        self.view.set_status("%s · Back leaves audio playing" % text)
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
                             "That source took too long to resolve. Try again.")
            return False
        except Exception as exc:  # noqa: BLE001 - quiet failure
            self._show_error("SOURCE FAILED", "Could not resolve that set: %s" % exc)
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
    def _load_target(self, target, page=1, push=True):
        if self._closed or self._busy:
            return False
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
        if push:
            self._push_current()
        self._apply_page(target, result)
        self._render_page(index=None)
        self._trace("loaded %r page=%s/%s rows=%s total=%s" %
                    (target, self._page, self._pages, len(self._rows), self._total))
        return True

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
        index = self._current_index() if keep_index else 0
        ok = self._load_target(self._target, self._page, push=False)
        if ok and keep_index:
            self._select_index(index)
        return ok

    # ----------------------------------------------------------------- plate
    def _start_loading(self, title, detail):
        self._show_plate("loading", title, detail, "Please wait…")
        self._loading_cancel.clear()
        frames = list(self._frames or [])
        head = getattr(self.view, "set_plate_head", None)
        if not frames or head is None:
            return
        def spin():
            index = 0
            while not self._loading_cancel.is_set() and not self._closed:
                try:
                    head(frames[index % len(frames)])
                except Exception:  # noqa: BLE001 - dead control is fail-soft
                    return
                index += 1
                if self._sleep is not None:
                    self._sleep(120)
                else:
                    try:
                        import xbmc
                        xbmc.sleep(120)
                    except Exception:
                        return
        self._loading_thread = threading.Thread(target=spin, name="rave-loading",
                                                daemon=True)
        self._loading_thread.start()

    def _finish_loading(self):
        self._loading_cancel.set()
        self._loading_thread = None
        if self._plate is not None and self._plate.kind == "loading":
            self._clear_plate()

    def _show_plate(self, kind, title, detail="", hint="", retry=None):
        self._plate = _Plate(kind, title, detail, hint, retry)
        setter = getattr(self.view, "set_plate", None)
        if setter is not None:
            setter(kind, title, detail, hint)
        self.view.set_status("%s · %s" % (title, detail) if detail else title)

    def _show_error(self, title, detail, retry=None):
        self._finish_loading()
        self._show_plate("error", title, detail, "OK retry · BACK back", retry)

    def _clear_plate(self):
        if self._plate is None:
            return
        self._plate = None
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

    def _set_rows(self, rows, index):
        setter = self.view.set_rows
        try:
            setter(rows, index)
        except TypeError:
            setter(rows)

    def _select_index(self, index):
        try:
            self.view.set_rows(self._rows, max(0, min(int(index), len(self._rows) - 1)))
        except Exception:  # noqa: BLE001 - a cosmetic restore
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
            scope = dict((key, label) for key, label, _p in SEARCH_SCOPES).get(
                target.scope, "Tape packs")
            total = max(0, int(getattr(page_obj, "total", 0) or 0))
            page = max(1, int(getattr(page_obj, "page", 1) or 1))
            pages = max(0, int(getattr(page_obj, "pages", 0) or 0))
            if pages > 1 and total:
                return _clip("“%s” · %s · p%d/%d" % (
                    target.query, scope, page, pages), 40)
            return _clip("“%s” · %s · %s results" % (
                target.query, scope, _thousands(total)), 40)
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
    def _open_keyboard(self, query="", scope="archive"):
        if self._closed or self._busy:
            return False
        self._push_current()
        self._view_kind = "keyboard"
        self._keyboard = {"query": str(query or ""), "scope": scope,
                          "row": 0, "cols": {}}
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
        scope_label = dict((key, label) for key, label, _p in SEARCH_SCOPES).get(
            (self._keyboard or {}).get("scope", "archive"), "Tape packs")
        self._subtitle = "Scope: %s · OK types · long-press OK actions" % scope_label
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
            if action == "SCOPE":
                scope_label = dict(
                    (key, label) for key, label, _p in SEARCH_SCOPES).get(
                        (keyboard.get("scope") or "archive"), "Tape packs")
                label = "SCOPE: %s  ›" % scope_label
                target = "scope"
                fact = "CHANGE"
            elif action == "SEARCH NOW":
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
        if action == "scope":
            self._cycle_scope(1)
            self._render_keyboard()
            return True
        if action == "search":
            return self._submit_search()
        if action == "cancel":
            return self.on_back()
        return False

    def _cycle_scope(self, delta):
        if self._keyboard is None:
            return
        keys = [key for key, _label, _plot in SEARCH_SCOPES]
        try:
            index = keys.index(self._keyboard.get("scope", "archive"))
        except ValueError:
            index = 0
        self._keyboard["scope"] = keys[(index + delta) % len(keys)]

    def _submit_search(self):
        query = " ".join(str(self._keyboard.get("query", "")).split())
        if not query:
            self.view.set_status("Type a search first — letters, digits or SPACE.")
            return False
        self._push_current()
        target = SearchTarget(query, self._keyboard.get("scope", "archive"))
        return self._load_target(target, 1, push=False)

    # ----------------------------------------------------------------- context
    def _build_context(self, entry):
        kind = getattr(entry, "kind", "")
        actions = []
        if kind in ("section", "pack", "genre", "show", "rtp_index", "rtp_post",
                    "rtp_category", "feed", "folder", "hardscore_post",
                    "live_genre", "download_missing"):
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

    def _cycle_rows_per_page(self):
        sizes = list(PAGE_SIZES)
        try:
            index = sizes.index(self._rows_per_page)
        except ValueError:
            index = 0
        new_rows = sizes[(index + 1) % len(sizes)]
        offset = (max(1, self._page) - 1) * self._rows_per_page + self._current_index()
        self._rows_per_page = new_rows
        try:
            self.data.rows_per_page = new_rows
        except Exception:  # noqa: BLE001 - read-only test double
            pass
        self.view.set_status("Rows per page: %d" % new_rows)
        if self._target is None:
            return True
        new_page = int(offset // new_rows) + 1
        return self._load_target(self._target, new_page, push=False)

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
        self.view.set_status("Removed from favourites" if ok
                             else "Could not remove that favourite.")
        if ok and self._target == "favourites":
            self._reload_current(keep_index=False)
        return bool(ok)

    def _delete_download(self, entry):
        if not hasattr(self.data, "delete_download"):
            return False
        key = getattr(entry, "fav_key", "") or getattr(entry, "target", "")
        try:
            ok = self.data.delete_download(key)
        except Exception:  # noqa: BLE001 - file/profile unavailable
            ok = False
        self.view.set_status("Download deleted" if ok else "That download was not found.")
        if ok and self._target == "downloads":
            self._reload_current(keep_index=False)
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
            keyboard=dict(self._keyboard) if self._keyboard is not None else None))

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


class _EntryLike(object):
    """Minimal row object for navigation/keyboard/action rows."""

    __slots__ = ("key", "label", "subtitle", "art", "kind", "source", "target",
                 "track", "hero", "fact", "code", "plot", "meta", "year",
                 "genre", "duration", "download_source", "downloadable",
                 "fav_key", "action", "chars")

    def __init__(self, key="", label="", subtitle="", art="", kind="",
                 source="", target="", track=None, hero="", fact="", code="",
                 plot="", meta="", year="", genre="", duration="",
                 download_source="", downloadable=False, fav_key="",
                 action="", chars=None):
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
