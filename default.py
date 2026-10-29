# -*- coding: utf-8 -*-
"""Rave Player 3.0 — Kodi plugin entry point.

Rebuilt in 2026 from the 2014 original. Python 3 only, no third-party
dependencies: everything comes from Kodi itself and the standard library.
"""

import sys

from resources.lib import routes


if __name__ == "__main__":
    routes.dispatch(sys.argv)
