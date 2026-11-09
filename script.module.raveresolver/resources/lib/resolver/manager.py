# -*- coding: utf-8 -*-
"""Adapter selection and the in-process -> NAS fallback policy.

Order is deliberate:

1. Mediafire, Drive, Podomatic, Mega page adapters (provider-specific);
2. the Direct adapter for plain audio files;
3. the NAS service only when an adapter is missing/not ready and the failure
   is fallback-eligible.

Policy failures (private/loopback URL, malformed URL, disabled Mega) are never
sent to the service: a remote resolver must not become an SSRF bypass.
"""

from . import policy
from .base import InvalidURL, ResolveError, UnsupportedURL
from .cache import Cache
from .direct import DirectAdapter
from .drive import DriveAdapter
from .http import HttpClient
from .log import Logger
from .mediafire import MediafireAdapter
from .mega import MegaAdapter
from .podomatic import PodomaticAdapter
from .service import ServiceClient
from .settings import Settings

_DEFAULT = None


class Resolver(object):
    """Resolve a URL with in-process adapters, then the optional NAS service."""

    def __init__(self, settings=None, http=None, cache=None, logger=None,
                 adapters=None, service=None, dns_resolver=None,
                 extra_hosts=None, native_mega=None, native_podomatic=None):
        self.settings = settings or Settings()
        self.logger = logger or Logger(secrets=(self.settings.service_token,))
        self.extra_hosts = tuple(extra_hosts or ())
        self.dns_resolver = dns_resolver
        self.http = http or HttpClient(
            timeout=self.settings.http_timeout,
            dns_resolver=dns_resolver, logger=self.logger)
        self.cache = cache or Cache(
            self.settings.cache_dir, ttl=self.settings.cache_ttl)
        if adapters is None:
            adapters = [
                MediafireAdapter(self.http, self.cache, logger=self.logger),
                DriveAdapter(self.http, self.cache, logger=self.logger),
                PodomaticAdapter(native=native_podomatic,
                                 logger=self.logger),
                MegaAdapter(enabled=self.settings.enable_mega,
                            native=native_mega, logger=self.logger),
                DirectAdapter(allow_hosts=self.extra_hosts,
                              dns_resolver=dns_resolver, logger=self.logger),
            ]
        self.adapters = list(adapters)
        if service is False:
            self.service = None
        elif service is not None:
            self.service = service
        else:
            self.service = ServiceClient.from_settings(
                self.settings, self.http, logger=self.logger,
                dns_resolver=dns_resolver)

    # ------------------------------------------------------------- selection
    def provider_for(self, url):
        return policy.provider_for(url, extra_hosts=self.extra_hosts)

    def needs_resolution(self, url):
        """True only for a **known** provider page (Mediafire/Drive/etc.).

        Unknown hosts are deliberately False: live-radio and other direct
        streams must not be routed through the resolver just because they are
        not on the direct-download allowlist.  Callers that want the service to
        try an unknown provider call ``resolve()`` explicitly.
        """
        return self.provider_for(url) not in ("", "direct")

    def adapter_for(self, url, provider=None):
        name = str(provider or self.provider_for(url) or "")
        if not name:
            return None
        for adapter in self.adapters:
            if adapter.name == name:
                if not adapter.matches(url):
                    raise InvalidURL(
                        "that URL does not belong to the %s provider" % name)
                return adapter
        raise UnsupportedURL("no adapter for provider %r" % name)

    def available_providers(self):
        names = [adapter.name for adapter in self.adapters]
        if self.service is not None:
            names.append("service")
        return names

    # --------------------------------------------------------------- resolve
    def resolve(self, url, provider=None, use_service=True):
        """Resolve one URL to a :class:`Resolution`.

        Raises :class:`ResolveError` subclasses.  ``use_service=False`` forces
        in-process only (useful for diagnostics/tests).
        """
        # Syntax and literal private-address check; DNS is done by the adapter
        # that actually connects (or by the direct adapter before returning).
        policy.check_url(url, resolve_dns=False)
        name = str(provider or self.provider_for(url) or "")
        primary = None
        adapter = None
        if name:
            adapter = self.adapter_for(url, name)
        if adapter is not None:
            try:
                return adapter.resolve(url)
            except ResolveError as exc:
                primary = exc
                self.logger.debug("in-process %s failed: %s"
                                  % (adapter.name, exc.message))
                if not exc.fallback:
                    raise
        else:
            primary = UnsupportedURL("no in-process resolver for that URL")

        if (not use_service or self.service is None or primary is None
                or not primary.fallback):
            raise primary
        self.logger.debug("falling back to resolver service for %s"
                          % (name or "unknown"))
        return self.service.resolve(url, provider=name or None)

    def resolve_url(self, url, provider=None, use_service=True):
        """Convenience returning a string, or ``""`` on any resolve failure."""
        try:
            return self.resolve(url, provider=provider,
                                use_service=use_service).url
        except ResolveError:
            return ""


def get_resolver():
    """Return the process-wide default resolver (built lazily)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Resolver()
    return _DEFAULT


def reset_resolver():
    """Drop the process-wide resolver (tests/settings changes)."""
    global _DEFAULT
    _DEFAULT = None


def resolve(url, provider=None, **kwargs):
    """Module-level convenience: ``resolver.resolve(url)``."""
    return get_resolver().resolve(url, provider=provider, **kwargs)
