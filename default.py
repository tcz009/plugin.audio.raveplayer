# -*- coding: utf-8 -*-
"""Rave Player 3.0 — Kodi plugin entry point.

Rebuilt in 2026 from the 2014 original. Python 3 only, no third-party
dependencies: everything comes from Kodi itself and the standard library.
"""

import sys
import traceback

from resources.lib import kodi, routes


def main(argv=None):
    """Run one plugin invocation; never let an error escape to Kodi."""
    try:
        routes.dispatch(sys.argv if argv is None else argv)
    except Exception:  # last-resort guard (dispatch already handles its own)
        kodi.log("fatal: unhandled plugin error\n%s" % traceback.format_exc(), level=40)


if __name__ == "__main__":
    main()
