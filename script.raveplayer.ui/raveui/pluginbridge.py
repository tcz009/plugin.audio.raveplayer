# -*- coding: utf-8 -*-
"""Read-only bridge to ``plugin.audio.raveplayer``'s data modules.

The Rave Screen never re-implements a scraper. It imports the plugin's existing
``resources/lib`` package under a private alias (``raveplayer_plugin``) so a
module name can never collide with this script add-on's own ``resources`` tree,
and calls only public read helpers:

    latest.recent_packs / latest.random_pack
    toronto.genres / toronto.tracks
    legacy.jungle_shows / legacy.jungle_tracks / legacy.packs / legacy.pack
    legacy.playable
    radio.curated / radio.stations / radio.stream_url
    archive.audio_files / archive.thumb
    http.safe_stream_url

No settings, caches, favourites, downloads or plugin directories are written.
"""

import importlib
import os
import sys
import types

PLUGIN_ID = "plugin.audio.raveplayer"
PLUGIN_ALIAS = "raveplayer_plugin"
MODULE_NAMES = ("archive", "http", "kodi", "latest", "legacy", "radio", "toronto", "ui")

_CACHE = {}


class PluginUnavailable(RuntimeError):
    """The data add-on is missing or does not expose resources/lib."""


def _xbmcaddon():
    import xbmcaddon

    return xbmcaddon


def plugin_addon(addon_factory=None):
    """Return the installed plugin's ``xbmcaddon.Addon`` object.

    ``xbmcaddon.Addon()`` with no argument means "the add-on currently running"
    — in this script that would be ``script.raveplayer.ui``, not the plugin. The
    bridge therefore always asks for the plugin id explicitly and then repairs
    the imported plugin ``kodi`` module's add-on context (settings, profile,
    icon/fanart/version) so cache and egress settings still come from the
    plugin's own configuration.
    """
    factory = addon_factory or _xbmcaddon().Addon
    try:
        return factory(PLUGIN_ID)
    except Exception as exc:  # noqa: BLE001 - missing add-on / test stub
        raise PluginUnavailable("%s is not installed (%s)" % (PLUGIN_ID, exc))


def plugin_path(addon_factory=None):
    """Return the installed plugin path, or raise :class:`PluginUnavailable`."""
    addon = plugin_addon(addon_factory)
    try:
        path = addon.getAddonInfo("path")
    except Exception as exc:  # noqa: BLE001 - missing add-on / test stub
        raise PluginUnavailable("%s has no add-on path (%s)" % (PLUGIN_ID, exc))
    path = str(path or "")
    if not path:
        raise PluginUnavailable("%s has no add-on path" % PLUGIN_ID)
    path = os.path.abspath(path)
    if not os.path.isdir(os.path.join(path, "resources", "lib")):
        raise PluginUnavailable("%s has no resources/lib at %s" % (PLUGIN_ID, path))
    return path


def _bind_addon_context(kodi_module, addon, root):
    """Point the imported plugin's ``kodi`` helpers at the plugin instance."""
    try:
        kodi_module.ADDON = addon
        kodi_module.ADDON_PATH = root
        for attribute, key in (("ADDON_ID", "id"), ("ADDON_NAME", "name"),
                               ("ADDON_VERSION", "version"), ("ICON", "icon"),
                               ("FANART", "fanart")):
            value = addon.getAddonInfo(key)
            if value:
                setattr(kodi_module, attribute, value)
    except Exception:  # noqa: BLE001 - missing metadata is not fatal
        pass


def _clear_alias(alias):
    for name in list(sys.modules):
        if name == alias or name.startswith(alias + "."):
            sys.modules.pop(name, None)


def _install_alias(alias, root):
    """Make ``root`` importable as the package ``alias``.

    The plugin package uses relative imports (``from . import kodi``); naming the
    tree ``raveplayer_plugin`` keeps those relative imports working without
    adding the plugin's ``resources`` package to this add-on's import namespace.
    """
    existing = sys.modules.get(alias)
    if existing is not None and getattr(existing, "__path__", None) == [root]:
        return
    _clear_alias(alias)
    package = types.ModuleType(alias)
    package.__path__ = [root]
    package.__package__ = alias
    package.__file__ = os.path.join(root, "__init__.py")
    sys.modules[alias] = package


def load_plugin(addon_factory=None):
    """Import the plugin data modules once and return a namespace.

    Raises :class:`PluginUnavailable` when the plugin is missing so callers can
    show a useful status line instead of a traceback.
    """
    addon = plugin_addon(addon_factory)
    root = plugin_path(addon_factory)
    cached = _CACHE.get(root)
    if cached is not None:
        return cached
    _install_alias(PLUGIN_ALIAS, root)
    modules = {}
    name = MODULE_NAMES[0]
    try:
        # Import the plugin's ``kodi`` wrapper first and repair its add-on
        # context *before* the data modules load. Those modules import ``kodi``
        # while executing (``from . import kodi``) and some cache module-level
        # copies of its constants, e.g. ``ui.DEFAULT_FANART = kodi.FANART``.
        # Binding afterwards leaves those copies pointing at the script add-on.
        kodi_module = importlib.import_module(
            "%s.resources.lib.kodi" % PLUGIN_ALIAS)
        _bind_addon_context(kodi_module, addon, root)
        modules["kodi"] = kodi_module
        for name in MODULE_NAMES:
            if name == "kodi":
                continue
            modules[name] = importlib.import_module(
                "%s.resources.lib.%s" % (PLUGIN_ALIAS, name))
    except Exception as exc:  # noqa: BLE001 - report one stable error type
        _clear_alias(PLUGIN_ALIAS)
        raise PluginUnavailable("could not import plugin %s: %s" % (name, exc))
    namespace = types.SimpleNamespace(root=root, addon=addon, **modules)
    _CACHE[root] = namespace
    return namespace


def reset_cache():
    """Drop the imported plugin modules (tests / a reinstalled plugin)."""
    _CACHE.clear()
    _clear_alias(PLUGIN_ALIAS)
