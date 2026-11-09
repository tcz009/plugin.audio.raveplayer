# -*- coding: utf-8 -*-
"""Minimal Kodi stubs so the add-on can be exercised outside Kodi.

Run: python3 test/run.py
"""

import json
import os
import tempfile

LOG_LINES = []
ITEMS = []
RESOLVED = []

INPUT_ALPHANUM = 0

ACTION_MOVE_LEFT = 1
ACTION_MOVE_RIGHT = 2
ACTION_MOVE_UP = 3
ACTION_MOVE_DOWN = 4
ACTION_PAGE_UP = 5
ACTION_PAGE_DOWN = 6
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92

NOTIFICATION_INFO = "info"


class _Addon(object):
    def getAddonInfo(self, key):
        values = {
            "id": "plugin.audio.raveplayer",
            "name": "Rave Player",
            "version": "3.0.0",
            "path": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "profile": os.path.join(tempfile.gettempdir(), "raveplayer-test-profile"),
            "icon": "icon.png",
            "fanart": "fanart.jpg",
        }
        return values.get(key, "")

    def getSetting(self, key):
        return {"results_per_page": "5", "radio_limit": "5"}.get(key, "")

    def setSetting(self, key, value):
        pass


class _Dialog(object):
    def __init__(self, value=""):
        self.value = value

    def input(self, *args, **kwargs):
        return self.value

    def notification(self, *args, **kwargs):
        pass

    def ok(self, *args, **kwargs):
        pass

    def yesno(self, *args, **kwargs):
        return True


Dialog = _Dialog


class DialogProgress(object):
    def __init__(self, *args, **kwargs):
        self.percent = 0
        self.cancelled = False

    def create(self, *args, **kwargs):
        pass

    def update(self, percent, *args, **kwargs):
        self.percent = percent

    def iscanceled(self):
        return self.cancelled

    def close(self):
        pass


class DialogProgressBG(object):
    def __init__(self, *args, **kwargs):
        self.percent = 0
        self.message = ""
        self.finished = False

    def create(self, *args, **kwargs):
        pass

    def update(self, percent, *args, **kwargs):
        self.percent = percent

    def isFinished(self):
        return self.finished

    def close(self):
        pass


class ListItem(object):
    def __init__(self, label="", path=""):
        self.label = label
        self.label2 = ""
        self.path = path
        self.art = {}
        self.info = {}
        self.properties = {}
        self.context = []

    def setArt(self, art):
        self.art.update(art or {})

    def setInfo(self, kind, info):
        self.info[kind] = info

    def setProperty(self, key, value):
        self.properties[key] = value

    def addContextMenuItems(self, items, replaceItems=False):
        self.context = list(items or [])

    def setPath(self, path):
        self.path = path

    def setMimeType(self, mime):
        self.mime = mime

    def setLabel(self, label):
        self.label = label

    def setLabel2(self, label):
        self.label2 = label


ACTION_PARENT_DIR = 9


class _DialogModule(object):
    pass


class WindowXML(object):
    """Minimal WindowXML base for script add-on tests.

    Real Kodi reads the XML from ``script_path/resources/skins/<skin>/720p``;
    this stub only records the constructor arguments and lifecycle so a test can
    drive the add-on's Python class without a renderer. Kodi's Python ``Window``
    API has no ``getId()``; the add-on proves activation with its own onInit
    flag.
    """

    def __init__(self, xml_filename="", script_path="", *args, **kwargs):
        self.xml_filename = xml_filename
        self.script_path = script_path
        self.shown = False
        self._closed = False
        self.focus_id = None
        self.actions = []

    def show(self):
        self.shown = True

    @property
    def closed(self):
        return self._closed

    def close(self):
        self._closed = True

    def setFocusId(self, control_id):
        self.focus_id = control_id

    def getControl(self, control_id):
        raise KeyError(control_id)

    def onAction(self, action):
        self.actions.append(action)

    def onClick(self, control_id):
        pass


def getCurrentWindowId():
    """Default to Home so window-close tests never poll."""
    return 10000
