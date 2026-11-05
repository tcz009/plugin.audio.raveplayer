# -*- coding: utf-8 -*-
"""The "Latest" view: newest from every source, merged and date-sorted.

Sources emit different date shapes (RFC 822 from feeds, ISO from DNBRADIO,
year/date strings from the Archive), so everything is normalised to a
`datetime` here and undated items sort last.
"""

import datetime
import random
import re

from . import archive, dnbradio, feeds, kodi

RAVE_COLLECTION = "collection:ravetapes AND mediatype:audio"
RANDOM_PAGE_CAP = 200

# Latest resolves DNB stream URLs while building the folder (see
# resolve_dnb_streams); short+parallel so an unreachable host is cheap.
DNB_RESOLVE_TIMEOUT = dnbradio.RESOLVE_TIMEOUT
DNB_RESOLVE_WORKERS = dnbradio.RESOLVE_WORKERS

# Feed fetches run in a bounded thread pool (K3 follow-up).  The HTTP
# route budget is still shared by every worker, so the whole Latest build
# remains bounded by that budget.
FEED_FETCH_WORKERS = feeds.FEED_WORKERS


def parse_date(value):
    """Best-effort date parsing across the sources; returns None if unknown."""
    if not value:
        return None
    text = str(value).strip()
    # ISO-ish: 2026-10-29, 2026-10-29T13:07:23Z
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        try:
            return datetime.datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    # RFC 822: Mon, 19 Jan 2026 11:51:21 +0000
    try:
        from email.utils import parsedate_to_datetime
        parsed = parsedate_to_datetime(text)
        if parsed:
            return parsed.replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _title(doc, fallback):
    """Archive titles are occasionally lists; always return clean text."""
    return archive.as_text(doc.get("title")) or str(fallback)


def recent_episodes(per_feed=6, workers=FEED_FETCH_WORKERS):
    items = []
    for entry, episodes in feeds.episodes_many(feeds.registry(), limit=per_feed,
                                              workers=workers):
        for episode in episodes:
            when = parse_date(episode.get("published"))
            items.append({
                "kind": "episode",
                "title": archive.as_text(episode.get("title")) or "Untitled",
                "url": episode["url"],
                "source": entry["name"],
                "when": when,
                "duration": episode.get("duration"),
            })
    return items


def recent_packs(rows=20):
    docs, _ = archive.search(RAVE_COLLECTION, rows=rows, sort="addeddate desc")
    items = []
    for doc in docs:
        identifier = doc.get("identifier")
        if not identifier:
            continue
        items.append({
            "kind": "pack",
            "title": _title(doc, identifier),
            "identifier": identifier,
            "source": "Rave Tape Packs",
            "when": parse_date(doc.get("addeddate") or doc.get("date")),
            "year": doc.get("year"),
        })
    return items


def recent_dnb(limit=12):
    items = []
    for show in dnbradio.mixes()[:limit]:
        items.append({
            "kind": "dnb",
            "title": archive.as_text(show.get("title")) or "Untitled",
            "id": show["id"],
            "source": "DNB Radio",
            "when": parse_date(show.get("date")),
        })
    return items


def merge(limit=60):
    # The three sources are independent; fetch them concurrently so a slow
    # Archive/DNB response does not add to the feed time.  Results are retrieved
    # in source order to keep the pre-sort ordering deterministic.  The HTTP
    # route budget and cache are shared by the workers (thread-safe since 3.9.12).
    groups = []
    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(recent_episodes), pool.submit(recent_packs),
                       pool.submit(recent_dnb)]
            for future in futures:
                try:
                    groups.append(future.result())
                except Exception:
                    groups.append([])
    except Exception:
        groups = [recent_episodes(), recent_packs(), recent_dnb()]
    items = groups[0] + groups[1] + groups[2]
    dated = [item for item in items if item.get("when")]
    undated = [item for item in items if not item.get("when")]
    dated.sort(key=lambda item: item["when"], reverse=True)
    return (dated + undated)[:limit]


def resolve_dnb_streams(items, timeout=DNB_RESOLVE_TIMEOUT, workers=DNB_RESOLVE_WORKERS):
    """Resolve the stream URL for every DNB row in one concurrent batch.

    Kodi must never be handed a playable row that cannot resolve: when the
    host is unreachable it treats the mixed folder as a playlist and auto-
    advances down it item after item (the "Latest cascade").  Rows whose listen
    page cannot be fetched are absent from the result, so the caller drops them
    instead of offering a dead item.

    Returns ``{mix_id: stream_url}`` for the rows that resolved.
    """
    mix_ids = []
    for item in items or []:
        if item.get("kind") != "dnb":
            continue
        mix_id = str(item.get("id") or "").strip()
        if mix_id:
            mix_ids.append(mix_id)
    if not mix_ids:
        return {}
    try:
        return dnbradio.stream_urls(mix_ids, timeout=timeout, workers=workers)
    except Exception as exc:  # a resolution failure must not empty the whole screen
        kodi.log("Latest: DNB stream resolution failed (%s)" % exc, level=30)
        return {}


RANDOM_PICK_ATTEMPTS = 3


def random_pack(attempts=RANDOM_PICK_ATTEMPTS):
    """Pick a random tape pack, with a small bounded retry.

    3.9.51: a single Archive search can return an empty page (transient
    ``numFound`` drift, rate limiting, a page past the end) and the Surprise
    then reported "No random pack found" intermittently. Three attempts with a
    fresh page are bounded; the caller (the screen) still has its own bounded
    fallback, so nothing here loops indefinitely.
    """
    try:
        attempts = max(1, min(int(attempts), 5))
    except (TypeError, ValueError):
        attempts = RANDOM_PICK_ATTEMPTS
    per_page = 50
    last_page = 1
    for _attempt in range(attempts):
        try:
            _, total = archive.search(RAVE_COLLECTION, rows=1)
        except Exception:
            continue
        if not total:
            continue
        pages = max(1, (total + per_page - 1) // per_page)
        last_page = max(1, min(RANDOM_PAGE_CAP, pages))
        page = random.randint(1, last_page)
        try:
            docs, _ = archive.search(RAVE_COLLECTION, page=page, rows=per_page)
        except Exception:
            continue
        candidates = [doc for doc in docs or []
                      if isinstance(doc, dict) and doc.get("identifier")]
        if not candidates:
            continue
        doc = random.choice(candidates)
        identifier = doc.get("identifier")
        return {
            "identifier": identifier,
            "title": _title(doc, identifier),
        }
    return None


def year_query(year):
    return "%s AND date:[%d-01-01 TO %d-12-31]" % (RAVE_COLLECTION, year, year)
