# -*- coding: utf-8 -*-
"""xbmcaddon stub."""

import atexit
import os
import shutil
import tempfile


PROFILE = os.path.join(tempfile.gettempdir(), "raveplayer-test-profile")

# Every test process gets its own cache directory.  Sharing
# /tmp/raveplayer-cache between runs made a Toronto/parsed-page test depend on
# whether an earlier run had warmed the cache (and on the order inside one
# run).  An explicit RAVEPLAYER_CACHE_DIR from the harness still wins, which is
# what the temp-cache matrix exercises.
_TEST_CACHE = tempfile.mkdtemp(prefix="raveplayer-test-cache-")
os.environ.setdefault("RAVEPLAYER_CACHE_DIR", _TEST_CACHE)
atexit.register(shutil.rmtree, _TEST_CACHE, True)


class Addon(object):
    def __init__(self, addon_id="plugin.audio.raveplayer"):
        self.addon_id = addon_id

    def getAddonInfo(self, key):
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        values = {
            "id": "plugin.audio.raveplayer",
            "name": "Rave Player",
            "version": "3.0.0",
            "path": root,
            "profile": PROFILE,
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
