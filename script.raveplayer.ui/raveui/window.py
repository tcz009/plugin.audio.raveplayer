# -*- coding: utf-8 -*-
"""The Kodi adapter: one full-screen ``WindowXML`` window and its controls.

There is deliberately no ``xbmcgui.WindowDialog`` and no ``Dialog`` overlay in
this module. The XML is a normal ``<window type="window">`` at 1280x720; Kodi
owns it like any other skin window.

One Kodi 19-22 behaviour is load-bearing: ``show()`` is asynchronous and Kodi
silently *refuses* the activation while a modal dialog is up (``Activate of
window '13000' refused because there are active modal dialogs``). No exception
is raised, so :func:`open_screen` waits for modals, verifies the active window
id and fails fast instead of waiting forever for a close that can never come.
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
    # Some remotes/keymaps send "parent directory" for Back.
    getattr(xbmcgui, "ACTION_PARENT_DIR", 9),
))
MOVE_ACTIONS = frozenset((
    getattr(xbmcgui, "ACTION_MOVE_UP", 3),
    getattr(xbmcgui, "ACTION_MOVE_DOWN", 4),
    getattr(xbmcgui, "ACTION_MOVE_LEFT", 1),
    getattr(xbmcgui, "ACTION_MOVE_RIGHT", 2),
    getattr(xbmcgui, "ACTION_PAGE_UP", 5),
    getattr(xbmcgui, "ACTION_PAGE_DOWN", 6),
))

# Bounded activation: wait for an open modal, then verify that Kodi really made
# this window the active one (show() reports nothing).
ACTIVATION_WAIT_SECONDS = 10.0
ACTIVATION_POLL_MS = 100
ACTIVE_CHECKS_PER_SHOW = 10


class KodiView(object):
    """Thin control-port implementation used by the controller."""

    def __init__(self, window):
        self.window = window
        self._missing_logged = set()

    def _control(self, control_id):
        try:
            return self.window.getControl(control_id)
        except Exception:  # noqa: BLE001 - skin control missing
            # A wrong id or a control that Kodi failed to create used to fail
            # completely silently: no rows, no status, just a blank screen.
            if control_id not in self._missing_logged:
                self._missing_logged.add(control_id)
                try:
                    xbmc.log("[script.raveplayer.ui] control %s missing from the "
                             "skin XML" % control_id, level=xbmc.LOGERROR)
                except Exception:
                    pass
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
        items = []
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
            items.append(item)
        # One GUI_MSG_LABEL_BIND for the whole list. ControlList.addItem()
        # re-sends the entire bound vector on every call, so the 400-show
        # JungleTapes list would queue 400 list rebuilds (O(n^2)) and churn the
        # GUI thread for seconds.
        try:
            control.addItems(items)
        except Exception:
            for item in items:
                try:
                    control.addItem(item)
                except Exception:
                    break
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
        self._initialized = False
        self._controller = None
        self._view = None
        super().__init__(*args, **kwargs)

    @property
    def closed(self):
        return self._closed

    @property
    def initialized(self):
        """True once Kodi has sent GUI_MSG_WINDOW_INIT and run onInit."""
        return self._initialized

    def onInit(self):
        # Set before any work: this is the only reliable proof that Kodi
        # activated the window (a modal-refused show() never gets here).
        self._initialized = True
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
        except Exception as exc:  # noqa: BLE001 - fail closed, never a blank window
            xbmc.log("[script.raveplayer.ui] init failed: %s" % exc,
                     level=xbmc.LOGERROR)
            self._view.set_status("Rave Screen could not load Rave Player data.")
            _notify("Rave Screen could not load Rave Player data. See the log.")
            self.close()
            return
        # defaultcontrol=50 already owns focus. Calling setFocusId() here only
        # makes Kodi log "Control 50 ... asked to focus, but it can't": the
        # deferred onInit callback runs before the window is active.

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


def _notify(message):
    try:
        xbmcgui.Dialog().notification("Rave Screen", str(message), "", 5000)
    except Exception:  # noqa: BLE001 - notification is decorative
        pass


def _modal_dialog_active():
    try:
        return bool(xbmc.getCondVisibility("System.HasActiveModalDialog"))
    except Exception:
        return False


def _activate(window):
    """Show the window and verify that Kodi actually initialised it.

    ``WindowXML.show()`` is asynchronous and Kodi silently refuses the
    activation while a modal dialog is open (``Activate of window '13000'
    refused because there are active modal dialogs``). Nothing is raised, and
    a refused activation never sends ``GUI_MSG_WINDOW_INIT``, so ``onInit``
    never runs (the device log had no "Window Init" line and no onInit).
    ``onInit`` running is therefore the activation signal; it executes on the
    script thread inside the ``xbmc.sleep`` below, which pumps the queued
    callback.
    """
    if not hasattr(window, "initialized"):
        # Test double without the lifecycle probe: fire and forget.
        window.show()
        return True
    deadline = time.monotonic() + ACTIVATION_WAIT_SECONDS
    while time.monotonic() < deadline:
        if getattr(window, "closed", False):
            return False
        if _modal_dialog_active():
            xbmc.sleep(ACTIVATION_POLL_MS)
            continue
        window.show()
        for _ in range(ACTIVE_CHECKS_PER_SHOW):
            xbmc.sleep(ACTIVATION_POLL_MS)
            if getattr(window, "initialized", False):
                return True
            if getattr(window, "closed", False):
                return False
    return False


def _cleanup(window):
    """Close the window, except when Kodi never activated it.

    Window.close() sends TMSG_GUI_PREVIOUS_WINDOW, i.e. it pops the *current*
    window history entry. For a window that never initialised that would kick
    the user out of the Rave Player root list. Dropping the reference instead
    lets Kodi's window destructor delete the unused window without touching
    the stack.
    """
    initialized = getattr(window, "initialized", None)
    if initialized is None or initialized or getattr(window, "closed", False):
        try:
            window.close()
        except Exception:
            pass


def open_screen(window_factory=None, monitor_factory=None):
    """Create/show the window and keep the script alive until Back closes it."""
    factory = window_factory or RaveScreenWindow
    window = factory(XML_FILE, ADDON_PATH)
    try:
        if not _activate(window):
            xbmc.log("[script.raveplayer.ui] window activation refused "
                     "(a modal dialog was probably open); not waiting.",
                     level=xbmc.LOGERROR)
            _notify("Could not open Rave Screen. Close any dialog and try again.")
            return window
        monitor = monitor_factory() if monitor_factory else xbmc.Monitor()
        while not getattr(window, "closed", False):
            try:
                if monitor.abortRequested():
                    break
            except Exception:
                pass
            xbmc.sleep(100)
    finally:
        # Idempotent with Back, which already closed the window.
        _cleanup(window)
    return window
