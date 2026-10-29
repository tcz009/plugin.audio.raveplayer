# -*- coding: utf-8 -*-
"""xbmcaddon stub."""

import os


class Addon(object):
    def getAddonInfo(self, key):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        values = {
            "id": "plugin.audio.raveplayer",
            "name": "Rave Player",
            "version": "3.0.0",
            "path": root,
            "icon": os.path.join(root, "icon.png"),
            "fanart": os.path.join(root, "fanart.jpg"),
        }
        return values.get(key, "")

    def getSetting(self, key):
        return {
            "results_per_page": "5",
            "radio_limit": "5",
        }.get(key, "")

    def setSetting(self, key, value):
        pass

    def getLocalizedString(self, string_id):
        return str(string_id)
