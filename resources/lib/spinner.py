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

import os
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


def frames_dir(addon_path=None):
    root = addon_path or kodi.ADDON_PATH
    return os.path.join(root, FRAME_DIR)


def frame_paths(size=FRAME_SIZE, addon_path=None):
    root = frames_dir(addon_path)
    return [os.path.join(root, "head-%d-%02d.png" % (size, index))
            for index in range(FRAME_COUNT)]


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
                WINDOW_XML, os.path.join(self.addon_path, SKIN_DIR)
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
            self._label(CONTROL_HINT, "Back / Stop to cancel")
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

    def iscanceled(self):
        if self.cancelled:
            return True
        if self.window is not None and getattr(self.window, "_rave_cancelled", False):
            return True
        return False

    def close(self):
        if self.window is not None:
            try:
                self.window.close()
            except Exception:
                pass
            self.window = None


def _build_window_class():
    base = getattr(xbmcgui, "WindowXML", None)
    if base is None:
        return None

    class _Overlay(base):
        def __init__(self, *args, **kwargs):
            self._rave_cancelled = False
            base.__init__(self, *args, **kwargs)

        def onAction(self, action):
            try:
                code = action.getId()
            except Exception:
                code = None
            if code in (getattr(xbmcgui, "ACTION_NAV_BACK", 92),
                        getattr(xbmcgui, "ACTION_STOP", 13)):
                self._rave_cancelled = True
                self.close()
                return
            try:
                base.onAction(self, action)
            except Exception:
                pass

    return _Overlay


_WINDOW_CLASS = _build_window_class()
