#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Route-level timing harness for the Kodi add-on (perf/overhaul-3.9.49).

`bench_sources.py` measures provider stages (fetch / cache / parse).  This
script measures what Kodi actually calls: ``routes.dispatch()`` for one menu
mode, cold (empty disk cache) and warm (cache populated), plus the import cost
of a fresh plugin process for the root menu.

    python3 scripts/bench_routes.py --samples 5 --cold-samples 1
    python3 scripts/bench_routes.py --only root,legacy_index,legacy_category
    python3 scripts/bench_routes.py --json /tmp/routes-kodi.json

RTP hosts are replayed from ``test/fixtures/bench`` (same bytes, simulated
upstream latency) exactly like ``bench_sources.py``; every other source is
live.  ``--replay all`` keeps the whole run offline.

The timing harness never writes to the repo cache: it uses the throwaway
``RAVEPLAYER_CACHE_DIR`` that ``bench_sources`` already configured.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import bench_sources as bs  # noqa: E402  (configures env + imports providers)

HARNESS = bs.KodiHarness()
routes = HARNESS.routes
# The tuning spinner is a UI thread, not play-start latency: disable it so a
# measurement does not start a GUI thread in the stub environment.
routes._start_tuning_spinner = lambda label: None
legacy = bs.legacy
toronto = bs.toronto
moxser = bs.moxser


def _safe(call, fallback=None):
    try:
        return call()
    except Exception:  # noqa: BLE001 - discovery must never abort the bench
        return fallback


def discover():
    """Resolve a few identifiers up front (not timed)."""
    ids = {"archive_id": None, "jt_show": None, "moxser_page_url": None,
           "rtp_pack": None, "rtp_post": None, "rtp_cat": "331",
           "archive_track": None, "radio_tag": "oldskool"}
    packs = _safe(legacy.packs, []) or []
    if packs:
        ids["rtp_pack"] = (packs[0] or {}).get("key")
    events = _safe(lambda: legacy.categories().get("events"), []) or []
    if events:
        ids["rtp_cat"] = str(events[0].get("id"))
    posts = _safe(lambda: legacy.category(ids["rtp_cat"]), []) or []
    if posts:
        ids["rtp_post"] = posts[0].get("id")
    shows = _safe(legacy.jungle_shows, []) or []
    if shows:
        ids["jt_show"] = shows[0].get("key")
    mixes = _safe(lambda: moxser.mixes(limit=1), []) or []
    if mixes:
        ids["moxser_page_url"] = mixes[0].get("page_url")
    docs, _total = _safe(lambda: bs.archive.search(
        "collection:ravetapes AND mediatype:audio", rows=1), ([], 0))
    if docs:
        ids["archive_id"] = docs[0].get("identifier")
    tracks = _safe(lambda: bs.archive.audio_files(ids["archive_id"] or ""), []) or []
    if tracks:
        ids["archive_track"] = tracks[0].get("url")
    return ids


def build(ids):
    """Return [(name, run, network_bound)] for every route we care about."""
    out = []

    def add(name, mode, network_bound=True, **params):
        out.append((name, HARNESS.route(mode, **params), network_bound))

    add("root", "root", network_bound=False)
    add("screen", "screen", network_bound=False)
    add("packs_menu", "packs_menu", network_bound=False)
    add("shows_menu", "shows_menu", network_bound=False)
    add("radio_menu", "radio_menu", network_bound=False)
    add("about", "about", network_bound=False)
    add("latest", "latest")
    add("search", "search", q="dreamscape")
    add("legacy_menu", "legacy_menu", network_bound=False)
    add("rtp_index", "legacy_index", kind="event")
    add("rtp_all", "legacy_packs")
    add("rtp_pack", "legacy_pack", pack=ids.get("rtp_pack"))
    add("rtp_category", "legacy_category", kind="event", cat=ids.get("rtp_cat"))
    add("rtp_post", "legacy_post", post=ids.get("rtp_post"))
    add("jt_index", "legacy_jt")
    if ids.get("jt_show"):
        add("jt_show", "legacy_jt_show", key=ids["jt_show"])
    add("toronto", "toronto")
    add("toronto_genre", "toronto_genre", genre="jungle")
    add("moxser", "moxser")
    if ids.get("moxser_page_url"):
        add("moxser_mix", "moxser_mix", page=ids["moxser_page_url"])
    add("hardscore", "hardscore")
    add("archive_list", "archive_list", key="jungle")
    if ids.get("archive_id"):
        add("archive_item", "archive_item", id=ids["archive_id"])
    add("filter_live", "filter_list", key="kool")
    return out


def play_scenarios(ids):
    """Play-start routes (resolve to a stream; the spinner is not timed)."""
    out = []
    if ids.get("archive_track"):
        out.append(("play_archive", _play(ids["archive_track"])))
    if ids.get("archive_id"):
        out.append(("play_all", _play_all(ids["archive_id"])))
    return out


def _play(url):
    def run():
        HARNESS.xbmcplugin.RESOLVED[:] = []
        routes.dispatch(["plugin://plugin.audio.raveplayer/", "1",
                         "?mode=play&url=%s" % bs.urllib.parse.quote(url, safe="")])
        return {"status": 200, "items": len(HARNESS.xbmcplugin.RESOLVED), "bytes": 0}
    return run


def _play_all(identifier):
    def run():
        routes.dispatch(["plugin://plugin.audio.raveplayer/", "-1",
                         "?mode=play_all&id=%s" % bs.urllib.parse.quote(identifier, safe="")])
        return {"status": 200, "items": 0, "bytes": 0}
    return run


def import_cost():
    """Fresh-process import + root dispatch, in ms (median of 3)."""
    code = (
        "import os, sys, time;"
        "sys.path.insert(0, %r); sys.path.insert(0, %r);"
        "t=time.perf_counter();"
        "import xbmcplugin;"
        "from resources.lib import routes;"
        "imported=time.perf_counter();"
        "routes.dispatch(['plugin://plugin.audio.raveplayer/', '1', '?mode=root']);"
        "print(int((imported-t)*1000), int((time.perf_counter()-t)*1000))"
    ) % (os.path.join(ROOT, "test", "stubs"), ROOT)
    try:
        env = dict(os.environ)
        env["RAVEPLAYER_CACHE_DIR"] = bs._BENCH_CACHE
        out = subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, env=env,
                                      stderr=subprocess.DEVNULL, timeout=120)
    except (subprocess.SubprocessError, OSError):
        return None, None
    import_ms, total_ms = out.decode("ascii", "replace").split()
    return float(import_ms), float(total_ms)


def run_scenarios(scenarios, cold_samples, warm_samples):
    records = []
    for scenario in scenarios:
        name, run = scenario[0], scenario[1]
        cold = []
        warm = []
        for _index in range(max(1, cold_samples)):
            bs._clear_caches()
            cold.append(bs._record(run, bs.Meter())["total_ms"])
        for _index in range(max(1, warm_samples)):
            warm.append(bs._record(run, bs.Meter())["total_ms"])
        records.append({"name": name, "cold": cold, "warm": warm})
        print("  %-16s cold %7.0f ms   warm p50 %6.0f ms"
              % (name, statistics.median(cold), statistics.median(warm)),
              file=sys.stderr)
    return records


def summarise(records):
    rows = []
    for record in records:
        rows.append({
            "name": record["name"],
            "cold_p50": round(statistics.median(record["cold"]), 1),
            "cold_p95": round(bs.percentile(record["cold"], 95), 1),
            "warm_p50": round(statistics.median(record["warm"]), 1),
            "warm_p95": round(bs.percentile(record["warm"], 95), 1),
        })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--cold-samples", type=int, default=1)
    parser.add_argument("--replay", choices=("auto", "none", "all"), default="auto")
    parser.add_argument("--latency-ms", type=float, default=350.0)
    parser.add_argument("--only", default="")
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    bs.install_replay(args.replay, args.latency_ms)
    ids = discover()
    scenarios = build(ids) + play_scenarios(ids)
    if args.only:
        wanted = set(part.strip() for part in args.only.split(",") if part.strip())
        scenarios = [row for row in scenarios if row[0] in wanted]

    rows = summarise(run_scenarios(scenarios, args.cold_samples, args.samples))
    import_ms, total_ms = import_cost()
    print()
    print("| Route | Cold p50 | Cold p95 | Warm p50 | Warm p95 |")
    print("|---|---:|---:|---:|---:|")
    for row in rows:
        print("| `%s` | %.1f | %.1f | %.1f | %.1f |" % (
            row["name"], row["cold_p50"], row["cold_p95"],
            row["warm_p50"], row["warm_p95"]))
    if import_ms is not None:
        print("\nFresh process: import %.0f ms, import+root dispatch %.0f ms"
              % (import_ms, total_ms))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({
                "replay": args.replay, "latency_ms": args.latency_ms,
                "cold_samples": args.cold_samples, "samples": args.samples,
                "routes": rows,
                "import_ms": import_ms, "import_and_root_ms": total_ms,
            }, handle, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
