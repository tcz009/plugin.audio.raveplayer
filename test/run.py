# -*- coding: utf-8 -*-
"""Smoke-test runner: executes routes against the live sources, outside Kodi.

    python3 test/run.py root
    python3 test/run.py archive_list key=rave page=1
    python3 test/run.py archive_item id=<identifier>
    python3 test/run.py radio_tag key=oldskool
    python3 test/run.py play url=https://example/x.mp3
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)

import xbmcplugin  # noqa: E402  (stub)

from resources.lib import routes  # noqa: E402


def main(argv):
    mode = argv[1] if len(argv) > 1 else "root"
    params = {}
    for chunk in argv[2:]:
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            params[key] = value
    params["mode"] = mode
    query = "&".join("%s=%s" % (key, value) for key, value in params.items())
    routes.dispatch(["plugin://plugin.audio.raveplayer/", "1", "?" + query])

    print("mode=%s  items=%d  resolved=%d  content=%s"
          % (mode, len(xbmcplugin.ITEMS), len(xbmcplugin.RESOLVED), xbmcplugin.CONTENT[-1:] or "-"))
    for item in xbmcplugin.ITEMS[:12]:
        thumb = item["art"].get("thumb") or item["art"].get("icon") or ""
        print("  %-60.60s %s  %s" % (item["label"], "DIR" if item["isFolder"] else "PLAY", thumb[:60]))
    for item in xbmcplugin.RESOLVED:
        print("  RESOLVED", item["ok"], item["path"][:90])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
