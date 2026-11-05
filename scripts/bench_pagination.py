#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermetic Kodi pagination benchmark (stubs, no Kodi, no network).

Every source is replaced with a deterministic in-memory list, then the real
route handlers build each page.  This measures the add-on's own paging and
row-building cost; it is *not* a device benchmark (run test/run.py on the
device for cold network timings).

    python3 scripts/bench_pagination.py --samples 5 [--json out.json]
"""

import argparse
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "test", "stubs"))
sys.path.insert(0, ROOT)

import xbmcplugin  # noqa: E402

from resources.lib import routes  # noqa: E402

PAGE = 50


def toronto_rows(count):
    return [{"name": "Toronto mix %04d" % index,
             "url": "https://toronto.example/files/%d.mp3" % index}
            for index in range(count)]


def moxser_rows(count):
    return [{"title": "Mox mix %04d" % index,
             "page_url": "https://moxser.com/mixes/%d" % index,
             "date": "2026-01-01", "flyer": ""} for index in range(count)]


def jt_rows(count):
    return [{"key": "show-%04d" % index, "name": "Show %04d" % index}
            for index in range(count)]


def rave_rows(count):
    return [{"name": "Rave %03d" % index, "slug": "rave-%03d" % index,
             "count": index, "mixcloud_count": 0} for index in range(count)]


def download_rows(count):
    return [{"title": "Download %04d" % index, "exists": False,
             "key": "dl-%04d" % index, "source": "Archive.org",
             "added": "2026-01-02"} for index in range(count)]


def station_rows(count):
    return [{"name": "Station %04d" % index,
             "url": "https://stream-%04d.example.test/live" % index,
             "favicon": ""} for index in range(count)]


def archive_tracks(count):
    return [{"title": "Tape %04d" % index,
             "url": "https://archive.org/download/p/%d.mp3" % index,
             "duration": 180} for index in range(count)]


def install_fixtures():
    routes._playable_url = lambda value: value
    routes.toronto_source.tracks = lambda genre: toronto_rows(2640)
    routes.moxser_source.mixes = lambda limit=0: moxser_rows(1001)
    routes.legacy.jungle_shows = lambda: jt_rows(310)
    routes._rave_catalog = lambda: rave_rows(55)
    routes.downloads.list_downloads = lambda: download_rows(120)
    routes.radio.stations = lambda tag, limit=500: station_rows(500)
    routes.radio.display = lambda station: (station["name"], "live")
    routes.radio.stream_url = lambda station: station["url"]
    routes.archive.audio_files = lambda identifier: archive_tracks(1645)
    routes.archive.thumb = lambda identifier: "/tmp/cover.jpg"
    routes.archive.item_title = lambda identifier: "Helter Skelter"
    docs = [{"identifier": "pack-%04d" % index, "title": "Pack %04d" % index}
            for index in range(2400)]
    routes.archive.search = lambda query, page=1, rows=50, sort="": (
        docs[(page - 1) * rows:page * rows], len(docs))
    routes._rows_per_page = lambda: PAGE


def render(route, params):
    del xbmcplugin.ITEMS[:]
    started = time.perf_counter()
    route(1, dict(params))
    elapsed = (time.perf_counter() - started) * 1000.0
    return len(xbmcplugin.ITEMS), elapsed


def bench(route, params, samples):
    _rows, cold = render(route, params)
    warm = [render(route, params)[1] for _ in range(samples)]
    return {
        "page": int(params.get("page", 1)),
        "rows": _rows,
        "cold_ms": round(cold, 2),
        "warm_p50_ms": round(statistics.median(warm), 2),
        "warm_p95_ms": round(sorted(warm)[max(0, int(len(warm) * 0.95) - 1)], 2),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)
    install_fixtures()
    cases = [
        ("Toronto 2,640", routes.toronto_genre, {"genre": "jungle", "page": 1}),
        ("Toronto 2,640", routes.toronto_genre, {"genre": "jungle", "page": 53}),
        ("Moxser 1,001", routes.moxser, {"page": 1}),
        ("Moxser 1,001", routes.moxser, {"page": 21}),
        ("JungleTapes 310", routes.legacy_jt, {"page": 1}),
        ("JungleTapes 310", routes.legacy_jt, {"page": 7}),
        ("Rave Nights 55", routes.rave_nights, {"page": 1}),
        ("Rave Nights 55", routes.rave_nights, {"page": 2}),
        ("Downloads 120", routes.downloads_menu, {"page": 1}),
        ("Downloads 120", routes.downloads_menu, {"page": 3}),
        ("Live radio 500", routes.radio_tag, {"key": "jungle", "page": 1}),
        ("Live radio 500", routes.radio_tag, {"key": "jungle", "page": 10}),
        ("Pack 1,645", routes.archive_item, {"id": "helter", "page": 1}),
        ("Pack 1,645", routes.archive_item, {"id": "helter", "page": 33}),
        ("Search 2,400", routes.search, {"q": "pack", "page": 1}),
        ("Search 2,400", routes.search, {"q": "pack", "page": 48}),
    ]
    results = [(label, bench(route, params, args.samples))
               for label, route, params in cases]
    print("| List | Page | Rows | Cold ms | Warm p50 ms | Warm p95 ms |")
    print("|---|---|---|---|---|---|")
    for label, row in results:
        print("| %s | %s | %s | %s | %s | %s |" % (
            label, row["page"], row["rows"], row["cold_ms"],
            row["warm_p50_ms"], row["warm_p95_ms"]))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump([{"list": label, **row} for label, row in results],
                      handle, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
