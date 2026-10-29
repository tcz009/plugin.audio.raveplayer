# -*- coding: utf-8 -*-
"""The researched rave catalogue that ships inside the add-on."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)


def test_catalogue_ships_with_the_addon():
    path = os.path.join(ROOT, "resources", "rave-catalog.json")
    data = json.load(open(path, encoding="utf-8"))
    assert len(data) >= 40
    for entry in data:
        assert entry["name"]
        assert entry["archive_query"]
        assert isinstance(entry["archive_count"], int)


def test_catalogue_loader_filters_empty_entries():
    from resources.lib import routes
    entries = routes._rave_catalog()
    assert entries, "loader should return archive entries"
    assert all(entry["count"] > 0 for entry in entries)
    assert all(entry["query"] for entry in entries)
    assert entries == sorted(entries, key=lambda item: item["count"], reverse=True)
