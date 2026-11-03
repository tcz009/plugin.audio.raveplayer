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
        self.assertIn("Spinning Rave Player head", open(path, encoding="utf-8").read())

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
        self.assertEqual(fake.controls[spinner.CONTROL_HINT].label, "Back to cancel")


def time_sleep(seconds):
    import time
    time.sleep(seconds)
