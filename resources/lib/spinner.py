# -*- coding: utf-8 -*-
"""Prototype spinning-head download overlay (3.9.19).

A small non-modal ``WindowXML`` overlay shows the Rave Player head as 10
pre-rendered 256px frames (~10 fps), with progress/filename/size/remaining and
a cancel hint.  It is opt-in via the ``spinner_overlay`` setting and falls back
to the existing ``DialogProgress`` if the window cannot be created.

The window is updated from the download loop (``downloads.download`` progress
callback); there is no separate animation timer, so slow chunks simply advance
the frame on the next update.  Everything is best-effort: failures never stop
the download.
"""

import functools
import os
import threading
import time

import xbmc
import xbmcgui

from . import kodi

FRAME_COUNT = 10
FPS = 10
FRAME_SIZE = 256
FRAME_DIR = os.path.join("resources", "art", "spinner")
WINDOW_XML = "raveplayer-spinner.xml"
SKIN_DIR = os.path.join("resources", "skins", "Default", "720p")
CONTROL_HEAD = 100
CONTROL_FILENAME = 101
CONTROL_PERCENT = 102
CONTROL_SIZE = 103
CONTROL_REMAINING = 104
CONTROL_HINT = 105
CONTROL_PROGRESS = 106
CONTROL_CANCEL = 107
TUNING_THRESHOLD = 0.4
TUNING_TIMEOUT = 25.0
SURPRISE_XML = "raveplayer-surprise.xml"
SURPRISE_DURATION = 1.2
SURPRISE_FPS = 10
CONTROL_SURPRISE_BG = 99
CONTROL_SURPRISE_HEAD = 100
CONTROL_SURPRISE_TITLE = 101
CONTROL_SURPRISE_SUB = 102
CONTROL_SURPRISE_CODE = 103
CONTROL_SURPRISE_HINT = 104


def frames_dir(addon_path=None):
    root = addon_path or kodi.ADDON_PATH
    return os.path.join(root, FRAME_DIR)


@functools.lru_cache(maxsize=8)
def frame_paths(size=FRAME_SIZE, addon_path=None):
    root = frames_dir(addon_path)
    return tuple(os.path.join(root, "head-%d-%02d.png" % (size, index))
                 for index in range(FRAME_COUNT))


def frame_index(elapsed):
    try:
        elapsed = max(0.0, float(elapsed))
    except (TypeError, ValueError):
        elapsed = 0.0
    return int(elapsed * FPS) % FRAME_COUNT


def format_bytes(value):
    try:
        value = max(0, int(value or 0))
    except (TypeError, ValueError):
        value = 0
    if value >= 1024 * 1024 * 1024:
        return "%.1f GB" % (value / float(1024 ** 3))
    if value >= 1024 * 1024:
        return "%.1f MB" % (value / float(1024 ** 2))
    if value >= 1024:
        return "%.0f KB" % (value / float(1024))
    return "%d B" % value


def format_remaining(done, total, elapsed):
    try:
        done = max(0, int(done or 0))
        total = max(0, int(total or 0))
        elapsed = max(0.0, float(elapsed or 0.0))
    except (TypeError, ValueError):
        return "Starting…"
    if total <= 0:
        return "Size unknown"
    if done <= 0 or elapsed <= 0:
        return "Starting…"
    rate = done / elapsed
    if rate <= 0:
        return "Starting…"
    remaining = max(0, total - done) / rate
    if remaining >= 60:
        return "%d:%02d remaining" % (remaining // 60, remaining % 60)
    return "%d sec remaining" % remaining


class SpinnerWindow(object):
    """Small wrapper around WindowXML; all methods are safe no-ops on failure."""

    def __init__(self, addon_path=None):
        self.addon_path = addon_path or kodi.ADDON_PATH
        self.window = None
        self.failed = False
        self.cancelled = False
        self.started = time.monotonic()

    def open(self):
        window_class = globals().get("_WINDOW_CLASS")
        if window_class is None:
            return False
        try:
            self.window = window_class(
                WINDOW_XML, self.addon_path
            )
            self.window.show()
            return True
        except Exception as exc:
            self.failed = True
            kodi.log("spinner window unavailable (%s)" % exc, level=xbmc.LOGWARNING)
            self.close()
            return False

    def _control(self, control_id):
        try:
            return self.window.getControl(control_id)
        except Exception:
            return None

    def _label(self, control_id, text):
        control = self._control(control_id)
        if control is not None:
            try:
                control.setLabel(str(text))
            except Exception:
                pass

    def update(self, done, total, elapsed=None, filename=""):
        if self.window is None:
            return False
        if elapsed is None:
            elapsed = time.monotonic() - self.started
        try:
            done = max(0, int(done or 0))
            total = max(0, int(total or 0))
            percent = int((done * 100) / total) if total else 0
            percent = max(0, min(percent, 100))
            image = self._control(CONTROL_HEAD)
            if image is not None:
                image.setImage(frame_paths(FRAME_SIZE, self.addon_path)[frame_index(elapsed)])
            self._label(CONTROL_FILENAME, filename or "Downloading…")
            self._label(CONTROL_PERCENT, "%d%%" % percent)
            self._label(CONTROL_SIZE, "%s of %s" % (format_bytes(done), format_bytes(total)))
            self._label(CONTROL_REMAINING, format_remaining(done, total, elapsed))
            self._label(CONTROL_HINT, "OK / Back / Stop to cancel")
            progress = self._control(CONTROL_PROGRESS)
            if progress is not None:
                try:
                    progress.setPercent(percent)
                except Exception:
                    pass
            return True
        except Exception as exc:
            self.failed = True
            kodi.log("spinner update failed (%s)" % exc, level=xbmc.LOGWARNING)
            self.close()
            return False

    def update_tuning(self, label, elapsed=None):
        """Show the compact panel in stream-tuning mode (no byte progress)."""
        if self.window is None:
            return False
        try:
            if elapsed is None:
                elapsed = time.monotonic() - self.started
            image = self._control(CONTROL_HEAD)
            if image is not None:
                image.setImage(frame_paths(FRAME_SIZE, self.addon_path)[frame_index(elapsed)])
            self._label(CONTROL_FILENAME, "%s — Tuning in…" % (label or "Stream"))
            self._label(CONTROL_PERCENT, "")
            self._label(CONTROL_SIZE, "")
            self._label(CONTROL_REMAINING, "Tuning in…")
            self._label(CONTROL_HINT, "OK / Back to cancel")
            progress = self._control(CONTROL_PROGRESS)
            if progress is not None:
                try:
                    progress.setPercent(0)
                except Exception:
                    pass
            return True
        except Exception as exc:
            self.failed = True
            kodi.log("tuning spinner update failed (%s)" % exc, level=xbmc.LOGWARNING)
            self.close()
            return False

    def iscanceled(self):
        if self.cancelled:
            return True
        if self.window is not None and getattr(self.window, "_rave_cancelled", False):
            return True
        try:
            if self.window is not None and str(
                    self.window.getProperty("rave_cancel") or "") == "1":
                self.cancelled = True
                return True
        except Exception:  # noqa: BLE001 - stub / window already gone
            pass
        return False

    def cancel(self, reason=""):
        """Mark the transfer cancelled (OK button, Back/Stop or the owner)."""
        self.cancelled = True
        if reason:
            kodi.log("spinner: %s" % reason, level=xbmc.LOGINFO)
        return True

    def close(self):
        if self.window is not None:
            try:
                self.window.close()
            except Exception:
                pass
            self.window = None


class SurpriseReveal(object):
    """Full-screen-ish Surprise Me reveal with a large animated head.

    The window is shown for at least ``duration`` seconds while the head frame
    advances at ``fps``.  Back/Stop marks it cancelled; a window or asset
    failure is swallowed so the caller can still pick the random pack.
    """

    def __init__(self, code="RANDOM PACK", *, duration=SURPRISE_DURATION,
                 fps=SURPRISE_FPS, window_factory=None, sleep=None,
                 clock=time.monotonic):
        self.code = str(code or "RANDOM PACK")
        self.duration = max(0.0, float(duration))
        self.fps = max(1, int(fps))
        self._window_factory = window_factory
        self._sleep = sleep or xbmc.sleep
        self._clock = clock
        self.window = None
        self.cancelled = False
        self.failed = False
        self.missing_controls = []

    def _control(self, control_id):
        try:
            control = self.window.getControl(control_id)
        except (TypeError, AttributeError, RuntimeError, ValueError):
            control = None
        except Exception:
            control = None
        if control is None:
            self.missing_controls.append(control_id)
        return control

    def _label(self, control_id, text):
        control = self._control(control_id)
        if control is not None:
            try:
                control.setLabel(str(text))
            except Exception:
                pass

    def _image(self, control_id, image):
        control = self._control(control_id)
        if control is not None and image:
            try:
                control.setImage(image)
            except Exception:
                pass

    def _frame(self, elapsed):
        self._image(CONTROL_SURPRISE_HEAD,
                    frame_paths(FRAME_SIZE, kodi.ADDON_PATH)[frame_index(elapsed)])

    def show(self):
        try:
            if self._window_factory is not None:
                window = self._window_factory()
            else:
                window_class = globals().get("_WINDOW_CLASS")
                if window_class is None:
                    return False
                window = window_class(SURPRISE_XML, kodi.ADDON_PATH)
            self.window = window
            window.show()
            burst = os.path.join(kodi.ADDON_PATH, "resources", "art", "surprise-burst.jpg")
            self._image(CONTROL_SURPRISE_BG, burst)
            self._frame(0)
            self._label(CONTROL_SURPRISE_TITLE, "SURPRISE ME")
            self._label(CONTROL_SURPRISE_SUB, "SPINNING THE RACK…")
            self._label(CONTROL_SURPRISE_CODE, self.code)
            self._label(CONTROL_SURPRISE_HINT, "Back to cancel")
            if self.missing_controls:
                # A skin/window load failure must fall back to the instant
                # pick, not leave a half-open overlay or abort the route.
                kodi.log("surprise reveal controls unavailable (%s)"
                         % ",".join(str(c) for c in self.missing_controls),
                         level=xbmc.LOGWARNING)
                self.failed = True
                self.close()
                return False
            started = self._clock()
            while True:
                if getattr(self.window, "_rave_cancelled", False):
                    self.cancelled = True
                    return False
                elapsed = max(0.0, self._clock() - started)
                self._frame(elapsed)
                if elapsed >= self.duration:
                    return True
                self._sleep(min(1.0 / self.fps, max(0.0, self.duration - elapsed)))
        except Exception as exc:  # noqa: BLE001 - reveal is decorative only
            self.failed = True
            kodi.log("surprise reveal unavailable (%s)" % exc.__class__.__name__,
                     level=xbmc.LOGWARNING)
            self.close()
            return False

    def close(self):
        window = self.window
        self.window = None
        if window is not None:
            try:
                window.close()
            except Exception:
                pass


class TuningSpinner(object):
    """Delayed stream-tuning overlay.

    The window is opened by a timer only after ``threshold`` seconds, so a fast
    resolve never flashes an overlay.  A second timer closes it and notifies the
    user after ``timeout`` seconds.  ``close()`` is idempotent and must be
    called before setResolvedUrl / Player.play.
    """

    def __init__(self, label, *, threshold=TUNING_THRESHOLD,
                 timeout=TUNING_TIMEOUT, window_factory=None,
                 notify=None, clock=time.monotonic):
        self.label = str(label or "Stream")
        self.threshold = max(0.0, float(threshold))
        self.timeout = max(0.0, float(timeout))
        self._window_factory = window_factory or SpinnerWindow
        self._notify = notify or kodi.notify
        self._clock = clock
        self._lock = threading.RLock()
        self.window = None
        self.expired = False
        self.closed = False
        self._show_timer = None
        self._timeout_timer = None

    def start(self):
        if self.closed:
            return False
        with self._lock:
            if self._show_timer is not None or self._timeout_timer is not None:
                return True
            self._show_timer = threading.Timer(self.threshold, self._show)
            self._show_timer.daemon = True
            self._show_timer.start()
            self._timeout_timer = threading.Timer(self.timeout, self._expire)
            self._timeout_timer.daemon = True
            self._timeout_timer.start()
        return True

    def _show(self):
        with self._lock:
            if self.closed or self.expired or self.window is not None:
                return
            try:
                window = self._window_factory()
                opened = bool(window.open())
            except Exception:
                opened = False
                window = None
            if not opened:
                return
            self.window = window
            try:
                window.update_tuning(self.label, 0)
            except Exception:
                pass

    def _expire(self):
        with self._lock:
            if self.closed or self.expired:
                return
            self.expired = True
            self.closed = True
            self._close_locked()
        try:
            self._notify("Stream taking too long — check your connection.")
        except Exception:
            pass

    def _close_locked(self):
        for timer in (self._show_timer, self._timeout_timer):
            if timer is not None:
                timer.cancel()
        window = self.window
        self.window = None
        if window is not None:
            try:
                window.close()
            except Exception:
                pass

    def close(self):
        with self._lock:
            if self.closed:
                return
            self.closed = True
            self._close_locked()

    def cancelled(self):
        return bool(self.window is not None and self.window.iscanceled())


def _build_window_class():
    base = getattr(xbmcgui, "WindowXML", None)
    if base is None:
        return None

    class _Overlay(base):
        def __init__(self, *args, **kwargs):
            self._rave_cancelled = False
            base.__init__(self, *args, **kwargs)

        def _cancel(self):
            # Mark only; the owner (download loop / reveal) closes the window.
            # Closing inside an action can tear down the plugin interpreter.
            self._rave_cancelled = True

        def onControl(self, control):
            try:
                control_id = control.getId()
            except Exception:
                control_id = None
            if control_id == CONTROL_CANCEL:
                self._cancel()
                return
            handler = getattr(base, "onControl", None)
            if handler is not None:
                try:
                    handler(self, control)
                except Exception:
                    pass

        def onAction(self, action):
            try:
                code = action.getId()
            except Exception:
                code = None
            if code in (getattr(xbmcgui, "ACTION_NAV_BACK", 92),
                        getattr(xbmcgui, "ACTION_STOP", 13),
                        getattr(xbmcgui, "ACTION_PREVIOUS_MENU", 10),
                        getattr(xbmcgui, "ACTION_PARENT_DIR", 9)):
                self._cancel()
                return
            try:
                base.onAction(self, action)
            except Exception:
                pass

    return _Overlay


_WINDOW_CLASS = _build_window_class()
