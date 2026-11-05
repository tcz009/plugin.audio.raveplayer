# -*- coding: utf-8 -*-
"""Rave Screen — script.raveplayer.ui entry point.

This is a normal Kodi script add-on: it owns one full-screen ``WindowXML``
window. It never opens an overlay over the plugin directory. Back closes the
window; the script then exits and Kodi returns to wherever the user launched it.
"""

import os
import sys
import traceback

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)


def main():
    try:
        from raveui.window import open_screen

        open_screen()
    except Exception:  # noqa: BLE001 - a script must never take Kodi down
        try:
            import xbmc

            xbmc.log("[script.raveplayer.ui] fatal:\n%s" % traceback.format_exc(),
                     level=xbmc.LOGERROR)
        except Exception:
            pass


if __name__ == "__main__":
    main()
