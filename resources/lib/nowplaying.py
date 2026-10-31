# -*- coding: utf-8 -*-
"""Best-effort "now playing" metadata parsed from Archive and tape titles.

FEATURES #9 wants the pack cover and the DJ/venue/date shown while a tape
plays.  The Archive's titles are free text ("Dreamscape_3_-_Absolutely_No_
Compromise_10.3.92", "Tape 1 - Carl Cox"), so this module never guesses: every
field is optional, unknown text is left alone, and an unmatched title produces
no extra plot text.

The vocabulary comes from the add-on's own data files (``rave-catalog.json``
and ``filters.json``), so new researched names work without a code change.
"""

import datetime
import json
import os
import re

_MONTHS = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)
_MONTH_ABBRS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
_MONTH_WORDS = _MONTHS + tuple(abbr.lower() for abbr in _MONTH_ABBRS)
_MONTH_WORDS = tuple(sorted(set(_MONTH_WORDS), key=len, reverse=True))
_MONTH_RE = "|".join(_MONTH_WORDS)
_MONTH_NUMBERS = {}
for _index, _name in enumerate(_MONTHS, 1):
    _MONTH_NUMBERS[_name] = _index
    _MONTH_NUMBERS[_name[:3]] = _index

# 10.3.92 / 10/03/1992 / 10-3-92 -- UK rave titles are day-first.
_DOTTED_DATE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})(?!\d)")
# 27th Nov 1993 / 27 November '93
_DAY_MONTH_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(%s)\.?,?\s+'?(\d{2,4})(?!\d)" % _MONTH_RE,
    re.IGNORECASE,
)
# April 2nd 1994 / Nov 27, 1993
_MONTH_DAY_DATE = re.compile(
    r"\b(%s)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+'?(\d{2,4})(?!\d)" % _MONTH_RE,
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(19[5-9]\d|20[0-2]\d)\b")

# Common oldskool/jungle/hardcore/garage DJs.  Longest names are tried first so
# "DJ Hype" wins over "Hype" and "Jumping Jack Frost" over "Frost".
DJ_NAMES = (
    "Andy C", "Bad Company", "Brockie", "Bryan Gee", "Carl Cox", "Darren Jay",
    "Dillinja", "DJ Die", "DJ Hype", "DJ Rap", "DJ SS", "Doc Scott",
    "Easygroove", "Ellis Dee", "Fabio", "Friction", "Goldie", "Grooverider",
    "Hype", "Jumping Jack Frost", "Jumpin Jack Frost", "Kenny Ken", "Krust",
    "LTJ Bukem", "Mampi Swift", "Mickey Finn", "Nicky Blackmarket", "Randall",
    "Ratpack", "Ray Keith", "Roni Size", "Seduction", "Shimon", "Slipmatt",
    "SS", "Storm", "Suv", "Top Buzz", "Vibes", "Zinc",
)

_DJ_PREFIX = re.compile(r"\bDJ\s+([A-Za-z][A-Za-z0-9'’.-]*(?:\s+[A-Za-z][A-Za-z0-9'’.-]*){0,2})")
_DJ_STOPWORDS = frozenset(
    ("a", "and", "at", "b", "live", "mix", "part", "recorded", "set", "show",
     "side", "tape", "the", "vol", "volume")
)

_RESOURCES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VOCABULARY = None


def _text(value):
    """Collapse lists/whitespace into a plain string."""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(part) for part in value)
    return " ".join(str(value or "").split())


def _normalise(text):
    """Case/punctuation-insensitive phrase form for vocabulary matching."""
    text = _text(text).casefold().replace("’", "'")
    text = re.sub(r"['`]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " " + " ".join(text.split()) + " "


def _load_names():
    """Return the researched catalogue + quick-filter names, longest first."""
    names = []
    for filename in ("rave-catalog.json", "filters.json"):
        path = os.path.join(_RESOURCES, filename)
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        for entry in data if isinstance(data, list) else []:
            if isinstance(entry, dict):
                name = entry.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
    seen = {}
    for name in names:
        key = _normalise(name).strip()
        if key:
            seen.setdefault(key, name)
    return sorted(seen.items(), key=lambda item: len(item[0]), reverse=True)


def _vocabulary():
    global _VOCABULARY
    if _VOCABULARY is None:
        _VOCABULARY = _load_names()
    return _VOCABULARY


def _expand_year(value):
    year = int(value)
    if year < 100:
        year += 2000 if year <= 26 else 1900
    return year if 1900 <= year <= 2030 else 0


def _format_date(day, month, year):
    """Return "10 Mar 1992", or "" for an impossible date."""
    year = _expand_year(year)
    month = int(month)
    if not (1 <= month <= 12 and year):
        return ""
    try:
        datetime.date(year, month, int(day))
    except ValueError:
        return ""
    return "%02d %s %d" % (int(day), _MONTH_ABBRS[month - 1], year)


def find_date(text):
    """Return the first recognisable date in ``text`` as display text, or ""."""
    text = _text(text)
    if not text:
        return ""
    match = _DOTTED_DATE.search(text)
    if match:
        formatted = _format_date(match.group(1), match.group(2), match.group(3))
        if formatted:
            return formatted
    match = _DAY_MONTH_DATE.search(text)
    if match:
        month = _MONTH_NUMBERS[match.group(2).lower()]
        formatted = _format_date(match.group(1), month, match.group(3))
        if formatted:
            return formatted
    match = _MONTH_DAY_DATE.search(text)
    if match:
        month = _MONTH_NUMBERS[match.group(1).lower()]
        formatted = _format_date(match.group(2), month, match.group(3))
        if formatted:
            return formatted
    match = _YEAR.search(text)
    return match.group(1) if match else ""


def _match_vocabulary(text):
    """Return the longest researched promotion/venue/station named in text."""
    normalised = _normalise(text)
    if not normalised.strip():
        return ""
    for key, display in _vocabulary():
        if " " + key + " " in normalised:
            return display
    return ""


def _match_known_dj(text):
    normalised = _normalise(text)
    if not normalised.strip():
        return ""
    for name in sorted(DJ_NAMES, key=lambda item: len(item), reverse=True):
        key = _normalise(name).strip()
        if key and " " + key + " " in normalised:
            return name
    match = _DJ_PREFIX.search(_text(text))
    if match:
        words = [word for word in match.group(1).split() if word.lower() not in _DJ_STOPWORDS]
        if words:
            return " ".join(words)
    return ""


def parse(pack_title="", track_title=""):
    """Parse a pack title and a track title into artist/venue/date fields.

    Returns a dict with three strings (empty when unknown).  The track title is
    preferred for the DJ; the pack title is preferred for the event and date.
    """
    pack_title = _text(pack_title)
    track_title = _text(track_title)
    return {
        "artist": _match_known_dj(track_title) or _match_known_dj(pack_title),
        "venue": _match_vocabulary(pack_title) or _match_vocabulary(track_title),
        "date": find_date(pack_title) or find_date(track_title),
    }


def summary(details):
    """Return the non-empty fields joined for a plot line."""
    if not isinstance(details, dict):
        return ""
    return " · ".join(
        str(details.get(key) or "").strip()
        for key in ("artist", "venue", "date")
        if str(details.get(key) or "").strip()
    )


def plot(base_plot, details):
    """Prefix ``base_plot`` with the parsed details, keeping the old text.

    An empty/unknown result returns ``base_plot`` untouched, so existing plots
    (and their tests) keep working.
    """
    base_plot = _text(base_plot)
    parsed = summary(details)
    if not parsed:
        return base_plot
    if not base_plot:
        return parsed
    return "%s — %s" % (parsed, base_plot)
