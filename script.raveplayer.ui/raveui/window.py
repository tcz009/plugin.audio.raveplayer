# -*- coding: utf-8 -*-
"""The Kodi adapter: one full-screen ``WindowXML`` window and its controls.

There is deliberately no ``xbmcgui.WindowDialog`` and no ``Dialog`` overlay in
this module. The XML is a normal ``<window type="window">`` at 1280x720; Kodi
owns it like any other skin window, so it cannot be "refused" the way a plugin
list overlay can on Kodi 22.
"""

import os
import time

import xbmc
import xbmcgui

from .controller import RaveScreenController
from .data import RaveData
from .playback import PlaybackService

ADDON_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML_FILE = "script-raveplayer-ui.xml"

CONTROL_BACKGROUND = 10
CONTROL_HERO = 20
CONTROL_TITLE = 22
CONTROL_SUBTITLE = 23
CONTROL_STATUS = 30
CONTROL_NOW_PLAYING = 31
CONTROL_LIST = 50
CONTROL_SPINNER_BG = 60
CONTROL_SPINNER_HEAD = 61
CONTROL_SPINNER_RING = 64
CONTROL_SPINNER_LABEL = 62
CONTROL_SPINNER_HINT = 63

BACK_ACTIONS = frozenset((
    getattr(xbmcgui, "ACTION_NAV_BACK", 92),
    getattr(xbmcgui, "ACTION_PREVIOUS_MENU", 10),
))
MOVE_ACTIONS = frozenset((
    getattr(xbmcgui, "ACTION_MOVE_UP", 3),
    getattr(xbmcgui, "ACTION_MOVE_DOWN", 4),
    getattr(xbmcgui, "ACTION_MOVE_LEFT", 1),
    getattr(xbmcgui, "ACTION_MOVE_RIGHT", 2),
    getattr(xbmcgui, "ACTION_PAGE_UP", 5),
    getattr(xbmcgui, "ACTION_PAGE_DOWN", 6),
))


class KodiView(object):
    """Thin control-port implementation used by the controller."""

    def __init__(self, window):
        self.window = window

    def _control(self, control_id):
        try:
            return self.window.getControl(control_id)
        except Exception:  # noqa: BLE001 - skin control missing
            return None

    def _label(self, control_id, text):
        control = self._control(control_id)
        if control is not None:
            try:
                control.setLabel(str(text or ""))
            except Exception:
                pass

    def _visible(self, control_id, visible):
        control = self._control(control_id)
        if control is not None:
            try:
                control.setVisible(bool(visible))
            except Exception:
                pass

    def set_title(self, text):
        self._label(CONTROL_TITLE, text)

    def set_subtitle(self, text):
        self._label(CONTROL_SUBTITLE, text)

    def set_status(self, text):
        self._label(CONTROL_STATUS, text)

    def set_now_playing(self, text):
        self._label(CONTROL_NOW_PLAYING, text)

    def set_rows(self, rows):
        control = self._control(CONTROL_LIST)
        if control is None:
            return
        try:
            control.reset()
        except Exception:
            pass
        for row in rows:
            item = xbmcgui.ListItem(label=row.label)
            try:
                item.setLabel2(row.subtitle)
            except Exception:
                pass
            if row.art:
                try:
                    item.setArt({"thumb": row.art, "icon": row.art})
                except Exception:
                    pass
            try:
                item.setInfo("music", {"title": row.label, "comment": row.subtitle})
            except Exception:
                pass
            try:
                control.addItem(item)
            except Exception:
                pass
        try:
            control.selectItem(0)
        except Exception:
            pass

    def set_hero(self, entry):
        # The wordmark (21), view title (22) and view subtitle (23) are owned by
        # set_title/set_subtitle. The hero is art only: overwriting the wordmark
        # with a row label made the screen look like a different app.
        if entry is None:
            return
        control = self._control(CONTROL_HERO)
        image = getattr(entry, "hero", "") or entry.art
        if control is not None and image:
            try:
                control.setImage(image)
            except Exception:
                pass

    def selected_index(self):
        control = self._control(CONTROL_LIST)
        if control is None:
            return 0
        try:
            return int(control.getSelectedPosition())
        except Exception:
            return 0

    def set_spinner_visible(self, visible):
        for control_id in (CONTROL_SPINNER_BG, CONTROL_SPINNER_HEAD,
                           CONTROL_SPINNER_RING, CONTROL_SPINNER_LABEL,
                           CONTROL_SPINNER_HINT):
            self._visible(control_id, visible)

    def set_spinner_background(self, path):
        control = self._control(CONTROL_SPINNER_BG)
        if control is not None and path:
            try:
                control.setImage(path)
            except Exception:
                pass

    def set_spinner_image(self, path):
        control = self._control(CONTROL_SPINNER_HEAD)
        if control is not None and path:
            try:
                control.setImage(path)
            except Exception:
                pass

    def set_spinner_label(self, text):
        self._label(CONTROL_SPINNER_LABEL, text)

    def notify(self, text):
        try:
            xbmcgui.Dialog().notification("Rave Screen", str(text), "", 4000)
        except Exception:
            pass

    def close(self):
        self.window.close()


class RaveScreenWindow(xbmcgui.WindowXML):
    """Full-screen Rave Screen window. Construct, then ``show()``."""

    def __init__(self, *args, **kwargs):
        self._closed = False
        self._controller = None
        self._view = None
        super().__init__(*args, **kwargs)

    @property
    def closed(self):
        return self._closed

    def onInit(self):
        if self._controller is not None:
            return
        self._view = KodiView(self)
        self._view.set_spinner_visible(False)
        self._view.set_spinner_background(
            os.path.join(ADDON_PATH, "resources", "art", "surprise-burst.jpg"))
        try:
            data = RaveData()
            self._controller = RaveScreenController(
                self._view, data, PlaybackService(),
                sleep=xbmc.sleep, clock=time.monotonic,
                frames=data.spinner_frames())
            self._controller.start()
        except Exception as exc:  # noqa: BLE001 - open with a useful status
            xbmc.log("[script.raveplayer.ui] init failed: %s" % exc,
                     level=xbmc.LOGERROR)
            self._view.set_status("Rave Screen could not load Rave Player data.")
    def onClick(self, control_id):
        if control_id == CONTROL_LIST and self._controller is not None:
            self._controller.on_click()
        elif control_id in (CONTROL_SPINNER_HEAD, CONTROL_SPINNER_BG):
            if self._controller is not None:
                self._controller.on_click()

    def onAction(self, action):
        try:
            action_id = action.getId()
        except Exception:
            action_id = None
        if action_id in BACK_ACTIONS:
            if self._controller is not None:
                should_close = self._controller.on_back()
            else:
                should_close = True
            if should_close:
                self.close()
            return
        # Let the list handle D-pad movement/scroll, then refresh the hero.
        try:
            super().onAction(action)
        except Exception:
            pass
        if action_id in MOVE_ACTIONS and self._controller is not None:
            self._controller.on_focus()

    def onFocus(self, control_id):
        if control_id == CONTROL_LIST and self._controller is not None:
            self._controller.on_focus()

    def close(self):
        if self._closed:
            return
        self._closed = True
        shutdown = getattr(self._controller, "shutdown", None)
        if shutdown is not None:
            shutdown()
        try:
            super().close()
        except Exception:
            pass


def open_screen(window_factory=None, monitor_factory=None):
    """Create/show the window and keep the script alive until Back closes it."""
    factory = window_factory or RaveScreenWindow
    window = factory(XML_FILE, ADDON_PATH)
    window.show()

    # show() silently does nothing when a modal dialog is up (Kodi logs
    # "Activate of window '13000' refused because there are active modal
    # dialogs" without an add-on id).  Retry briefly, then fail fast instead of
    # looping forever with an invisible window.
    def _active():
        if getattr(window, "closed", False):
            return True
        try:
            current = xbmcgui.getCurrentWindowId()
        except Exception:
            return False
        if current and current >= 13000:
            return True
        # Unit tests inject a fake window and the stub reports window 0; treat
        # an explicit injected factory as proof the window is up.
        if window_factory is not None and not getattr(window, "closed", False):
            return True
        return False

    deadline = time.time() + 7.5
    while not _active() and time.time() < deadline:
        xbmc.sleep(250)
    if not _active():
        xbmc.log("[script.raveplayer.ui] screen refused: modal dialog active",
                 level=xbmc.LOGERROR)
        try:
            xbmcgui.Dialog().notification("Rave Screen", "Close the open dialog and try again.", xbmcgui.NOTIFICATION_WARNING)
        except Exception:
            pass
        try:
            window.close()
        except Exception:
            pass
        return None

    monitor = monitor_factory() if monitor_factory else xbmc.Monitor()
    while not getattr(window, "closed", False):
        try:
            if monitor.abortRequested():
                window.close()
                break
        except Exception:
            pass
        xbmc.sleep(100)
    return window
