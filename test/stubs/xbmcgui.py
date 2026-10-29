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


class ListItem(object):
    def __init__(self, label="", path=""):
        self.label = label
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

    def setLabel(self, label):
        self.label = label


class _DialogModule(object):
    pass
