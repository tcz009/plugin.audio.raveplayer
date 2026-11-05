# -*- coding: utf-8 -*-
"""Bounded worker-thread task runner for window data loads.

Kodi's Python window callbacks run on the GUI thread. Network scrapers there
would freeze focus movement, so a source load or a surprise pick runs on a
daemon thread while the controller polls with ``xbmc.sleep`` (which yields and
lets Kodi repaint the "Loading…" status). The timeout is a hard upper bound;
the worker cannot be killed, but its late result is ignored.
"""

import threading
import time


class TaskTimeout(RuntimeError):
    pass


class TaskFailed(RuntimeError):
    pass


class DirectTaskRunner(object):
    """Run the callable inline; used by tests and deterministic callers."""

    def run(self, function):
        return function()


class ThreadTaskRunner(object):
    def __init__(self, sleep=None, clock=None, monitor=None, timeout=15.0):
        self.timeout = max(0.0, float(timeout))
        if sleep is None:
            import xbmc

            sleep = xbmc.sleep
        self.sleep = sleep
        self.clock = clock or time.monotonic
        if monitor is None:
            import xbmc

            monitor = xbmc.Monitor()
        self.monitor = monitor

    def run(self, function):
        outcome = {}

        def target():
            try:
                outcome["value"] = function()
            except Exception as exc:  # noqa: BLE001 - re-raised on the GUI thread
                outcome["error"] = exc

        thread = threading.Thread(target=target, name="rave-screen-load")
        thread.daemon = True
        thread.start()
        started = self.clock()
        while thread.is_alive():
            try:
                if self.monitor.abortRequested():
                    raise TaskTimeout("Kodi is shutting down")
            except TaskTimeout:
                raise
            except Exception:  # noqa: BLE001 - monitor is advisory
                pass
            if self.clock() - started >= self.timeout:
                raise TaskTimeout("source took longer than %.0fs" % self.timeout)
            self.sleep(50)
        if "error" in outcome:
            raise TaskFailed(str(outcome["error"]))
        return outcome.get("value")
