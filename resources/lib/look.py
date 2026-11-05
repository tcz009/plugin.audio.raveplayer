# -*- coding: utf-8 -*-
"""The 2026 Rave Player look, in one place.

This module is intentionally tiny and dependency-free: it is the single source
of truth for the visual vocabulary shared by the plugin's native lists and the
Rave Screen *script* (which imports it read-only where it can).  It carries no
routing, networking or caching code.

The values mirror ``docs/rave-screen/RAVE-SCREEN-DESIGN.md`` §9 exactly.  The
native Kodi list cannot draw the Rave Screen's custom furniture (focus plates,
baked Impact labels, scanlines); what it *can* do is keep the same semantics:

* one sticker per destination (a tape pack is a tape, live radio is a radio),
* a square pack cover in the art slot and a 16:9 fanart behind it,
* a short Label2 fact and a visible description,
* a coloured status line for empty/error states instead of a dead directory.

Kodi markup colours are ``0xAARRGGBB``.  The helpers below only ever emit
``[COLOR 0xAARRGGBB]…[/COLOR]``.
"""

# Colour tokens — docs/rave-screen/RAVE-SCREEN-DESIGN.md §9.1.
TOKENS = {
    "ink": "0xFF07070B",
    "ink_2": "0xFF0B0B11",
    "paper": "0xFFF2EEE3",
    "muted": "0xFFA8A399",
    "acid": "0xFFE8FF00",
    "magenta": "0xFFFF2D8F",
    "cyan": "0xFF22E6FF",
    "orange": "0xFFFF6A1A",
}

# Design spec §4.2: cosmetic print furniture only, never a routing key.
RP_CODES = {
    "latest": "RP-01",
    "surprise": "RP-02",
    "packs_menu": "RP-03",
    "favourites": "RP-12",
    "fav_list": "RP-12",
    "downloads": "RP-05",
    "downloads_menu": "RP-05",
    "pirate_radio": "RP-19",
    "shows_menu": "RP-27",
    "radio_menu": "RP-31",
    "search": "RP-44",
    "about": "RP-99",
    "screen": "RP-00",
}

# Status line tags.  Empty is a standby condition, error is a signal fault,
# loading is in-flight.  One spot colour per surface (design §9.1).
STATUS = {
    "empty": ("E8FF00", "STANDBY"),
    "error": ("FF2D8F", "ERROR"),
    "loading": ("22E6FF", "LOADING"),
}


def rp_code(mode):
    """Return the print code for a route mode ("" when not part of the map)."""
    return RP_CODES.get(str(mode or ""), "")


def colour(name, fallback="paper"):
    """Return one ARGB colour token."""
    return TOKENS.get(str(name), TOKENS.get(fallback, TOKENS["paper"]))


def marked(text, name="paper", bold=False):
    """Wrap display text in a Kodi colour (and optional bold) markup."""
    body = "[B]%s[/B]" % text if bold else str(text)
    return "[COLOR %s]%s[/COLOR]" % (colour(name), body)
