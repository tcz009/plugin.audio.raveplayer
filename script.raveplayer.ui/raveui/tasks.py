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

    def run(self, function, on_poll=None):
        """Run ``function`` on a daemon thread and pump progress until it ends.

        ``on_poll`` overrides this runner's default hook for this call only.
        A background caller (the Surprise pick worker) passes a token-scoped
        callback that is inert once its run is invalidated, so the shared
        ``_on_runner_poll`` can never animate a control from that thread.
        """
        if self._is_cancelled():
            raise TaskCancelled("window closed before the load started")
        poll = self.on_poll if on_poll is None else on_poll
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
            self._poll(poll)
            self.sleep(50)
        if "error" in outcome:
            raise TaskFailed(str(outcome["error"]))
        return outcome.get("value")

    def _poll(self, callback=None):
        if callback is None:
            callback = self.on_poll
        if callback is None:
            return
        try:
            callback()
        except Exception:  # noqa: BLE001 - a progress tick is advisory
            pass


class BackgroundTask(object):
    """A daemon-thread task whose result is collected from the GUI thread.

    Unlike :class:`ThreadTaskRunner` this never pumps or waits: the caller
    starts it and polls :meth:`poll` from its own loop.  That is what the
    stale-while-revalidate refresh needs — the cached page keeps receiving
    key events while a source call runs off to the side.
    """

    def __init__(self, function, name="rave-screen-refresh"):
        self._outcome = {}
        self._thread = threading.Thread(target=self._run, args=(function,),
                                        name=name)
        self._thread.daemon = True

    def _run(self, function):
        try:
            self._outcome["value"] = function()
        except Exception as exc:  # noqa: BLE001 - re-raised on the GUI thread
            self._outcome["error"] = exc

    def start(self):
        self._thread.start()
        return self

    def poll(self):
        """Return ``("running", None)``, ``("done", value)`` or ``("error", exc)``."""
        if self._thread.is_alive():
            return ("running", None)
        if "error" in self._outcome:
            return ("error", self._outcome["error"])
        return ("done", self._outcome.get("value"))


class ImmediateTask(object):
    """A :class:`BackgroundTask` double for tests: runs inline, then reports."""

    def __init__(self, function, name="rave-screen-refresh"):
        self._outcome = {}
        try:
            self._outcome["value"] = function()
        except Exception as exc:  # noqa: BLE001 - surfaced by poll
            self._outcome["error"] = exc

    def start(self):
        return self

    def poll(self):
        if "error" in self._outcome:
            return ("error", self._outcome["error"])
        return ("done", self._outcome.get("value"))
