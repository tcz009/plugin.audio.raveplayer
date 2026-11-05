# -*- coding: utf-8 -*-
"""The Kodi adapter: one full-screen ``WindowXML`` window and its controls.

There is deliberately no ``xbmcgui.WindowDialog`` and no ``Dialog`` overlay in
this module. The XML is a normal ``<window type="window">`` at 1280x720; Kodi
owns it like any other skin window.

One Kodi 19-22 behaviour is load-bearing: ``show()`` is asynchronous and Kodi
silently *refuses* the activation while a modal dialog is up (``Activate of
window '13000' refused because there are active modal dialogs``). No exception
is raised, so :func:`open_screen` waits for modals, verifies that ``onInit``
really ran and fails fast instead of waiting forever for a close that can never
come.
"""

import os
import time

import xbmc
import xbmcgui

from .controller import HOME_TITLE, RaveScreenController
from .data import RaveData
from .downloadqueue import DownloadQueue
from .playback import PlaybackService

ADDON_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML_FILE = "script-raveplayer-ui.xml"
ART_ROOT = os.path.join(ADDON_PATH, "resources", "art", "rave-screen")
HERO_FALLBACK = os.path.join(ART_ROOT, "hero-fallback-640x360.jpg")

# Control IDs are the WINDOWXML-CONTROL-MAP.md contract. The list is 50:
# Kodi's WindowXML window list lives on 50-59 and addItems()/getCurrentListPosition()
# are bound to it. Never move it to 500.
CONTROL_STATUS = 30
CONTROL_NOW_PLAYING = 31
CONTROL_LIST = 50
CONTROL_BED = 100
CONTROL_NOISE = 101
CONTROL_MARK = 111
CONTROL_WORDMARK = 112
CONTROL_CLOCK = 114
CONTROL_ROOMS_IDLE = 115
CONTROL_ROOMS_ON_AIR = 116
CONTROL_VIEW_TITLE = 119
CONTROL_VIEW_SUBTITLE = 120
CONTROL_FOCUS_STICKER = 121
CONTROL_HERO_SHADOW = 200
CONTROL_HERO = 201
CONTROL_HERO_SCRIM = 202
CONTROL_HERO_STICKER = 204
CONTROL_HERO_CODE = 207
CONTROL_HERO_TITLE = 210
CONTROL_HERO_META = 211
CONTROL_HERO_PLOT = 212
CONTROL_FOOTER = 600
CONTROL_ON_AIR = 601
CONTROL_NOW_KICKER = 602
CONTROL_NOW_TITLE = 603
CONTROL_NOW_META = 604
CONTROL_OK_KEYCAP = 612
CONTROL_OK_HINT = 613
CONTROL_BACK_KEYCAP = 614
CONTROL_BACK_HINT = 615
CONTROL_PAGE_INFO = 617
CONTROL_SPINNER_BG = 700
CONTROL_SPINNER_RING = 701
CONTROL_SPINNER_HEAD = 702
CONTROL_SPINNER_CAPTION = 703
CONTROL_SPINNER_TITLE = 704
CONTROL_SPINNER_SUB = 705
CONTROL_SPINNER_LABEL = 706
CONTROL_SPINNER_CANCEL = 707
CONTROL_SPINNER_KEYCAP = 708
CONTROL_SPINNER_HINT = 709
CONTROL_SPINNER_MARK = 710
CONTROL_SPINNER_TOP = 711
CONTROL_SPINNER_CODE = 712
CONTROL_SPINNER_NOISE = 713
# Loading / empty / error plates. They are one state of the same window, bound
# to a property exactly like the Surprise splash (never a literal <visible>false</visible>).
CONTROL_PLATE_SCRIM = 720
CONTROL_PLATE = 721
CONTROL_PLATE_HEAD = 722
CONTROL_PLATE_KICKER = 723
CONTROL_PLATE_TITLE = 724
CONTROL_PLATE_DETAIL = 725
CONTROL_PLATE_HINT = 726
CONTROL_PLATE_CODE = 727

SPLASH_PROPERTY = "rp_splash"
PLATE_PROPERTY = "rp_plate"
PLATE_HEAD_PROPERTY = "rp_plate_head"
LIVE_PROPERTY = "rp_live"

MAX_VIEW_TITLE = 30
MAX_VIEW_SUBTITLE = 40

SPINNER_CONTROLS = (
    CONTROL_SPINNER_BG, CONTROL_SPINNER_RING, CONTROL_SPINNER_HEAD,
    CONTROL_SPINNER_CAPTION, CONTROL_SPINNER_TITLE, CONTROL_SPINNER_SUB,
    CONTROL_SPINNER_LABEL, CONTROL_SPINNER_CANCEL, CONTROL_SPINNER_KEYCAP,
    CONTROL_SPINNER_HINT, CONTROL_SPINNER_MARK, CONTROL_SPINNER_TOP,
    CONTROL_SPINNER_CODE, CONTROL_SPINNER_NOISE,
)
PLATE_CONTROLS = (
    CONTROL_PLATE_SCRIM, CONTROL_PLATE, CONTROL_PLATE_KICKER,
    CONTROL_PLATE_TITLE, CONTROL_PLATE_DETAIL, CONTROL_PLATE_HINT,
    CONTROL_PLATE_CODE,
)

BACK_ACTIONS = frozenset((
    getattr(xbmcgui, "ACTION_NAV_BACK", 92),
    getattr(xbmcgui, "ACTION_PREVIOUS_MENU", 10),
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
LEFT_RIGHT_ACTIONS = {
    getattr(xbmcgui, "ACTION_MOVE_LEFT", 1): -1,
    getattr(xbmcgui, "ACTION_MOVE_RIGHT", 2): 1,
}
CONTEXT_ACTIONS = frozenset((
    getattr(xbmcgui, "ACTION_CONTEXT_MENU", 117),
    getattr(xbmcgui, "ACTION_INFO", 11),
))
STOP_ACTIONS = frozenset((getattr(xbmcgui, "ACTION_STOP", 13),))

# Bounded activation: wait for an open modal, then verify that Kodi really made
# this window the active one (show() reports nothing).
ACTIVATION_WAIT_SECONDS = 10.0
ACTIVATION_POLL_MS = 100
ACTIVE_CHECKS_PER_SHOW = 10


class _Log(object):
    """Callable logger with a debug-level trace channel for device evidence."""

    @staticmethod
    def __call__(message):
        xbmc.log("[script.raveplayer.ui] %s" % message, level=xbmc.LOGWARNING)

    @staticmethod
    def trace(message):
        xbmc.log("[script.raveplayer.ui] %s" % message, level=xbmc.LOGINFO)


def _clip(text, limit):
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[:max(1, limit - 1)].rstrip() + "…"


class KodiView(object):
    """Thin control-port implementation used by the controller."""

    def __init__(self, window):
        self.window = window
        self._missing_logged = set()

    def _control(self, control_id):
        try:
            return self.window.getControl(control_id)
        except Exception:  # noqa: BLE001 - skin control missing
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
        if control is None:
            return False
        try:
            control.setVisible(bool(visible))
        except Exception:
            return False
        return True

    def set_title(self, text):
        text = _clip(str(text or ""), MAX_VIEW_TITLE)
        self._view_title = text
        self._label(CONTROL_VIEW_TITLE, text)
        self._visible(CONTROL_VIEW_TITLE, text != HOME_TITLE)
        if text == HOME_TITLE:
            self._visible(CONTROL_VIEW_SUBTITLE, False)

    def set_subtitle(self, text):
        self._label(CONTROL_VIEW_SUBTITLE, _clip(text, MAX_VIEW_SUBTITLE))
        self._visible(CONTROL_VIEW_SUBTITLE,
                      getattr(self, "_view_title", HOME_TITLE) != HOME_TITLE)

    def set_status(self, text):
        self._label(CONTROL_STATUS, text)

    def set_room_count(self, count, unit="ROOMS"):
        """Write the plural-aware header count label (ROOMS/ROWS/KEYS/ACTIONS)."""
        try:
            count = max(0, int(count))
        except (TypeError, ValueError):
            count = 0
        unit = str(unit or "ROOMS").upper()
        singular = {"ROOMS": "ROOM", "ROWS": "ROW"}.get(unit, unit.rstrip("S"))
        shown = singular if count == 1 else unit
        self._label(CONTROL_ROOMS_IDLE, "[B]%d[/B] %s · STANDBY" % (count, shown))
        self._label(CONTROL_ROOMS_ON_AIR, "[B]%d[/B] %s · ON AIR" % (count, shown))

    def set_page_info(self, text):
        self._label(CONTROL_PAGE_INFO, text)

    def set_key_hints(self, ok_text, back_text):
        self._label(CONTROL_OK_HINT, ok_text)
        self._label(CONTROL_BACK_HINT, back_text)

    def set_live(self, live):
        try:
            self.window.setProperty(LIVE_PROPERTY, "1" if live else "0")
        except Exception:
            pass

    def set_keyboard_mode(self, active):
        """Hide the hero while the in-window keyboard owns the right column."""
        try:
            self.window.setProperty("rp_keyboard", "1" if active else "0")
        except Exception:
            pass

    def set_now_playing(self, text):
        try:
            self.window.setProperty("rp_now", str(text or ""))
        except Exception:
            pass

    def set_footer(self, footer):
        """Paint the one footer model (idle / playing / paused / live)."""
        if footer is None:
            return
        try:
            for key, value in footer.properties().items():
                self.window.setProperty(key, value)
        except Exception:
            pass
        self._label(CONTROL_NOW_KICKER, footer.kicker)
        self._label(CONTROL_NOW_TITLE, footer.title)
        self._label(CONTROL_NOW_META, footer.meta)
        self._visible(CONTROL_ON_AIR, footer.on_air)
        self.set_now_playing(footer.status_line())

    @staticmethod
    def _is_art(path):
        path = str(path or "")
        if not path:
            return False
        if path.startswith(("http://", "https://", "special://",
                            "plugin://", "file://")):
            return True
        return os.path.isfile(path)

    def _row_art(self, entry):
        icon = getattr(entry, "art", "") or getattr(entry, "hero", "")
        hero = getattr(entry, "hero", "") or icon
        if not self._is_art(hero):
            hero = HERO_FALLBACK
        if not self._is_art(icon):
            # Keyboard/action/page rows have no cover of their own.  The small
            # NO SIGNAL fallback read as an error at 36 px; use the brand mark.
            icon = os.path.join(ART_ROOT, "mark.png")
        return icon, hero

    def set_rows(self, rows, selected=0):
        control = self._control(CONTROL_LIST)
        if control is None:
            return
        rows = list(rows or [])
        try:
            control.reset()
        except Exception:
            pass
        items = []
        for index, row in enumerate(rows):
            icon, hero = self._row_art(row)
            subtitle = getattr(row, "subtitle", "") or ""
            fact = str(getattr(row, "fact", "") or subtitle)
            code = str(getattr(row, "code", "") or "")
            plot = str(getattr(row, "plot", "") or subtitle)
            meta = str(getattr(row, "meta", "") or "")
            if not meta:
                meta = "%s  ·  %s" % (fact, code) if fact and code else (fact or code)
            item = xbmcgui.ListItem(label=row.label)
            try:
                item.setLabel2(fact)
            except Exception:
                pass
            try:
                item.setArt({"icon": icon, "thumb": icon,
                             "fanart": hero, "poster": icon})
            except Exception:
                pass
            try:
                item.setProperty("rp_index", "%02d" % (index + 1))
                item.setProperty("rp_code", code)
                item.setProperty("rp_meta", meta)
            except Exception:
                pass
            try:
                item.setInfo("video", {"plot": plot})
            except Exception:
                pass
            items.append(item)
        try:
            control.addItems(items)
        except Exception:
            for item in items:
                try:
                    control.addItem(item)
                except Exception:
                    break
        try:
            position = max(0, min(int(selected), len(items) - 1)) if items else 0
            control.selectItem(position)
        except (TypeError, ValueError):
            try:
                control.selectItem(0)
            except Exception:
                pass
        except Exception:
            pass

    def set_hero(self, entry):
        control = self._control(CONTROL_HERO)
        if control is None:
            return
        if entry is None:
            image = HERO_FALLBACK
        else:
            icon, hero = self._row_art(entry)
            image = hero or icon
        if image:
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
        # Property first: the XML condition must already be true when the
        # controls are made visible, otherwise the GUI thread can evaluate the
        # old (hidden) condition for a frame and drop the reveal again.
        try:
            self.window.setProperty(SPLASH_PROPERTY, "1" if visible else "0")
        except Exception:
            pass
        shown = 0
        for control_id in SPINNER_CONTROLS:
            if self._visible(control_id, visible):
                shown += 1
        xbmc.log("[script.raveplayer.ui] spinner visible=%s %s=%d controls=%d"
                 % (visible, SPLASH_PROPERTY, 1 if visible else 0, shown),
                 level=xbmc.LOGDEBUG)

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

    # ---------------------------------------------------------- plate state
    def set_plate(self, kind, title, detail="", hint=""):
        kind = str(kind or "loading")
        try:
            self.window.setProperty(PLATE_PROPERTY, "1")
            self.window.setProperty(PLATE_HEAD_PROPERTY,
                                    "1" if kind == "loading" else "0")
        except Exception:
            pass
        self._label(CONTROL_PLATE_KICKER,
                    {"loading": "LOADING", "empty": "STANDBY",
                     "error": "ERROR"}.get(kind, kind.upper()))
        self._label(CONTROL_PLATE_TITLE, title)
        self._label(CONTROL_PLATE_DETAIL, detail)
        self._label(CONTROL_PLATE_HINT, hint or "BACK returns")
        self._label(CONTROL_PLATE_CODE,
                    {"loading": "PLEASE WAIT", "empty": "NO ROWS",
                     "error": "SOURCE ERROR"}.get(kind, "SYSTEM"))
        xbmc.log("[script.raveplayer.ui] plate %s title=%r" % (kind, title),
                 level=xbmc.LOGDEBUG)

    def set_plate_head(self, path):
        control = self._control(CONTROL_PLATE_HEAD)
        if control is not None and path:
            try:
                control.setImage(path)
            except Exception:
                pass

    def clear_plate(self):
        try:
            self.window.setProperty(PLATE_PROPERTY, "0")
            self.window.setProperty(PLATE_HEAD_PROPERTY, "0")
        except Exception:
            pass

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
        self._view.clear_plate()
        self._view.set_live(False)
        self._view.set_spinner_background(
            os.path.join(ART_ROOT, "surprise-burst-1280x720.jpg"))
        try:
            queue = DownloadQueue(logger=_Log())
            data = RaveData(download_queue=queue)
            self._controller = RaveScreenController(
                self._view, data, PlaybackService(),
                sleep=xbmc.sleep, clock=time.monotonic,
                frames=data.spinner_frames(), logger=_Log(),
                download_queue=queue)
            self._controller.start()
            # Kodi focuses defaultcontrol=50 while the list is still empty (the
            # controller imports the plugin and binds 11 rows during onInit).
            # That focus attempt fails and is never retried, so the painted
            # window would receive no key events while the previous window
            # keeps them. Focus explicitly *after* the rows exist.
            try:
                self.setFocusId(CONTROL_LIST)
            except Exception as exc:  # noqa: BLE001 - cosmetically harmless
                xbmc.log("[script.raveplayer.ui] focus after bind failed: %s" % exc,
                         level=xbmc.LOGWARNING)
        except Exception as exc:  # noqa: BLE001 - fail closed, never a blank window
            xbmc.log("[script.raveplayer.ui] init failed: %s" % exc,
                     level=xbmc.LOGERROR)
            self._view.set_status("Rave Screen could not load Rave Player data.")
            _notify("Rave Screen could not load Rave Player data. See the log.")
            self.close()
            return
        # defaultcontrol=50 already owns focus; no explicit focus call is needed.

    def onClick(self, control_id):
        if self._controller is None:
            return
        if control_id == CONTROL_LIST:
            self._controller.on_click()
        elif control_id == CONTROL_SPINNER_CANCEL:
            if self._controller.on_back():
                self.close()

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
        if action_id in LEFT_RIGHT_ACTIONS and self._controller is not None:
            if self._controller.on_horizontal(LEFT_RIGHT_ACTIONS[action_id]):
                return
        if action_id in CONTEXT_ACTIONS and self._controller is not None:
            self._controller.on_context()
            return
        if action_id in STOP_ACTIONS and self._controller is not None:
            self._controller.on_stop()
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
        # Closing a script window returns to whatever spawned it (the plugin
        # root launcher), which on Kodi 22 can immediately relaunch the app.
        # One Back must leave the add-on: send Home explicitly after the close.
        try:
            xbmc.executebuiltin("ActivateWindow(Home)")
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
    activation while a modal dialog is open. Nothing is raised, and a refused
    activation never sends ``GUI_MSG_WINDOW_INIT``, so ``onInit`` never runs.
    ``onInit`` running is therefore the activation signal.
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
        controller = getattr(window, "_controller", None)
        while not getattr(window, "closed", False):
            try:
                if monitor.abortRequested():
                    break
            except Exception:
                pass
            tick = getattr(controller, "tick", None)
            if callable(tick):
                try:
                    tick()
                except Exception:  # noqa: BLE001 - a footer probe never closes
                    pass
            xbmc.sleep(100)
    finally:
        _cleanup(window)

    return window
