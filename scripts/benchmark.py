#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reproducible Kodi route benchmark for 3.9.20 (no Kodi UI).

Usage: python3 scripts/benchmark.py [--repeat N] [--cold-runs N]
Runs the real routes with the repo stubs and the on-disk HTTP cache.  Network
is live for Latest/pack-open; the cache directory is temporary per cold run.
"""
import argparse
import importlib
import os
import shutil
import statistics
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "test", "stubs"))
sys.path.insert(0, ROOT)

PACK = "dreamscape-19-toil-and-trouble-jungle-8-tape-pack-1995"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--cold-runs", type=int, default=2)
    args = parser.parse_args()

    cache_dir = tempfile.mkdtemp(prefix="rave-bench-cache-")
    os.environ["RAVEPLAYER_CACHE_DIR"] = cache_dir
    started = time.perf_counter()
    import xbmcplugin  # noqa: F401
    routes = importlib.import_module("resources.lib.routes")
    import_seconds = time.perf_counter() - started

    def dispatch(mode, query=""):
        xbmcplugin.ITEMS.clear()
        xbmcplugin.RESOLVED.clear()
        xbmcplugin.CONTENT.clear()
        argv = ["plugin://plugin.audio.raveplayer/", "1",
                "?" + query + ("&" if query else "") + "mode=" + mode]
        t0 = time.perf_counter()
        routes.dispatch(argv)
        return time.perf_counter() - t0

    def median(mode):
        return statistics.median(dispatch(mode) for _ in range(args.repeat))

    print("import (root process) %.4f s" % import_seconds)
    for mode in ("root", "packs_menu", "shows_menu", "radio_menu", "downloads_menu"):
        print("%-18s %.4f s" % (mode, median(mode)))
    colds, warms = [], []
    for _ in range(args.cold_runs):
        cache = tempfile.mkdtemp(prefix="rave-bench-cold-")
        os.environ["RAVEPLAYER_CACHE_DIR"] = cache
        colds.append(dispatch("latest"))
        warms.append(dispatch("latest"))
        shutil.rmtree(cache, ignore_errors=True)
    print("latest cold       %.2f s (runs %s)" % (statistics.median(colds),
                                                   ", ".join("%.2f" % v for v in colds)))
    print("latest warm       %.2f s" % statistics.median(warms))
    cold = dispatch("archive_item", "id=" + PACK)
    warm = dispatch("archive_item", "id=" + PACK)
    print("pack open cold    %.2f s" % cold)
    print("pack open cached  %.4f s" % warm)
    shutil.rmtree(cache_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
