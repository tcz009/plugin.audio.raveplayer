# -*- coding: utf-8 -*-
"""Rave Player 3.0 — Kodi plugin entry point.

Rebuilt in 2026 from the 2014 original. Python 3 only, no third-party
dependencies: everything comes from Kodi itself and the standard library.
"""

import sys
import traceback

import xbmc

from resources.lib import kodi, routes


def _maybe_launch_screen(argv):
    """Opening the add-on should go straight into the full-screen app.

    The classic directory menu remains the fallback (and is reachable from the
    screen); this only changes what a normal add-on launch does.
    """
    args = list(argv or [])
    params = {}
    for part in args[2:]:
        part = part.lstrip("?")
        if "=" in part:
            key, _, value = part.partition("=")
            params[key.lstrip("?")] = value
    mode = params.get("mode")
    if mode not in (None, ""):
        return False
    try:
        if not bool(xbmc.getCondVisibility(
                "System.AddonIsEnabled(%s)" % routes.RAVE_SCREEN_ADDON)):
            return False
        xbmc.executebuiltin("RunScript(%s)" % routes.RAVE_SCREEN_ADDON)
        return True
    except Exception:  # noqa: BLE001 - fall back to the classic menu
        return False


def main(argv=None):
    """Run one plugin invocation; never let an error escape to Kodi."""
    try:
        args = sys.argv if argv is None else argv
        if _maybe_launch_screen(args):
            return
        routes.dispatch(args)
    except Exception:  # last-resort guard (dispatch already handles its own)
        kodi.log("fatal: unhandled plugin error\n%s" % traceback.format_exc(), level=40)


if __name__ == "__main__":
    main()
