# -*- coding: utf-8 -*-
"""Offline tests for the Latest merge and the by-year/surprise helpers."""

import datetime
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import dnbradio, latest  # noqa: E402


class DateTests(unittest.TestCase):
    def test_iso_dates(self):
        self.assertEqual(latest.parse_date("2026-10-29"), datetime.datetime(2026, 10, 29))
        self.assertEqual(latest.parse_date("2026-10-29T13:07:23Z"), datetime.datetime(2026, 10, 29))

    def test_rfc822_dates(self):
        self.assertEqual(latest.parse_date("Mon, 19 Jan 2026 11:51:21 +0000").date(),
                         datetime.date(2026, 1, 19))

    def test_unknown_and_empty(self):
        self.assertIsNone(latest.parse_date(""))
        self.assertIsNone(latest.parse_date(None))
        self.assertIsNone(latest.parse_date("not a date"))
        self.assertIsNone(latest.parse_date("2026-13-45"))

    def test_year_query(self):
        query = latest.year_query(1993)
        self.assertIn("collection:ravetapes", query)
        self.assertIn("date:[1993-01-01 TO 1993-12-31]", query)


class MergeTests(unittest.TestCase):
    def test_merge_orders_newest_first_and_keeps_undated_last(self):
        feeds_rows = [
            {"id": "a", "name": "Feed A", "plot": ""},
        ]
        episodes_row = [
            {"title": "New episode", "url": "http://x/1.mp3", "published": "2026-10-29", "duration": 10},
        ]
        archive_rows = ([{"identifier": "pack-1", "title": "Pack One", "addeddate": "2020-01-01"}], 1)
        dnb_rows = [{"id": "9", "title": "DNB Show", "date": "2021-05-05"}]

        with mock.patch.object(latest.feeds, "registry", return_value=feeds_rows), \
                mock.patch.object(latest.feeds, "episodes", return_value=episodes_row), \
                mock.patch.object(latest.archive, "search", return_value=archive_rows), \
                mock.patch.object(latest.dnbradio, "mixes", return_value=dnb_rows):
            merged = latest.merge(limit=10)

        titles = [item["title"] for item in merged]
        self.assertEqual(titles[:3], ["New episode", "DNB Show", "Pack One"])
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0]["kind"], "episode")
        self.assertEqual(merged[2]["kind"], "pack")

    def test_merge_limit(self):
        with mock.patch.object(latest.feeds, "registry", return_value=[]), \
                mock.patch.object(latest.archive, "search", return_value=([], 0)), \
                mock.patch.object(latest.dnbradio, "mixes", return_value=[]):
            self.assertEqual(latest.merge(limit=5), [])

    def test_recent_packs_skips_missing_identifier(self):
        rows = ([{"identifier": "", "title": "bad"}, {"identifier": "ok", "title": "Good"}], 2)
        with mock.patch.object(latest.archive, "search", return_value=rows):
            items = latest.recent_packs()
        self.assertEqual([item["identifier"] for item in items], ["ok"])

    def test_recent_packs_normalises_list_titles(self):
        rows = ([{"identifier": "ok", "title": ["Dreamscape", "XIX"]}], 1)
        with mock.patch.object(latest.archive, "search", return_value=rows):
            items = latest.recent_packs()
        self.assertEqual(items[0]["title"], "Dreamscape XIX")


class RandomPackTests(unittest.TestCase):
    def test_returns_a_pack(self):
        with mock.patch.object(latest.archive, "search", side_effect=[
                ([], 100), ([{"identifier": "picked", "title": "Picked Pack"}], 100)]):
            with mock.patch.object(latest.random, "randint", return_value=2), \
                    mock.patch.object(latest.random, "choice", side_effect=lambda docs: docs[0]):
                pack = latest.random_pack()
        self.assertEqual(pack["identifier"], "picked")

    def test_empty_archive_returns_none(self):
        with mock.patch.object(latest.archive, "search", return_value=([], 0)):
            self.assertIsNone(latest.random_pack())

    def test_last_page_is_reachable(self):
        with mock.patch.object(latest.archive, "search", side_effect=[
                ([], 724), ([{"identifier": "picked", "title": "Picked"}], 724)]):
            with mock.patch.object(latest.random, "randint", return_value=15) as randint:
                pack = latest.random_pack()
        self.assertEqual(randint.call_args[0], (1, 15))
        self.assertEqual(pack["identifier"], "picked")

    def test_document_without_identifier_is_ignored(self):
        with mock.patch.object(latest.archive, "search", side_effect=[
                ([], 100), ([{"title": "No identifier"}], 100)]):
            with mock.patch.object(latest.random, "randint", return_value=1):
                self.assertIsNone(latest.random_pack())


class DnbStreamBatchTests(unittest.TestCase):
    """The directory-build batch must drop mixes whose host cannot be reached."""

    @staticmethod
    def _fetch(reachable):
        def fake(url, timeout=20, headers=None, ttl=0):
            if reachable not in url:
                return None
            mix_id = url.rsplit("mix=", 1)[-1]
            return '<a href="https://proxy.dnbradio.com/%s.mp3">' % mix_id
        return fake

    def test_unreachable_mixes_are_dropped_from_the_batch(self):
        with mock.patch.object(dnbradio.http, "fetch", side_effect=self._fetch("mix=10")):
            found = dnbradio.stream_urls(["10", "11", "12"], timeout=1, workers=4)
        self.assertEqual(found, {"10": "https://proxy.dnbradio.com/10.mp3"})

    def test_duplicate_ids_are_resolved_once(self):
        calls = []

        def fake(url, timeout=20, headers=None, ttl=0):
            calls.append(url)
            mix_id = url.rsplit("mix=", 1)[-1]
            return '<a href="https://proxy.dnbradio.com/%s.mp3">' % mix_id

        with mock.patch.object(dnbradio.http, "fetch", side_effect=fake):
            found = dnbradio.stream_urls(["7", "8", "7"], timeout=1, workers=4)
        self.assertEqual(found, {"7": "https://proxy.dnbradio.com/7.mp3",
                                 "8": "https://proxy.dnbradio.com/8.mp3"})
        self.assertEqual(len([url for url in calls if "mix=7" in url]), 1)

    def test_empty_id_list_does_not_fetch(self):
        with mock.patch.object(dnbradio.http, "fetch") as fetch:
            self.assertEqual(dnbradio.stream_urls([], timeout=1), {})
            self.assertEqual(dnbradio.stream_urls([None, ""], timeout=1), {})
        self.assertFalse(fetch.called)

    def test_a_raising_worker_does_not_empty_the_batch(self):
        def fake(url, timeout=20, headers=None, ttl=0):
            if "mix=2" in url:
                raise RuntimeError("boom")
            return '<a href="https://proxy.dnbradio.com/1.mp3">'

        with mock.patch.object(dnbradio.http, "fetch", side_effect=fake):
            found = dnbradio.stream_urls(["1", "2"], timeout=1, workers=2)
        self.assertEqual(found, {"1": "https://proxy.dnbradio.com/1.mp3"})


class ResolveDnbStreamsTests(unittest.TestCase):
    def test_resolves_only_dnb_rows_in_one_batch(self):
        items = [
            {"kind": "pack", "identifier": "pack-1"},
            {"kind": "dnb", "id": "10"},
            {"kind": "episode", "url": "https://x/1.mp3"},
            {"kind": "dnb", "id": "11"},
        ]
        with mock.patch.object(latest.dnbradio, "stream_urls",
                               return_value={"10": "https://p/10.mp3"}) as urls:
            found = latest.resolve_dnb_streams(items)
        self.assertEqual(found, {"10": "https://p/10.mp3"})
        self.assertEqual(urls.call_args[0][0], ["10", "11"])
        self.assertEqual(urls.call_args[1]["timeout"], latest.DNB_RESOLVE_TIMEOUT)
        self.assertEqual(urls.call_args[1]["workers"], latest.DNB_RESOLVE_WORKERS)

    def test_no_dnb_rows_does_not_touch_the_network(self):
        with mock.patch.object(latest.dnbradio, "stream_urls") as urls:
            self.assertEqual(latest.resolve_dnb_streams([{"kind": "pack"}]), {})
            self.assertEqual(latest.resolve_dnb_streams([]), {})
        self.assertFalse(urls.called)

    def test_a_failed_batch_returns_no_streams_instead_of_raising(self):
        items = [{"kind": "dnb", "id": "10"}]
        with mock.patch.object(latest.dnbradio, "stream_urls", side_effect=RuntimeError("boom")):
            self.assertEqual(latest.resolve_dnb_streams(items), {})


if __name__ == "__main__":
    unittest.main()
