# -*- coding: utf-8 -*-
"""Screens package for the full-screen Rave Screen.

New screen data/action modules live here so the main shell
(``raveui/window.py``, ``raveui/controller.py`` and the skin XML) can stay a
thin adapter.  Every module in this package is pure Python: it can be imported
and tested without ``xbmc``/``xbmcgui`` or a device.
"""

from .live import LiveRadio, LiveTrack, Row, Station, StationState, load_stations

__all__ = [
    "LiveRadio",
    "LiveTrack",
    "Row",
    "Station",
    "StationState",
    "load_stations",
]
