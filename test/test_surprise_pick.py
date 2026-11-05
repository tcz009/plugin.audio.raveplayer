# -*- coding: utf-8 -*-
"""Offline tests for the reliable Surprise pick (retry/cache/single-play)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCREEN = os.path.join(ROOT, "script.raveplayer.ui")
sys.path.insert(0, SCREEN)

from raveui import surprise_pick  # noqa: E402

PACK_A = {"identifier": "pack-a", "title": "Dreamscape 19"}
PACK_B = {"identifier": "pack-b", "title": "World Dance 1994"}


class FakeRandom(object):
    def __init__(self, picks=None):
        self.picks = list(picks or [])
        self.calls = 0

    def choice(self, sequence):
        self.calls += 1
        if self.picks:
            pick = self.picks.pop(0)
            if callable(pick):
                return pick(sequence)
            if isinstance(pick, int):
                return sequence[pick]
            return pick
        return sequence[0]


class Backend(object):
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if not self.outcomes:
            return None
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class Sleep(object):
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


def picker(backend, **kwargs):
    kwargs.setdefault("random_module", FakeRandom())
    return surprise_pick.SurprisePicker(pick=backend, **kwargs)


class HappyPathTests(unittest.TestCase):
    def test_first_attempt_succeeds(self):
        backend = Backend([PACK_A])
        result = picker(backend).pick_once()
        self.assertTrue(result)
        self.assertTrue(result.ok)
        self.assertEqual(result.identifier, "pack-a")
        self.assertEqual(result.title, "Dreamscape 19")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.source, "backend")
        self.assertEqual(backend.calls, 1)

    def test_callable_alias(self):
        backend = Backend([PACK_A])
        result = picker(backend)()
        self.assertTrue(result)

    def test_attempts_are_clamped_to_two_or_three(self):
        self.assertEqual(picker(Backend([]), attempts=99).attempts, 3)
        self.assertEqual(picker(Backend([]), attempts=1).attempts, 2)
        self.assertEqual(picker(Backend([]), attempts="bad").attempts, 3)


class RetryTests(unittest.TestCase):
    def test_transient_none_is_retried_with_short_backoff(self):
        backend = Backend([None, PACK_A])
        sleep = Sleep()
        result = picker(backend, sleep=sleep).pick_once()
        self.assertTrue(result)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(backend.calls, 2)
        self.assertEqual(sleep.calls, [0.35])
        self.assertLessEqual(sum(sleep.calls), 1.2)

    def test_exception_is_retried(self):
        backend = Backend([RuntimeError("archive 503"), PACK_B])
        result = picker(backend, sleep=Sleep()).pick_once()
        self.assertTrue(result)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.identifier, "pack-b")

    def test_malformed_pack_is_retried(self):
        backend = Backend([{"title": "no id"}, {"identifier": "/etc/passwd"},
                           PACK_A])
        result = picker(backend, sleep=Sleep()).pick_once()
        self.assertTrue(result)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(result.identifier, "pack-a")

    def test_exhaustion_returns_one_clear_failure(self):
        backend = Backend([None, RuntimeError("timeout"), None])
        sleep = Sleep()
        result = picker(backend, sleep=sleep).pick_once()
        self.assertFalse(result)
        self.assertFalse(result.ok)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(backend.calls, 3)
        self.assertEqual(sleep.calls, [0.35, 0.8])
        self.assertEqual(result.reason, surprise_pick.FAILURE_MESSAGE)
        self.assertTrue(result.last_error)
        self.assertEqual(result.message, surprise_pick.FAILURE_MESSAGE)

    def test_no_picker_is_a_clear_failure_without_retries(self):
        result = surprise_pick.SurprisePicker(pick=None).pick_once()
        self.assertFalse(result)
        self.assertEqual(result.attempts, 0)
        self.assertIn("not available", result.message)


class CacheTests(unittest.TestCase):
    def test_cached_pack_is_preferred_and_skips_the_backend(self):
        cache = surprise_pick.PackCache()
        cache.remember(PACK_A)
        backend = Backend([RuntimeError("must not be called")])
        result = picker(backend, cache=cache).pick_once()
        self.assertTrue(result)
        self.assertEqual(result.source, "cache")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(backend.calls, 0)

    def test_recent_pick_is_avoided_when_another_cache_pack_exists(self):
        cache = surprise_pick.PackCache()
        cache.remember([PACK_A, PACK_B])
        engine = picker(Backend([]), cache=cache)
        first = engine.pick_once()
        second = engine.pick_once()
        self.assertTrue(first)
        self.assertTrue(second)
        self.assertEqual(first.source, "cache")
        self.assertEqual(second.source, "cache")
        self.assertNotEqual(first.identifier, second.identifier)

    def test_cache_remember_latest_and_bound(self):
        cache = surprise_pick.PackCache(limit=2)
        self.assertEqual(cache.remember_latest([
            {"identifier": "one", "title": "One"},
            {"id": "two", "label": "Two"},
            {"identifier": "", "title": "skip"},
        ]), 2)
        self.assertEqual(len(cache), 2)
        cache.remember({"identifier": "three", "title": "Three"})
        self.assertEqual(cache.identifiers, ["two", "three"])
        self.assertTrue(cache.forget("two"))
        self.assertFalse(cache.forget("two"))
        self.assertNotIn("two", cache)

    def test_cache_dedupes_and_returns_copies(self):
        cache = surprise_pick.PackCache()
        cache.remember(PACK_A)
        cache.remember(PACK_A)
        self.assertEqual(len(cache), 1)
        chosen = cache.choose(FakeRandom())
        chosen["title"] = "mutated"
        self.assertEqual(cache.choose(FakeRandom())["title"], "Dreamscape 19")

    def test_cache_falls_back_to_a_recent_pack_when_it_is_the_only_one(self):
        cache = surprise_pick.PackCache()
        cache.remember(PACK_A)
        engine = picker(Backend([]), cache=cache)
        self.assertEqual(engine.pick_once().identifier, "pack-a")
        self.assertEqual(engine.pick_once().identifier, "pack-a")

    def test_broken_cache_is_not_fatal(self):
        class BrokenCache(object):
            def choose(self, random_module=None, avoid=()):
                raise RuntimeError("cache down")

        result = picker(Backend([PACK_A]), cache=BrokenCache()).pick_once()
        self.assertTrue(result)
        self.assertEqual(result.source, "backend")


class ResolverTests(unittest.TestCase):
    def test_unplayable_pack_is_retried(self):
        seen = []

        def resolve(identifier):
            seen.append(identifier)
            return {"url": "https://example.test/a.mp3"} if identifier == "pack-b" else {}

        backend = Backend([PACK_A, PACK_B])
        result = picker(backend, resolve=resolve, sleep=Sleep()).pick_once()
        self.assertTrue(result)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.track["url"], "https://example.test/a.mp3")
        self.assertEqual(result.track.url, "https://example.test/a.mp3")
        self.assertEqual(result.track.pack, "World Dance 1994")
        self.assertEqual(seen, ["pack-a", "pack-b"])

    def test_exhausted_unplayable_packs_get_a_specific_message(self):
        backend = Backend([PACK_A, PACK_B, PACK_A])
        result = picker(backend, resolve=lambda identifier: {},
                        sleep=Sleep()).pick_once()
        self.assertFalse(result)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(result.message, surprise_pick.UNPLAYABLE_MESSAGE)

    def test_resolve_exception_counts_as_a_failed_attempt(self):
        calls = []

        def resolve(identifier):
            calls.append(identifier)
            if len(calls) == 1:
                raise RuntimeError("metadata failed")
            return {"url": "https://example.test/a.mp3"}

        backend = Backend([PACK_A, PACK_B])
        result = picker(backend, resolve=resolve, sleep=Sleep()).pick_once()
        self.assertTrue(result)
        self.assertEqual(result.track["url"], "https://example.test/a.mp3")

    def test_cached_pack_with_lost_tracks_is_dropped(self):
        cache = surprise_pick.PackCache()
        cache.remember(PACK_A)
        result = picker(Backend([PACK_B]), cache=cache,
                        resolve=lambda identifier: {"url": "https://x.test/a"}
                        if identifier == "pack-b" else {}).pick_once()
        self.assertTrue(result)
        self.assertEqual(result.identifier, "pack-b")
        self.assertNotIn("pack-a", cache)


class CancelTests(unittest.TestCase):
    def test_cancel_before_the_first_attempt(self):
        backend = Backend([PACK_A])
        result = picker(backend, should_stop=lambda: True).pick_once()
        self.assertTrue(result.cancelled)
        self.assertFalse(result)
        self.assertEqual(result.attempts, 0)
        self.assertEqual(backend.calls, 0)
        self.assertEqual(result.message, surprise_pick.CANCELLED_MESSAGE)

    def test_cancel_between_retries_stops_immediately(self):
        backend = Backend([None, PACK_A])
        state = {"calls": 0}

        def should_stop():
            # Called once before the loop and once per attempt: return True
            # only when the second attempt is about to start.
            state["calls"] += 1
            return state["calls"] > 2

        sleep = Sleep()
        result = picker(backend, should_stop=should_stop, sleep=sleep).pick_once()
        self.assertTrue(result.cancelled)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(backend.calls, 1)
        self.assertEqual(sleep.calls, [])

    def test_broken_should_stop_is_not_a_cancel(self):
        def broken():
            raise RuntimeError("monitor down")
        result = picker(Backend([PACK_A]), should_stop=broken).pick_once()
        self.assertTrue(result)


class IdentifierTests(unittest.TestCase):
    def test_rejects_paths_controls_and_overlong_ids(self):
        self.assertEqual(surprise_pick.clean_identifier(" pack-a "), "pack-a")
        for bad in (None, "", "a/b", "a\\b", "..", ".", "a\nb", "x" * 200):
            self.assertEqual(surprise_pick.clean_identifier(bad), "")

    def test_clean_pack_normalises_title(self):
        self.assertEqual(surprise_pick.clean_pack({"id": "pack-a"}),
                         {"identifier": "pack-a", "title": "pack-a"})
        self.assertEqual(surprise_pick.clean_pack({"identifier": "pack-a",
                                                   "title": ["A", "B"]}),
                         {"identifier": "pack-a", "title": "A B"})
        self.assertEqual(surprise_pick.clean_pack(None), {})

    def test_make_resolver_picks_one_playable_file(self):
        class Archive(object):
            def audio_files(self, identifier):
                return [
                    {"title": "Bad", "url": "file:///etc/passwd"},
                    {"title": "Good", "url": "https://example.test/a.mp3"},
                ]

        resolve = surprise_pick.make_resolver(
            Archive(), safe_url=lambda url: url
            if str(url).startswith("https://") else "")
        track = resolve("pack-a")
        self.assertEqual(track["title"], "Good")
        self.assertEqual(track.url, "https://example.test/a.mp3")
        self.assertEqual(track.identifier, "pack-a")
        self.assertEqual(track.pack, "")
        self.assertFalse(track.live)
        self.assertEqual(resolve("bad/id"), {})


class PlayOnceTests(unittest.TestCase):
    def test_fire_runs_once_and_trips_before_the_callback(self):
        calls = []
        gate = surprise_pick.PlayOnce()
        self.assertTrue(gate.fire(calls.append, "one"))
        self.assertTrue(gate.fired)
        self.assertFalse(gate.fire(calls.append, "two"))
        self.assertEqual(calls, ["one"])

    def test_callback_exception_does_not_reopen_the_gate(self):
        calls = []

        def fail(value):
            calls.append(value)
            raise RuntimeError("player died")

        gate = surprise_pick.PlayOnce()
        with self.assertRaises(RuntimeError):
            gate.fire(fail, 1)
        self.assertFalse(gate.fire(fail, 2))
        self.assertEqual(calls, [1])

    def test_reset_allows_a_new_gesture(self):
        gate = surprise_pick.PlayOnce()
        self.assertTrue(gate.fire(lambda: None))
        gate.reset()
        self.assertTrue(gate.fire(lambda: None))


class PickAndHandoffTests(unittest.TestCase):
    def test_failure_never_calls_handoff(self):
        handoffs = []
        result = surprise_pick.pick_and_handoff(
            picker(Backend([None, None, None]), sleep=Sleep()),
            handoffs.append)
        self.assertFalse(result)
        self.assertEqual(handoffs, [])

    def test_success_hands_off_once_and_a_second_gesture_is_blocked(self):
        backend = Backend([PACK_A, PACK_B])
        engine = picker(backend)
        handoffs = []
        gate = surprise_pick.PlayOnce()
        first = surprise_pick.pick_and_handoff(engine, handoffs.append,
                                               track_of=lambda result: result.pack,
                                               guard=gate)
        second = surprise_pick.pick_and_handoff(engine, handoffs.append,
                                                track_of=lambda result: result.pack,
                                                guard=gate)
        self.assertTrue(first)
        self.assertTrue(second)
        self.assertEqual(len(handoffs), 1)
        self.assertEqual(handoffs[0]["identifier"], "pack-a")

    def test_picker_guard_is_shared_even_without_an_explicit_gate(self):
        engine = picker(Backend([PACK_A, PACK_B]))
        handoffs = []
        surprise_pick.pick_and_handoff(
            engine, handoffs.append, track_of=lambda result: result.pack)
        surprise_pick.pick_and_handoff(
            engine, handoffs.append, track_of=lambda result: result.pack)
        self.assertEqual(len(handoffs), 1)

    def test_result_callback_sees_the_failure(self):
        seen = []
        result = surprise_pick.pick_and_handoff(
            picker(Backend([None, None, None]), sleep=Sleep()),
            lambda track: None, on_result=seen.append)
        self.assertFalse(result)
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0])


if __name__ == "__main__":
    unittest.main()


class FromPluginTests(unittest.TestCase):
    def test_wires_random_pack_and_archive_resolution(self):
        class Latest(object):
            def __init__(self):
                self.calls = 0

            def random_pack(self):
                self.calls += 1
                return PACK_A

        class Archive(object):
            def audio_files(self, identifier):
                return [{"title": "Tape 1", "url": "https://example.test/a.mp3"}]

        class Http(object):
            def safe_stream_url(self, url):
                return url

        modules = type("Modules", (), {"latest": Latest(), "archive": Archive(),
                                       "http": Http()})()
        engine = surprise_pick.from_plugin(modules)
        result = engine.pick_once()
        self.assertTrue(result)
        self.assertEqual(result.source, "backend")
        self.assertEqual(result.track["url"], "https://example.test/a.mp3")
        self.assertEqual(modules.latest.calls, 1)

    def test_missing_plugin_fails_clearly_without_retries(self):
        result = surprise_pick.from_plugin(None).pick_once()
        self.assertFalse(result)
        self.assertIn("not available", result.message)
