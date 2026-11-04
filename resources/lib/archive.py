# -*- coding: utf-8 -*-
"""Internet Archive provider.

The Archive's advancedsearch and metadata endpoints are public, stable and
need no key, which makes them a much better backbone than scraping the dead
fan sites the 2014 add-on relied on.
"""

import re
import urllib.parse

from . import http

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/%s"
DOWNLOAD_URL = "https://archive.org/download/%s/%s"
THUMB_URL = "https://archive.org/services/img/%s"

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".ogg", ".flac", ".wav", ".aac", ".opus")
FIELDS = ["identifier", "title", "year", "date", "addeddate", "downloads", "mediatype", "creator", "description"]

SEARCH_TTL = 300
ITEM_TTL = 3600

MAX_ROWS = 500

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")

# Archive items usually carry curated ``subject`` tags.  Map the scene genres
# the add-on displays; anything unrecognised stays blank rather than guessing.
_GENRE_RULES = (
    ("Drum & Bass", re.compile(r"\b(?:drum\s*(?:&|and|n|'n')\s*bass|d\s*&\s*b|dnb)\b",
                               re.IGNORECASE)),
    ("Jungle", re.compile(r"\bjungle\b", re.IGNORECASE)),
    ("Hardcore", re.compile(r"\bhard\s*core\b", re.IGNORECASE)),
    ("House", re.compile(r"\bhouse\b", re.IGNORECASE)),
    ("UK Garage", re.compile(r"\b(?:uk\s*garage|garage|2[-\s]?step|speed\s*garage)\b",
                             re.IGNORECASE)),
    ("Techno", re.compile(r"\btechno\b", re.IGNORECASE)),
    ("Trance", re.compile(r"\btrance\b", re.IGNORECASE)),
    ("Dubstep", re.compile(r"\bdubstep\b", re.IGNORECASE)),
    ("Grime", re.compile(r"\bgrime\b", re.IGNORECASE)),
    ("Old Skool", re.compile(r"\bold\s*skool\b|\bold\s*school\b", re.IGNORECASE)),
    ("Rave", re.compile(r"\brave\b", re.IGNORECASE)),
)


def _quote(value):
    return urllib.parse.quote(str(value), safe="")


def _relative_url_path(name):
    """Return a safely quoted relative URL path for an Archive filename, or ''.

    Archive metadata is third-party input.  Reject absolute paths, backslashes,
    control characters and empty/"."/".." segments so a hostile or malformed
    filename cannot escape the item's directory (or inject URL parts) when it
    is handed to Kodi for playback.
    """
    text = str(name or "")
    if not text or text.startswith("/") or "\\" in text or _CONTROL_RE.search(text):
        return ""
    quoted = []
    for part in text.split("/"):
        if part in ("", ".", ".."):
            return ""
        quoted.append(urllib.parse.quote(part, safe=""))
    return "/".join(quoted)


def _safe_directory(value):
    """Validate/normalise Archive's item ``dir`` field for URL building."""
    if not isinstance(value, str) or not value.startswith("/"):
        return ""
    if "\\" in value or "?" in value or "#" in value or _CONTROL_RE.search(value):
        return ""
    text = value.rstrip("/")
    if not text:
        return ""
    parts = text.split("/")[1:]
    if not parts or any(part in ("", ".", "..") for part in parts):
        return ""
    return "/" + "/".join(urllib.parse.quote(part, safe="") for part in parts)


def thumb(identifier):
    return THUMB_URL % _quote(identifier)


def as_text(value):
    """Collapse whitespace and turn Archive's occasional lists into text."""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(part) for part in value)
    return " ".join(str(value or "").split())


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _genre(value):
    """Return a display genre from an item's Archive ``subject`` tags, or ""."""
    text = as_text(value)
    if not text:
        return ""
    for label, pattern in _GENRE_RULES:
        if pattern.search(text):
            return label
    return ""


def search(query, page=1, rows=50, sort="downloads desc"):
    """Return (docs, total) for an Archive.org full-text query."""
    rows = max(1, min(_as_int(rows) or 50, MAX_ROWS))
    page = max(1, _as_int(page) or 1)
    params = [
        ("q", query),
        ("rows", str(rows)),
        ("page", str(page)),
        ("output", "json"),
        ("sort[]", sort),
    ]
    params += [("fl[]", field) for field in FIELDS]
    url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
    data = http.fetch_json(url, timeout=25, ttl=SEARCH_TTL)
    if not isinstance(data, dict):
        return [], 0
    response = data.get("response")
    if not isinstance(response, dict):
        return [], 0
    docs = response.get("docs")
    if not isinstance(docs, list):
        docs = []
    docs = [doc for doc in docs if isinstance(doc, dict)]
    try:
        total = int(response.get("numFound") or 0)
    except (TypeError, ValueError):
        total = 0
    return docs, max(0, total)


def item(identifier):
    """Return the metadata dict for one Archive.org item, or {}."""
    identifier = str(identifier or "")
    if not identifier:
        return {}
    data = http.fetch_json(METADATA_URL % _quote(identifier), timeout=25, ttl=ITEM_TTL)
    return data if isinstance(data, dict) else {}


def item_title(identifier):
    """Return the item-level (pack) title, or "" when the Archive has none."""
    data = item(identifier)
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    return as_text(metadata.get("title"))


def audio_files(identifier):
    """Return playable audio files for an item, best format first, de-duplicated.

    The Archive lists every derivative it has generated next to the original,
    so a tape with MP3 originals also carries OGG copies with the same stem.
    Files are de-duplicated per folder *and* stem, which keeps ``Tape 1/01.mp3``
    and ``Tape 2/01.mp3`` (different folders) while dropping the OGG twin.
    """
    data = item(identifier)
    files = data.get("files")
    if not isinstance(files, list):
        files = []
    best = {}
    for entry in files:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        lower = name.lower()
        if not lower.endswith(AUDIO_EXTENSIONS):
            continue
        if lower.endswith(("_spectrogram.png", "_sample.mp3")):
            continue
        relative = _relative_url_path(name)
        if not relative:
            continue
        key = _file_key(name)
        rank = _rank(entry)
        current = best.get(key)
        if current is None or rank < current[0]:
            best[key] = (rank, name.lower(), entry, relative)
    ordered = sorted(best.values())
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    item_title = as_text(metadata.get("title"))
    # Prefer the item's curated subject tags; fall back to an explicit genre
    # word in the title ("Jungle", "Drum & Bass") and leave anything else blank.
    genre = _genre(metadata.get("subject")) or _genre(item_title)
    base = _direct_base(data)
    tracks = []
    for _rank_value, _name, entry, relative in ordered:
        tracks.append({
            "name": entry.get("name"),
            "title": _track_title(entry, item_title),
            "size": _as_int(entry.get("size")),
            "duration": _duration(entry.get("length")),
            "genre": genre,
            "url": (base + relative) if base
                   else DOWNLOAD_URL % (_quote(identifier), relative),
        })
    return tracks


def _direct_base(data):
    """https://<storage-node><dir>/ from item metadata, or '' to use /download/.

    archive.org/download redirects to a storage node and that redirect
    occasionally lands on a node returning HTTP 500 while the item's own
    d1/d2/server still serves the file.  Using the node directly avoids the
    bad hop; callers fall back to the old URL when metadata has no server.
    """
    if not isinstance(data, dict):
        return ""
    directory = _safe_directory(data.get("dir"))
    if not directory:
        return ""
    for key in ("d1", "server", "d2"):
        node = data.get(key)
        if not isinstance(node, str):
            continue
        node = node.strip()
        if not node or len(node) > 253 or not _HOST_RE.match(node) or ".." in node:
            continue
        # A3 defence-in-depth: a hostile d1/server value must not point Kodi at
        # an arbitrary host (loopback/LAN included).  Real Archive nodes are
        # always archive.org subdomains.
        lowered = node.lower()
        if lowered != "archive.org" and not lowered.endswith(".archive.org"):
            continue
        return "https://%s%s/" % (node, directory)
    return ""


def _file_key(name):
    """Identify one recording: same folder + same stem, any audio extension."""
    lower = name.lower()
    folder, _, base = lower.rpartition("/")
    for extension in AUDIO_EXTENSIONS:
        if base.endswith(extension):
            base = base[: -len(extension)]
            break
    return folder, base


def _duration(value):
    """Return seconds from the Archive's ``length`` field, or None."""
    if isinstance(value, (int, float)):
        try:
            number = int(value)
        except (ValueError, OverflowError):
            return None
        return number if number > 0 else None
    text = as_text(value)
    if not text:
        return None
    if ":" in text:
        try:
            parts = [int(part) for part in re.findall(r"\d+", text)[:3]]
        except (ValueError, OverflowError):
            return None
        if not parts:
            return None
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + part
        return seconds or None
    try:
        seconds = int(float(text))
    except (TypeError, ValueError, OverflowError):
        return None
    return seconds if seconds > 0 else None


def _track_title(entry, item_title):
    """Return something a human can pick from a list.

    Archive rips are inconsistent: sometimes the only useful label is the
    filename ("TAPE 3 - MASTERVIBE.mp3"), sometimes every file repeats the
    same generic title ("Dreamscape XIX Arena 2"). Prefer a descriptive
    filename, then a distinct per-track title, then a tidied filename.
    """
    pretty = _pretty(entry.get("name"))
    title = as_text(entry.get("title"))
    if _is_descriptive(pretty):
        return pretty
    if title and title != item_title:
        return title
    return pretty


def _is_descriptive(text):
    text = as_text(text)
    if not text or len(text) < 5:
        return False
    if re.match(r"^(track|audio|file|part)?\s*\d+$", text, re.IGNORECASE):
        return False
    return bool(re.search(r"[A-Za-z]", text))


def _rank(entry):
    source = str(entry.get("source") or "").lower()
    if source == "original":
        return 0
    fmt = str(entry.get("format") or "").lower()
    if fmt in ("vbr mp3", "mp3"):
        return 1
    return 2


def _pretty(name):
    text = as_text(name)
    if not text:
        return "Untitled"
    base = text.split("/")[-1]
    for extension in AUDIO_EXTENSIONS:
        if base.lower().endswith(extension):
            base = base[: -len(extension)]
            break
    return base.replace("_", " ").strip() or "Untitled"
