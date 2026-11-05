# -*- coding: utf-8 -*-
"""The spinning-head reveal, run on its own reveal worker.

The controller paints the splash from ``onClick`` and then hands the pick and
this frame loop to a worker thread, so the Kodi GUI can render while the
network pick is in flight. Kodi repaints independently of the Python thread;
each ``setImage`` marks the control dirty and the next frame draws it. Device
checks on the Shield (Kodi 22) captured distinct head angles at 0.6 s spacing
during the 1.2 s reveal.

``setImage`` is still a WindowXML control call, so keep the loop bounded,
poll ``cancelled`` and never touch a control after the window is closed.
"""

import time

FRAME_COUNT = 10
FPS = 10
MIN_DURATION = 1.2


def frame_index(elapsed, frame_count=FRAME_COUNT, fps=FPS):
    try:
        elapsed = max(0.0, float(elapsed))
        frame_count = max(1, int(frame_count))
        fps = max(1, int(fps))
    except (TypeError, ValueError):
        return 0
    return int(elapsed * fps) % frame_count


class SpinnerAnimator(object):
    """Advance the head for at least ``duration`` seconds on the caller thread.

    ``set_image`` is expected to be a WindowXML control's ``setImage`` (or a
    test recorder). ``sleep`` takes **milliseconds**, matching ``xbmc.sleep``.
    ``cancelled`` is polled before each frame; when true the reveal stops without
    a playback handoff.
    """

    def __init__(self, frames, set_image, duration=MIN_DURATION, fps=FPS,
                 sleep=None, clock=None, cancelled=None):
        self.frames = list(frames or [])
        self.set_image = set_image
        self.duration = max(0.0, float(duration))
        self.fps = max(1, int(fps))
        if sleep is None:
            import xbmc

            sleep = xbmc.sleep
        self.sleep = sleep
        self.clock = clock or time.monotonic
        self.cancelled = cancelled or (lambda: False)

    def run(self):
        if not self.frames:
            return False
        started = self.clock()
        interval = 1.0 / self.fps
        while True:
            if self.cancelled():
                return False
            elapsed = max(0.0, self.clock() - started)
            index = frame_index(elapsed, len(self.frames), self.fps)
            try:
                self.set_image(self.frames[index])
            except Exception:  # noqa: BLE001 - a dead control must not crash
                return False
            if elapsed >= self.duration:
                return True
            remaining = self.duration - elapsed
            self.sleep(int(round(min(interval, remaining) * 1000)))
