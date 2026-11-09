# -*- coding: utf-8 -*-
"""Bridge to ``plugin.audio.raveplayer``'s public data and playback helpers.

The Rave Screen never re-implements a scraper. It imports the plugin's existing
``resources/lib`` package under a private alias (``raveplayer_plugin``) so a
module name can never collide with this script add-on's own ``resources`` tree,
and calls only public helpers:

    latest.recent_packs / latest.random_pack
    toronto.genres / toronto.tracks
    legacy.jungle_shows / legacy.jungle_tracks / legacy.packs / legacy.pack
    legacy.categories / category_page / all_packs / post / playable
    radio.curated / radio.stations / radio.stream_url / radio.display
    archive.search / audio_files / thumb
    dnbradio.mixes / stream_url
    moxser.mixes / mix
    hardscore.items / page
    getdarker.items
    feeds.registry / episodes
    pirate.entries
    legacyblog.sources / posts / post
    routes.classic_filters / classic_raves / classic_radio_sections /
    classic_archive_sections / classic_years /
    web_source_page / web_live_stations
    favourites.load / add / remove / has / key
    downloads.eligible / plan / download / list_downloads / delete / format_size
    handoff.platform_kind / target
    http.safe_stream_url

The bridge imports the same package as the plugin, so writing favourites or
downloads goes through the plugin's own profile paths and locks.  The screen
never writes settings or cache keys of its own.
"""

import importlib
import os
import sys
import threading
import types

PLUGIN_ID = "plugin.audio.raveplayer"
PLUGIN_ALIAS = "raveplayer_plugin"
MODULE_NAMES = (
    "archive", "http", "kodi", "latest", "legacy", "radio", "toronto", "ui",
    "favourites", "downloads", "feeds", "moxser", "hardscore", "getdarker",
    "dnbradio", "pirate", "handoff", "live", "nowplaying", "spinner",
    "routes", "legacyblog", "webapi",
)

_CACHE = {}
_IMPORT_LOCK = threading.Lock()


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


class _PluginNamespace(object):
    """Lazy view over the plugin's ``resources/lib`` modules.

    3.9.52: the shell used to import all twenty data modules during window
    init (about a third of a second on the Shield), even though painting Home
    needs none of them.  Only ``kodi`` is imported eagerly, because its add-on
    context must be repaired *before* any data module caches a constant such
    as ``ui.DEFAULT_FANART``; every other module is imported on first
    attribute access and kept on the namespace.
    """

    def __init__(self, root, addon, alias, loaded):
        self.root = root
        self.addon = addon
        self._alias = alias
        self._loaded = loaded

    def _module(self, name):
        module = self._loaded.get(name)
        if module is not None:
            return module
        with _IMPORT_LOCK:
            module = self._loaded.get(name)
            if module is None:
                module = importlib.import_module(
                    "%s.resources.lib.%s" % (self._alias, name))
                self._loaded[name] = module
        return module

    def __getattr__(self, name):
        if name.startswith("_") or name not in MODULE_NAMES:
            raise AttributeError(name)
        return self._module(name)

    def __dir__(self):
        return sorted(set(list(self.__dict__) + list(MODULE_NAMES) +
                          ["root", "addon"]))


def load_plugin(addon_factory=None):
    """Return a lazy namespace over the plugin data modules.

    Raises :class:`PluginUnavailable` when the plugin is missing so callers can
    show a useful status line instead of a traceback.

    The whole check/repair/install sequence runs under ``_IMPORT_LOCK``: the
    idle prefetch thread and the GUI opening a room can call this at the same
    time, and an unlocked ``_install_alias``/``_clear_alias`` pair could leave
    duplicate package objects or a transient :class:`PluginUnavailable`.
    """
    with _IMPORT_LOCK:
        return _load_plugin_locked(addon_factory)


def _load_plugin_locked(addon_factory=None):
    addon = plugin_addon(addon_factory)
    root = plugin_path(addon_factory)
    cached = _CACHE.get(root)
    if cached is not None:
        return cached
    _install_alias(PLUGIN_ALIAS, root)
    try:
        # Import the plugin's ``kodi`` wrapper first and repair its add-on
        # context *before* any data module loads. Those modules import ``kodi``
        # while executing (``from . import kodi``) and some cache module-level
        # copies of its constants, e.g. ``ui.DEFAULT_FANART = kodi.FANART``.
        # Binding afterwards leaves those copies pointing at the script add-on.
        kodi_module = importlib.import_module(
            "%s.resources.lib.kodi" % PLUGIN_ALIAS)
        _bind_addon_context(kodi_module, addon, root)
    except Exception as exc:  # noqa: BLE001 - report one stable error type
        _clear_alias(PLUGIN_ALIAS)
        raise PluginUnavailable("could not import plugin kodi: %s" % exc)
    namespace = _PluginNamespace(root, addon, PLUGIN_ALIAS,
                                 {"kodi": kodi_module})
    _CACHE[root] = namespace
    return namespace


def reset_cache():
    """Drop the imported plugin modules (tests / a reinstalled plugin)."""
    _CACHE.clear()
    _clear_alias(PLUGIN_ALIAS)
