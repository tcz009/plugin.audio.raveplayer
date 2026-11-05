# -*- coding: utf-8 -*-
"""Bounded worker-thread task runner for window data loads.

Kodi queues Python window callbacks and runs them on the thread that owns the
interpreter (this script), so a blocking network call there would also block
Back and D-pad handling. A source load or a surprise pick therefore runs on a
daemon thread while the owner polls with ``xbmc.sleep``, which pumps the queued
callbacks and lets Kodi repaint the "Loading…" status. The timeout is a hard
upper bound; the worker cannot be killed, but its late result is ignored. When
the window closes (``cancelled``), the poll stops at once instead of waiting
for the worker to finish.
"""

import threading
import time


class TaskTimeout(RuntimeError):
    pass


class TaskFailed(RuntimeError):
    pass


class TaskCancelled(RuntimeError):
    """The window closed while the worker was still running."""


class DirectTaskRunner(object):
    """Run the callable inline; used by tests and deterministic callers."""

    def run(self, function):
        return function()


class ThreadTaskRunner(object):
    def __init__(self, sleep=None, clock=None, monitor=None, timeout=15.0,
                 cancelled=None, on_poll=None):
        self.timeout = max(0.0, float(timeout))
        self.cancelled = cancelled
        # `on_poll` runs on the *caller* thread (the GUI thread for loads) on
        # every poll, so progress animation never touches a control from the
        # worker thread.
        self.on_poll = on_poll
        if sleep is None:
            import xbmc

            sleep = xbmc.sleep
        self.sleep = sleep
        self.clock = clock or time.monotonic
        if monitor is None:
            import xbmc

            monitor = xbmc.Monitor()
        self.monitor = monitor

    def _is_cancelled(self):
        if self.cancelled is None:
            return False
        try:
            return bool(self.cancelled())
        except Exception:  # noqa: BLE001 - the predicate is advisory
            return False

    def run(self, function):
        if self._is_cancelled():
            raise TaskCancelled("window closed before the load started")
        outcome = {}

        def target():
            try:
                outcome["value"] = function()
            except Exception as exc:  # noqa: BLE001 - re-raised on the caller thread
                outcome["error"] = exc

        thread = threading.Thread(target=target, name="rave-screen-load")
        thread.daemon = True
        thread.start()
        started = self.clock()
        while thread.is_alive():
            if self._is_cancelled():
                raise TaskCancelled("window closed")
            try:
                if self.monitor.abortRequested():
                    raise TaskTimeout("Kodi is shutting down")
            except TaskTimeout:
                raise
            except Exception:  # noqa: BLE001 - monitor is advisory
                pass
            if self.clock() - started >= self.timeout:
                raise TaskTimeout("source took longer than %.0fs" % self.timeout)
            self._poll()
            self.sleep(50)
        if "error" in outcome:
            raise TaskFailed(str(outcome["error"]))
        return outcome.get("value")

    def _poll(self):
        if self.on_poll is None:
            return
        try:
            self.on_poll()
        except Exception:  # noqa: BLE001 - a progress tick is advisory
            pass
