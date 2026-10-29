# -*- coding: utf-8 -*-
"""Offline tests for route helpers (no plugin directory, no network)."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.dirname(HERE))

from resources.lib import routes  # noqa: E402


class RouteHelperTests(unittest.TestCase):
    def test_clean_description_unescapes_and_strips_tags(self):
        value = ["<p>Jungle &amp; drum", "&amp; bass</p>"]
        self.assertEqual(routes._clean_description(value), "Jungle & drum & bass")

    def test_clean_description_truncates(self):
        self.assertEqual(len(routes._clean_description("x" * 900)), 600)

    def test_clean_description_handles_empty_values(self):
        self.assertEqual(routes._clean_description(None), "")
        self.assertEqual(routes._clean_description([]), "")

    def test_year_label_never_renders_none(self):
        self.assertEqual(routes._year_label({}), "")
        self.assertEqual(routes._year_label({"year": None, "date": None}), "")
        self.assertEqual(routes._year_label({"date": "1995-01-01"}), "1995")
        self.assertEqual(routes._year_label({"year": [1997, 1998]}), "1997")

    def test_page_number_clamps_invalid_values(self):
        self.assertEqual(routes._page_number({"page": "3"}), 3)
        self.assertEqual(routes._page_number({"page": "0"}), 1)
        self.assertEqual(routes._page_number({"page": "nope"}), 1)
        self.assertEqual(routes._page_number({}), 1)

    def test_rows_per_page_falls_back_when_setting_is_zero(self):
        with mock.patch.object(routes.kodi, "setting_int", return_value=0):
            self.assertEqual(routes._rows_per_page(), routes.ROWS_PER_PAGE)
        with mock.patch.object(routes.kodi, "setting_int", return_value=-1):
            self.assertEqual(routes._rows_per_page(), routes.ROWS_PER_PAGE)

    def test_params_from_argv_handles_question_mark_and_blanks(self):
        self.assertEqual(
            routes.params_from_argv(["plugin://x/", "1", "?mode=root&key=rave"]),
            {"mode": "root", "key": "rave"},
        )
        self.assertEqual(routes.params_from_argv(["plugin://x/", "1"]), {})

    def test_archive_items_skips_documents_without_identifier(self):
        docs = [
            {"identifier": "good", "title": ["A", "Title"], "year": "1994"},
            {"title": "no id"},
        ]
        with mock.patch.object(routes.ui, "menu_item") as menu_item:
            routes._archive_items(1, docs)
        self.assertEqual(menu_item.call_count, 1)
        args = menu_item.call_args[0]
        self.assertIn("A Title", args[2])
        self.assertIn("1994", args[2])

    def test_dispatch_without_valid_handle_does_not_raise(self):
        with mock.patch.object(routes.kodi, "log") as log:
            routes.dispatch([])
        self.assertTrue(log.called)

    def test_radio_tag_unknown_section_notifies_and_ends(self):
        with mock.patch.object(routes.kodi, "notify") as notify, \
                mock.patch.object(routes.kodi, "end_directory") as end:
            routes.radio_tag(1, {"key": "missing"})
        self.assertTrue(notify.called)
        self.assertTrue(end.called)

    def test_legacy_pack_without_key_does_not_fetch(self):
        with mock.patch.object(routes.legacy, "packs") as packs, \
                mock.patch.object(routes.kodi, "notify"), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.legacy_pack(1, {})
        self.assertFalse(packs.called)

    def test_legacy_show_without_key_does_not_fetch(self):
        with mock.patch.object(routes.legacy, "jungle_tracks") as tracks, \
                mock.patch.object(routes.kodi, "notify"), \
                mock.patch.object(routes.kodi, "end_directory"):
            routes.legacy_jt_show(1, {})
        self.assertFalse(tracks.called)


if __name__ == "__main__":
    unittest.main()
