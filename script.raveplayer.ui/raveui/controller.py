# -*- coding: utf-8 -*-
"""Rave Screen controller — UI behaviour with no Kodi imports.

The window class in :mod:`raveui.window` is a thin adapter over this controller;
tests drive the controller with a fake view, a fake data source and a fake
playback service. Every state transition is explicit:

* home -> section -> (pack/genre/show) -> tracks -> playback
* Back pops one level, and Back at home closes the window exactly once
* a surprise picks once, animates once, and hands off playback at most once
"""

from dataclasses import dataclass

import threading

from .animation import FPS, MIN_DURATION, SpinnerAnimator
from .tasks import TaskCancelled, TaskTimeout, ThreadTaskRunner

HOME_TITLE = "RAVE SCREEN"
# Label 23 is 530 px wide at 720p; the previous sentence clipped ("...one rando").
HOME_SUBTITLE = "OK opens a source · SPINNING SURPRISE picks one"


@dataclass
class _ViewState:
    title: str
    subtitle: str
    rows: list


class RaveScreenController(object):
    def __init__(self, view, data, playback, *, animator_factory=None,
                 task_runner=None, sleep=None, clock=None, monitor=None,
                 frames=None, logger=None):
        self.view = view
        self.data = data
        self.playback = playback
        self._animator_factory = animator_factory or SpinnerAnimator
        self._sleep = sleep
        self._clock = clock
        self._logger = logger or self._default_log
        self._task_runner = task_runner or ThreadTaskRunner(
            sleep=self._sleep_ms, clock=clock, monitor=monitor,
            # Back closes the window while a 15 s source load or random pick is
            # still polling; stop waiting immediately instead of keeping the
            # script (and the closed window) alive until the worker finishes.
            cancelled=lambda: self._closed)
        self._frames = list(frames) if frames is not None else list(
            data.spinner_frames() if hasattr(data, "spinner_frames") else [])
        self._title = HOME_TITLE
        self._subtitle = HOME_SUBTITLE
        self._rows = []
        self._stack = []
        self._closed = False
        self._busy = False
        self._surprising = False
        self._handed_off = False

    # ------------------------------------------------------------- lifecycle
    def start(self):
        rows = list(self.data.home_rows())
        self._title = HOME_TITLE
        self._subtitle = HOME_SUBTITLE
        self._render(rows)
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

    def on_focus(self):
        if self._closed:
            return None
        entry = self._selected()
        if entry is not None:
            self.view.set_hero(entry)
        return entry

    def on_click(self):
        if self._closed:
            return False
        if self._handed_off:
            self.view.set_status("Already playing — press Back to exit.")
            return False
        if self._busy:
            return False
        entry = self._selected()
        if entry is None:
            self.view.set_status("Nothing selected.")
            return False
        if entry.kind == "section":
            return self._open_section(entry)
        if entry.kind == "surprise":
            # The GUI thread is inside this Python call; running the 1.2 s
            # frame loop here blocks repaint and the splash is never drawn.
            # Hand it to a worker so Kodi can paint the spinner, then return.
            if self._closed or self._busy or self._handed_off:
                return False
            thread = threading.Thread(target=self.surprise, name="rave-surprise",
                                      daemon=True)
            thread.start()
            return True
        if entry.track is not None:
            return self._handoff(entry.track)
        if entry.kind in ("pack", "genre", "show"):
            return self._open_children(entry)
        self.view.set_status("Nothing to play on that row.")
        return False

    def shutdown(self):
        """Mark closed without touching the window (called by the adapter)."""
        self._closed = True

    def on_back(self):
        """Pop a level; return True when the caller must close the window."""
        if self._closed:
            return True
        # Once playback has been handed off, Back means "leave the screen" from
        # any depth: the footer says so, and it avoids a Back that only pops a
        # list while audio keeps playing behind a window the user wanted closed.
        if self._busy or self._handed_off:
            self._closed = True
            self.view.set_status("Closing…")
            self.view.close()
            return True
        if self._stack:
            state = self._stack.pop()
            self._title = state.title
            self._subtitle = state.subtitle
            self._render(state.rows)
            return False
        self._closed = True
        self.view.close()
        return True

    # ------------------------------------------------------------- surprises
    def surprise(self):
        """Pick one pack + track, spin for >=1.2s, then hand off playback."""
        if self._closed or self._busy or self._handed_off:
            return False
        self._busy = True
        self._surprising = True
        self.view.set_spinner_visible(True)
        if self._frames:
            self.view.set_spinner_image(self._frames[0])
        self.view.set_spinner_label("RANDOM PACK · RP-02")
        self.view.set_status("Spinning for one random pack and track…")
        try:
            pick = self._task_runner.run(self.data.random_pick)
            if self._closed:
                return False
            if pick is None:
                self.view.set_status("No random pack found — try again.")
                return False
            self.view.set_spinner_label("RANDOM PACK · RP-02")
            if not self._frames:
                self.view.set_status("Spinning art unavailable — no playback.")
                return False
            animator = self._animator_factory(
                frames=self._frames,
                set_image=self.view.set_spinner_image,
                duration=MIN_DURATION,
                fps=FPS,
                sleep=self._sleep_ms,
                clock=self._clock,
                cancelled=lambda: self._closed,
            )
            try:
                completed = animator.run()
            except Exception as exc:  # noqa: BLE001 - dead control / bad frame
                completed = False
                self._log("surprise animation failed: %s" % exc)
            if self._closed:
                return False
            if not completed:
                self.view.set_status("Surprise animation unavailable — no playback.")
                return False
            return self._handoff(pick)
        except TaskCancelled:
            # The user pressed Back; the window is closing and the late result
            # is irrelevant. Never paint a status line on a closed window.
            return False
        except TaskTimeout as exc:
            self.view.set_status("Random pick timed out — try again.")
            self._log("surprise pick timeout: %s" % exc)
            return False
        except Exception as exc:  # noqa: BLE001 - fail soft, no traceback to Kodi
            self.view.set_status("Could not pick a random pack — see the log.")
            self._log("surprise pick failed: %s" % exc)
            return False
        finally:
            self.view.set_spinner_visible(False)
            self._surprising = False
            self._busy = False

    # -------------------------------------------------------------- internals
    def _open_section(self, entry):
        return self._load_and_push(
            entry,
            lambda: self.data.section_entries(entry.key),
            entry.label,
            entry.subtitle)

    def _open_children(self, entry):
        return self._load_and_push(
            entry,
            lambda: self.data.entries_for(entry),
            entry.label,
            entry.subtitle)

    def _load_and_push(self, entry, loader, title, subtitle):
        self._busy = True
        self.view.set_status("Loading %s…" % entry.label)
        try:
            rows = self._task_runner.run(loader)
        except TaskCancelled:
            return False
        except TaskTimeout as exc:
            self.view.set_status("Timed out loading %s — try again." % entry.label)
            self._log("load timeout for %s: %s" % (entry.key, exc))
            return False
        except Exception as exc:  # noqa: BLE001 - never crash the window
            self.view.set_status("Could not load %s — see the log." % entry.label)
            self._log("load failed for %s: %s" % (entry.key, exc))
            return False
        finally:
            self._busy = False
        if self._closed:
            return False
        rows = list(rows or [])
        if not rows:
            self.view.set_status("Nothing in %s right now." % entry.label)
            return False
        self._stack.append(_ViewState(self._title, self._subtitle, self._rows))
        self._title = title
        self._subtitle = subtitle
        self._render(rows)
        return True

    def _handoff(self, track):
        if self._closed or self._handed_off:
            return False
        self._handed_off = True
        try:
            result = self.playback.play(track)
        except Exception as exc:  # noqa: BLE001 - bad URL / Kodi API failure
            self._handed_off = False
            self.view.set_status("Could not start playback — see the log.")
            self._log("playback handoff failed: %s" % exc)
            return False
        text = getattr(result, "text", None) or "Now playing: %s" % track.title
        self.view.set_now_playing(text)
        self.view.set_status("Playing — press Back to exit.")
        try:
            self.view.notify(text)
        except Exception:  # noqa: BLE001 - notification is decorative
            pass
        return True

    def _render(self, rows):
        self._rows = list(rows or [])
        self.view.set_title(self._title)
        self.view.set_subtitle(self._subtitle)
        self.view.set_rows(self._rows)
        if self._rows:
            self.view.set_hero(self._rows[0])
        else:
            self.view.set_hero(None)

    def _selected(self):
        try:
            index = int(self.view.selected_index())
        except (TypeError, ValueError, AttributeError):
            index = 0
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return None

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

    @staticmethod
    def _default_log(message):
        try:
            import xbmc

            xbmc.log("[script.raveplayer.ui] %s" % message, level=xbmc.LOGWARNING)
        except Exception:
            pass
