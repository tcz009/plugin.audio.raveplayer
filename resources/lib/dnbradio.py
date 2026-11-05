# -*- coding: utf-8 -*-
"""DNBRADIO.com archive — present-day jungle and drum & bass shows.

The recordings index lists recent mixes with ids; each listen page carries a
direct MP3 behind an archive proxy, so the stream URL is resolved on demand.
"""

import html as html_module
import re
import urllib.parse

from . import cache, http, kodi

BASE = "https://dnbradio.com"
RECORDINGS = BASE + "/recordings"
RECORDINGS_TTL = 10 * 60
STREAM_TTL = 6 * 60 * 60
# One small disk entry maps mix id -> resolved MP3 for the whole batch.  A warm
# Latest used to spawn one worker per DNB row purely to re-read and re-regex
# one listen page each; the map makes the warm path zero threads, one read.
STREAM_MAP_KEY = "dnbradio:streams:v1"
STREAM_MAP_MAX = 200

# Directory builds resolve several mixes at once; keep the batch short so an
# unreachable host cannot stall the "Latest" folder.
RESOLVE_TIMEOUT = 3.0
RESOLVE_WORKERS = 8

MIX_RE = re.compile(r'href="/listen\?mix=(\d+)"\s+title="([^"]+)"', re.IGNORECASE)
MP3_RE = re.compile(r'(?:href|src)="(https?://[^"]+?\.mp3[^"]*)"', re.IGNORECASE)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
        date, separator, show = clean.partition(" : ")
        # The page's title attribute is "2026-10-29 : DJ - Show".  If a page
        # ever loses the separator, do not present the whole string as both
        # the title and the date.
        if separator and DATE_RE.match(date.strip()):
            result.append({
                "id": mix_id,
                "title": show.strip() or clean,
                "date": date.strip(),
            })
        else:
            result.append({"id": mix_id, "title": clean or "Untitled", "date": ""})
    return result


def mixes():
    return parse_recordings(
        http.fetch(RECORDINGS, timeout=25, headers={"Referer": BASE + "/"}, ttl=RECORDINGS_TTL)
    )


def parse_listen(page):
    """Extract the MP3 URL from a listen page HTML (no I/O)."""
    if not page:
        return ""
    match = MP3_RE.search(page)
    if not match:
        return ""
    return html_module.unescape(match.group(1))


def stream_url(mix_id, timeout=25):
    """Resolve a mix id to a playable MP3 URL, or '' if the page changed."""
    return parse_listen(http.fetch(link(mix_id), timeout=timeout,
                                  headers={"Referer": RECORDINGS}, ttl=STREAM_TTL))


def _cached_streams():
    value = cache.get(STREAM_MAP_KEY, STREAM_TTL)
    return value if isinstance(value, dict) else {}


def _remember_streams(found):
    """Merge resolved ids into the batch map (best effort, bounded)."""
    if not found:
        return
    merged = _cached_streams()
    merged.update(found)
    if len(merged) > STREAM_MAP_MAX:
        # Dicts keep insertion order; drop the oldest ids first.
        for key in list(merged)[: len(merged) - STREAM_MAP_MAX]:
            merged.pop(key, None)
    cache.put(STREAM_MAP_KEY, merged, sync=False)


def stream_urls(mix_ids, timeout=RESOLVE_TIMEOUT, workers=RESOLVE_WORKERS):
    """Resolve several mix ids concurrently, dropping the ones that fail.

    Returns ``{mix_id: mp3_url}`` for the ids that resolved.  Directory builds
    must stay snappy, so the requests run in parallel with a short timeout: an
    unreachable host costs one timeout, not one per row.  Failed ids are simply
    absent so the caller can drop the dead playable row instead of shipping it.

    A small disk map caches the batch resolutions for the same 6 h as the
    listen pages they came from, so a warm directory resolves with one cache
    read and no worker threads.
    """
    unique = []
    for mix_id in mix_ids or []:
        text = str(mix_id or "").strip()
        if text and text not in unique:
            unique.append(text)
    if not unique:
        return {}
    known = _cached_streams()
    found = {mix_id: known[mix_id] for mix_id in unique if known.get(mix_id)}
    missing = [mix_id for mix_id in unique if mix_id not in found]
    if not missing:
        return found
    if len(missing) == 1:
        url = stream_url(missing[0], timeout=timeout)
        if url:
            found[missing[0]] = url
            _remember_streams({missing[0]: url})
        return found
    try:
        from concurrent.futures import ThreadPoolExecutor

        count = max(1, min(int(workers or 1), len(missing)))
        with ThreadPoolExecutor(max_workers=count) as pool:
            jobs = [(pool.submit(stream_url, mix_id, timeout), mix_id)
                    for mix_id in missing]
            for job, mix_id in jobs:
                try:
                    url = job.result()
                except Exception as exc:  # one bad page must not drop the batch
                    kodi.log("DNB stream resolve failed for mix %s (%s)" % (mix_id, exc), level=30)
                    continue
                if url:
                    found[mix_id] = url
    except Exception as exc:  # never let the batch take the directory down
        kodi.log("DNB stream batch failed (%s)" % exc, level=30)
        return found
    _remember_streams({mix_id: found[mix_id] for mix_id in missing
                       if mix_id in found})
    return found


def link(mix_id):
    return "%s/listen?mix=%s" % (BASE, urllib.parse.quote(str(mix_id)))
