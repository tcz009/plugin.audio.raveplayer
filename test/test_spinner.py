# -*- coding: utf-8 -*-
"""Offline tests for the spinning-head download overlay prototype."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)

from resources.lib import spinner  # noqa: E402


class FakeControl(object):
    def __init__(self, control_id):
        self.control_id = control_id
        self.image = ""
        self.label = ""
        self.percent = None

    def setImage(self, image):
        self.image = image

    def setLabel(self, label):
        self.label = label

    def setPercent(self, percent):
        self.percent = percent


class FakeWindow(object):
    created = []

    def __init__(self, xml, skin_dir):
        self.xml = xml
        self.skin_dir = skin_dir
        self.controls = {}
        self.shown = False
        self.closed = False
        self._rave_cancelled = False
        FakeWindow.created.append(self)

    def show(self):
        self.shown = True

    def close(self):
        self.closed = True

    def getControl(self, control_id):
        if control_id not in self.controls:
            self.controls[control_id] = FakeControl(control_id)
        return self.controls[control_id]


class SpinnerTests(unittest.TestCase):
    def tearDown(self):
        FakeWindow.created = []

    def test_frames_exist_at_both_sizes(self):
        for size in (128, 256):
            paths = spinner.frame_paths(size, ROOT)
            self.assertEqual(len(paths), spinner.FRAME_COUNT)
            for path in paths:
                self.assertTrue(os.path.exists(path), path)
                self.assertIn("head-%d-" % size, os.path.basename(path))
        self.assertEqual(spinner.frame_paths(128, ROOT)[0],
                         os.path.join(ROOT, "resources", "art", "spinner",
                                      "head-128-00.png"))

    def test_skin_xml_exists(self):
        path = os.path.join(ROOT, spinner.SKIN_DIR, spinner.WINDOW_XML)
        self.assertTrue(os.path.exists(path), path)
        with open(path, encoding="utf-8") as handle:
            xml = handle.read()
        self.assertIn("Spinning Rave Player head", xml)
        # 3.9.54 device QA P2-3: the plugin-path download overlay exposes a
        # real, focusable Cancel control as well as Back/Stop handling.
        self.assertIn('id="107"', xml)
        self.assertIn("CANCEL", xml)
        self.assertIn("<defaultcontrol>107</defaultcontrol>", xml)

    def test_frame_math_wraps_at_fps(self):
        self.assertEqual(spinner.frame_index(0), 0)
        self.assertEqual(spinner.frame_index(0.1), 1)
        self.assertEqual(spinner.frame_index(0.99), 9)
        self.assertEqual(spinner.frame_index(1.0), 0)
        self.assertEqual(spinner.frame_index(-1), 0)

    def test_remaining_and_size_formatting(self):
        self.assertEqual(spinner.format_bytes(0), "0 B")
        self.assertTrue(spinner.format_bytes(1024 * 1024).endswith("MB"))
        self.assertIn("remaining", spinner.format_remaining(5, 10, 1))
        self.assertEqual(spinner.format_remaining(0, 10, 1), "Starting…")

    def test_window_lifecycle_updates_controls_and_closes(self):
        with mock.patch.object(spinner, "_WINDOW_CLASS", FakeWindow):
            overlay = spinner.SpinnerWindow(addon_path=ROOT)
            self.assertTrue(overlay.open())
            self.assertTrue(overlay.update(50, 100, elapsed=0.5, filename="Set.mp3"))
            window = FakeWindow.created[0]
            self.assertTrue(window.shown)
            self.assertEqual(window.controls[spinner.CONTROL_FILENAME].label, "Set.mp3")
            self.assertEqual(window.controls[spinner.CONTROL_PERCENT].label, "50%")
            self.assertTrue(window.controls[spinner.CONTROL_HEAD].image.endswith(
                "head-256-%02d.png" % spinner.frame_index(0.5)))
            overlay.close()
            self.assertTrue(window.closed)

    def test_window_open_failure_falls_back(self):
        class Broken(object):
            def __init__(self, *args, **kwargs):
                raise RuntimeError("no skin")

        with mock.patch.object(spinner, "_WINDOW_CLASS", Broken):
            overlay = spinner.SpinnerWindow(addon_path=ROOT)
            self.assertFalse(overlay.open())
        self.assertTrue(overlay.failed)

    def test_cancel_state(self):
        with mock.patch.object(spinner, "_WINDOW_CLASS", FakeWindow):
            overlay = spinner.SpinnerWindow(addon_path=ROOT)
            overlay.open()
            self.assertFalse(overlay.iscanceled())
            FakeWindow.created[0]._rave_cancelled = True
            self.assertTrue(overlay.iscanceled())

    def test_owner_cancel_is_sticky(self):
        with mock.patch.object(spinner, "_WINDOW_CLASS", FakeWindow):
            overlay = spinner.SpinnerWindow(addon_path=ROOT)
            overlay.open()
            self.assertTrue(overlay.cancel("test"))
            self.assertTrue(overlay.iscanceled())

    def test_back_stop_and_cancel_control_all_cancel_the_window(self):
        window_class = spinner._WINDOW_CLASS
        if window_class is None:
            self.skipTest("no WindowXML stub")
        action_codes = [getattr(__import__("xbmcgui"), name)
                        for name in ("ACTION_NAV_BACK", "ACTION_STOP",
                                     "ACTION_PREVIOUS_MENU", "ACTION_PARENT_DIR")
                        if hasattr(__import__("xbmcgui"), name)]
        for code in action_codes:
            window = window_class(spinner.WINDOW_XML, ROOT)

            class Action(object):
                def getId(self):
                    return code

            window.onAction(Action())
            self.assertTrue(window._rave_cancelled, code)

        class Control(object):
            def getId(self):
                return spinner.CONTROL_CANCEL

        window = window_class(spinner.WINDOW_XML, ROOT)
        window.onControl(Control())
        self.assertTrue(window._rave_cancelled)


if __name__ == "__main__":
    unittest.main()


class FakeTuningWindow(object):
    created = []

    def __init__(self):
        self.opened = False
        self.closed = False
        self.updated = []
        FakeTuningWindow.created.append(self)

    def open(self):
        self.opened = True
        return True

    def close(self):
        self.closed = True

    def update_tuning(self, label, elapsed=None):
        self.updated.append(label)

    def iscanceled(self):
        return False


class TuningSpinnerTests(unittest.TestCase):
    def setUp(self):
        FakeTuningWindow.created = []

    def _factory(self):
        return FakeTuningWindow()

    def test_fast_resolve_never_opens_the_window(self):
        tune = spinner.TuningSpinner("Kool FM", threshold=0.05, timeout=1.0,
                                     window_factory=self._factory)
        tune.start()
        tune.close()
        time_sleep(0.12)
        self.assertEqual(FakeTuningWindow.created, [])
        self.assertFalse(tune.expired)

    def test_slow_resolve_opens_tuning_mode_and_closes(self):
        tune = spinner.TuningSpinner("Kool FM", threshold=0.01, timeout=1.0,
                                     window_factory=self._factory)
        tune.start()
        time_sleep(0.06)
        self.assertEqual(len(FakeTuningWindow.created), 1)
        window = FakeTuningWindow.created[0]
        self.assertTrue(window.opened)
        self.assertEqual(window.updated[0], "Kool FM")
        tune.close()
        self.assertTrue(window.closed)

    def test_timeout_closes_and_notifies(self):
        notes = []
        tune = spinner.TuningSpinner("Rinse FM", threshold=0.01, timeout=0.03,
                                     window_factory=self._factory,
                                     notify=notes.append)
        tune.start()
        tune._expire()
        self.assertTrue(tune.expired)
        self.assertTrue(tune.closed)
        self.assertIn("taking too long", " ".join(notes))
        tune.close()
        self.assertEqual(len(notes), 1)

    def test_update_tuning_sets_label_and_clears_progress(self):
        window = spinner.SpinnerWindow()
        fake = FakeWindow(spinner.WINDOW_XML, "/tmp")
        window.window = fake
        self.assertTrue(window.update_tuning("Kool FM", 0))
        self.assertEqual(fake.controls[spinner.CONTROL_FILENAME].label,
                         "Kool FM — Tuning in…")
        self.assertEqual(fake.controls[spinner.CONTROL_REMAINING].label, "Tuning in…")
        self.assertEqual(fake.controls[spinner.CONTROL_HINT].label, "OK / Back to cancel")


def time_sleep(seconds):
    import time
    time.sleep(seconds)


class SurpriseWindowFake(object):
    def __init__(self, cancelled=False):
        self.controls = {}
        self.shown = False
        self.closed = False
        self._rave_cancelled = cancelled

    def show(self):
        self.shown = True

    def close(self):
        self.closed = True

    def getControl(self, control_id):
        if control_id not in self.controls:
            self.controls[control_id] = FakeControl(control_id)
        return self.controls[control_id]


class SurpriseRevealTests(unittest.TestCase):
    def test_reveal_animates_for_at_least_min_duration(self):
        window = SurpriseWindowFake()
        clock = {"now": 0.0}
        def now():
            return clock["now"]
        def sleep(seconds):
            clock["now"] += seconds
        reveal = spinner.SurpriseReveal(
            "RANDOM PACK", duration=1.2, fps=10,
            window_factory=lambda: window, sleep=sleep, clock=now)
        self.assertTrue(reveal.show())
        self.assertTrue(window.shown)
        self.assertGreaterEqual(clock["now"], 1.2)
        self.assertGreaterEqual(len(window.controls[spinner.CONTROL_SURPRISE_HEAD].image), 1)
        self.assertEqual(window.controls[spinner.CONTROL_SURPRISE_TITLE].label,
                         "SURPRISE ME")
        self.assertEqual(window.controls[spinner.CONTROL_SURPRISE_SUB].label,
                         "SPINNING THE RACK…")
        reveal.close()
        self.assertTrue(window.closed)

    def test_back_cancels_without_waiting_for_min_duration(self):
        window = SurpriseWindowFake(cancelled=True)
        reveal = spinner.SurpriseReveal(
            "RANDOM PACK", duration=1.2,
            window_factory=lambda: window, sleep=lambda seconds: None,
            clock=lambda: 0.0)
        self.assertFalse(reveal.show())
        self.assertTrue(reveal.cancelled)

    def test_missing_controls_or_typeerror_is_fail_soft(self):
        class BadWindow(SurpriseWindowFake):
            def getControl(self, control_id):
                raise TypeError("Non-Existent Control %s" % control_id)
        window = BadWindow()
        reveal = spinner.SurpriseReveal(
            "RANDOM PACK", window_factory=lambda: window,
            sleep=lambda seconds: None, clock=lambda: 0.0)
        self.assertFalse(reveal.show())
        self.assertTrue(reveal.failed)
        self.assertTrue(window.closed)

    def test_window_failure_is_fail_soft(self):
        def broken():
            raise RuntimeError("no window")
        reveal = spinner.SurpriseReveal("RANDOM PACK", window_factory=broken)
        self.assertFalse(reveal.show())
        self.assertTrue(reveal.failed)
