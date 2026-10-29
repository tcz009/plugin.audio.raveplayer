# -*- coding: utf-8 -*-
"""DNBRADIO.com archive — present-day jungle and drum & bass shows.

The recordings index lists recent mixes with ids; each listen page carries a
direct MP3 behind an archive proxy, so the stream URL is resolved on demand.
"""

import html as html_module
import re
import urllib.parse

from . import http

BASE = "https://dnbradio.com"
RECORDINGS = BASE + "/recordings"

MIX_RE = re.compile(r'href="/listen\?mix=(\d+)"\s+title="([^"]+)"', re.IGNORECASE)
MP3_RE = re.compile(r'https?://[^"\'\s>]+\.mp3[^"\'\s<]*', re.IGNORECASE)


def parse_recordings(body):
    """Parse the recordings page HTML into mix dicts (no I/O)."""
    if not body:
        return []
    seen, result = set(), []
    for mix_id, title in MIX_RE.findall(body):
        if mix_id in seen:
            continue
        seen.add(mix_id)
        clean = html_module.unescape(title).replace(" on DNBRADIO", "").strip()
        date, _, show = clean.partition(" : ")
        result.append({
            "id": mix_id,
            "title": show.strip() or clean,
            "date": date.strip(),
        })
    return result


def mixes():
    return parse_recordings(http.fetch(RECORDINGS, timeout=25, headers={"Referer": BASE + "/"}))


def parse_listen(page):
    """Extract the MP3 URL from a listen page HTML (no I/O)."""
    if not page:
        return ""
    match = MP3_RE.search(page)
    if not match:
        return ""
    return html_module.unescape(match.group(0)).replace("&amp;", "&")


def stream_url(mix_id):
    """Resolve a mix id to a playable MP3 URL, or '' if the page changed."""
    return parse_listen(http.fetch("%s/listen?mix=%s" % (BASE, mix_id), timeout=25,
                                   headers={"Referer": RECORDINGS}))


def link(mix_id):
    return "%s/listen?mix=%s" % (BASE, urllib.parse.quote(str(mix_id)))
