# -*- coding: utf-8 -*-
"""Rave Resolver SDK for Kodi.

Typical caller (plugin.audio.raveplayer)::

    from resolver import Resolver, ResolveError

    resolver = Resolver()
    try:
        stream = resolver.resolve(page_url)
    except ResolveError:
        ...
    item = xbmcgui.ListItem(path=stream.kodi_url())

Direct, Mediafire and Drive work entirely in-process.  Mega and Podomatic page
resolution use a native adapter when one is supplied, otherwise the optional
NAS ``/api/resolve`` service.  See ``README.md`` in this add-on and
``docs/KODI-RESOLVER.md`` in the plugin repo for the integration contract.
"""

from .base import (Adapter, AdapterNotReady, BaseAdapter, BlockedURL,
                   HostNotAllowed, InvalidURL, NotFound, ProviderError,
                   ProviderTimeout,
                   RateLimited, Resolution, ResolveError, ServiceAuthError,
                   ServiceError, ServiceProtocolError, UnsupportedURL)
from .manager import Resolver, get_resolver, reset_resolver, resolve

__version__ = "1.1.0"

__all__ = [
    "Adapter", "AdapterNotReady", "BaseAdapter", "BlockedURL", "HostNotAllowed", "InvalidURL",
    "NotFound", "ProviderError", "ProviderTimeout", "RateLimited",
    "Resolution", "ResolveError", "ServiceAuthError", "ServiceError",
    "ServiceProtocolError", "UnsupportedURL", "Resolver", "get_resolver",
    "reset_resolver", "resolve", "__version__",
]
