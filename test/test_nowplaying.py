# -*- coding: utf-8 -*-
"""Offline tests for the now-playing title parser (FEATURES #9)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import nowplaying  # noqa: E402


class DateParserTests(unittest.TestCase):
    def test_year_only(self):
        self.assertEqual(nowplaying.find_date("Tape Pack - 1995"), "1995")

    def test_day_month_name(self):
        self.assertEqual(nowplaying.find_date("Big Bang 27th Nov 1993"), "27 Nov 1993")
        self.assertEqual(nowplaying.find_date("Big Bang 27 November 1993"), "27 Nov 1993")

    def test_month_day_name(self):
        self.assertEqual(nowplaying.find_date("World Dance - April 2nd 1994"), "02 Apr 1994")

    def test_dotted_uk_dates_are_day_first(self):
        self.assertEqual(nowplaying.find_date("World_Dance_94_-_10.3.92"), "10 Mar 1992")
        self.assertEqual(nowplaying.find_date("10/03/1992"), "10 Mar 1992")

    def test_impossible_date_falls_back_to_year(self):
        self.assertEqual(nowplaying.find_date("31/02/1994"), "1994")

    def test_no_date_is_not_guessed(self):
        self.assertEqual(nowplaying.find_date("Tape 1 - Side A"), "")
        self.assertEqual(nowplaying.find_date("1990s rave"), "")


class TitleParserTests(unittest.TestCase):
    def test_known_dj_venue_and_year(self):
        details = nowplaying.parse(
            "Dreamscape 19 - Toil And Trouble - Jungle 8 Tape Pack - 1995",
            "Tape 1 - Carl Cox",
        )
        self.assertEqual(details["artist"], "Carl Cox")
        self.assertEqual(details["venue"], "Dreamscape")
        self.assertEqual(details["date"], "1995")

    def test_longest_dj_name_wins(self):
        self.assertEqual(nowplaying.parse("", "DJ Hype")["artist"], "DJ Hype")
        self.assertEqual(nowplaying.parse("", "Tape 1 - Jumping Jack Frost")["artist"],
                         "Jumping Jack Frost")
        self.assertEqual(nowplaying.parse("", "Tape 1 - LTJ Bukem")["artist"], "LTJ Bukem")

    def test_venue_uses_researched_catalogue_and_filter_names(self):
        self.assertEqual(nowplaying.parse("Fantazia The Big Bang", "")["venue"], "Fantazia")
        self.assertEqual(nowplaying.parse("Kool FM 30th Oct 1993", "")["venue"], "Kool FM")
        self.assertEqual(
            nowplaying.parse("Rave Tape Packs - Slammin' Vinyl", "")["venue"],
            "Slammin' Vinyl",
        )

    def test_unknown_explicit_dj_still_parses(self):
        details = nowplaying.parse("", "DJ Unknown - Live at Bagleys")
        self.assertEqual(details["artist"], "Unknown")
        self.assertEqual(details["venue"], "Bagleys")

    def test_unknown_title_returns_empty_fields(self):
        self.assertEqual(
            nowplaying.parse("Mystery Tape", "Track 1"),
            {"artist": "", "venue": "", "date": ""},
        )


class PlotTests(unittest.TestCase):
    def test_plot_keeps_existing_base_text(self):
        details = nowplaying.parse("Kool FM 30th October 1993", "Brockie")
        plotted = nowplaying.plot("From archive.org item pack-1", details)
        self.assertEqual(
            plotted,
            "Brockie · Kool FM · 30 Oct 1993 — From archive.org item pack-1",
        )

    def test_plot_without_details_is_unchanged(self):
        details = nowplaying.parse("Mystery Tape", "Track 1")
        self.assertEqual(nowplaying.plot("From archive.org item pack-1", details),
                         "From archive.org item pack-1")

    def test_summary_skips_empty_fields(self):
        self.assertEqual(nowplaying.summary({"artist": "Fabio", "venue": "", "date": "1994"}),
                         "Fabio · 1994")
        self.assertEqual(nowplaying.summary(None), "")


if __name__ == "__main__":
    unittest.main()
