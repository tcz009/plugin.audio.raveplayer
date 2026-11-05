# -*- coding: utf-8 -*-
"""Headless owner for the in-flight download queue.

``window.open_screen()`` calls :meth:`DownloadQueue.spawn_worker` before its
interpreter exits.  This module is that separate ``script.raveplayer.ui``
process: it loads the persisted queue, restarts any interrupted transfer and
polls until nothing is active, then exits.  It never creates a window and never
touches a Kodi control, so a download survives Back/close.

Start it through Kodi::

    RunScript(script.raveplayer.ui,downloads)
"""

import time

from .downloadqueue import DownloadQueue, default_store_path


def run(store_path=None, monitor=None, poll_seconds=0.5, logger=None):
    path = store_path or default_store_path()
    if not path:
        return 0
    queue = DownloadQueue(store_path=path, logger=logger)
    if not queue.acquire_worker_lock():
        queue.release_worker_lock()
        return 0
    if monitor is None:
        try:
            import xbmc

            monitor = xbmc.Monitor()
        except Exception:  # noqa: BLE001 - outside Kodi the loop is bounded
            monitor = None
    try:
        queue.resume()
        while queue.active():
            if monitor is not None:
                try:
                    if monitor.abortRequested():
                        break
                except Exception:  # noqa: BLE001 - monitor is advisory
                    pass
            queue.heartbeat()
            queue.refresh()
            queue.resume()
            _sleep(poll_seconds)
        return 0
    finally:
        queue.release_worker_lock()


def _sleep(seconds):
    try:
        import xbmc

        xbmc.sleep(int(max(0.05, float(seconds)) * 1000))
    except Exception:  # noqa: BLE001 - tests / CLI
        time.sleep(max(0.05, float(seconds)))
