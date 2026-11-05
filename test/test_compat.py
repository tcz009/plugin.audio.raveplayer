# -*- coding: utf-8 -*-
"""Python 3.9-3.14 compatibility guards (Kodi 22 ships Python 3.14).

Nothing here needs a Kodi device: the checks are static/AST based plus an
import smoke test.  They fail if future code uses syntax newer than the 3.9
floor, imports a module removed from the 3.9-3.14 window, or calls a removed
standard-library API.
"""

import ast
import glob
import importlib
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)

RUNTIME_FILES = sorted(glob.glob(os.path.join(ROOT, "resources", "lib", "*.py")))
RUNTIME_FILES.append(os.path.join(ROOT, "default.py"))

# Modules removed from the standard library in the Python 3.9-3.14 window.
REMOVED_MODULES = frozenset((
    "aifc", "asynchat", "asyncore", "audioop", "cgi", "cgitb", "chunk",
    "crypt", "distutils", "imp", "lib2to3", "mailcap", "msilib", "nis",
    "nntplib", "ossaudiodev", "pipes", "smtpd", "sndhdr", "spwd", "sunau",
    "telnetlib", "uu", "xdrlib",
))

# Removed/deprecated standard-library callables that used to be common.
REMOVED_CALLS = frozenset((
    ("locale", "getdefaultlocale"),
    ("inspect", "getargspec"),
    ("time", "clock"),
    ("platform", "linux_distribution"),
))


def _runtime_sources():
    for path in RUNTIME_FILES:
        with open(path, encoding="utf-8") as handle:
            yield path, handle.read()


class Python39SyntaxTests(unittest.TestCase):
    def test_runtime_code_parses_with_the_39_grammar(self):
        for path, source in _runtime_sources():
            try:
                ast.parse(source, filename=path, feature_version=(3, 9))
            except SyntaxError as exc:  # pragma: no cover - failure path
                self.fail("%s uses syntax newer than Python 3.9: %s" % (path, exc))


class RemovedApiTests(unittest.TestCase):
    def test_no_removed_stdlib_imports(self):
        used = set()
        for path, source in _runtime_sources():
            tree = ast.parse(source, filename=path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        used.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    used.add(node.module.split(".")[0])
        self.assertEqual(used & REMOVED_MODULES, set())

    def test_no_removed_stdlib_calls(self):
        found = []
        for path, source in _runtime_sources():
            tree = ast.parse(source, filename=path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    key = (node.value.id, node.attr)
                    if key in REMOVED_CALLS:
                        found.append("%s:%s.%s" % (path, key[0], key[1]))
        self.assertEqual(found, [])


class ImportSmokeTests(unittest.TestCase):
    def test_every_runtime_module_imports(self):
        for path in RUNTIME_FILES:
            name = os.path.basename(path)[:-3]
            if name == "__init__" or name == "default":
                continue
            importlib.import_module("resources.lib." + name)

    def test_entry_point_module_imports(self):
        # default.py runs routes.dispatch only under __main__.
        importlib.import_module("resources.lib.routes")


class EntryPointGuardTests(unittest.TestCase):
    """K1: default.py has a last-resort guard and routes dispatch to the handler."""

    def setUp(self):
        # Load the add-on entry point by path.  ``import default`` resolved to
        # script.raveplayer.ui/default.py whenever that directory happened to
        # be on sys.path (test_rave_screen inserts it), so this test depended
        # on module discovery order and failed under a shuffled run.
        import importlib.util

        path = os.path.join(ROOT, "default.py")
        spec = importlib.util.spec_from_file_location("raveplayer_entry", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.entry = module

    def test_main_swallows_a_dispatch_error(self):
        with mock.patch.object(self.entry.routes, "dispatch",
                               side_effect=RuntimeError("boom")), \
                mock.patch.object(self.entry.kodi, "log") as log:
            self.entry.main(["plugin://x/", "1", "?mode=root"])
        self.assertTrue(log.called)

    def test_main_passes_argv_through(self):
        argv = ["plugin://x/", "2", "?mode=root"]
        with mock.patch.object(self.entry.routes, "dispatch") as dispatch:
            self.entry.main(argv)
        self.assertEqual(dispatch.call_args[0][0], argv)


if __name__ == "__main__":
    unittest.main()
